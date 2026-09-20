"""Session management for AgentWeave."""

from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    AGENT_RUNNER_DEFAULTS,
    DEFAULT_AGENTS,
    RUNNER_TYPES,
    SESSION_FILE,
    VALID_MODES,
    is_valid_agent_name,
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

    # DEAD (2026-09-20): get_agent_role, hub_client and get_agent_hub_client (lines 62-80).
    # Why: the role subsystem was deleted (CLAUDE.md, Architecture rules) and no module in
    #   src/agentweave calls any of the three — the only repo-wide hits are their own
    #   definitions, tests/test_session.py:58, and a prose reference in hub/hub/launchability.py:478.
    # Live equivalent: roles — none, deliberately. hub_client — the Hub reads the key itself
    #   from ProjectSession.data (hub/hub/launchability.py:476), never through this class.
    # Removal: the class's remaining read accessors are reached only from diagnostics functions
    #   that are themselves dead (diagnostics.py:843, :1119) — see their DEAD blocks; these three
    #   go with tests/test_session.py:54.
    def get_agent_role(self, agent: str) -> str:
        """Get session role for an agent (principal/delegate/reviewer/collaborator)."""
        return self.agents.get(agent, {}).get("role", "delegate")

    @property
    def hub_client(self) -> str:
        """Get session-level hub_client mode (auto/cli/mcp). Defaults to 'auto'."""
        from .constants import HUB_CLIENT_DEFAULT

        return self._data.get("hub_client", HUB_CLIENT_DEFAULT)

    def get_agent_hub_client(self, agent: str) -> str:
        """Get hub_client mode for an agent, with per-agent override of session default."""
        from .constants import HUB_CLIENT_DEFAULT

        agent_override = self.agents.get(agent, {}).get("hub_client")
        if agent_override:
            return agent_override
        return self._data.get("hub_client", HUB_CLIENT_DEFAULT)

    def get_agent_yolo(self, agent: str) -> bool:
        """Return True if yolo mode is enabled for the agent."""
        return bool(self.agents.get(agent, {}).get("yolo", False))

    # DEAD (2026-09-20): nothing ever sets yolo through this class.
    # Why: `set_agent_yolo` has zero references in the whole repository — not src/agentweave,
    #   not tests/, not hub/. Only its definition here.
    # Live equivalent: the Hub owns the posture (hub/hub/runner_commands.py's yolo argument,
    #   set from Agent/conversation state), not session.json.
    # Removal: the read side `get_agent_yolo` above IS live (diagnostics.py:877) — keep it.
    def set_agent_yolo(self, agent: str, enabled: bool) -> None:
        """Enable or disable yolo mode for an agent."""
        if agent not in self._data.get("agents", {}):
            raise ValueError(f"Agent {agent!r} not in session")
        self._data["agents"][agent]["yolo"] = enabled
        self._data["updated"] = now_iso()

    def get_runner_config(self, agent: str) -> dict:
        """Return runner config for an agent.

        Falls back to AGENT_RUNNER_DEFAULTS if not explicitly configured.
        Returns dict with 'runner', 'env_vars', 'model', 'cli', and 'read_only' keys.
        """
        from .constants import CLAUDE_PROXY_PROVIDERS

        agent_cfg = self.agents.get(agent, {})
        runner = agent_cfg.get("runner") or AGENT_RUNNER_DEFAULTS.get(agent, "native")
        env_vars = agent_cfg.get("env_vars", {})
        model = agent_cfg.get("model")
        cli = agent_cfg.get("cli")
        read_only = bool(agent_cfg.get("read_only", False))

        # If no model specified, use provider default
        if not model and runner == "claude_proxy" and agent in CLAUDE_PROXY_PROVIDERS:
            model = CLAUDE_PROXY_PROVIDERS[agent].get("model")

        return {
            "runner": runner,
            "env_vars": env_vars,
            "model": model,
            "cli": cli,
            "read_only": read_only,
        }

    def get_runner_options(self, agent: str) -> dict:
        """Return runner-specific options for an agent, defaulting to {}."""
        return self.agents.get(agent, {}).get("runner_options", {}) or {}

    # DEAD (2026-09-20): no CLI command configures a runner any more.
    # Why: the only reference in the repository outside this file is a fixture call in
    #   tests/test_diagnostics.py:95; none of the five surviving cmd_* functions
    #   (cli.py:80/130/162/1161/1303) reaches it, and RUNNER_TYPES it validates against is a
    #   list of nine kinds a Runner row cannot hold (hub/hub/db/models.py:311).
    # Live equivalent: Runner rows created through the Hub (hub/hub/api/v1/runners.py).
    # Removal: check tests/test_diagnostics.py:95 still has a way to build its fixture.
    def set_runner_config(
        self, agent: str, runner: str, env_vars: dict, model: Optional[str] = None
    ) -> None:
        """Store runner config for an agent.

        Args:
            agent:    Agent name (must already be in session).
            runner:   One of RUNNER_TYPES.
            env_vars: Dict with ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY_VAR for
                      claude_proxy runners; empty dict for native/manual.
            model:    Optional model name to pass to runners that support model selection.
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

    # DEAD (2026-09-20): nothing in the product writes session.json, or pushes it to a Hub.
    # Why: `Session(...)` and `Session.create(...)` are constructed only under tests/ (test_session.py,
    #   test_diagnostics.py, test_config.py), and no `.save()` call exists in src/agentweave — the
    #   only `.save()` hits there are jobs.py:351/362 on Job. `2026-08-03-single-runtime` removed the
    #   CLI push path and the watchdog that re-pushed it; hub/hub/api/v1/session_sync.py:9-14 records
    #   the same fact from the receiving end.
    # Live equivalent: none. `Session.load()` above is not a live read path either — its only
    #   callers are diagnostics.py:843 and :1119, both inside functions `collect_diagnostics`
    #   never calls (see their DEAD blocks), plus config.py, which is dead as a whole.
    # Removal: `create` (below) builds the deleted vocabulary — principal, role, mode,
    #   active_tasks, discussions — and goes with it; tests/test_session.py exercises both.
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

        if not is_valid_agent_name(principal):
            raise ValueError(f"Invalid principal name: {principal!r}")
        # Ensure principal is included
        if principal not in agent_list:
            agent_list = [principal] + agent_list

        # Validate each agent name
        for ag in agent_list:
            if not is_valid_agent_name(ag):
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

    # DEAD (2026-09-20): the whole run below — set_principal, add_task, complete_task,
    # get_summary, sync_agents, remove_agent — has no caller in the product.
    # Why: repo-wide greps over src/agentweave, tests/, hub/ and scripts/ return zero hits for
    #   set_principal, complete_task, get_summary and remove_agent (definitions aside), and
    #   `Session.add_task` zero (the `add_task` hits are hub/hub/api/v1/tasks.py:1634's unrelated
    #   add_task_dependency); sync_agents appears only in tests/test_session.py:101-126. They are
    #   the deleted principal/role/session-task vocabulary (CLAUDE.md, "When compacting").
    # Live equivalent: tasks and rosters live in the Hub (hub/hub/api/v1/tasks.py, agents.py).
    # Removal: they mutate `self._data` only, and nothing persists it (see `save` above), so
    #   deleting them changes no stored state; tests/test_session.py:91-126 goes with sync_agents.
    def set_principal(self, name: str) -> None:
        """Set the principal agent, updating both the top-level field and agent role
        entries."""
        if name not in self._data.get("agents", {}):
            raise ValueError(f"Agent {name!r} not in session")
        # Demote old principal
        old = self._data.get("principal")
        if old and old in self._data["agents"] and old != name:
            self._data["agents"][old]["role"] = "delegate"
        # Promote new principal
        self._data["agents"][name]["role"] = "principal"
        self._data["principal"] = name
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

    def sync_agents(
        self, declared_agents: Dict[str, Dict[str, Any]]
    ) -> Tuple[List[str], List[str], List[str]]:
        """Sync session agents with declared configuration from agentweave.yml.

        Args:
            declared_agents: Dict mapping agent name to agent config dict.
                Each config dict may contain: runner, model, yolo, read_only, env,
                base_url

        Returns:
            Tuple of (added_agents, updated_agents, orphaned_agents)
        """
        added: List[str] = []
        updated: List[str] = []

        # Add or update agents from YAML
        for agent_name, config in declared_agents.items():
            is_new = agent_name not in self._data.get("agents", {})
            if is_new:
                # New agent - add to session
                self._data["agents"][agent_name] = {
                    "role": "delegate",
                    "since": self._now(),
                }
                added.append(agent_name)

            # Update agent configuration
            agent_data = self._data["agents"][agent_name]
            was_updated = False

            if (
                "runner" in config
                and config["runner"]
                and agent_data.get("runner") != config["runner"]
            ):
                agent_data["runner"] = config["runner"]
                was_updated = True
            if "model" in config:
                new_model = config.get("model")
                if new_model:
                    if agent_data.get("model") != new_model:
                        agent_data["model"] = new_model
                        was_updated = True
                elif "model" in agent_data:
                    del agent_data["model"]
                    was_updated = True
            if "runner_options" in config and config["runner_options"]:
                new_opts = dict(config["runner_options"])
                if agent_data.get("runner_options") != new_opts:
                    agent_data["runner_options"] = new_opts
                    was_updated = True
            if "cli" in config and config["cli"]:
                new_cli = str(config["cli"])
                if agent_data.get("cli") != new_cli:
                    agent_data["cli"] = new_cli
                    was_updated = True
            elif "cli" in agent_data:
                # Field removed from yml — drop it from session too so an old
                # override doesn't outlive its declaration.
                del agent_data["cli"]
                was_updated = True
            if "yolo" in config:
                new_yolo = bool(config["yolo"])
                if agent_data.get("yolo") != new_yolo:
                    agent_data["yolo"] = new_yolo
                    was_updated = True
            if "read_only" in config:
                new_read_only = bool(config["read_only"])
                if agent_data.get("read_only") != new_read_only:
                    agent_data["read_only"] = new_read_only
                    was_updated = True
            if "env" in config and config["env"]:
                if config.get("base_url"):
                    # claude_proxy pattern: first env entry is the API key var;
                    # store it as ANTHROPIC_API_KEY_VAR so runner.py can resolve it.
                    new_env_vars = {
                        "ANTHROPIC_BASE_URL": config["base_url"],
                        "ANTHROPIC_API_KEY_VAR": config["env"][0],
                    }
                else:
                    # Convert env list to env_vars dict format used in session.json
                    # The values are the env var names themselves (to be resolved at runtime)
                    new_env_vars = {var: var for var in config["env"]}
                if agent_data.get("env_vars") != new_env_vars:
                    agent_data["env_vars"] = new_env_vars
                    was_updated = True
            elif config.get("base_url"):
                # base_url with no env list — URL only, no API key var
                new_env_vars = {"ANTHROPIC_BASE_URL": config["base_url"]}
                if agent_data.get("env_vars") != new_env_vars:
                    agent_data["env_vars"] = new_env_vars
                    was_updated = True

            # Track as updated if modified (but not if just added)
            if not is_new and was_updated:
                updated.append(agent_name)

        # Find orphaned agents (in session but not in YAML)
        current_agents = set(self.agent_names)
        declared_names = set(declared_agents.keys())
        orphaned = list(current_agents - declared_names)

        self._data["updated"] = self._now()
        return added, updated, orphaned

    def remove_agent(self, name: str) -> bool:
        """Remove an agent from the session by name."""
        if name in self._data.get("agents", {}):
            del self._data["agents"][name]
            self._data["updated"] = self._now()
            return True
        return False

    def _now(self) -> str:
        """Get current ISO timestamp."""
        from .utils import now_iso

        return now_iso()


# DEAD (2026-09-20): no session is ever pushed to a Hub from here.
# Why: its only caller is `Session.save()` (line 184), which itself has no caller in
#   src/agentweave — see the DEAD block above `save`. The receiving endpoint says the same from
#   the other side: hub/hub/api/v1/session_sync.py:9-14 records that the CLI push path and the
#   watchdog that used it both ceased to exist in `2026-08-03-single-runtime`.
# Live equivalent: none. The Hub is authoritative for the roster (hub/hub/api/v1/agents.py).
# Removal: `HttpTransport.push_session` (transport/http.py:549) and its abstract declaration
#   (transport/base.py:80) become unreachable with it; POST /session/sync keeps test callers.
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
