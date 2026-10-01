"""The Claude Code adapter (design D1/D3): one stream transport, no RPC transport.

`ClaudeStreamTransport` delegates argv construction and line parsing to `runner_commands` and
`runner_parsing`, which keep the builders and parsers themselves (design D1, "Why the existing
modules stay"). `one_shot`/`parse_one_shot` are copied here from `worker.py`'s today's Claude
branches, **by copy, not cut** — `worker.py` and `conversation_titles.py` keep their own originals
until task 3.5 re-points them at the adapter and deletes them (same precedent as task 2.1's
`one_shot.py`), so this file lands without moving any existing caller.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from .. import runner_commands
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
from .one_shot import WorkerUsage, _int_or_none, extract_json_object


def parse_claude_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `claude --output-format json` (copied from `worker.py`,
    design D8: `worker.py:142-146`'s builder and `:297-327`'s parser)."""
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
    write_tool_kinds = CLAUDE_WRITE_TOOLS

    def launchability(self, agent: str, config: Mapping[str, Any]) -> LaunchVerdict:
        cli, present, reason = probe_binary(self.binary, config.get("cli"), agent)
        return LaunchVerdict(
            runner=self.name,
            cli=cli,
            present=present,
            authorized=True,
            runnable=present,
            reason=reason,
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
        return runner_commands.posture_at_rest(
            "claude", "mcp" if axes.approvals != "none" else "cli", yolo
        )

    def one_shot(
        self,
        purpose: Literal["worker", "title"],
        *,
        model: Optional[str],
        prompt: str,
        output_schema_path: Optional[str] = None,
    ) -> List[str]:
        if purpose == "worker":
            cmd = [self.binary, "--tools", "", "--strict-mcp-config", "--output-format", "json"]
        else:
            cmd = [self.binary, "--tools", "", "--strict-mcp-config"]
        if model:
            cmd += ["--model", model]
        return cmd + ["-p", neutralise_file_mentions(prompt)]

    def parse_one_shot(self, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
        return parse_claude_envelope(stdout)
