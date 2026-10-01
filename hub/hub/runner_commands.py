"""Command-line construction for Hub-spawned agent runs — Claude Code and Codex CLI only.

The Hub owns command construction independently from the lifecycle CLI. Every flag below was
verified against the supported runner CLIs. Claude runs through `PtySession`; Codex's
non-interactive JSONL mode runs through `PipeSession` (see `pty_runner.py`).

Kimi and OpenCode are explicitly out of scope for this module (per-runner command construction
for them is deferred) — `runner_adapters.build_command` (design D6) raises `UnsupportedRunnerError`
for a runner with no adapter, so the caller gets a clear, stated reason rather than a silently
wrong command.

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
non-yolo runs receive `--permission-mode DEFAULT_CLAUDE_PERMISSION_MODE`. That default has moved
twice. It was `manual` until 2026-08-06, when operator testing showed it refuses every write —
headless execution has no terminal at which an operator could answer the prompt `manual` raises. It
was `acceptEdits` until 2026-08-13, which fixed writing and left executing broken for the same
reason: `acceptEdits` still prompts for `Bash`, so an agent could write code and never run it. It is
now the workspace posture, which the *Hub* answers, and which therefore needs no terminal at all —
falling back to `acceptEdits` only where no Hub tool server is configured to do the answering.

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

from .model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE

# Copilot names an MCP tool `<server>-<tool>` (VERIFIED: `hubprobe-ping`), so a Copilot run's
# callable names are known too (`a-copilot-agent-runs-over-acp` D16). `CopilotAdapter` reads it as
# its `mcp_tool_prefix`, the member every caller asks (`each-runner-cli-is-one-adapter` D3).
COPILOT_MCP_TOOL_PREFIX = "agentweave-"


# The posture a non-yolo Claude run gets when the operator has chosen none.
#
# `manual` was used until 2026-08-06 and is unusable headlessly: it defers each decision to an
# operator prompt that nothing can answer, so every write was refused. `acceptEdits` replaced it,
# and produced a run that could *edit* — but it still prompts for `Bash`, and headless there is
# nothing to answer that prompt either. An agent could write code and never run it (found by
# driving the loop end to end, 2026-08-13: the same agent under `workspace` ran 14/14 tests).
#
# `workspace` is the answer because the Hub answers it: each request is checked against the run's
# own workspace by `_decide`. That is *narrower* than `acceptEdits`, which accepted every edit with
# no path check at all, and it permits the execution an agent needs to produce evidence about its
# own work. Isolation is still carried by the agent's git worktree, which this does not widen.
DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE

# The default for a run with no Hub tool server configured. `workspace` *is* `manual` plus an
# answerer, and that answerer is the Hub's own MCP server — so without it, defaulting to
# `workspace` would name an approver that is not there and refuse everything, which is precisely
# the failure `acceptEdits` was introduced to end. A run that cannot be answered gets the posture
# that needs no answering.
DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"

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

# The run variables forwarded to the Hub's MCP server child process for a Codex run -- Codex
# resolves values from its own environment, so no secret is ever embedded in argv or config.
# Declared once here, not in `codex_appserver.py` (design D12, R3): that module already imports
# `OPERATOR_POSTURE` from this one, and the reverse import would be the cycle D1 forbids.
# `_codex_exec_mcp_args` reads it in place; `codex_appserver.run_turn` reads it through its
# existing `from .runner_commands import` line.
CODEX_MCP_ENV_NAMES = (
    "AW_RUN_TOKEN",
    "AW_AGENT_IDENTITY",
    "AW_RUN_ID",
    "AW_TURN_DEPTH",
    "HUB_URL",
)


def claude_posture_at_rest(approvals: str, yolo: bool) -> str:
    """The permission posture a Claude run gets when neither the conversation nor the agent chose
    one: Full access under `yolo`; `workspace` when the Hub's permission tool is there to answer it
    (`approvals != "none"`); otherwise `acceptEdits`, which needs no answerer.

    `ClaudeAdapter.posture_at_rest` returns this, and so does the argv builder below when it decides
    the default posture, so the Permissions pill (which reads the adapter, F283) cannot say one
    thing while the run does another. Each runner's rule lives with its own adapter (design D3);
    this one stays here beside the argv it shapes.
    """
    if yolo:
        return FULL_ACCESS_PERMISSION_MODE
    return (
        DEFAULT_CLAUDE_PERMISSION_MODE
        if approvals != "none"
        else DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER
    )


class UnsupportedRunnerError(ValueError):
    """Raised when asked to build a command for a runner this module doesn't cover yet.

    `build_command` itself moved to `hub.runner_adapters` (design D6, task 3.1) — this class
    stays here (`hub.runner_adapters` imports it) since it is not a registry D5 names for deletion.
    """


def _claude_mcp_args(mcp_command: Optional[List[str]], *, yolo: bool) -> List[str]:
    """The argv fragment that starts the Hub's MCP server for a Claude run (design D1).

    `ClaudeStreamTransport.inject_mcp` calls this directly; `_build_claude_command` calls it at
    the same position. Returns `[]` when no server is configured — every caller treats a
    non-empty result as "a server is injected" (design D1: "guarded by it being non-empty").
    """
    if not mcp_command:
        return []
    config = {
        "mcpServers": {
            "agentweave": {
                "type": "stdio",
                "command": mcp_command[0],
                "args": mcp_command[1:],
            }
        }
    }
    args = ["--mcp-config", json.dumps(config)]
    if not yolo:
        args += ["--allowedTools", "mcp__agentweave__*"]
    return args


#: The Hub's call command, pre-allowed on every non-yolo Claude run
#: (`a-run-reaches-the-hub-without-mcp` D13): where no approver answers -- the `cli` path, or a
#: blocked MCP server under F299's condition A -- a prompt for it would be denied. Claude's prefix
#: rules are shell-operator-aware, so `aw-tool x && y` does not match. They restrict no path;
#: the call command's own calls-root check does (D3).
CLAUDE_CALL_COMMAND_RULES = ("Bash(aw-tool:*)", "PowerShell(aw-tool:*)")


def _build_claude_command(
    *,
    cli: str,
    prompt: str,
    model: Optional[str],
    context_file: Optional[Path],
    session_id: Optional[str],
    yolo: bool,
    approvals: str,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_args: Optional[List[str]] = None,
    control_overrides: Optional[Dict[str, str]] = None,
    restrict_spec_writes: bool = False,
    described_access_path: str = "mcp",
) -> List[str]:
    cmd = [cli, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    if control_args:
        cmd += control_args
    if restrict_spec_writes:
        # Unconditional — including under `yolo=True`. The line just below this one skips
        # `--allowedTools` entirely when yolo is set, because that flag governs a *permission
        # prompt* yolo is explicitly meant to bypass. This flag governs which tools exist at all,
        # a different axis (F4/design D6, round 2): a yolo-configured agent is exactly the run
        # posture likeliest to act on a discovered fix instead of proposing one, so it is the one
        # this restriction must not have an exception for.
        #
        # `MultiEdit` is Claude's default tool for a multi-hunk edit, so leaving it out (F277) let
        # the most ordinary way to change a file through silently -- a model reaching for it never
        # learned it was meant to propose. A nudge, not a sandbox: `Bash` is not named either.
        #
        # A spec turn told the call command keeps `Write` (`a-run-reaches-the-hub-without-mcp`
        # D16): it must write `.agentweave/calls/*.json` to call `submit_spec_document`, and
        # Claude's rules have no negation to confine `Write` to that directory, so the nudge
        # against `Write` is weaker for that turn, stated rather than hidden.
        removed = (
            "Edit,MultiEdit,NotebookEdit"
            if described_access_path == "shim"
            else "Edit,MultiEdit,Write,NotebookEdit"
        )
        cmd += ["--disallowedTools", removed]
    # An operator's `permission_mode` control arrives inside `control_args`, which is spliced in
    # above; the default posture below is appended *after* it and would win. Suppress the default
    # whenever the override supplied one, or the composer's Permissions pill would appear to work
    # and change nothing — the worst available failure mode.
    operator_set_permission_mode = "--permission-mode" in (control_args or [])
    # The posture this run falls back to, decided before the flags are assembled because two
    # places need it: the approver flag below, and the mode flag at the end. `workspace` only
    # works where the Hub's server is there to answer it.
    default_posture = claude_posture_at_rest(approvals, False)
    defaults_to_approver = (
        not operator_set_permission_mode
        and not yolo
        and default_posture in (APPROVER_PERMISSION_MODES)
    )
    if context_file is not None and context_file.exists():
        cmd += ["--append-system-prompt-file", str(context_file)]
    mcp_args = _claude_mcp_args(mcp_command, yolo=yolo)
    cmd += mcp_args
    if not yolo:
        # One `--allowedTools` occurrence, whose values run to the next flag: after the MCP rule
        # when there is one, else a new option. Kept out of `_claude_mcp_args`, which is the MCP
        # injection and would otherwise carry an unrelated rule (verification 2026-10-01, 7.1).
        if "--allowedTools" in mcp_args:
            cmd += list(CLAUDE_CALL_COMMAND_RULES)
        else:
            cmd += ["--allowedTools", *CLAUDE_CALL_COMMAND_RULES]
    # The "Workspace only" posture is `manual` plus an answerer. Emitted here rather than from the
    # catalog because only this function knows whether the server that answers is even configured:
    # naming an approver that will not be there makes every tool call fail, which the model
    # reports as a broken approval system. Guarded by `mcp_args` being non-empty and by
    # `operator_set_permission_mode` for the same reason the default posture below is — an
    # approver flag must not outlive the posture that asked for it.
    if mcp_args and (
        (
            operator_set_permission_mode
            and (control_overrides or {}).get("permission_mode") in APPROVER_PERMISSION_MODES
        )
        or defaults_to_approver
    ):
        cmd += ["--permission-prompt-tool", CLAUDE_PERMISSION_PROMPT_TOOL]
    if not operator_set_permission_mode:
        if yolo:
            cmd += ["--dangerously-skip-permissions"]
        else:
            # `workspace` is this repo's name for the posture, not Claude's. Claude is told
            # `manual`; what makes it "workspace" rather than "ask the operator" is the approver
            # flag emitted above, and the two must be decided together or one outlives the other.
            spelling = "manual" if default_posture == WORKSPACE_PERMISSION_MODE else default_posture
            cmd += ["--permission-mode", spelling]
    if session_id:
        cmd += ["--resume", session_id]
    if extra_flags:
        cmd += extra_flags
    cmd += ["-p", prompt]
    return cmd


def _codex_exec_mcp_args(mcp_command: Optional[List[str]]) -> List[str]:
    """The three `-c mcp_servers.agentweave.*` flags that start the Hub's MCP server for a Codex
    `exec` run (design D1). Returns `[]` when no server is configured -- `CodexExecTransport
    .inject_mcp` calls this directly; `_build_codex_command` calls it at the same position.

    Codex filters the environment inherited by dynamically configured stdio MCP servers, so only
    `CODEX_MCP_ENV_NAMES` is forwarded: Codex resolves their values from its own local environment.
    """
    if not mcp_command:
        return []
    args = ["-c", f"mcp_servers.agentweave.command={json.dumps(mcp_command[0])}"]
    args += ["-c", f"mcp_servers.agentweave.args={json.dumps(mcp_command[1:])}"]
    args += ["-c", f"mcp_servers.agentweave.env_vars={json.dumps(list(CODEX_MCP_ENV_NAMES))}"]
    return args


def _build_codex_command(
    *,
    cli: str,
    prompt: str,
    model: Optional[str],
    context_file: Optional[Path],
    session_id: Optional[str],
    yolo: bool,
    full_access: bool = False,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_args: Optional[List[str]] = None,
    restrict_spec_writes: bool = False,
) -> List[str]:
    """Build a `codex exec` invocation.

    `full_access` is the "Full access" posture, read from the operator's `permission_mode` rather
    than from `yolo`. Codex's catalog control renders nothing to argv (`ApplySpec(style="none")`),
    because on the app-server transport the posture is carried in the thread's own policy — so
    without this, the *only* thing that could reach the sandbox flag below was `yolo`, and `yolo`
    is written by one surface: setting an agent's default posture. The same posture chosen for a
    single turn through the composer left this branch selecting `workspace-write`, silently.
    Same defect as the app-server transport's, in the transport beside it.
    """
    cmd = [cli, "exec"]
    cmd += ["--json", "--skip-git-repo-check"]
    cmd += _codex_exec_mcp_args(mcp_command)
    if context_file is not None and context_file.exists():
        cmd += ["-c", f"model_instructions_file={context_file}"]
    if model:
        cmd += ["--model", model]
    if control_args:
        cmd += control_args
    if restrict_spec_writes:
        # Replaces the yolo/no-yolo branch entirely rather than layering on top of it — the two
        # are mutually exclusive Codex flags, not a value this can override in place. Appending
        # `--sandbox read-only` beside `--dangerously-bypass-approvals-and-sandbox` would ship a
        # contradictory command line, so under this restriction `yolo` is not consulted at all
        # (F4/design D6, round 2 — the restriction holds unconditionally, on both runners).
        cmd += ["--sandbox", "read-only"]
    elif yolo or full_access:
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
