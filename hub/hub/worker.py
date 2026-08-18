"""One-shot, out-of-band model invocations owned by the Hub.

A *worker* reads one deterministically-assembled prompt and returns one schema-validated answer.
It is not an agent turn: no streaming protocol, no tool server, no permission posture, no injected
project context. `conversation_titles.py` is the proto-worker this generalises — it already builds
a one-shot command, spawns it blocking with a timeout, parses, and never raises. What it does not
do, and what a checkpoint needs, is validate the answer against a schema and leave a durable record
of what the call cost.

**No `Run` row is recorded, deliberately** — the same trap `conversation_titles` documents.
`turn_scheduler.schedule_agent` and `trigger_agent_directly` both gate on
`Run.project_id == p, Run.agent == a, Run.status == "running"`, so a worker run recorded under an
agent's name makes that agent look busy and stalls its queue until the worker returns. A worker
produces no output rows, no timeline entry and no context cost; it is accounted for in
`worker_invocations` instead.

Three properties below were established by capturing real output from `claude` 2.1.221 and
`codex-cli` 0.146.0 rather than assumed, and each one is load-bearing:

* **`stdin` must be `DEVNULL`.** Given an open stdin, `codex exec` blocks on
  "Reading additional input from stdin..." indefinitely — observed hanging for over six minutes
  having written zero bytes. The timeout would eventually cover it, but only after burning the
  whole budget on a call that was never going to start.
* **stderr is not a failure signal.** A fully successful `codex exec` writes its banner, its
  workdir, its token count *and* transport errors ("ERROR ... 503 Service Unavailable", retried
  transparently) to stderr while exiting 0 with a correct answer on stdout. Only the exit code and
  the parse outcome decide whether a worker succeeded.
* **Both CLIs report usage in JSON mode**, so the answer is read out of a machine-readable
  envelope rather than scraped from prose. `claude --output-format json` returns a single object
  whose `result` is the answer text; `codex exec --json` returns JSONL whose `item.completed`
  carries the answer and whose `turn.completed` carries the usage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from .db.engine import async_session_factory
from .db.models import WorkerInvocation
from .model_catalog import get_provider
from .pty_runner import resolve_executable
from .subprocess_windows import no_console_kwargs
from .utils import short_id

logger = logging.getLogger(__name__)

# A worker reads a prompt and writes a paragraph or two of JSON. It is far heavier than a title
# (45s) and far lighter than an agent turn, and it runs out of band, so nothing is blocked while
# it thinks.
WORKER_TIMEOUT_SECONDS = 180

# Checkpoints can be requested in bursts — several conversations crossing a threshold at once,
# or an operator working through a backlog. The same reasoning as `MAX_CONCURRENT_TITLE_RUNS`:
# a bound keeps a burst from becoming a fork bomb without making a queue crawl.
MAX_CONCURRENT_WORKER_RUNS = 2
_gate = asyncio.Semaphore(MAX_CONCURRENT_WORKER_RUNS)

# CLIs with a supported one-shot invocation. Anything else is refused with a stated outcome
# rather than a guessed invocation — the line `runner_commands.build_command` and
# `conversation_titles.build_title_command` both hold.
SUPPORTED_CLIS = ("claude", "codex")

# Every way a worker call can end. "ok" is the only success; the rest are distinguished because
# "it failed" is not diagnosable — a timeout, a CLI that is not installed, and a model that
# answered in prose are three different problems with three different fixes.
OUTCOMES = (
    "ok",
    "unsupported_cli",
    "unknown_model",
    "spawn_failed",
    "nonzero_exit",
    "timeout",
    "unparseable",
    "schema_invalid",
)


@dataclass(frozen=True)
class WorkerUsage:
    """What one invocation consumed, normalised across providers. All fields optional.

    A provider that does not report a dimension leaves it None rather than reporting zero:
    "no reasoning tokens" and "this CLI does not tell us about reasoning tokens" are different
    facts, and only the second one should stop anybody trying to add up a bill.
    """

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cost_usd_micros: Optional[int] = None


@dataclass(frozen=True)
class WorkerResult:
    """The outcome of one invocation. Never carries an exception — see `run_worker`."""

    outcome: str
    parsed: Optional[BaseModel] = None
    answer_text: Optional[str] = None
    usage: WorkerUsage = field(default_factory=WorkerUsage)
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    invocation_id: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


def build_worker_command(*, cli: str, model: Optional[str], prompt: str) -> Optional[List[str]]:
    """The one-shot invocation in JSON mode, or None when this CLI has no supported one.

    Deliberately not `runner_commands.build_command`: that builds an *agent turn*. JSON mode is
    chosen over plain text for both CLIs because it is the only way the call reports what it cost,
    and because it puts the answer at a fixed address instead of at the end of a stream of prose.
    """
    if cli == "claude":
        cmd = ["claude", "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        return cmd + ["-p", prompt]
    if cli == "codex":
        cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]
        if model:
            cmd += ["--model", model]
        return cmd + [prompt]
    return None


def model_is_declared(cli: str, model: Optional[str]) -> bool:
    """Whether the catalog declares *model* for *cli*. No model at all is the CLI's own default.

    Checked before spawning because a mistyped model is a slow, billable failure otherwise: the
    CLI starts, contacts the provider, and fails somewhere the operator cannot see.

    Exact ids only, matching `runners._reject_undeclared_model` — deliberately *not* the alias
    resolution `context_window_for_model` does. A worker's model comes from a runner record that
    was validated by that rule at creation, and a worker that accepted models the runner registry
    refuses would be the laxer of two gates on the same value.
    """
    if model is None:
        return True
    provider = get_provider(cli)
    return provider is not None and provider.model(model) is not None


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """The last balanced **top-level** JSON object in *text*, or None.

    Models append rather than prepend: asked for JSON and nothing else, one that disobeys says
    "Here is the object:" first, or wraps it in a fenced block. Taking the last complete object
    handles both, and handles neither being present by returning None. Same instinct as
    `conversation_titles.title_from_output` taking the last non-empty line.

    "Top-level" is the whole difficulty. A scan that considers every `{` finds the *nested* ones
    too, and since they come later, "last" would return the innermost trailing object — for
    `{"a": {"b": 1}}` it would answer `{"b": 1}`. So a candidate that parses advances the cursor
    past its own end rather than to the next character.
    """
    decoder = json.JSONDecoder()
    found: Optional[Dict[str, Any]] = None
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            candidate, end = decoder.raw_decode(text, index)
        except ValueError:
            index += 1
            continue
        if isinstance(candidate, dict):
            found = candidate
            index = end
        else:  # pragma: no cover — raw_decode at a "{" yields a dict or raises
            index += 1
    return found


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_claude_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `claude --output-format json`.

    The envelope is one object whose `result` is the answer. `usage.input_tokens` counts only
    what was not served from cache — it read 2 input tokens against 47091 cache reads in the
    captured sample — so cache dimensions are carried separately rather than folded in.
    """
    envelope = extract_json_object(stdout)
    if envelope is None:
        return None, WorkerUsage(), "claude produced no JSON envelope"

    raw_usage = envelope.get("usage")
    usage = WorkerUsage()
    if isinstance(raw_usage, dict):
        cost = envelope.get("total_cost_usd")
        usage = WorkerUsage(
            input_tokens=_int_or_none(raw_usage.get("input_tokens")),
            output_tokens=_int_or_none(raw_usage.get("output_tokens")),
            cache_read_tokens=_int_or_none(raw_usage.get("cache_read_input_tokens")),
            cache_write_tokens=_int_or_none(raw_usage.get("cache_creation_input_tokens")),
            cost_usd_micros=round(cost * 1_000_000) if isinstance(cost, (int, float)) else None,
        )

    if envelope.get("is_error"):
        subtype = envelope.get("subtype") or envelope.get("api_error_status")
        return None, usage, f"claude reported an error: {subtype}"

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        return None, usage, "claude envelope carried no result text"
    return result, usage, None


def parse_codex_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `codex exec --json`.

    JSONL. The answer arrives as an `item.completed` whose item is an `agent_message`; usage
    arrives separately on `turn.completed`. Unparseable lines are skipped rather than failing the
    call — the stream is a event log, and a future CLI adding an event we do not understand is
    not a reason to discard an answer we do.
    """
    answer: Optional[str] = None
    usage = WorkerUsage()
    failure: Optional[str] = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue

        kind = event.get("type")
        if kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    answer = text
        elif kind == "turn.completed":
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = WorkerUsage(
                    input_tokens=_int_or_none(raw_usage.get("input_tokens")),
                    output_tokens=_int_or_none(raw_usage.get("output_tokens")),
                    cache_read_tokens=_int_or_none(raw_usage.get("cached_input_tokens")),
                    cache_write_tokens=_int_or_none(raw_usage.get("cache_write_input_tokens")),
                    reasoning_tokens=_int_or_none(raw_usage.get("reasoning_output_tokens")),
                )
        elif kind == "turn.failed":
            error = event.get("error")
            detail = error.get("message") if isinstance(error, dict) else None
            failure = f"codex turn failed: {detail or 'no detail'}"

    if failure is not None:
        return None, usage, failure
    if answer is None:
        return None, usage, "codex produced no agent message"
    return answer, usage, None


def parse_envelope(cli: str, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    if cli == "claude":
        return parse_claude_envelope(stdout)
    if cli == "codex":
        return parse_codex_envelope(stdout)
    return None, WorkerUsage(), f"no envelope parser for {cli!r}"


@dataclass(frozen=True)
class _Spawn:
    """What came back from the process itself, before anything is made of it."""

    outcome: str
    stdout: str = ""
    exit_code: Optional[int] = None
    error: Optional[str] = None


def _run_worker_process(cmd: List[str], cwd: Optional[str], timeout: int) -> _Spawn:
    """Blocking spawn. Classifies its own failure and never raises into the caller.

    `stdin=DEVNULL` is not incidental: `codex exec` given an open stdin blocks reading it forever
    (observed, >6 minutes, zero bytes written). stderr is captured but never consulted for
    success — a successful codex run writes transport errors there.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — argv list, no shell
            resolve_executable(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            **no_console_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return _Spawn("timeout", error=f"worker exceeded {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return _Spawn("spawn_failed", error=f"{type(exc).__name__}: {exc}")

    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "").strip().splitlines()
        detail = stderr_tail[-1] if stderr_tail else "no stderr"
        return _Spawn(
            "nonzero_exit",
            stdout=completed.stdout or "",
            exit_code=completed.returncode,
            error=f"exited {completed.returncode}: {detail}",
        )
    return _Spawn("ok", stdout=completed.stdout or "", exit_code=0)


async def _record(
    *,
    project_id: str,
    kind: str,
    prompt_version: str,
    runner_id: Optional[str],
    cli: str,
    model: Optional[str],
    conversation_id: Optional[str],
    result: WorkerResult,
) -> Optional[str]:
    """Persist the invocation. A recording failure never fails the call it is recording."""
    invocation_id = f"wrk-{short_id()}"
    try:
        async with async_session_factory() as db:
            db.add(
                WorkerInvocation(
                    id=invocation_id,
                    project_id=project_id,
                    kind=kind,
                    prompt_version=prompt_version,
                    runner_id=runner_id,
                    cli=cli,
                    model=model,
                    conversation_id=conversation_id,
                    outcome=result.outcome,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    cache_read_tokens=result.usage.cache_read_tokens,
                    cache_write_tokens=result.usage.cache_write_tokens,
                    reasoning_tokens=result.usage.reasoning_tokens,
                    cost_usd_micros=result.usage.cost_usd_micros,
                    error=result.error,
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — accounting must not take the work down with it
        logger.warning("worker invocation record failed", exc_info=True)
        return None
    return invocation_id


async def run_worker(
    *,
    project_id: str,
    kind: str,
    prompt: str,
    prompt_version: str,
    output_model: Type[BaseModel],
    cli: str,
    model: Optional[str] = None,
    runner_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    timeout_seconds: int = WORKER_TIMEOUT_SECONDS,
    cwd: Optional[str] = None,
) -> WorkerResult:
    """Run one worker invocation and record it. Returns an outcome; never raises.

    Callers pass primitives rather than a `Runner` row so the spawn does not hold a session open
    across a call that can take minutes. Every exit records an invocation, including the ones that
    never spawn — an operator asking why no checkpoint appeared should find the answer in one
    place regardless of how early it failed.
    """
    if cli not in SUPPORTED_CLIS:
        result = WorkerResult("unsupported_cli", error=f"{cli!r} has no one-shot invocation")
    elif not model_is_declared(cli, model):
        result = WorkerResult("unknown_model", error=f"{model!r} is not a model {cli!r} declares")
    else:
        cmd = build_worker_command(cli=cli, model=model, prompt=prompt)
        if cmd is None:  # pragma: no cover — SUPPORTED_CLIS and the builder agree
            result = WorkerResult("unsupported_cli", error=f"no command for {cli!r}")
        else:
            started = asyncio.get_running_loop().time()
            async with _gate:
                spawn = await asyncio.to_thread(_run_worker_process, cmd, cwd, timeout_seconds)
            duration_ms = round((asyncio.get_running_loop().time() - started) * 1000)
            result = _interpret(spawn, cli, output_model, duration_ms)

    invocation_id = await _record(
        project_id=project_id,
        kind=kind,
        prompt_version=prompt_version,
        runner_id=runner_id,
        cli=cli,
        model=model,
        conversation_id=conversation_id,
        result=result,
    )
    if not result.ok:
        logger.info("worker %s finished %s: %s", kind, result.outcome, result.error)
    return WorkerResult(
        outcome=result.outcome,
        parsed=result.parsed,
        answer_text=result.answer_text,
        usage=result.usage,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        error=result.error,
        invocation_id=invocation_id,
    )


def _interpret(
    spawn: _Spawn, cli: str, output_model: Type[BaseModel], duration_ms: int
) -> WorkerResult:
    """Turn a finished process into an outcome: envelope, then answer, then schema."""
    if spawn.outcome != "ok":
        return WorkerResult(
            spawn.outcome,
            exit_code=spawn.exit_code,
            duration_ms=duration_ms,
            error=spawn.error,
        )

    # The CLI succeeded, so usage is worth keeping even when the answer turns out unusable —
    # a worker that burned tokens producing prose still cost money.
    answer, usage, envelope_error = parse_envelope(cli, spawn.stdout)
    if envelope_error is not None:
        return WorkerResult(
            "unparseable",
            usage=usage,
            exit_code=spawn.exit_code,
            duration_ms=duration_ms,
            error=envelope_error,
        )

    payload = extract_json_object(answer or "")
    if payload is None:
        return WorkerResult(
            "unparseable",
            answer_text=answer,
            usage=usage,
            exit_code=spawn.exit_code,
            duration_ms=duration_ms,
            error="the answer contained no JSON object",
        )

    try:
        parsed = output_model.model_validate(payload)
    except ValidationError as exc:
        return WorkerResult(
            "schema_invalid",
            answer_text=answer,
            usage=usage,
            exit_code=spawn.exit_code,
            duration_ms=duration_ms,
            error=f"{exc.error_count()} schema violation(s): {exc.errors()[0].get('msg')}",
        )

    return WorkerResult(
        "ok",
        parsed=parsed,
        answer_text=answer,
        usage=usage,
        exit_code=spawn.exit_code,
        duration_ms=duration_ms,
    )
