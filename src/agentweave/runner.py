"""Runner helpers: resolve per-agent env vars and build Claude proxy commands.

Shared between cli.py (switch/run commands) and watchdog.py (auto-ping).
"""

import json
import os
from typing import TYPE_CHECKING, Dict, List, Optional

from .constants import AGENTS_DIR

if TYPE_CHECKING:
    from .session import Session


def get_agent_env(session: "Session", agent: str) -> Dict[str, str]:
    """Return env var overrides needed to run a claude_proxy agent.

    Returns an empty dict for native or manual runner agents, or when the
    required API key env var is not set in the current shell environment.
    Callers should warn the user if the returned dict is empty but the agent
    is configured as claude_proxy.
    """
    config = session.get_runner_config(agent)
    if config.get("runner") != "claude_proxy":
        return {}
    env_vars = config.get("env_vars", {})
    base_url = env_vars.get("ANTHROPIC_BASE_URL", "")
    api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR", "")
    if not base_url or not api_key_var:
        return {}
    api_key = os.environ.get(api_key_var, "")
    if not api_key:
        return {}
    return {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_API_KEY": api_key,
    }


def get_missing_api_key_var(session: "Session", agent: str) -> Optional[str]:
    """Return the name of the unset API key env var for a claude_proxy agent, or None."""
    config = session.get_runner_config(agent)
    if config.get("runner") != "claude_proxy":
        return None
    api_key_var = config.get("env_vars", {}).get("ANTHROPIC_API_KEY_VAR", "")
    if api_key_var and not os.environ.get(api_key_var):
        return api_key_var
    return None


def get_claude_session_id(agent: str) -> Optional[str]:
    """Load saved Claude session ID for an agent from .agentweave/agents/<agent>-session.json."""
    session_file = AGENTS_DIR / f"{agent}-session.json"
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        return data.get("session_id")
    except Exception:
        return None


def save_claude_session_id(agent: str, session_id: str) -> None:
    """Persist Claude session ID for an agent to .agentweave/agents/<agent>-session.json."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = AGENTS_DIR / f"{agent}-session.json"
    session_file.write_text(json.dumps({"session_id": session_id}))


def build_claude_proxy_cmd(
    agent: str,
    prompt: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
) -> List[str]:
    """Build the Claude CLI command for a claude_proxy agent.

    Uses the same --output-format stream-json flag as native claude pings so the
    watchdog can parse JSONL output and extract the session_id for resumption.

    Args:
        agent:      Agent name
        prompt:     The prompt to send
        session_id: Optional session ID for --resume
        model:      Optional model name to pass via --model flag
    """
    cmd = ["claude", "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]
    return cmd
