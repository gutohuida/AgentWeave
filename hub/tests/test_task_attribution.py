"""Who is on a task and in what capacity — `one-answer-to-what-is-happening`, group 4 (D8, D9).

**In Python, over the derivation, not over the renderer.** That is the whole point of this file.
F49 was a five-line derivation bug live from the day it shipped: `decision.in_flight` is a sequence
of `(task_id, agent)` pairs, `set(...)` of it is a set of *tuples*, and the membership test asked it
with a bare task id — so it never matched and `working` was unreachable in production. It had five
vitest cases over the rendering and none over the deriving.

Each capacity is asserted from its own source, and `test_the_owning_module_is_the_only_reader`
enforces the encapsulation the same way `test_nothing_pushes` enforces `task_integration.py`'s
never-push guarantee: by reading the source, because Python cannot and a comment is not a mechanism.
"""

from pathlib import Path

import pytest

from hub.db.models import Task
from hub.task_attribution import (
    CAPACITY_ASSIGNED,
    CAPACITY_HELD,
    CAPACITY_NEXT,
    CAPACITY_WORKING,
    FlowStaffing,
    LiveRuns,
    attribute,
)


def _task(task_id: str, *, status: str = "in_progress", assignee: str | None = None) -> Task:
    return Task(
        id=task_id,
        project_id="proj-test",
        title=f"Task {task_id}",
        status=status,
        assignee=assignee,
    )


def _staffing(*, selected=None, unstaffable=None) -> FlowStaffing:
    return FlowStaffing(selected=selected or {}, unstaffable=unstaffable or {})


def _live(*, task_ids=(), agents=()) -> LiveRuns:
    return LiveRuns(task_ids=frozenset(task_ids), agents_without_task=frozenset(agents))


# ---------------------------------------------------------------------------
# 4.1 — each of the four capacities, from its own source
# ---------------------------------------------------------------------------


def test_working_comes_from_the_runs_table():
    """A run is genuinely in flight against this task. The only source that can say so is the runs
    table — the firing cannot, because the firing is about what happens next."""
    task = _task("task-w")
    result = attribute(
        task,
        staffing=_staffing(unstaffable={"task-w": "builder"}),
        live=_live(task_ids={"task-w"}),
    )
    assert result.agent == "builder"
    assert result.capacity == CAPACITY_WORKING


def test_held_comes_from_the_firing_minus_the_runs():
    """The state F23 asked to keep visible, finally wearing its own name (F63).

    The scheduler appends an `under_review` task with an assignee to the cannot-staff collection
    unconditionally, so a review that ended without a verdict stays on the board. Nothing is
    running against it. `working` would be a lie about a task with no run anywhere in the database
    — which is exactly what the board said about `relay`."""
    task = _task("task-h", status="under_review", assignee="critic")
    result = attribute(
        task,
        staffing=_staffing(unstaffable={"task-h": "critic"}),
        live=_live(),
    )
    assert result.agent == "critic"
    assert result.capacity == CAPACITY_HELD


def test_next_comes_from_the_firings_selection():
    """Who the next firing would give it to. For a `completed` task that is its **reviewer**, not
    the agent that did the work — the distinction the board collapsed in F26, so `completed |
    relay` read as "relay is working this" when it meant "relay is who would review this"."""
    task = _task("task-n", status="completed", assignee="builder")
    result = attribute(
        task,
        staffing=_staffing(selected={"task-n": "critic"}),
        live=_live(),
    )
    assert result.agent == "critic", "the selection outranks the task's own assignee"
    assert result.capacity == CAPACITY_NEXT


def test_assigned_comes_from_the_tasks_own_assignee():
    """Nobody is being selected and nothing is running: the blocked case, waiting on a person."""
    task = _task("task-a", status="blocked", assignee="builder")
    result = attribute(task, staffing=_staffing(), live=_live())
    assert result.agent == "builder"
    assert result.capacity == CAPACITY_ASSIGNED


def test_a_task_nobody_is_on_is_attributed_to_nobody():
    """Omitted rather than blank. A reader must never see a name with no meaning attached, which
    is F26 in one line — and `Attribution.__bool__` is what lets the renderer say that in one."""
    result = attribute(_task("task-none"), staffing=_staffing(), live=_live())
    assert result.agent is None
    assert result.capacity is None
    assert not result


def test_the_four_capacities_are_reachable_and_distinct():
    """F49's actual shape: a branch that could never match. Asserting the set of outcomes is
    reachable at all is the cheap check that would have caught it."""
    reached = {
        attribute(
            _task("t"), staffing=_staffing(unstaffable={"t": "a"}), live=_live(task_ids={"t"})
        ).capacity,
        attribute(_task("t"), staffing=_staffing(unstaffable={"t": "a"}), live=_live()).capacity,
        attribute(_task("t"), staffing=_staffing(selected={"t": "a"}), live=_live()).capacity,
        attribute(_task("t", assignee="a"), staffing=_staffing(), live=_live()).capacity,
    }
    assert reached == {CAPACITY_WORKING, CAPACITY_HELD, CAPACITY_NEXT, CAPACITY_ASSIGNED}


# ---------------------------------------------------------------------------
# 4.2 / 4.3 — the two lies the old derivation told
# ---------------------------------------------------------------------------


def test_a_review_whose_run_has_ended_is_not_presented_as_working():
    """4.2, and F63 stated directly. The measured case: `relay` shown mid-turn on a task whose
    review run had already failed, with no run anywhere in the database."""
    task = _task("task-f63", status="under_review", assignee="relay")
    result = attribute(
        task,
        staffing=_staffing(unstaffable={"task-f63": "relay"}),
        live=_live(task_ids={"some-other-task"}, agents=set()),
    )
    assert result.capacity == CAPACITY_HELD
    assert result.capacity != CAPACITY_WORKING


def test_an_agent_mid_turn_elsewhere_does_not_make_a_second_task_read_as_worked():
    """4.3. `builder` is mid-turn on an unbound run and also holds a second task nothing is running
    against. The second must not read as worked.

    **Asserted with the agent-fallback off, because the fallback is still on by default and still
    tells this lie.** It is carried deliberately: a flow's ordinary work firing writes no
    `task_id`, so with the fallback removed today every actively-worked flow task would read
    `held` — the same class of lie in the other direction. Both halves are asserted here so the
    carried defect is a measured fact rather than a footnote, and
    `openspec/explorations/2026-08-26-the-other-half-of-the-binding.md` is what removing it waits on.
    """
    task = _task("task-second", status="under_review", assignee="builder")
    staffing = _staffing(unstaffable={"task-second": "builder"})
    live = _live(agents={"builder"})

    assert attribute(task, staffing=staffing, live=live, agent_fallback=False).capacity == (
        CAPACITY_HELD
    ), "with a written run→task edge this is held, which is the truth"

    assert attribute(task, staffing=staffing, live=live).capacity == CAPACITY_WORKING, (
        "and this is the over-report the fallback still concedes to — pinned so that removing the "
        "fallback is visible as a behaviour change rather than a silent one"
    )


def test_the_fallback_never_changes_a_task_the_runs_table_can_answer():
    """The fallback is bounded and one-directional: it only ever adds `working` where `task_id`
    said nothing. A task the runs table names is answered by the runs table either way."""
    task = _task("task-bound")
    staffing = _staffing(unstaffable={"task-bound": "builder"})
    live = _live(task_ids={"task-bound"})
    assert attribute(task, staffing=staffing, live=live).capacity == CAPACITY_WORKING
    assert (
        attribute(task, staffing=staffing, live=live, agent_fallback=False).capacity
        == CAPACITY_WORKING
    )


# ---------------------------------------------------------------------------
# 4.4 — the encapsulation, enforced rather than documented
# ---------------------------------------------------------------------------


def test_the_owning_module_is_the_only_reader_of_the_cannot_staff_collection():
    """D9's enforcement, in the idiom `test_nothing_pushes` already uses.

    `FiringDecision._cannot_staff` means *"this firing cannot staff anybody onto this"*. It was
    public, and public on a frozen dataclass means any consumer may pick it up and read it as
    anything. One did: the board read it as "this agent is mid-turn on it" and told the operator
    `relay` was working a task whose review run had already failed (F63).

    Python cannot enforce a private field. The codebase already answers that with a source scan,
    and this is the same answer for the same reason: a claim about the code, not about one
    execution.
    """
    package = Path(__import__("hub").__file__).parent
    owners = {"scheduler.py", "task_attribution.py"}
    offenders = []
    for path in package.rglob("*.py"):
        if path.name in owners or "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "_cannot_staff" in source:
            offenders.append(str(path.relative_to(package)))
    assert offenders == [], (
        f"{offenders} read the firing decision's cannot-staff collection directly. Only "
        f"task_attribution.staffing_from_decision may; it is the one place that turns 'cannot be "
        f"staffed' into a capacity, and every surface that bypassed it has read it as activity."
    )


def test_the_old_public_name_is_gone():
    """D8's other half. `in_flight` read as "this is running", which is the meaning that was never
    true — the field is about staffing. A field left under its old name is a field a future
    consumer misreads the same way."""
    from hub.scheduler import DECISION_PROCEED_EMPTY, FiringDecision

    decision = FiringDecision(kind=DECISION_PROCEED_EMPTY)
    assert not hasattr(decision, "in_flight")
    assert hasattr(decision, "_cannot_staff")


@pytest.mark.parametrize(
    "capacity", [CAPACITY_WORKING, CAPACITY_HELD, CAPACITY_NEXT, CAPACITY_ASSIGNED]
)
def test_every_capacity_the_wire_can_carry_is_one_this_module_produces(capacity):
    """The values are unchanged by D8's rename — only the field name moved. A value the UI's union
    type accepts but nothing produces is an unreachable branch of the kind F49 was."""
    from hub.task_attribution import CAPACITIES

    assert capacity in CAPACITIES


def test_staffing_reads_both_of_the_firings_answers():
    """The module's own seam, exercised against a real `FiringDecision`.

    Found by mutation check 4.9(c): emptying `unstaffable` in `staffing_from_decision` left every
    other test in this file green, because they all build `FlowStaffing` by hand. Four cases in
    `test_board_agent_role.py` caught it through the API — so the behaviour was covered, but this
    module's own boundary was not, and a unit file that cannot fail when its subject is gutted is
    not testing its subject.
    """
    from hub.db.models import Task as TaskModel
    from hub.scheduler import DECISION_CLAIM, FiringDecision, LoopSelection
    from hub.task_attribution import staffing_from_decision

    selected_task = TaskModel(id="t-sel", project_id="proj-test", title="s", status="pending")
    decision = FiringDecision(
        kind=DECISION_CLAIM,
        selections=(LoopSelection(task=selected_task, agent="builder"),),
        _cannot_staff=(("t-held", "critic"),),
    )

    staffing = staffing_from_decision(decision)

    assert staffing.selected == {"t-sel": "builder"}
    assert staffing.unstaffable == {"t-held": "critic"}
    # Selection outranks held work for the same task — the more current statement wins.
    assert staffing.agent_for("t-sel") == "builder"
    assert staffing.agent_for("t-held") == "critic"
    assert staffing.agent_for("t-unknown") is None
