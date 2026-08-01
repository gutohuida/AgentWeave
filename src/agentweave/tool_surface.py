"""Agent identity binding and tool-access-path resolution.

Two mechanisms specified by ``agent-tool-surface`` (openspec change
``hub-native-experience``, phase 4):

- **Identity** is established once, at spawn, by whoever starts an agent's process — the
  Hub's native runtime (``agent_trigger.py``), the watchdog's ping spawn, or a human via
  ``agentweave switch``/``agentweave run``. It is never asserted by a tool-call parameter
  or a CLI flag; a process that was not spawned with a bound identity has none, and any
  tool that would cause an attributed effect must refuse rather than fall back to
  ``"unknown"`` or ``"user"``.
- **Access path** (MCP tool-protocol server vs. plain CLI commands) is probed per runner
  per environment rather than configured by hand. ``hub_client`` in session.json becomes
  the operator's explicit override; when unset ("auto"), the path is probed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Dict, Optional, Tuple

AW_AGENT_IDENTITY_ENV = "AW_AGENT_IDENTITY"


class UnboundIdentityError(RuntimeError):
    """Raised when a tool that causes an attributed effect has no bound agent identity."""


def bound_identity() -> str:
    """Return the identity the Hub/watchdog/switch bound to this process's environment.

    Raises ``UnboundIdentityError`` rather than defaulting to a placeholder — an effect
    with no attributable agent must be refused, not silently recorded against
    ``"unknown"`` (agent-tool-surface spec: "There is no unattributed effect").
    """
    identity = os.environ.get(AW_AGENT_IDENTITY_ENV, "").strip()
    if not identity:
        raise UnboundIdentityError(
            f"No bound agent identity ({AW_AGENT_IDENTITY_ENV} is not set in this "
            "process's environment). This process was not spawned as a specific agent — "
            "run `agentweave switch <agent>` first, or launch via the Hub or the "
            "watchdog, both of which set this automatically."
        )
    return identity


# ---------------------------------------------------------------------------
# Access path: tool-protocol (MCP) vs. plain CLI commands
# ---------------------------------------------------------------------------

# Runners this module knows how to probe for a live "agentweave" MCP registration via
# "<cli> mcp list". Deliberately excludes opencode (file-based registration, no `mcp
# list` subcommand), kimi/manual (unverified), and copilot (task 4.3: "Claude Code and
# Codex first; Copilot after").
PROBEABLE_RUNNERS = {"claude", "claude_proxy", "native", "codex"}

_PROBE_TTL_SECONDS = 300.0
_probe_cache: Dict[str, Tuple[bool, float]] = {}


def probe_mcp_registered(cli: str) -> bool:
    """Best-effort check: is the ``agentweave`` MCP server actually registered for
    *cli* in the current environment (as opposed to merely theoretically supported)?

    Cached for ``_PROBE_TTL_SECONDS`` per CLI binary so repeated watchdog pings don't
    re-shell out on every message.
    """
    now = time.monotonic()
    cached = _probe_cache.get(cli)
    if cached is not None and now - cached[1] < _PROBE_TTL_SECONDS:
        return cached[0]

    if not cli or shutil.which(cli) is None:
        _probe_cache[cli] = (False, now)
        return False

    try:
        result = subprocess.run(
            [cli, "mcp", "list"],
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            timeout=10,
        )
        available = result.returncode == 0 and "agentweave" in (result.stdout or "").lower()
    except Exception:
        available = False

    _probe_cache[cli] = (available, now)
    return available


def resolve_access_path(runner: str, cli: str, override: Optional[str] = None) -> str:
    """Return ``"mcp"`` or ``"cli"`` — the access path an agent of *runner* should use.

    *override* is the operator's explicit ``hub_client`` setting (``"cli"``/``"mcp"``);
    when it is unset or ``"auto"``, the path is probed rather than assumed. Runners this
    module cannot yet probe default to ``"cli"`` — the guaranteed-available path — rather
    than assuming an unverified tool-protocol server is reachable.
    """
    if override in ("cli", "mcp"):
        return override
    if runner not in PROBEABLE_RUNNERS:
        return "cli"
    return "mcp" if probe_mcp_registered(cli) else "cli"


def access_path_notice(access_path: str) -> str:
    """One line telling the agent which access path is in use this turn.

    Per spec: "The agent is told which path to use" — never both, never neither.
    """
    if access_path == "mcp":
        return (
            "[AgentWeave] Tool access: the `agentweave` MCP tools are available — call "
            "send_message / create_task / update_task / ask_user directly."
        )
    return (
        "[AgentWeave] Tool access: MCP tools are not available in this environment. Use "
        "`agentweave` CLI commands instead — e.g. `agentweave msg send --to <agent> -m "
        '"..."`, `agentweave task create --title "..."`, `agentweave task update <id> '
        '--status <status>`, `agentweave question ask -q "..."`, `agentweave inbox '
        "--agent <you> --mark-read`."
    )
