"""Configuration management for agentweave.yml.

Provides loading, validation, and generation of the declarative configuration file
that serves as the single source of truth for project settings, agents, and jobs.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from .constants import RUNNER_TYPES, VALID_MODES

# Path to agentweave.yml at project root
AGENTWEAVE_YML_PATH = Path("agentweave.yml")


class ConfigValidationError(Exception):
    """Raised when agentweave.yml validation fails."""

    def __init__(self, message: str, line: Optional[int] = None):
        self.line = line
        if line:
            super().__init__(f"Line {line}: {message}")
        else:
            super().__init__(message)


@dataclass
class AgentConfig:
    """Configuration for a single agent."""

    runner: str = "claude"
    model: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    yolo: bool = False
    pilot: bool = False
    base_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {"runner": self.runner}
        if self.model:
            result["model"] = self.model
        if self.roles:
            result["roles"] = self.roles
        if self.env:
            result["env"] = self.env
        if self.yolo:
            result["yolo"] = True
        if self.pilot:
            result["pilot"] = True
        if self.base_url:
            result["base_url"] = self.base_url
        return result


@dataclass
class JobConfig:
    """Configuration for a scheduled job."""

    schedule: str
    agent: str
    prompt: str
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {
            "schedule": self.schedule,
            "agent": self.agent,
            "prompt": self.prompt,
        }
        if not self.enabled:
            result["enabled"] = False
        return result


@dataclass
class HubConfig:
    """Configuration for Hub connection."""

    url: str = "http://localhost:8000"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"url": self.url}


@dataclass
class ProjectConfig:
    """Configuration for project metadata."""

    name: str = "Unnamed Project"
    mode: str = "hierarchical"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"name": self.name, "mode": self.mode}


@dataclass
class AgentWeaveConfig:
    """Root configuration for agentweave.yml."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    hub: HubConfig = field(default_factory=HubConfig)
    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    jobs: Optional[Dict[str, JobConfig]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {
            "project": self.project.to_dict(),
            "hub": self.hub.to_dict(),
            "agents": {name: cfg.to_dict() for name, cfg in self.agents.items()},
        }
        if self.jobs is not None:
            result["jobs"] = {name: cfg.to_dict() for name, cfg in self.jobs.items()}
        return result


def _validate_cron(expr: str) -> bool:
    """Validate a cron expression.

    Supports standard 5-field cron (minute hour day month weekday).
    """
    # Basic cron pattern: 5 fields separated by spaces
    # Each field can be: number, *, */n, n-m, n-m/s, or comma-separated values
    parts = expr.split()
    if len(parts) != 5:
        return False

    # Simple regex for each field
    field_pattern = re.compile(
        r"^(\*|\*\/\d+|\d+|\d+-\d+|\d+-\d+\/\d+|(\d+|\d+-\d+|\*\/\d+)(,\d+|,\d+-\d+|,\*\/\d+)*)$"
    )

    return all(field_pattern.match(part) for part in parts)


def _validate_env_field(value: Any, path: str) -> List[str]:
    """Validate the env field - must be a list of strings, not a dict.

    Raises:
        ConfigValidationError: If env is a dict or contains invalid values.
    """
    if isinstance(value, dict):
        raise ConfigValidationError(
            f"{path}: env must be a list of variable names, not key-value pairs. "
            f"Use env: [VAR_NAME] instead of env: {{VAR_NAME: value}}"
        )
    if not isinstance(value, list):
        raise ConfigValidationError(
            f"{path}: env must be a list of strings, got {type(value).__name__}"
        )
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigValidationError(
                f"{path}[{i}]: env items must be strings, got {type(item).__name__}"
            )
    return value


def _validate_agent_config(name: str, data: Any, line_map: Dict[str, int]) -> AgentConfig:
    """Validate and parse an agent configuration section."""
    if not isinstance(data, dict):
        raise ConfigValidationError(
            f"agents.{name}: must be a mapping", line_map.get(f"agents.{name}")
        )

    # Validate runner if present
    runner = data.get("runner", "claude")
    if runner not in RUNNER_TYPES:
        raise ConfigValidationError(
            f"agents.{name}.runner: invalid runner '{runner}'. "
            f"Must be one of: {', '.join(RUNNER_TYPES)}",
            line_map.get(f"agents.{name}.runner"),
        )

    # Validate env field
    env_data = data.get("env", [])
    env_list = _validate_env_field(env_data, f"agents.{name}.env")

    # Validate base_url if present
    base_url = data.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise ConfigValidationError(
                f"agents.{name}.base_url: must be a string, got {type(base_url).__name__}",
                line_map.get(f"agents.{name}.base_url"),
            )
        if not base_url:
            raise ConfigValidationError(
                f"agents.{name}.base_url: must be a non-empty string",
                line_map.get(f"agents.{name}.base_url"),
            )
        if not base_url.startswith(("http://", "https://")):
            raise ConfigValidationError(
                f"agents.{name}.base_url: must start with http:// or https://",
                line_map.get(f"agents.{name}.base_url"),
            )

    return AgentConfig(
        runner=runner,
        model=data.get("model"),
        roles=data.get("roles", []),
        env=env_list,
        yolo=data.get("yolo", False),
        pilot=data.get("pilot", False),
        base_url=base_url,
    )


def _validate_job_config(name: str, data: Any, line_map: Dict[str, int]) -> JobConfig:
    """Validate and parse a job configuration section."""
    if not isinstance(data, dict):
        raise ConfigValidationError(f"jobs.{name}: must be a mapping", line_map.get(f"jobs.{name}"))

    # Required fields
    if "schedule" not in data:
        raise ConfigValidationError(
            f"jobs.{name}: missing required field 'schedule'", line_map.get(f"jobs.{name}")
        )
    if "agent" not in data:
        raise ConfigValidationError(
            f"jobs.{name}: missing required field 'agent'", line_map.get(f"jobs.{name}")
        )
    if "prompt" not in data:
        raise ConfigValidationError(
            f"jobs.{name}: missing required field 'prompt'", line_map.get(f"jobs.{name}")
        )

    # Validate cron expression
    schedule = data["schedule"]
    if not _validate_cron(schedule):
        raise ConfigValidationError(
            f"jobs.{name}.schedule: invalid cron expression '{schedule}'. "
            f"Use format: 'minute hour day month weekday' (e.g., '0 9 * * 1-5')",
            line_map.get(f"jobs.{name}.schedule"),
        )

    return JobConfig(
        schedule=schedule,
        agent=data["agent"],
        prompt=data["prompt"],
        enabled=data.get("enabled", True),
    )


def _build_line_map(content: str) -> Dict[str, int]:
    """Build a mapping from YAML path to line number.

    This is a simple heuristic-based mapper that tracks the line number
    for top-level and second-level keys.
    """
    line_map: Dict[str, int] = {}
    current_section: Optional[str] = None

    for line_num, line in enumerate(content.split("\n"), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check for section header (no leading whitespace, ends with colon)
        if not line.startswith(" ") and not line.startswith("\t"):
            if ":" in stripped:
                key = stripped.split(":")[0].strip()
                line_map[key] = line_num
                current_section = key
        # Check for subsection (2-space indent, ends with colon)
        elif (
            line.startswith("  ")
            and not line.startswith("    ")
            and ":" in stripped
            and current_section
        ):
            key = stripped.split(":")[0].strip()
            line_map[f"{current_section}.{key}"] = line_num

    return line_map


def load_agentweave_yml(path: Optional[Path] = None) -> AgentWeaveConfig:
    """Load and validate agentweave.yml.

    Args:
        path: Path to the YAML file. Defaults to ./agentweave.yml

    Returns:
        Parsed and validated AgentWeaveConfig

    Raises:
        ConfigValidationError: If the file is invalid or missing required fields.
        FileNotFoundError: If the file doesn't exist.
        ImportError: If pyyaml is not installed.
    """
    if yaml is None:
        raise ImportError(
            "pyyaml is required for agentweave.yml support. "
            "Install with: pip install 'agentweave-ai[mcp]'"
        )

    target_path = path or AGENTWEAVE_YML_PATH

    if not target_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {target_path}")

    content = target_path.read_text(encoding="utf-8")
    line_map = _build_line_map(content)

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        line = getattr(exc, "problem_mark", None)
        line_num = line.line + 1 if line else None
        raise ConfigValidationError(f"YAML parse error: {exc}", line_num) from exc

    if not isinstance(data, dict):
        raise ConfigValidationError("Configuration must be a YAML mapping (object)")

    # Parse project section
    project_data = data.get("project", {})
    if not isinstance(project_data, dict):
        raise ConfigValidationError("project: must be a mapping", line_map.get("project"))
    project_name = project_data.get("name", "Unnamed Project")
    project_mode = project_data.get("mode", "hierarchical")
    if project_mode not in VALID_MODES:
        raise ConfigValidationError(
            f"project.mode: invalid mode '{project_mode}'. "
            f"Must be one of: {', '.join(VALID_MODES)}",
            line_map.get("project.mode"),
        )
    project = ProjectConfig(name=project_name, mode=project_mode)

    # Parse hub section
    hub_data = data.get("hub", {})
    if not isinstance(hub_data, dict):
        raise ConfigValidationError("hub: must be a mapping", line_map.get("hub"))
    hub = HubConfig(url=hub_data.get("url", "http://localhost:8000"))

    # Parse agents section
    agents_data = data.get("agents", {})
    if not isinstance(agents_data, dict):
        raise ConfigValidationError("agents: must be a mapping", line_map.get("agents"))
    agents = {
        name: _validate_agent_config(name, cfg, line_map) for name, cfg in agents_data.items()
    }

    # Parse jobs section (optional)
    jobs_data = data.get("jobs")
    jobs: Optional[Dict[str, JobConfig]] = None
    if jobs_data is not None:
        if not isinstance(jobs_data, dict):
            raise ConfigValidationError("jobs: must be a mapping", line_map.get("jobs"))
        jobs = {name: _validate_job_config(name, cfg, line_map) for name, cfg in jobs_data.items()}

    return AgentWeaveConfig(
        project=project,
        hub=hub,
        agents=agents,
        jobs=jobs,
    )


def generate_agentweave_yml(
    session: Any,
    path: Optional[Path] = None,
) -> Path:
    """Generate agentweave.yml from an existing Session object.

    Args:
        session: A Session instance to serialize
        path: Output path. Defaults to ./agentweave.yml

    Returns:
        Path to the generated file

    Raises:
        ImportError: If pyyaml is not installed.
    """
    if yaml is None:
        raise ImportError(
            "pyyaml is required for agentweave.yml support. "
            "Install with: pip install 'agentweave-ai[mcp]'"
        )

    from .session import Session

    if not isinstance(session, Session):
        raise TypeError("session must be a Session instance")

    target_path = path or AGENTWEAVE_YML_PATH

    # Build config from session
    agents: Dict[str, AgentConfig] = {}
    for agent_name in session.agent_names:
        runner_cfg = session.get_runner_config(agent_name)

        # Get env vars as list of names
        env_vars = list(runner_cfg.get("env_vars", {}).values())

        agents[agent_name] = AgentConfig(
            runner=runner_cfg.get("runner", "claude"),
            model=runner_cfg.get("model"),
            roles=[],  # Roles are in roles.json, not session
            env=env_vars,
            yolo=session.get_agent_yolo(agent_name),
            pilot=session.get_agent_pilot(agent_name),
        )

    config = AgentWeaveConfig(
        project=ProjectConfig(name=session.name, mode=session.mode),
        hub=HubConfig(),
        agents=agents,
    )

    # Generate YAML with header comment
    header = """# AgentWeave Configuration
# This file defines your project settings, agents, and scheduled jobs.
# It SHOULD be committed to version control.
#
# Secret values (API keys, tokens) should NOT be added here.
# Use environment variables or a .env file instead (gitignored).

"""

    yaml_content = yaml.dump(
        config.to_dict(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    target_path.write_text(header + yaml_content, encoding="utf-8")
    return target_path


def save_agentweave_yml(
    config: AgentWeaveConfig,
    path: Optional[Path] = None,
) -> Path:
    """Save an AgentWeaveConfig to agentweave.yml.

    Args:
        config: Configuration to save
        path: Output path. Defaults to ./agentweave.yml

    Returns:
        Path to the saved file

    Raises:
        ImportError: If pyyaml is not installed.
    """
    if yaml is None:
        raise ImportError(
            "pyyaml is required for agentweave.yml support. "
            "Install with: pip install 'agentweave-ai[mcp]'"
        )

    target_path = path or AGENTWEAVE_YML_PATH

    header = """# AgentWeave Configuration
# This file defines your project settings, agents, and scheduled jobs.
# It SHOULD be committed to version control.
#
# Secret values (API keys, tokens) should NOT be added here.
# Use environment variables or a .env file instead (gitignored).

"""

    yaml_content = yaml.dump(
        config.to_dict(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    target_path.write_text(header + yaml_content, encoding="utf-8")
    return target_path
