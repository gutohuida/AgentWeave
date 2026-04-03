"""Session management for AgentWeave."""

from typing import Any, Dict, List, Optional

from .constants import (
    AGENT_NAME_RE,
    AGENT_RUNNER_DEFAULTS,
    DEFAULT_AGENTS,
    RUNNER_TYPES,
    SESSION_FILE,
    VALID_MODES,
)
from .utils import generate_id, load_json, now_iso, save_json


class Session:
    """Manages an inter-agent collaboration session."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """Initialize session with data."""
        self._data = data or {}

    @property
    def id(self) -> str:
        """Get session ID."""
        return self._data.get("id", "unknown")

    @property
    def name(self) -> str:
        """Get session name."""
        return self._data.get("name", "Unnamed Session")

    @property
    def mode(self) -> str:
        """Get collaboration mode."""
        return self._data.get("mode", "hierarchical")

    @property
    def principal(self) -> str:
        """Get principal agent."""
        return self._data.get("principal", "claude")

    @property
    def agents(self) -> Dict[str, Dict[str, Any]]:
        """Get agent configurations."""
        return self._data.get("agents", {})

    @property
    def agent_names(self) -> List[str]:
        """Get list of agent names in this session."""
        return list(self._data.get("agents", {}).keys())

    def get_agent_role(self, agent: str) -> str:
        """Get session role for an agent (principal/delegate/reviewer/collaborator)."""
        return self.agents.get(agent, {}).get("role", "delegate")

    def get_agent_yolo(self, agent: str) -> bool:
        """Return True if yolo mode is enabled for the agent."""
        return bool(self.agents.get(agent, {}).get("yolo", False))

    def set_agent_yolo(self, agent: str, enabled: bool) -> None:
        """Enable or disable yolo mode for an agent."""
        if agent not in self._data.get("agents", {}):
            raise ValueError(f"Agent {agent!r} not in session")
        self._data["agents"][agent]["yolo"] = enabled
        self._data["updated"] = now_iso()

    def get_runner_config(self, agent: str) -> dict:
        """Return runner config for an agent.

        Falls back to AGENT_RUNNER_DEFAULTS if not explicitly configured.
        Returns dict with 'runner', 'env_vars', and 'model' keys.
        """
        from .constants import CLAUDE_PROXY_PROVIDERS

        agent_cfg = self.agents.get(agent, {})
        runner = agent_cfg.get("runner") or AGENT_RUNNER_DEFAULTS.get(agent, "native")
        env_vars = agent_cfg.get("env_vars", {})
        model = agent_cfg.get("model")

        # If no model specified, use provider default
        if not model and runner == "claude_proxy" and agent in CLAUDE_PROXY_PROVIDERS:
            model = CLAUDE_PROXY_PROVIDERS[agent].get("model")

        return {"runner": runner, "env_vars": env_vars, "model": model}

    def set_runner_config(
        self, agent: str, runner: str, env_vars: dict, model: Optional[str] = None
    ) -> None:
        """Store runner config for an agent.

        Args:
            agent:    Agent name (must already be in session).
            runner:   One of RUNNER_TYPES.
            env_vars: Dict with ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY_VAR for
                      claude_proxy runners; empty dict for native/manual.
            model:    Optional model name for claude_proxy agents (e.g., "MiniMax-M2.5").
        """
        if runner not in RUNNER_TYPES:
            raise ValueError(f"Invalid runner type: {runner!r}. Must be one of {RUNNER_TYPES}")
        if agent not in self._data.get("agents", {}):
            raise ValueError(f"Agent {agent!r} not in session")
        self._data["agents"][agent]["runner"] = runner
        self._data["agents"][agent]["env_vars"] = env_vars
        if model:
            self._data["agents"][agent]["model"] = model
        self._data["updated"] = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self._data

    @classmethod
    def load(cls) -> Optional["Session"]:
        """Load session from file."""
        data = load_json(SESSION_FILE)
        if data:
            return cls(data)
        return None

    def save(self) -> bool:
        """Save session to file and sync to Hub if HTTP transport is active."""
        result = save_json(SESSION_FILE, self._data)
        if result:
            _push_session_to_hub(self._data)
        return result

    @classmethod
    def create(
        cls,
        name: str,
        principal: Optional[str] = None,
        mode: str = "hierarchical",
        agents: Optional[List[str]] = None,
    ) -> "Session":
        """Create a new session.

        Args:
            name:      Project/session name.
            principal: The lead agent (must be in agents list). Defaults to the
                       first agent in the agents list.
            mode:      Collaboration mode.
            agents:    List of agent names. Defaults to DEFAULT_AGENTS.
                       Any name matching AGENT_NAME_RE is accepted.
        """
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}")

        agent_list = agents if agents else DEFAULT_AGENTS
        if principal is None:
            principal = agent_list[0]

        if not AGENT_NAME_RE.match(principal):
            raise ValueError(f"Invalid principal name: {principal!r}")
        # Ensure principal is included
        if principal not in agent_list:
            agent_list = [principal] + agent_list

        # Validate each agent name
        for ag in agent_list:
            if not AGENT_NAME_RE.match(ag):
                raise ValueError(f"Invalid agent name: {ag!r}")

        agent_map = {}
        for ag in agent_list:
            if ag == principal:
                role = "principal"
            elif len(agent_list) == 2:
                role = "delegate"
            else:
                role = "collaborator"
            agent_map[ag] = {"role": role, "since": now_iso()}

        data = {
            "id": generate_id("session"),
            "name": name,
            "created": now_iso(),
            "updated": now_iso(),
            "mode": mode,
            "principal": principal,
            "agents": agent_map,
            "active_tasks": [],
            "completed_tasks": [],
            "discussions": [],
        }

        return cls(data)

    def update(self, **kwargs: Any) -> None:
        """Update session fields."""
        self._data.update(kwargs)
        self._data["updated"] = now_iso()

    def add_task(self, task_id: str) -> None:
        """Add task to active tasks."""
        tasks = self._data.get("active_tasks", [])
        if task_id not in tasks:
            tasks.append(task_id)
            self._data["active_tasks"] = tasks

    def complete_task(self, task_id: str) -> None:
        """Move task from active to completed."""
        active = self._data.get("active_tasks", [])
        completed = self._data.get("completed_tasks", [])

        if task_id in active:
            active.remove(task_id)
            completed.append(task_id)
            self._data["active_tasks"] = active
            self._data["completed_tasks"] = completed

    def get_summary(self) -> Dict[str, Any]:
        """Get session summary."""
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "principal": self.principal,
            "agents": self.agents,
            "active_tasks_count": len(self._data.get("active_tasks", [])),
            "completed_tasks_count": len(self._data.get("completed_tasks", [])),
        }


def _push_session_to_hub(session_data: Dict[str, Any]) -> None:
    """Push session config to the Hub if HTTP transport is configured.

    Silently swallows all exceptions — a failed push must never break CLI commands.
    """
    try:
        from .transport import get_transport

        transport = get_transport()
        if transport.get_transport_type() == "http":
            transport.push_session(session_data)
    except Exception:
        pass
