"""Token-budget enforcement at the durable queue-to-run boundary."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Project, Run, TurnUsage
from hub.inbound_queue import new_entry
from hub.turn_scheduler import schedule_agent


async def _configure_agent(app, auth_headers, name: str) -> None:
    response = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200


async def _set_budget_and_usage(*, limit: int, used: int) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project is not None
        project.token_budget = limit
        historical = Run(
            id="run-budget-history",
            project_id=project.id,
            agent="history",
            status="completed",
        )
        session.add(historical)
        session.add(
            TurnUsage(
                id="usage-budget-history",
                run_id=historical.id,
                project_id=project.id,
                agent="history",
                status="measured",
                input_tokens=used,
                output_tokens=0,
                total_tokens=used,
            )
        )
        await session.commit()


async def _queue(name: str, origin_type: str) -> str:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=name)
        session.add(conversation)
        entry = new_entry(
            project_id="proj-test",
            agent=name,
            origin_type=origin_type,
            origin_agent="source" if origin_type == "agent" else None,
            content="queued work",
            hop_depth=1 if origin_type == "agent" else 0,
            conversation_id=conversation.id,
        )
        session.add(entry)
        await session.commit()
        return entry.id


def _completed_claude_spawn(session_id: str):
    session = MagicMock()
    session.pid = 7001
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,'
        f'"session_id":"{session_id}"}}\n',
        "",
    ]
    session.wait.return_value = 0
    return MagicMock(return_value=session)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin_type", ["agent", "job"])
async def test_exhausted_budget_keeps_autonomous_entries_queued(
    app, auth_headers, origin_type
) -> None:
    name = f"paused-{origin_type}"
    await _configure_agent(app, auth_headers, name)
    await _set_budget_and_usage(limit=100, used=100)
    entry_id = await _queue(name, origin_type)

    result = await schedule_agent("proj-test", name)
    assert result.response is None
    assert result.waiting_reason == "token budget exhausted"

    async with async_session_factory() as session:
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)
            )
        ).scalar_one_or_none()
        runs = (
            await session.execute(select(Run).where(Run.agent == name))
        ).scalars().all()
        assert entry is not None and entry.state == "queued"
        assert runs == []

    status = await app.get(f"/api/v1/queue/{name}/status", headers=auth_headers)
    assert status.json()["waiting_reason"] == "token budget exhausted"


@pytest.mark.asyncio
async def test_operator_turn_starts_while_budget_is_exhausted(app, auth_headers) -> None:
    name = "operator-over-budget"
    await _configure_agent(app, auth_headers, name)
    await _set_budget_and_usage(limit=100, used=100)
    await _queue(name, "operator")

    with patch(
        "hub.api.v1.agent_trigger.PtySession.spawn", _completed_claude_spawn("operator-session")
    ), patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        scheduled = await schedule_agent("proj-test", name)
        assert scheduled.response is not None
        await asyncio_gather_background_runs()

    async with async_session_factory() as session:
        run = (
            await session.execute(select(Run).where(Run.agent == name))
        ).scalar_one()
        assert run.initiator == "operator"
        assert run.status == "completed"


@pytest.mark.asyncio
async def test_autonomous_turn_below_budget_persists_initiator(app, auth_headers) -> None:
    name = "autonomous-under-budget"
    await _configure_agent(app, auth_headers, name)
    await _set_budget_and_usage(limit=101, used=100)
    await _queue(name, "agent")

    with patch(
        "hub.api.v1.agent_trigger.PtySession.spawn", _completed_claude_spawn("autonomous-session")
    ), patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        scheduled = await schedule_agent("proj-test", name)
        assert scheduled.response is not None
        await asyncio_gather_background_runs()

    async with async_session_factory() as session:
        run = (
            await session.execute(select(Run).where(Run.agent == name))
        ).scalar_one()
        assert run.initiator == "autonomous"


@pytest.mark.asyncio
async def test_increasing_budget_reschedules_retained_autonomous_work(app, auth_headers) -> None:
    name = "resume-after-budget"
    await _configure_agent(app, auth_headers, name)
    await _set_budget_and_usage(limit=100, used=100)
    entry_id = await _queue(name, "agent")
    assert (await schedule_agent("proj-test", name)).waiting_reason == "token budget exhausted"

    with patch(
        "hub.api.v1.agent_trigger.PtySession.spawn", _completed_claude_spawn("resumed-session")
    ), patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.patch(
            "/api/v1/accounting/budget",
            json={"token_budget": 200},
            headers=auth_headers,
        )
        assert response.status_code == 200
        await asyncio_gather_background_runs()

    async with async_session_factory() as session:
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)
            )
        ).scalar_one_or_none()
        run = (
            await session.execute(select(Run).where(Run.agent == name))
        ).scalar_one()
        assert entry is not None and entry.state == "delivered"
        assert run.initiator == "autonomous"


async def asyncio_gather_background_runs() -> None:
    for task in list(agent_trigger._background_runs):
        await task
