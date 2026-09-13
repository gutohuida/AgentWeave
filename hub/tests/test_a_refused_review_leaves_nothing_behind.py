"""`a-refused-review-leaves-nothing-behind` — F319 and F320, pinned before either is fixed.

**F319.** A review dispatch stages the reviewer into the task (`enter_selected_task`: the assignee,
then `completed -> under_review` and its transition row) before it provisions the checkout, so that
a refused request provisions nothing (`2026-08-28-a-review-started-by-hand-can-finish` D10). That
staging is pending state in the dispatch's session, and a refusal raised during or after it was
supposed to abandon it. It does not: `trigger_agent_directly` has one caller,
`turn_scheduler.schedule_agent`, and its refusal branch commits the same session to record the
refusal's words (F97). Measured live 2026-09-12: tasks left `under_review`, held by a reviewer that
never ran, and a second reviewer refused as *"already under review"*. Design D1 is the repair: the
branch discards the dispatch's transaction **first**, then records exactly what it records today.

**F320.** A pass that gives up on its head does not go on. The input queued behind it waits for a
tick that does not exist. Design D4 is the repair: the pass repeats the attempt only while the
previous attempt gave up on something, counts each entry at most once per pass, and is bounded.

**Every test here was written against the unmodified tree** (tasks §1). What holds today is a pin;
what must move is a whole test under a strict xfail naming the section that moves it — never one
assertion inside a pin, because a strict xfail stops at its first failing line and pins nothing
after it. `raises=AssertionError` is added to each marker so a test that fails for any other reason
(a fixture that did not build, a guard `RuntimeError`) is reported as a failure, not as the
expected one. Each test's docstring names the §4 mutation that must fail it once its section lands.
"""

import ast
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from hub import sse as sse_module
from hub import worktrees
from hub.api.v1 import agent_trigger
from hub.api.v1.agent_trigger import TriggerAgentError, TriggerAgentResponse
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    EventLog,
    EvidenceFootprint,
    InboundQueueEntry,
    Project,
    RequirementEvidence,
    Run,
    RunDivergence,
    SpecRequirement,
    Task,
    TaskTransition,
)
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, new_entry, withdraw_entry
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator
from hub.turn_scheduler import schedule_agent

from .test_a_flow_names_what_it_cannot_staff import _roster
from .test_agent_trigger import _init_repo

pytestmark = pytest.mark.asyncio

#: Captured at import, before `conftest`'s autouse fixture stubs it, as `test_review_turn.py` does.
_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"
TRIGGER_ROUTE = "/api/v1/projects/proj-test/agent/trigger"

REVIEWER = "rr-reviewer"
SECOND = "rr-second"
WORKER = "rr-worker"

MOVES_IN_3 = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="a-refused-review-leaves-nothing-behind §3"
)

#: The words that tell B0, B1 and B2's refusals apart (`review_turn.py`, `worktrees.py`).
B_REFUSAL_WORDS = {
    "B0": "not a git repository",
    "B1": "is not present in this repository",
    "B2": "refusing existing path",
}
MISSING_COMMIT = "e" * 40


# ---------------------------------------------------------------------------
# 1.1 — fixtures
# ---------------------------------------------------------------------------


def _which():
    return patch("hub.launchability.shutil.which", return_value="/usr/bin/claude")


def _head_of(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


async def _snapshot(task_id: str):
    """`(status, assignee, transition count)` — what *"as it was"* is measured by."""
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        transitions = await db.scalar(
            select(func.count())
            .select_from(TaskTransition)
            .where(TaskTransition.task_id == task_id)
        )
        return (task.status, task.assignee, transitions)


async def _evidence(db, task_id: str, suffix: str, *, actor_kind: str, actor: str, sha=None):
    requirement_id = f"req-rr-{task_id}"
    if await db.get(SpecRequirement, requirement_id) is None:
        db.add(
            SpecRequirement(
                id=requirement_id,
                project_id="proj-test",
                document_id=f"doc-rr-{task_id}",
                identifier="FR-1",
                key="fr-1",
                digest="d" * 64,
            )
        )
    evidence_id = f"ev-rr-{task_id}-{suffix}"
    db.add(
        RequirementEvidence(
            id=evidence_id,
            project_id="proj-test",
            requirement_id=requirement_id,
            task_id=task_id,
            digest="d" * 64,
            kind="artifact_diff",
            actor_kind=actor_kind,
            actor=actor,
            summary="did it",
            review_state="awaiting",
        )
    )
    if sha is not None:
        db.add(
            EvidenceFootprint(
                id=f"fp-rr-{task_id}-{suffix}",
                project_id="proj-test",
                evidence_id=evidence_id,
                kind="git",
                commit_sha=sha,
                branch="main",
            )
        )
    await db.commit()


async def _operator_completed(task_id: str, *, sha: str) -> str:
    """An operator-completed task whose one operator-kind evidence row names *sha*.

    Operator-completed, so no agent is recorded as completing it: leg A's refusal is then the
    evidence-author half of the guard (F306), which is the one the route cannot see coming.
    """
    async with async_session_factory() as db:
        task = Task(id=task_id, project_id="proj-test", title=f"t {task_id}", status="pending")
        db.add(task)
        await db.commit()
        for status in ("in_progress", "completed"):
            await apply_transition(db, task, status, operator())
        await db.commit()
        await _evidence(db, task_id, "op", actor_kind="operator", actor="operator-x", sha=sha)
    return task_id


async def _conversation(agent: str) -> str:
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        db.add(conversation)
        await db.commit()
        return conversation.id


async def _entry(agent, conversation_id, *, attempts=0, review_task_id=None, content="x"):
    async with async_session_factory() as db:
        entry = new_entry(
            project_id="proj-test",
            agent=agent,
            origin_type="operator",
            content=content,
            hop_depth=0,
            conversation_id=conversation_id,
            review_task_id=review_task_id,
        )
        entry.delivery_attempts = attempts
        db.add(entry)
        await db.commit()
        return entry.id


async def _queue_review(agent: str, task_id: str, *, attempts: int = 0) -> str:
    return await _entry(
        agent,
        await _conversation(agent),
        attempts=attempts,
        review_task_id=task_id,
        content=f"review {task_id}",
    )


async def _row(entry_id: str) -> InboundQueueEntry:
    async with async_session_factory() as db:
        return (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
        ).scalar_one()


async def _runs() -> list:
    async with async_session_factory() as db:
        return list((await db.execute(select(Run.id))).scalars().all())


async def _events(event_type: str, **where) -> int:
    async with async_session_factory() as db:
        query = select(func.count()).select_from(EventLog).where(EventLog.event_type == event_type)
        for column, value in where.items():
            query = query.where(getattr(EventLog, column) == value)
        return await db.scalar(query)


async def _register(app, auth_headers, *agents):
    """Agents with no runner — for the legs where `trigger_agent_directly` is patched."""
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {} for agent in agents}}},
        headers=auth_headers,
    )


def _started(kw) -> TriggerAgentResponse:
    return TriggerAgentResponse(
        success=True,
        message="started",
        agent=kw["agent"],
        run_id="run-rr-fake",
        status="running",
        conversation_id=kw["conversation_id"],
    )


def _refused(ids) -> TriggerAgentError:
    return TriggerAgentError(409, "refused " + ",".join(ids), request_level=True)


# ---------------------------------------------------------------------------
# 1.2 — B0, B1, B2 on the scheduler path
# ---------------------------------------------------------------------------


async def _b_leg(
    leg, app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    if leg == "B0":
        sha = "c" * 40  # `tmp_path` is the project root, and it is not a repository
    else:
        repo = _init_repo(tmp_path / "repo")
        await bind_project_workspace(repo)
        monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
        sha = MISSING_COMMIT if leg == "B1" else _head_of(repo)
        if leg == "B2":
            obstruction = repo / ".agentweave" / "reviews" / REVIEWER
            obstruction.mkdir(parents=True)
            (obstruction / "x.txt").write_text("x")
    await _roster(app, auth_headers, bind_runner, REVIEWER)
    task_id = await _operator_completed(f"task-rr-{leg.lower()}", sha=sha)
    before = await _snapshot(task_id)
    entry_id = await _queue_review(REVIEWER, task_id)
    with _which():
        result = await schedule_agent("proj-test", REVIEWER)
    return task_id, before, entry_id, result


@pytest.mark.parametrize("leg", ["B0", "B1", "B2"])
async def test_a_refused_review_on_the_scheduler_path_records_the_refusal(
    leg, app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Pin, passes today (design D0): the refusal's words, its count and its classification.

    §2 rolls the dispatch back and must keep all of this, because it is written *after* the
    rollback (F97). Mutation 4.3 — the `waiting_reason` write moved above the rollback — must fail
    this, because the write is then discarded with the staging.
    """
    _task_id, _before, entry_id, result = await _b_leg(
        leg, app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    entry = await _row(entry_id)
    assert (entry.state, entry.delivery_attempts) == ("queued", 1)
    assert entry.waiting_reason == result.waiting_reason
    assert B_REFUSAL_WORDS[leg] in entry.waiting_reason, entry.waiting_reason
    assert result.refusal is not None and result.refusal.status_code == 409
    assert await _runs() == []


@pytest.mark.parametrize("leg", ["B0", "B1", "B2"])
async def test_a_refused_review_on_the_scheduler_path_leaves_the_task_as_it_was(
    leg, app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """F319: the task after a refused review equals the task before it.

    Today it reads `under_review`, held by the refused reviewer, one transition longer: the
    scheduler's refusal branch committed the staging. Mutation 4.1 (no rollback) and 4.2 (the
    rollback below the branch's first commit) must fail this.
    """
    task_id, before, _entry_id, _result = await _b_leg(
        leg, app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert await _snapshot(task_id) == before
    assert await _runs() == []


# ---------------------------------------------------------------------------
# 1.3 — B1 through the route
# ---------------------------------------------------------------------------


async def _b1_through_the_route(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, REVIEWER, SECOND)
    task_id = await _operator_completed("task-rr-route", sha=MISSING_COMMIT)
    before = await _snapshot(task_id)
    with _which():
        response = await app.post(
            TRIGGER_ROUTE,
            json={"agent": REVIEWER, "message": f"review {task_id}", "review_task_id": task_id},
            headers=auth_headers,
        )
    return task_id, before, response


async def test_a_refused_review_through_the_route_is_answered_and_withdrawn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Pin, passes today: F108's answer. `409`, the refusal naming the commit, and the entry
    withdrawn with `queue_entry_withdrawn`. §2 must keep it; no §4 mutation targets it."""
    _task_id, _before, response = await _b1_through_the_route(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert response.status_code == 409, response.text
    assert MISSING_COMMIT in response.json()["detail"]
    async with async_session_factory() as db:
        states = (
            (
                await db.execute(
                    select(InboundQueueEntry.state).where(InboundQueueEntry.agent == REVIEWER)
                )
            )
            .scalars()
            .all()
        )
    assert states == ["withdrawn"]
    assert await _events("queue_entry_withdrawn", agent=REVIEWER) == 1


async def test_a_refused_review_through_the_route_does_not_stop_another_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """F319 as the operator met it: the task is as it was, so a second reviewer is not refused as
    *"already under review"* by the first, who never ran. It may still be refused for the commit.
    Mutation 4.1 must fail this."""
    task_id, before, _response = await _b1_through_the_route(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert await _snapshot(task_id) == before
    with _which():
        second = await app.post(
            TRIGGER_ROUTE,
            json={"agent": SECOND, "message": f"review {task_id}", "review_task_id": task_id},
            headers=auth_headers,
        )
    assert "already under review" not in second.json().get("detail", ""), second.text


# ---------------------------------------------------------------------------
# 1.4 — leg A, the timing gap, through the route
# ---------------------------------------------------------------------------

GUARD_WORDS = "recorded evidence for this task"


async def _leg_a(app, auth_headers, bind_runner):
    """The route's check passes because X has recorded nothing yet; X's own turn then records
    evidence, and every delivery after that is refused by the §3.4 guard, which is not patched."""
    await _roster(app, auth_headers, bind_runner, REVIEWER)
    task_id = await _operator_completed("task-rr-a", sha="c" * 40)
    async with async_session_factory() as db:
        db.add(Run(id="run-rr-a", project_id="proj-test", agent=REVIEWER, status="running"))
        await db.commit()
    before = await _snapshot(task_id)
    with _which():
        response = await app.post(
            TRIGGER_ROUTE,
            json={"agent": REVIEWER, "message": f"review {task_id}", "review_task_id": task_id},
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    entry_id = response.json()["queue_entry_id"]

    async with async_session_factory() as db:
        await _evidence(db, task_id, "x", actor_kind="agent", actor=REVIEWER)
        run = await db.get(Run, "run-rr-a")
        run.status = "completed"
        await db.commit()

    passes = []
    for _ in range(DELIVERY_ATTEMPT_LIMIT):
        with _which():
            await schedule_agent("proj-test", REVIEWER)
        entry = await _row(entry_id)
        passes.append((await _snapshot(task_id), entry.waiting_reason or ""))
    return task_id, before, entry_id, passes


async def test_leg_a_records_the_guards_refusal_and_gives_up_at_the_limit(
    app, auth_headers, bind_runner
):
    """Pin, passes today: the guard's sentence is the entry's reason on every pass, and the third
    pass gives up with `queue_entry_abandoned`. Mutation 4.3 must fail this."""
    _task_id, _before, entry_id, passes = await _leg_a(app, auth_headers, bind_runner)
    for _snap, waiting_reason in passes:
        assert GUARD_WORDS in waiting_reason, waiting_reason
    entry = await _row(entry_id)
    assert entry.state == "withdrawn"
    assert GUARD_WORDS in (entry.abandoned_reason or ""), entry.abandoned_reason
    assert await _events("queue_entry_abandoned", agent=REVIEWER) == 1


async def test_leg_a_leaves_the_task_as_it_was_after_every_pass(app, auth_headers, bind_runner):
    """F319's leg A. Today the refused author is left holding the completed task: the assignee is
    written before the guard refuses, and the scheduler commits it. Mutation 4.1 must fail this."""
    _task_id, before, _entry_id, passes = await _leg_a(app, auth_headers, bind_runner)
    assert [snap for snap, _reason in passes] == [before] * DELIVERY_ATTEMPT_LIMIT


# ---------------------------------------------------------------------------
# 1.5 — leg T, a deferral after the staging
# ---------------------------------------------------------------------------


async def _leg_t(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.delenv("HUB_URL", raising=False)
    monkeypatch.setattr(agent_trigger.bound_address, "get", lambda *a, **k: None)
    await _roster(app, auth_headers, bind_runner, REVIEWER)
    task_id = await _operator_completed("task-rr-t", sha=_head_of(repo))
    before = await _snapshot(task_id)
    entry_id = await _queue_review(REVIEWER, task_id)
    with _which():
        result = await schedule_agent("proj-test", REVIEWER)
    return task_id, before, entry_id, result


async def test_leg_t_defers_without_counting(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Pin, passes today: the Hub not knowing its own address clears on its own, so it counts
    nothing and refuses nothing. No §4 mutation targets it."""
    _task_id, _before, entry_id, result = await _leg_t(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    entry = await _row(entry_id)
    assert (entry.state, entry.delivery_attempts) == ("queued", 0)
    assert result.terminal_failure is False
    assert result.refusal is None


async def test_leg_t_leaves_the_task_as_it_was(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """F319 for a deferral: the staging precedes the last raise site (`:1146`), so a transient
    refusal committed it too. Mutation 4.1 must fail this."""
    task_id, before, _entry_id, _result = await _leg_t(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert await _snapshot(task_id) == before
    assert await _runs() == []


# ---------------------------------------------------------------------------
# 1.6 — F320 at the scheduler
# ---------------------------------------------------------------------------


def _trigger(calls, *, allowed, decide):
    """A patched `trigger_agent_directly` that records the entry ids it is called with and raises
    `RuntimeError("test guard")` past *allowed* calls — `pytest-timeout` is not installed, so a
    loop that fails to stop must fail the test rather than hang it."""

    async def trigger(**kw):
        ids = tuple(kw["queue_entry_ids"])
        calls.append(ids)
        if len(calls) > allowed:
            raise RuntimeError("test guard")
        return decide(ids, kw)

    return trigger


async def _head(agent):
    """H: a review entry at `LIMIT - 1`, in a conversation of its own."""
    return await _queue_review(agent, "task-nope", attempts=DELIVERY_ATTEMPT_LIMIT - 1)


@MOVES_IN_3
async def test_the_pass_that_gives_up_on_its_head_delivers_the_entry_behind(app, auth_headers):
    """1.6(a). F320: H is given up on, and B, waiting in another conversation, starts in the same
    pass. Today the pass ends after H. Mutation 4.7 (no loop) must fail this."""
    agent = "rr-f320-a"
    await _register(app, auth_headers, agent)
    head = await _head(agent)
    behind = await _entry(agent, await _conversation(agent), content="b")
    calls: list = []

    def decide(ids, kw):
        if head in ids:
            raise _refused(ids)
        return _started(kw)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=2, decide=decide))):
        result = await schedule_agent("proj-test", agent)
    assert calls == [(head,), (behind,)]
    assert (await _row(head)).state == "withdrawn"
    assert result.response is not None and result.response.run_id == "run-rr-fake"


@MOVES_IN_3
async def test_the_entry_behind_is_counted_once_when_it_is_refused_too(app, auth_headers):
    """1.6(b). The pass goes on to B, B is refused as well, and B is counted once — not three
    times in one pass (F114). Mutation 4.5 (continue after any refusal) must fail this on its guard
    `RuntimeError`, and 4.7 (no loop) on its call count."""
    agent = "rr-f320-b"
    await _register(app, auth_headers, agent)
    head = await _head(agent)
    behind = await _entry(agent, await _conversation(agent), content="b")
    calls: list = []

    def decide(ids, kw):
        raise _refused(ids)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=2, decide=decide))):
        await schedule_agent("proj-test", agent)
    assert calls == [(head,), (behind,)]
    assert (await _row(head)).state == "withdrawn"
    row = await _row(behind)
    assert (row.state, row.delivery_attempts) == ("queued", 1)


async def test_a_transient_refusal_of_the_head_ends_the_pass(app, auth_headers):
    """1.6(c). Pin, passes today: a refusal that clears on its own counts nothing, so nothing was
    given up on and the pass stops — repeating it would busy-loop. Mutation 4.6 (also continue
    after a transient refusal) must fail this on its guard `RuntimeError`."""
    agent = "rr-f320-c"
    await _register(app, auth_headers, agent)
    head = await _head(agent)
    await _entry(agent, await _conversation(agent), content="b")
    calls: list = []

    def decide(ids, kw):
        raise TriggerAgentError(409, "transient", transient=True)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=1, decide=decide))):
        await schedule_agent("proj-test", agent)
    assert calls == [(head,)]
    row = await _row(head)
    assert (row.state, row.delivery_attempts) == ("queued", DELIVERY_ATTEMPT_LIMIT - 1)


@MOVES_IN_3
async def test_a_pass_that_gives_up_on_everything_reports_the_refusal(app, auth_headers):
    """1.6(d). Three heads at `LIMIT - 1` in three conversations, all refused: three calls, all
    three given up, and the pass reports the refusal that emptied the queue, not *"queue is
    empty"* (design D5). The bound (`len(initial) + 1`) is never reached. Mutations 4.7 (no loop)
    and 4.8 (the last attempt's result, unconditionally) must fail this."""
    agent = "rr-f320-d"
    await _register(app, auth_headers, agent)
    heads = [await _head(agent) for _ in range(3)]
    calls: list = []

    def decide(ids, kw):
        raise _refused(ids)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=3, decide=decide))):
        result = await schedule_agent("proj-test", agent)
    assert calls == [(head,) for head in heads]
    assert [(await _row(head)).state for head in heads] == ["withdrawn"] * 3
    assert result.waiting_reason == f"refused {heads[-1]}"
    assert result.waiting_reason != "queue is empty"


async def test_a_lone_head_given_up_reports_its_refusal(app, auth_headers):
    """1.6(e). Pin, passes today: H alone, refused at its limit. The result is the refusal and
    `terminal_failure` is `True`. Keeps §3's result rule (3.2) from regressing the ordinary case;
    no §4 mutation targets it."""
    agent = "rr-f320-e"
    await _register(app, auth_headers, agent)
    head = await _head(agent)
    calls: list = []

    def decide(ids, kw):
        raise _refused(ids)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=2, decide=decide))):
        result = await schedule_agent("proj-test", agent)
    assert (await _row(head)).state == "withdrawn"
    assert result.waiting_reason == f"refused {head}"
    assert result.terminal_failure is True


async def test_a_rider_is_counted_once_in_a_pass(app, auth_headers):
    """1.6(f), the rider (R2, design D4). Pin, passes today: one call, `[H1, M]`, H1 given up and M
    counted once. With the loop, H6 is reached and given up too — (d) covers that, so H6 is not
    asserted here. What is asserted is that M, riding in every attempt, is counted **once**:
    R2 measured R1's loop without the once-per-pass rule carry M in `[H1, M]`, `[M, H6]`, `[M]`
    and withdraw it at 3 in one pass. Mutation 4.10 (the once-per-pass guard removed) must fail
    this, with M `withdrawn` at 3."""
    agent = "rr-f320-f"
    await _register(app, auth_headers, agent)
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.turn_delivery_cap = 2
        await db.commit()
    conversation = await _conversation(agent)
    h1 = await _entry(
        agent,
        conversation,
        attempts=DELIVERY_ATTEMPT_LIMIT - 1,
        review_task_id="task-nope",
        content="h1",
    )
    m = await _entry(agent, conversation, content="m")
    await _entry(
        agent,
        conversation,
        attempts=DELIVERY_ATTEMPT_LIMIT - 1,
        review_task_id="task-nope",
        content="h6",
    )
    calls: list = []

    def decide(ids, kw):
        raise _refused(ids)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=3, decide=decide))):
        await schedule_agent("proj-test", agent)
    assert (await _row(h1)).state == "withdrawn"
    row = await _row(m)
    assert (row.state, row.delivery_attempts) == ("queued", 1)


@MOVES_IN_3
async def test_the_pass_stops_at_a_rider_refused_alone(app, auth_headers):
    """1.6(g) (R3, design D13). H1 and M in C1, N in C2. The pass gives up on H1, then carries M
    alone; M is refused, counts nothing (it was counted in this pass) and gives up on nothing, so
    the pass stops. N waits behind M as it waits behind any refused head below its limit — the
    requirement's *"refused and gave up on nothing"*. Today the pass makes one call. Mutations
    4.5 (continue after any refusal) and 4.10 (M counted twice: `queued` at 2) must fail this."""
    agent = "rr-f320-g"
    await _register(app, auth_headers, agent)
    c1 = await _conversation(agent)
    h1 = await _entry(
        agent, c1, attempts=DELIVERY_ATTEMPT_LIMIT - 1, review_task_id="task-nope", content="h1"
    )
    m = await _entry(agent, c1, content="m")
    n = await _entry(agent, await _conversation(agent), content="n")
    calls: list = []

    def decide(ids, kw):
        if h1 in ids or m in ids:
            raise _refused(ids)
        return _started(kw)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=2, decide=decide))):
        await schedule_agent("proj-test", agent)
    assert calls == [(h1, m), (m,)]
    assert (await _row(h1)).state == "withdrawn"
    rows = [await _row(m), await _row(n)]
    assert [(row.state, row.delivery_attempts) for row in rows] == [("queued", 1), ("queued", 0)]


# ---------------------------------------------------------------------------
# 1.7 — F320 through the route
# ---------------------------------------------------------------------------


@MOVES_IN_3
async def test_the_route_starts_its_input_behind_a_head_given_up(app, auth_headers):
    """1.7. H waits at `LIMIT - 1`; the operator sends a plain message, which opens a new
    conversation. The pass gives up on H and starts the operator's turn, and the answer says so.
    Today it answers `queued`, *"queued behind other input for this agent"*, and the input is never
    delivered. Mutation 4.7 (no loop) must fail this."""
    agent = "rr-f320-route"
    await _register(app, auth_headers, agent)
    head = await _head(agent)
    calls: list = []

    def decide(ids, kw):
        if head in ids:
            raise _refused(ids)
        return _started(kw)

    with patch(TRIGGER, AsyncMock(side_effect=_trigger(calls, allowed=2, decide=decide))):
        response = await app.post(
            TRIGGER_ROUTE, json={"agent": agent, "message": "hello"}, headers=auth_headers
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "running", body
    assert len(calls) == 2 and head not in calls[1]


# ---------------------------------------------------------------------------
# 1.8 — the one-caller pin
# ---------------------------------------------------------------------------

_HUB_PACKAGE = Path(__file__).resolve().parents[1] / "hub"


def _references(source: str, name: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.alias) and name in (node.name, node.asname):
            return True
    return False


async def test_trigger_agent_directly_has_one_caller():
    """Design D2(e): the rollback lives in `turn_scheduler.schedule_agent` because that is the
    only caller of `trigger_agent_directly`, and a refusal inside the dispatch is abandoned only
    because that caller discards it. A second caller would get the staging back. Pinned so a second
    caller has to meet the reason. Passes today; no §4 mutation targets it.

    Scanned with `ast`, not text: `trigger_agent_directly(` misses `partial(trigger_agent_directly,
    ...)` and anything imported under another name, and matches the docstrings and comments that
    name the function. The scanner is checked against those shapes first, so it is not vacuous.
    """
    name = "trigger_agent_directly"
    assert _references("from hub.api.v1.agent_trigger import trigger_agent_directly as t", name)
    assert _references("import functools\nf = functools.partial(trigger_agent_directly, x=1)", name)
    assert _references(
        "from hub.api.v1 import agent_trigger\nagent_trigger.trigger_agent_directly()", name
    )
    assert not _references(
        '"""trigger_agent_directly() is named here."""\n# trigger_agent_directly(', name
    )

    referencing = {
        path.relative_to(_HUB_PACKAGE).as_posix()
        for path in _HUB_PACKAGE.rglob("*.py")
        if _references(path.read_text(encoding="utf-8"), name)
    }
    referencing.discard("api/v1/agent_trigger.py")  # the `def` itself
    assert referencing == {"turn_scheduler.py"}


# ---------------------------------------------------------------------------
# 1.8a — an open divergence is not closed by a refused review
# ---------------------------------------------------------------------------


async def _divergence(db, divergence_id: str) -> RunDivergence:
    # By `id`, not `db.get`: the primary key is `sequence` (models.py, `RunDivergence`).
    return (
        await db.execute(select(RunDivergence).where(RunDivergence.id == divergence_id))
    ).scalar_one()


async def _completed_with_an_open_divergence(task_id: str) -> str:
    """Built through the product (R3, design D13): a worker's run bound to the task, the operator
    completing the task while the run is still running, and the run's end evaluated."""
    async with async_session_factory() as db:
        task = Task(id=task_id, project_id="proj-test", title="div", status="pending")
        run = Run(id="run-rr-div", project_id="proj-test", agent=WORKER, status="running")
        db.add_all([task, run])
        await db.flush()
        await bind_run_to_task(db, run, task)  # pending -> in_progress, origin runtime
        await db.commit()
        await apply_transition(db, task, "completed", operator())
        await db.commit()
        run.status = "completed"
        await db.commit()
    divergence_id = await evaluate_run_end("run-rr-div")
    assert divergence_id is not None
    async with async_session_factory() as db:
        divergence = await _divergence(db, divergence_id)
        assert divergence.task_status_at_end == "completed"
        assert divergence.outcome == "surfaced"
        assert divergence.resolved_at is None
        await _evidence(
            db, task_id, "op", actor_kind="operator", actor="operator-x", sha=MISSING_COMMIT
        )
    return divergence_id


async def _divergence_leg(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, REVIEWER, WORKER)
    task_id = "task-rr-div"
    divergence_id = await _completed_with_an_open_divergence(task_id)
    before = await _snapshot(task_id)
    await _queue_review(REVIEWER, task_id)
    broadcasts: list = []
    real_broadcast = sse_module.sse_manager.broadcast

    async def spy(project_id, event_type, payload):
        broadcasts.append(event_type)
        return await real_broadcast(project_id, event_type, payload)

    monkeypatch.setattr(sse_module.sse_manager, "broadcast", spy)
    with _which():
        await schedule_agent("proj-test", REVIEWER)
    return task_id, before, divergence_id, broadcasts


async def test_the_divergence_fixture_is_built_through_the_product(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Pin, passes today: the B1-refused review reaches a completed task carrying an open
    divergence, so 1.8a's xfail below can fail only on what it asserts. No §4 mutation targets it.
    """
    task_id, before, _divergence_id, _broadcasts = await _divergence_leg(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert before[:2] == ("completed", WORKER)
    async with async_session_factory() as db:
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == task_id)
            )
        ).scalar_one()
    assert B_REFUSAL_WORDS["B1"] in (entry.waiting_reason or ""), entry.waiting_reason


async def test_a_refused_review_does_not_close_an_open_divergence(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """1.8a (R2, design D8). Entering review resolves the task's open divergences
    (`apply_transition` -> `resolve_divergences_for_task`), and today the scheduler commits that
    with the rest of the staging: the divergence is closed by a review that never happened, and a
    `run_divergence_resolved` row says so. Mutation 4.1 must fail this.

    **What a rollback cannot take back, recorded and not asserted:** `resolve_divergences_for_task`
    broadcasts `run_divergence_resolved` over SSE at staging time, so the live activity feed still
    reads *"1 open divergence on T resolved"* after the rollback, until a reload drops it (its row
    was rolled back). That is D8's accepted residual, and §8.5 files it as a finding once §2 makes
    it real. `broadcasts` is captured for that record.
    """
    task_id, before, divergence_id, _broadcasts = await _divergence_leg(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    async with async_session_factory() as db:
        divergence = await _divergence(db, divergence_id)
        assert divergence.resolved_at is None
    assert await _events("run_divergence_resolved") == 0
    assert await _snapshot(task_id) == before


# ---------------------------------------------------------------------------
# 1.8b — input withdrawn while its turn is dispatched is not counted
# ---------------------------------------------------------------------------


async def test_input_withdrawn_during_its_dispatch_is_not_counted(app, auth_headers):
    """1.8b (R3, F328, design D13). The operator withdraws the entry while its turn is being
    dispatched, and the dispatch is then refused. Today the refusal branch counts it anyway, to
    the limit, gives it the reason *"the Hub stopped retrying"* and announces
    `queue_entry_abandoned` — about input the operator withdrew. Mutation 4.4b (2.1's
    `state == "queued"` filter dropped) must fail this.

    **This covers only a dispatch that holds no database lock**, which the patched trigger does
    not. A real review dispatch holds the write lock while it records the reviewer, so an operator's
    withdrawal waits on it and commits after the re-read, and is still counted (pre-approval review,
    test O2). F328 is narrowed by §2, not closed (8.5a).
    """
    agent = "rr-withdrawn"
    await _register(app, auth_headers, agent)
    entry_id = await _entry(
        agent, await _conversation(agent), attempts=DELIVERY_ATTEMPT_LIMIT - 1, content="e"
    )
    calls: list = []
    withdrew: list = []

    async def withdraw_then_refuse(**kw):
        ids = tuple(kw["queue_entry_ids"])
        calls.append(ids)
        if len(calls) > 1:
            raise RuntimeError("test guard")
        async with async_session_factory() as other:
            # Recorded, not asserted here: an `AssertionError` raised inside the product's call
            # path would satisfy this test's `raises=AssertionError` for the wrong reason.
            withdrew.append(await withdraw_entry(other, "proj-test", entry_id) is not None)
        raise _refused(ids)

    with patch(TRIGGER, AsyncMock(side_effect=withdraw_then_refuse)):
        await schedule_agent("proj-test", agent)
    assert withdrew == [True]
    row = await _row(entry_id)
    assert (row.state, row.delivery_attempts) == ("withdrawn", DELIVERY_ATTEMPT_LIMIT - 1)
    assert not row.abandoned_reason
    assert await _events("queue_entry_abandoned", agent=agent) == 0
