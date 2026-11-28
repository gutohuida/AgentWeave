"""`screens-stop-repeating-work-on-every-read` (`ledger-tally-scoped`): the work tally issues the
same SQL statements however much history the project holds, and loads only the columns it reads."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event

from hub import work_tally
from hub.db.engine import async_session_factory, engine
from hub.db.models import Build, Run, SpecDocument, Task, TaskTransition, TurnUsage

from .test_a_build_has_a_driver_a_level_and_its_people import P

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


async def _grow(start: int, count: int) -> None:
    async with async_session_factory() as db:
        for i in range(start, start + count):
            doc = f"spdoc-tq{i}"
            db.add(
                SpecDocument(
                    id=doc, project_id=P, path=f"spec/changes/tq{i}/spec.json", title=f"T{i}"
                )
            )
            db.add(
                Build(
                    id=f"build-tq{i}",
                    project_id=P,
                    document_id=doc,
                    driver="hand",
                    level="reviewed",
                    state="finished",
                    created_at=T0,
                )
            )
            await db.flush()
            db.add(
                Task(
                    id=f"task-tq{i}",
                    project_id=P,
                    title="t",
                    status="approved",
                    build_id=f"build-tq{i}",
                    spec_document_id=doc,
                )
            )
            await db.flush()
            for seq, (a, b) in enumerate(
                [("pending", "in_progress"), ("in_progress", "completed")], start=1
            ):
                db.add(
                    TaskTransition(
                        id=f"tr-tq{i}-{seq}",
                        project_id=P,
                        task_id=f"task-tq{i}",
                        from_status=a,
                        to_status=b,
                        actor_kind="agent",
                        created_at=T0 + timedelta(seconds=seq),
                    )
                )
            db.add(
                Run(
                    id=f"run-tq{i}",
                    project_id=P,
                    agent="dev",
                    task_id=f"task-tq{i}",
                    status="completed",
                    started_at=T0,
                    ended_at=T0 + timedelta(seconds=5),
                )
            )
            await db.flush()
            db.add(
                TurnUsage(
                    id=f"usage-tq{i}",
                    run_id=f"run-tq{i}",
                    project_id=P,
                    agent="dev",
                    status="measured",
                    total_tokens=1,
                    api_equivalent_usd_micros=5,
                    observed_at=T0,
                )
            )
        await db.commit()


async def _count(**kw) -> int:
    """The statements the tally's own session issues: the listener is on the shared engine, so
    anything else in this worker that touches the database while the tally runs is not counted."""
    seen: list[str] = []
    own: list = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if own and conn is own[0]:
            seen.append(statement)

    sa_event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        async with async_session_factory() as db:
            own.append((await db.connection()).sync_connection)
            await work_tally.tally(db, P, **kw)
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", capture)
    return len(seen)


@pytest.mark.asyncio
async def test_queries_flat_in_history(app, auth_headers):
    await _grow(0, 2)
    small_whole = await _count()
    small_build = await _count(build_id="build-tq0")
    small_spend = await _count(spend_only=True)
    assert small_spend < small_whole
    await _grow(2, 4)
    assert await _count() == small_whole
    assert await _count(build_id="build-tq0") == small_build
    assert await _count(spend_only=True) == small_spend
    whole = None
    async with async_session_factory() as db:
        whole = await work_tally.tally(db, P)
    assert whole["builds"]["build-tq3"]["runs"]["total"] == 1


@pytest.mark.asyncio
async def test_spend_only_tally_gives_the_same_spend(app, auth_headers):
    await _grow(0, 3)
    async with async_session_factory() as db:
        whole = await work_tally.tally(db, P)
        lean = await work_tally.tally(db, P, spend_only=True)
    assert lean["project"] == whole["project"]
    assert lean["workers"] == whole["workers"]
    assert lean["spend"] == whole["spend"]
    assert [g["row"] for g in lean["groups"]["agent"]] == [
        g["row"] for g in whole["groups"]["agent"]
    ]
