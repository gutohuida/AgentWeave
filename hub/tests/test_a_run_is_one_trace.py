"""Acceptance test for `a-run-is-a-trace-you-can-export` (trace-1019, Tier 2).

One real turn through `POST /agent/trigger`, the background task, `_execute_run`, the real Claude
parser and `record_agent_output`, with only the spawned process faked. Mid-turn, the run reports a
refused permission decision through `/agent-actions/permission-decisions` with its own credential,
exactly as `mcp_server._report_decision` does. The fake process holds the tool's result back until
that report has been answered, so the decision lands while the run is live, as it does for real.

Then the product's own routes are read: one trace for the run, whose spans include the model call,
the tool call and the judge decision under it; a key written in the prompt, the model's text, the
tool's input and the judge's reason appears nowhere in it; the export is OTLP JSON carrying it; and
the clear removes it while the conversation's own rows stay.

Written before the build and seen failing (404 on `/traces/by-run/...`: no route, no table).
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput

from ._background_runs import await_background_runs

PROJECT = "proj-test"
AGENT = "tracer"
SESSION = "sess-trace-1019"
CALL = "toolu_trace_1"
#: A Hub key shape, which the named patterns redact wherever it appears.
SECRET = "aw_live_" + "Zq7" * 11


def _assistant_line() -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "msg_trace_1",
                "model": "claude-haiku-4-5-20251001",
                "content": [
                    {"type": "text", "text": f"I will check the key {SECRET} first."},
                    {
                        "type": "tool_use",
                        "id": CALL,
                        "name": "Bash",
                        "input": {"command": f"curl -H 'X: {SECRET}' http://example.invalid"},
                    },
                ],
            },
            "session_id": SESSION,
        }
    )


def _refused_result_line() -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": CALL,
                        "is_error": True,
                        "content": "Denied: the command reaches the network.",
                    }
                ]
            },
            "session_id": SESSION,
        }
    )


def _final_lines() -> List[str]:
    return [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "msg_trace_2",
                    "model": "claude-haiku-4-5-20251001",
                    "content": [{"type": "text", "text": "The call was refused, so I stopped."}],
                },
                "session_id": SESSION,
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "The call was refused, so I stopped.",
                "session_id": SESSION,
                "usage": {"input_tokens": 12, "output_tokens": 34},
                "modelUsage": {
                    "claude-haiku-4-5-20251001": {"inputTokens": 12, "outputTokens": 34}
                },
            }
        ),
    ]


def _gated_pty(captured: Dict[str, Any], decided: threading.Event):
    """A spawn whose output stops after the tool call until *decided* is set (read runs in an
    executor thread, so blocking here holds the turn open the way a real approval does)."""

    def _spawn(*args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        session = MagicMock()
        session.pid = 4343
        state = {"step": 0}

        def _read(*_a, **_k):
            step = state["step"]
            state["step"] += 1
            if step == 0:
                return _assistant_line() + "\n"
            if step == 1:
                decided.wait(timeout=20)
                return _refused_result_line() + "\n"
            if step == 2:
                return "\n".join(_final_lines()) + "\n"
            return ""

        session.read.side_effect = _read
        session.wait.return_value = 0
        return session

    return MagicMock(side_effect=_spawn)


async def _wait_for_tool_row(run_id: str) -> None:
    for _ in range(200):
        async with async_session_factory() as db:
            found = (
                await db.execute(
                    select(AgentOutput.id).where(
                        AgentOutput.run_id == run_id, AgentOutput.kind == "tool_use"
                    )
                )
            ).first()
        if found:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the tool call was never recorded")


@pytest.mark.asyncio
async def test_one_turn_is_one_redacted_trace_that_exports_and_clears(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(AGENT, cli="claude")

    captured: Dict[str, Any] = {}
    decided = threading.Event()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _gated_pty(captured, decided)):
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"/api/v1/projects/{PROJECT}/agent/trigger",
                json={
                    "agent": AGENT,
                    "message": f"Check the service with key {SECRET}.",
                    "session_mode": "new",
                },
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            try:
                await _wait_for_tool_row(run_id)
                token = captured["env"]["AW_RUN_TOKEN"]
                report = await app.post(
                    "/api/v1/agent-actions/permission-decisions",
                    json={
                        "tool_name": "Bash",
                        "tool_use_id": CALL,
                        "allowed": False,
                        "reason": f"the command names {SECRET} and reaches the network",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert report.status_code == 202, report.text
            finally:
                decided.set()
            await await_background_runs()

    # One trace for the run.
    by_run = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/by-run/{run_id}", headers=auth_headers
    )
    assert by_run.status_code == 200, by_run.text
    trace = by_run.json()
    spans = trace["spans"]
    trace_id = trace["trace_id"]
    assert len(trace_id) == 32 and all(span["trace_id"] == trace_id for span in spans)

    roots = [span for span in spans if span["parent_span_id"] is None]
    assert len(roots) == 1
    root = roots[0]
    assert root["operation"] == "invoke_agent"
    assert root["attributes"]["gen_ai.agent.name"] == AGENT
    assert root["attributes"]["aw.run.id"] == run_id
    assert root["end_time"] is not None
    prompt_text = json.dumps(root["attributes"]["gen_ai.input.messages"])
    assert "Check the service with key" in prompt_text

    chats = [span for span in spans if span["operation"] == "chat"]
    assert chats, "no model-call span"
    assert "I will check the key" in json.dumps(chats[0]["attributes"]["gen_ai.output.messages"])

    tools = [span for span in spans if span["operation"] == "execute_tool"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["attributes"]["gen_ai.tool.name"] == "Bash"
    assert tool["attributes"]["gen_ai.tool.call.id"] == CALL
    assert tool["status"] == "error"
    assert tool["end_time"] is not None

    judges = [span for span in spans if span["operation"] == "aw.judge"]
    assert len(judges) == 1
    judge = judges[0]
    assert judge["parent_span_id"] == tool["span_id"]
    assert judge["attributes"]["aw.decision.allowed"] is False
    assert "reaches the network" in judge["attributes"]["aw.decision.reason"]

    # Redacted everywhere: prompt, model text, tool input, judge reason.
    assert SECRET not in json.dumps(trace)
    assert "<redacted>" in prompt_text

    # Listed as a trace of the project.
    # The run's own kind of trace: the requests that started it are traces too.
    listed = await app.get(
        f"/api/v1/projects/{PROJECT}/traces",
        params={"operation": "invoke_agent"},
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    assert [row["trace_id"] for row in listed.json()["traces"]] == [trace_id]

    # Export: OTLP JSON for the day, carrying every span of the trace.
    today = datetime.now(timezone.utc).date()
    window = {"since": today.isoformat(), "until": (today + timedelta(days=1)).isoformat()}
    exported = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/export", params=window, headers=auth_headers
    )
    assert exported.status_code == 200, exported.text
    otlp = exported.json()
    otlp_spans = [
        span
        for resource in otlp["resourceSpans"]
        for scope in resource["scopeSpans"]
        for span in scope["spans"]
    ]
    assert {span["traceId"] for span in otlp_spans} == {trace_id}
    assert {span["spanId"] for span in otlp_spans} == {span["span_id"] for span in spans}
    assert all(int(span["startTimeUnixNano"]) > 0 for span in otlp_spans)
    assert SECRET not in exported.text

    # Clear the day: the trace goes, the conversation's own rows stay.
    async with async_session_factory() as db:
        outputs_before = (
            await db.execute(select(func.count()).where(AgentOutput.run_id == run_id))
        ).scalar_one()
    cleared = await app.request(
        "DELETE", f"/api/v1/projects/{PROJECT}/traces", params=window, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted_spans"] == len(spans)
    gone = await app.get(f"/api/v1/projects/{PROJECT}/traces/by-run/{run_id}", headers=auth_headers)
    assert gone.status_code == 404
    empty = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/export", params=window, headers=auth_headers
    )
    assert [
        s for r in empty.json()["resourceSpans"] for sc in r["scopeSpans"] for s in sc["spans"]
    ] == []
    async with async_session_factory() as db:
        outputs_after = (
            await db.execute(select(func.count()).where(AgentOutput.run_id == run_id))
        ).scalar_one()
    assert outputs_after == outputs_before > 0
