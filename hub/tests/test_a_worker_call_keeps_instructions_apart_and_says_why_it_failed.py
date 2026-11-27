"""A worker call: its instructions in the system prompt, its answer in the schema's shape, and a
failure said in the CLI's own words.

The build retrospective of `spdoc-857c9e7dd18e` failed twice on 2026-11-27 as "exited 1: no
stderr": `claude -p` had refused an oversized prompt, writing why into its JSON envelope on stdout
and nothing to stderr, so the Hub kept nothing of the reason. `PROMPT_TOO_LONG` below is that
envelope as `claude` 2.1.301 printed it for the retrospective's first part, cut to the fields read.
"""

from __future__ import annotations

import json
import subprocess

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import WorkerInvocation
from hub.runner_adapters.claude import (
    WORKER_SYSTEM_PROMPT,
    claude_one_shot_failure,
    parse_claude_envelope,
)
from hub.worker import build_worker_command, run_worker, strict_output_schema

PROJECT = "proj-worker-call"

PROMPT_TOO_LONG = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": 400,
        "terminal_reason": "prompt_too_long",
        "duration_ms": 659,
        "total_cost_usd": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "result": (
            "Prompt is too long · the request is ~1006791 tokens (limit 1000000) but this "
            "conversation is only ~573103 tokens — the rest is system prompt, tool definitions, "
            "and attachment content. A single-exchange conversation cannot be compacted; reduce "
            "attached files/tools or start with less context."
        ),
    }
)
#: A `--json-schema` call's envelope (claude 2.1.301, 2026-11-27): the answer is `structured_output`.
STRUCTURED = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 2,
        "result": "Here it is.",
        "structured_output": {"verdict": "blue", "sure": True},
        "usage": {"input_tokens": 2, "output_tokens": 9, "cache_creation_input_tokens": 1097},
        "total_cost_usd": 0.0002456,
    }
)


class Verdict(BaseModel):
    verdict: str
    sure: bool = False


def _patch(monkeypatch, *, stdout: str, returncode: int = 0, seen=None):
    def fake_run(cmd, **kwargs):
        if seen is not None:
            seen["cmd"] = list(cmd)
            seen["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)


async def _run(**overrides):
    kwargs = {
        "project_id": PROJECT,
        "kind": "build-retrospective",
        "prompt": "the data",
        "prompt_version": "v1",
        "output_model": Verdict,
        "cli": "claude",
        "model": "claude-sonnet-5-5",
        "initiator": "operator",
    }
    kwargs.update(overrides)
    return await run_worker(**kwargs)


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1]


def test_an_oversized_prompt_is_named_with_the_providers_own_count():
    failure = claude_one_shot_failure(PROMPT_TOO_LONG)
    assert failure is not None and failure.too_large
    assert (failure.prompt_tokens, failure.limit_tokens) == (1_006_791, 1_000_000)
    assert failure.reason.startswith("Prompt is too long")


def test_an_envelope_that_is_no_error_is_no_failure():
    assert claude_one_shot_failure(STRUCTURED) is None
    assert claude_one_shot_failure("") is None


def test_a_structured_answer_is_the_answer():
    answer, usage, error = parse_claude_envelope(STRUCTURED)
    assert error is None
    assert json.loads(answer) == {"verdict": "blue", "sure": True}
    assert usage.cache_write_tokens == 1097


def test_an_error_envelope_says_what_the_cli_said():
    _answer, _usage, error = parse_claude_envelope(PROMPT_TOO_LONG)
    assert "Prompt is too long" in error


def test_a_worker_brings_its_own_system_prompt_and_the_answers_schema():
    schema = strict_output_schema(Verdict)
    cmd = build_worker_command(
        cli="claude", model=None, prompt="data", system="Judge the sky.", schema=schema
    )
    assert _flag(cmd, "--system-prompt") == "Judge the sky."
    assert json.loads(_flag(cmd, "--json-schema")) == schema
    assert _flag(cmd, "--setting-sources") == ""
    assert cmd.stdin == "data"
    # With none of its own, a worker still does not run under the coding agent's prompt.
    bare = build_worker_command(cli="claude", model=None, prompt="data")
    assert _flag(bare, "--system-prompt") == WORKER_SYSTEM_PROMPT
    assert "--json-schema" not in bare


def test_a_system_prompt_too_long_for_the_command_line_goes_before_the_data():
    long = "x" * 20_000
    cmd = build_worker_command(cli="claude", model=None, prompt="data", system=long)
    assert _flag(cmd, "--system-prompt") == WORKER_SYSTEM_PROMPT
    assert cmd.stdin == f"{long}\n\ndata"


@pytest.mark.parametrize("cli", ["codex", "copilot"])
def test_a_cli_with_no_system_channel_reads_the_instructions_first(cli, monkeypatch):
    monkeypatch.setattr(
        "hub.runner_adapters.copilot.copilot_one_shot_command",
        lambda *, prompt, model, custom_instructions: ["copilot", "-p", prompt],
    )
    cmd = build_worker_command(cli=cli, model=None, prompt="data", system="Judge the sky.")
    assert "Judge the sky.\n\ndata" in cmd


@pytest.mark.asyncio
async def test_a_refused_prompt_is_recorded_in_the_clis_words(app, monkeypatch):
    _patch(monkeypatch, stdout=PROMPT_TOO_LONG, returncode=1)
    result = await _run()

    assert result.outcome == "nonzero_exit"
    assert result.failure is not None and result.failure.too_large
    assert result.failure.prompt_tokens == 1_006_791
    assert "no stderr" not in result.error
    assert result.error.startswith("exited 1: Prompt is too long")
    async with async_session_factory() as db:
        row = (await db.execute(select(WorkerInvocation))).scalars().one()
    assert row.error == result.error


@pytest.mark.asyncio
async def test_a_worker_call_sends_its_instructions_and_schema(app, monkeypatch):
    seen: dict = {}
    _patch(monkeypatch, stdout=STRUCTURED, seen=seen)
    result = await _run(system="Judge the sky.")

    assert result.ok and result.parsed == Verdict(verdict="blue", sure=True)
    assert _flag(seen["cmd"], "--system-prompt") == "Judge the sky."
    assert json.loads(_flag(seen["cmd"], "--json-schema")) == strict_output_schema(Verdict)
    assert seen["input"] == "the data"
