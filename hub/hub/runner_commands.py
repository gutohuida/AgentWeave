"""Command-line construction for Hub-spawned agent runs — Claude Code and Codex CLI only.

Mirrors `agentweave.watchdog._agent_ping_cmd`'s `claude`/`claude_proxy`/`native` and `codex`
branches, reimplemented here for the same reason as `launchability.py` and
`runner_events.py`: the Hub has no dependency on the `agentweave-ai` package. Every flag
below was verified live against the CLIs actually installed on this machine (Claude Code
2.1.220, codex-cli 0.146.0) — new-session and `--resume` invocations for both, spawned
through the real `PtySession` (see `pty_runner.py`), not just a plain shell.

Kimi, OpenCode, and Copilot are explicitly out of scope for this task (per-runner command
construction for them is deferred) — `build_command` raises `UnsupportedRunnerError` for
anything else so the caller gets a clear, stated reason rather than a silently wrong command.

One deliberate divergence from the watchdog: `_agent_ping_cmd` never passes a permission-
bypass flag for claude/claude_proxy/native, even when the agent's `yolo` flag is enabled —
confirmed by reading `agentweave/watchdog.py` in full; only codex/copilot/kimi apply yolo.
`cli.py:4407`'s yolo-enable hint even claims `--dangerously-skip-permissions` "will be used"
for claude, but nothing in the watchdog actually passes it. That gap makes a yolo-enabled
claude agent hang on file-edit permission prompts with no human present to answer them —
harmless for the watchdog (a human is usually nearby) but fatal for a headless Hub-spawned
run. This module passes `--dangerously-skip-permissions` when yolo is enabled for claude,
fixing that gap rather than reproducing it, since this is new code with no regression risk
to existing users.
"""

from __future__ import annotations

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
        )
    if runner in ("claude", "claude_proxy", "native"):
        return _build_claude_command(
            cli=cli,
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=session_id,
            yolo=yolo,
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
) -> List[str]:
    cmd = [cli, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    if context_file is not None and context_file.exists():
        cmd += ["--append-system-prompt-file", str(context_file)]
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
) -> List[str]:
    cmd = [cli, "exec"]
    if session_id:
        cmd += ["resume", session_id]
    cmd += ["--json", "--skip-git-repo-check"]
    if context_file is not None and context_file.exists():
        cmd += ["-c", f"model_instructions_file={context_file}"]
    if model:
        cmd += ["--model", model]
    if yolo:
        cmd += ["--dangerously-bypass-approvals-and-sandbox"]
    else:
        cmd += ["--sandbox", "workspace-write"]
    cmd += [prompt]
    return cmd
