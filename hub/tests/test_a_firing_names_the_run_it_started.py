"""A job or loop firing names the run it started, so the operator can open that run's trace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, JobRun, Run

JOBS = "/api/v1/projects/proj-test/jobs"


async def _seed(app, auth_headers):
    created = await app.post(
        JOBS,
        json={"name": "trace-firings", "agent": "kimi", "message": "go", "cron": "0 9 * * *"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    base = datetime.now(timezone.utc) - timedelta(hours=3)
    async with async_session_factory() as session:
        for n in (1, 2):
            session.add(
                Conversation(
                    id=f"conv-fr-{n}",
                    project_id=project_id,
                    agent="kimi",
                    provider_session_id=f"conv-fr-{n}",
                    lifecycle="open",
                )
            )
        # Oldest to newest: a run-backed firing, a skipped one (no run), a second run-backed one.
        firings = [
            ("jr-fr-1", 0, "completed", "conv-fr-1"),
            ("jr-fr-2", 1, "skipped", None),
            ("jr-fr-3", 2, "completed", "conv-fr-2"),
        ]
        for jr_id, hours, status, conversation in firings:
            session.add(
                JobRun(
                    id=jr_id,
                    job_id=job_id,
                    project_id=project_id,
                    fired_at=base + timedelta(hours=hours),
                    status=status,
                    trigger="scheduled",
                    conversation_id=conversation,
                )
            )
        for run_id, hours, conversation in (
            ("run-fr-1", 0, "conv-fr-1"),
            ("run-fr-3", 2, "conv-fr-2"),
        ):
            session.add(
                Run(
                    id=run_id,
                    project_id=project_id,
                    agent="kimi",
                    conversation_id=conversation,
                    status="completed",
                    started_at=base + timedelta(hours=hours, seconds=2),
                    turn_depth=0,
                )
            )
        await session.commit()
    return job_id


@pytest.mark.asyncio
async def test_history_names_each_firings_run_newest_first(app, auth_headers):
    job_id = await _seed(app, auth_headers)

    resp = await app.get(f"{JOBS}/{job_id}/history", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    # Newest first: reversing the route's order changes this list and fails the test.
    assert [(r["id"], r["run_id"]) for r in resp.json()] == [
        ("jr-fr-3", "run-fr-3"),
        ("jr-fr-2", None),
        ("jr-fr-1", "run-fr-1"),
    ]
    assert resp.json()[0]["conversation_id"] == "conv-fr-2"


@pytest.mark.asyncio
async def test_job_detail_history_carries_the_same_run_ids(app, auth_headers):
    job_id = await _seed(app, auth_headers)

    resp = await app.get(f"{JOBS}/{job_id}", headers=auth_headers)

    assert [(r["id"], r["run_id"]) for r in resp.json()["history"]] == [
        ("jr-fr-3", "run-fr-3"),
        ("jr-fr-2", None),
        ("jr-fr-1", "run-fr-1"),
    ]


@pytest.mark.asyncio
async def test_loop_firing_runs_cover_firings_beyond_the_loops_last_ten(app, auth_headers):
    """The rail shows every open firing of a loop; the run of an old one must still resolve."""
    created = await app.post(
        JOBS,
        json={
            "name": "many-firings",
            "agent": "kimi",
            "message": "go",
            "cron": "0 9 * * *",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "First"}],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    loop = created.json()["loop"]
    job_id = created.json()["id"]
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    base = datetime.now(timezone.utc) - timedelta(days=1)
    async with async_session_factory() as session:
        for n in range(15):
            session.add(
                Conversation(
                    id=f"conv-lf-{n}",
                    project_id=project_id,
                    agent="kimi",
                    provider_session_id=f"conv-lf-{n}",
                    lifecycle="open",
                )
            )
            session.add(
                JobRun(
                    id=f"jr-lf-{n}",
                    job_id=job_id,
                    project_id=project_id,
                    fired_at=base + timedelta(hours=n),
                    status="completed",
                    trigger="scheduled",
                    conversation_id=f"conv-lf-{n}",
                )
            )
            session.add(
                Run(
                    id=f"run-lf-{n}",
                    project_id=project_id,
                    agent="kimi",
                    conversation_id=f"conv-lf-{n}",
                    status="completed",
                    started_at=base + timedelta(hours=n, seconds=2),
                    turn_depth=0,
                )
            )
        await session.commit()

    detail = await app.get(f"/api/v1/projects/proj-test/loops/{loop['id']}", headers=auth_headers)
    assert "jr-lf-0" not in [h["id"] for h in detail.json()["history"]]  # older than the last ten

    resp = await app.get(
        f"/api/v1/projects/proj-test/loops/{loop['id']}/firing-runs",
        params=[
            ("conversation_id", "conv-lf-0"),
            ("conversation_id", "conv-lf-14"),
            ("conversation_id", "nope"),
        ],
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"conv-lf-0": "run-lf-0", "conv-lf-14": "run-lf-14"}
