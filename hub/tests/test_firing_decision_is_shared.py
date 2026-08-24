"""`loop-notices-and-reacts` group 4 — one decision, and the guards on what may be claimed.

Design D3: what a firing does stops being spread across `_do_fire_job` and becomes one function.
The reason is not tidiness. `_loop_queue_order`'s own comment records what happened the one time
the board and the firing derived the same thing separately: *"Both derivations shared the flaw, so
the board and the firing agreed on the wrong task — two consistent wrong answers read as a match,
which is how it survived review."*

Human-only check 13.1 of `task-dependencies` is that agreement, checked by eye. These tests are it
made mechanical.
"""

import pytest
from sqlalchemy import select

from hub.api.v1.jobs import _batch_loop_summaries
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task, TaskDependency
from hub.scheduler import (
    CLAIMABLE_LOOP_TASK_STATUSES,
    DECISION_CLAIM,
    DECISION_PROCEED_EMPTY,
    DECISION_STALLED,
    decide_firing,
)

pytestmark = pytest.mark.asyncio


async def _loop_with(db, suffix, tasks, deps=()):
    job = AIJob(
        id=f"job-dec-{suffix}",
        project_id="proj-test",
        name=f"Decision {suffix}",
        agent="dec-agent",
        message="hello",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(id=f"loop-dec-{suffix}", project_id="proj-test", job_id=job.id, purpose=suffix)
    db.add(loop)
    await db.commit()
    for task_id, status in tasks:
        db.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=task_id,
                status=status,
                loop_id=loop.id,
            )
        )
    await db.commit()
    for task_id, on_id in deps:
        db.add(
            TaskDependency(
                id=f"tdep-{task_id}-{on_id}",
                project_id="proj-test",
                task_id=task_id,
                depends_on_task_id=on_id,
            )
        )
    await db.commit()
    return job, loop


async def _fresh_loop(db, job_id):
    return (await db.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()


# ---------------------------------------------------------------------------
# 4.1 — the board and the firing agree
# ---------------------------------------------------------------------------


async def test_the_board_and_the_firing_name_the_same_task_when_there_is_one(app):
    """When the decision claims, the board's current item is that same task. The gated task is
    created first, so a derivation that ignored the dependency gate would pick it."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(
            db,
            "agree",
            [("task-dec-b", "pending"), ("task-dec-a", "pending")],
            deps=[("task-dec-b", "task-dec-a")],
        )

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="dec-agent")
        current = (await _batch_loop_summaries(db, [job.id]))[job.id].current_tasks

    assert decision.kind == DECISION_CLAIM
    assert [s.task.id for s in decision.selections] == ["task-dec-a"]
    assert [t["id"] for t in current] == ["task-dec-a"]


async def test_a_stalled_queue_claims_nothing_and_the_board_offers_no_claimable_item(app):
    """4.1's own case. A queue of `completed` work is stalled: the firing refuses with a reason,
    and the board shows no current item — `completed` is in neither set, which is the gap both
    2026-08-20 stall bugs lived in."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "stalled", [("task-dec-done", "completed")])

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="dec-agent")
        current = (await _batch_loop_summaries(db, [job.id]))[job.id].current_tasks

    assert decision.kind == DECISION_STALLED
    assert decision.selections == ()
    assert decision.stall_reason and "stalled" in decision.stall_reason
    assert current == []


async def test_a_blocked_queue_stalls_the_firing_while_the_board_still_shows_the_work(app):
    """Where the two legitimately differ, and why they are not one set.

    A blocked task stalls the firing — no agent can move it — but it *is* what the loop is working
    on, and the operator is the one who has to unblock it. A board that agreed with the firing here
    would show nothing and the loop would read as idle: the defect fixed on 2026-08-24.
    """
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "blocked", [("task-dec-blk", "blocked")])

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="dec-agent")
        current = (await _batch_loop_summaries(db, [job.id]))[job.id].current_tasks

    assert decision.kind == DECISION_STALLED
    assert [t["id"] for t in current] == ["task-dec-blk"]


async def test_an_empty_queue_proceeds_rather_than_stalling(app):
    """The third answer. A queue nobody has filled is not stalled — filling it is the agent's job,
    so the firing proceeds. Distinguishing this from a stall is what stopped the 2026-08-20 spin."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "empty", [])

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="dec-agent")

    assert decision.kind == DECISION_PROCEED_EMPTY
    assert decision.selections == ()
    assert decision.stall_reason is None


async def test_the_decision_carries_the_default_agent(app):
    """Design D2's default, now expressed by the decision rather than beside it."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "agent", [("task-dec-agent", "pending")])

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="whoever")

    assert [s.agent for s in decision.selections] == ["whoever"]


# ---------------------------------------------------------------------------
# 4.4 / 4.5 — the two statuses that must never be claimable
# ---------------------------------------------------------------------------


async def test_completed_is_not_claimable(app):
    """Design D3. Widening the tuple is the obvious wrong fix for "a reviewer should pick this up",
    and it is actor-blind: it would also offer the task back to the agent that completed it, which
    author/reviewer separation then refuses. `loop-becomes-a-flow` makes claimability a question
    about `(task, agent)` instead — this asserts the wrong fix has not been taken meanwhile."""
    assert "completed" not in CLAIMABLE_LOOP_TASK_STATUSES


async def test_blocked_is_not_claimable(app):
    """A live risk rather than a theoretical one: this change's own tasks asserted `blocked` was in
    this set until 2026-08-24. Claiming it spawns an agent every tick against work that only a
    person can move — the 2026-08-20 spin, in its other form."""
    assert "blocked" not in CLAIMABLE_LOOP_TASK_STATUSES


async def test_a_queue_of_only_completed_work_never_yields_a_selection(app):
    """The property behind 4.4, rather than the constant behind it: whatever the set says, the
    decision must not hand an agent a task it cannot move."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(
            db, "nosel", [("task-dec-c1", "completed"), ("task-dec-c2", "under_review")]
        )

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, job.id), default_agent="dec-agent")

    assert decision.selections == ()
    assert decision.kind == DECISION_STALLED


# ---------------------------------------------------------------------------
# 5.1 / 5.5 — the cadence, and the label that makes it safe to read
# ---------------------------------------------------------------------------


async def test_create_loop_defaults_to_a_five_minute_cadence(app):
    """5.1. The default became payable only once a busy tick is refused and a repeated stall counts
    in place — before groups 1 and 2 a fast tick manufactured duplicate briefings, so the honest
    advice was *slowly*. Read off the signature rather than by calling the tool, which would need a
    live Hub: `mcp_server` may import only stdlib and fastmcp, so there is nothing to stub."""
    import inspect

    from hub.mcp_server import create_loop

    default = inspect.signature(create_loop).parameters["cron"].default
    assert default == "*/5 * * * *"


async def test_a_stalled_loop_reports_why_on_its_summary(app):
    """5.5. The board's label comes from `decide_firing` — the same computation that would refuse
    the firing — so the two cannot say different things about why nothing is happening."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "label", [("task-dec-label", "completed")])

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job.id]))[job.id]

    assert summary.stall_reason is not None
    assert "no claimable task" in summary.stall_reason
    assert "1 completed" in summary.stall_reason


async def test_a_loop_that_would_fire_reports_no_stall_reason(app):
    """The absence is what the UI keys the label off, so it has to be a real None rather than an
    empty string."""
    async with async_session_factory() as db:
        job, _loop = await _loop_with(db, "nolabel", [("task-dec-ok", "pending")])

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job.id]))[job.id]

    assert summary.stall_reason is None


# ---------------------------------------------------------------------------
# 7.5 — the decision has exactly two call sites, asserted from the source
# ---------------------------------------------------------------------------


async def test_the_firing_decision_has_exactly_two_call_sites():
    """A source scan in the manner of `test_task_transitions.py`'s origin scan (task 7.5).

    The tests above prove the firing and the board *agree*. They cannot prove that agreement is
    structural rather than coincidental: two separate derivations that happen to match today pass
    every one of them. That is not a hypothetical — `_loop_queue_order`'s own comment records the
    time it happened, when both derivations shared a flaw and "two consistent wrong answers read as
    a match".

    So this asserts the shape instead of the outcome: `decide_firing` is called from the firing and
    from the board, and from nowhere else. A third caller is not automatically wrong, but it is a
    new consumer of the decision and should arrive with its own agreement test rather than
    silently. A *removed* caller is the real quarry — it means something went back to deriving the
    answer for itself, which is exactly how the board lost sight of `blocked` tasks on 2026-08-21.

    Parsed rather than grepped. `decide_firing` is discussed by name in comments and docstrings
    across both modules and in `schemas/jobs.py`, so a textual scan would have to special-case
    prose, and would start counting a *mention* as a caller the moment someone wrote one into a
    third file. `ast` distinguishes a call from a sentence about one for free.

    `async` only because this module's `pytestmark` makes every test in it async; the scan reads
    files and touches no database.
    """
    import ast
    from pathlib import Path

    hub_package = Path(__file__).resolve().parents[1] / "hub"
    call_sites = set()
    for path in sorted(hub_package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "decide_firing":
                call_sites.add(path.name)

    assert call_sites == {"scheduler.py", "jobs.py"}, (
        "`decide_firing` must be the one place a firing is decided; "
        f"found call sites in {sorted(call_sites)}"
    )
