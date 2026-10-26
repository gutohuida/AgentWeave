"""A turn start's git runs off the event loop, on threads streaming runs cannot exhaust.

`turn-starts-approvals-and-evidence-never-freeze-the-hub`: FR-1 (turn-start-no-stall), FR-6
(blocking-work-not-starved) and FR-8 (same-outcomes). Measured on the operator's Hub before this
change: a turn start ran about ten git calls on the loop, 1.02 s on average and up to 20.8 s, while
every other request waited.

Each test starts a real task-bound turn against a real repository with real provisioning, and
`slow_git` adds 250 ms to every git process: one call left on the loop is a 250 ms stall.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hub import blocking, worktrees
from hub.api.v1 import agent_trigger
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task

from ._background_runs import await_background_runs
from ._loop_lag import STALL_LIMIT, LagProbe, slow_git

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree
TASK = "task-0f0f0f0f0f0f"
READERS = tuple(f"reader{i}" for i in range(8))
#: A first turn, unmeasured: a turn start imports a dozen modules on first use, which is a cost of
#: the suite's cold process rather than of any turn a running Hub starts.
WARM = "task-0e0e0e0e0e0e"


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(path), capture_output=True, text=True, check=True
    ).stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
async def task_turn(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch):
    """A writing agent, a task assigned to it with no checkout yet, and the spawn stubbed: the
    turn start runs every pre-spawn step for real and stops where the process would start."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    agents = {"writer": {"runner": "claude"}}
    # Eight more, read-only so their turns take no checkout: the streaming runs of FR-6.
    agents.update({name: {"runner": "claude", "read_only": True} for name in READERS})
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": agents}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    for name in agents:
        await bind_runner(name, cli="claude")
    spawned = []
    real_execute_run = agent_trigger._execute_run

    async def _spawn(**kwargs):  # noqa: ANN003, ANN202
        if kwargs["agent"] in READERS:
            return await real_execute_run(**kwargs)
        spawned.append(kwargs["work_dir"])
        async with async_session_factory() as session:
            run = await session.get(Run, kwargs["run_id"])
            run.status = "completed"
            await session.commit()

    monkeypatch.setattr(agent_trigger, "_execute_run", _spawn)
    async with async_session_factory() as session:
        for task_id in (WARM, TASK):
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title="t",
                    status="assigned",
                    assignee="writer",
                    workspace_scheme="task",
                )
            )
        await session.commit()

    async def _start(task_id=TASK, agent="writer"):
        async with async_session_factory() as session:
            conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
            session.add(conversation)
            await session.commit()
            with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
                response = await agent_trigger.trigger_agent_directly(
                    project_id="proj-test",
                    agent=agent,
                    message="work on it",
                    conversation_id=conversation.id,
                    session=session,
                    task_id=task_id,
                )
            await session.commit()
        await asyncio.sleep(0)  # let the stubbed executor task record its spawn
        return response

    await _start(WARM)
    spawned.clear()
    return repo, spawned, _start


@pytest.mark.asyncio
async def test_a_turn_start_that_creates_its_checkout_never_stalls_the_loop(task_turn):
    repo, spawned, start = task_turn
    with slow_git(threading.current_thread()) as git:
        async with LagProbe() as probe:
            await start()
    assert git.calls, "the turn start ran no git at all, so this measured nothing"
    assert not git.on_loop, [call.argv[:3] for call in git.on_loop]
    assert probe.worst < STALL_LIMIT, f"the loop stalled {probe.worst * 1000:.0f} ms"
    # FR-8: the same checkout, on the same branch, as when this ran on the loop.
    checkout = worktrees.task_worktree_path(repo, TASK)
    assert spawned == [str(checkout)]
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == worktrees.task_branch_name(TASK)


@pytest.mark.asyncio
async def test_a_turn_starts_git_is_not_queued_behind_streaming_runs(task_turn, monkeypatch):
    """FR-6: eight live runs stream at once, each blocked reading its process the way a Claude run
    is for its whole turn, on a default executor sized as a 4-CPU VDI's (`min(32, cpu + 4)` = 8).
    The ninth turn's git still begins at once, and the turn starts."""
    _repo, spawned, start = task_turn
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=8))
    release = threading.Event()
    reading = threading.Semaphore(0)

    def _blocked_process(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        process = MagicMock()
        process.pid = 4321
        state = {"read": False}

        def _read(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
            if not state["read"]:
                state["read"] = True
                reading.release()
                release.wait(30)
            return ""

        process.read.side_effect = _read
        process.wait.return_value = 0
        return process

    monkeypatch.setattr(agent_trigger.PtySession, "spawn", _blocked_process)
    monkeypatch.setattr(agent_trigger.PipeSession, "spawn", _blocked_process)
    try:
        for name in READERS:
            await start(task_id=None, agent=name)
        for _ in READERS:
            assert await asyncio.wait_for(asyncio.to_thread(reading.acquire, True, 10), 15)
        with slow_git(threading.current_thread()) as git:
            asked = time.perf_counter()
            await asyncio.wait_for(start(), timeout=20)
        off_loop = [call for call in git.calls if not call.on_loop]
        assert off_loop and not git.on_loop, [call.argv[:3] for call in git.on_loop]
        assert off_loop[0].started - asked < 0.100
        assert spawned
    finally:
        release.set()
        await await_background_runs()


@pytest.mark.asyncio
async def test_serialized_git_never_overlaps_even_when_its_caller_is_cancelled():
    """D5: worktree creation, release and merges ran one at a time while they ran on the loop.
    Off it, they still do -- including when the coroutine waiting for one is cancelled while its
    git is still running, which must not let the next one start."""
    running = []
    overlaps = []
    entered = threading.Event()

    def _work(tag: str) -> str:
        running.append(tag)
        if len(running) > 1:
            overlaps.append(list(running))
        entered.set()
        time.sleep(0.2)
        running.remove(tag)
        return tag

    first = asyncio.ensure_future(blocking.run_serialized(_work, "first"))
    await asyncio.to_thread(entered.wait, 5)
    first.cancel()
    second = await blocking.run_serialized(_work, "second")
    assert second == "second"
    assert overlaps == []
