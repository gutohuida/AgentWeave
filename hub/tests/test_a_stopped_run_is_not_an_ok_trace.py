"""F792: a run that did not complete does not read `ok`.

`finish_run` gave the root `ok` to every run that was not `failed`, so a turn the operator stopped
listed and opened exactly like one that completed. OTel keeps `error` for failures: a run that was
stopped, interrupted or abandoned ends `unset` with a message naming how it ended, and the summary
carries the run's own status so the list and the drawer can say so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub import traces
from hub.db.engine import async_session_factory
from hub.db.models import Run, TraceSpan

PROJECT = "proj-test"


async def _ended_run(run_id: str, status: str) -> TraceSpan:
    started = datetime.now(timezone.utc) - timedelta(seconds=30)
    async with async_session_factory() as db:
        run = Run(
            id=run_id, project_id=PROJECT, agent="tracer", status="running", started_at=started
        )
        db.add(run)
        traces.start_run(db, run, prompt="go", runner="claude", model="haiku")
        await db.commit()
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = status
        run.ended_at = started + timedelta(seconds=10)
        await traces.finish_run(db, run_id)
        await db.commit()
    async with async_session_factory() as db:
        return await db.get(TraceSpan, traces.root_span_id(run_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("stopped", "stopped by the operator"),
        ("interrupted", "interrupted"),
        ("abandoned", "abandoned"),
    ],
)
async def test_a_run_that_did_not_complete_is_not_ok(app, status, message):
    root = await _ended_run(f"run-f792-{status}", status)
    assert root.ended is True
    assert root.status == "unset"
    assert root.status_message == message
    assert root.attributes["aw.run.status"] == status


@pytest.mark.asyncio
async def test_a_completed_run_is_still_ok(app):
    root = await _ended_run("run-f792-completed", "completed")
    assert root.status == "ok" and root.status_message is None


@pytest.mark.asyncio
async def test_the_summary_carries_the_runs_own_status(app, auth_headers):
    await _ended_run("run-f792-listed", "stopped")
    listed = await app.get(f"/api/v1/projects/{PROJECT}/traces", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (summary,) = [t for t in listed.json()["traces"] if t["run_id"] == "run-f792-listed"]
    assert summary["run_status"] == "stopped"
