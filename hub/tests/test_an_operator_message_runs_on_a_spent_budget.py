"""F814: with the token budget spent, the operator's own message still runs.

`BudgetExhaustionNotice` and the trigger's `budget_note` tell the operator that their messages
still run. The scheduler decided "autonomous or operator" from the agent's oldest eligible entry
alone, so an operator message in a second conversation sat behind an agent's budget-held message in
the first, and the whole agent stayed held. The turn that runs is now the operator's, and the
autonomous head stays held.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project, Run, TurnUsage
from hub.inbound_queue import new_entry
from hub.turn_scheduler import schedule_agent

from ._background_runs import await_background_runs as _drain

PROJECT = "proj-test"
AGENT = "budgeted"


def _completed_session(pid):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"bud-1"}\n',
        "",
    ]
    session.wait.return_value = 0
    return session


async def _register(app, auth_headers, bind_runner):
    await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(AGENT, cli="claude")


async def _spend_the_budget():
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.token_budget = 100
        db.add(Run(id="run-spent-814", project_id=PROJECT, agent="history", status="completed"))
        db.add(
            TurnUsage(
                id="usage-spent-814",
                project_id=PROJECT,
                run_id="run-spent-814",
                agent="history",
                status="measured",
                input_tokens=500,
                output_tokens=0,
                total_tokens=500,
            )
        )
        await db.commit()


async def _queue(conversation_id, origin_type, content, origin_agent=None):
    async with async_session_factory() as db:
        if await db.get(Conversation, conversation_id) is None:
            db.add(
                Conversation(
                    id=conversation_id,
                    project_id=PROJECT,
                    agent=AGENT,
                    lifecycle="open",
                    origin="operator",
                    title=conversation_id,
                    lineage_id=conversation_id,
                )
            )
        entry = new_entry(
            project_id=PROJECT,
            agent=AGENT,
            origin_type=origin_type,
            origin_agent=origin_agent,
            content=content,
            hop_depth=1 if origin_type == "agent" else 0,
            conversation_id=conversation_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


async def _entry(entry_id):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)))
            .scalars()
            .one()
        )


@pytest.mark.asyncio
async def test_an_operator_message_behind_a_held_agent_message_runs(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    autonomous = await _queue("conv-814-peer", "agent", "from beta", origin_agent="beta")
    operator = await _queue("conv-814-own", "operator", "Reply with PRED.")
    await _spend_the_budget()

    spawn = MagicMock(return_value=_completed_session(8140))
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        await schedule_agent(PROJECT, AGENT)
        await _drain()

    spawn.assert_called_once()
    prompt = " ".join(str(part) for part in spawn.call_args.args[0])
    assert "Reply with PRED." in prompt
    assert "from beta" not in prompt
    assert (await _entry(operator)).state != "queued"
    held = await _entry(autonomous)
    assert held.state == "queued"
    assert held.waiting_reason == "token budget exhausted"
    async with async_session_factory() as db:
        run = (
            (await db.execute(select(Run).where(Run.agent == AGENT, Run.project_id == PROJECT)))
            .scalars()
            .all()
        )
    assert [r.conversation_id for r in run] == ["conv-814-own"]


@pytest.mark.asyncio
async def test_a_spent_budget_still_holds_autonomous_input_alone(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    autonomous = await _queue("conv-814-peer", "agent", "from beta", origin_agent="beta")
    await _spend_the_budget()

    spawn = MagicMock(return_value=_completed_session(8141))
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        await schedule_agent(PROJECT, AGENT)
        await _drain()

    spawn.assert_not_called()
    assert (await _entry(autonomous)).waiting_reason == "token budget exhausted"


@pytest.mark.asyncio
async def test_the_status_route_does_not_call_a_runnable_operator_message_held(
    app, auth_headers, bind_runner
):
    await _register(app, auth_headers, bind_runner)
    await _queue("conv-814-peer", "agent", "from beta", origin_agent="beta")
    await _queue("conv-814-own", "operator", "Reply with PRED.")
    await _spend_the_budget()

    status = await app.get(f"/api/v1/projects/{PROJECT}/queue/{AGENT}/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert status.json()["waiting_reason"] != "token budget exhausted"
