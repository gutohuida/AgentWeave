"""Session management for AgentWeave."""

from typing import Any, Dict, List, Optional

from .constants import AGENT_NAME_RE, DEFAULT_AGENTS, SESSION_FILE, VALID_MODES
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
        """Save session to file."""
        return save_json(SESSION_FILE, self._data)

    @classmethod
    def create(
        cls,
        name: str,
        principal: str = "claude",
        mode: str = "hierarchical",
        agents: Optional[List[str]] = None,
    ) -> "Session":
        """Create a new session.

        Args:
            name:      Project/session name.
            principal: The lead agent (must be in agents list).
            mode:      Collaboration mode.
            agents:    List of agent names. Defaults to DEFAULT_AGENTS.
                       Any name matching AGENT_NAME_RE is accepted.
        """
        if not AGENT_NAME_RE.match(principal):
            raise ValueError(f"Invalid principal name: {principal!r}")
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}")

        agent_list = agents if agents else DEFAULT_AGENTS
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

    def update(self, **kwargs) -> None:
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
