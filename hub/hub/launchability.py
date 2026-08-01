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
from typing import Any, Dict, Optional

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
    (known auth requirements satisfied), ``runnable`` (both, and not blocked by pilot/manual
    mode), and ``reason`` (stated cause when not runnable, else ``None``).
    """
    runner = config.get("runner", "native")
    pilot = bool(config.get("pilot", False))

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

    if pilot:
        reason = "Agent is in pilot mode; automatic execution is disabled."
    elif not present:
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
        "runnable": present and authorized and not pilot,
        "reason": reason,
    }


def resolve_agent_env(runner: str, config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build the subprocess environment for spawning *runner*, resolving provider
    credentials from the Hub's own process environment (task 3.11).

    Closes the gap that used to require `eval $(agentweave switch <agent>)` in a
    terminal before a `claude_proxy` agent could actually authenticate — the Hub now
    resolves the same `env_vars` indirection (`ANTHROPIC_API_KEY_VAR` names an env var
    to read, plain values are passed through, and a value equal to its own key name is
    treated as another env-var-name placeholder) itself, at spawn time.

    Deliberately reimplemented rather than imported from `agentweave.watchdog`'s
    `_prepare_agent_env`/`_prepare_runner_env` (which this mirrors exactly) — see this
    module's own docstring on why the Hub never hard-depends on the CLI package.

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


async def get_agent_config(project_id: str, agent: str, db: AsyncSession) -> Dict[str, Any]:
    """Return the merged runner config `probe_agent` expects for one agent.

    Merges three sources, in increasing priority: the session-synced `agents.<name>` entry
    (session.json, pushed by the CLI — has `runner`/`model`/`cli`/`env_vars`/`yolo`/`pilot`
    for CLI-configured agents), any self-registered `Agent.config` JSON, and — separately,
    since it lives in its own column rather than either JSON blob — `Agent.pilot`. That last
    merge matters: `register-session` and `POST /agents/{name}/pilot` set pilot mode by
    writing `Agent.pilot` directly, never `Agent.config` or session.json, so an agent that
    became a pilot only through those two endpoints would otherwise never be recognized as
    one here.
    """
    from .db.models import Agent, ProjectSession

    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    session_agents_meta = (row.data.get("agents", {}) if row else {}) or {}
    meta = dict(session_agents_meta.get(agent, {}))

    agent_result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_result.scalars().first()
    if agent_row:
        if agent_row.config:
            meta = {**agent_row.config, **meta}
        # OR'd rather than overridden either way: treating an agent as a pilot when either
        # source says so is the safe default — the wrong direction to get wrong is running
        # a pilot agent automatically, not the reverse.
        meta["pilot"] = bool(meta.get("pilot")) or bool(agent_row.pilot)
    return meta
