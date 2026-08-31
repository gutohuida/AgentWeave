"""F162: approving inside the turn strands the work, and the record says the opposite.

**The window.** An agent calls `update_task(completed)` *during* its turn. The commit that holds
its edits does not exist yet — it is made when the turn ends. Between those two moments the task's
own branch still points at the commit it was cut from, so `task_integration.task_branch_tip`
answers with a commit that contains none of the work. That commit is already on the main branch by
construction, so `integrate` records `ALREADY_INTEGRATED` — *"there was nothing to merge"* — which
`is_retryable` classifies as a fact a repeat cannot alter. The task reads `approved`, the work sits
unmerged on its branch, and no surface offers a remedy.

**The reproduction was committed before the fix, asserting that wrong behaviour**, the way
`test_loop_lands_its_work.py` was — commit `9f9f18d` is where the measurement lives. Group 3 of
`approval-waits-for-the-turn-to-end` flipped it, and the flipped form is what is here now.

**It reproduces the window, not merely a state** (design D8). A test that only left the branch
empty would pass against code that resolves the base commit for an entirely different reason. What
makes this the window is that a run bound to the task is *live at the moment of the transition* —
a `Run` row recorded `running` **and** a session handle in this Hub process's registry, which is
what the fix's predicate reads. Both halves are asserted before the approval, so a fixture that
stopped producing either fails here rather than passing for the wrong reason.
"""

import pytest

from hub import requirement_evidence, run_liveness, task_integration, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, Run, Task

from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
from .test_task_integration import (
    AGENT_BRANCH,
    BASE,
    PATH,
    TASKS,
    accept_evidence,
    approve,
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


class LiveTurn:
    """Stands in for the `PtySession` a live turn holds in `run_liveness.active_ptys`.

    Only the two members the liveness question needs: `isalive()`, which `PtySession` answers from
    its own process handle (`pty_runner.py:287`), and `pid`, which the registry's other consumers
    read. Deliberately not a real subprocess — the predicate this reproduces is registry-first by
    design (D3), precisely so that liveness never depends on interrogating an OS pid.
    """

    def __init__(self, pid: int = 424242) -> None:
        self.pid = pid

    def isalive(self) -> bool:
        return True

    def terminate(self, force: bool = False) -> None:  # pragma: no cover - never called here
        pass


@pytest.fixture
async def turn(request):
    """An agent, a task-bound run recorded `running`, and a live handle for it in this process.

    Returns the run id. The registry entry is removed on teardown whatever the test does, because
    it is module-global state shared with every other test in the session.
    """
    async with async_session_factory() as session:
        session.add(Agent(id="ag-window", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-window",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_window-secret"),
            )
        )
        await session.commit()

    request.addfinalizer(lambda: run_liveness.active_ptys.pop("run-window", None))
    return "run-window"


async def bind_run_to(run_id: str, task_id: str) -> None:
    """What `run_task_binding._bind` writes (`run_task_binding.py:427`), set directly.

    Directly rather than through a real turn: the binding is one column, and driving a real agent
    process would make this a test of the runner rather than of the window.
    """
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        run.task_id = task_id
        await session.commit()


def go_live(run_id: str) -> LiveTurn:
    """Register the handle a turn holds while its process is running."""
    session = LiveTurn()
    run_liveness.active_ptys[run_id] = session
    return session


def end_the_turn(run_id: str) -> None:
    """What `_execute_run`'s `finally` does (`agent_trigger.py:2257`): the registry entry goes.

    The `Run` row's status is deliberately left alone. The predicate does not read it, and a test
    that tidied both would not distinguish a fix that reads the registry from one that reads the
    column — which is the distinction the crash case turns on.
    """
    run_liveness.active_ptys.pop(run_id, None)
    run_liveness.active_app_server_runs.discard(run_id)


def branch_the_task_without_committing(root, task_id):
    """The worktree branch a turn is given, at the commit it was cut from.

    This *is* the window: the branch exists because the turn started, and holds no commit because
    the turn has not ended. `git branch <name> main` rather than `checkout -b`, so the repository's
    checkout is left on `main` exactly as an integration expects to find it.
    """
    branch = worktrees.task_branch_name(task_id)
    git(root, "branch", branch, "main")
    return git(root, "rev-parse", branch).stdout.strip()


# ---------------------------------------------------------------------------
# 1.1 / 1.2 / 3.7 — the reproduction, flipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_inside_the_turn_is_refused(app, auth_headers, turn, tmp_path):
    """Tasks 1.1, 1.2 and 3.7: the window is refused, and the refusal costs the task nothing.

    As committed at `9f9f18d` this asserted the defect — a `200`, the task reading `approved`, a
    `skipped` integration naming the **base** commit with `ALREADY_INTEGRATED`, and the turn's real
    commit never reaching `main` with no retry able to alter it. Every one of those is now the
    opposite, and the last block is what makes it a fix rather than a block: once the turn has
    ended, the same task approves and merges the commit that actually holds the work.
    """
    base = make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Windowed loop")
    task = await loop_task(app, auth_headers, loop)
    await bind_run_to(turn, task)

    tip = branch_the_task_without_committing(tmp_path, task)
    assert tip == base, "the window requires the task's branch to hold none of the turn's work"

    # Both halves of "live", read back rather than assumed: the recorded status and the handle this
    # Hub process holds. The predicate reads exactly these two.
    async with async_session_factory() as session:
        run = await session.get(Run, turn)
        assert run.task_id == task and run.status == "running"
    go_live(turn)
    assert turn in run_liveness.active_ptys

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied"
    assert detail["unfinished"] == [{"agent": "builder", "run_id": turn}]

    # Status unchanged, and no integration attempted or recorded — both properties of where the
    # gate already sits, before `task.status = to_status` and before the history row.
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "under_review"
    assert await integrations(app, auth_headers, task) == []

    # The turn ends: its work is committed, and the registry entry goes with it.
    git(tmp_path, "checkout", "-q", worktrees.task_branch_name(task))
    (tmp_path / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    git(tmp_path, "add", "feature.py")
    git(tmp_path, "commit", "-q", "-m", "the turn's work")
    work = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    git(tmp_path, "checkout", "-q", "main")
    end_the_turn(turn)

    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == work
    assert work in commits_on(tmp_path, "main"), "the commit that holds the work is what merged"


# ---------------------------------------------------------------------------
# 2.1 / 2.5 / 2.6 — the predicate itself
#
# Directly, not through the gate. The gate's use of it is group 3's subject; these are about the
# one question `run_liveness` answers, and each of them is a sentence in the requirement.
# ---------------------------------------------------------------------------


async def plain_task(app, auth_headers, title="Some work"):
    created = await app.post(TASKS, json={"title": title}, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def add_run(run_id, *, task_id=None, status="running", agent="builder"):
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status=status,
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(f"aw_{run_id}-secret"),
            )
        )
        await session.commit()


async def live_turn(task_id, **kwargs):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        return await run_liveness.live_turn_for_task(session, task, **kwargs)


@pytest.mark.asyncio
async def test_a_run_this_process_holds_a_handle_for_reads_live(app, auth_headers, turn):
    """Task 2.1, arm 1. The registry is the answer, and it names the agent for the sentence."""
    task = await plain_task(app, auth_headers)
    await bind_run_to(turn, task)
    go_live(turn)

    found = await live_turn(task)
    assert found is not None
    assert found.run_id == turn
    assert found.agent == "builder"


@pytest.mark.asyncio
async def test_a_run_recorded_running_with_no_handle_reads_not_live(app, auth_headers, turn):
    """Task 2.1, arm 2 — and the whole reason the column is not the predicate.

    `reconcile_interrupted_runs` runs only in `lifespan()` startup, so a crashed agent leaves
    `Run.status == "running"` until the Hub restarts. Reading the column alone would wedge approval
    on this task indefinitely, on one crash, with no way out but a restart.
    """
    task = await plain_task(app, auth_headers)
    await bind_run_to(turn, task)

    async with async_session_factory() as session:
        assert (await session.get(Run, turn)).status == "running"
    assert turn not in run_liveness.active_ptys

    assert await live_turn(task) is None


@pytest.mark.asyncio
async def test_an_app_server_run_reads_live(app, auth_headers, request):
    """Task 2.1, arm 3. Codex's transport registers membership and no session handle at all
    (`agent_trigger.py:2411`), so a predicate that only consulted `active_ptys` would answer "not
    live" for a Codex agent that is still working."""
    task = await plain_task(app, auth_headers)
    await add_run("run-appserver", task_id=task, agent="codexer")
    run_liveness.active_app_server_runs.add("run-appserver")
    request.addfinalizer(lambda: run_liveness.active_app_server_runs.discard("run-appserver"))

    found = await live_turn(task)
    assert found is not None and found.run_id == "run-appserver"
    assert found.agent == "codexer"


@pytest.mark.asyncio
async def test_a_live_run_bound_to_another_task_is_not_this_tasks_turn(app, auth_headers, turn):
    """Task 2.4's scoping. The predicate asks about *this* task, not about the Hub being busy."""
    mine = await plain_task(app, auth_headers, title="Mine")
    theirs = await plain_task(app, auth_headers, title="Theirs")
    await bind_run_to(turn, theirs)
    go_live(turn)

    assert await live_turn(mine) is None
    assert await live_turn(theirs) is not None


@pytest.mark.asyncio
async def test_a_turn_is_never_blocked_by_itself(app, auth_headers, turn, request):
    """Task 2.5, design D10 — the exclusion, and the case that proves it is not too wide.

    A reviewer approves the work it has just read from inside its own turn, and since migration
    `0092` that turn is bound to the very task it is approving (`run_task_binding.py:170-189`,
    `:427`). Without the exclusion the gate refuses every review the product staffs, with a remedy
    the refused party cannot take — its only way out is for the turn to end, and it *is* the turn.

    The second half is what keeps it a carve-out rather than a hole: a *different* live run bound
    to the same task still answers, so excluding the actor does not disarm the predicate.
    """
    task = await plain_task(app, auth_headers)
    await bind_run_to(turn, task)
    go_live(turn)

    assert await live_turn(task, acting_run_id=turn) is None

    await add_run("run-second", task_id=task, agent="reviewer")
    run_liveness.active_ptys["run-second"] = LiveTurn()
    request.addfinalizer(lambda: run_liveness.active_ptys.pop("run-second", None))

    other = await live_turn(task, acting_run_id=turn)
    assert other is not None and other.run_id == "run-second"


@pytest.mark.asyncio
async def test_the_acting_run_exclusion_cannot_tell_a_working_turn_from_a_review(
    app, auth_headers, turn
):
    """Task 2.6 — D10's residual, pinned rather than left in prose (round 3).

    `_bind` writes `run.task_id = task.id` for a **working** turn exactly as for a review turn
    (`run_task_binding.py:427`), so the `Run` row carries nothing that distinguishes them. The
    exclusion is therefore unconditional on what the acting run is *for*, and an agent mid-turn on
    a task whose `completed` the **operator** recorded — which
    `_guard_author_is_not_reviewer` permits, since no completing agent is recorded
    (`task_transition_service.py:304-305`) — can approve its own in-flight work from inside its own
    turn. That is F162 reached through the carve-out built to protect reviewers.

    Narrow, and not a reason to drop D10, whose absence breaks every flow review. Closing it costs
    a join through `InboundQueueEntry.review_task_id`, which `Run` does not carry; the trade was
    considered and declined for scope. This asserts the shape so a later change that makes the join
    cheap knows exactly what it would be closing.
    """
    task = await plain_task(app, auth_headers)
    await bind_run_to(turn, task)
    go_live(turn)

    async with async_session_factory() as session:
        run = await session.get(Run, turn)
        # Nothing on the row says "this is a review". That is the residual.
        assert run.task_id == task
        assert not hasattr(run, "review_task_id")

    assert (
        await live_turn(task, acting_run_id=turn) is None
    ), "a working turn is excluded on the same terms as a review turn — the known residual"


# ---------------------------------------------------------------------------
# 3.1 / 3.8 / 3.9 — the gate's scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_whose_process_died_does_not_block_approval(app, auth_headers, turn, tmp_path):
    """A crashed agent leaves `Run.status == "running"` until the Hub next starts, because
    `reconcile_interrupted_runs` runs only in `lifespan()` (`main.py:350`). A gate reading that
    column would wedge this task's approval until a restart. This is the whole reason the predicate
    is registry-first and absence means not-live."""
    make_repo(tmp_path)
    await set_main_branch("main")
    loop = await make_loop(app, auth_headers, name="Crashed loop")
    task = await loop_task(app, auth_headers, loop)
    await bind_run_to(turn, task)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")

    async with async_session_factory() as session:
        assert (await session.get(Run, turn)).status == "running"
    assert turn not in run_liveness.active_ptys

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]


@pytest.mark.asyncio
async def test_a_task_with_no_run_is_unaffected(app, auth_headers, tmp_path):
    """No run bound to it at all — approval proceeds exactly as it did before this requirement.
    Deliberately without the `turn` fixture, so nothing in the process could answer for it."""
    make_repo(tmp_path)
    await set_main_branch("main")
    loop = await make_loop(app, auth_headers, name="Quiet loop")
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_rigor_does_not_exempt_the_refusal(app, auth_headers, turn, tmp_path):
    """Refused identically at `sketch` and at `gate`.

    The `sketch` half is the one that matters. `_enforced_requirements` filters `sketch` out
    entirely and `evaluate` returns early for a task with nothing enforcing, so a check placed
    below that return would be dead in every default project — which is where this defect was
    measured. Asserted by `blocking` being empty while `unfinished` is not: it is the liveness
    check refusing, not the requirement.
    """
    make_repo(tmp_path)
    await set_main_branch("main")
    run_headers = {"Authorization": "Bearer aw_run_window-secret"}
    await make_document(app, auth_headers, run_headers)
    task = await linked_task(app, auth_headers)
    await bind_run_to(turn, task)
    go_live(turn)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    sketch = refused.json()["detail"]
    assert sketch["blocking"] == [], "a sketch document enforces nothing — this is the live turn"
    assert sketch["unfinished"] and sketch["unfinished"][0]["agent"] == "builder"

    raised = await app.post(
        f"{BASE}/documents/{PATH}/rigor", json={"rigor": "gate"}, headers=auth_headers
    )
    assert raised.status_code == 200, raised.text

    refused_again = await app.patch(
        f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers
    )
    assert refused_again.status_code == 409, refused_again.text
    gated = refused_again.json()["detail"]
    assert gated["blocking"], "a gate document has its own reason to refuse as well"
    assert gated["unfinished"] == sketch["unfinished"], "and the live-turn claim is unchanged"


@pytest.mark.asyncio
async def test_a_project_where_integration_cannot_be_attempted_is_refused_the_same(
    app, auth_headers, turn, tmp_path
):
    """Task 3.9, and the interaction with `task-lifecycle-governance:720`.

    `_merge_situation` returns `None` for a project with no configured main branch, so the two
    repository-aware checks are silent there — each of their four preconditions is *a reason to not
    know, never a reason to refuse*. This check is not one of them and fires anyway: `approved` is
    a judgement that work is good, and judging work an agent has not finished producing is false
    whether or not anything is merged afterwards. Pinned here rather than left to be re-derived,
    because reading `:720` alone this looks like a breach of the corpus.

    The second half is what keeps `:720` true: once the turn ends, the same task approves and the
    integration is recorded as skipped exactly as it would have been before this requirement.
    """
    make_repo(tmp_path)
    # No `set_main_branch` — this is the project the merge checks cannot ask about.
    loop = await make_loop(app, auth_headers, name="Unresolvable loop")
    task = await loop_task(app, auth_headers, loop)
    await bind_run_to(turn, task)
    go_live(turn)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["unfinished"] and detail["unmergeable"] == [] and detail["unaccepted"] == []

    end_the_turn(turn)
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text
    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]


@pytest.mark.asyncio
async def test_a_reviewer_approves_from_inside_its_own_review_turn(
    app, auth_headers, turn, tmp_path, request
):
    """Task 3.8 — the change's largest regression risk, in the populated shape.

    Since migration `0092` a review run is bound to the very task it inspects, so a predicate that
    counted the acting run would refuse every review the product staffs — including the only path
    ever observed carrying a flow's work to a main branch. Driven through the agent surface rather
    than the service, because that is the door a reviewer actually comes through.
    """
    make_repo(tmp_path)
    await set_main_branch("main")
    builder_headers = {"Authorization": "Bearer aw_run_window-secret"}
    task = await plain_task(app, auth_headers, title="Reviewed work")

    # The author's turn: claiming binds its run to the task, completing ends it.
    for status in ("in_progress", "completed"):
        moved = await app.patch(
            f"/api/v1/agent-actions/tasks/{task}",
            json={"status": status},
            headers=builder_headers,
        )
        assert moved.status_code == 200, moved.text
    end_the_turn(turn)

    entered = await app.patch(
        f"{TASKS}/{task}", json={"status": "under_review"}, headers=auth_headers
    )
    assert entered.status_code == 200, entered.text

    # The reviewer's own turn, bound to the task it is reviewing and live at this moment.
    async with async_session_factory() as session:
        session.add(Agent(id="ag-reviewer", project_id="proj-test", name="reviewer"))
        session.add(
            Run(
                id="run-reviewer",
                project_id="proj-test",
                agent="reviewer",
                status="running",
                turn_depth=0,
                task_id=task,
                capability_token_hash=hash_run_token("aw_run_reviewer-secret"),
            )
        )
        await session.commit()
    run_liveness.active_ptys["run-reviewer"] = LiveTurn()
    request.addfinalizer(lambda: run_liveness.active_ptys.pop("run-reviewer", None))

    approved = await app.patch(
        f"/api/v1/agent-actions/tasks/{task}",
        json={"status": "approved"},
        headers={"Authorization": "Bearer aw_run_reviewer-secret"},
    )
    assert approved.status_code == 200, approved.text
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "approved"


# ---------------------------------------------------------------------------
# 4.2 — the evidence route, through the same refusal
#
# Round 2 answered *whether* it shares the window at the source (design D9): it does, by the same
# mechanism through the other door. This proves it, and proves the one refusal covers both — the
# requirement is a statement about when a task's work is knowable, not about which mechanism
# resolves it.
# ---------------------------------------------------------------------------


async def footprint_sha(evidence_id):
    async with async_session_factory() as session:
        row = (
            await session.execute(
                EvidenceFootprint.__table__.select().where(
                    EvidenceFootprint.evidence_id == evidence_id
                )
            )
        ).first()
        return row.commit_sha if row is not None else None


@pytest.mark.asyncio
async def test_the_evidence_route_is_refused_inside_the_turn_too(app, auth_headers, turn, tmp_path):
    """Task 4.2. A task resolved by **accepted evidence** rather than by its own branch tip is
    refused inside the turn on exactly the same terms.

    The window is identical and structural. `read_footprint` observes the checkout's `HEAD` at the
    moment evidence is recorded, and mid-turn that is the commit the turn was cut from — so the
    footprint names a commit holding none of the work *by construction*, asserted below rather than
    assumed. Nothing downstream repairs that in time: `_targets` (`task_integration.py:219`) does
    not filter on `reachable_from_main`, so an already-shipped pre-turn commit is a live merge
    target, and `restamp_run_footprints` — the thing that *does* repair it — runs at turn **end**
    and re-merges nothing (`requirement_evidence.py:845`). Approving in between merges the stale
    commit and records `ALREADY_INTEGRATED`, which is F162 with a different resolver.

    The second half is the same as the branch-tip case and is what makes this a fix rather than a
    block: once the turn ends and its footprints are restamped, the same task approves and merges
    the commit that actually holds the work.
    """
    base = make_repo(tmp_path)
    await set_main_branch("main")
    run_headers = {"Authorization": "Bearer aw_run_window-secret"}
    await make_document(app, auth_headers, run_headers)

    # The agent's branch, cut from main and holding none of the turn's work yet. Evidence is
    # recorded from here, which is where a real agent records it: mid-turn, before any commit.
    git(tmp_path, "checkout", "-q", "-b", AGENT_BRANCH)
    evidence = await accept_evidence(app, auth_headers, run_headers)
    git(tmp_path, "checkout", "-q", "main")

    assert await footprint_sha(evidence) == base, (
        "the window requires the accepted footprint to name the pre-turn commit — "
        "if it names the work, this test is reproducing something else"
    )

    task = await linked_task(app, auth_headers)
    # The binding, not the authorship, is what the predicate reads — on this route as on the other.
    # In the shape the product produces they coincide: the agent working the task claims it, which
    # binds its run, and records its evidence from that same turn. Evidence recorded by *another*
    # task's run against a shared requirement is a merge target here (`_targets` reaches it through
    # `TaskRequirementLink`) and is outside the test; that residual is on the record in the
    # requirement rather than left to be discovered.
    await bind_run_to(turn, task)
    go_live(turn)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied"
    assert detail["unfinished"] == [{"agent": "builder", "run_id": turn}]
    # Nothing is wrong with the evidence: it is accepted, and its commit exists. The live turn is
    # the only claim being made, which is what makes the refusal's "this clears itself" true.
    assert detail["unaccepted"] == [] and detail["unmergeable"] == []

    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "under_review"
    assert await integrations(app, auth_headers, task) == []

    # The turn ends: the work is committed and the run's footprints are re-pointed at it, which is
    # what `_execute_run`'s finalize block does before the registry entry goes.
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n", create=False)
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        moved = await requirement_evidence.restamp_run_footprints(
            session,
            project_id="proj-test",
            run_id=turn,
            root=tmp_path,
            commit_sha=work,
            main_branch="main",
        )
        await session.commit()
    assert moved == 1
    end_the_turn(turn)

    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == work
    assert work in commits_on(tmp_path, "main"), "the commit that holds the work is what merged"
