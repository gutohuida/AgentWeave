"""`runner_events.diagnostic_event` (`a-copilot-agent-runs-over-acp` task 6.1, design D10).

`agent-stream-events` *Versioned kind-specific payloads*: "Diagnostic payloads SHALL identify
stream and severity". Until this builder the Hub had the `diagnostic` kind in its closed set and
no way to build one.
"""

from typing import get_args

from hub.runner_events import MAX_TOOL_RESULT_BYTES, PAYLOAD_VERSION, diagnostic_event
from hub.schemas.agents import StreamEventKind


def test_payload_names_stream_severity_and_summary():
    event = diagnostic_event(
        stream="copilot", severity="warning", summary="Copilot did not select the agent file"
    )
    assert event.kind == "diagnostic"
    assert event.kind in get_args(StreamEventKind)
    assert event.content == "Copilot did not select the agent file"
    assert event.payload == {
        "version": PAYLOAD_VERSION,
        "stream": "copilot",
        "severity": "warning",
        "summary": "Copilot did not select the agent file",
    }


def test_code_and_facts_are_carried_when_given():
    event = diagnostic_event(
        stream="copilot",
        severity="info",
        summary="a new session was started",
        code="copilot.session_missing",
        facts={"old_session_id": "abc"},
    )
    assert event.payload["code"] == "copilot.session_missing"
    assert event.payload["facts"] == {"old_session_id": "abc"}


def test_summary_is_bounded_and_redacted():
    secret = "ghp_" + "A1b2C3d4" * 5
    event = diagnostic_event(stream="copilot", severity="warning", summary=f"token {secret}")
    assert secret not in event.content
    assert secret not in str(event.payload)

    long = diagnostic_event(
        stream="copilot", severity="info", summary="word " * MAX_TOOL_RESULT_BYTES
    )
    assert len(long.content.encode("utf-8")) <= MAX_TOOL_RESULT_BYTES
    assert long.payload["truncated"] is True


def test_facts_strings_are_redacted_too():
    secret = "ghp_" + "Z9y8X7w6" * 5
    event = diagnostic_event(
        stream="copilot", severity="warning", summary="removed", facts={"token": secret, "n": 1}
    )
    assert secret not in str(event.payload["facts"])
