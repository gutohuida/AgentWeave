"""Slice 5 group A, tasks 1.2 and 1.3: Copilot's compaction, errors and subagents reach the stream.

`a-copilot-agent-uses-hooks-and-its-own-agents` design D4 (compaction), D5 (errors) and D6
(subagents). Every fixture is fed through `copilot_acp.CopilotEventMapper` **in the order task
1.1's real capture recorded it** (`fixtures/copilot/{compaction,subagent,error}.jsonl`): raw
`github.com/copilot/sessionEvent` notifications go to `on_raw_event` with their whole params (the
envelope's `agentId` and `dataOmitted` live there), `session/update` notifications to
`on_session_update`, then `finish()`, exactly as `copilot_acp.run_turn` routes them.

Each test here failed before group A was built: the mapper mapped no compaction or subagent type
at all (drive task 7.2 measured zero events from `compaction.jsonl`), and it turned the `Error:`
echo, not the raw event, into the error.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub.copilot_acp import RAW_EVENT_METHOD, CopilotEventMapper
from hub.runner_events import RunEvent

FIXTURES = Path(__file__).parent / "fixtures" / "copilot"


def _load(name: str) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _feed(messages: List[Dict[str, Any]], mapper: CopilotEventMapper = None) -> List[RunEvent]:
    mapper = mapper or CopilotEventMapper()
    events: List[RunEvent] = []
    for message in messages:
        params = message.get("params") or {}
        if message.get("method") == RAW_EVENT_METHOD:
            events += mapper.on_raw_event(params.get("type"), params.get("data"), params)
        elif message.get("method") == "session/update":
            update = params.get("update")
            if isinstance(update, dict) and update.get("sessionUpdate") != "usage_update":
                # `run_turn` routes `usage_update` to the context reading, never the mapper.
                events += mapper.on_session_update(update)
    return events + mapper.finish()


def _raw(type_: str, data: Dict[str, Any], **envelope: Any) -> Dict[str, Any]:
    params = {"sessionId": "<redacted>", "type": type_, "data": data}
    params.update(envelope)
    return {"jsonrpc": "2.0", "method": RAW_EVENT_METHOD, "params": params}


def _chunk(text: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "<redacted>",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }


def _index_of(messages: List[Dict[str, Any]], type_: str) -> int:
    return next(
        i
        for i, message in enumerate(messages)
        if message.get("method") == RAW_EVENT_METHOD and message["params"].get("type") == type_
    )


def _compacted(events: List[RunEvent]) -> List[RunEvent]:
    return [e for e in events if e.kind == "status" and e.payload.get("phase") == "compacted"]


# --------------------------------------------------------------------------- 1.2 compaction


def test_the_captured_compaction_is_one_compacted_status_with_its_counts():
    events = _feed(_load("compaction.jsonl"))

    compacted = _compacted(events)
    assert len(compacted) == 1
    payload = compacted[0].payload
    # The captured `session.compaction_complete`: 45 -> 790 of 128,000, a manual `/compact`.
    assert payload["pre_tokens"] == 45
    assert payload["post_tokens"] == 790
    assert payload["token_limit"] == 128000
    # Integers, not "<redacted>": `_SECRET_FIELD_RE` matches any key containing `token` (D4).
    assert all(type(payload[key]) is int for key in ("pre_tokens", "post_tokens", "token_limit"))
    assert payload["trigger"] == "manual"
    assert payload["percent"] == round(45 / 128000 * 100, 2)
    # Copilot's summary is never stored (D4).
    assert "summaryContent" not in json.dumps(payload)
    assert "<overview>" not in json.dumps(payload)
    assert "requested" in compacted[0].content


def test_a_failed_compaction_is_a_warning_diagnostic_not_a_compaction():
    messages = _load("compaction.jsonl")
    at = _index_of(messages, "session.compaction_complete")
    failed = copy.deepcopy(messages[at])
    failed["params"]["data"] = {
        "success": False,
        "error": "summariser timed out",
        "statusCode": 504,
    }
    messages[at] = failed

    events = _feed(messages)

    assert _compacted(events) == []
    diagnostics = [e for e in events if e.kind == "diagnostic"]
    failures = [d for d in diagnostics if d.payload.get("code") == "copilot.compaction_failed"]
    assert len(failures) == 1
    assert failures[0].payload["stream"] == "copilot"
    assert failures[0].payload["severity"] == "warning"
    assert "summariser timed out" in failures[0].content


def test_a_compaction_too_large_to_relay_still_counts_from_its_start_event():
    """An oversized event loses its whole `data` (D1, R3). A mapper that requires
    `data.success` would drop exactly the large compactions this backstop exists for."""
    messages = [
        _raw(
            "session.compaction_start",
            {"currentTokens": 152000, "tokenLimit": 200000, "trigger": "threshold"},
        ),
        _raw(
            "session.compaction_complete",
            {"omitted": True, "bytes": 48211, "limit": 32768},
            dataOmitted="too-large",
        ),
    ]

    events = _feed(messages)

    compacted = _compacted(events)
    assert len(compacted) == 1
    payload = compacted[0].payload
    assert payload["pre_tokens"] == 152000
    assert payload["token_limit"] == 200000
    assert "post_tokens" not in payload
    assert payload["percent"] == 76.0
    assert "too large to relay" in compacted[0].content


def test_an_unserializable_compaction_report_is_a_diagnostic_and_does_not_count():
    events = _feed(
        [_raw("session.compaction_complete", {"omitted": True}, dataOmitted="unserializable")]
    )
    assert _compacted(events) == []
    assert [e.payload.get("code") for e in events if e.kind == "diagnostic"] == [
        "copilot.compaction_unreadable"
    ]


@pytest.mark.parametrize(
    "where", ["envelope agentId", "data agentId", "data parentToolCallId"], ids=str
)
def test_a_subagents_compaction_is_not_the_conversations(where):
    messages = _load("compaction.jsonl")
    at = _index_of(messages, "session.compaction_complete")
    if where == "envelope agentId":
        messages[at]["params"]["agentId"] = "87c20d8e-8d8b-4523-a4b2-4c7f5d625672"
    elif where == "data agentId":
        messages[at]["params"]["data"]["agentId"] = "87c20d8e"
    else:
        messages[at]["params"]["data"]["parentToolCallId"] = "call_parent"

    events = _feed(messages)

    assert _compacted(events) == []
    assert not any(e.payload.get("code", "").startswith("copilot.compaction") for e in events)


# --------------------------------------------------------------------------- 1.2 subagents


def test_the_captured_subagent_is_a_started_and_completed_pair_on_the_task_calls_id():
    events = _feed(_load("subagent.jsonl"))

    task_uses = [
        e
        for e in events
        if e.kind == "tool_use" and '"agent_type": "explore"' in e.payload["input"]
    ]
    assert len(task_uses) == 1
    call_id = task_uses[0].call_id

    started = [e for e in events if e.kind == "status" and e.payload["phase"] == "subagent_started"]
    completed = [
        e for e in events if e.kind == "status" and e.payload["phase"] == "subagent_completed"
    ]
    # Paired by `call_id`, never by position: a raw event can overtake the queued `tool_use`.
    assert [e.payload["call_id"] for e in started] == [call_id]
    assert [e.payload["call_id"] for e in completed] == [call_id]
    done = completed[0].payload
    assert done["agent_name"] == "explore"
    assert done["model"] == "claude-haiku-4.5"
    assert type(done["total_tokens"]) is int and done["total_tokens"] == 8825
    assert done["duration_ms"] == 4518
    assert done["total_tool_calls"] == 1
    assert started[0].content == "file-name-probe started"
    assert completed[0].content == "file-name-probe finished"


def test_a_failed_subagent_carries_its_error_and_its_counts():
    events = _feed(
        [
            _raw(
                "subagent.failed",
                {
                    "toolCallId": "call_task_9",
                    "agentName": "code-review",
                    "agentDisplayName": "reviewer",
                    "error": "model refused with key sk-ant-test-value",
                    "totalTokens": 120,
                    "durationMs": 900,
                    "totalToolCalls": 0,
                },
                agentId="sub-1",
            )
        ]
    )
    failed = [e for e in events if e.kind == "status" and e.payload["phase"] == "subagent_failed"]
    assert len(failed) == 1
    payload = failed[0].payload
    assert payload["call_id"] == "call_task_9"
    assert payload["total_tokens"] == 120
    assert "sk-ant-test-value" not in json.dumps(payload)
    assert "sk-ant-test-value" not in failed[0].content
    assert failed[0].content.startswith("reviewer failed: ")


# --------------------------------------------------------------------------- 1.3 errors


def _texts(events: List[RunEvent]) -> List[str]:
    return [e.content for e in events if e.kind == "text"]


def test_the_captured_error_is_one_error_event_and_no_echoed_text():
    messages = _load("error.jsonl")
    # The recorded order: the raw `session.error` reaches the pipe before its `Error:` chunk (D5).
    assert _index_of(messages, "session.error") < len(messages) - 1
    assert messages[-1]["params"]["update"]["content"]["text"].startswith("Error: ")

    events = _feed(messages)

    errors = [e for e in events if e.kind == "error"]
    assert len(errors) == 1
    payload = errors[0].payload
    assert payload["code"] == "copilot.authentication"
    assert payload["status_code"] == 401
    assert "Authentication failed with provider" in payload["message"]
    assert not any(e.kind == "diagnostic" and "Authentication" in e.content for e in events)
    assert not any("Error: Authentication" in text for text in _texts(events))


def test_prose_before_the_echo_is_kept_as_text_and_the_error_stays_single():
    """The echo is one chunk appended to whatever is accumulating, so the block is
    `"Let me run the tests.Error: ..."`; the match is on the chunk, at arrival (D5, R3)."""
    messages = _load("error.jsonl")
    messages.insert(len(messages) - 1, _chunk("Let me run the tests."))

    events = _feed(messages)

    assert _texts(events) == ["Let me run the tests."]
    assert len([e for e in events if e.kind == "error"]) == 1


def test_the_order_matters_a_reversed_capture_keeps_the_echo():
    """Nothing emits the chunk first (D5), so nothing is held for it. Reversed, the chunk has
    already accumulated when the raw event arrives: the error is still recorded, and the text is
    recorded as it is -- which is why the test above fails if its fixture's order is reversed."""
    messages = _load("error.jsonl")
    at = _index_of(messages, "session.error")
    raw = messages.pop(at)
    messages.append(raw)

    events = _feed(messages)

    assert len([e for e in events if e.kind == "error"]) == 1
    assert any(text.startswith("Error: Authentication") for text in _texts(events))


def test_without_the_raw_event_the_echo_is_text_as_before():
    messages = _load("error.jsonl")
    messages.pop(_index_of(messages, "session.error"))

    events = _feed(messages)

    assert not any(e.kind == "error" for e in events)
    assert any(text.startswith("Error: Authentication") for text in _texts(events))


@pytest.mark.parametrize("where", ["envelope agentId", "data parentToolCallId"], ids=str)
def test_a_subagents_error_is_one_error_event_naming_it_and_no_text(where):
    data: Dict[str, Any] = {"errorType": "model_error", "message": "subagent tool crashed"}
    envelope: Dict[str, Any] = {}
    if where == "envelope agentId":
        envelope["agentId"] = "sub-7"
    else:
        data["parentToolCallId"] = "call_task_7"
    mapper = CopilotEventMapper()

    events = _feed(
        [_raw("session.error", data, **envelope), _chunk("Error: subagent tool crashed")], mapper
    )

    errors = [e for e in events if e.kind == "error"]
    assert len(errors) == 1
    assert errors[0].payload["code"] == "copilot.model_error"
    assert errors[0].payload["subagent_id"] == ("sub-7" if envelope else "call_task_7")
    assert _texts(events) == []
    # Only a root error fails the turn (slice 2's rule, D5 finding 8).
    assert mapper.root_error is None


def test_a_root_error_still_fails_the_turn():
    mapper = CopilotEventMapper()
    _feed(_load("error.jsonl"), mapper)
    assert mapper.root_error is not None
    assert mapper.root_error.startswith("Authentication failed with provider")


@pytest.mark.parametrize("error_type", ["Quota", "rate-limit", "x" * 33, None, 7])
def test_an_unrecognisable_error_type_is_coded_unknown(error_type):
    events = _feed([_raw("session.error", {"errorType": error_type, "message": "boom"})])
    assert [e.payload["code"] for e in events if e.kind == "error"] == ["copilot.unknown"]


def test_an_error_message_is_stored_without_a_key_it_quotes():
    events = _feed(
        [
            _raw(
                "session.error",
                {
                    "errorType": "authentication",
                    "message": "Provider refused key sk-ant-test-value (HTTP 401)",
                    "remediation": "sign_in",
                },
            )
        ]
    )
    (error,) = [e for e in events if e.kind == "error"]
    assert "sk-ant-test-value" not in json.dumps(error.payload)
    assert "sk-ant-test-value" not in error.content
    assert error.payload["remediation"] == "sign_in"


def test_each_raw_error_swallows_at_most_one_echo():
    events = _feed(
        [
            _raw("session.error", {"errorType": "internal", "message": "boom"}),
            _chunk("Error: boom"),
            _raw("tool.execution_start", {"toolCallId": "c1", "toolName": "shell"}),
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"update": {"sessionUpdate": "tool_call", "toolCallId": "c1"}},
            },
            _chunk("Error: boom"),
        ]
    )
    assert len([e for e in events if e.kind == "error"]) == 1
    assert _texts(events) == ["Error: boom"]


@pytest.mark.asyncio
async def test_recording_a_quota_error_places_no_hold_of_its_own(app):
    """The recorder adds no hold path (D5). Slice 4 may hold the queue from the same raw event
    through the run's allowance reading; that is not the recorder's."""
    from hub import provider_allowance
    from hub.db.engine import async_session_factory
    from hub.db.models import AgentOutput
    from hub.output_recording import record_agent_output

    (error,) = [
        e
        for e in _feed([_raw("session.error", {"errorType": "quota", "message": "No quota left"})])
        if e.kind == "error"
    ]
    assert error.payload["code"] == "copilot.quota"

    async with async_session_factory() as db:
        before = await provider_allowance.provider_hold(db, "proj-test", "cp5")
        await record_agent_output(
            db,
            "proj-test",
            "cp5",
            content=error.content,
            session_id=None,
            kind=error.kind,
            payload=error.payload,
        )
        after = await provider_allowance.provider_hold(db, "proj-test", "cp5")
        rows = (
            (await db.execute(select(AgentOutput).where(AgentOutput.agent == "cp5")))
            .scalars()
            .all()
        )

    assert before is None and after is None
    assert len(rows) == 1


# --------------------------------------------------------------------------- timeline order


def test_text_written_before_a_compaction_reads_before_its_card():
    """Drive 7.2 (2026-10-04) posted the card ahead of the "ok" reply the conversation held before
    `/compact`: a raw event's card was emitted while the earlier message was still open. A card
    a raw event produces closes the open block first, so the timeline reads in the order it
    happened."""
    events = _feed(_load("compaction.jsonl"))
    kinds = [(e.kind, e.payload.get("phase") or e.content[:12]) for e in events]
    assert kinds.index(("text", "ok")) < kinds.index(("status", "compacted"))


def test_prose_before_an_error_reads_before_the_error():
    messages = _load("error.jsonl")
    at = _index_of(messages, "session.error")
    messages.insert(at, _chunk("Let me run the tests."))

    events = _feed(messages)

    assert [e.kind for e in events if e.kind in ("text", "error")] == ["text", "error"]
    assert _texts(events) == ["Let me run the tests."]


def test_a_subagents_streamed_text_reads_before_its_completion():
    events = _feed(_load("subagent.jsonl"))
    order = [
        (e.kind, e.payload.get("phase"))
        for e in events
        if e.kind == "text" or (e.kind == "status" and "subagent" in e.payload.get("phase", ""))
    ]
    assert order.index(("text", None)) < order.index(("status", "subagent_completed"))
