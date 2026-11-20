"""The start gate (`one-profile-runs-many-turns-at-once-on-different-tasks`, task `start-gate`:
FR-2, FR-3, FR-5, FR-6, FR-7, FR-8, FR-9, FR-12).

Whether a start may run now: the conversation has no running turn (always), the task's checkout
has no running writing turn (always), the agent's shared worktree has no other run of the agent in
it (always), and -- only while the project's "profiles run in parallel" switch is off -- the agent
has no running run at all. While the switch is on, a queued entry that cannot start does not stop
the agent's later entries.

Driven through `POST /agent/trigger`, which queues and schedules exactly as every other door does,
with a spawn that hangs until the test releases it, so "running at the same time" is a fact the
database and the spawned processes both show.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Project, Run, Task
from hub.turn_scheduler import CONVERSATION_TURN_RUNNING, schedule_agent

from .test_agent_trigger import _await_background_run
from .test_turn_workspace import _agent, _init_repo, _real_worktrees

TASK_A = "task-0a0a0a0a0a0a"
TASK_B = "task-0b0b0b0b0b0b"
TASK_C = "task-0c0c0c0c0c0c"

#: How long a wait for a spawn or a run's end lasts: a deadline, not a count of polls. A start in
#: a task's checkout runs a real `git worktree add` before it spawns, several seconds each on a
#: loaded Windows machine, and the switch-off test chains a run's end, its re-drain and such a
#: start behind one wait. A count of 1000 10 ms polls (about 10 s) failed it every time (OPMR-8)
#: while the third turn did start, a second or so later.
_WAIT_SECONDS = 60.0


async def _set_project(**values) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        for key, value in values.items():
            setattr(project, key, value)
        await session.commit()


async def _tasks(*task_ids: str, assignee: Optional[str] = "writer") -> None:
    async with async_session_factory() as session:
        for task_id in task_ids:
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=task_id,
                    status="assigned" if assignee else "pending",
                    assignee=assignee,
                )
            )
        await session.commit()


class _Spawns:
    """A spawn that hangs each process until its own release, recording each one's `cwd`."""

    def __init__(self) -> None:
        self.cwds: List[Path] = []
        self.releases: List[threading.Event] = []
        #: For each spawn, which earlier spawns had been released when it happened.
        self.released_before: List[List[bool]] = []
        #: Set by `release_all`: a process spawned after it does not hang (a queued turn that
        #: starts as the others end).
        self.closed = False

    def __call__(self, *args, **kwargs):
        release = threading.Event()
        if self.closed:
            release.set()
        self.released_before.append([event.is_set() for event in self.releases])
        self.releases.append(release)
        self.cwds.append(Path(kwargs["cwd"]))
        hanging = MagicMock()
        hanging.pid = 9000 + len(self.releases)
        hanging.read.side_effect = lambda size=4096: (release.wait(), "")[1]
        hanging.wait.return_value = 0
        return hanging

    def release_all(self) -> None:
        self.closed = True
        for event in self.releases:
            event.set()

    async def wait_for(self, count: int) -> None:
        deadline = time.monotonic() + _WAIT_SECONDS
        while time.monotonic() < deadline:
            if len(self.cwds) >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"expected {count} spawns, saw {len(self.cwds)}")


async def _post(app, auth_headers, agent: str = "writer", **body):
    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": agent, **body},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _running(**where) -> List[Run]:
    async with async_session_factory() as session:
        query = select(Run).where(Run.project_id == "proj-test", Run.status == "running")
        for column, value in where.items():
            query = query.where(getattr(Run, column) == value)
        return list((await session.execute(query)).scalars().all())


async def _queued(agent: str = "writer") -> List[InboundQueueEntry]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(InboundQueueEntry)
                    .where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.agent == agent,
                        InboundQueueEntry.state == "queued",
                    )
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def _await_ended(count: int) -> None:
    """Until at most *count* runs are still running."""
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        if len(await _running()) <= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"runs still running: {len(await _running())}")


async def _queue(agent: str, content: str, task_id: Optional[str] = None) -> str:
    """Input queued for *agent* in a conversation of its own, as a job or a peer queues it, without
    scheduling it: the route refuses starting a task assigned to another agent before it queues."""
    from hub.conversations import new_conversation
    from hub.inbound_queue import new_entry

    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="job")
        session.add(conversation)
        await session.flush()
        session.add(
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="job",
                content=content,
                hop_depth=0,
                conversation_id=conversation.id,
                task_id=task_id,
            )
        )
        await session.commit()
        return conversation.id


def _patched(spawns: _Spawns):
    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawns),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    )


async def _agents(app, auth_headers, bind_runner, *names: str) -> None:
    """Every agent in one sync: a sync names the whole roster, so a second would drop the first."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    for name in names:
        await bind_runner(name, cli="claude")


async def _repo_project(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, mp, *agents: str
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(mp)
    await _agents(app, auth_headers, bind_runner, "writer", *agents)
    await _set_project(main_branch="main")
    return repo


# ---------------------------------------------------------------------------
# FR-3: two tasks of one profile at once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_two_tasks_of_one_profile_run_at_the_same_time(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-two-tasks-at-once."""
    repo = await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _tasks(TASK_A, TASK_B)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first = await _post(app, auth_headers, message="one", task_id=TASK_A)
            second = await _post(app, auth_headers, message="two", task_id=TASK_B)
            assert first["status"] == "running" and second["status"] == "running", second
            await spawns.wait_for(2)
            running = await _running(agent="writer")
            assert sorted(run.task_id for run in running) == [TASK_A, TASK_B]
        finally:
            spawns.release_all()
            await _await_background_run()
    assert spawns.cwds == [
        worktrees.task_worktree_path(repo, TASK_A),
        worktrees.task_worktree_path(repo, TASK_B),
    ]


# ---------------------------------------------------------------------------
# FR-6: one turn per conversation, whatever the switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_a_second_message_to_a_running_chat_waits_for_its_turn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-conversation-serial: the second message waits, and starts only once the first turn has
    ended; the two runs of that conversation never run together."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first = await _post(app, auth_headers, message="one")
            assert first["status"] == "running"
            conversation_id = first["conversation_id"]
            await spawns.wait_for(1)
            second = await _post(app, auth_headers, message="two", conversation_id=conversation_id)
            assert second["status"] == "queued", second
            assert second["waiting_reason"] == CONVERSATION_TURN_RUNNING
            assert len(await _running(conversation_id=conversation_id)) == 1
            # A pass of the agent's queue while the turn runs still leaves it waiting.
            await schedule_agent("proj-test", "writer")
            assert len(spawns.cwds) == 1
            spawns.releases[0].set()
            await spawns.wait_for(2)
        finally:
            spawns.release_all()
            await _await_background_run()
    # The second spawn happened only after the first was released.
    assert spawns.released_before[1] == [True]
    assert spawns.cwds[0] == spawns.cwds[1]


@pytest.mark.asyncio
async def test_with_the_switch_off_a_second_message_to_a_running_chat_waits_as_before(
    app, auth_headers, bind_runner
):
    """FR-2 and FR-6: off, the same wait, in today's words."""
    await _agent(app, auth_headers, bind_runner, "writer")
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first = await _post(app, auth_headers, message="one")
            second = await _post(
                app, auth_headers, message="two", conversation_id=first["conversation_id"]
            )
            assert second["status"] == "queued"
            assert "already running" in second["waiting_reason"]
        finally:
            spawns.release_all()
            await _await_background_run()


# ---------------------------------------------------------------------------
# FR-9 and FR-8: two chats at once, in two trees
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_two_chats_of_one_profile_run_together_in_their_own_trees(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-two-chats, and ac-separate-trees for two concurrent chats: each started at once, each in
    its own thread worktree, and a file one writes is not in the other's tree."""
    repo = await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            chat_a = await _post(app, auth_headers, message="chat a")
            chat_b = await _post(app, auth_headers, message="chat b")
            assert chat_a["status"] == "running" and chat_b["status"] == "running", chat_b
            await spawns.wait_for(2)
            running = await _running(agent="writer")
            assert {run.conversation_id for run in running} == {
                chat_a["conversation_id"],
                chat_b["conversation_id"],
            }
            cwd_a, cwd_b = spawns.cwds
            assert cwd_a == worktrees.thread_worktree_path(
                repo, "writer", chat_a["conversation_id"]
            )
            assert cwd_b == worktrees.thread_worktree_path(
                repo, "writer", chat_b["conversation_id"]
            )
            (cwd_a / "a.txt").write_text("a\n")
            (cwd_b / "b.txt").write_text("b\n")
            assert not (cwd_b / "a.txt").exists() and not (cwd_a / "b.txt").exists()
            assert {run.workspace_dir for run in running} == {str(cwd_a), str(cwd_b)}
        finally:
            spawns.release_all()
            await _await_background_run()


# ---------------------------------------------------------------------------
# FR-7: one writing turn per task checkout, whatever the switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("second_agent", ["writer", "other"])
async def test_with_the_switch_on_a_second_writing_start_on_a_task_waits_for_the_first(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, second_agent
):
    """ac-task-writer: by the same profile or another, the second start waits until the first
    ends, then runs in the same task checkout."""
    repo = await _repo_project(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        *([second_agent] if second_agent != "writer" else []),
    )
    await _tasks(TASK_A)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first = await _post(app, auth_headers, message="one", task_id=TASK_A)
            assert first["status"] == "running"
            await spawns.wait_for(1)
            if second_agent == "writer":
                # The same profile's start lands in the task's conversation, which waits on its
                # own turn first (step 1).
                second = await _post(app, auth_headers, message="two", task_id=TASK_A)
                assert second["status"] == "queued", second
                assert second["waiting_reason"] == CONVERSATION_TURN_RUNNING
            else:
                # Another profile's start, in a conversation of its own, waits on the checkout
                # (step 2).
                await _queue(second_agent, "two", task_id=TASK_A)
                await schedule_agent("proj-test", second_agent)
                (waiting,) = await _queued(second_agent)
                assert TASK_A in (waiting.waiting_reason or "")
            assert len(await _running(task_id=TASK_A)) == 1
            spawns.releases[0].set()
            await spawns.wait_for(2)
        finally:
            spawns.release_all()
            await _await_background_run()
    assert spawns.released_before[1] == [True]
    assert spawns.cwds == [worktrees.task_worktree_path(repo, TASK_A)] * 2


# ---------------------------------------------------------------------------
# FR-5: a blocked entry does not hold the profile's queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_an_entry_behind_a_held_checkout_does_not_block_the_next(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-queue-skip-blocked: `other` holds task A's checkout; `writer`'s first queued entry is about
    task A and its second is a chat. The chat starts; the task entry keeps waiting, then runs once
    `other`'s turn ends."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "other"
    )
    await _tasks(TASK_A, assignee=None)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            held = await _post(app, auth_headers, agent="other", message="hold", task_id=TASK_A)
            assert held["status"] == "running"
            await spawns.wait_for(1)
            # The task entry heads writer's queue; a chat's input is behind it.
            blocked = await _queue("writer", "task a", task_id=TASK_A)
            chat = await _queue("writer", "a chat")
            await schedule_agent("proj-test", "writer")
            await spawns.wait_for(2)
            assert [run.conversation_id for run in await _running(agent="writer")] == [chat]
            queued = await _queued()
            assert [entry.conversation_id for entry in queued] == [blocked]
            assert TASK_A in (queued[0].waiting_reason or "")
            # Released, and `other`'s run-end re-drain starts the task entry.
            spawns.releases[0].set()
            await spawns.wait_for(3)
            assert await _queued() == []
        finally:
            spawns.release_all()
            await _await_background_run()


@pytest.mark.asyncio
async def test_with_the_switch_off_an_entry_behind_a_held_checkout_still_heads_the_queue(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """FR-2: off, the queue keeps its order -- the chat behind the held task entry waits too."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "other"
    )
    await _tasks(TASK_A, assignee=None)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            await _post(app, auth_headers, agent="other", message="hold", task_id=TASK_A)
            await spawns.wait_for(1)
            await _queue("writer", "task a", task_id=TASK_A)
            await _queue("writer", "a chat")
            await schedule_agent("proj-test", "writer")
            assert len(spawns.cwds) == 1
            assert len(await _queued()) == 2
        finally:
            spawns.release_all()
            await _await_background_run()


# ---------------------------------------------------------------------------
# FR-12: turning the switch off drains
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turning_the_switch_off_lets_both_runs_finish_before_the_third_starts(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-switch-off: two runs of one profile running, a third ready task; the switch goes off.
    Both finish, and the third starts only after both have ended."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _tasks(TASK_A, TASK_B, TASK_C)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            for task_id in (TASK_A, TASK_B):
                started = await _post(app, auth_headers, message=task_id, task_id=task_id)
                assert started["status"] == "running"
            await spawns.wait_for(2)
            await _set_project(profiles_run_in_parallel=False)
            third = await _post(app, auth_headers, message=TASK_C, task_id=TASK_C)
            assert third["status"] == "queued"
            assert "already running" in third["waiting_reason"]
            spawns.releases[0].set()
            await _await_ended(1)
            # One run still running: the third still waits, and a pass does not start it.
            await schedule_agent("proj-test", "writer")
            assert len(spawns.cwds) == 2
            assert [run.task_id for run in await _running(agent="writer")] == [TASK_B]
            spawns.releases[1].set()
            await spawns.wait_for(3)
        finally:
            spawns.release_all()
            await _await_background_run()
    assert spawns.released_before[2] == [True, True]


# ---------------------------------------------------------------------------
# FR-8, step 3: the shared worktree takes one run at a time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_a_task_run_does_not_hold_the_shared_worktree(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """A run in a task's checkout is not in the agent's shared worktree, so a job-style
    conversation (not a thread) starts beside it there at once."""
    from hub.conversations import new_conversation

    repo = await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _tasks(TASK_A)
    await _set_project(profiles_run_in_parallel=True)
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="writer", origin="job")
        session.add(conversation)
        await session.commit()
        job_conversation = conversation.id
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            await _post(app, auth_headers, message="task", task_id=TASK_A)
            firing = await _post(
                app, auth_headers, message="scheduled", conversation_id=job_conversation
            )
            assert firing["status"] == "running", firing
            await spawns.wait_for(2)
        finally:
            spawns.release_all()
            await _await_background_run()
    assert spawns.cwds == [
        worktrees.task_worktree_path(repo, TASK_A),
        worktrees.worktree_path(repo, "writer"),
    ]


def test_the_shared_worktree_is_predicted_as_the_resolver_chooses_it(tmp_path):
    from hub.api.v1.agent_trigger import untasked_workspace

    repo = tmp_path
    writing: Dict[str, object] = {}
    assert untasked_workspace(
        repo, "writer", writing, thread=None, project_is_repo=True
    ) == worktrees.worktree_path(repo, "writer")
    thread: Optional[str] = "conv-aaaaaaaaaaaa"
    assert untasked_workspace(
        repo, "writer", writing, thread=thread, project_is_repo=True
    ) == worktrees.thread_worktree_path(repo, "writer", "conv-aaaaaaaaaaaa")
    assert untasked_workspace(repo, "writer", writing, thread=None, project_is_repo=False) is None
    assert (
        untasked_workspace(repo, "reader", {"read_only": True}, thread=None, project_is_repo=True)
        is None
    )
