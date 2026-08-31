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

from hub import task_integration, worktrees
from hub.agent_auth import hash_run_token
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, Task

from .test_loop_lands_its_work import loop_task, make_loop
from .test_task_integration import (
    approve,
    commits_on,
    git,
    integrations,
    make_repo,
    set_main_branch,
)


class LiveTurn:
    """Stands in for the `PtySession` a live turn holds in `_active_ptys`.

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

    request.addfinalizer(lambda: agent_trigger._active_ptys.pop("run-window", None))
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
    agent_trigger._active_ptys[run_id] = session
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
    assert turn in agent_trigger._active_ptys

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
    assert work not in commits_on(tmp_path, "main"), (
        "the task reads approved and its work is not in the product — this is F162"
    )
    assert not task_integration.is_retryable(recorded[0]["outcome"], recorded[0]["reason"]), (
        "and no retry can alter it: ALREADY_INTEGRATED describes a fact about the base commit"
    )
