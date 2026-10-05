"""F490: a run's registered secret is scrubbed from what the agent writes through its Hub tools.

`run_secrets.scrub` covered only what a run's output recorder stores. Everything an agent sends
through its AgentWeave tools (messages, questions, tasks, checkpoint notes, permission cards, spec
documents, evidence) arrives at `/api/v1/agent-actions` under the run's own credential and was
stored verbatim, so a Copilot provider run that read its key from its environment and passed it to
`send_message` put the key in the Hub's database and on the operator's screen.

These tests go through the real routes, as the run, and then read every text column of every table:
the key must be nowhere, in whatever form the agent spelled it in its JSON.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import JSON, String, Text, select

from hub import run_secrets
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Base, Message, Run

SECRET = "sk-ant-api03-f490ProbeKeyValue0123456789"


async def _active_run(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-credential"
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
    return {"Authorization": f"Bearer {token}"}


async def _sync_agents(app, auth_headers, *names):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {} for name in names}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _rows_holding(value: str) -> list[str]:
    """Every `table.column` of every row whose text holds *value*."""
    found = []
    async with async_session_factory() as session:
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, (String, Text, JSON)):
                    continue
                rows = (await session.execute(select(column))).scalars().all()
                for stored in rows:
                    text = stored if isinstance(stored, str) else json.dumps(stored)
                    if stored is not None and value in text:
                        found.append(f"{table.name}.{column.name}")
    return found


@pytest.fixture
def registered_run():
    run_id = "run-f490"
    run_secrets.register(run_id, [SECRET])
    yield run_id
    run_secrets.forget(run_id)


@pytest.mark.asyncio
async def test_an_agent_cannot_store_its_runs_secret_through_its_tools(
    app, auth_headers, registered_run
):
    await _sync_agents(app, auth_headers, "peer", "cp5")
    headers = await _active_run(registered_run, "cp5")

    message = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "peer", "subject": f"key {SECRET}", "content": f"the key is {SECRET}"},
    )
    assert message.status_code == 201, message.text
    assert SECRET not in message.text

    # The same value spelled with JSON escapes: a byte-level match would miss it.
    escaped = "".join(f"\\u{ord(ch):04x}" for ch in SECRET)
    raw = ('{"recipient": "peer", "content": "escaped ' + escaped + '"}').encode()
    message2 = await app.post(
        "/api/v1/agent-actions/messages",
        headers={**headers, "Content-Type": "application/json"},
        content=raw,
    )
    assert message2.status_code == 201, message2.text

    task = await app.post(
        "/api/v1/agent-actions/tasks",
        headers=headers,
        json={"title": f"rotate {SECRET}", "description": f"old key {SECRET}"},
    )
    assert task.status_code == 201, task.text

    question = await app.post(
        "/api/v1/agent-actions/questions",
        headers=headers,
        json={
            "question": f"Is {SECRET} the right key?",
            "header": "Key",
            "multi_select": False,
            "options": [
                {"label": "yes", "description": f"use {SECRET}"},
                {"label": "no", "description": "stop"},
            ],
        },
    )
    assert question.status_code == 201, question.text

    card = await app.post(
        "/api/v1/agent-actions/permission-requests",
        headers=headers,
        json={
            "tool_name": "Bash",
            "tool_input": {"command": f"curl -H 'x-api-key: {SECRET}' https://api.anthropic.com"},
            "tool_use_id": "tu-f490",
        },
    )
    assert card.status_code in (200, 201), card.text

    assert await _rows_holding(SECRET) == []

    async with async_session_factory() as session:
        stored = (
            (await session.execute(select(Message.content).where(Message.sender == "cp5")))
            .scalars()
            .all()
        )
    assert sorted(stored) == sorted(
        [f"the key is {run_secrets.REDACTED}", f"escaped {run_secrets.REDACTED}"]
    )


@pytest.mark.asyncio
async def test_a_run_with_nothing_registered_writes_what_it_sent(app, auth_headers):
    """The scrub is the run's own registry, not a pattern: another run's text is untouched."""
    await _sync_agents(app, auth_headers, "peer", "plain")
    headers = await _active_run("run-f490-plain", "plain")
    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "peer", "content": f"not a registered value: {SECRET}"},
    )
    assert response.status_code == 201, response.text
    async with async_session_factory() as session:
        stored = await session.get(Message, response.json()["id"])
    assert stored.content == f"not a registered value: {SECRET}"
