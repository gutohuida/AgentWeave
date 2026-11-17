"""Each landing batch's record, and the dashboard every project has
(`landing-time-and-test-flakiness-are-measured`, FR-7, FR-8).

The seams: a batch landed end to end by `landing_queue.drain` with real git and a real pytest check
(the fixtures of `test_a_failing_batch_is_narrowed`), read back through the dashboard query route
and the dashboard's own panels; and a project created through `ProjectLifecycleService`. Migration
0181 on an existing project is `test_migration_0181_landing_record`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from hub import landing_dashboard
from hub.db.engine import async_session_factory
from hub.db.models import LandingBatch, TaskLanding
from hub.project_lifecycle import ProjectLifecycleService

from .test_a_failing_batch_is_narrowed import (  # noqa: F401 -- the autouse gather window
    _a_long_gather_window,
    _approve,
    _batches,
    _project,
    _repo,
    _tasks,
)
from .test_a_landing_failure_is_blamed_only_where_it_reproduces import _failing_times

P = "proj-test"
OP = f"/api/v1/projects/{P}/dashboards"


def _by_name(columns, row) -> dict:
    return dict(zip(columns, row, strict=True))


async def _seeded_dashboard(app, auth_headers, project_id: str) -> dict:
    listed = await app.get(f"/api/v1/projects/{project_id}/dashboards", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    named = [d for d in listed.json()["dashboards"] if d["name"] == landing_dashboard.NAME]
    assert len(named) == 1, listed.json()
    ran = await app.get(
        f"/api/v1/projects/{project_id}/dashboards/{named[0]['id']}/run", headers=auth_headers
    )
    assert ran.status_code == 200, ran.text
    return ran.json()


def _no_panel_errors(run: dict) -> None:
    assert [p["title"] for p in run["panels"]] == [p["title"] for p in landing_dashboard.PANELS]
    assert [p["error"] for p in run["panels"]] == [None] * len(run["panels"]), run["panels"]


@pytest.mark.asyncio
async def test_a_landed_batch_records_its_wait_its_check_runs_and_its_outcome(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-batch-record: the task was approved 2 minutes before the batch formed, and the batch's
    check failed once and passed on its confirmation re-run. Read through the dashboard query route:
    a wait of about 2 minutes, 2 or more check runs, outcome landed."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    counter = tmp_path_factory.mktemp("counters") / "flaky.txt"
    _repo(tmp_path, ledger, _failing_times("flaky", counter, 1))
    await _project()
    [task_id], _ = await _tasks(tmp_path, [({"one.py": "x = 1\n"}, None)])
    await _approve(app, auth_headers, task_id)
    async with async_session_factory() as session:
        [landing] = (
            (await session.execute(select(TaskLanding).where(TaskLanding.task_id == task_id)))
            .scalars()
            .all()
        )
        landing.created_at = landing.created_at - timedelta(minutes=2)  # ready 2 minutes ago
        await session.commit()

    from hub import landing_queue

    await landing_queue.drain()

    [batch] = await _batches()
    assert batch.state == "landed", (batch.state, batch.error)
    assert counter.read_text(encoding="utf-8") == "0", "premise: the first run failed test_flaky"
    queried = await app.post(
        f"{OP}/query", json={"sql": landing_dashboard.BATCHES_SQL}, headers=auth_headers
    )
    assert queried.status_code == 200, queried.text
    body = queried.json()
    [row] = [_by_name(body["columns"], r) for r in body["rows"]]
    assert row["batch"] == batch.id
    assert 1.9 <= row["wait (min)"] <= 2.5, row
    assert row["check runs"] >= 2, row
    assert isinstance(row["check time (min)"], float), row
    assert row["outcome"] == "landed", row
    assert batch.ready_at is not None and batch.slot_at is not None
    assert batch.checks_ended_at is not None and batch.checks_ended_at >= batch.slot_at


@pytest.mark.asyncio
async def test_a_batch_from_before_the_record_reads_not_recorded_never_zero(app, auth_headers):
    """ac-old-batch-null: a batch with none of the record's fields; the dashboard shows its wait,
    check time and check runs as 'not recorded', and leaves it out of the median and the line."""
    async with async_session_factory() as session:
        session.add(
            LandingBatch(
                id="lbat-old000000001",
                project_id=P,
                base_sha="0" * 40,
                state="landed",
                task_ids=[],
                prefixes=[],
                results=[],
                narrowing=[],
            )
        )
        await landing_dashboard.seed(session, P)
        await session.commit()

    run = await _seeded_dashboard(app, auth_headers, P)
    _no_panel_errors(run)
    batches, median, over_time, flakiest = run["panels"]
    [row] = [_by_name(batches["columns"], r) for r in batches["rows"]]
    assert row["wait (min)"] == "not recorded", row
    assert row["check time (min)"] == "not recorded", row
    assert row["check runs"] == "not recorded", row
    assert row["outcome"] == "landed", row
    assert median["rows"] == [[None]], median
    assert over_time["rows"] == [], over_time
    assert flakiest["rows"] == [], flakiest


@pytest.mark.asyncio
async def test_a_new_project_has_the_dashboard_and_every_panel_runs_on_it_empty(
    app, auth_headers, tmp_path
):
    """ac-dashboard-every-project, a new empty project: created, it has the dashboard, and every
    panel runs with no error on no batches and no history."""
    async with async_session_factory() as session:
        created = await ProjectLifecycleService(session).create_new(tmp_path / "fresh")
    run = await _seeded_dashboard(app, auth_headers, created.id)
    _no_panel_errors(run)
    assert [len(p["rows"]) for p in run["panels"]] == [0, 1, 0, 0]


async def test_seeding_twice_keeps_one_dashboard(app):
    async with async_session_factory() as session:
        await landing_dashboard.seed(session, P)
        await session.commit()
        await landing_dashboard.seed(session, P)
        await session.commit()
        from hub.db.models import Dashboard

        named = (
            (
                await session.execute(
                    select(Dashboard).where(
                        Dashboard.project_id == P, Dashboard.name == landing_dashboard.NAME
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(named) == 1
