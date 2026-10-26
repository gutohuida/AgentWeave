"""Trace spans are kept for a bounded window (`trace-retention`, `retention-no-stall`, D4).

The Hub deletes spans older than the project's retention window on its own, in small batches off
the request path; the operator sets the window in the project's trace settings. Agent outputs,
events, messages and runs are history and are never touched.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, func, select, text

from hub import db_maintenance, trace_retention
from hub.db.engine import async_session_factory, engine
from hub.db.models import EventLog, TraceSpan

from .conftest import TEST_PROJECT_ID

PROJECT = TEST_PROJECT_ID
NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
SETTINGS = f"/api/v1/projects/{PROJECT}/traces/settings"


def _span(project: str, start: datetime, name: str = "s") -> TraceSpan:
    return TraceSpan(
        span_id=uuid.uuid4().hex[:16],
        trace_id=uuid.uuid4().hex,
        project_id=project,
        name=name,
        operation="aw.request",
        start_time=start,
        trace_started_at=start,
        attributes={"pad": "x" * 200},
        events=[],
    )


async def _add(*spans: TraceSpan) -> None:
    async with async_session_factory() as db:
        db.add_all(spans)
        await db.commit()


async def _names(project: str = PROJECT) -> set:
    async with async_session_factory() as db:
        rows = await db.execute(select(TraceSpan.name).where(TraceSpan.project_id == project))
        return set(rows.scalars())


async def test_spans_older_than_the_default_window_go_and_newer_ones_stay(app) -> None:
    window = timedelta(days=trace_retention.DEFAULT_RETENTION_DAYS)
    await _add(
        _span(PROJECT, NOW - window - timedelta(days=30), "ancient"),
        _span(PROJECT, NOW - window - timedelta(seconds=1), "just-expired"),
        _span(PROJECT, NOW - window + timedelta(seconds=1), "just-kept"),
        _span(PROJECT, NOW - timedelta(minutes=5), "recent"),
        # A span that starts long before its trace did (`aw.deliver` does, by up to ~18h on the
        # operator's data) is judged by its own start, not its trace's.
        _span(PROJECT, NOW - timedelta(days=1), "own-start"),
    )
    report = await trace_retention.sweep(now=NOW)
    assert await _names() == {"just-kept", "recent", "own-start"}
    assert report[PROJECT]["deleted"] == 2
    assert report[PROJECT]["window_days"] == trace_retention.DEFAULT_RETENTION_DAYS
    assert report[PROJECT]["cutoff"] == NOW - window


async def test_the_window_is_the_projects_and_the_next_sweep_honours_a_change(
    app, auth_headers
) -> None:
    got = (await app.get(SETTINGS, headers=auth_headers)).json()
    assert got["retention_days"] == trace_retention.DEFAULT_RETENTION_DAYS
    assert got["retention_days_default"] == trace_retention.DEFAULT_RETENTION_DAYS
    await _add(
        _span(PROJECT, NOW - timedelta(days=5), "five-days"),
        _span(PROJECT, NOW - timedelta(days=2), "two-days"),
        _span("proj-other", NOW - timedelta(days=5), "other-project"),
    )
    put = await app.put(SETTINGS, json={"retention_days": 3}, headers=auth_headers)
    assert put.status_code == 200, put.text
    assert put.json()["retention_days"] == 3
    await trace_retention.sweep(now=NOW)
    assert await _names() == {"two-days"}
    assert await _names("proj-other") == {"other-project"}  # its own, default window

    put = await app.put(SETTINGS, json={"retention_days": 1}, headers=auth_headers)
    assert put.status_code == 200, put.text
    await trace_retention.sweep(now=NOW)
    assert await _names() == set()

    reset = await app.put(SETTINGS, json={"retention_days": None}, headers=auth_headers)
    assert reset.json()["retention_days"] == trace_retention.DEFAULT_RETENTION_DAYS


async def test_a_window_outside_its_bounds_is_refused(app, auth_headers) -> None:
    for days in (0, -1, trace_retention.MAX_RETENTION_DAYS + 1):
        put = await app.put(SETTINGS, json={"retention_days": days}, headers=auth_headers)
        assert put.status_code == 422, (days, put.text)


async def test_the_sweep_touches_nothing_but_trace_spans(app) -> None:
    async with async_session_factory() as db:
        db.add(
            EventLog(
                id="evt-retention-old",
                project_id=PROJECT,
                event_type="context_warning",
                agent="a",
                data={},
                timestamp=NOW - timedelta(days=400),
            )
        )
        await db.commit()
    await trace_retention.sweep(now=NOW)
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(EventLog)) >= 1


async def test_a_large_backlog_is_deleted_in_small_transactions_readers_run_between(app) -> None:
    """The first sweep on the operator's database removes tens of thousands of spans: it must
    never be one delete, and a reader must get in while it runs (retention-no-stall)."""
    old = NOW - timedelta(days=60)
    backlog = trace_retention.BATCH_SIZE * 4 + 7
    async with async_session_factory() as db:
        await db.execute(
            TraceSpan.__table__.insert(),
            [
                {
                    "span_id": f"{i:016x}",
                    "trace_id": f"{i:032x}",
                    "project_id": PROJECT,
                    "name": "old",
                    "operation": "aw.request",
                    "status": "unset",
                    "start_time": old,
                    "trace_started_at": old,
                    "ended": True,
                    "attributes": {"pad": "x" * 500},
                    "events": [],
                }
                for i in range(backlog)
            ],
        )
        await db.commit()

    deletes: list = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("DELETE FROM TRACE_SPANS"):
            deletes.append(cursor.rowcount)

    event.listen(engine.sync_engine, "after_cursor_execute", _count)
    reads: list = []
    try:
        sweeping = asyncio.create_task(trace_retention.sweep(now=NOW))
        while not sweeping.done():
            started = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT count(*) FROM agent_outputs"))
            reads.append((started, sweeping.done()))
            await asyncio.sleep(0.005)
        report = await sweeping
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", _count)
    assert report[PROJECT]["deleted"] == backlog
    assert len(deletes) >= 5
    assert max(deletes) <= trace_retention.BATCH_SIZE
    assert any(not done for _, done in reads), "no read ran while the sweep was in progress"
    assert await _names() == set()


async def test_the_maintenance_pass_sweeps_then_refreshes_statistics(app, monkeypatch) -> None:
    calls: list = []

    async def _sweep(now=None):  # noqa: ANN001
        calls.append("sweep")
        return {}

    async def _stats():
        calls.append("stats")

    monkeypatch.setattr(trace_retention, "sweep", _sweep)
    monkeypatch.setattr(db_maintenance, "refresh_statistics", _stats)
    await db_maintenance.run_pass(statistics_due=True)
    await db_maintenance.run_pass(statistics_due=False)
    assert calls == ["sweep", "stats", "sweep"]


async def test_a_failing_sweep_does_not_end_the_maintenance_loop(app, monkeypatch) -> None:
    passes: list = []

    async def _sweep(now=None):  # noqa: ANN001
        passes.append(1)
        raise RuntimeError("boom")

    async def _stats():
        return None

    monkeypatch.setattr(trace_retention, "sweep", _sweep)
    monkeypatch.setattr(db_maintenance, "refresh_statistics", _stats)
    monkeypatch.setattr(db_maintenance, "FIRST_PASS_DELAY_SECONDS", 0)
    monkeypatch.setattr(db_maintenance, "PASS_INTERVAL_SECONDS", 0.01)
    task = asyncio.create_task(db_maintenance.maintain_forever())
    try:
        deadline = time.monotonic() + 10
        while len(passes) < 3 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    assert len(passes) >= 3
