"""`loop-becomes-a-flow` task 10.5 — the whole chain, with no operator in it.

A document declares A → B. A flow runs A with one agent, a second agent reviews and approves it, and
B then starts — and nothing in that sequence is an operator action. This is the assertion the change
exists for: every group before it is a mechanism, and this is the only test that shows the mechanisms
compose into the thing the proposal promised.

**What is real here and what is simulated, stated plainly, because the difference is the whole value
of the test.** Real: the firing decision, the reviewer ladder, the claim, the dependency gate, the
queue entry, the `review_task_id`, and the git checkout the reviewer is spawned into. Simulated: the
two *judgements* a model would make — that the work is done, and that it passes review — because
there is no model in a test. So this demonstrates that the Hub **routes** the chain unaided; it
cannot demonstrate that an agent decides well.

**`test_the_reviewer_reaches_its_verdict_from_the_checkout` is the load-bearing one** (design D9).
10.5 says a chain that completes because the two agents talked has not demonstrated anything, so the
author's work is committed to a branch that does not exist on `main`, and the assertion is that the
reviewer's own working directory contains it. No message passes between the two agents at any point
— there is no `send_message` in this file, deliberately.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EvidenceFootprint,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskDependency,
    TaskTransition,
)
from hub.scheduler import JobScheduler
from hub.task_transition_service import apply_transition
from hub.task_transitions import ACTOR_OPERATOR, run_actor

from .test_agent_trigger import _await_background_run, _fake_pty, _init_repo
from .test_review_turn import _REAL_ENSURE_REVIEW_CHECKOUT, _author_commit, _roster

pytestmark = pytest.mark.asyncio

_SUCCESS_LINE = '{"type":"result","subtype":"success","is_error":false}\n'

BUILDER = "builder"
CRITIC = "critic"
NOW = datetime.now(timezone.utc)


async def _flow_with_a_then_b(db, *, commit: str, branch: str):
    """The decomposition an operator would have approved: A, then B, with A already finished.

    A is walked to `completed` **through `apply_transition` as BUILDER**, not written at that status
    directly. An unattributable completed task is offered to nobody (`task_is_claimable_by`), so a
    fixture that skipped the history would produce a queue the flow correctly refuses to staff, and
    the test would fail for a reason that has nothing to do with what it is checking.
    """
    job = AIJob(
        id="job-chain",
        project_id="proj-test",
        name="Ledger decomposition",
        agent=BUILDER,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()

    db.add(
        SpecDocument(
            id="doc-chain",
            project_id="proj-test",
            path="spec/ledger.html",
            title="Ledger",
            phase="current",
            kind="capability",
        )
    )
    db.add(
        SpecRequirement(
            id="req-chain",
            project_id="proj-test",
            document_id="doc-chain",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    await db.commit()

    loop = Loop(
        id="loop-chain",
        project_id="proj-test",
        job_id=job.id,
        purpose="balance the ledger",
        spec_document_id="doc-chain",
    )
    db.add(loop)
    await db.commit()

    task_a = Task(
        id="task-chain-a",
        project_id="proj-test",
        title="Balance the ledger",
        status="pending",
        loop_id=loop.id,
    )
    task_b = Task(
        id="task-chain-b",
        project_id="proj-test",
        title="Report on the balanced ledger",
        status="pending",
        loop_id=loop.id,
    )
    db.add_all([task_a, task_b])
    await db.commit()

    db.add(
        TaskDependency(
            id="dep-chain",
            project_id="proj-test",
            task_id=task_b.id,
            depends_on_task_id=task_a.id,
        )
    )
    await db.commit()

    actor = run_actor(run_id="run-chain-builder", agent=BUILDER)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task_a, status, actor)
    await db.commit()

    # The evidence that makes A reviewable at all: without a commit there is nothing to check out,
    # and `prepare_review_turn` refuses rather than guessing.
    db.add(
        RequirementEvidence(
            id="ev-chain",
            project_id="proj-test",
            requirement_id="req-chain",
            task_id=task_a.id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=BUILDER,
            summary="ledger balances",
            produced_at=NOW - timedelta(minutes=5),
        )
    )
    db.add(
        EvidenceFootprint(
            id="fp-chain",
            project_id="proj-test",
            evidence_id="ev-chain",
            kind="git",
            commit_sha=commit,
            branch=branch,
            observed_at=NOW - timedelta(minutes=5),
        )
    )
    await db.commit()
    return job, loop


async def _fire(job_id, *, spawn=None):
    """One firing, with the spawn always faked.

    **Always**, even where the test does not inspect it. A firing that reaches a real
    `PtySession.spawn` hangs the suite rather than failing it — the tell is a flat CPU reading
    against a growing wall clock — and this file binds a real project workspace, so its turns get
    far enough to try. The first version of this helper faked the spawn only when a test asked for
    the handle, and hung for exactly that reason.
    """
    scheduler = JobScheduler()
    spawn = spawn or _fake_pty([_SUCCESS_LINE])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                job = await db.get(AIJob, job_id)
                await scheduler._fire_job_internal(job, trigger="scheduled", session=db)
            await _await_background_run()


async def _entries():
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.origin_type == "job")
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def test_the_chain_runs_a_review_and_then_b_with_no_operator_action(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Task 10.5. Three firings, and the operator is absent from all of them.

    Firing 1 staffs the review — A is finished and sorts ahead of pending work (design D10), and
    BUILDER may not review its own, so the ladder reaches CRITIC by availability alone with nothing
    declared. Firing 2, after the verdict, starts B: its prerequisite is approved, so the dependency
    gate that refused it now permits it.
    """
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, BUILDER, CRITIC)
    async with async_session_factory() as db:
        job, _loop = await _flow_with_a_then_b(db, commit=sha, branch="agentweave/builder")

    # --- firing 1: the review is staffed, and B is not started alongside it -------------------
    await _fire(job.id)

    entries = await _entries()
    assert [e.agent for e in entries] == [CRITIC], "the ladder staffs the reviewer, not the author"
    assert entries[0].review_task_id == "task-chain-a"

    async with async_session_factory() as db:
        assert (
            await db.get(Task, "task-chain-b")
        ).status == "pending", (
            "B's prerequisite is not approved yet, so the gate must still refuse it"
        )

    # --- the reviewer's verdict, the one thing a test has to simulate --------------------------
    async with async_session_factory() as db:
        task_a = await db.get(Task, "task-chain-a")
        critic_actor = run_actor(run_id="run-chain-critic", agent=CRITIC)
        await apply_transition(db, task_a, "under_review", critic_actor)
        await apply_transition(db, task_a, "approved", critic_actor)
        await db.commit()

    # --- firing 2: B starts, because its prerequisite cleared ---------------------------------
    await _fire(job.id)

    entries = await _entries()
    assert len(entries) == 2, "one more firing, one more turn"
    assert entries[1].agent == BUILDER
    assert entries[1].review_task_id is None, "B is ordinary work, and acquires no checkout"
    assert "Report on the balanced ledger" in entries[1].content

    async with async_session_factory() as db:
        assert (await db.get(Task, "task-chain-b")).status == "assigned"
        assert (await db.get(Task, "task-chain-a")).status == "approved"


async def test_no_judgement_in_the_chain_was_the_operators(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """10.5's "with no operator action at any point", asserted against the recorded history — and
    narrowed to what the history can honestly support, for a reason worth reading.

    Every status change records its actor, so the claim is checkable rather than trusted. Checking
    it turned up that **the flow's own claim is attributed to the operator**: `_do_fire_job` calls
    `apply_transition(..., "assigned", operator())`, so the record says a human assigned every task
    a loop ever claimed. Nobody did. This predates the change — loops have always claimed this way —
    but 10.5 is the first requirement that reads the actor column and so the first thing to notice.

    It is not fixed here. `Actor` has two kinds, and its own docstring insists that *"no run id" and
    "the operator" are different propositions*; the flow's claim is a third — the Hub acting on a
    schedule — and giving it a name is a migration plus a semantic change to an audit trail the
    operator reads. Recorded as a design open question instead.

    So this asserts the thing that actually matters and is actually true: **no judgement in the
    chain was the operator's.** Nothing was completed, reviewed, approved or rejected by a human.
    The operator-attributed rows are pinned to exactly the flow's own claims, so if a real operator
    action ever creeps in, or if the attribution is fixed, this test fails and says which.
    """
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, BUILDER, CRITIC)
    async with async_session_factory() as db:
        job, _loop = await _flow_with_a_then_b(db, commit=sha, branch="agentweave/builder")

    await _fire(job.id)
    async with async_session_factory() as db:
        task_a = await db.get(Task, "task-chain-a")
        critic_actor = run_actor(run_id="run-chain-critic", agent=CRITIC)
        await apply_transition(db, task_a, "under_review", critic_actor)
        await apply_transition(db, task_a, "approved", critic_actor)
        await db.commit()
    await _fire(job.id)

    async with async_session_factory() as db:
        transitions = (
            (
                await db.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id.in_(("task-chain-a", "task-chain-b"))
                    )
                )
            )
            .scalars()
            .all()
        )

    assert transitions, "a chain that recorded no transitions has not run"

    # Every judgement — finishing work, and every review outcome — was an agent's.
    judgements = [
        t
        for t in transitions
        if t.to_status in ("completed", "under_review", "approved", "rejected", "revision_needed")
    ]
    assert judgements, "the chain must have reached a review outcome to be worth checking"
    assert all(t.actor_kind != ACTOR_OPERATOR for t in judgements), (
        "a judgement attributed to the operator means the flow did not route itself: "
        f"{[(t.task_id, t.to_status) for t in judgements if t.actor_kind == ACTOR_OPERATOR]}"
    )

    # And the operator-attributed rows are exactly the flow's own claims — the misattribution
    # above, pinned so that fixing it, or a genuine operator action appearing, both fail here.
    operator_rows = {
        (t.task_id, t.to_status) for t in transitions if t.actor_kind == ACTOR_OPERATOR
    }
    assert operator_rows == {("task-chain-b", "assigned")}, (
        "the only operator-attributed transition should be the flow claiming B; anything else is "
        "either a real operator action in the chain or the attribution having changed"
    )


async def test_the_reviewer_reaches_its_verdict_from_the_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Design D9, and 10.5's own qualification: *"a chain that completes because the two agents
    talked has not demonstrated this."*

    `ledger.py` exists only on the author's branch. If the reviewer were spawned into its ordinary
    working checkout the file would not be there, and the only way to see the work would be to ask
    the author — which is finding F10, the circularity `review_turn.py`'s docstring records: *"the
    only way to see it was to integrate it, which is what the review was meant to decide."*

    The real `ensure_review_checkout` is restored deliberately; the suite's default fake would make
    this assertion vacuous.
    """
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, BUILDER, CRITIC)
    async with async_session_factory() as db:
        job, _loop = await _flow_with_a_then_b(db, commit=sha, branch="agentweave/builder")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    await _fire(job.id, spawn=fake_spawn)

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    assert cwd == worktrees.review_path(repo, CRITIC)
    # The two halves of the property: not visible from the project, visible from where the reviewer
    # actually stands.
    assert not (repo / "ledger.py").exists()
    assert (cwd / "ledger.py").read_text() == "def balance():\n    return 0\n"


async def test_the_flow_never_relays_anything_between_the_two_agents(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The other half of 10.5's qualification, from the messaging side.

    The review mechanism is *claimability* — design D3's "no handoff message, no review task row,
    nothing asked of the finishing agent that could be omitted". A `Message` between the two would
    mean the chain ran on a handover the author had to remember to send, which is the thing the
    design replaced.
    """
    from hub.db.models import Message

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, BUILDER, CRITIC)
    async with async_session_factory() as db:
        job, _loop = await _flow_with_a_then_b(db, commit=sha, branch="agentweave/builder")

    await _fire(job.id)

    async with async_session_factory() as db:
        messages = (await db.execute(select(Message))).scalars().all()
    assert messages == [], "the flow staffs by claiming, never by relaying"


async def test_the_repo_helper_actually_hides_the_work(tmp_path):
    """A guard on the fixture rather than on the product.

    Every assertion above rests on `ledger.py` being absent from the project checkout. If
    `_author_commit` ever started committing to `main`, all of them would still pass and none of
    them would mean anything.
    """
    repo = _init_repo(tmp_path / "repo")
    _author_commit(repo, filename="ledger.py", body="x = 1\n")
    assert not (repo / "ledger.py").exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "agentweave/builder"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert "agentweave/builder" in branches
