"""Command-line construction for Hub-spawned agent runs — Claude Code and Codex CLI only.

The Hub owns command construction independently from the lifecycle CLI. Every flag below was
verified against the supported runner CLIs. Claude runs through `PtySession`; Codex's
non-interactive JSONL mode runs through `PipeSession` (see `pty_runner.py`).

Kimi, OpenCode, and Copilot are explicitly out of scope for this task (per-runner command
construction for them is deferred) — `build_command` raises `UnsupportedRunnerError` for
anything else so the caller gets a clear, stated reason rather than a silently wrong command.

Codex has two transports. The default is `codex app-server` (see `codex_appserver.py`), where the
Hub answers each approval itself and can accept its own MCP server without weakening the sandbox.
This module builds the *other* one — `codex exec` — which a runner selects by carrying
`--no-app-server` in its flags. `exec` is non-interactive and exposes no `--ask-for-approval` flag,
so approvals there resolve by policy only: deny everything (which silently kills every AgentWeave
tool call) or `--dangerously-bypass-approvals-and-sandbox`. That is why it is no longer the default
and why an agent on it is reported as unable to collaborate unless yolo is set.

Claude permission posture is always stated explicitly, so it comes from the Hub rather than from
whatever `~/.claude/settings.json` says on the machine the Hub runs on (openspec change
`2026-08-06-claude-non-yolo-permission-mode`). Yolo runs receive `--dangerously-skip-permissions`;
non-yolo runs receive `--permission-mode DEFAULT_CLAUDE_PERMISSION_MODE`. That default was `manual`
until 2026-08-06, when operator testing showed it refuses every write — headless execution has no
terminal at which an operator could answer the prompt `manual` raises, and no approval surface
exists yet (`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`).

Either default is suppressed when the operator has chosen a posture through the `permission_mode`
control, whose rendered flag arrives in `control_args`. The agent's own
`default_permission_mode` arrives by the same route — `trigger_agent_directly` fills the control in
when the conversation states none, so a chosen default and a per-run choice are one mechanism here
rather than two, and this module has no separate notion of an agent-level default to keep in step.
When a run also configures the Hub's own MCP server, `--allowedTools "mcp__agentweave__*"` is added
so that server's tools stay usable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .model_catalog import WORKSPACE_PERMISSION_MODE, render_control_args

SUPPORTED_RUNNERS = ("claude", "claude_proxy", "native", "codex")

# The posture a non-yolo Claude run gets when the operator has chosen none. `manual` was used
# until 2026-08-06 and is unusable headlessly: it defers each decision to an operator prompt that
# nothing can answer, so every write was refused with "Claude requested permissions to write to
# ..., but you haven't granted it yet". `acceptEdits` keeps the Hub — not the host machine's
# settings — in control of posture while producing a run that can do work. Isolation is still
# carried by the agent's own git worktree, which this does not widen. `manual` remains selectable
# through the `permission_mode` control for a deliberately inert run.
DEFAULT_CLAUDE_PERMISSION_MODE = "acceptEdits"

# The tool `--permission-prompt-tool` names for the "Workspace only" posture. `mcp__<server>__<tool>`
# is Claude's addressing for an MCP tool; the server half must match the name `_build_claude_command`
# registers in `--mcp-config` above, and the tool half `mcp_server.py`'s own function name.
CLAUDE_PERMISSION_PROMPT_TOOL = "mcp__agentweave__approve_tool_call"

# The two postures that route decisions through the approver, differing only in who answers:
# `workspace` has the Hub decide against the run's own directory; `manual` puts each call to the
# operator. Before this, `manual` meant "ask" with nothing able to answer, so it refused
# everything — the label promised a prompt that could never appear.
APPROVER_PERMISSION_MODES = (WORKSPACE_PERMISSION_MODE, "manual")

# Value of the spawned run's `AW_PERMISSION_POSTURE`, telling the approval tool that the operator
# answers rather than the Hub. Restated in `mcp_server.py` rather than imported from here: that
# module is spawned standalone and imports only stdlib plus fastmcp (see its own docstring).
# `test_permission_approver.py` asserts the two agree.
OPERATOR_POSTURE = "operator"

# claude_proxy and native both invoke the claude CLI (see _build_claude_command) under a
# different auth/proxy setup — their catalog identity for control-override rendering is
# still "claude", the provider the catalog actually declares controls for.
_CATALOG_PROVIDER_BY_RUNNER: Dict[str, str] = {
    "claude": "claude",
    "claude_proxy": "claude",
    "native": "claude",
    "codex": "codex",
}


def catalog_provider_for_runner(runner: str) -> Optional[str]:
    return _CATALOG_PROVIDER_BY_RUNNER.get(runner)


class UnsupportedRunnerError(ValueError):
    """Raised when asked to build a command for a runner this module doesn't cover yet."""


def build_command(
    *,
    runner: str,
    cli: str,
    prompt: str,
    model: Optional[str] = None,
    context_file: Optional[Path] = None,
    session_id: Optional[str] = None,
    yolo: bool = False,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_overrides: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Build the full CLI invocation for one turn.

    ``cli`` is the resolved binary name/path (see `launchability.RUNNER_CLI` /
    `pty_runner.resolve_executable`) — this function only builds the argument list.
    ``session_id`` set means resume; unset means a new session. Raises
    ``UnsupportedRunnerError`` for any runner other than claude/claude_proxy/native/codex.

    ``control_overrides`` (control id -> value, e.g. ``{"effort": "high"}``) must already be
    validated against the model catalog by the caller (`model_catalog.validate_overrides`) —
    this function only renders each control's declared `ApplySpec` into argv
    (`model_catalog.render_control_args`); it does not itself reject an invalid value. Model
    selection is not part of this dict — it stays the dedicated ``model`` parameter above,
    which every runner already threads through its own command shape.
    """
    provider = catalog_provider_for_runner(runner)
    control_args = (
        render_control_args(provider, control_overrides)
        if provider and control_overrides
        else []
    )
    if runner == "codex":
        return _build_codex_command(
            cli=cli,
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            extra_flags=extra_flags,
            control_args=control_args,
        )
    if runner in ("claude", "claude_proxy", "native"):
        return _build_claude_command(
            cli=cli,
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            extra_flags=extra_flags,
            control_args=control_args,
            control_overrides=control_overrides,
        )
    raise UnsupportedRunnerError(
        f"runner {runner!r} is not yet supported for direct Hub spawn "
        f"(supported: {', '.join(SUPPORTED_RUNNERS)})"
    )


def _build_claude_command(
    *,
    cli: str,
    prompt: str,
    model: Optional[str],
    context_file: Optional[Path],
    session_id: Optional[str],
    yolo: bool,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_args: Optional[List[str]] = None,
    control_overrides: Optional[Dict[str, str]] = None,
) -> List[str]:
    cmd = [cli, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    if control_args:
        cmd += control_args
    # An operator's `permission_mode` control arrives inside `control_args`, which is spliced in
    # above; the default posture below is appended *after* it and would win. Suppress the default
    # whenever the override supplied one, or the composer's Permissions pill would appear to work
    # and change nothing — the worst available failure mode.
    operator_set_permission_mode = "--permission-mode" in (control_args or [])
    if context_file is not None and context_file.exists():
        cmd += ["--append-system-prompt-file", str(context_file)]
    if mcp_command:
        config = {
            "mcpServers": {
                "agentweave": {
                    "type": "stdio",
                    "command": mcp_command[0],
                    "args": mcp_command[1:],
                }
            }
        }
        cmd += ["--mcp-config", json.dumps(config)]
        if not yolo:
            cmd += ["--allowedTools", "mcp__agentweave__*"]
        # The "Workspace only" posture is `manual` plus an answerer. Emitted here rather than from
        # the catalog because only this function knows whether the server that answers is even
        # configured: naming an approver that will not be there makes every tool call fail, which
        # the model reports as a broken approval system. Guarded by
        # `operator_set_permission_mode` for the same reason the default posture below is — an
        # approver flag must not outlive the posture that asked for it.
        if (
            operator_set_permission_mode
            and (control_overrides or {}).get("permission_mode") in APPROVER_PERMISSION_MODES
        ):
            cmd += ["--permission-prompt-tool", CLAUDE_PERMISSION_PROMPT_TOOL]
    if not operator_set_permission_mode:
        if yolo:
            cmd += ["--dangerously-skip-permissions"]
        else:
            cmd += ["--permission-mode", DEFAULT_CLAUDE_PERMISSION_MODE]
    if session_id:
        cmd += ["--resume", session_id]
    if extra_flags:
        cmd += extra_flags
    cmd += ["-p", prompt]
    return cmd


def _build_codex_command(
    *,
    cli: str,
    prompt: str,
    model: Optional[str],
    context_file: Optional[Path],
    session_id: Optional[str],
    yolo: bool,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_args: Optional[List[str]] = None,
) -> List[str]:
    cmd = [cli, "exec"]
    cmd += ["--json", "--skip-git-repo-check"]
    if mcp_command:
        cmd += ["-c", f"mcp_servers.agentweave.command={json.dumps(mcp_command[0])}"]
        cmd += ["-c", f"mcp_servers.agentweave.args={json.dumps(mcp_command[1:])}"]
        # Codex filters environment inherited by dynamically configured stdio MCP servers.
        # Forward names only: Codex resolves their values from its own local environment.
        forwarded = [
            "AW_RUN_TOKEN",
            "AW_AGENT_IDENTITY",
            "AW_RUN_ID",
            "AW_TURN_DEPTH",
            "HUB_URL",
        ]
        cmd += ["-c", f"mcp_servers.agentweave.env_vars={json.dumps(forwarded)}"]
    if context_file is not None and context_file.exists():
        cmd += ["-c", f"model_instructions_file={context_file}"]
    if model:
        cmd += ["--model", model]
    if control_args:
        cmd += control_args
    if yolo:
        cmd += ["--dangerously-bypass-approvals-and-sandbox"]
    else:
        cmd += ["--sandbox", "workspace-write"]
    # `--sandbox` (and every other exec-level option above, including control_args)
    # belongs to `codex exec`, not its `resume` subcommand. Keep all exec-level options
    # before `resume`; newer Codex releases reject a sandbox flag placed after the
    # subcommand with "unexpected argument '--sandbox'" — the same ordering constraint
    # applies to `-c model_reasoning_effort=...`.
    if session_id:
        cmd += ["resume", session_id]
    if extra_flags:
        cmd += extra_flags
    cmd += [prompt]
    return cmd
