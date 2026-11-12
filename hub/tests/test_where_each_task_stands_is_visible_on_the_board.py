"""One true stage per card (`where-each-task-stands-is-visible-on-the-board`, FR-9..FR-16): the
tasks route reports each task's stage from bound runs, landing rows, questions and prerequisites,
when it entered the stage, and what it waits on. Every assertion reads the route."""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Question, Run, Task, TaskDependency, TaskLanding

P = "proj-test"
_n = iter(range(1, 10_000))


async def _add(*rows) -> None:
    async with async_session_factory() as db:
        db.add_all(rows)
        await db.commit()


async def _task(status: str, **kw) -> str:
    n = next(_n)
    await _add(Task(id=f"task-stage-{n}", project_id=P, title=f"t{n}", status=status, **kw))
    return f"task-stage-{n}"


async def _landing(task_id: str, state: str, **kw) -> None:
    n = next(_n)
    await _add(
        TaskLanding(
            id=f"landing-stage-{n}",
            project_id=P,
            task_id=task_id,
            state=state,
            order_key=float(n),
            **kw,
        )
    )


async def _run(task_id: str, agent: str = "worker") -> None:
    await _add(
        Run(
            id=f"run-stage-{next(_n)}", project_id=P, agent=agent, status="running", task_id=task_id
        )
    )


async def _row(app, auth_headers, task_id: str) -> dict:
    listed = await app.get(f"/api/v1/projects/{P}/tasks", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (row,) = [t for t in listed.json()["tasks"] if t["id"] == task_id]
    return row


@pytest.mark.asyncio
async def test_an_approved_task_is_on_main_only_once_it_has_landed(app, auth_headers):
    task_id = await _task("approved")
    await _landing(task_id, "checking")
    assert (await _row(app, auth_headers, task_id))["stage"] == "checking"

    await _landing(task_id, "landed", landed_sha="abcdef1234567890")
    row = await _row(app, auth_headers, task_id)
    assert row["stage"] == "on_main"
    assert row["stage_detail"] == "abcdef1"


@pytest.mark.asyncio
async def test_an_approved_task_with_no_landing_is_not_on_main(app, auth_headers):
    task_id = await _task("approved")
    assert (await _row(app, auth_headers, task_id))["stage"] == "approved_waiting"


@pytest.mark.asyncio
async def test_only_the_task_a_run_is_bound_to_is_being_worked_on(app, auth_headers):
    a = await _task("in_progress", assignee="D")
    b = await _task("assigned", assignee="D")
    await _run(a, "D")
    assert (await _row(app, auth_headers, a))["stage"] == "working"
    assert (await _row(app, auth_headers, b))["stage"] == "not_started"


@pytest.mark.asyncio
async def test_held_and_not_landed_cards_carry_their_detail(app, auth_headers):
    held = await _task("approved")
    await _landing(held, "held", reason="check lint is failing")
    gone = await _task("approved")
    await _landing(gone, "not_landed", reason="the checkout has uncommitted changes")

    held_row = await _row(app, auth_headers, held)
    assert held_row["stage"] == "landing_held"
    assert held_row["stage_waits_on"] == "check lint is failing"
    gone_row = await _row(app, auth_headers, gone)
    assert gone_row["stage"] == "did_not_land"
    assert gone_row["stage_detail"] == "the checkout has uncommitted changes"


@pytest.mark.asyncio
async def test_the_route_reports_when_the_task_entered_its_stage(app, auth_headers):
    checking = await _task("approved")
    await _landing(checking, "checking")
    waiting = await _task("completed", updated=datetime.now(timezone.utc) - timedelta(days=2))

    assert (await _row(app, auth_headers, waiting))["stage"] == "waiting_for_review"
    since = (await _row(app, auth_headers, waiting))["stage_since"]
    age = datetime.now(timezone.utc) - datetime.fromisoformat(since.replace("Z", "+00:00")).replace(
        tzinfo=timezone.utc
    )
    assert timedelta(days=1, hours=23) < age < timedelta(days=2, hours=1)
    fresh = datetime.fromisoformat((await _row(app, auth_headers, checking))["stage_since"])
    assert datetime.now(timezone.utc) - fresh.replace(tzinfo=timezone.utc) < timedelta(minutes=2)


@pytest.mark.asyncio
async def test_what_a_waiting_task_waits_on_is_named_and_a_busy_one_names_nothing(
    app, auth_headers
):
    asking = await _task("in_progress", assignee="A")
    await _add(
        Question(
            id=f"q-stage-{next(_n)}",
            project_id=P,
            from_agent="Q",
            question="which way?",
            blocking=True,
            blocked_task_id=asking,
        )
    )
    prereq = await _task("in_progress", readable_id="AW-7")
    gated = await _task("pending")
    await _add(
        TaskDependency(
            id=f"dep-stage-{next(_n)}", project_id=P, task_id=gated, depends_on_task_id=prereq
        )
    )
    busy = await _task("in_progress", assignee="C")
    await _run(busy, "C")

    a = await _row(app, auth_headers, asking)
    assert a["stage"] == "waiting_for_answer"
    assert a["stage_waits_on"] == "Q"
    b = await _row(app, auth_headers, gated)
    assert b["stage"] == "not_started"
    assert b["stage_waits_on"] == "AW-7"
    c = await _row(app, auth_headers, busy)
    assert c["stage"] == "working"
    assert c["stage_waits_on"] is None
