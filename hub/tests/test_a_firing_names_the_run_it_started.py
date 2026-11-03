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
