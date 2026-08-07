"""Actor-derived messaging, task-ledger, and question capabilities."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Message, Question, Run, Task


async def _active_run(run_id: str, agent: str) -> tuple[dict[str, str], str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}, token


async def _sync_agent(app, auth_headers, agent_name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent_name: {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


@pytest.mark.asyncio
async def test_agent_message_derives_sender_and_run_and_rejects_identity_fields(app, auth_headers):
    await _sync_agent(app, auth_headers, "peer")
    headers, _ = await _active_run("run-msg-author", "author")

    rejected = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "peer", "content": "hello", "sender": "impostor"},
    )
    assert rejected.status_code == 422

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers={**headers, "X-AgentWeave-Agent": "impostor", "X-AgentWeave-Run": "fake"},
        json={"recipient": "peer", "content": "hello"},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    async with async_session_factory() as session:
        message = await session.get(Message, message_id)
        assert message.sender == "author"
        assert message.project_id == "proj-test"
        assert message.created_by_run_id == "run-msg-author"


@pytest.mark.asyncio
async def test_message_to_unknown_recipient_is_rejected_and_recorded_on_senders_timeline(app):
    """Task 5.3/5.5: a send_message to a name no agent is registered under must be
    rejected (not silently queued to nowhere, which was the previous behavior) and the
    rejection must be visible on the sending agent's own timeline, not only as error text
    the agent itself received."""
    from hub.db.models import EventLog

    headers, _ = await _active_run("run-msg-ghost", "sender-of-ghost-message")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "no-such-agent", "content": "hello"},
    )

    assert response.status_code == 404
    assert "no-such-agent" in response.json()["detail"]

    async with async_session_factory() as session:
        # No message/queue entry was actually created for the unknown recipient.
        orphaned = (
            (await session.execute(select(Message).where(Message.recipient == "no-such-agent")))
            .scalars()
            .all()
        )
        assert orphaned == []

        events = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "agent_action_rejected")
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].agent == "sender-of-ghost-message"
        assert events[0].severity == "warn"
        assert events[0].data["reason"] == "unknown_recipient"
        assert events[0].data["recipient"] == "no-such-agent"


@pytest.mark.asyncio
async def test_agent_task_crud_retains_create_and_latest_update_runs(app):
    creator_headers, _ = await _active_run("run-task-create", "creator")
    updater_headers, _ = await _active_run("run-task-update", "updater")

    rejected = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=creator_headers,
        json={"title": "No impersonation", "assigner": "impostor"},
    )
    assert rejected.status_code == 422

    created = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=creator_headers,
        json={"title": "Shared work", "assignee": "worker", "priority": "high"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["assigner"] == "creator"

    listed = await app.get("/api/v1/agent-actions/tasks", headers=updater_headers)
    assert listed.status_code == 200
    assert task_id in {item["id"] for item in listed.json()}
    fetched = await app.get(f"/api/v1/agent-actions/tasks/{task_id}", headers=updater_headers)
    assert fetched.status_code == 200

    updated = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}",
        headers={**updater_headers, "X-AgentWeave-Agent": "impostor"},
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        assert task.created_by_run_id == "run-task-create"
        assert task.updated_by_run_id == "run-task-update"
        assert task.assigner == "creator"


@pytest.mark.asyncio
async def test_agent_can_read_only_its_own_question_answer(app, auth_headers):
    asker_headers, _ = await _active_run("run-question-owner", "asker")
    other_headers, _ = await _active_run("run-question-other", "other")

    rejected = await app.post(
        "/api/v1/agent-actions/questions",
        headers=asker_headers,
        json={"question": "Which path?", "from_agent": "impostor"},
    )
    assert rejected.status_code == 422

    asked = await app.post(
        "/api/v1/agent-actions/questions",
        headers=asker_headers,
        json={"question": "Which path?", "blocking": True},
    )
    assert asked.status_code == 201
    question_id = asked.json()["id"]

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{question_id}",
        headers=auth_headers,
        json={"answer": "Take the safe path."},
    )
    assert answered.status_code == 200

    own = await app.get(f"/api/v1/agent-actions/questions/{question_id}", headers=asker_headers)
    assert own.status_code == 200
    assert own.json()["answer"] == "Take the safe path."
    not_own = await app.get(f"/api/v1/agent-actions/questions/{question_id}", headers=other_headers)
    assert not_own.status_code == 404

    async with async_session_factory() as session:
        question = await session.get(Question, question_id)
        assert question.from_agent == "asker"
        assert question.created_by_run_id == "run-question-owner"


@pytest.mark.asyncio
async def test_run_credential_cannot_read_operator_coordination_or_configuration(app):
    headers, _ = await _active_run("run-denied-surface", "bounded")

    for path in (
        "/api/v1/projects/proj-test/status",
        "/api/v1/projects/proj-test/messages",
        "/api/v1/projects/proj-test/queue/settings",
        "/api/v1/projects/proj-test/agents",
        "/api/v1/projects/proj-test/accounting",
    ):
        response = await app.get(path, headers=headers)
        assert response.status_code == 401, path

    absent = await app.get("/api/v1/agent-actions/inbound-queue", headers=headers)
    assert absent.status_code == 404


@pytest.mark.asyncio
async def test_agent_task_not_found_is_project_scoped(app):
    headers, _ = await _active_run("run-task-missing", "reader")
    response = await app.get("/api/v1/agent-actions/tasks/task-missing", headers=headers)
    assert response.status_code == 404

    async with async_session_factory() as session:
        assert (await session.execute(select(Task))).scalars().all() == []


@pytest.mark.asyncio
async def test_a_refused_action_is_recorded_where_the_operator_can_see_it(app):
    """A denial the operator never learns about is the gap this reporting closes: the agent hits
    a wall, works around it, and the one person who could widen it never knew."""
    from hub.db.models import EventLog

    headers, _ = await _active_run("run-denied", "walled")
    resp = await app.post(
        "/api/v1/agent-actions/permission-decisions",
        headers=headers,
        json={
            "tool_name": "Write",
            "tool_use_id": "toolu_denied",
            "allowed": False,
            "reason": "'/etc/passwd' is outside your workspace",
        },
    )
    assert resp.status_code == 202, resp.text

    async with async_session_factory() as session:
        rows = (
            (await session.execute(select(EventLog).where(EventLog.event_type == "permission_denied")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].agent == "walled"
    assert rows[0].severity == "warning"
    assert rows[0].data["tool_name"] == "Write"
    assert "outside your workspace" in rows[0].data["reason"]


@pytest.mark.asyncio
async def test_an_allowed_action_is_not_recorded(app):
    """One row per allowed tool call would bury the refusals under the unremarkable case."""
    from hub.db.models import EventLog

    headers, _ = await _active_run("run-allowed", "working")
    resp = await app.post(
        "/api/v1/agent-actions/permission-decisions",
        headers=headers,
        json={"tool_name": "Write", "tool_use_id": "t", "allowed": True, "reason": "inside"},
    )
    assert resp.status_code == 202

    async with async_session_factory() as session:
        rows = (
            (await session.execute(select(EventLog).where(EventLog.event_type == "permission_denied")))
            .scalars()
            .all()
        )
    assert rows == []


@pytest.mark.asyncio
async def test_permission_decisions_require_a_bound_run(app):
    """The endpoint is agent-authenticated like every other agent action."""
    resp = await app.post(
        "/api/v1/agent-actions/permission-decisions",
        json={"tool_name": "Write", "allowed": False, "reason": "x"},
    )
    assert resp.status_code in (401, 403)
