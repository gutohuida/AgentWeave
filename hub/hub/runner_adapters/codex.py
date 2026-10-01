"""The Codex adapter (design D1/D3): one stream transport (`exec`), one RPC transport
(`app-server`).

`CodexExecTransport` delegates argv construction and line parsing to `runner_commands` and
`runner_parsing`, same as `claude.py` (design D1, "Why the existing modules stay").
`CodexAppServerTransport` wraps `codex_appserver.run_turn` with today's own arguments
(`agent_trigger.py`'s `_execute_codex_appserver_run._start_turn`, unchanged). `posture_for`,
`_CODEX_APPROVAL_LABELS` and `parse_codex_envelope`/one-shot builders are copied here from
`agent_trigger.py`/`worker.py`/`conversation_titles.py`'s existing Codex branches -- **by copy,
not cut**: those modules keep their own originals until task 3.4/3.5 re-point them at this adapter
and delete them, so this file lands without moving any existing caller (same precedent as
`claude.py`, task 2.2).

`CodexAdapter.transport`'s body is `codex_appserver.uses_app_server`'s today (minus its
`runner_cli != "codex"` guard, which the adapter lookup replaces) -- design D5 marks that function
for deletion, but its two real callers (`agent_trigger.py:1221`, `agents.py:260`) are outside this
package and belong to tasks 3.3/3.6; deleting it here would break their imports before those tasks
land, so it stays until whichever of them removes the last caller (filed as F472).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from .. import codex_appserver, runner_commands
from ..codex_appserver import TurnOutcome
from ..file_mentions import neutralise_file_mentions
from ..model_catalog import (
    FULL_ACCESS_PERMISSION_MODE,
    PERMISSION_MODE_CONTROL,
    WORKSPACE_PERMISSION_MODE,
    render_control_args,
)
from ..runner_parsing import (
    AccountingSample,
    ParsedLine,
    parse_codex_line,
    read_codex_rollout_accounting,
)
from ..workspace_writes import CODEX_WRITE_TOOL
from .base import (
    AccessAxes,
    LaunchRequest,
    LaunchVerdict,
    RpcCallbacks,
    RpcTransport,
    RpcTurnRequest,
    RunnerAdapter,
    StreamTransport,
    probe_binary,
)
from .one_shot import WorkerUsage, _int_or_none


def parse_codex_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `codex exec --json` (copied from `worker.py`, design D8:
    `worker.py:204-211`'s builder and `:330-379`'s parser).

    JSONL. The answer arrives as an `item.completed` whose item is an `agent_message`; usage
    arrives separately on `turn.completed`. Unparseable lines are skipped rather than failing the
    call -- the stream is an event log, and a future CLI adding an event we do not understand is
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


class CodexExecTransport(StreamTransport):
    """Codex's non-interactive transport: a pipe-spawned process parsed line by line."""

    spawn_kind = "pipe"
    instruction_channel = "-c model_instructions_file"
    context_window_source = "catalog"

    def build_launch(self, req: LaunchRequest) -> List[str]:
        control_args = (
            render_control_args("codex", req.control_overrides) if req.control_overrides else []
        )
        full_access = (req.control_overrides or {}).get(
            PERMISSION_MODE_CONTROL
        ) == FULL_ACCESS_PERMISSION_MODE
        return runner_commands._build_codex_command(
            cli=CodexAdapter.binary,
            prompt=req.prompt,
            model=req.model,
            context_file=req.context_file,
            session_id=req.session_id,
            yolo=req.yolo,
            full_access=full_access,
            mcp_command=req.mcp_command,
            extra_flags=req.extra_flags,
            control_args=control_args,
            restrict_spec_writes=req.restrict_spec_writes,
        )

    def inject_mcp(self, mcp_command: List[str], *, yolo: bool) -> List[str]:
        return runner_commands._codex_exec_mcp_args(mcp_command)

    def approval_channel(self, tool_surface: str) -> Literal["none"]:
        return "none"

    def map_events(self, line: str, *, model: Optional[str]) -> ParsedLine:
        return parse_codex_line(line, model=model)

    def usage_from(
        self, *, session_id: str, env: Optional[Dict[str, str]], model: Optional[str]
    ) -> Optional[AccountingSample]:
        codex_home = Path(env["CODEX_HOME"]) if env and env.get("CODEX_HOME") else None
        return read_codex_rollout_accounting(session_id, codex_home=codex_home, model=model)


_STREAM_TRANSPORT = CodexExecTransport()

# How Codex's approval methods read on the operator's card. Copied from `agent_trigger.py`'s
# `_CODEX_APPROVAL_LABELS` (not cut, same precedent as this module's other copies): the raw method
# names ("item/commandExecution/requestApproval") are protocol, not something to put in front of a
# person deciding in seconds.
_CODEX_APPROVAL_LABELS = {
    codex_appserver.COMMAND_APPROVAL_METHOD: "a command",
    codex_appserver.FILE_CHANGE_APPROVAL_METHOD: "a file change",
}


class CodexAppServerTransport(RpcTransport):
    """Codex's RPC transport: a JSON-RPC peer the Hub drives (`codex_appserver.py`)."""

    instruction_channel = None  # F325 is open; design D11 covers it.
    context_window_source = "reported"

    def posture_for(self, permission_mode: Optional[str]) -> Optional[str]:
        """Maps the operator's chosen posture onto what `decide_approval` reads. Copied from
        `agent_trigger._codex_posture`, unchanged (design D3)."""
        if permission_mode == "manual":
            return runner_commands.OPERATOR_POSTURE
        if permission_mode == WORKSPACE_PERMISSION_MODE:
            return WORKSPACE_PERMISSION_MODE
        if permission_mode == FULL_ACCESS_PERMISSION_MODE:
            return FULL_ACCESS_PERMISSION_MODE
        return None

    def permission_card_label(self, method: str, subject: Mapping[str, Any]) -> str:
        return _CODEX_APPROVAL_LABELS.get(method, method)

    def refusal_label(self, method: str, subject: Mapping[str, Any]) -> str:
        return codex_appserver.approval_label(method)

    def workspace_verdict(
        self, method: str, subject: Mapping[str, Any], workspace: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        return codex_appserver.workspace_verdict(subject, workspace)

    async def run_turn(self, req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome:
        return await codex_appserver.run_turn(
            cli=req.cli,
            cwd=req.cwd,
            env=req.env,
            prompt=req.prompt,
            model=req.model,
            resume_thread_id=req.resume_session_id,
            yolo=req.yolo,
            mcp_command=req.mcp_command,
            config_overrides=req.config_overrides,
            on_event=cb.on_event,
            on_usage=cb.on_usage,
            on_accounting=cb.on_accounting,
            on_thread_started=cb.on_session,
            should_interrupt=cb.should_interrupt,
            posture=self.posture_for(req.permission_mode),
            workspace=req.workspace,
            request_approval=cb.request_approval,
            on_refusal=cb.on_refusal,
        )


_RPC_TRANSPORT = CodexAppServerTransport()


class CodexAdapter(RunnerAdapter):
    """Codex (design D3's "Codex" column)."""

    name = "codex"
    binary = "codex"
    display_name = "Codex"
    catalog_provider = "codex"
    transport_sentinels = codex_appserver.TRANSPORT_SENTINELS
    mcp_env_names = runner_commands.CODEX_MCP_ENV_NAMES
    write_tool_kinds = {CODEX_WRITE_TOOL: "changes[].path"}
    one_shot_takes_schema = True

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
        # Derived from the same flag check `transport` uses, so what the operator is told and
        # what actually runs cannot drift apart (today's `agents.py:249-274`, text unchanged).
        if yolo or codex_appserver.APP_SERVER_OPT_OUT_FLAG not in (flags or []):
            return True, None
        return False, (
            "This Codex agent's runner opted out of the app-server transport "
            f'(flags: ["{codex_appserver.APP_SERVER_OPT_OUT_FLAG}"]) and the agent does not have '
            "Full access, so it falls back to classic exec — AgentWeave tool calls "
            "(send_message, etc.) will be silently denied with no operator "
            f"present to approve them. Bind a runner without "
            f"{codex_appserver.APP_SERVER_OPT_OUT_FLAG}, or set this agent's permissions to Full "
            "access."
        )

    def guard_env(
        self, proc_env: Optional[Dict[str, str]], config: Mapping[str, Any]
    ) -> Optional[Dict[str, str]]:
        return proc_env

    def transport(self, flags: Optional[Sequence[str]]) -> StreamTransport | RpcTransport:
        if codex_appserver.APP_SERVER_OPT_OUT_FLAG in (flags or []):
            return _STREAM_TRANSPORT
        return _RPC_TRANSPORT

    def stream_transport(self) -> Optional[StreamTransport]:
        return _STREAM_TRANSPORT

    def posture_at_rest(self, axes: AccessAxes, *, yolo: bool) -> str:
        return runner_commands.posture_at_rest(
            "codex", "mcp" if axes.approvals != "none" else "cli", yolo
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
            cmd = [self.binary, "exec", "--skip-git-repo-check", "--json"]
            cmd += ["--ephemeral", "--sandbox", "read-only"]
            if output_schema_path:
                cmd += ["--output-schema", output_schema_path]
            if model:
                cmd += ["--model", model]
            return cmd + [neutralise_file_mentions(prompt)]
        cmd = [self.binary, "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
        if model:
            cmd += ["--model", model]
        return cmd + [neutralise_file_mentions(prompt)]

    def parse_one_shot(self, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
        return parse_codex_envelope(stdout)
