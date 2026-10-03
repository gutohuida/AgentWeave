"""The Copilot adapter: one RPC transport, ACP (`copilot --acp`).

`a-copilot-agent-runs-over-acp` ("slice 2") shipped before this package existed, so it built
Copilot's behaviour as free functions (`copilot_acp`, `copilot_probe`, `copilot_env`) and left the
adapter its "Slice 1 member names" table describes to whichever change landed second. This module
is that adapter. Every member delegates to the function slice 2 already ships; none re-derives
Copilot behaviour. That is what lets `ADAPTERS`, `RUNNER_CLIS` and `CATALOG` name the same three
runners (design D2, F471), and lets every call site ask `get_adapter` instead of carrying a
`runner == "copilot"` branch (F473).

Copilot has no stream transport (`stream_transport()` is `None`): ACP is the only way the Hub runs
a Copilot turn, and its argv is built inside `run_turn` (slice 2 D1/D3).

The one-shot builder, its environment and its envelope parser moved here from `worker.py`, which
re-exports them; `copilot_acp`/`copilot_probe` are imported inside the members that call them, so
importing this package still loads no `hub.db`/`hub.api` (design D1).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from .. import runner_commands
from ..codex_appserver import TurnOutcome
from ..copilot_env import copilot_guard_env
from ..file_mentions import neutralise_file_mentions
from ..runner_provider import copilot_provider_env, has_provider, provider_launch_verdict
from ..workspace_writes import COPILOT_WRITE_TOOLS
from .base import (
    AccessAxes,
    LaunchVerdict,
    RpcCallbacks,
    RpcTransport,
    RpcTurnRequest,
    RunnerAdapter,
    StreamTransport,
)
from .one_shot import WorkerUsage

#: A Copilot one-shot call, offered **no tool** (`a-copilot-agent-runs-over-acp` D14). Tools
#: are removed by `--excluded-tools`, which always wins; `--available-tools=` is never used, because
#: an empty value means *no filter* (`app.js`'s `Y0`) and, with `--allow-all-tools`, would approve
#: every built-in tool on an untrusted transcript (F420). `--allow-all-tools` is required for `-p`,
#: and with every tool excluded it grants nothing. Task 1.2's capture confirmed zero tools.
COPILOT_ONE_SHOT_FLAGS: Tuple[str, ...] = (
    "--output-format",
    "json",
    "--no-auto-update",
    "--disable-builtin-mcps",
    "--no-ask-user",
    "--excluded-tools=builtin:*,mcp:*,custom:*",
    "--allow-all-tools",
)


def copilot_one_shot_command(
    *, prompt: str, model: Optional[str], custom_instructions: bool
) -> List[str]:
    """`copilot -p` for a one-shot call. `cmd[0]` is the absolute platform executable, never the
    bare `copilot` that `resolve_executable` would resolve to the npm shim. Raises
    `CopilotExecutableNotFound` (a `FileNotFoundError`) when there is none; the callers turn that
    into their own "could not spawn" outcome.

    `custom_instructions=False` adds `--no-custom-instructions`: the worker wants none, while the
    titler runs in the project's directory precisely so the project's memory applies.
    """
    from .. import copilot_probe

    cmd = [str(copilot_probe.resolve_copilot_executable(None)), "-p"]
    cmd.append(neutralise_file_mentions(prompt))
    cmd += list(COPILOT_ONE_SHOT_FLAGS)
    if not custom_instructions:
        cmd.append("--no-custom-instructions")
    if model and model != "auto":
        cmd += ["--model", model]
    return cmd


def copilot_one_shot_env(config: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    """The Hub's environment through the one Copilot filter, under the worker home (D14): no
    GitHub token, no allow-all or trust variable, no ambient provider override. Then the runner's
    own model provider from `config` (`runner_probe_config`'s shape, `model` the one the spawn
    names), through the same function as a run's `guard_env` (slice 5 D7, finding 1)."""
    from ..copilot_home import ensure_copilot_worker_home

    config = config or {}
    home = ensure_copilot_worker_home()
    env, _removed = copilot_guard_env(dict(os.environ), {})
    env = copilot_provider_env(env, config.get("provider_config"), config.get("model"))
    env["COPILOT_HOME"] = str(home)
    return env


def parse_copilot_envelope(stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
    """(answer text, usage, error) from `copilot -p --output-format json`.

    JSONL, one session event per line (task 1.2's capture): the answer is the last
    `assistant.message`'s `content`, a failure is a `session.error`, and the closing `result` line
    carries the session id. Usage stays empty: premium requests and credits are slice 4's.
    """
    answer: Optional[str] = None
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
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        kind = event.get("type")
        if kind == "assistant.message":
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                answer = content
        elif kind == "session.error":
            message = data.get("message")
            failure = (
                f"copilot reported an error: {message or data.get('errorType') or 'no detail'}"
            )
    if failure is not None:
        return None, WorkerUsage(), failure
    if answer is None:
        return None, WorkerUsage(), "copilot produced no assistant message"
    return answer, WorkerUsage(), None


def _request_label(subject: Mapping[str, Any]) -> str:
    """Copilot's requests share one method and differ by kind, so the card and the refusal name
    the request's own `tool_name` (slice 2 D8, *Operator posture*)."""
    return str(subject.get("tool_name") or "a Copilot request")


class CopilotAcpTransport(RpcTransport):
    """Copilot's RPC transport: an ACP peer the Hub drives (`copilot_acp.run_turn`)."""

    tests_mcp_before_first_prompt = True

    # Not an argv flag: the rendered stable context is the Hub-written custom agent file, chosen
    # over ACP with `session/set_config_option {configId: "agent"}` (slice 2 D4/D6).
    instruction_channel = "session/set_config_option agent"
    # `usage_update.size` (slice 1 D13, VERIFIED-LOCAL).
    context_window_source = "reported"

    def posture_for(self, permission_mode: Optional[str]) -> Optional[str]:
        """D8's posture table. `run_turn` applies it itself, with the run's `yolo` (an unset mode
        under `yolo` is Full access), so this is the answer for a run without `yolo`."""
        from .. import copilot_acp

        return copilot_acp.posture_for(permission_mode)

    def permission_card_label(self, method: str, subject: Mapping[str, Any]) -> str:
        return _request_label(subject)

    def refusal_label(self, method: str, subject: Mapping[str, Any]) -> str:
        return _request_label(subject)

    def workspace_verdict(
        self, method: str, subject: Mapping[str, Any], workspace: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        # Worked out inside the turn, by Copilot's own Workspace-only judge, before the card is
        # requested (`copilot_acp.run_turn`, slice 2 D5) -- read here, never recomputed.
        verdict = subject.get("workspace_verdict")
        return verdict if isinstance(verdict, dict) else None

    async def run_turn(self, req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome:
        from .. import copilot_acp

        if req.agent is None:
            raise copilot_acp.CopilotACPError("A Copilot turn needs the agent it runs as.")
        return await copilot_acp.run_turn(
            cwd=req.cwd,
            env=req.env,
            prompt=req.prompt,
            model=req.model,
            resume_session_id=req.resume_session_id,
            agent=req.agent,
            per_turn_context=req.per_turn_context,
            tool_surface_context=req.tool_surface_context,
            stable_context=req.stable_context,
            control_overrides=req.control_overrides,
            told_access_path=req.told_access_path,
            permission_mode=req.permission_mode,
            workspace=req.workspace,
            restrict_spec_writes=req.restrict_spec_writes,
            extra_flags=req.extra_flags,
            cli=req.cli,
            mcp_command=req.mcp_command,
            yolo=req.yolo,
            on_event=cb.on_event,
            on_usage=cb.on_usage,
            on_accounting=cb.on_accounting,
            on_session=cb.on_session,
            on_session_missing=cb.on_session_missing,
            await_mcp_announce=cb.await_mcp_announce,
            render_surface=cb.render_surface,
            on_mcp_status=cb.on_mcp_status,
            should_interrupt=cb.should_interrupt,
            request_approval=cb.request_approval,
            on_refusal=cb.on_refusal,
            # No `on_decision`: `a-run-records-that-its-calls-were-allowed` has not landed, so a
            # Copilot run records refusals only, as Codex does (slice 2 task 7.3).
        )


_RPC_TRANSPORT = CopilotAcpTransport()


class CopilotAdapter(RunnerAdapter):
    """GitHub Copilot (slice 2's "Slice 1 member names" table)."""

    name = "copilot"
    binary = "copilot"
    display_name = "GitHub Copilot"
    catalog_provider = "copilot"
    mcp_tool_prefix = runner_commands.COPILOT_MCP_TOOL_PREFIX
    # Slice 2 D16: Copilot's own task tool dispatches a subagent, which is not an AgentWeave agent.
    host_tool_note = (
        "Copilot has its own tools with similar purposes (such as its task tool); these AgentWeave "
        "tools are the only way to reach AgentWeave agents or the operator."
    )
    # `None`: the Hub's MCP child inherits the run's environment (slice 2 D3).
    mcp_env_names = None
    # Each names its files under `locations[].path`, a diff's `changes[].path` as the fallback.
    write_tool_kinds = dict.fromkeys(sorted(COPILOT_WRITE_TOOLS), "locations[].path")
    one_shot_takes_schema = False
    # DOCUMENTED, `context-management` (design D9).
    compaction_percent = 80

    def launchability(self, agent: str, config: Mapping[str, Any]) -> LaunchVerdict:
        # Read from Copilot itself (slice 2 D15): a cached verdict from a model-free ACP
        # handshake, refreshed in the background. Never spawns here, never raises.
        from ..copilot_probe import CopilotProbe

        cli_override = config.get("cli")
        verdict: LaunchVerdict = CopilotProbe.verdict(  # type: ignore[assignment]
            str(cli_override) if cli_override else None
        )
        provider_config = config.get("provider_config")
        if has_provider(provider_config):
            # A provider runner needs its key, not a GitHub login (slice 5 D7): the probe supplies
            # only whether the CLI is present, and its version.
            return provider_launch_verdict(verdict, provider_config)  # type: ignore[return-value]
        return verdict

    def collaboration(
        self, flags: Optional[Sequence[str]], *, yolo: bool
    ) -> Tuple[bool, Optional[str]]:
        # Every Copilot turn answers its requests over ACP, whatever its flags (slice 2 D8).
        return True, None

    def guard_env(
        self, proc_env: Optional[Dict[str, str]], config: Mapping[str, Any]
    ) -> Optional[Dict[str, str]]:
        # Always a full environment: the strips apply to the inherited one too (slice 2 D3).
        base = proc_env if proc_env is not None else dict(os.environ)
        filtered, _removed = copilot_guard_env(base, config.get("env_vars") or {})
        # Then the runner's own model provider, or none (slice 5 D7): stripped from both sources
        # above, set here only from the runner's validated `provider_config`.
        return copilot_provider_env(filtered, config.get("provider_config"), config.get("model"))

    def transport(self, flags: Optional[Sequence[str]]) -> StreamTransport | RpcTransport:
        return _RPC_TRANSPORT

    def stream_transport(self) -> Optional[StreamTransport]:
        return None

    def posture_at_rest(self, axes: AccessAxes, *, yolo: bool) -> str:
        # Copilot's answer is the same on either access path (slice 2 D5): its ACP posture table's
        # answer for an unset mode.
        from .. import copilot_acp

        return copilot_acp.posture_for(None, yolo=yolo)

    def one_shot(
        self,
        purpose: Literal["worker", "title"],
        *,
        model: Optional[str],
        prompt: str,
        output_schema_path: Optional[str] = None,
    ) -> List[str]:
        # The titler keeps the project's custom instructions: it runs in the project's directory
        # so that its memory applies (slice 2 D14). The worker wants none.
        return copilot_one_shot_command(
            prompt=prompt, model=model, custom_instructions=purpose == "title"
        )

    def one_shot_env(
        self, purpose: Literal["worker", "title"], config: Optional[Mapping[str, Any]] = None
    ) -> Optional[Dict[str, str]]:
        return copilot_one_shot_env(config)

    def parse_one_shot(self, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
        return parse_copilot_envelope(stdout)
