"""F162: approving inside the turn strands the work, and the record says the opposite.

**The window.** An agent calls `update_task(completed)` *during* its turn. The commit that holds
its edits does not exist yet — it is made when the turn ends. Between those two moments the task's
own branch still points at the commit it was cut from, so `task_integration.task_branch_tip`
answers with a commit that contains none of the work. That commit is already on the main branch by
construction, so `integrate` records `ALREADY_INTEGRATED` — *"there was nothing to merge"* — which
`is_retryable` classifies as a fact a repeat cannot alter. The task reads `approved`, the work sits
unmerged on its branch, and no surface offers a remedy.

**This file is written before the fix and asserts today's wrong behaviour**, the way
`test_loop_lands_its_work.py` was (its own docstring records the commit where its measurement
lives). Group 3 of `approval-waits-for-the-turn-to-end` flips it.

**It reproduces the window, not merely a state** (design D8). A test that only left the branch
empty would pass against code that resolves the base commit for an entirely different reason. What
makes this the window is that a run bound to the task is *live at the moment of the transition* —
a `Run` row recorded `running` **and** a session handle in this Hub process's registry, which is
what the fix's predicate reads. Both halves are asserted before the approval, so a fixture that
stopped producing either fails here rather than passing for the wrong reason.
"""

import pytest

from hub import run_liveness, task_integration, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, Task

from .test_loop_lands_its_work import loop_task, make_loop
from .test_task_integration import (
    TASKS,
    approve,
    commits_on,
    git,
    integrations,
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
# 1.1 / 1.2 — the reproduction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_inside_the_turn_strands_the_work(app, auth_headers, turn, tmp_path):
    """Tasks 1.1 and 1.2: the window, and the consequence — not only the state.

    Four assertions, and the last two are the ones that matter. That the skip is recorded against
    the **base** commit is the mechanism; that the turn's real commit never reaches `main` and the
    record is unretryable is the damage.
    """
    base = make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Windowed loop")
    task = await loop_task(app, auth_headers, loop)
    await bind_run_to(turn, task)

    tip = branch_the_task_without_committing(tmp_path, task)
    assert tip == base, "the window requires the task's branch to hold none of the turn's work"

    # Both halves of "live", read back rather than assumed: the recorded status and the handle this
    # Hub process holds. The fix's predicate reads exactly these two.
    async with async_session_factory() as session:
        run = await session.get(Run, turn)
        assert run.task_id == task and run.status == "running"
    go_live(turn)
    assert turn in run_liveness.active_ptys

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "approved"

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["commit_sha"] == base
    assert recorded[0]["reason"] == task_integration.ALREADY_INTEGRATED.format(
        commit=base[:12], target="main"
    )

    # The turn ends and commits its work — after the approval, which is the whole point.
    git(tmp_path, "checkout", "-q", worktrees.task_branch_name(task))
    (tmp_path / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    git(tmp_path, "add", "feature.py")
    git(tmp_path, "commit", "-q", "-m", "the turn's work")
    work = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    git(tmp_path, "checkout", "-q", "main")

    assert work != base
    assert work not in commits_on(
        tmp_path, "main"
    ), "the task reads approved and its work is not in the product — this is F162"
    assert not task_integration.is_retryable(
        recorded[0]["outcome"], recorded[0]["reason"]
    ), "and no retry can alter it: ALREADY_INTEGRATED describes a fact about the base commit"


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
