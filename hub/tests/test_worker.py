"""The Worker: one-shot, out-of-band, schema-validated model calls.

Section 4 of 2026-08-07-conversation-handoff-rework.

**The envelope samples below are captured, not invented.** They are the real stdout of
`claude` 2.1.221 (`--output-format json`) and `codex-cli` 0.146.0 (`exec --json`), recorded
before the parser was written. That ordering matters: the previous attempt at reading these
CLIs — `conversation_titles.title_from_output` — documents its heuristic with a premise that is
no longer true ("Codex prints progress and configuration ahead of its answer"), because in 0.146.0
all of that goes to *stderr* and stdout carries one clean line. A parser written against an
imagined shape passes its own tests and fails on contact.
"""

import subprocess

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import WORKER_OUTCOMES, WorkerInvocation
from hub.worker import (
    OUTCOMES,
    _run_worker_process,
    build_worker_command,
    extract_json_object,
    model_is_declared,
    parse_claude_envelope,
    parse_codex_envelope,
    run_worker,
)

PROJECT = "proj-test"


class Answer(BaseModel):
    objective: str
    state: str
    confidence: float


# Captured verbatim. Kept whole — including `modelUsage` and `iterations`, which the parser never
# reads — because ignoring unknown fields is part of what is being asserted.
CLAUDE_STDOUT = r"""{"is_error":false,"duration_api_ms":4797,"num_turns":1,"stop_reason":"end_turn","session_id":"ffe44ab2-292c-4e8c-9bd2-6035d01b0db0","total_cost_usd":0.015330299999999998,"usage":{"input_tokens":2,"cache_creation_input_tokens":0,"cache_read_input_tokens":47091,"output_tokens":38,"service_tier":"standard","inference_geo":"not_available","iterations":[{"input_tokens":2,"output_tokens":38,"cache_read_input_tokens":47091,"type":"message"}],"speed":"standard"},"modelUsage":{"claude-sonnet-5":{"inputTokens":2,"outputTokens":38,"contextWindow":1000000,"canonicalModel":"claude-sonnet-5","provider":"firstParty"}},"permission_denials":[],"terminal_reason":"completed","subtype":"success","api_error_status":null,"result":"{\"objective\": \"test of one-shot invocation\", \"state\": \"acknowledged\", \"confidence\": 1.0}","ttft_ms":3405,"type":"result","duration_ms":3412,"uuid":"ba76ab49-2bb4-414f-adcc-5f18c295065c"}"""  # noqa: E501

# Captured verbatim, all four events.
CODEX_STDOUT = r"""{"type":"thread.started","thread_id":"019fe277-4166-7351-b25b-e49932218098"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"{\"objective\":\"Test one-shot invocation\",\"state\":\"completed\",\"confidence\":1}"}}
{"type":"turn.completed","usage":{"input_tokens":17590,"cached_input_tokens":11008,"cache_write_input_tokens":0,"output_tokens":20,"reasoning_output_tokens":0}}"""  # noqa: E501

# Captured verbatim from a run that exited 0 with a correct answer. Every line of it is on
# stderr, including one that says ERROR.
CODEX_STDERR = """OpenAI Codex v0.146.0
--------
workdir: C:\\Users\\huida\\Documents\\projects\\AgentWeave\\testbed
model: gpt-5.6-sol
--------
2026-08-08T17:34:00.750985Z ERROR codex_api::endpoint::responses_websocket: \
failed to connect to websocket: HTTP error: 503 Service Unavailable
tokens used
6,602"""


# --------------------------------------------------------------------------- command building


def test_the_claude_command_asks_for_json_and_is_not_an_agent_turn():
    cmd = build_worker_command(cli="claude", model="claude-haiku-4-5-20251001", prompt="hi")
    assert cmd[:3] == ["claude", "--output-format", "json"]
    assert cmd[-2:] == ["-p", "hi"]
    assert "--model" in cmd
    # The spec is explicit: a worker invocation carries no streaming protocol, no tool server,
    # no permission posture, no injected context. Pin it, because the tempting fix for any
    # future worker problem is to borrow a flag from `build_command`.
    for forbidden in ("--permission-mode", "--mcp-config", "--allowedTools", "stream-json"):
        assert forbidden not in cmd


def test_the_codex_command_asks_for_jsonl_and_passes_the_prompt_positionally():
    cmd = build_worker_command(cli="codex", model="gpt-5.6-sol", prompt="hi")
    assert cmd[:4] == ["codex", "exec", "--skip-git-repo-check", "--json"]
    assert cmd[-1] == "hi"
    # `-p` is `--profile` for codex, not the prompt. Passing it here would silently look for a
    # config profile named after the entire prompt.
    assert "-p" not in cmd


def test_an_unsupported_cli_gets_no_guessed_invocation():
    assert build_worker_command(cli="gemini", model=None, prompt="hi") is None


def test_a_model_is_checked_against_the_catalog_before_anything_is_spawned():
    assert model_is_declared("claude", "claude-haiku-4-5-20251001")
    assert model_is_declared("codex", "gpt-5.6-sol")
    assert model_is_declared("claude", None)  # the CLI's own default
    assert not model_is_declared("claude", "gpt-5.6-sol")  # a codex model on the claude CLI
    assert not model_is_declared("claude", "a-model-nobody-declares")
    # Exact ids only, matching `runners._reject_undeclared_model`. The alias resolution
    # `context_window_for_model` performs is for samples reporting whatever the provider called
    # the model; this is a gate on an operator's choice, and the runner registry already refuses
    # aliases at the point that choice is made.
    assert not model_is_declared("claude", "haiku")


# --------------------------------------------------------------------------- JSON extraction


def test_the_last_complete_json_object_wins():
    """Models append rather than prepend: a disobedient one narrates first, or fences."""
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('Here is the object:\n{"a": 1}\n') == {"a": 1}
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('{"a": 1}\nOn reflection:\n{"a": 2}') == {"a": 2}
    # Nested objects are not candidates. A scan that treated every `{` as a start would return
    # the innermost trailing one — this is the bug the real claude envelope, whose `usage`,
    # `iterations` and `modelUsage` are all nested objects, caught immediately.
    assert extract_json_object('{"a": {"b": 1}}') == {"a": {"b": 1}}
    assert extract_json_object('{"a": {"b": 1}}\ntrailing prose') == {"a": {"b": 1}}
    assert extract_json_object("no json at all") is None
    assert extract_json_object("") is None
    # A bare array is not an object, and the schema layer expects an object.
    assert extract_json_object("[1, 2, 3]") is None


# --------------------------------------------------------------------------- envelope parsing


def test_the_real_claude_envelope_yields_its_answer_and_its_usage():
    answer, usage, error = parse_claude_envelope(CLAUDE_STDOUT)
    assert error is None
    assert extract_json_object(answer) == {
        "objective": "test of one-shot invocation",
        "state": "acknowledged",
        "confidence": 1.0,
    }
    # `input_tokens` counts only what was *not* served from cache — 2, against 47091 cache reads.
    # Folding them together would misreport the call by four orders of magnitude.
    assert usage.input_tokens == 2
    assert usage.cache_read_tokens == 47091
    assert usage.output_tokens == 38
    assert usage.cost_usd_micros == 15330


def test_a_claude_error_envelope_is_an_error_but_still_reports_what_it_cost():
    stdout = (
        '{"is_error":true,"subtype":"error_max_turns","usage":{"input_tokens":5,'
        '"output_tokens":0},"result":null}'
    )
    answer, usage, error = parse_claude_envelope(stdout)
    assert answer is None
    assert "error_max_turns" in error
    assert usage.input_tokens == 5


def test_the_real_codex_jsonl_yields_its_answer_and_its_usage():
    answer, usage, error = parse_codex_envelope(CODEX_STDOUT)
    assert error is None
    assert extract_json_object(answer) == {
        "objective": "Test one-shot invocation",
        "state": "completed",
        "confidence": 1,
    }
    assert usage.input_tokens == 17590
    assert usage.cache_read_tokens == 11008
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 0


def test_an_unrecognised_codex_event_does_not_discard_a_good_answer():
    """The stream is an event log. A future CLI adding an event is not a reason to fail."""
    stdout = CODEX_STDOUT + '\n{"type":"something.new","payload":{"whatever":true}}\nnot json'
    answer, _, error = parse_codex_envelope(stdout)
    assert error is None
    assert answer is not None


def test_codex_with_no_agent_message_is_an_error_not_a_silent_empty():
    answer, _, error = parse_codex_envelope('{"type":"turn.started"}')
    assert answer is None
    assert "no agent message" in error


# --------------------------------------------------------------------------- the spawn


def test_the_spawn_closes_stdin(monkeypatch):
    """Load-bearing, and discovered the hard way: given an open stdin, `codex exec` blocks on
    "Reading additional input from stdin..." indefinitely — observed for over six minutes with
    zero bytes written. Without this the timeout is the only thing that ends the call, and it
    ends it having achieved nothing."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    _run_worker_process(["codex", "exec"], None, 5)
    assert seen["stdin"] is subprocess.DEVNULL


def test_stderr_is_never_a_failure_signal(monkeypatch):
    """A successful codex run writes its banner, its token count *and* transport errors to
    stderr while exiting 0. Only the exit code and the parse decide success."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=CODEX_STDOUT, stderr=CODEX_STDERR)

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    spawn = _run_worker_process(["codex", "exec"], None, 5)
    assert spawn.outcome == "ok"
    assert "ERROR" in CODEX_STDERR  # the trap is real, and the parser walked past it


# --------------------------------------------------------------------------- outcomes, end to end


def _patch_spawn(monkeypatch, *, stdout="", returncode=0, stderr="", raises=None):
    def fake_run(cmd, **kwargs):
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)


async def _invocations():
    async with async_session_factory() as db:
        rows = (await db.execute(select(WorkerInvocation))).scalars().all()
        return list(rows)


async def _run(**overrides):
    kwargs = {
        "project_id": PROJECT,
        "kind": "checkpoint",
        "prompt": "Summarise.",
        "prompt_version": "checkpoint/1",
        "output_model": Answer,
        "cli": "claude",
        "model": "claude-haiku-4-5-20251001",
        "runner_id": "run-abc",
        "conversation_id": "conv-1",
    }
    kwargs.update(overrides)
    return await run_worker(**kwargs)


@pytest.mark.asyncio
async def test_a_good_answer_is_parsed_validated_and_recorded(app, monkeypatch):
    _patch_spawn(monkeypatch, stdout=CLAUDE_STDOUT)
    result = await _run()

    assert result.ok
    assert isinstance(result.parsed, Answer)
    assert result.parsed.state == "acknowledged"
    assert result.usage.output_tokens == 38
    assert result.duration_ms is not None

    rows = await _invocations()
    assert len(rows) == 1
    row = rows[0]
    # Task 4.4's list, in full.
    assert row.prompt_version == "checkpoint/1"
    assert row.runner_id == "run-abc"
    assert row.model == "claude-haiku-4-5-20251001"
    assert row.cli == "claude"
    assert row.kind == "checkpoint"
    assert row.conversation_id == "conv-1"
    assert row.outcome == "ok"
    assert row.duration_ms is not None
    assert row.output_tokens == 38
    assert row.cost_usd_micros == 15330
    assert row.error is None
    assert result.invocation_id == row.id


@pytest.mark.asyncio
async def test_a_cli_that_fails_is_recorded_not_raised(app, monkeypatch):
    _patch_spawn(monkeypatch, returncode=2, stderr="claude: command failed")
    result = await _run()
    assert result.outcome == "nonzero_exit"
    assert result.exit_code == 2
    assert "command failed" in result.error
    assert (await _invocations())[0].outcome == "nonzero_exit"


@pytest.mark.asyncio
async def test_a_cli_that_times_out_is_recorded_not_raised(app, monkeypatch):
    _patch_spawn(monkeypatch, raises=subprocess.TimeoutExpired(cmd="claude", timeout=180))
    result = await _run()
    assert result.outcome == "timeout"
    assert "180s" in result.error
    assert (await _invocations())[0].outcome == "timeout"


@pytest.mark.asyncio
async def test_a_cli_that_cannot_be_launched_is_recorded_not_raised(app, monkeypatch):
    _patch_spawn(monkeypatch, raises=OSError("No such file or directory: 'claude'"))
    result = await _run()
    assert result.outcome == "spawn_failed"
    assert "OSError" in result.error
    assert (await _invocations())[0].outcome == "spawn_failed"


@pytest.mark.asyncio
async def test_an_answer_that_is_prose_is_unparseable_and_still_billed(app, monkeypatch):
    """The model ignored the instruction and wrote a paragraph. The call still cost money, so
    usage is kept even though the answer is useless."""
    prose = CLAUDE_STDOUT.replace(
        r"{\"objective\": \"test of one-shot invocation\", \"state\": \"acknowledged\", "
        r"\"confidence\": 1.0}",
        "Sure! Here is a summary of the conversation.",
    )
    _patch_spawn(monkeypatch, stdout=prose)
    result = await _run()
    assert result.outcome == "unparseable"
    assert result.usage.output_tokens == 38
    row = (await _invocations())[0]
    assert row.outcome == "unparseable"
    assert row.output_tokens == 38


@pytest.mark.asyncio
async def test_an_envelope_that_is_not_json_at_all_is_unparseable(app, monkeypatch):
    _patch_spawn(monkeypatch, stdout="claude: unrecognised option '--output-format'")
    result = await _run()
    assert result.outcome == "unparseable"
    assert (await _invocations())[0].outcome == "unparseable"


@pytest.mark.asyncio
async def test_an_answer_that_misses_the_schema_is_distinguished_from_prose(app, monkeypatch):
    """Valid JSON, wrong shape. A different problem from prose, and a different fix — so it
    gets its own outcome rather than being folded into `unparseable`."""
    wrong = CLAUDE_STDOUT.replace(
        r"{\"objective\": \"test of one-shot invocation\", \"state\": \"acknowledged\", "
        r"\"confidence\": 1.0}",
        r"{\"objective\": \"only this one\"}",
    )
    _patch_spawn(monkeypatch, stdout=wrong)
    result = await _run()
    assert result.outcome == "schema_invalid"
    assert result.parsed is None
    assert (await _invocations())[0].outcome == "schema_invalid"


@pytest.mark.asyncio
async def test_an_unsupported_cli_is_recorded_without_spawning(app, monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover — the point is that it is not reached
        raise AssertionError("a worker must not spawn an unsupported CLI")

    monkeypatch.setattr(subprocess, "run", explode)
    result = await _run(cli="gemini", model=None)
    assert result.outcome == "unsupported_cli"
    assert (await _invocations())[0].outcome == "unsupported_cli"


@pytest.mark.asyncio
async def test_an_undeclared_model_is_refused_before_it_is_billed(app, monkeypatch):
    """A mistyped model is otherwise a slow, billable failure: the CLI starts, contacts the
    provider, and fails somewhere the operator never looks."""

    def explode(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("a worker must not spawn an undeclared model")

    monkeypatch.setattr(subprocess, "run", explode)
    result = await _run(model="gpt-5.6-sol")  # a codex model, on the claude CLI
    assert result.outcome == "unknown_model"
    assert (await _invocations())[0].outcome == "unknown_model"


@pytest.mark.asyncio
async def test_no_run_row_is_created(app, monkeypatch):
    """The trap `conversation_titles` documents: `turn_scheduler.schedule_agent` and
    `trigger_agent_directly` gate on a running `Run` for the agent, so a worker recorded as a run
    would make that agent look busy and stall its queue until the worker returned."""
    from hub.db.models import Run

    _patch_spawn(monkeypatch, stdout=CLAUDE_STDOUT)
    await _run()
    async with async_session_factory() as db:
        assert (await db.execute(select(Run))).scalars().all() == []


def test_the_outcome_vocabulary_cannot_drift_from_the_check_constraint():
    """`worker.OUTCOMES` and the column constraint are written in two files; a new outcome added
    to one and not the other fails at INSERT time in production and nowhere in the tests."""
    assert tuple(OUTCOMES) == tuple(WORKER_OUTCOMES)
