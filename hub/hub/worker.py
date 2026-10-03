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
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from .db.engine import async_session_factory
from .db.models import Runner, WorkerInvocation
from .file_mentions import restore_file_mentions
from .model_catalog import get_provider, undeclared_model_reason
from .pty_runner import resolve_executable
from .runner_adapters import get_adapter
from .runner_adapters.claude import parse_claude_envelope  # noqa: F401
from .runner_adapters.codex import parse_codex_envelope  # noqa: F401
from .runner_adapters.copilot import (  # noqa: F401
    COPILOT_ONE_SHOT_FLAGS,
    copilot_one_shot_command,
    copilot_one_shot_env,
    parse_copilot_envelope,
)
from .runner_adapters.one_shot import WorkerUsage, _int_or_none, extract_json_object  # noqa: F401
from .runner_provider import (
    DAMAGED_PROVIDER_REASON,
    damaged_provider,
    has_provider,
    is_provider_model,
    provider_model_problem,
    runner_probe_config,
)
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


def one_shot_env(cli: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    """The environment a one-shot spawn of *cli* gets: its adapter's, or None (inherit the Hub's).

    `config` is the runner's (`runner_provider.runner_probe_config`, with `model` the one the
    spawn names), so a provider runner's one-shot gets its provider's variables (slice 5 D7).
    """
    adapter = get_adapter(cli)
    return adapter.one_shot_env("worker", config) if adapter is not None else None


async def _runner_config(runner_id: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """The spawning runner's config for `one_shot_env`, read from its row in a session of its own
    that is closed before the spawn. `{}` for no runner id, or a row that no longer exists."""
    if not runner_id:
        return {}
    async with async_session_factory() as db:
        runner = await db.get(Runner, runner_id)
    if runner is None:
        return {}
    return {**runner_probe_config(runner), "model": model}


def build_worker_command(
    *,
    cli: str,
    model: Optional[str],
    prompt: str,
    output_schema_path: Optional[str] = None,
) -> Optional[List[str]]:
    """The one-shot invocation in JSON mode, or None when this CLI has no supported one.

    Deliberately not `runner_commands.build_command`: that builds an *agent turn*. JSON mode is
    chosen over plain text for both CLIs because it is the only way the call reports what it cost,
    and because it puts the answer at a fixed address instead of at the end of a stream of prose.

    Every runner goes through its adapter's `one_shot` (design D8).
    """
    adapter = get_adapter(cli)
    if adapter is not None:
        return adapter.one_shot(
            "worker", model=model, prompt=prompt, output_schema_path=output_schema_path
        )
    return None


def model_is_declared(cli: str, model: Optional[str]) -> bool:
    """Whether the catalog declares *model* for *cli*. No model at all is the CLI's own default.

    Checked before spawning because a mistyped model is a slow, billable failure otherwise: the
    CLI starts, contacts the provider, and fails somewhere the operator cannot see.

    A declared id or a declared alias, matching `runners._reject_undeclared_model` exactly (both
    go through `ProviderDescriptor.model`). A worker's model comes from a runner record that was
    validated by that same rule at creation, and a worker that accepted a value the runner
    registry refuses — or refused one it accepts — would be two gates disagreeing on one value.
    """
    if model is None:
        return True
    provider = get_provider(cli)
    return provider is not None and provider.model(model) is not None


def strict_output_schema(output_model: Type[BaseModel]) -> Dict[str, Any]:
    """A Pydantic schema tightened to the contract Codex structured output accepts.

    Pydantic permits undeclared properties and omits defaulted fields from ``required``. The
    Responses structured-output API deliberately accepts neither ambiguity. Requiring the
    defaulted list fields is safe: the model must return them, while validation still accepts the
    same values it did before.
    """
    schema = output_model.model_json_schema()

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for value in node:
                tighten(value)

    tighten(schema)
    return schema


def parse_envelope(cli: str, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """Thin wrapper over `get_adapter(cli).parse_one_shot` (design D8)."""
    adapter = get_adapter(cli)
    if adapter is not None:
        return adapter.parse_one_shot(stdout)
    return None, WorkerUsage(), f"no envelope parser for {cli!r}"


@dataclass(frozen=True)
class _Spawn:
    """What came back from the process itself, before anything is made of it."""

    outcome: str
    stdout: str = ""
    exit_code: Optional[int] = None
    error: Optional[str] = None


def _run_worker_process(
    cmd: List[str], cwd: Optional[str], timeout: int, env: Optional[Dict[str, str]] = None
) -> _Spawn:
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
            # None inherits the Hub's environment, as every spawn did; Copilot's is filtered.
            env=env,
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
                    ai_nano_aiu=result.usage.ai_nano_aiu,
                    premium_requests=result.usage.premium_requests,
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
    try:
        config: Optional[Dict[str, Any]] = await _runner_config(runner_id, model)
    except Exception:  # noqa: BLE001 — this function never raises; the row decides the env
        logger.warning("worker could not read runner %s", runner_id, exc_info=True)
        config = None
    provider_config = (config or {}).get("provider_config")
    if config is None:
        result = WorkerResult("spawn_failed", error="the runner's record could not be read")
    elif damaged_provider(provider_config):
        # No launchability check precedes a one-shot, so this is it: a damaged provider is not
        # quietly run on the GitHub subscription (slice 5 D7).
        result = WorkerResult("spawn_failed", error=DAMAGED_PROVIDER_REASON)
    elif has_provider(provider_config) and not is_provider_model(model):
        # A provider runner's model is a Claude API id the `copilot` catalog does not declare: the
        # runner registry judges it by the provider rule, and so does this.
        result = WorkerResult("unknown_model", error=provider_model_problem(model))
    elif not has_provider(provider_config) and not model_is_declared(cli, model):
        result = WorkerResult("unknown_model", error=undeclared_model_reason(cli, model))
    else:
        adapter = get_adapter(cli)
        worker_dir_context = tempfile.TemporaryDirectory(prefix="agentweave-worker-")
        worker_dir = worker_dir_context.name
        schema_path = None
        if adapter is not None and adapter.one_shot_takes_schema:
            schema_path = os.path.join(worker_dir, "output-schema.json")
            with open(schema_path, "w", encoding="utf-8") as schema_file:
                json.dump(strict_output_schema(output_model), schema_file)
        cmd: Optional[List[str]] = None
        env: Optional[Dict[str, str]] = None
        unspawnable: Optional[WorkerResult] = None
        try:
            cmd = build_worker_command(
                cli=cli,
                model=model,
                prompt=prompt,
                output_schema_path=schema_path,
            )
            env = one_shot_env(cli, config)
        except FileNotFoundError as exc:
            # Copilot's executable cannot be resolved (D14, R3). Not `unsupported_cli`, which is
            # what a `None` command means: the CLI is supported and could not be spawned.
            unspawnable = WorkerResult("spawn_failed", error=str(exc))
        if unspawnable is not None:
            result = unspawnable
        elif cmd is None:  # a CLI with no adapter and no Copilot branch (D8)
            result = WorkerResult("unsupported_cli", error=f"no command for {cli!r}")
        else:
            started = asyncio.get_running_loop().time()
            async with _gate:
                spawn = await asyncio.to_thread(
                    _run_worker_process, cmd, cwd or worker_dir, timeout_seconds, env
                )
            duration_ms = round((asyncio.get_running_loop().time() - started) * 1000)
            result = _interpret(spawn, cli, output_model, duration_ms)
        worker_dir_context.cleanup()

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


def _restore_mentions(value: Any) -> Any:
    """`restore_file_mentions` over every string in a parsed answer, and nothing else (F409, D7).

    The prompt was neutralised on the way in, so a model that echoes a path puts a backslash before the at-sign; the
    stored record is the operator's text, so the escape comes off before validation. Numbers,
    booleans and `null` pass through untouched.
    """
    if isinstance(value, str):
        return restore_file_mentions(value)
    if isinstance(value, list):
        return [_restore_mentions(item) for item in value]
    if isinstance(value, dict):
        return {key: _restore_mentions(item) for key, item in value.items()}
    return value


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
        parsed = output_model.model_validate(_restore_mentions(payload))
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
