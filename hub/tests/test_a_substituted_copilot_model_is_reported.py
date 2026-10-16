"""`a-substituted-copilot-model-is-reported`: a model or effort Copilot substitutes at session start
is reported before the first prompt (F662 item 3; D3 of the archived openspec
`the-copilot-catalog-matches-the-cli`).

Driven through `run_turn` with the fake session of `test_copilot_acp_run_turn.py`, so the check is
exercised where it fires: after agent selection, before `session/prompt`. The first case replays
the answers Copilot 1.0.91 gave on this machine, recorded without a prompt
(`fixtures/copilot_acp/session_start_1.0.91_grok-4.7_max.jsonl`): an Auto-only plan reports
`auto` for a requested `grok-4.7`, and the agent-selection answer carries the `model` option. The
concrete-substitute cases are shaped as the work PC's 1.0.89-1 `claude-opus-4.7` capture (result
keys `models`, `configOptions`, `modes`, `sessionId`; model `claude-sonnet-5`).
"""

import json
import pathlib

import pytest

from .test_copilot_acp_run_turn import (
    _END_TURN,
    AGENT_MODE_URI,
    AGENT_NAME,
    INIT_RESPONSE,
    SESSION_ID,
    _agent_option,
    _allow_all_option,
    _drive,
    _mode_option,
    _raw_event,
)

pytestmark = pytest.mark.asyncio

FIXTURE = (
    pathlib.Path(__file__).parent
    / "fixtures"
    / "copilot_acp"
    / "session_start_1.0.91_grok-4.7_max.jsonl"
)


def _captured():
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    by_method = {row["method"]: row["result"] for row in rows if "method" in row}
    return by_method["session/new"], by_method["session/set_config_option"]


def _model_option(current, values=("auto", "claude-sonnet-5", "claude-opus-5.5", "gpt-5-mini")):
    return {
        "type": "select",
        "id": "model",
        "name": "Model",
        "category": "model",
        "currentValue": current,
        "options": [{"value": v, "name": v, "description": v} for v in values],
    }


def _effort_option(current, values=("low", "medium", "high")):
    return {
        "type": "select",
        "id": "reasoning_effort",
        "name": "Reasoning effort",
        "currentValue": current,
        "options": [{"value": v, "name": v} for v in values],
    }


def _models(current, ids=("auto", "claude-sonnet-5", "claude-opus-5.5", "gpt-5-mini")):
    return {
        "availableModels": [{"modelId": m, "name": m, "description": m} for m in ids],
        "currentModelId": current,
    }


def _new(models, extra_options=()):
    """A `session/new` result in the order 1.0.89-1 sent its keys."""
    result = {}
    if models is not None:
        result["models"] = models
    result["configOptions"] = [
        _mode_option(),
        *extra_options,
        _agent_option(""),
        _allow_all_option(),
    ]
    result["modes"] = {"currentModeId": AGENT_MODE_URI}
    result["sessionId"] = SESSION_ID
    return result


def _selected(*extra_options):
    return {
        "configOptions": [
            _mode_option(),
            *extra_options,
            _agent_option(AGENT_NAME),
            _allow_all_option(),
        ]
    }


def _script(new_result, selected_result, *during_prompt):
    return [
        {"response": INIT_RESPONSE},
        {"response": new_result},
        {"response": selected_result},
        {"response": {}},  # session/set_mode
        *during_prompt,
        _END_TURN,
    ]


def _usage(used=1000, size=128000):
    return {
        "notification": "session/update",
        "params": {
            "sessionId": SESSION_ID,
            "update": {"sessionUpdate": "usage_update", "used": used, "size": size},
        },
    }


def _diagnostics(events, code):
    return [e.payload for e in events if e.kind == "diagnostic" and e.payload.get("code") == code]


async def _run_turn(monkeypatch, script, **overrides):
    holder = {}
    stamped = []
    usages = []

    from . import test_copilot_acp_run_turn as harness

    original = harness._FakeACPSession

    class _Recorded(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            holder["fake"] = self

    monkeypatch.setattr(harness, "_FakeACPSession", _Recorded)

    async def on_event(event):
        stamped.append((event, [method for method, _ in holder["fake"].sent_requests]))

    async def on_usage(sample):
        usages.append(sample)

    fake, _events, outcome = await _drive(
        monkeypatch, script, on_event=on_event, on_usage=on_usage, **overrides
    )
    events = [event for event, _ in stamped]
    return fake, events, stamped, usages, outcome


def _before_prompt(stamped, code):
    return [
        "session/prompt" not in sent
        for event, sent in stamped
        if event.kind == "diagnostic" and event.payload.get("code") == code
    ]


class TestTheCapturedAutoOnlyPlan:
    async def test_a_concrete_request_answered_auto_is_reported_once_before_the_prompt(
        self, monkeypatch
    ):
        new_result, selected_result = _captured()
        assert list(new_result) == ["models", "configOptions", "modes", "sessionId"]
        script = _script(
            new_result,
            selected_result,
            _raw_event(
                "session.auto_mode_resolved",
                {"chosenModel": "claude-sonnet-5", "availableModels": ["claude-sonnet-5"]},
            ),
            _usage(),
        )
        _fake, events, stamped, usages, outcome = await _run_turn(
            monkeypatch, script, model="grok-4.7", control_overrides={"effort": "max"}
        )

        substituted = _diagnostics(events, "copilot.model_substituted")
        assert len(substituted) == 1, substituted
        assert substituted[0]["severity"] == "info"
        assert substituted[0]["facts"] == {"requested": "grok-4.7", "resolved": "auto"}
        assert "grok-4.7" in substituted[0]["summary"]
        assert "Auto" in substituted[0]["summary"]
        assert _before_prompt(stamped, "copilot.model_substituted") == [True]
        # The plan offers no effort option under Auto: nothing to compare.
        assert _diagnostics(events, "copilot.effort_substituted") == []
        # Auto's own resolution still names the model for the meter.
        assert [u.model for u in usages] == ["claude-sonnet-5"]
        assert outcome.status == "completed"


class TestAConcreteSubstitute:
    async def test_the_agent_answers_model_is_the_one_reported(self, monkeypatch):
        script = _script(
            _new(_models("claude-sonnet-5"), [_model_option("claude-sonnet-5")]),
            _selected(_model_option("gpt-5-mini")),
            _raw_event("session.tools_updated", {"model": "gpt-5-mini"}),
            _usage(),
        )
        _fake, events, stamped, usages, outcome = await _run_turn(
            monkeypatch, script, model="claude-opus-4.7"
        )

        substituted = _diagnostics(events, "copilot.model_substituted")
        assert len(substituted) == 1, substituted
        assert substituted[0]["facts"] == {"requested": "claude-opus-4.7", "resolved": "gpt-5-mini"}
        summary = substituted[0]["summary"]
        assert "claude-sonnet-5" in summary and "claude-opus-5.5" in summary
        assert "auto" not in summary.split("allows")[-1]
        assert _before_prompt(stamped, "copilot.model_substituted") == [True]
        assert [u.model for u in usages] == ["gpt-5-mini"]
        assert outcome.status == "completed"

    async def test_an_agent_answer_without_a_model_option_falls_back_to_current_model_id(
        self, monkeypatch
    ):
        # The 1.0.88 agent answer carried no `model` option; `options` is replaced by it.
        script = _script(
            _new(_models("claude-sonnet-5"), [_model_option("claude-sonnet-5")]),
            _selected(),
            _usage(),
        )
        _fake, events, _stamped, usages, _outcome = await _run_turn(
            monkeypatch, script, model="claude-opus-4.7"
        )

        substituted = _diagnostics(events, "copilot.model_substituted")
        assert [d["facts"]["resolved"] for d in substituted] == ["claude-sonnet-5"]
        assert [u.model for u in usages] == ["claude-sonnet-5"]


class TestEffort:
    async def test_an_unsupported_effort_run_as_medium_is_reported(self, monkeypatch):
        script = _script(
            _new(_models("gpt-5-mini"), [_model_option("gpt-5-mini"), _effort_option("medium")]),
            _selected(_model_option("gpt-5-mini"), _effort_option("medium")),
        )
        _fake, events, stamped, _usages, _outcome = await _run_turn(
            monkeypatch, script, model="gpt-5-mini", control_overrides={"effort": "max"}
        )

        effort = _diagnostics(events, "copilot.effort_substituted")
        assert len(effort) == 1, effort
        assert effort[0]["severity"] == "info"
        assert effort[0]["facts"] == {
            "requested": "max",
            "resolved": "medium",
            "offered": ["low", "medium", "high"],
        }
        assert _before_prompt(stamped, "copilot.effort_substituted") == [True]
        assert _diagnostics(events, "copilot.model_substituted") == []

    async def test_a_matching_effort_is_not_reported(self, monkeypatch):
        script = _script(
            _new(_models("gpt-5.5"), [_model_option("gpt-5.5"), _effort_option("high")]),
            _selected(_model_option("gpt-5.5"), _effort_option("high")),
        )
        _fake, events, _stamped, _usages, _outcome = await _run_turn(
            monkeypatch, script, model="gpt-5.5", control_overrides={"effort": "high"}
        )
        assert _diagnostics(events, "copilot.effort_substituted") == []
        assert _diagnostics(events, "copilot.model_substituted") == []


class TestNothingToReport:
    @pytest.mark.parametrize(
        ("model", "new_result", "selected_result"),
        [
            # Auto: currentModelId is the default, not Auto's choice.
            ("auto", _new(_models("claude-sonnet-5")), _selected(_model_option("claude-sonnet-5"))),
            (None, _new(_models("claude-sonnet-5")), _selected(_model_option("claude-sonnet-5"))),
            # A match.
            (
                "claude-sonnet-5",
                _new(_models("claude-sonnet-5")),
                _selected(_model_option("claude-sonnet-5")),
            ),
            # The 1.0.88 shape: no models block, no model option.
            ("claude-opus-4.7", _new(None), _selected()),
            # Mistyped fields.
            ("claude-opus-4.7", _new("claude-sonnet-5"), _selected(_model_option(5))),
            ("claude-opus-4.7", _new({"currentModelId": ["x"]}), _selected()),
        ],
    )
    async def test_no_diagnostic_and_the_turn_completes(
        self, monkeypatch, model, new_result, selected_result
    ):
        script = _script(new_result, selected_result)
        _fake, events, _stamped, _usages, outcome = await _run_turn(
            monkeypatch, script, model=model, control_overrides={"effort": "max"}
        )
        assert _diagnostics(events, "copilot.model_substituted") == []
        assert _diagnostics(events, "copilot.effort_substituted") == []
        assert outcome.status == "completed"
