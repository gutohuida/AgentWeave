"""Per-agent launchability probe — is the runner's CLI present, authorized, and runnable?

Deliberately reimplemented rather than imported from the CLI's
``agentweave.diagnostics.check_agent_readiness``: the Hub has no dependency on the
``agentweave-ai`` package (it must be probeable even when installed standalone), so this
mirrors that logic's CLI-presence and authorization checks against a small, independent
runner->CLI table instead of ``agentweave.constants.RUNNER_CONFIGS``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Runner -> CLI binary name. Mirrors the "cli" field of RUNNER_CONFIGS in
# agentweave.constants (kept independent — see module docstring).
RUNNER_CLI: Dict[str, Optional[str]] = {
    "claude": "claude",
    "native": None,  # falls back to the agent name
    "claude_proxy": "claude",
    "kimi": "kimi",
    "opencode": "opencode",
    "codex": "codex",
    "codex_mcp": "codex",
    "manual": None,
    "copilot": "copilot",
}


def probe_agent(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a launchability verdict for one agent.

    ``config`` is the agent's merged runner configuration — the session.json
    ``agents.<name>`` entry overlaid with any self-registered ``Agent.config`` — the same
    shape the CLI's ``session.get_runner_config()`` returns.

    Returns a dict with ``runner``, ``cli``, ``present`` (binary found), ``authorized``
    (known auth requirements satisfied), ``runnable`` (both, and not blocked by manual
    mode), and ``reason`` (stated cause when not runnable, else ``None``).
    """
    runner = config.get("runner", "native")

    if runner == "manual":
        return {
            "runner": runner,
            "cli": None,
            "present": False,
            "authorized": True,
            "runnable": False,
            "reason": "Runner is set to manual — no CLI to launch automatically.",
        }

    cli_override = config.get("cli")
    cli = str(cli_override) if cli_override else (RUNNER_CLI.get(runner) or name)

    if cli_override:
        present = os.path.isfile(cli_override) and os.access(cli_override, os.X_OK)
        missing_reason = f"Pinned runner CLI {cli_override!r} is not an executable file."
    else:
        present = shutil.which(cli) is not None
        missing_reason = f"Runner CLI {cli!r} was not found in PATH."

    authorized = True
    auth_reason: Optional[str] = None
    if runner == "claude_proxy":
        env_vars = config.get("env_vars") or {}
        api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
        base_url = env_vars.get("ANTHROPIC_BASE_URL")
        if not base_url or not api_key_var:
            authorized = False
            auth_reason = "Proxy runner is missing ANTHROPIC_BASE_URL or ANTHROPIC_API_KEY_VAR."
        elif not os.environ.get(api_key_var):
            authorized = False
            auth_reason = (
                f"Required proxy API key variable ${api_key_var} is not set "
                "in the Hub's environment."
            )
    elif runner == "copilot":
        has_token = bool(
            os.environ.get("COPILOT_GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )
        if not has_token:
            authorized = False
            auth_reason = (
                "No GitHub auth token found (COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN)."
            )

    if not present:
        reason = missing_reason
    elif not authorized:
        reason = auth_reason
    else:
        reason = None

    return {
        "runner": runner,
        "cli": cli,
        "present": present,
        "authorized": authorized,
        "runnable": present and authorized,
        "reason": reason,
    }


def resolve_agent_env(runner: str, config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build the subprocess environment for spawning *runner*, resolving provider
    credentials from the Hub's own process environment (task 3.11).

    The Hub resolves `env_vars` indirection (`ANTHROPIC_API_KEY_VAR` names an env var
    to read, plain values are passed through, and a value equal to its own key name is
    treated as another env-var-name placeholder) itself, at spawn time.

    Returns `None` when no override is needed at all (`PtySession.spawn` then inherits
    the Hub process's own environment unchanged); otherwise a full environment dict —
    the Hub's own `os.environ`, merged with the agent's resolved `env_vars`.
    """
    env_vars = config.get("env_vars") or {}
    proc_env: Optional[Dict[str, str]] = None
    if env_vars:
        proc_env = dict(os.environ)
        proc_env.update(env_vars)
        api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
        if api_key_var:
            resolved = os.environ.get(api_key_var, "")
            if resolved:
                proc_env["ANTHROPIC_API_KEY"] = resolved
            else:
                # Key var declared but not set in the Hub's own environment — clear any
                # inherited key so the failure is an explicit 401, not a silent wrong key.
                proc_env.pop("ANTHROPIC_API_KEY", None)
        for var_name, value in env_vars.items():
            if var_name in ("ANTHROPIC_API_KEY_VAR", "ANTHROPIC_BASE_URL"):
                continue
            if value == var_name:
                resolved = os.environ.get(var_name)
                if resolved:
                    proc_env[var_name] = resolved
                else:
                    proc_env.pop(var_name, None)

    # Native Claude must not silently inherit a proxy's ANTHROPIC_BASE_URL from
    # whatever shell the Hub itself happened to be started from — its own auth and
    # endpoint selection are Claude Code's to make, not the Hub's.
    if runner == "claude":
        base = proc_env if proc_env is not None else os.environ
        if base.get("ANTHROPIC_BASE_URL"):
            proc_env = dict(base)
            proc_env.pop("ANTHROPIC_BASE_URL", None)

    return proc_env


# ---------------------------------------------------------------------------
# Access path: tool-protocol (MCP) vs. plain CLI commands
#
# Independent mirror of agentweave.tool_surface's probing logic (same reason this whole
# module is independent of agentweave.constants.RUNNER_CONFIGS — see module docstring).
# Native runtime spawns agents on the Hub host itself, so probing "<cli> mcp list" here
# checks the same CLI installation the Hub is about to launch.
# ---------------------------------------------------------------------------

PROBEABLE_RUNNERS = {"claude", "claude_proxy", "native", "codex"}
MCP_INJECTABLE_RUNNERS = PROBEABLE_RUNNERS

_PROBE_TTL_SECONDS = 300.0
_probe_cache: Dict[str, Tuple[bool, float]] = {}


def probe_mcp_registered(cli: str) -> bool:
    """Best-effort check: is the ``agentweave`` MCP server actually registered for
    *cli* on the Hub host, as opposed to merely theoretically supported?
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
    """Choose the per-run path now that the Hub injects its canonical server."""
    del cli
    if override == "cli":
        return "cli"
    if runner not in MCP_INJECTABLE_RUNNERS:
        return "cli"
    return "mcp"


def access_path_notice(access_path: str) -> str:
    """One line telling the agent which access path is in use this turn."""
    if access_path == "mcp":
        return (
            "[AgentWeave] Tool access: the `agentweave` MCP tools are available — call "
            "send_message / create_task / update_task / ask_user directly."
        )
    return (
        "[AgentWeave] Tool access: MCP tools are not available in this environment. Use "
        "`agentweave` CLI commands instead — e.g. `agentweave msg send --to <agent> -m "
        '"..."`, `agentweave task create --title "..."`, `agentweave task update <id> '
        '--status <status>`, `agentweave question ask -q "..."`, or `agentweave agent '
        'request <name> --template <template> --task "..."`. Inbound content is already '
        "included in this turn; no retrieval command is needed."
    )


async def get_agent_config(project_id: str, agent: str, db: AsyncSession) -> Dict[str, Any]:
    """Return the merged runner config `probe_agent` expects for one agent.

    Merges two sources, in increasing priority: the session-synced `agents.<name>` entry
    (session.json, pushed by the CLI — has `runner`/`model`/`cli`/`env_vars`/`yolo` for
    CLI-configured agents) and any self-registered `Agent.config` JSON.
    """
    from .db.models import Agent, ProjectSession

    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    session_data = row.data if row else {}
    session_agents_meta = (session_data.get("agents", {})) or {}
    meta = dict(session_agents_meta.get(agent, {}))
    if "hub_client" not in meta and session_data.get("hub_client"):
        # Session-wide default (session.json's top-level `hub_client`), same fallback
        # order as the CLI's Session.get_agent_hub_client — a per-agent override wins.
        meta["hub_client"] = session_data["hub_client"]

    agent_result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_result.scalars().first()
    if agent_row and agent_row.config:
        meta = {**agent_row.config, **meta}
    return meta
