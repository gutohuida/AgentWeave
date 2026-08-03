"""Command-line construction for Hub-spawned agent runs — Claude Code and Codex CLI only.

The Hub owns command construction independently from the lifecycle CLI. Every flag below was
verified against the supported runner CLIs. Claude runs through `PtySession`; Codex's
non-interactive JSONL mode runs through `PipeSession` (see `pty_runner.py`).

Kimi, OpenCode, and Copilot are explicitly out of scope for this task (per-runner command
construction for them is deferred) — `build_command` raises `UnsupportedRunnerError` for
anything else so the caller gets a clear, stated reason rather than a silently wrong command.

Yolo-enabled Claude runs receive `--dangerously-skip-permissions`; headless Hub execution has no
interactive terminal where an operator could answer a permission prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

SUPPORTED_RUNNERS = ("claude", "claude_proxy", "native", "codex")


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
) -> List[str]:
    """Build the full CLI invocation for one turn.

    ``cli`` is the resolved binary name/path (see `launchability.RUNNER_CLI` /
    `pty_runner.resolve_executable`) — this function only builds the argument list.
    ``session_id`` set means resume; unset means a new session. Raises
    ``UnsupportedRunnerError`` for any runner other than claude/claude_proxy/native/codex.
    """
    if runner == "codex":
        return _build_codex_command(
            cli=cli,
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=session_id,
            yolo=yolo,
            mcp_command=mcp_command,
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
) -> List[str]:
    cmd = [cli, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
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
    if yolo:
        cmd += ["--dangerously-skip-permissions"]
    if session_id:
        cmd += ["--resume", session_id]
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
    if yolo:
        cmd += ["--dangerously-bypass-approvals-and-sandbox"]
    else:
        cmd += ["--sandbox", "workspace-write"]
    # `--sandbox` belongs to `codex exec`, not its `resume` subcommand. Keep all
    # exec-level options before `resume`; newer Codex releases reject a sandbox
    # flag placed after the subcommand with "unexpected argument '--sandbox'".
    if session_id:
        cmd += ["resume", session_id]
    cmd += [prompt]
    return cmd
