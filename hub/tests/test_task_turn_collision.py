"""D8: a task's checkout takes one writing turn at a time, and waiting is not failing.

Before per-task isolation "one process per checkout" was true without anybody stating it. It was a
*consequence* of two independent facts — a checkout belonged to an agent, and an agent may have
only one run in flight (`agent_trigger.py`'s per-agent 409) — and keying the workspace by task
broke the coupling. `resolve_bound_task` never consults `Task.assignee`, and `bind_run_to_task`
fills `assignee` only when it is empty, so nothing refused a second agent on the same task: an
operator starting task T on one builder while another was already running on it is an ordinary
sequence of clicks, and it handed two live processes the same working directory on the same branch.

Four things have to hold together, and each is a separate way for this to be wrong:

1.  the refusal exists at all, and names who holds the task (4.12);
2.  it is scoped to exactly the turns that get a task checkout — a review turn, a read-only agent
    and a grandfathered task are all safe today and must stay startable (4.13);
3.  it is classified **transient**, so the queue entry waits instead of being counted towards
    abandonment and dropped after three ticks (4.15);
4.  the flow scheduler pre-empts it and records the collision, rather than letting a busy flow
    report itself stalled (4.16, finding F23's reason).

**Asserted at `trigger_agent_directly`, not through `POST /trigger`.** `schedule_agent` converts
every `TriggerAgentError` into a `ScheduleResult` and never re-raises, so the route answers 200
with `status: "queued"` and a waiting reason. A route-level assertion about a 409 would be vacuous
— which is what R3 caught in this task's own text.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1 import agent_trigger
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EvidenceFootprint,
    InboundQueueEntry,
    Loop,
    Project,
    RequirementEvidence,
    Run,
    Task,
    TaskRequirementLink,
)
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, new_entry
from hub.scheduler import decide_firing
from hub.turn_scheduler import schedule_agent

pytestmark = pytest.mark.asyncio

#: Valid task ids, in the shape `short_id` mints and `validate_task_id` accepts: `task-` plus hex.
#: An id of any other shape takes `task_workspace`'s unmintable-id fallback, gets the per-agent
#: checkout, and would make every test here pass while proving nothing.
HELD_TASK = "task-c0ffee0c0ffee0"
OTHER_TASK = "task-b0b0b0b0b0b0"

HOLDER = "collision-holder"
CHALLENGER = "collision-challenger"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(path), capture_output=True, text=True, check=False
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


async def _agent(app, auth_headers, bind_runner, name, config=None):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude", **(config or {})}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="claude")


async def _conversation(agent: str) -> str:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


async def _task(task_id: str, *, scheme: Optional[str] = None, status: str = "in_progress") -> None:
    """A task row. *scheme* is only ever passed as `'agent'`, standing in for migration `0095`.

    Nothing in the product may write that column (design D4), so a grandfathered task can only be
    created the way the migration creates one.
    """
    async with async_session_factory() as session:
        task = Task(id=task_id, project_id="proj-test", title=task_id, status=status)
        if scheme is not None:
            task.workspace_scheme = scheme
        session.add(task)
        await session.commit()


async def _holding_run(agent: str, task_id: str, run_id: str = "run-holder") -> str:
    """A `running` run bound to *task_id* — the fact the refusal reads.

    Written directly rather than by taking a real turn: the holder's own spawn is not part of any
    statement here, and a second live turn in the harness would need its own draining.
    """
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                task_id=task_id,
            )
        )
        await session.commit()
    return run_id


async def _end_run(run_id: str) -> None:
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()


async def _spawned_cwd(*, agent: str, **kwargs) -> Optional[str]:
    """Take one turn far enough to decide its workspace and return the spawned `cwd`.

    `test_turn_workspace.py`'s harness, and the same two clean-ups for the same reasons: the
    background task the trigger started, and the still-`running` `Run` row the next turn would be
    refused over.

    **The wait and the drain are inside the patch**, and that placement is load-bearing rather than
    incidental. `trigger_agent_directly` returns as soon as it has scheduled `_execute_run`, and
    the spawn happens inside that task — so a `with` block closing on the return releases the patch
    before the call it patches happens, and under load the run reaches the real `PtySession.spawn`,
    fails for want of a binary, and `cwd` is never captured. That is the same scoping bug
    `test_project_workspace_unavailable.py` records as "the whole of F40's real cause", and it was
    reproduced on unmodified `main` while writing this file. The wait itself is on `"cwd" in
    captured` rather than on `_background_runs`, which is not populated yet at the moment the drain
    would look.
    """
    captured = {}

    def _spawn(cmd, cwd=None, env=None, **rest):
        captured["cwd"] = cwd
        raise RuntimeError("stop here: the workspace decision is what this test is about")

    async with async_session_factory() as session:
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                await trigger_agent_directly(session=session, agent=agent, **kwargs)
                for _ in range(1000):
                    if "cwd" in captured:
                        break
                    await asyncio.sleep(0.01)
                while agent_trigger._background_runs:
                    await asyncio.gather(
                        *list(agent_trigger._background_runs), return_exceptions=True
                    )

    async with async_session_factory() as session:
        for run in (
            (await session.execute(select(Run).where(Run.agent == agent, Run.status == "running")))
            .scalars()
            .all()
        ):
            run.status = "failed"
        await session.commit()
    return captured.get("cwd")


# ---------------------------------------------------------------------------
# 4.12 — the refusal exists, and says who holds it
# ---------------------------------------------------------------------------


async def test_a_second_agent_is_refused_while_another_holds_the_tasks_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.12 — the invariant that used to follow for free from one-checkout-per-agent.

    The message names the holder because that is the only actionable half: "the task is busy" tells
    an operator nothing they can look at, and the agent named is the one whose turn has to end.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    await _holding_run(HOLDER, HELD_TASK)

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent=CHALLENGER,
                    message="I'll take this one too",
                    conversation_id=conversation_id,
                    session=session,
                    task_id=HELD_TASK,
                )

    assert HOLDER in excinfo.value.detail
    assert HELD_TASK in excinfo.value.detail
    # Nothing was provisioned: the refusal sits above the first call that touches the disk.
    assert not (repo / ".agentweave" / "tasks" / HELD_TASK).exists()


async def test_a_turn_on_a_different_task_is_not_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The refusal is per *task*, not per project.

    Without this, a refusal keyed on "any running run exists" would pass 4.12 and quietly serialise
    the whole project down to one writing turn — which is the opposite of what per-task isolation
    is for.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    await _task(OTHER_TASK)
    await _holding_run(HOLDER, HELD_TASK)

    cwd = await _spawned_cwd(
        project_id="proj-test",
        agent=CHALLENGER,
        message="a different piece of work",
        conversation_id=conversation_id,
        task_id=OTHER_TASK,
    )

    assert cwd is not None


# ---------------------------------------------------------------------------
# 4.13 — the three exemptions
# ---------------------------------------------------------------------------


async def test_a_review_turn_bound_to_the_held_task_is_not_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.13(a) — a review turn is bound to the task it inspects and never touches its checkout.

    It runs in a checkout of the commit under review, which `review_context` resolves *instead of*
    the ordinary workspace rather than as an adjustment to it. Refusing it would forbid exactly the
    thing a busy task most needs: somebody looking at what was just done.

    The exemption is structural rather than a clause — the refusal lives inside the branch a review
    turn never enters — so this test is the guard against a later reading that moves the check up to
    where the binding is first known and makes it apply to everything bound.
    """
    repo = _init_repo(tmp_path / "repo")
    (repo / "work.txt").write_text("the work under review\n")
    _git(repo, "add", "work.txt")
    _git(repo, "commit", "-q", "-m", "the work")
    reviewed_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK, status="completed")
    await _holding_run(HOLDER, HELD_TASK)
    async with async_session_factory() as session:
        session.add(
            TaskRequirementLink(
                id="link-collision",
                project_id="proj-test",
                task_id=HELD_TASK,
                requirement_id="req-collision",
            )
        )
        session.add(
            RequirementEvidence(
                id="ev-collision",
                project_id="proj-test",
                requirement_id="req-collision",
                task_id=HELD_TASK,
                digest="e" * 64,
                kind="commit",
                actor_kind="agent",
                actor=HOLDER,
                summary="done",
                review_state="accepted",
            )
        )
        session.add(
            EvidenceFootprint(
                id="fp-collision",
                project_id="proj-test",
                evidence_id="ev-collision",
                kind="git",
                commit_sha=reviewed_commit,
                branch="main",
            )
        )
        await session.commit()

    cwd = await _spawned_cwd(
        project_id="proj-test",
        agent=CHALLENGER,
        message="review it",
        conversation_id=conversation_id,
        task_id=HELD_TASK,
        review_task_id=HELD_TASK,
    )

    assert cwd is not None
    # The review checkout, not the task's working directory — the point of the exemption.
    assert Path(cwd) != repo / ".agentweave" / "tasks" / HELD_TASK
    assert _git(Path(cwd), "rev-parse", "HEAD").stdout.strip() == reviewed_commit


async def test_a_read_only_agent_is_not_refused_while_another_holds_the_task(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.13(b) — a read-only agent shares the project checkout and has no isolation to collide over.

    `is_writing_agent` keeps precedence over the binding (task 4.7), so this turn was never going to
    take the task's checkout. Refusing it would stop an analyst reading a repository because
    somebody else is writing in a different directory.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER, config={"read_only": True})
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    await _holding_run(HOLDER, HELD_TASK)

    cwd = await _spawned_cwd(
        project_id="proj-test",
        agent=CHALLENGER,
        message="just reading",
        conversation_id=conversation_id,
        task_id=HELD_TASK,
    )

    assert Path(cwd) == repo


async def test_a_grandfathered_task_is_not_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.13(c) — a task stamped `workspace_scheme = 'agent'` is worked in per-agent checkouts.

    There the old coupling still holds: each agent has its own directory, and one agent per
    directory is still enforced by the per-agent refusal thirty lines above. Refusing here would
    forbid something that has been safe for as long as the product has existed, on a task the
    operator was already part-way through.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK, scheme="agent")
    await _holding_run(HOLDER, HELD_TASK)

    cwd = await _spawned_cwd(
        project_id="proj-test",
        agent=CHALLENGER,
        message="carry on with the old one",
        conversation_id=conversation_id,
        task_id=HELD_TASK,
    )

    assert cwd is not None


# ---------------------------------------------------------------------------
# 4.15 — waiting is not failing
# ---------------------------------------------------------------------------


async def test_a_collision_leaves_the_entry_queued_and_delivers_it_when_the_task_is_free(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.15 — the refusal that would otherwise have thrown the operator's message away.

    `schedule_agent` sorts refusals into two buckets and the terminal one counts a delivery attempt,
    withdrawing the entry at `DELIVERY_ATTEMPT_LIMIT`. That branch's own comment gives its reason —
    a refusal raised there "repeats identically forever" — and a collision with another turn is the
    one refusal in the set that does not: it ends when that turn does. Left in the terminal bucket,
    three ticks of an ordinary flow discard the input.

    So the loop below runs the limit *and one more*, and then frees the task: the same entry, never
    re-queued by anybody, is delivered.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    run_id = await _holding_run(HOLDER, HELD_TASK)

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        session.add(
            new_entry(
                project_id="proj-test",
                agent=CHALLENGER,
                origin_type="operator",
                content="please start this",
                hop_depth=0,
                conversation_id=conversation_id,
                task_id=HELD_TASK,
            )
        )
        await session.commit()

    for _ in range(DELIVERY_ATTEMPT_LIMIT + 1):
        # `which` is patched here for the same reason as every other schedule in this file. On a
        # machine with no `claude` on PATH the turn is refused for *that* reason instead, and that
        # refusal is terminal — so the collision this test is about never gets to fire. CI is such
        # a machine, which is how this passed locally and failed there.
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", CHALLENGER)
        assert result.terminal_failure is False
        assert HOLDER in (result.waiting_reason or "")

    async with async_session_factory() as session:
        entry = (await session.execute(select(InboundQueueEntry))).scalars().one()
        assert entry.state == "queued"
        assert (entry.delivery_attempts or 0) == 0
        assert entry.abandoned_reason is None

    await _end_run(run_id)

    captured = {}
    # Delivery is observed *as it happens*, not read back afterwards, and that distinction is the
    # whole reason this block looks like it does. `_spawn` below raises, so the run this schedule
    # starts ends `failed`, and `return_run_entries` puts the entry straight back — correctly: a
    # run that died carrying input must not swallow it. Reading `entry.state` after the background
    # run has finished therefore says nothing about the delivery this test set up. It used to pass
    # anyway, because the *re-drain* that follows a run ending delivered the entry a second time
    # and left `delivered` behind — an outcome produced by a second delivery, asserted by a test
    # whose own docstring says "never re-queued by anybody", and true only on a machine where the
    # re-drain could get as far as a spawn. On a machine with no `claude` on PATH the second
    # delivery is refused for that reason instead and the entry reads `queued`, which is how this
    # cell turned CI red while passing here.
    deliveries = []
    real_deliver = agent_trigger.deliver_entries_with_run

    async def _record_delivery(db, **kwargs):
        entries = await real_deliver(db, **kwargs)
        deliveries.append([(entry.id, entry.delivery_attempts or 0) for entry in entries])
        return entries

    def _spawn(cmd, cwd=None, env=None, **rest):
        captured["cwd"] = cwd
        raise RuntimeError("stop here: delivery is what this test is about")

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.api.v1.agent_trigger.deliver_entries_with_run", _record_delivery):
                result = await schedule_agent("proj-test", CHALLENGER)
                for _ in range(1000):
                    if "cwd" in captured:
                        break
                    await asyncio.sleep(0.01)
                while agent_trigger._background_runs:
                    await asyncio.gather(
                        *list(agent_trigger._background_runs), return_exceptions=True
                    )

    assert result.waiting_reason is None
    assert captured.get("cwd") is not None
    # The entry the collision refused was handed to this turn, and the `0` is the load-bearing
    # half: `delivery_attempts` is incremented only by `return_run_entries`, so a zero at the
    # moment of delivery is the assertion that nothing put this entry back to get here.
    async with async_session_factory() as session:
        entry = (await session.execute(select(InboundQueueEntry))).scalars().one()
        assert deliveries[0] == [(entry.id, 0)]


async def test_the_status_route_reports_the_collision_the_trigger_refused_on(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """F97 — the reason has to survive as far as the surface the operator is actually looking at.

    Measured live on 2026-08-28 with two agents and one task. `POST /agent/trigger` answered with
    the refusal's own sentence; `GET /queue/{agent}/status`, polled one second later, answered
    `waiting_count: 1, waiting_reason: null`. That route re-derives the reason from questions it
    can answer itself — is the agent running, is the hop budget spent, is the CLI on PATH, is the
    workspace there — and a collision with another turn is none of them, so it fell through to the
    delivery-attempt counter, which for a transient refusal is zero, and reported nothing at all.

    The state under test is exactly the one the test above leaves behind, which is the point: the
    entry is queued, unbilled and correct, and the operator could not tell that from an entry that
    is stuck.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    run_id = await _holding_run(HOLDER, HELD_TASK)

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        session.add(
            new_entry(
                project_id="proj-test",
                agent=CHALLENGER,
                origin_type="operator",
                content="please start this",
                hop_depth=0,
                conversation_id=conversation_id,
                task_id=HELD_TASK,
            )
        )
        await session.commit()

    # `which` patched for this file's usual reason: without it the turn is refused for a missing
    # CLI instead, and that refusal is both terminal and one the status route can already see.
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        result = await schedule_agent("proj-test", CHALLENGER)
        assert result.terminal_failure is False

        status = await app.get(
            f"/api/v1/projects/proj-test/queue/{CHALLENGER}/status", headers=auth_headers
        )
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["waiting_count"] == 1
    assert body["delivery_attempts"] == 0
    assert HOLDER in (body["waiting_reason"] or ""), body["waiting_reason"]
    assert HELD_TASK in body["waiting_reason"]

    # And the wait ending clears it, so a requeued entry never explains itself with a wait that
    # is over.
    await _end_run(run_id)

    def _spawn(cmd, cwd=None, env=None, **rest):
        raise RuntimeError("stop here: delivery is what clears the reason")

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await schedule_agent("proj-test", CHALLENGER)
            while agent_trigger._background_runs:
                await asyncio.gather(*list(agent_trigger._background_runs), return_exceptions=True)

    async with async_session_factory() as session:
        entry = (await session.execute(select(InboundQueueEntry))).scalars().one()
        assert entry.waiting_reason is None


# ---------------------------------------------------------------------------
# 4.16 — the flow scheduler's counterpart
# ---------------------------------------------------------------------------


async def test_a_flow_records_a_task_another_agents_turn_holds_instead_of_dropping_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.16 — finding F23's shape, one column over.

    A candidate whose own assignee is mid-turn is recorded rather than skipped, because a bare
    `continue` made a flow whose agents were all busy report itself stalled with `current_tasks:
    []`. D8 adds a second way to be unstartable that the walk cannot see from `running` alone: the
    task below has *no assignee at all*, so nothing in the per-agent view knows it is being worked,
    and the firing would happily staff its default agent onto a checkout somebody else is using.

    The pair recorded is `(task, the agent that holds it)` — the turn that is actually running, not
    the one this firing wanted to start.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _holding_run(HOLDER, HELD_TASK)

    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-collision",
                project_id="proj-test",
                name="Collision",
                agent=CHALLENGER,
                message="work the queue",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.commit()
        session.add(
            Loop(
                id="loop-collision",
                project_id="proj-test",
                job_id="job-collision",
                purpose="collision",
            )
        )
        await session.commit()
        session.add(
            Task(
                id=HELD_TASK,
                project_id="proj-test",
                title="held work",
                status="in_progress",
                loop_id="loop-collision",
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        loop = (await session.execute(select(Loop))).scalars().one()
        decision = await decide_firing(session, loop, default_agent=CHALLENGER)

    assert [(task_id, agent) for task_id, agent in decision._cannot_staff] == [(HELD_TASK, HOLDER)]
    assert decision.selections == ()


# ---------------------------------------------------------------------------
# F90 — the hold ends when the holder does, without waiting for something else
# ---------------------------------------------------------------------------


async def test_a_run_ending_redrains_the_agents_it_was_holding_back(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """F90. `schedule_agent` at the end of a run re-drains *that* agent, and D8 parks a **different**
    one.

    A challenger refused by the one-writer rule is refused transiently: the entry keeps its
    delivery attempts, stays `queued`, and `turn_scheduler` says "the next tick tries again". There
    is no tick. `redrain_queued_agents` is reachable from project open, settings save and relocate
    and from nowhere else, so the entry waited for an unrelated operator action.

    Measured live on 2026-08-28 in `aw-e2e1`: `builder` held a task, `reviewer`'s turn on the same
    task was parked, `builder` finished, and four minutes later every agent was idle with the entry
    still `queued`, `delivery_attempts` 0 and `waiting_reason: null`. Saving unrelated queue
    settings delivered it instantly.

    **Nothing here calls `schedule_agent` for the challenger**, which is the whole assertion, and it
    is what `test_a_collision_leaves_the_entry_queued_and_delivers_it_when_the_task_is_free` cannot
    say: that test ends the holder's run with a database write and then schedules the challenger by
    hand, so it proves the entry *can* be delivered once the task is free and not that anything
    delivers it. Here the holder takes a real turn and the run ends through `_execute_run`.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    # Both in one sync: `_agent` posts the whole roster, so a second call would unregister the
    # first agent.
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {HOLDER: {"runner": "claude"}, CHALLENGER: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(HOLDER, cli="claude")
    await bind_runner(CHALLENGER, cli="claude")
    holder_conversation = await _conversation(HOLDER)
    challenger_conversation = await _conversation(CHALLENGER)
    await _task(HELD_TASK)

    # Parked, not merely queued: written straight to the queue so nothing has scheduled it, which
    # is the state a transient D8 refusal leaves behind.
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        session.add(
            new_entry(
                project_id="proj-test",
                agent=CHALLENGER,
                origin_type="operator",
                content="my turn on this task",
                hop_depth=0,
                conversation_id=challenger_conversation,
                task_id=HELD_TASK,
            )
        )
        await session.commit()

    def _spawn(cmd, cwd=None, env=None, **rest):
        # `FileNotFoundError`, not the `RuntimeError` the other harnesses in this file raise. That
        # one escapes `_execute_run` entirely — the spawn sits above its `try` — so the run is
        # never finalised and the very moment under test never arrives. This is the "the CLI is
        # not on PATH" branch, which ends the run properly.
        raise FileNotFoundError("claude")

    async def _challenger_run():
        async with async_session_factory() as session:
            return (
                (await session.execute(select(Run).where(Run.agent == CHALLENGER)))
                .scalars()
                .first()
            )

    async with async_session_factory() as session:
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent=HOLDER,
                    message="I have this task",
                    conversation_id=holder_conversation,
                    session=session,
                    task_id=HELD_TASK,
                )
                # The holder's turn, then whatever its ending starts. Drained repeatedly because
                # the challenger's run is created inside the holder's, so one pass over the set
                # that existed at the first look would miss it.
                for _ in range(400):
                    if agent_trigger._background_runs:
                        await asyncio.gather(
                            *list(agent_trigger._background_runs), return_exceptions=True
                        )
                    if await _challenger_run() is not None:
                        break
                    await asyncio.sleep(0.01)

    run = await _challenger_run()
    assert run is not None, (
        "the challenger never got a turn after the holder's run ended; nothing on the "
        "run-completion path re-drains an agent other than the one whose run it was"
    )
    assert run.task_id == HELD_TASK


async def test_a_holder_whose_tail_raises_still_releases_the_task_it_held(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """F286, task 3.3 — the same release as the test above, on the run that used to skip it.

    `test_a_run_ending_redrains_the_agents_it_was_holding_back` ends the holder's run through the
    spawn-failure branch, so the run is relabelled `failed` and the release rode along with the
    relabel. This one ends it the other way: the turn runs, exits 0, and something *after* the
    terminal commit raises. Before F286 the release was gated on the relabel having happened, so
    exactly this shape — a run that ended cleanly and then tripped over its own bookkeeping — kept
    D8's checkout for good, and the challenger parked behind it never ran. Nothing recovers that
    on its own: `redrain_queued_agents` is reachable from project open, settings save and relocate,
    and from nowhere else.

    The exception is **injected** rather than provoked, and injected **after the terminal commit**
    (`_report_abandoned_entries` is the first `await` past `db.commit()` in `_execute_run`'s
    finalize block). `holder_status_when_it_raised` is the guard on that placement: raised any
    earlier the row would still read `running`, which is the case that always worked.

    As in the F90 test above, **nothing here schedules the challenger.**
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {HOLDER: {"runner": "claude"}, CHALLENGER: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(HOLDER, cli="claude")
    await bind_runner(CHALLENGER, cli="claude")
    holder_conversation = await _conversation(HOLDER)
    challenger_conversation = await _conversation(CHALLENGER)
    await _task(HELD_TASK)

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        session.add(
            new_entry(
                project_id="proj-test",
                agent=CHALLENGER,
                origin_type="operator",
                content="my turn on this task",
                hop_depth=0,
                conversation_id=challenger_conversation,
                task_id=HELD_TASK,
            )
        )
        await session.commit()

    def _spawn(cmd, cwd=None, env=None, **rest):
        """A turn that succeeds — the opposite of the F90 test's `FileNotFoundError`.

        The whole point here is a run that reaches a *terminal* status of its own before anything
        goes wrong, so the failure has to happen downstream of the finalize commit rather than at
        the spawn.
        """
        pty = MagicMock()
        pty.pid = 4321
        pty.read.side_effect = lambda *a, **k: ""
        pty.wait.return_value = 0
        return pty

    holder_status_when_it_raised = []
    real_report = agent_trigger._report_abandoned_entries

    async def _raise_once_for_the_holder(db, project_id, agent, run_id):
        if agent == HOLDER and not holder_status_when_it_raised:
            # Its own connection, so this is the committed status: `async_session_factory` sets
            # `expire_on_commit=False`, and the window's own session would read the value it
            # assigned in memory whether or not the commit had happened yet.
            async with async_session_factory() as probe:
                holder_status_when_it_raised.append((await probe.get(Run, run_id)).status)
            raise RuntimeError("bookkeeping after the terminal commit blew up")
        return await real_report(db, project_id, agent, run_id)

    async def _challenger_run():
        async with async_session_factory() as session:
            return (
                (await session.execute(select(Run).where(Run.agent == CHALLENGER)))
                .scalars()
                .first()
            )

    async with async_session_factory() as session:
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                with patch.object(
                    agent_trigger, "_report_abandoned_entries", _raise_once_for_the_holder
                ):
                    await trigger_agent_directly(
                        project_id="proj-test",
                        agent=HOLDER,
                        message="I have this task",
                        conversation_id=holder_conversation,
                        session=session,
                        task_id=HELD_TASK,
                    )
                    for _ in range(400):
                        if agent_trigger._background_runs:
                            await asyncio.gather(
                                *list(agent_trigger._background_runs), return_exceptions=True
                            )
                        if await _challenger_run() is not None:
                            break
                        await asyncio.sleep(0.01)

    assert holder_status_when_it_raised == ["completed"], (
        "the raise has to land on a row that has already ended — otherwise this tests the "
        "relabel, which was never the broken half"
    )

    run = await _challenger_run()
    assert run is not None, (
        "the challenger never got a turn: the holder's run ended cleanly, its tail raised, and "
        "the task checkout it was holding was never released"
    )
    assert run.task_id == HELD_TASK

    async with async_session_factory() as session:
        holder_run = (await session.execute(select(Run).where(Run.agent == HOLDER))).scalars().one()
        # The relabel stays gated, and this is the row it is gated for. A completed run whose
        # bookkeeping raised is still a completed run.
        assert holder_run.status == "completed"
        assert holder_run.error is None
