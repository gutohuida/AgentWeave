"""An undelivered message says how its last attempt ended.

F291: a run that fails before its process spawns writes no output row. Its input is retried up to
`DELIVERY_ATTEMPT_LIMIT` and then abandoned, keeping `delivered_in_run_id` as the operator's
breadcrumb from the dropped message to the run that ate it. Before this change the run's own
outcome never reached the screen — `RunFacts` carried no `error`, so nothing the conversation, the
recent-chat route or the agent timeline serves could say why.

Tasks 1.1-1.4 (`an-undelivered-message-says-how-its-last-attempt-ended`).
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, EventLog, InboundQueueEntry, Run

PROJECT = "proj-test"
BASE = f"/api/v1/projects/{PROJECT}"


async def _project_id(app, auth_headers) -> str:
    resp = await app.get(f"{BASE}/status", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["project_id"]


async def _seed_abandoned_entry(
    project_id: str,
    *,
    entry_id: str,
    agent: str,
    run_id: str,
    conversation_id: str,
    run_status: str = "failed",
    run_error: str | None = "%1 is not a valid Win32 application.",
) -> None:
    """A message the Hub gave up on, whose last attempt was `run_id`."""
    started = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with async_session_factory() as session:
        if await get_conversation_by_id(session, conversation_id) is None:
            session.add(
                Conversation(
                    id=conversation_id, project_id=project_id, agent=agent, lifecycle="open"
                )
            )
        session.add(
            Run(
                id=run_id,
                project_id=project_id,
                agent=agent,
                conversation_id=conversation_id,
                status=run_status,
                started_at=started,
                ended_at=started + timedelta(seconds=1),
                error=run_error,
            )
        )
        session.add(
            InboundQueueEntry(
                id=entry_id,
                project_id=project_id,
                agent=agent,
                origin_type="operator",
                content="the message nobody ever received",
                arrived_at=started,
                hop_depth=0,
                state="withdrawn",
                withdrawn_at=started + timedelta(seconds=2),
                delivery_attempts=3,
                abandoned_reason="delivery failed 3 times; the Hub stopped retrying",
                delivered_in_run_id=run_id,
                conversation_id=conversation_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_the_chat_route_carries_the_last_attempts_error(app, auth_headers):
    """Task 1.1: `runs[R].error` on the conversation's chat route equals the run's own error."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent-u1"
    await _seed_abandoned_entry(
        project_id,
        entry_id="entry-u1",
        agent=agent,
        run_id="run-u1",
        conversation_id="sess-u1",
    )

    resp = await app.get(f"{BASE}/agent/{agent}/chat/sess-u1", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["runs"]["run-u1"]["error"] == "%1 is not a valid Win32 application."


@pytest.mark.asyncio
async def test_the_recent_chat_route_carries_the_last_attempts_error(app, auth_headers):
    """Task 1.2, first half: the sessionless recent-chat route serves the same fact."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent-u2"
    await _seed_abandoned_entry(
        project_id,
        entry_id="entry-u2",
        agent=agent,
        run_id="run-u2",
        conversation_id="sess-u2",
    )

    resp = await app.get(f"{BASE}/agent/{agent}/chat?limit=50", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["runs"]["run-u2"]["error"] == "%1 is not a valid Win32 application."


@pytest.mark.asyncio
async def test_the_timeline_route_carries_the_last_attempts_error(app, auth_headers):
    """Task 1.2, second half: `GET /agents/{name}/timeline` with a `run_failed` event naming R."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent-u3"
    run_id = "run-u3"
    started = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=project_id,
                agent=agent,
                status="failed",
                started_at=started,
                ended_at=started + timedelta(seconds=1),
                error="%1 is not a valid Win32 application.",
            )
        )
        session.add(
            EventLog(
                id="evt-u3",
                project_id=project_id,
                event_type="run_failed",
                agent=agent,
                timestamp=started + timedelta(seconds=1),
                data={"run_id": run_id},
            )
        )
        await session.commit()

    resp = await app.get(f"{BASE}/agents/{agent}/timeline", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["runs"][run_id]["error"] == "%1 is not a valid Win32 application."


@pytest.mark.asyncio
async def test_a_completed_runs_facts_carry_no_error(app, auth_headers):
    """Task 1.3: `error` is present and `null`, not merely absent, for a run that recorded none."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent-u4"
    run_id = "run-u4"
    started = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=project_id,
                agent=agent,
                status="completed",
                started_at=started,
                ended_at=started + timedelta(seconds=1),
                exit_code=0,
            )
        )
        session.add(
            EventLog(
                id="evt-u4",
                project_id=project_id,
                event_type="run_completed",
                agent=agent,
                timestamp=started + timedelta(seconds=1),
                data={"run_id": run_id},
            )
        )
        await session.commit()

    resp = await app.get(f"{BASE}/agents/{agent}/timeline", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    facts = body["runs"][run_id]
    assert "error" in facts
    assert facts["error"] is None


@pytest.mark.asyncio
async def test_an_over_long_error_is_served_fitted_not_a_500(app, auth_headers):
    """Task 1.4: a 2,000-character `Run.error` is fitted to `RunFacts`' bound and the route
    answers 200, rather than turning a response-validation failure into a 500."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent-u5"
    long_error = "W" * 2000
    await _seed_abandoned_entry(
        project_id,
        entry_id="entry-u5",
        agent=agent,
        run_id="run-u5",
        conversation_id="sess-u5",
        run_error=long_error,
    )

    resp = await app.get(f"{BASE}/agent/{agent}/chat/sess-u5", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    error = body["runs"]["run-u5"]["error"]
    assert error is not None
    assert len(error) <= 500
    assert error == long_error[:500]
