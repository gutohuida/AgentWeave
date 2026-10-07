"""`a-read-only-agent-holds-no-task-work` (F425) -- spec/changes, trial Hub document
`spdoc-e7299e2e30ce`.

`worktrees.takes_task_workspace` gives a task checkout only to a writing agent, so a `read_only`
agent's turn bound to a task's work ran in the project directory -- the operator's own checkout --
and, not being isolated, was never snapshotted. `read_only` is a workspace declaration, not a
sandbox: the agent can still write. So a read-only agent does not hold a task's work at all. Its
work turn is refused at the dispatch (the one place an assignment becomes writing), the doors the
operator and agents use refuse it early, and a flow does not pick it for ordinary work. It still
reviews.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from hub import worktrees
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task, TaskTransition
from hub.scheduler import decide_firing
from hub.task_transition_service import RunNotBoundError, apply_transition
from hub.task_transitions import run_actor

from .test_a_loop_staffs_the_agent_it_names import _fresh_loop, _loop_job, _task
from .test_agent_trigger import _await_background_run, _fake_pty, _init_repo
from .test_review_turn import (
    _REAL_ENSURE_REVIEW_CHECKOUT,
    _author_commit,
    _reviewable_task,
    _trigger_review,
)

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"


async def _roster(app, auth_headers, bind_runner, **agents):
    """`name=read_only` pairs, synced and bound to a runner."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    name: {"runner": "claude", "read_only": read_only}
                    for name, read_only in agents.items()
                }
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    for name in agents:
        await bind_runner(name, cli="claude")


async def _plain_task(task_id, *, status="assigned", assignee="reader"):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=f"Task {task_id}",
                status=status,
                assignee=assignee,
            )
        )
        await session.commit()


async def _conversation(agent):
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


def _status(repo: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(repo), capture_output=True, text=True
    ).stdout


# ---------------------------------------------------------------------------
# turn-refused
# ---------------------------------------------------------------------------


async def test_a_read_only_agents_work_turn_is_refused_before_any_workspace(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """refused-turn. A task grandfathered onto `reader` before this change: the operator triggers
    `reader` on it. Refused with the agent, the task and the remedy; no run, nothing written."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, reader=True)
    await _plain_task("task-f425-turn")
    conversation_id = await _conversation("reader")
    before = _status(repo)

    async with async_session_factory() as session:
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="reader",
                    message="work on it",
                    conversation_id=conversation_id,
                    session=session,
                    task_id="task-f425-turn",
                )

    assert excinfo.value.status_code == 409
    assert excinfo.value.request_level
    for word in ("reader", "task-f425-turn", "read-only", "writing agent"):
        assert word in excinfo.value.detail, word
    async with async_session_factory() as session:
        assert (await session.execute(select(Run.id))).first() is None
    assert _status(repo) == before


async def test_the_trigger_route_refuses_it_too(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The operator's own door: `POST /agent/trigger` with the task answers the refusal."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, reader=True)
    await _plain_task("task-f425-route")

    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "reader", "message": "work on it", "task_id": "task-f425-route"},
            headers=auth_headers,
        )

    assert response.status_code == 409, response.text
    assert "read-only" in response.text


async def test_a_read_only_agent_still_reviews(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """review-ok. The intended use: `reader` reviews a completed task in its review checkout."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, reader=True)
    await _reviewable_task(commit=sha)

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await _trigger_review(app, auth_headers, agent="reader")
            assert response.status_code == 200, response.text
            await _await_background_run()

    assert Path(fake_spawn.call_args.kwargs["cwd"]) == worktrees.review_path(repo, "reader")


async def test_a_writing_agents_work_turn_is_unchanged(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Control: the same trigger for a writing agent is not refused by this rule."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, writer=False)
    await _plain_task("task-f425-writer", assignee="writer")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "writer", "message": "work on it", "task_id": "task-f425-writer"},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()


# ---------------------------------------------------------------------------
# assignment-refused
# ---------------------------------------------------------------------------


async def test_creating_a_task_for_a_read_only_agent_is_refused(app, auth_headers, bind_runner):
    """create-refused, at creation."""
    await _roster(app, auth_headers, bind_runner, reader=True)

    created = await app.post(
        TASKS, json={"title": "Write it", "assignee": "reader"}, headers=auth_headers
    )

    assert created.status_code == 422, created.text
    assert "reader" in created.text and "read-only" in created.text
    async with async_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Task)) == 0


async def test_assigning_a_task_to_a_read_only_agent_is_refused(app, auth_headers, bind_runner):
    """create-refused, by PATCH; the task keeps its assignee."""
    await _roster(app, auth_headers, bind_runner, reader=True, writer=False)
    await _plain_task("task-f425-patch", assignee="writer")

    patched = await app.patch(
        f"{TASKS}/task-f425-patch", json={"assignee": "reader"}, headers=auth_headers
    )

    assert patched.status_code == 422, patched.text
    assert "read-only" in patched.text
    async with async_session_factory() as session:
        assert (await session.get(Task, "task-f425-patch")).assignee == "writer"


async def test_handing_a_review_to_a_read_only_agent_is_allowed(app, auth_headers, bind_runner):
    """The PATCH that hands a completed task to a reviewer is a review hold, not work."""
    await _roster(app, auth_headers, bind_runner, reader=True, writer=False)
    await _plain_task("task-f425-review", status="completed", assignee=None)

    patched = await app.patch(
        f"{TASKS}/task-f425-review",
        json={"status": "under_review", "assignee": "reader"},
        headers=auth_headers,
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["assignee"] == "reader"


async def test_a_read_only_agents_run_cannot_claim_a_task(app, auth_headers, bind_runner):
    """claim-refused: an unassigned task, a run of `reader` holding nothing."""
    await _roster(app, auth_headers, bind_runner, reader=True)
    await _plain_task("task-f425-claim", status="pending", assignee=None)
    async with async_session_factory() as session:
        session.add(
            Run(id="run-f425-claim", project_id="proj-test", agent="reader", status="running")
        )
        await session.commit()

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f425-claim")
        with pytest.raises(RunNotBoundError) as excinfo:
            await apply_transition(
                session, task, "in_progress", run_actor("run-f425-claim", "reader")
            )

    assert excinfo.value.http_status == 403
    assert "read-only" in str(excinfo.value)
    async with async_session_factory() as session:
        task = await session.get(Task, "task-f425-claim")
        assert (task.status, task.assignee) == ("pending", None)
        assert (await session.get(Run, "run-f425-claim")).task_id is None
        assert await session.scalar(select(func.count()).select_from(TaskTransition)) == 0


# ---------------------------------------------------------------------------
# flow-excludes
# ---------------------------------------------------------------------------


async def test_a_flow_does_not_give_ordinary_work_to_a_read_only_agent(
    app, auth_headers, bind_runner
):
    """flow. `reader` sorts first among the free agents; the pending task still goes to `writer`."""
    await _roster(app, auth_headers, bind_runner, gamma=False, reader=True, writer=False)
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="f425", agent="gamma", declares_document=True)
        task = await _task(db, loop, suffix="f425")
        db.add(Run(id="run-f425-gamma", project_id="proj-test", agent="gamma", status="running"))
        await db.commit()

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent) for s in decision.selections] == [(task.id, "writer")]


async def test_a_flow_whose_own_agent_is_read_only_does_not_start_it_on_work(
    app, auth_headers, bind_runner
):
    """The job's own agent is the default for the first task; a read-only one is passed over."""
    await _roster(app, auth_headers, bind_runner, reader=True, writer=False)
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="f425own", agent="reader", declares_document=True)
        task = await _task(db, loop, suffix="f425own")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent) for s in decision.selections] == [(task.id, "writer")]
