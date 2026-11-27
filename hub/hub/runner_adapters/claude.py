"""The Claude Code adapter (design D1/D3): one stream transport, no RPC transport.

`ClaudeStreamTransport` delegates argv construction and line parsing to `runner_commands` and
`runner_parsing`, which keep the builders and parsers themselves (design D1, "Why the existing
modules stay"). `one_shot`/`parse_one_shot` are copied here from `worker.py`'s today's Claude
branches, **by copy, not cut** — `worker.py` and `conversation_titles.py` keep their own originals
until task 3.5 re-points them at the adapter and deletes them (same precedent as task 2.1's
`one_shot.py`), so this file lands without moving any existing caller.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from .. import claude_signin, runner_commands
from ..file_mentions import neutralise_file_mentions
from ..model_catalog import render_control_args
from ..runner_parsing import AccountingSample, ParsedLine, parse_claude_line
from ..workspace_writes import CLAUDE_WRITE_TOOLS
from .base import (
    AccessAxes,
    LaunchRequest,
    LaunchVerdict,
    RunnerAdapter,
    StreamTransport,
    probe_binary,
)
from .one_shot import (
    OneShotCommand,
    OneShotFailure,
    WorkerUsage,
    _int_or_none,
    extract_json_object,
    with_system,
)


def parse_claude_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `claude --output-format json` (copied from `worker.py`,
    design D8: `worker.py:142-146`'s builder and `:297-327`'s parser).

    A call given `--json-schema` answers in `structured_output`, already validated against it by
    the CLI; that object is the answer, re-serialised, and `result` is only read without one."""
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
        return None, usage, f"claude reported an error: {_error_of(envelope)}"

    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        return json.dumps(structured, ensure_ascii=False), usage, None

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        return None, usage, "claude envelope carried no result text"
    return result, usage, None


#: Claude's refusal of an oversized request: "Prompt is too long · the request is ~1006909 tokens
#: (limit 1000000) but ..." (claude 2.1.301, captured 2026-11-27).
_TOO_LONG = re.compile(r"~?([\d,]+) tokens \(limit ([\d,]+)\)")


def _error_of(envelope: Dict[str, Any]) -> str:
    """An error envelope's reason as the CLI wrote it: its `result` text, which names the cause
    ("Prompt is too long ..."), or its terminal reason and status when it carried none."""
    result = envelope.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip()
    reason = envelope.get("terminal_reason") or envelope.get("subtype")
    status = envelope.get("api_error_status")
    return f"{reason} (status {status})" if status else str(reason)


def claude_one_shot_failure(stdout: str) -> Optional[OneShotFailure]:
    """The failure an error envelope on stdout describes, or None when there is no such envelope."""
    envelope = extract_json_object(stdout)
    if envelope is None or not envelope.get("is_error"):
        return None
    reason = _error_of(envelope)
    too_large = envelope.get("terminal_reason") == "prompt_too_long" or reason.startswith(
        "Prompt is too long"
    )
    counts = _TOO_LONG.search(reason) if too_large else None
    return OneShotFailure(
        reason=reason,
        too_large=too_large,
        prompt_tokens=int(counts.group(1).replace(",", "")) if counts else None,
        limit_tokens=int(counts.group(2).replace(",", "")) if counts else None,
    )


#: The system prompt of a worker call that brings none of its own. It replaces Claude Code's own,
#: which describes a coding assistant in a repository: a worker is neither, and that prompt was
#: most of a small call's input (3,584 tokens against 1,097 for the same call, 2026-11-27).
WORKER_SYSTEM_PROMPT = (
    "You do one task for AgentWeave, a local app that runs AI agents building software: the one "
    "the message describes. Answer exactly as it asks."
)
#: A system prompt longer than this goes on stdin before the data instead: an argument is capped
#: by the command line (F682), and the schema shares it.
_SYSTEM_ARG_LIMIT = 16_000
#: What a reader may use: read-only, and contained to its working directory by
#: `--permission-mode default` (measured for Read 2026-10-12, Grep 2026-11-27).
READER_TOOLS = "Read,Grep,Glob"


def _worker_argv(
    binary: str,
    tools: str,
    *,
    model: Optional[str],
    prompt: str,
    system: Optional[str],
    schema: Optional[Dict[str, Any]],
    reading: bool,
) -> OneShotCommand:
    """A worker's argv: its own system prompt instead of Claude Code's, none of the operator's
    settings, memory or `CLAUDE.md` (`--setting-sources ""`), no session file left behind, and the
    answer validated against *schema* by the CLI itself (`--json-schema`).

    A reader adds an explicit `--permission-mode default`: in -p mode a Read outside the working
    directory is then denied, even when the operator's own settings default to bypassing
    permissions (measured 2026-10-12, claude 2.1.291)."""
    instructions = system or WORKER_SYSTEM_PROMPT
    data = prompt
    if len(instructions) > _SYSTEM_ARG_LIMIT:
        instructions, data = WORKER_SYSTEM_PROMPT, with_system(instructions, prompt)
    cmd = [binary, "--tools", tools, "--strict-mcp-config"]
    if reading:
        cmd += ["--permission-mode", "default"]
    cmd += ["--setting-sources", "", "--no-session-persistence", "--disable-slash-commands"]
    cmd += ["--system-prompt", instructions]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema, separators=(",", ":"))]
    cmd += ["--output-format", "json"]
    if model:
        cmd += ["--model", model]
    # On stdin, not after `-p`: an argument is capped by the command line (F682).
    return OneShotCommand(cmd + ["-p"], stdin=neutralise_file_mentions(data))


class ClaudeStreamTransport(StreamTransport):
    """Claude Code's one transport — a PTY-spawned process parsed line by line."""

    spawn_kind = "pty"
    instruction_channel = "--append-system-prompt-file"
    context_window_source = "reported"

    def build_launch(self, req: LaunchRequest) -> List[str]:
        control_args = (
            render_control_args("claude", req.control_overrides) if req.control_overrides else []
        )
        return runner_commands._build_claude_command(
            cli=ClaudeAdapter.binary,
            prompt=req.prompt,
            model=req.model,
            context_file=req.context_file,
            session_id=req.session_id,
            yolo=req.yolo,
            approvals=req.axes.approvals,
            mcp_command=req.mcp_command,
            extra_flags=req.extra_flags,
            control_args=control_args,
            control_overrides=req.control_overrides,
            restrict_spec_writes=req.restrict_spec_writes,
            described_access_path=req.described_access_path,
        )

    def inject_mcp(self, mcp_command: List[str], *, yolo: bool) -> List[str]:
        return runner_commands._claude_mcp_args(mcp_command, yolo=yolo)

    def approval_channel(self, tool_surface: str) -> Literal["mcp_permission_tool", "none"]:
        return "mcp_permission_tool" if tool_surface == "mcp" else "none"

    def map_events(self, line: str, *, model: Optional[str]) -> ParsedLine:
        return parse_claude_line(line)

    def usage_from(
        self, *, session_id: str, env: Optional[Dict[str, str]], model: Optional[str]
    ) -> Optional[AccountingSample]:
        return None


_STREAM_TRANSPORT = ClaudeStreamTransport()


class ClaudeAdapter(RunnerAdapter):
    """Claude Code (design D3's "Claude" column)."""

    name = "claude"
    binary = "claude"
    display_name = "Claude"
    catalog_provider = "claude"
    mcp_tool_prefix = "mcp__agentweave__"
    host_tool_note = (
        "Your host also has tools with similar names — `SendMessage` continues a subagent you "
        "started — which cannot reach AgentWeave profiles or the operator."
    )
    # FR-9 of `dashboards-that-feel-alive-and-draw-right-the-first-time`: Claude Code defers MCP
    # tools behind `ToolSearch`, and a Haiku turn called it 21 times, never the tool it loaded.
    deferred_tool_note = (
        "Where these tools are listed as deferred, load every one you need with one `ToolSearch` "
        "call (`select:mcp__agentweave__<name>,mcp__agentweave__<name>`), then call each tool by "
        "its full name. `ToolSearch` only loads a schema and never runs a tool: once it has "
        "returned a tool, do not search for it again -- call it."
    )
    write_tool_kinds = CLAUDE_WRITE_TOOLS
    # `checkpoint_policy.py:24`'s comment: the value today's thresholds were chosen against.
    compaction_percent = 95
    one_shot_reads_files = True
    # F677 (research 2026-10-07 §1): a turn is one `-p` process and the run ends when it does.
    # Since 2.1.292 that process waits for a background command and then takes a second,
    # unprompted model turn; before it, the command was killed after the reply. With this the
    # model is told the parameter is unsupported, and the run ends at its reply.
    run_env_defaults = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}

    def run_env(self, model: Optional[str]) -> Dict[str, str]:
        env = super().run_env(model)
        # FR-9 of `dashboards-that-feel-alive-and-draw-right-the-first-time`: with the tools
        # deferred, a Haiku turn called `ToolSearch` 51 times, never once the tool it loaded, then
        # saved queries over guessed tables; the note above did not stop it. Haiku is given the
        # tools themselves instead. Other models keep tool search, which saves their context.
        if model and "haiku" in model.lower():
            env["ENABLE_TOOL_SEARCH"] = "false"
        return env

    def launchability(self, agent: str, config: Mapping[str, Any]) -> LaunchVerdict:
        cli, present, reason = probe_binary(self.binary, config.get("cli"), agent)
        # F1183: a sign-in that cannot be renewed fails every turn; say so before one is spent.
        signin = claude_signin.unrenewable_reason() if present else None
        return LaunchVerdict(
            runner=self.name,
            cli=cli,
            present=present,
            authorized=signin is None,
            runnable=present and signin is None,
            reason=reason if reason else signin,
        )

    def collaboration(
        self, flags: Optional[Sequence[str]], *, yolo: bool
    ) -> Tuple[bool, Optional[str]]:
        return True, None

    def guard_env(
        self, proc_env: Optional[Dict[str, str]], config: Mapping[str, Any]
    ) -> Optional[Dict[str, str]]:
        env_vars = config.get("env_vars") or {}
        if "ANTHROPIC_BASE_URL" in env_vars:
            return proc_env
        base = proc_env if proc_env is not None else os.environ
        if base.get("ANTHROPIC_BASE_URL"):
            proc_env = dict(base)
            proc_env.pop("ANTHROPIC_BASE_URL", None)
        return proc_env

    def transport(self, flags: Optional[Sequence[str]]) -> StreamTransport:
        return _STREAM_TRANSPORT

    def stream_transport(self) -> Optional[StreamTransport]:
        return _STREAM_TRANSPORT

    def posture_at_rest(self, axes: AccessAxes, *, yolo: bool) -> str:
        return runner_commands.claude_posture_at_rest(axes.approvals, yolo)

    def one_shot(
        self,
        purpose: Literal["worker", "title"],
        *,
        model: Optional[str],
        prompt: str,
        output_schema_path: Optional[str] = None,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        if purpose == "worker":
            return _worker_argv(
                self.binary,
                "",
                model=model,
                prompt=prompt,
                system=system,
                schema=schema,
                reading=False,
            )
        # The titler runs in the project's directory so that its `CLAUDE.md` applies
        # (`conversation_titles.build_title_command`), so it keeps Claude Code's own setup.
        # JSON too, so the title call's usage is read and counted (F240).
        cmd = [self.binary, "--tools", "", "--strict-mcp-config", "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        # On stdin, not after `-p`: an argument is capped by the command line (F682).
        stdin = neutralise_file_mentions(with_system(system, prompt))
        return OneShotCommand(cmd + ["-p"], stdin=stdin)

    def read_one_shot(
        self,
        *,
        model: Optional[str],
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        """The read-only file tools, no MCP server, contained to the working directory."""
        return _worker_argv(
            self.binary,
            READER_TOOLS,
            model=model,
            prompt=prompt,
            system=system,
            schema=schema,
            reading=True,
        )

    def one_shot_failure(self, stdout: str) -> Optional[OneShotFailure]:
        return claude_one_shot_failure(stdout)

    def parse_one_shot(self, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
        return parse_claude_envelope(stdout)
