"""Start work on a task resumes the agent's conversation for that task (decision fix-D13).

The work-PC drive's 355k-token re-discovery (wpc-obs-2) came from this path: "Start work"
(`useStartWorkOnTask`) sends `task_id` and no `conversation_id`, and the trigger route opened a new
conversation every time, so the agent re-read the repository from scratch. A conversation bound to
the task is the agent's conversation for it (`Conversation.task_id`, released when the task is
decided or by the operator), so Start work now resumes the newest open one; with none, it opens a
new one as before. The composer never sends `task_id`, so a new conversation it starts stays clean.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Task

from ._background_runs import await_background_runs
from .test_project_scoped_runtime import _bind_runner

pytestmark = pytest.mark.asyncio
TRIGGER = "/api/v1/projects/proj-test/agent/trigger"


async def _setup(app, auth_headers, *, conversations):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"builder": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_runner(app, auth_headers, "proj-test", "builder")
    async with async_session_factory() as db:
        db.add(Task(id="task-d13", project_id="proj-test", title="Work", status="in_progress"))
        for conv_id, agent, task_id, lifecycle in conversations:
            db.add(
                Conversation(
                    id=conv_id,
                    project_id="proj-test",
                    agent=agent,
                    lifecycle=lifecycle,
                    origin="operator",
                    task_id=task_id,
                )
            )
        await db.commit()


async def _start_work(app, auth_headers, task_id="task-d13", **extra):
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn"),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        resp = await app.post(
            TRIGGER,
            json={"agent": "builder", "message": "Start work on task-d13.", "task_id": task_id}
            | extra,
            headers=auth_headers,
        )
        await await_background_runs()
    assert resp.status_code == 200, resp.text
    return resp.json()["conversation_id"]


async def test_start_work_resumes_the_agents_conversation_bound_to_the_task(app, auth_headers):
    await _setup(
        app,
        auth_headers,
        conversations=[
            ("conv-d13-old", "builder", "task-d13", "open"),
            ("conv-d13-other", "builder", None, "open"),
        ],
    )
    assert await _start_work(app, auth_headers) == "conv-d13-old"
    async with async_session_factory() as db:
        convs = (
            (await db.execute(select(Conversation).where(Conversation.agent == "builder")))
            .scalars()
            .all()
        )
        entries = (await db.execute(select(InboundQueueEntry))).scalars().all()
    assert len(convs) == 2, "no new conversation was opened"
    assert [e.conversation_id for e in entries] == ["conv-d13-old"]


async def test_with_no_bound_conversation_start_work_opens_a_new_one(app, auth_headers):
    await _setup(
        app,
        auth_headers,
        conversations=[
            ("conv-d13-unbound", "builder", None, "open"),
            ("conv-d13-archived", "builder", "task-d13", "archived"),
            ("conv-d13-peer", "reviewer", "task-d13", "open"),
        ],
    )
    opened = await _start_work(app, auth_headers)
    assert opened not in ("conv-d13-unbound", "conv-d13-archived", "conv-d13-peer")


async def test_a_named_conversation_still_wins(app, auth_headers):
    await _setup(
        app,
        auth_headers,
        conversations=[
            ("conv-d13-bound", "builder", "task-d13", "open"),
            ("conv-d13-chosen", "builder", None, "open"),
        ],
    )
    assert (
        await _start_work(app, auth_headers, conversation_id="conv-d13-chosen") == "conv-d13-chosen"
    )


async def test_a_trigger_without_a_task_opens_a_new_conversation(app, auth_headers):
    """The composer's new conversation sends no task: it begins clean, as before."""
    await _setup(
        app, auth_headers, conversations=[("conv-d13-bound", "builder", "task-d13", "open")]
    )
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn"),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        resp = await app.post(
            TRIGGER, json={"agent": "builder", "message": "hi"}, headers=auth_headers
        )
        await await_background_runs()
    assert resp.json()["conversation_id"] != "conv-d13-bound"
