"""`the-build-card-shows-where-check-time-went` (FR-2, FR-3, FR-4): the build figures route counts
every check run whole, keeps timeouts out of failed, reads an unrecorded slot as unknown, and gives
the wait from approval to landing. Rows are written by hand so each expected figure is arithmetic.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Build, TaskCheckRun, TaskLanding, TaskTransition

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    P,
    _approved,
    _build,
    _document,
    _move,
    _roster_rows,
    _tasks_by_key,
    author_headers,  # noqa: F401, F811 -- a fixture, used by name
)

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
H = 3600


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _tasks(n: int):
    return [
        {"key": f"t{i}", "description": f"Build {i}", "requirements": ["alpha"]}
        for i in range(1, n + 1)
    ]


async def _approved_build(app, auth_headers, author_headers, approvals):  # noqa: F811
    """A build whose tasks t1.. are approved at the given offsets (seconds from T0); its start is T0."""
    await _roster_rows("dev")
    await _approved(app, auth_headers, author_headers, _document(tasks=_tasks(len(approvals))))
    built = await _build(app, auth_headers, driver="hand", level="fast")
    assert built.status_code == 200, built.text
    build_id = built.json()["build_outcome"]["build"]["id"]
    tasks = await _tasks_by_key()
    for key, when in zip(sorted(tasks), approvals, strict=True):
        task = tasks[key]
        for status in ("in_progress", "completed", "approved"):
            await _move(task.id, status, "dev", run_id=f"run-{key}")
        async with async_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(TaskTransition)
                        .where(TaskTransition.task_id == task.id)
                        .order_by(TaskTransition.sequence)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                row.created_at = _at(when if row is rows[-1] else 0)
            await db.commit()
    async with async_session_factory() as db:
        build = await db.get(Build, build_id)
        build.created_at = T0
        await db.commit()
    return build_id, tasks


def _check(task_id, name, began, ended, slot=None, state="passed", **extra):
    return TaskCheckRun(
        id=name,
        project_id=P,
        task_id=task_id,
        main_sha="a",
        target_shas=[],
        state=state,
        results=extra.pop("results", []),
        error="",
        started_at=_at(began),
        slot_at=None if slot is None else _at(slot),
        ended_at=_at(ended),
        **extra,
    )


async def _figures(app, auth_headers, build_id):
    read = await app.get(f"{BASE}/builds/{build_id}/figures", headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()


@pytest.mark.asyncio
async def test_check_time_is_counted_whole_and_a_timeout_is_not_a_failure(
    app, auth_headers, author_headers  # noqa: F811
):
    """Three tasks build for 1 h; their check runs total 2 h (queued 30 min of it), one timed out."""
    build_id, tasks = await _approved_build(app, auth_headers, author_headers, [H, H, H])
    t1, t2, t3 = (tasks[k].id for k in ("t1", "t2", "t3"))
    async with async_session_factory() as db:
        db.add_all(
            [
                _check(t1, "c1", 0, 2400, slot=600),  # waited 600 s, ran 1800 s
                _check(t2, "c2", 0, 2400, slot=1200, state="failed"),  # waited 1200, ran 1200
                _check(
                    t3,
                    "c3",
                    0,
                    2400,
                    slot=0,
                    state="failed",
                    results=[{"name": "slow", "timed_out": True}],
                ),  # ran 2400 s and timed out
            ]
        )
        await db.commit()

    figures = await _figures(app, auth_headers, build_id)

    checks = figures["checks"]
    assert checks["running_seconds"] + checks["waiting_seconds"] == 3 * 2400 == checks["seconds"]
    assert (checks["waiting_seconds"], checks["no_slot_runs"]) == (1800, 0)
    assert (checks["runs"], checks["passed"], checks["failed"], checks["timed_out"]) == (3, 1, 1, 1)
    assert sum(figures["time"].values()) == H, "the wall bar still sums to the build's wall time"


@pytest.mark.asyncio
async def test_a_run_with_no_slot_time_is_running_and_its_wait_is_unknown(
    app, auth_headers, author_headers  # noqa: F811
):
    build_id, tasks = await _approved_build(app, auth_headers, author_headers, [H, H])
    async with async_session_factory() as db:
        db.add(_check(tasks["t1"].id, "old1", 0, 600))
        db.add(_check(tasks["t2"].id, "old2", 0, 300))
        await db.commit()
    checks = (await _figures(app, auth_headers, build_id))["checks"]
    assert checks["waiting_seconds"] is None
    assert (checks["running_seconds"], checks["no_slot_runs"]) == (900, 2)

    async with async_session_factory() as db:
        db.add(_check(tasks["t1"].id, "new1", 700, 1000, slot=760))
        await db.commit()
    checks = (await _figures(app, auth_headers, build_id))["checks"]
    assert checks["waiting_seconds"] == 60
    assert (checks["running_seconds"], checks["no_slot_runs"]) == (900 + 240, 2)


@pytest.mark.asyncio
async def test_landing_wait_is_the_time_from_last_approval_to_landing(
    app, auth_headers, author_headers  # noqa: F811
):
    """t1 approved 11:40, landed 16:58 (5 h 18 m); t2 landed after 10 min; t3 approved, not landed."""
    at = 2 * H + 40 * 60  # 11:40 when T0 is 09:00
    build_id, tasks = await _approved_build(app, auth_headers, author_headers, [at, at, at])
    async with async_session_factory() as db:
        for key, minutes in (("t1", 5 * 60 + 18), ("t2", 10)):
            db.add(
                TaskLanding(
                    id=f"land-{key}",
                    project_id=P,
                    task_id=tasks[key].id,
                    state="landed",
                    order_key=1.0,
                    created_at=_at(at),
                    ended_at=_at(at + minutes * 60),
                )
            )
        await db.commit()

    landing = (await _figures(app, auth_headers, build_id))["landing"]

    assert landing["landed"] == 2
    assert landing["longest_seconds"] == (5 * 60 + 18) * 60
    assert landing["total_seconds"] == (5 * 60 + 28) * 60
    assert landing["waiting"] == 1
    assert landing["longest_waiting_seconds"] > 0
