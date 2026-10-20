"""F783: a Copilot turn's deadline does not count time its run spends waiting on the operator.

`spec/changes/the-turn-clock-counts-work-not-waiting`, FR-1 `clock-pauses-for-operator`. A
blocking `ask_user` question (asked through the real agent route, by the run's own credential)
and an Ask me permission card each pause the clock; the clock still bounds the turn's own work,
and it runs again once the wait is over.
"""

from __future__ import annotations

import asyncio

import pytest

import hub.copilot_acp as copilot_acp

from .test_a_task_waits_while_its_run_waits import make_agent, make_run, one
from .test_copilot_acp_run_turn import (
    _END_TURN,
    _OPTIONS,
    SESSION_ID,
    _drive,
    _new_with,
    _raw_event,
)

#: A prompt that answers 3 s after it is sent: three times the 1 s budget these tests give it.
_ANSWERS_IN_3_S = [{"sleep": 3}, _END_TURN]


async def _turn(monkeypatch, run_id: str, script):
    _fake, _events, outcome = await _drive(
        monkeypatch, script, env={"AW_RUN_ID": run_id}, turn_timeout=1
    )
    return outcome


async def _ask(app, run_id: str, agent: str, *, blocking: bool = True) -> str:
    await make_agent(agent)
    headers = await make_run(run_id, agent=agent)
    asked = await app.post(
        "/api/v1/agent-actions/questions", headers=headers, json=one(blocking=blocking)
    )
    assert asked.status_code == 201, asked.text
    return asked.json()["id"]


@pytest.mark.asyncio
async def test_an_open_question_pauses_the_clock(app, monkeypatch):
    await _ask(app, "run-asks", "asker")

    waiting = await _turn(monkeypatch, "run-asks", _new_with() + _ANSWERS_IN_3_S)
    assert waiting.status == "completed", waiting.error

    # The same turn with nothing open is still bounded by its own work.
    unpaused = await _turn(monkeypatch, "run-asks-nothing", _new_with() + _ANSWERS_IN_3_S)
    assert unpaused.status == "failed"
    assert unpaused.error_kind == "turn_timeout"


@pytest.mark.parametrize("resolution", ["answer", "decline"])
@pytest.mark.asyncio
async def test_resolving_the_question_mid_turn_restarts_the_clock(
    app, auth_headers, monkeypatch, resolution
):
    """Answered (or declined) through the operator route half a second into the turn: the clock
    runs again from there, so a prompt that needs 3 s is cut at about 1.5 s."""
    question_id = await _ask(app, f"run-{resolution}", f"{resolution}-asker")
    turn = asyncio.ensure_future(
        _turn(monkeypatch, f"run-{resolution}", _new_with() + _ANSWERS_IN_3_S)
    )
    await asyncio.sleep(0.5)
    url = f"/api/v1/projects/proj-test/questions/{question_id}"
    if resolution == "answer":
        resolved = await app.patch(url, headers=auth_headers, json={"answer": "blue"})
    else:
        resolved = await app.post(f"{url}/decline", headers=auth_headers)
    assert resolved.status_code == 200, resolved.text

    outcome = await turn
    assert outcome.status == "failed"
    assert outcome.error_kind == "turn_timeout"


@pytest.mark.asyncio
async def test_a_non_blocking_question_does_not_pause_the_clock(app, monkeypatch):
    await _ask(app, "run-notes", "noter", blocking=False)

    outcome = await _turn(monkeypatch, "run-notes", _new_with() + _ANSWERS_IN_3_S)
    assert outcome.status == "failed"
    assert outcome.error_kind == "turn_timeout"


def _ask_me_request():
    return {
        "server_request": {
            "id": 3,
            "method": "session/request_permission",
            "params": {
                "sessionId": SESSION_ID,
                "toolCall": {
                    "toolCallId": "call_ps_1",
                    "title": "Show the log",
                    "kind": "execute",
                    "rawInput": {"command": "git log -3", "commands": ["git log -3"]},
                },
                "options": _OPTIONS,
            },
        }
    }


@pytest.mark.asyncio
async def test_an_open_ask_me_card_pauses_the_clock(monkeypatch):
    async def request_approval(method, subject):
        await asyncio.sleep(3)
        return True

    start = _raw_event(
        "tool.execution_start",
        {"toolCallId": "call_ps_1", "toolName": "powershell", "arguments": {}},
    )
    # The judge is the turn's own work and took ~1.9 s here on a cold start: decided at once, so
    # only the card's wait is measured against the 1 s budget.
    monkeypatch.setattr(
        copilot_acp,
        "decide_permission",
        lambda *a, **k: {"outcome": copilot_acp.ASK_OPERATOR, "reason": "Ask me"},
    )
    monkeypatch.setattr(copilot_acp, "workspace_verdict", lambda *a, **k: {"allow": True})
    _fake, _events, outcome = await _drive(
        monkeypatch,
        _new_with() + [start, _ask_me_request(), _END_TURN],
        env={"AW_RUN_ID": "run-card"},
        permission_mode="manual",
        request_approval=request_approval,
        turn_timeout=1,
    )

    assert outcome.status == "completed", outcome.error
