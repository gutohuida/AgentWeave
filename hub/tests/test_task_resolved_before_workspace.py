"""D2: which task a turn is about is answered before a workspace is provisioned.

`resolve_bound_task` used to run a hundred lines *after* the workspace was chosen, so a request
naming a task the project does not have still provisioned a git worktree, seeded ignore rules and
resolved a review checkout before anything refused it. Moving the call above all of that changes
**four** observable answers, not one, and this file is where each of them is chosen rather than
discovered.

Three of them now answer "that task does not exist" where they used to answer something else
(`work_dir` on a review turn, `work_dir` for a writing agent, an unresolvable review target). One
of them deliberately does **not** move: an unavailable project directory still wins, because the
call is placed *after* `resolve_project_workspace`, not at the top of the function.

**Reachability, stated because it bounds what these tests are evidence of.** The explicit `task_id`
argument to `trigger_agent_directly` is the only route to `resolve_task_for_project`'s refusal here.
`POST /agent/trigger` validates `body.task_id` itself before it ever gets this far
(`agent_trigger.py:941-945`), and the drain path reaches the binding through `queue_entry_ids`,
where a vanished task is deliberately swallowed rather than refused
(`run_task_binding.py:270-276`). So these tests call the function directly, as the sibling
precedence tests in `test_agent_trigger.py` do.
"""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.run_task_binding import TaskBindingError

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree

#: A task id no fixture creates. Named rather than inlined so a reader can see at a glance that
#: every test below is asking the same question of a different code path.
ABSENT_TASK = "task-does-not-exist"


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True, check=False)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


async def _agent(app, auth_headers, bind_runner, name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="claude")


async def _conversation(agent):
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


@pytest.mark.asyncio
async def test_a_task_that_does_not_exist_is_refused_and_provisions_no_worktree(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """3.1 — the observable consequence of the move, against a real repository.

    The refusal itself is not new; *where* it happens is. Before D2 the writing agent's worktree
    was already on disk by the time the task was checked, so a mistyped id left a checkout and a
    branch behind for an agent that never ran. The `worktree_path(...).exists()` assertion is the
    one that fails if the call ever slides back down the function, and it needs the real
    `resolve_agent_workspace` — the suite stubs it to a no-op by default, which would make this
    test pass for the wrong reason.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TaskBindingError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="writer",
                    message="work on it",
                    conversation_id=conversation_id,
                    session=session,
                    task_id=ABSENT_TASK,
                )

    assert excinfo.value.http_status == 404
    assert ABSENT_TASK in excinfo.value.detail
    assert not worktrees.worktree_path(repo, "writer").exists()
    async with async_session_factory() as session:
        assert (await session.execute(select(Run.id))).first() is None


@pytest.mark.asyncio
async def test_an_unavailable_workspace_still_wins_over_the_task_refusal(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """3.2 — the precedence D2 preserves.

    D2 rejected moving the resolution to the *top* of the function precisely so this answer would
    not change: when the project's directory is gone, the operator needs the 409 that names
    `directory_state` and offers repair, not "that task does not exist" — the second is true but
    unactionable while the first is also true.
    """
    directory = tmp_path / "proj"
    directory.mkdir(parents=True)
    await bind_project_workspace(directory)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    shutil.rmtree(directory)

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="writer",
                    message="work on it",
                    conversation_id=conversation_id,
                    session=session,
                    task_id=ABSENT_TASK,
                )

    assert excinfo.value.status_code == 409
    assert excinfo.value.workspace_unavailable is True
    assert excinfo.value.directory_state == "missing"
    assert ABSENT_TASK not in excinfo.value.detail


@pytest.mark.asyncio
async def test_a_missing_task_outranks_work_dir_on_a_review_turn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """3.2b(a) — `agent_trigger.py:492-497` used to answer this, and now does not.

    Both statements are wrong, and the task id is the more specific one: it decides which workspace
    the turn would have had at all, which is the very thing the `work_dir` refusal is about.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, "reviewer")
    conversation_id = await _conversation("reviewer")
    async with async_session_factory() as session:
        session.add(
            Task(id="task-review", project_id="proj-test", title="Reviewed", status="completed")
        )
        await session.commit()

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TaskBindingError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="reviewer",
                    message="review it",
                    conversation_id=conversation_id,
                    session=session,
                    work_dir="subdir",
                    task_id=ABSENT_TASK,
                    review_task_id="task-review",
                )

    assert ABSENT_TASK in excinfo.value.detail
    assert "work_dir" not in excinfo.value.detail


@pytest.mark.asyncio
async def test_a_missing_task_outranks_work_dir_for_a_writing_agent(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """3.2b(b) — `agent_trigger.py:511-516` used to answer this, and now does not.

    The project has to be a real repository for the `work_dir` refusal to have a subject at all
    (`project_is_repo`), so this is the case where the two refusals genuinely compete rather than
    one of them being absent.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TaskBindingError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="writer",
                    message="work on it",
                    conversation_id=conversation_id,
                    session=session,
                    work_dir="subdir",
                    task_id=ABSENT_TASK,
                )

    assert ABSENT_TASK in excinfo.value.detail
    assert "work_dir" not in excinfo.value.detail


@pytest.mark.asyncio
async def test_a_missing_task_outranks_an_unresolvable_review_target(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """3.2b(c) — `ReviewTurnRefused` at `agent_trigger.py:506-509` used to answer this.

    `task-review` exists but has no evidence naming a commit, so `prepare_review_turn` refuses with
    a 409 that reads "no commit to review". After the move that refusal is never reached, because
    the turn also names a task that does not exist — and the review preparation is exactly the step
    that would otherwise provision a checkout for a turn that cannot legally run.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, "reviewer")
    conversation_id = await _conversation("reviewer")
    async with async_session_factory() as session:
        session.add(
            Task(id="task-review", project_id="proj-test", title="Reviewed", status="completed")
        )
        await session.commit()

    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TaskBindingError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="reviewer",
                    message="review it",
                    conversation_id=conversation_id,
                    session=session,
                    task_id=ABSENT_TASK,
                    review_task_id="task-review",
                )

    assert ABSENT_TASK in excinfo.value.detail
    assert "commit" not in excinfo.value.detail


@pytest.mark.asyncio
async def test_a_real_task_still_binds_and_the_turn_still_gets_its_workspace(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The move is a reordering, not a new gate: a task that *does* exist is still bound and still
    gets a workspace.

    Without this the five tests above are all satisfied by a `resolve_bound_task` that refused
    everything, which is the failure mode a precedence suite is most exposed to.

    **Updated in phase 4B, and the id is the reason.** This test used to name `task-real` and assert
    the *agent's* worktree. Once the binding decides the workspace (design D3) a bound turn runs in
    the task's own checkout — but `task-real` is not a shape `validate_task_id` accepts, so it
    would have gone on passing while quietly exercising the unmintable-id fallback instead of the
    ordinary bound path. A valid id and the task workspace is what this test now claims.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    async with async_session_factory() as session:
        session.add(
            Task(id="task-99aabb00", project_id="proj-test", title="Real", status="pending")
        )
        await session.commit()

    captured = {}

    def _spawn(cmd, cwd=None, env=None, **kwargs):
        captured["cwd"] = cwd
        raise RuntimeError("stop here: the workspace decision is what this test is about")

    async with async_session_factory() as session:
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="writer",
                    message="work on it",
                    conversation_id=conversation_id,
                    session=session,
                    task_id="task-99aabb00",
                )

    async with async_session_factory() as session:
        run = (await session.execute(select(Run))).scalars().first()
        assert run is not None
        assert run.task_id == "task-99aabb00"
    assert worktrees.task_worktree_path(repo, "task-99aabb00").is_dir()
