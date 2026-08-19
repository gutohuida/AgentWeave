"""Actor-derived messaging, task-ledger, and question capabilities."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Message, Question, Run, Task


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


async def _loop_with_agent(session, *, suffix, agent, run_count=0, control=None):
    """A loop whose queue-write authorization (design D1/D7/D10,
    `2026-08-18-a-loop-writes-its-own-queue`) turns on `AIJob.agent`, `run_count`, and `control`.
    Mirrors `_declaring_loop` (test_spec_declared_tasks.py) and `_make_job`/`_make_loop`
    (test_scheduler.py) rather than inventing a fourth fixture shape."""
    job = AIJob(
        id=f"job-loop-{suffix}",
        project_id="proj-test",
        name=f"Loop job {suffix}",
        agent=agent,
        message="go",
        cron="0 9 * * *",
        session_mode="new",
        enabled=True,
        run_count=run_count,
    )
    session.add(job)
    await session.flush()
    loop = Loop(
        id=f"loop-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose="authorship gate fixture",
        control=control,
    )
    session.add(loop)
    await session.flush()
    return loop


async def _set_run_count(loop_id: str, run_count: int) -> None:
    async with async_session_factory() as session:
        loop = await session.get(Loop, loop_id)
        job = await session.get(AIJob, loop.job_id)
        job.run_count = run_count
        await session.commit()


@pytest.mark.asyncio
async def test_loop_operator_adds_regardless_of_a_distinct_executors_fire_count(app, auth_headers):
    """Design D7: 'a loop with a distinct creator keeps D1's unconditional creator-privilege
    rule' -- and D8 collapses 'creator' into `AIJob.agent`, leaving no field this data model can
    use to express a creator distinct from both the executor and the operator. The only caller
    that can ever be 'distinct' from a loop's own agent and still succeed is the operator, so
    that is what this exercises: the operator adding to a loop whose agent is someone else,
    before AND after that loop has fired -- neither call is gated by run_count.
    """
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="distinct", agent="executor-a")
        await session.commit()
        loop_id = loop.id

    before_fire = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={"title": "distinct-before-fire", "loop_id": loop_id},
    )
    assert before_fire.status_code == 201, before_fire.text

    await _set_run_count(loop_id, 1)

    after_fire = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={"title": "distinct-after-fire", "loop_id": loop_id},
    )
    assert after_fire.status_code == 201, after_fire.text


@pytest.mark.asyncio
async def test_loop_operator_is_exempt_from_the_self_created_fire_gate(app, auth_headers):
    """The operator bypasses D7's extra gate too -- even on a loop whose own agent would be
    refused for the same call (test_loop_self_created_agent_gated_after_first_fire, below)."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="operator-bypass", agent="self-agent")
        await session.commit()
        loop_id = loop.id

    await _set_run_count(loop_id, 1)

    response = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={"title": "operator-bypasses-self-gate", "loop_id": loop_id},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_loop_non_creator_non_operator_is_refused_and_told_to_send_message(app):
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="bystander", agent="executor-a")
        await session.commit()
        loop_id = loop.id

    bystander_headers, _ = await _active_run("run-loop-bystander", "bystander")
    response = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=bystander_headers,
        json={"title": "not yours to add", "loop_id": loop_id},
    )
    assert response.status_code == 403
    assert "send_message" in response.json()["detail"]

    async with async_session_factory() as session:
        remaining = (
            (await session.execute(select(Task).where(Task.loop_id == loop_id))).scalars().all()
        )
        assert remaining == []


@pytest.mark.asyncio
async def test_loop_self_created_agent_gated_after_first_fire(app):
    """Design D7's boundary: before the loop's first fire, its own agent may still extend its
    queue (indistinguishable from `create_loop`'s own initial queue); after, it needs the
    operator."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="self-fire-gate", agent="self-agent")
        await session.commit()
        loop_id = loop.id

    self_headers, _ = await _active_run("run-loop-self", "self-agent")

    before_fire = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=self_headers,
        json={"title": "self-before-fire", "loop_id": loop_id},
    )
    assert before_fire.status_code == 201, before_fire.text

    await _set_run_count(loop_id, 1)

    after_fire = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=self_headers,
        json={"title": "self-after-fire", "loop_id": loop_id},
    )
    assert after_fire.status_code == 403
    detail = after_fire.json()["detail"]
    assert "operator" in detail.lower()
    # The refusal must name the way FORWARD, not just the wall. Driving 13.4 against a real agent
    # on 2026-08-19 showed it read the old wording, restated it, and stopped: it was told approval
    # was required and given no mechanism to request one, so no question ever reached the operator.
    # Its two sibling refusals in this file already name their route ("use send_message to ask the
    # creator"); this one named none.
    assert "ask_user" in detail, f"the refusal names no route out: {detail!r}"

    async with async_session_factory() as session:
        created = (
            (await session.execute(select(Task).where(Task.loop_id == loop_id))).scalars().all()
        )
        assert [task.title for task in created] == ["self-before-fire"]


@pytest.mark.asyncio
async def test_loop_explicit_operator_control_matches_the_unset_default(app):
    """Design D10 (task A1.4): the generalisation is proven, not asserted — a loop whose
    `control` is explicitly `"operator"` must reach the exact same outcome as one where it was
    never set (`test_loop_self_created_agent_gated_after_first_fire`, above), because NULL means
    the current default rather than "nothing decided yet"."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(
            session, suffix="explicit-operator", agent="self-agent-explicit", control=None
        )
        await session.commit()
        loop_id = loop.id

    self_headers, _ = await _active_run("run-loop-self-explicit", "self-agent-explicit")

    before_fire = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=self_headers,
        json={"title": "explicit-before-fire", "loop_id": loop_id},
    )
    assert before_fire.status_code == 201, before_fire.text

    await _set_run_count(loop_id, 1)

    after_fire = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=self_headers,
        json={"title": "explicit-after-fire", "loop_id": loop_id},
    )
    assert after_fire.status_code == 403
    assert "operator" in after_fire.json()["detail"].lower()


@pytest.mark.asyncio
async def test_loop_delegated_control_lets_the_creator_decide_after_first_fire(app):
    """Design D10: once control is delegated to the creator agent, D7's first-fire boundary no
    longer applies — the creator decides for itself, `run_count` included."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(
            session, suffix="delegated", agent="self-agent-delegated", control="creator"
        )
        await session.commit()
        loop_id = loop.id

    await _set_run_count(loop_id, 1)

    self_headers, _ = await _active_run("run-loop-delegated", "self-agent-delegated")
    response = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=self_headers,
        json={"title": "delegated-after-fire", "loop_id": loop_id},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_loop_control_delegation_and_take_back_via_the_operator_route(app, auth_headers):
    """Design D10 (tasks A1.2/A1.3/A1.5): only the operator may delegate or take back control —
    a run-bearer credential does not even satisfy `get_project`'s own operator-only auth (the
    `aw_run_` prefix fails `_operator_from_credential` before this route's own belt-and-suspenders
    `_require_operator` header check is ever reached) — and each change is recorded with actor and
    time (`EventLog`, `agent=None` meaning the operator, matching `loop_archived`'s own precedent).
    """
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="delegate-route", agent="creator-agent")
        await session.commit()
        loop_id = loop.id

    _, run_token = await _active_run("run-loop-nonop", "creator-agent")
    refused = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop_id}/control",
        headers={"Authorization": f"Bearer {run_token}"},
        json={"control": "creator"},
    )
    assert refused.status_code == 401

    async with async_session_factory() as session:
        unchanged = await session.get(Loop, loop_id)
        assert unchanged.control is None

    delegated = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop_id}/control",
        headers=auth_headers,
        json={"control": "creator"},
    )
    assert delegated.status_code == 200, delegated.text
    assert delegated.json()["control"] == "creator"

    taken_back = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop_id}/control",
        headers=auth_headers,
        json={"control": "operator"},
    )
    assert taken_back.status_code == 200, taken_back.text
    # Taking control back stores NULL, not the literal string "operator" — the same
    # never-a-stored-copy-of-the-default rule `Loop.control`'s own comment states.
    assert taken_back.json()["control"] is None

    from hub.db.models import EventLog

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(EventLog)
                    .where(EventLog.event_type == "loop_control_changed")
                    .order_by(EventLog.timestamp)
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 2
    assert events[0].data == {"id": loop_id, "from": "operator", "to": "creator"}
    assert events[1].data == {"id": loop_id, "from": "creator", "to": "operator"}
    assert all(event.agent is None for event in events)
    assert all(event.timestamp is not None for event in events)


@pytest.mark.asyncio
async def test_loop_control_rejects_an_unknown_value(app, auth_headers):
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="bad-control", agent="creator-agent")
        await session.commit()
        loop_id = loop.id

    response = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop_id}/control",
        headers=auth_headers,
        json={"control": "nobody"},
    )
    assert response.status_code == 422


async def _end_loop(loop_id: str, *, ending_state: str, stop_reason: str) -> None:
    from datetime import datetime, timezone

    async with async_session_factory() as session:
        loop = await session.get(Loop, loop_id)
        loop.ending_state = ending_state
        loop.stop_reason = stop_reason
        loop.stopped_at = datetime(2026, 8, 19, 3, 0, tzinfo=timezone.utc)
        await session.commit()


@pytest.mark.asyncio
async def test_loop_stopped_refuses_every_caller_including_the_operator(app, auth_headers):
    """Design D12 (task A3.1): once `ending_state` is set, the queue is closed to everyone —
    including the operator, who is exempt from every OTHER gate in
    `_authorize_loop_task_creation` but not this one, because this is not "who may extend the
    queue" but "does the queue still exist to extend"."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="stopped", agent="creator-agent")
        await session.commit()
        loop_id = loop.id

    await _end_loop(loop_id, ending_state="stopped", stop_reason="loop queue is empty")

    creator_headers, _ = await _active_run("run-loop-stopped-creator", "creator-agent")
    from_creator = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=creator_headers,
        json={"title": "late task from creator", "loop_id": loop_id},
    )
    assert from_creator.status_code == 403, from_creator.text
    detail = from_creator.json()["detail"]
    assert detail["code"] == "loop_stopped"
    assert detail["ending_state"] == "stopped"
    assert detail["stop_reason"] == "loop queue is empty"
    assert detail["stopped_at"].startswith("2026-08-19T03:00:00")
    assert detail["offered_task"]["title"] == "late task from creator"

    from_operator = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={"title": "late task from operator", "loop_id": loop_id},
    )
    assert from_operator.status_code == 403, from_operator.text
    assert from_operator.json()["detail"]["code"] == "loop_stopped"

    async with async_session_factory() as session:
        created = (
            (await session.execute(select(Task).where(Task.loop_id == loop_id))).scalars().all()
        )
        assert created == []


@pytest.mark.asyncio
async def test_loop_merely_disabled_is_not_stopped(app, auth_headers):
    """Design D6 rejected a third 'paused' state — an operator disabling the job via the
    existing `toggle_job` path leaves `ending_state`/`stop_reason`/`stopped_at` all `None`, so it
    must not trip A3.1's refusal. Only the loop's own termination path does that."""
    async with async_session_factory() as session:
        loop = await _loop_with_agent(session, suffix="paused", agent="creator-agent")
        job = await session.get(AIJob, loop.job_id)
        job.enabled = False
        await session.commit()
        loop_id = loop.id

    response = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={"title": "task while merely paused", "loop_id": loop_id},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_agent_can_read_only_its_own_question_answer(app, auth_headers):
    asker_headers, _ = await _active_run("run-question-owner", "asker")
    other_headers, _ = await _active_run("run-question-other", "other")

    rejected = await app.post(
        "/api/v1/agent-actions/questions",
        headers=asker_headers,
        json={
            "question": "Which path?",
            "from_agent": "impostor",
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
        },
    )
    assert rejected.status_code == 422

    asked = await app.post(
        "/api/v1/agent-actions/questions",
        headers=asker_headers,
        json={
            "question": "Which path?",
            "blocking": True,
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
        },
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
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "permission_denied")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].agent == "walled"
    # "warn", not "warning": the activity view's severity chips, borders and filter list know
    # only the former, so a denial stored as "warning" rendered unmarked and was hidden by the
    # very filter meant to surface it.
    assert rows[0].severity == "warn"
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
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "permission_denied")
                )
            )
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


# ---------------------------------------------------------------------------
# A delegated task is runtime state, not message decoration (run-task-binding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_delegated_task_reaches_the_queue_entry(app, auth_headers):
    """On the `Message` alone the task went nowhere, which is why the board depended on agents
    remembering. It has to survive the queue to bind the run that eventually does the work."""
    from hub.db.models import InboundQueueEntry

    await _sync_agent(app, auth_headers, "receiver")
    headers, _ = await _active_run("run-delegate-1", "delegator")

    async with async_session_factory() as session:
        session.add(
            Task(id="task-delegated", project_id="proj-test", title="Work", status="pending")
        )
        await session.commit()

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "receiver", "content": "please do this", "task_id": "task-delegated"},
    )
    assert response.status_code == 201, response.text

    async with async_session_factory() as session:
        entry = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "receiver")
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.task_id == "task-delegated"


@pytest.mark.asyncio
async def test_a_delegation_naming_an_unknown_task_is_refused(app, auth_headers):
    """Refused at the moment of the call, in the tool result the agent is already reading, rather
    than through a run that quietly starts unbound and is never checked at its boundary."""
    await _sync_agent(app, auth_headers, "receiver-2")
    headers, _ = await _active_run("run-delegate-2", "delegator-2")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "receiver-2", "content": "do it", "task_id": "task-nonexistent"},
    )
    assert response.status_code == 404, response.text
    assert "task-nonexistent" in response.json()["detail"]


@pytest.mark.asyncio
async def test_request_agent_grants_no_binding(app):
    """`request_agent(name, template, task)` takes `task` as free text — a description of work for
    an agent that may not exist yet, not a reference to a row. It gains no binding power here, and
    an agent must not be able to acquire one through it (design D3)."""
    from hub.api.v1.agent_actions import BoundAgentRequest

    assert "task_id" not in BoundAgentRequest.model_fields
    assert BoundAgentRequest.model_fields["task"].annotation is str


# ---------------------------------------------------------------------------
# How a dropped task is answered is the operator's, not the agent's
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_cannot_change_its_own_task_s_divergence_policy(app):
    """The agent plane shares `TaskUpdate` with the operator route, so without an explicit guard an
    agent could set its own task to `surface` and disarm the check that exists to catch it dropping
    the work — the same reason no agent-facing operation binds a run."""
    headers, _ = await _active_run("run-policy-1", "worker")

    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-policy-guard",
                project_id="proj-test",
                title="Work",
                status="in_progress",
                divergence_policy="retry",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-policy-guard",
        headers=headers,
        json={"divergence_policy": "surface"},
    )
    assert response.status_code == 403, response.text
    assert "operator" in response.json()["detail"]

    async with async_session_factory() as session:
        task = await session.get(Task, "task-policy-guard")
        assert task.divergence_policy == "retry"


@pytest.mark.asyncio
async def test_an_agent_cannot_change_its_own_task_s_escalation_agent(app):
    headers, _ = await _active_run("run-policy-2", "worker2")

    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-escalation-guard",
                project_id="proj-test",
                title="Work",
                status="in_progress",
                divergence_policy="escalate",
                escalation_agent="reviewer",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-escalation-guard",
        headers=headers,
        json={"escalation_agent": None},
    )
    assert response.status_code == 403, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-escalation-guard")
        assert task.escalation_agent == "reviewer"


@pytest.mark.asyncio
async def test_an_agent_may_still_move_its_task(app):
    """The guard is about the policy, not about the ledger. An agent recording real progress is the
    whole point of the binding."""
    headers, _ = await _active_run("run-policy-3", "worker3")

    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-policy-move",
                project_id="proj-test",
                title="Work",
                status="in_progress",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-policy-move",
        headers=headers,
        json={"status": "completed"},
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# A block is observed, never asserted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_cannot_declare_its_own_task_blocked(app):
    """The one status an agent under a completion gate would most like to reach.

    An agent able to assert it could claim to be waiting on a person it never asked. It is withheld
    from the MCP `update_task` signature so the request cannot be expressed there at all, and
    refused here because this HTTP route is reachable without going through the tool.
    """
    headers, _ = await _active_run("run-block-1", "worker-block")

    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-agent-block",
                project_id="proj-test",
                title="Work",
                status="in_progress",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-agent-block",
        headers=headers,
        json={"status": "blocked", "blocked_reason": "I say I am stuck"},
    )
    assert response.status_code == 403, response.text
    assert "ask_user" in response.json()["detail"]

    async with async_session_factory() as session:
        task = await session.get(Task, "task-agent-block")
        assert task.status == "in_progress"
        assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_the_operator_may_park_a_task_by_hand(app, auth_headers):
    """Not every blocker is a question an agent asked."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-operator-block",
                project_id="proj-test",
                title="Work",
                status="in_progress",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-operator-block",
        headers=auth_headers,
        json={"status": "blocked", "blocked_reason": "Waiting on the staging API key"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"
    assert response.json()["blocked_reason"] == "Waiting on the staging API key"


@pytest.mark.asyncio
async def test_a_hand_set_block_must_say_what_it_is_waiting_for(app, auth_headers):
    """An unexplained block leaves the operator working out what they are holding up — the position
    they were in when the card said `in_progress` and nothing was happening (R5)."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-block-no-reason",
                project_id="proj-test",
                title="Work",
                status="in_progress",
            )
        )
        await session.commit()

    for body in ({"status": "blocked"}, {"status": "blocked", "blocked_reason": "   "}):
        response = await app.patch(
            "/api/v1/projects/proj-test/tasks/task-block-no-reason",
            headers=auth_headers,
            json=body,
        )
        assert response.status_code == 422, response.text

    async with async_session_factory() as session:
        assert (await session.get(Task, "task-block-no-reason")).status == "in_progress"


@pytest.mark.asyncio
async def test_leaving_the_waiting_status_drops_what_it_was_waiting_for(app, auth_headers):
    """Whichever exit it was. A reason outliving its block describes something that already
    arrived."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-block-release",
                project_id="proj-test",
                title="Work",
                status="blocked",
                blocked_reason="Waiting on the staging API key",
            )
        )
        await session.commit()

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-block-release",
        headers=auth_headers,
        json={"status": "in_progress"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["blocked_reason"] is None
