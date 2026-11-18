"""`a-build-view-showing-every-task-and-run-of-a-build` (FR-2, FR-4, FR-7, FR-8, FR-12): the build
view's one read, `GET /project/builds/{id}/tasks`.

The runs are the figures route's (`work_tally`), so the two agree for the same build; the tasks come
in the document's declared order, then the ones added later; a send-back sits in the task's own list
with who made it and why; evidence reads one of five states.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    RequirementEvidence,
    Run,
    SpecRequirement,
    Task,
    TaskTransition,
    TurnUsage,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

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

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


async def _run(run_id, agent, task_id, began, ended, micros, model="m", priced=True):
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent=agent,
                task_id=task_id,
                status="completed",
                started_at=_at(began),
                ended_at=_at(ended),
            )
        )
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{run_id}",
                run_id=run_id,
                project_id=P,
                agent=agent,
                status="measured",
                model=model,
                total_tokens=10,
                api_equivalent_usd_micros=micros if priced else None,
                observed_at=_at(ended),
            )
        )
        await db.commit()


async def _send_back(task_id, agent, run_id, reason_class, reason):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        await apply_transition(
            db,
            task,
            "revision_needed",
            run_actor(run_id, agent),
            reason_class=reason_class,
            reason=reason,
        )
        await db.commit()


@pytest.mark.asyncio
async def test_a_build_reads_its_tasks_in_order_with_runs_send_backs_and_evidence(
    app, auth_headers, author_headers  # noqa: F811
):
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="reviewed", builders=["dev"])
    assert built.status_code == 200, built.text
    build_id = built.json()["build_outcome"]["build"]["id"]
    tasks = await _tasks_by_key()
    t1, t2 = tasks["t1"], tasks["t2"]

    # A Hub-filed fix task joined the build later: it comes after the declared ones.
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-fix",
                project_id=P,
                title="Fix main",
                status="pending",
                build_id=build_id,
                created_at=_at(-1000),  # older than the others: order is declared first, not by age
            )
        )
        await db.commit()

    # t1: built, sent back with a defect, built again.
    await _move(t1.id, "in_progress", "dev", run_id="run-b1")
    await _move(t1.id, "completed", "dev", run_id="run-b1")
    await _move(t1.id, "under_review", "qa", run_id="run-r1")
    await _send_back(t1.id, "qa", "run-r1", "defect", "alpha does not work")
    await _move(t1.id, "in_progress", "dev", run_id="run-b2")
    # The tally names a run's role from the task's status when it began, so the moves sit on the
    # same clock as the runs.
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == t1.id)
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .all()
        )
        for row, seconds in zip(rows, (0, 90, 100, 195, 200), strict=True):
            row.created_at = _at(seconds)
        await db.commit()
    await _run("run-b1", "dev", t1.id, 0, 100, 2_000_000, model="sonnet")
    await _run("run-r1", "qa", t1.id, 100, 200, 1_000_000, model="opus")
    await _run("run-b2", "dev", t1.id, 200, 300, 0, priced=False)
    # t2: only unpriced runs.
    await _run("run-u1", "dev", t2.id, 0, 50, 0, priced=False)
    await _run("run-elsewhere", "dev", None, 0, 50, 9_000_000)  # not this build's

    async with async_session_factory() as db:
        requirement = (
            await db.execute(select(SpecRequirement).where(SpecRequirement.key == "alpha"))
        ).scalar_one()
        db.add(
            RequirementEvidence(
                id="ev-1",
                project_id=P,
                requirement_id=requirement.id,
                digest=requirement.digest,
                kind="test_result",
                actor_kind="agent",
                actor="dev",
                task_id=t1.id,
                review_state="rejected",
            )
        )
        await db.commit()

    read = await app.get(f"{BASE}/builds/{build_id}/tasks", headers=auth_headers)

    assert read.status_code == 200, read.text
    body = read.json()
    assert [t["id"] for t in body["tasks"]] == [t1.id, t2.id, "task-fix"]
    assert [t["declared"] for t in body["tasks"]] == [True, True, False]
    first, second = body["tasks"][0], body["tasks"][1]
    # Oldest first, roles as the tally names them, a cost only where one was measured.
    assert [(r["id"], r["role"], r["model"]) for r in first["runs"]] == [
        ("run-b1", "build", "sonnet"),
        ("run-r1", "review", "opus"),
        ("run-b2", "build", "m"),
    ]
    assert [r["cost_state"] for r in first["runs"]] == ["measured", "measured", "unpriced"]
    assert first["runs"][2]["cost_usd_micros"] is None
    assert [r["cost_state"] for r in second["runs"]] == ["unpriced"]
    (sb,) = first["send_backs"]
    assert (sb["by"], sb["reason_class"], sb["reason"], sb["to"]) == (
        {"kind": "agent", "agent": "qa"},
        "defect",
        "alpha does not work",
        "revision_needed",
    )
    assert first["requirements"] == [
        {"identifier": first["requirements"][0]["identifier"], "evidence": "rejected"}
    ]
    assert second["requirements"][0]["evidence"] == "missing"
    assert body["build_runs"] == []

    # The totals the view adds up are the figures route's.
    figures = (await app.get(f"{BASE}/builds/{build_id}/figures", headers=auth_headers)).json()
    runs = [r for t in body["tasks"] for r in t["runs"]] + body["build_runs"]
    assert len(runs) == figures["runs"] == 4
    assert sum(len(t["send_backs"]) for t in body["tasks"]) == figures["send_backs"] == 1
    assert figures["unpriced"] == 2
    assert figures["run_seconds"] == 100 + 100 + 100 + 50


@pytest.mark.asyncio
async def test_another_projects_build_has_no_tasks_read(app, auth_headers):
    read = await app.get(f"{BASE}/builds/build-nope/tasks", headers=auth_headers)
    assert read.status_code == 404
