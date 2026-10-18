"""F679 acceptance (spdoc-48a94dbf4a02): a Claude subagent's tool call reaches the operator as the
subagent's.

`fixtures/claude_subagent/stream.jsonl` is four real lines from `claude -p --output-format
stream-json --verbose` (CC 2.1.301, Haiku, 2026-10-18, background tasks off as the Hub runs it), in
the order the CLI emitted them: the parent's `Agent` call ("count files"), the subagent's `Bash`
call and its result (each line carrying `parent_tool_use_id`, `task_description`, `agent_id`), and
the `Agent` call's own result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, PermissionRequest, Run
from hub.runner_parsing import parse_claude_line

LINES = (
    (Path(__file__).parent / "fixtures" / "claude_subagent" / "stream.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
)
AGENT_CALL = json.loads(LINES[0])["message"]["content"][0]["id"]
BASH_CALL = json.loads(LINES[1])["message"]["content"][0]["id"]


def _tool_events():
    return [
        event
        for line in LINES
        for event in parse_claude_line(line).events
        if event.kind in ("tool_use", "tool_result")
    ]


def test_a_subagents_calls_carry_the_call_they_came_from():
    events = _tool_events()
    by_call = {(e.kind, e.payload["call_id"]): e.payload for e in events}
    for kind in ("tool_use", "tool_result"):
        subagent = by_call[(kind, BASH_CALL)]["subagent"]
        assert subagent == {
            "parent_call_id": AGENT_CALL,
            "description": "count files",
            "type": "general-purpose",
        }
    assert "subagent" not in by_call[("tool_use", AGENT_CALL)]
    assert "subagent" not in by_call[("tool_result", AGENT_CALL)]


async def _seed(run_id, conversation_id, agent):
    async with async_session_factory() as db:
        db.add(
            Conversation(id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open")
        )
        db.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
            )
        )
        for sequence, event in enumerate(_tool_events()):
            db.add(
                AgentOutput(
                    id=f"out-{run_id}-{sequence}",
                    project_id="proj-test",
                    agent=agent,
                    conversation_id=conversation_id,
                    content=event.content,
                    kind=event.kind,
                    payload=event.payload,
                    run_id=run_id,
                    sequence=sequence,
                )
            )
        for request_id, call in (("perm-sub", BASH_CALL), ("perm-own", AGENT_CALL)):
            db.add(
                PermissionRequest(
                    id=request_id,
                    project_id="proj-test",
                    agent=agent,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    tool_name="Bash",
                    tool_use_id=call,
                    tool_input={"command": "ls"},
                    status="pending",
                )
            )
        await db.commit()


@pytest.mark.asyncio
async def test_a_listed_request_names_the_subagent_that_made_the_call(app, auth_headers):
    await _seed("run-sub-1", "conv-sub-1", "lead")
    listed = await app.get(
        "/api/v1/projects/proj-test/permission-requests?include_expired=true",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id["perm-sub"]["subagent"] == {
        "parent_call_id": AGENT_CALL,
        "description": "count files",
        "type": "general-purpose",
    }
    assert by_id["perm-own"]["subagent"] is None
