"""A refused Copilot call does not end the turn (F660, change
`a-refused-copilot-call-does-not-end-the-turn`, decision fix-D3).

ACP's `reject_once` carries no reason, and Copilot's runtime ends the prompt on a rejected root
call: the run read `completed`, exit 0, with nothing after the refusal (work-PC runs
`run-047359204292`, `run-b175c9ffa621`, `run-b1f5b4bedc18`). The Hub now sends one follow-up
`session/prompt` carrying the reason, and says so when a turn still ends on a refusal.

Each script replays the wire order of a refused root call. Steps 1-3 follow
`fixtures/copilot_acp/turn_write_shell_mcp.jsonl`; steps 4-5 follow Copilot's `events.jsonl` for
the work-PC runs (their ACP-level order is uncaptured): raw start, `tool_call` pending, the
permission request, raw complete (rejected), `tool_call_update` failed, then the prompt result.
There is no `agent_message_chunk` after the reject.
"""

import asyncio
import logging
import time

import pytest

from hub import copilot_acp
from hub.copilot_acp import TurnOutcome, run_turn
from tests.test_copilot_acp_run_turn import (
    _LOADED_HUB,
    _MCP_START,
    _OPTIONS,
    AGENT_NAME,
    SESSION_ID,
    WORK,
    _collector,
    _FakeACPSession,
    _mcp_permission,
    _new_with,
    _patch_spawn,
    _raw_event,
)

OUTSIDE = "Get-ChildItem 'C:\\Python*'"
END_TURN = {"response": {"stopReason": "end_turn", "usage": {"inputTokens": 1}}}


class _Fake(_FakeACPSession):
    """The run-turn fake plus two entries this file needs, leaving the shared ones unchanged:
    ``{"hang": asyncio.Event()}`` blocks the in-flight request until the event is set (R2: the
    shared fake cannot "never answer"), and ``{"sleep": seconds}`` spends time inside it."""

    async def request(self, method, params, *, timeout=30.0):
        while self._script and ("hang" in self._script[0] or "sleep" in self._script[0]):
            entry = self._script.pop(0)
            if "hang" in entry:
                self.sent_requests.append((method, params))
                await entry["hang"].wait()
                raise AssertionError("a hang entry was released")
            await asyncio.sleep(entry["sleep"])
        return await super().request(method, params, timeout=timeout)


def _update(update):
    return {"notification": "session/update", "params": {"sessionId": SESSION_ID, "update": update}}


def _chunk(text):
    return _update(
        {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
    )


def _start(call_id, command=OUTSIDE, *, subagent=False):
    data = {"toolCallId": call_id, "toolName": "powershell", "arguments": {"command": command}}
    event = _raw_event("tool.execution_start", data)
    if subagent:
        data["parentToolCallId"] = "call_task_root"
        event["params"]["agentId"] = "agent-sub-1"
    return event


def _pending(call_id, command=OUTSIDE):
    return _update(
        {
            "sessionUpdate": "tool_call",
            "toolCallId": call_id,
            "title": "List the Python folders",
            "kind": "execute",
            "status": "pending",
            "rawInput": {"command": command},
        }
    )


def _permission(call_id, command=OUTSIDE, request_id=7):
    return {
        "server_request": {
            "id": request_id,
            "method": "session/request_permission",
            "params": {
                "sessionId": SESSION_ID,
                "toolCall": {
                    "toolCallId": call_id,
                    "title": "List the Python folders",
                    "kind": "execute",
                    "status": "pending",
                    "rawInput": {"command": command, "commands": [command]},
                },
                "options": _OPTIONS,
            },
        }
    }


def _rejected(call_id, *, subagent=False):
    data = {
        "toolCallId": call_id,
        "success": False,
        "error": {"code": "rejected", "message": "The user rejected this tool call."},
    }
    event = _raw_event("tool.execution_complete", data)
    if subagent:
        data["parentToolCallId"] = "call_task_root"
        event["params"]["agentId"] = "agent-sub-1"
    return event


def _failed_update(call_id):
    return _update({"sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": "failed"})


def _refused_root(call_id="call_ps_1", command=OUTSIDE, request_id=7):
    """Steps 1-5 of a refused root call."""
    return [
        _start(call_id, command),
        _pending(call_id, command),
        _permission(call_id, command, request_id),
        _rejected(call_id),
        _failed_update(call_id),
    ]


async def _drive(monkeypatch, script, *, fake_hook=None, **overrides):
    events = []
    fake = _Fake(script)
    if fake_hook is not None:
        fake_hook(fake)
    _patch_spawn(monkeypatch, fake)
    kwargs = {
        "cwd": WORK,
        "env": {"AW_RUN_ID": "run-f660"},
        "prompt": "List the Python installs.",
        "model": None,
        "resume_session_id": None,
        "agent": AGENT_NAME,
        "per_turn_context": "## Workspace\n- root: C:\\work",
        "tool_surface_context": "## Tools",
        "stable_context": None,
        "control_overrides": None,
        "told_access_path": "mcp",
        "permission_mode": "acceptEdits",
        "workspace": WORK,
        "restrict_spec_writes": False,
        "extra_flags": None,
        "on_event": _collector(events),
        "on_session": _collector([]),
    }
    kwargs.update(overrides)
    outcome = await run_turn(**kwargs)
    return fake, events, outcome


def _prompts(fake):
    return [p for m, p in fake.sent_requests if m == "session/prompt"]


def _prompt_text(params):
    return "\n".join(b.get("text", "") for b in params["prompt"] if b.get("type") == "text")


def _continuations(fake):
    return [p for p in _prompts(fake) if "call ask_user" in _prompt_text(p)]


def _codes(events):
    return [e.payload.get("code") for e in events if e.kind == "diagnostic"]


def _diag(events, code):
    found = [e for e in events if e.kind == "diagnostic" and e.payload.get("code") == code]
    return found


def _texts(events):
    return [e.payload.get("text") for e in events if e.kind == "text"]


# --- 1.1 the stop reason ---------------------------------------------------------------------


async def test_the_stop_reason_is_on_the_outcome(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="hub.copilot_acp")
    script = _new_with() + [_chunk("Done."), END_TURN]
    _fake, _events, outcome = await _drive(monkeypatch, script)
    assert outcome.stop_reason == "end_turn"
    logged = [r.getMessage() for r in caplog.records if "end_turn" in r.getMessage()]
    assert logged and "run-f660" in logged[0], caplog.text


# --- 1.2 / 1.3 the continuation --------------------------------------------------------------


async def test_a_judge_refusal_that_ends_the_turn_is_continued_once_with_its_reason(monkeypatch):
    refusals = []

    async def on_refusal(method, subject):
        refusals.append(subject)

    script = (
        _new_with()
        + _refused_root()
        + [END_TURN, _chunk("I will stay inside the workspace instead."), END_TURN]
    )
    fake, events, outcome = await _drive(monkeypatch, script, on_refusal=on_refusal)

    continuations = _continuations(fake)
    assert len(continuations) == 1, _prompts(fake)
    assert continuations[0]["sessionId"] == SESSION_ID
    text = _prompt_text(continuations[0])
    assert text.startswith("The Hub refused your last tool call (a command)")
    assert "Edit files allows file changes inside the workspace only" in text
    assert "another way" in text
    assert outcome.status == "completed"
    assert outcome.refusal_continuations == 1
    assert outcome.ended_on_refusal is False
    assert len(refusals) == 1
    kinds = [(e.kind, e.payload.get("code") or e.payload.get("text")) for e in events]
    continued = kinds.index(("diagnostic", "copilot.refusal_continued"))
    reply = kinds.index(("text", "I will stay inside the workspace instead."))
    assert continued < reply, kinds


async def test_an_operator_deny_that_ends_the_turn_is_continued_with_the_operator_named(
    monkeypatch,
):
    async def request_approval(method, subject):
        return False

    script = (
        _new_with()
        + _refused_root(command="echo hi")
        + [END_TURN, _chunk("Understood, I will not run it."), END_TURN]
    )
    fake, _events, outcome = await _drive(
        monkeypatch, script, permission_mode="manual", request_approval=request_approval
    )
    continuations = _continuations(fake)
    assert len(continuations) == 1
    assert _prompt_text(continuations[0]).startswith(
        "The operator did not approve your last tool call (a command)"
    )
    assert outcome.status == "completed"


async def test_with_no_operator_channel_the_refusal_is_the_hubs(monkeypatch):
    script = _new_with() + _refused_root(command="echo hi") + [END_TURN, _chunk("Fine."), END_TURN]
    fake, _events, _outcome = await _drive(
        monkeypatch, script, permission_mode="manual", request_approval=None
    )
    continuations = _continuations(fake)
    assert len(continuations) == 1
    text = _prompt_text(continuations[0])
    assert text.startswith("The Hub refused your last tool call")
    assert "no operator channel" in text
    assert "operator did not approve" not in text


# --- 1.4 / 1.5 / 1.16 what clears the record ---------------------------------------------------


async def test_a_subagent_refusal_is_not_continued_by_the_hub(monkeypatch):
    call = "call_sub_1"
    script = _new_with() + [
        _start(call, subagent=True),
        _permission(call),
        _rejected(call, subagent=True),
        _update(
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_task_root",
                "status": "completed",
            }
        ),
        _chunk("The subagent could not list it; here is what I found."),
        END_TURN,
    ]
    fake, events, outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []
    assert "copilot.turn_ended_on_refusal" not in _codes(events)
    assert outcome.ended_on_refusal is False


async def test_a_subagent_refusal_alone_before_end_turn_is_not_recorded(monkeypatch):
    """Without the subagent flag, a subagent's refused call would read as a root one."""
    call = "call_sub_2"
    script = _new_with() + [
        _start(call, subagent=True),
        _permission(call),
        _rejected(call, subagent=True),
        END_TURN,
    ]
    fake, events, outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []
    assert outcome.ended_on_refusal is False
    assert outcome.stop_reason == "end_turn"


@pytest.mark.parametrize(
    "text", ["I cannot list that folder, so I stopped.", "Should I try another way?"]
)
async def test_a_refusal_followed_by_agent_text_is_not_continued(monkeypatch, text):
    """A question in prose is not read: the agent answered the refusal, and the turn is over."""
    script = _new_with() + _refused_root() + [_chunk(text), END_TURN]
    fake, events, outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []
    assert "copilot.turn_ended_on_refusal" not in _codes(events)
    assert outcome.ended_on_refusal is False


async def test_a_turn_that_ends_on_a_question_without_a_refusal_is_not_continued(monkeypatch):
    script = _new_with() + [_chunk("Which folder do you mean?"), END_TURN]
    fake, _events, outcome = await _drive(monkeypatch, script)
    assert len(_prompts(fake)) == 1
    assert outcome.refusal_continuations == 0


async def test_a_blank_chunk_after_a_refusal_is_not_agent_text(monkeypatch):
    script = (
        _new_with()
        + _refused_root()
        + [_chunk("  \n"), END_TURN, _chunk("Done another way."), END_TURN]
    )
    fake, _events, _outcome = await _drive(monkeypatch, script)
    assert len(_continuations(fake)) == 1


async def test_a_later_allowed_root_call_clears_the_refusal(monkeypatch):
    """The Hub's own MCP call is allowed under Edit files; its start comes after the refusal."""
    script = _new_with(_LOADED_HUB) + _refused_root() + [_MCP_START, _mcp_permission(8), END_TURN]
    fake, _events, _outcome = await _drive(monkeypatch, script)
    assert [a["outcome"]["optionId"] for _, a in fake.sent_responses] == [
        "reject_once",
        "allow_once",
    ]
    assert _continuations(fake) == []


async def test_a_parallel_call_started_before_the_refusal_does_not_clear_it(monkeypatch):
    a, b = "call_a", "call_b"
    script = _new_with() + [
        _start(a),
        _start(b, "Get-Date"),
        _permission(a),
        _update({"sessionUpdate": "tool_call_update", "toolCallId": b, "status": "completed"}),
        _rejected(a),
        END_TURN,
        _chunk("Going another way."),
        END_TURN,
    ]
    fake, _events, _outcome = await _drive(monkeypatch, script)
    continuations = _continuations(fake)
    assert len(continuations) == 1


async def test_a_parallel_call_started_after_the_refusal_clears_it(monkeypatch):
    a, b = "call_a", "call_b"
    script = _new_with() + [
        _start(a),
        _permission(a),
        _start(b, "Get-Date"),
        _rejected(a),
        END_TURN,
    ]
    fake, _events, _outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []


# --- 1.6 / 1.14 a stop is never continued ------------------------------------------------------


async def test_no_continuation_after_stop(monkeypatch):
    refusals = []

    async def on_refusal(method, subject):
        refusals.append(subject)

    script = _new_with() + _refused_root() + [END_TURN]
    fake, _events, outcome = await _drive(
        monkeypatch, script, on_refusal=on_refusal, should_interrupt=lambda: bool(refusals)
    )
    assert [m for m, _ in fake.sent_notifications].count("session/cancel") == 1
    assert _continuations(fake) == []
    assert outcome.status == "interrupted"


async def test_a_cancelled_stop_reason_is_not_continued(monkeypatch):
    script = _new_with() + _refused_root() + [{"response": {"stopReason": "cancelled"}}]
    fake, _events, outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []
    assert outcome.status == "interrupted"


async def test_a_stop_just_before_the_result_is_not_continued(monkeypatch):
    holder = {}

    def should_interrupt():
        fake = holder.get("fake")
        return fake is not None and not fake._script

    script = _new_with() + _refused_root() + [END_TURN]
    fake, _events, outcome = await _drive(
        monkeypatch,
        script,
        fake_hook=lambda f: holder.setdefault("fake", f),
        should_interrupt=should_interrupt,
    )
    assert [m for m, _ in fake.sent_notifications].count("session/cancel") == 1
    assert _continuations(fake) == []
    assert outcome.status == "interrupted"
    assert fake.closed_with_force is True


# --- 1.7 / 1.8 a turn that still ends on a refusal says so ---------------------------------------


async def test_a_turn_that_ends_on_a_refusal_without_continuing_says_so(monkeypatch):
    monkeypatch.setattr(copilot_acp, "REFUSAL_CONTINUATIONS_PER_TURN", 0, raising=False)
    script = _new_with() + _refused_root() + [END_TURN]
    fake, events, outcome = await _drive(monkeypatch, script)
    assert _continuations(fake) == []
    (said,) = _diag(events, "copilot.turn_ended_on_refusal")
    assert said.payload["severity"] == "warning"
    facts = said.payload["facts"]
    assert facts["tool_call_id"] == "call_ps_1"
    assert facts["label"] == "a command"
    assert facts["decided_by"] == "hub"
    assert facts["continuations"] == 0
    assert "inside the workspace" in facts["reason"]
    assert outcome.ended_on_refusal is True
    assert outcome.status == "completed"


async def test_the_continuation_is_bounded(monkeypatch):
    script = (
        _new_with()
        + _refused_root()
        + [END_TURN]
        + _refused_root("call_ps_9", request_id=9)
        + [END_TURN]
    )
    fake, events, outcome = await _drive(monkeypatch, script)
    assert len(_prompts(fake)) == 2
    (said,) = _diag(events, "copilot.turn_ended_on_refusal")
    assert said.payload["facts"]["continuations"] == 1
    assert said.payload["facts"]["tool_call_id"] == "call_ps_9"
    assert outcome.ended_on_refusal is True
    assert outcome.refusal_continuations == 1


# --- 1.9 / 1.10 / 1.15 a continuation that fails ----------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        {"error": {"code": -32603, "message": "Internal error", "data": {"errorType": "other"}}},
        {"process_exited": True},
    ],
    ids=["error-response", "process-exited"],
)
async def test_a_continuation_that_fails_leaves_the_first_outcome_standing(monkeypatch, failure):
    finishes = []
    real_finish = copilot_acp.CopilotEventMapper.finish

    def counting_finish(self):
        finishes.append(1)
        return real_finish(self)

    monkeypatch.setattr(copilot_acp.CopilotEventMapper, "finish", counting_finish)
    script = _new_with() + _refused_root() + [END_TURN, failure]
    fake, events, outcome = await _drive(monkeypatch, script)
    assert len(_continuations(fake)) == 1
    assert outcome.status == "completed", outcome
    assert outcome.error is None
    assert outcome.ended_on_refusal is True
    assert outcome.refusal_continuations == 1
    (failed,) = _diag(events, "copilot.refusal_continuation_failed")
    assert failed.payload["severity"] == "warning"
    assert failed.payload["facts"]["label"] == "a command"
    assert finishes == [1]
    assert fake.closed_with_force is True


async def test_a_quota_refusal_during_the_continuation_fails_the_run(monkeypatch):
    quota = {
        "error": {
            "code": -32603,
            "message": "quota",
            "data": {"errorType": "quota", "errorCode": "quota_exceeded"},
        }
    }
    script = _new_with() + _refused_root() + [END_TURN, quota]
    _fake, _events, outcome = await _drive(monkeypatch, script)
    assert outcome.status == "failed"


async def test_a_root_session_error_during_the_continuation_fails_the_run(monkeypatch):
    error = _raw_event("session.error", {"errorType": "model_error", "message": "upstream down"})
    script = _new_with() + _refused_root() + [END_TURN, error, END_TURN]
    _fake, _events, outcome = await _drive(monkeypatch, script)
    assert outcome.status == "failed"
    assert "upstream down" in (outcome.error or "")


async def test_a_continuation_that_fails_after_output_fails_the_run(monkeypatch):
    """wpc1-h: once the continuation produced output, its failure is the turn's."""
    script = (
        _new_with()
        + _refused_root()
        + [END_TURN, _chunk("Trying another way..."), {"process_exited": True}]
    )
    fake, events, outcome = await _drive(monkeypatch, script)
    assert len(_continuations(fake)) == 1
    assert outcome.status == "failed"
    assert outcome.error
    assert "copilot.refusal_continuation_failed" not in _codes(events)


async def test_the_continuation_uses_the_remaining_deadline(monkeypatch):
    hang = asyncio.Event()
    script = _new_with() + [{"sleep": 0.6}] + _refused_root() + [END_TURN, {"hang": hang}]
    started = time.monotonic()
    fake, events, outcome = await _drive(monkeypatch, script, turn_timeout=1.0)
    elapsed = time.monotonic() - started
    assert len(_continuations(fake)) == 1
    assert [m for m, _ in fake.sent_notifications].count("session/cancel") == 1
    assert elapsed < 1.5, f"a fresh deadline would take over 1.6 s; took {elapsed:.2f}"
    assert outcome.status == "completed"
    assert fake.closed_with_force is True
    assert "copilot.refusal_continuation_failed" in _codes(events)


async def test_a_cancelled_task_during_the_continuation_propagates(monkeypatch):
    hang = asyncio.Event()
    holder = {}
    script = _new_with() + _refused_root() + [END_TURN, {"hang": hang}]
    events = []

    async def drive():
        return await _drive(
            monkeypatch,
            script,
            fake_hook=lambda f: holder.setdefault("fake", f),
            on_event=_collector(events),
        )

    task = asyncio.ensure_future(drive())
    for _ in range(200):
        await asyncio.sleep(0.01)
        fake = holder.get("fake")
        if fake is not None and len(_continuations(fake)) == 1:
            break
    else:
        task.cancel()
        pytest.fail("no continuation was sent")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "copilot.refusal_continuation_failed" not in _codes(events)
    assert holder["fake"].closed_with_force is not None


# --- 1.11 the lifecycle fields -------------------------------------------------------------------


def test_a_completed_copilot_run_carries_its_stop_reason():
    from hub.api.v1.agent_trigger import _runtime_turn_fields

    outcome = TurnOutcome(
        session_id="s",
        status="completed",
        stop_reason="end_turn",
        ended_on_refusal=True,
        refusal_continuations=1,
    )
    assert _runtime_turn_fields(outcome) == {
        "stop_reason": "end_turn",
        "ended_on_refusal": True,
        "refusal_continuations": 1,
    }
    assert _runtime_turn_fields(TurnOutcome(session_id="s", status="completed")) == {}

    class CodexOutcome:
        thread_id = "t"
        status = "completed"
        error = None

    assert _runtime_turn_fields(CodexOutcome()) == {}
    assert _runtime_turn_fields(None) == {}


# --- 2.D.2 the divergence names the refusal ------------------------------------------------------


async def _diverged_payload(session, run_id):
    from sqlalchemy import select

    from hub.db.models import EventLog

    rows = (
        (await session.execute(select(EventLog).where(EventLog.event_type == "run_diverged")))
        .scalars()
        .all()
    )
    return [r.data for r in rows if (r.data or {}).get("run_id") == run_id]


@pytest.mark.parametrize(
    "code", ["copilot.turn_ended_on_refusal", "copilot.refusal_continuation_failed"]
)
async def test_a_task_run_that_ended_on_a_refusal_names_it_in_its_divergence(app, code):
    from hub.db.engine import async_session_factory
    from hub.db.models import AgentOutput
    from hub.run_divergence import evaluate_run_end
    from tests.test_run_divergence import _bound_run

    run_id = f"run-f660-{code.rsplit('.', 1)[-1]}"
    async with async_session_factory() as session:
        await _bound_run(session, run_id, f"task-{run_id}")
        session.add(
            AgentOutput(
                id=f"out-{run_id}",
                project_id="proj-test",
                agent="worker",
                content="The turn ended on a refusal.",
                kind="diagnostic",
                run_id=run_id,
                payload={
                    "stream": "copilot",
                    "severity": "warning",
                    "summary": "The turn ended on a refusal.",
                    "code": code,
                    "facts": {
                        "tool_call_id": "call_ps_1",
                        "label": "a command",
                        "reason": "Edit files allows file changes inside the workspace only",
                        "decided_by": "hub",
                        "continuations": 1,
                    },
                },
            )
        )
        await session.commit()

    assert await evaluate_run_end(run_id) is not None
    async with async_session_factory() as session:
        (payload,) = await _diverged_payload(session, run_id)
    assert payload["refusal"] == {
        "label": "a command",
        "reason": "Edit files allows file changes inside the workspace only",
    }


async def test_a_task_run_with_no_refusal_keeps_its_divergence(app):
    from hub.db.engine import async_session_factory
    from hub.run_divergence import evaluate_run_end
    from tests.test_run_divergence import _bound_run

    async with async_session_factory() as session:
        await _bound_run(session, "run-f660-plain", "task-f660-plain")
    assert await evaluate_run_end("run-f660-plain") is not None
    async with async_session_factory() as session:
        (payload,) = await _diverged_payload(session, "run-f660-plain")
    assert "refusal" not in payload
