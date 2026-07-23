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

from .constants import RUNNER_TYPES, VALID_DOC_THRESHOLDS, VALID_ECHO_GUARD, VALID_MODES

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
class QualityConfig:
    """Quality governance settings for AI-generated code."""

    review_required: bool = False
    docs_path: Optional[str] = None
    docs_threshold: str = "never"
    echo_chamber_guard: str = "off"
    attribution_tag: bool = False
    dependency_check: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {}
        if self.review_required:
            result["review_required"] = True
        if self.docs_path is not None:
            result["docs_path"] = self.docs_path
        if self.docs_threshold != "never":
            result["docs_threshold"] = self.docs_threshold
        if self.echo_chamber_guard != "off":
            result["echo_chamber_guard"] = self.echo_chamber_guard
        if self.attribution_tag:
            result["attribution_tag"] = True
        if self.dependency_check:
            result["dependency_check"] = True
        return result


@dataclass
class AgentConfig:
    """Configuration for a single agent."""

    runner: str = "claude"
    model: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    yolo: bool = False
    pilot: bool = False
    principal: bool = False
    base_url: Optional[str] = None
    runner_options: Optional[Dict[str, Any]] = None
    cli: Optional[str] = None

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
        if self.principal:
            result["principal"] = True
        if self.base_url:
            result["base_url"] = self.base_url
        if self.runner_options is not None:
            result["runner_options"] = self.runner_options
        if self.cli:
            result["cli"] = self.cli
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
    # True only for a freshly generated agentweave.yml that hasn't been reviewed
    # yet (set by `agentweave init`, cleared by `agentweave activate`). Lets
    # setup skills tell "untouched scaffold" apart from "user-reviewed config".
    scaffold: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {"name": self.name, "mode": self.mode}
        if self.scaffold:
            result["scaffold"] = True
        return result


@dataclass
class AgentWeaveConfig:
    """Root configuration for agentweave.yml."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    hub: HubConfig = field(default_factory=HubConfig)
    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    jobs: Optional[Dict[str, JobConfig]] = None
    quality: Optional[QualityConfig] = None
    opencode: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: Dict[str, Any] = {
            "project": self.project.to_dict(),
            "hub": self.hub.to_dict(),
            "agents": {name: cfg.to_dict() for name, cfg in self.agents.items()},
        }
        if self.jobs is not None:
            result["jobs"] = {name: cfg.to_dict() for name, cfg in self.jobs.items()}
        if self.quality is not None:
            result["quality"] = self.quality.to_dict()
        if self.opencode is not None:
            result["opencode"] = self.opencode
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

    # Validate cli override (optional, runner-relative). When set, it should be
    # a non-empty string -- the watchdog trusts it as the literal CLI to invoke.
    # We don't validate that the file exists here; the user may be on a host
    # where the binary is only present at runtime, and a missing path is caught
    # at launch time with a clearer error than a YAML parse failure.
    cli = data.get("cli")
    if cli is not None:
        if not isinstance(cli, str):
            raise ConfigValidationError(
                f"agents.{name}.cli: must be a string, got {type(cli).__name__}",
                line_map.get(f"agents.{name}.cli"),
            )
        if not cli:
            raise ConfigValidationError(
                f"agents.{name}.cli: must be a non-empty string",
                line_map.get(f"agents.{name}.cli"),
            )

    return AgentConfig(
        runner=runner,
        model=data.get("model"),
        roles=data.get("roles", []),
        env=env_list,
        yolo=data.get("yolo", False),
        pilot=data.get("pilot", False),
        principal=bool(data.get("principal", False)),
        base_url=base_url,
        runner_options=data.get("runner_options"),
        cli=cli,
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
    project_scaffold = bool(project_data.get("scaffold", False))
    project = ProjectConfig(name=project_name, mode=project_mode, scaffold=project_scaffold)

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

    # Validate at most one principal agent
    principal_agents = [name for name, cfg in agents.items() if cfg.principal]
    if len(principal_agents) > 1:
        raise ConfigValidationError(
            f"Only one agent can have 'principal: true'. Found: {', '.join(principal_agents)}"
        )

    # Parse jobs section (optional)
    jobs_data = data.get("jobs")
    jobs: Optional[Dict[str, JobConfig]] = None
    if jobs_data is not None:
        if not isinstance(jobs_data, dict):
            raise ConfigValidationError("jobs: must be a mapping", line_map.get("jobs"))
        jobs = {name: _validate_job_config(name, cfg, line_map) for name, cfg in jobs_data.items()}

    # Parse quality section (optional)
    quality_data = data.get("quality")
    quality: Optional[QualityConfig] = None
    if quality_data is not None:
        if not isinstance(quality_data, dict):
            raise ConfigValidationError("quality: must be a mapping", line_map.get("quality"))
        docs_threshold = quality_data.get("docs_threshold", "never")
        if docs_threshold not in VALID_DOC_THRESHOLDS:
            raise ConfigValidationError(
                f"quality.docs_threshold: invalid value '{docs_threshold}'. "
                f"Must be one of: {', '.join(VALID_DOC_THRESHOLDS)}",
                line_map.get("quality.docs_threshold"),
            )
        echo_chamber_guard = quality_data.get("echo_chamber_guard", "off")
        if echo_chamber_guard not in VALID_ECHO_GUARD:
            raise ConfigValidationError(
                f"quality.echo_chamber_guard: invalid value '{echo_chamber_guard}'. "
                f"Must be one of: {', '.join(VALID_ECHO_GUARD)}",
                line_map.get("quality.echo_chamber_guard"),
            )
        quality = QualityConfig(
            review_required=bool(quality_data.get("review_required", False)),
            docs_path=quality_data.get("docs_path"),
            docs_threshold=docs_threshold,
            echo_chamber_guard=echo_chamber_guard,
            attribution_tag=bool(quality_data.get("attribution_tag", False)),
            dependency_check=bool(quality_data.get("dependency_check", False)),
        )

    # Parse opencode section (optional) -- opaque nested config for opencode.json
    # auto-generation. Lenient validation: just check it's a mapping if present.
    opencode_data = data.get("opencode")
    opencode: Optional[Dict[str, Any]] = None
    if opencode_data is not None:
        if not isinstance(opencode_data, dict):
            raise ConfigValidationError("opencode: must be a mapping", line_map.get("opencode"))
        opencode = opencode_data

    return AgentWeaveConfig(
        project=project,
        hub=hub,
        agents=agents,
        jobs=jobs,
        quality=quality,
        opencode=opencode,
    )


def _yaml_dq(value: Any) -> str:
    """Escape a value for safe inclusion inside a YAML double-quoted scalar.

    Escapes backslashes first (so they don't corrupt later escapes), then double
    quotes, then the control characters that would otherwise break the scalar or
    span extra lines. Without this, a project name containing a Windows path
    (e.g. ``C:\\Users\\me\\proj``) or a newline produced invalid YAML that failed
    to parse for the entire generated file.
    """
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return text


def _format_agent_block(
    agent_name: str,
    runner: str,
    model: Optional[str],
    env_vars: List[str],
    yolo: bool,
    pilot: bool,
    is_principal: bool,
    cli: Optional[str],
    runner_options: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a single agent's YAML block (2-space indented, no trailing newline)."""
    lines = [f"  {agent_name}:"]
    lines.append(f"    runner: {runner}")
    if model:
        lines.append(f"    model: {model}")
    if is_principal:
        lines.append("    principal: true")
    lines.append("    roles: []              # add roles: [tech_lead, backend_dev, ...]")
    if env_vars:
        env_str = ", ".join(env_vars)
        lines.append(f"    env: [{env_str}]")
    if yolo:
        lines.append("    yolo: true")
    if pilot:
        lines.append("    pilot: true")
    if cli:
        lines.append(f"    cli: {cli}")
    if runner_options:
        lines.append("    runner_options:")
        for k, v in runner_options.items():
            lines.append(f"      {k}: {str(v).lower() if isinstance(v, bool) else v}")
    return "\n".join(lines)


def generate_agentweave_yml(
    session: Any,
    path: Optional[Path] = None,
) -> Path:
    """Generate a comprehensive agentweave.yml from an existing Session object.

    The generated file contains the active session agents at the top and
    richly commented reference examples for every runner, section, and option
    so operators can uncomment and adapt what they need.

    Args:
        session: A Session instance to serialize
        path: Output path. Defaults to ./agentweave.yml

    Returns:
        Path to the generated file
    """
    from .session import Session

    if not isinstance(session, Session):
        raise TypeError("session must be a Session instance")

    target_path = path or AGENTWEAVE_YML_PATH

    # -- Build active-agent blocks from session ------------------------------
    active_blocks: List[str] = []
    for agent_name in session.agent_names:
        runner_cfg = session.get_runner_config(agent_name)
        env_vars = list(runner_cfg.get("env_vars", {}).values())
        active_blocks.append(
            _format_agent_block(
                agent_name=agent_name,
                runner=runner_cfg.get("runner", "claude"),
                model=runner_cfg.get("model"),
                env_vars=env_vars,
                yolo=session.get_agent_yolo(agent_name),
                pilot=session.get_agent_pilot(agent_name),
                is_principal=(agent_name == session.principal),
                cli=runner_cfg.get("cli"),
                runner_options=runner_cfg.get("runner_options"),
            )
        )
    active_agents_yaml = "\n\n".join(active_blocks)

    project_name = _yaml_dq(session.name)
    project_mode = session.mode

    template = f"""\
# ==============================================================
# AgentWeave Configuration -- {project_name}
# ==============================================================
# COMMIT this file. Remove or comment out what you don't need.
# Never put secrets here -- use environment variables or .env
# (agentweave init creates a .env placeholder at the project root).
#
# Apply changes at any time with:
#   agentweave activate
# Check health with:
#   agentweave doctor
# ==============================================================

# -- PROJECT ----------------------------------------------------
project:
  name: "{project_name}"

  # Collaboration mode -- controls who can assign tasks to whom.
  #   hierarchical  The principal agent delegates; delegates report back (default)
  #   peer          Any agent can assign tasks to any other
  #   review        Optimized for code-review workflows
  mode: {project_mode}

  # This file was auto-generated by `agentweave init` with defaults and has
  # not been reviewed yet. Setup skills (aw-setup, aw-setup-*) treat
  # scaffold: true as "run the full interview", not "read existing answers".
  # `agentweave activate` clears this automatically once you run it.
  scaffold: true

# -- HUB --------------------------------------------------------
hub:
  url: http://localhost:8000

  # Start the Hub (choose one):
  #   agentweave hub start            # Docker (recommended)
  #   agentweave hub start --native   # no Docker -- needs: pip install agentweave-hub uvicorn

# -- AGENTS -----------------------------------------------------
# Runner types:
#   claude      Claude Code CLI (claude)
#   kimi        Kimi Code CLI (kimi)
#   codex       OpenAI Codex CLI (codex exec --json)
#   codex_mcp   Codex as persistent MCP server (codex mcp-server)
#   opencode    OpenCode terminal agent (opencode)
#   copilot     GitHub Copilot CLI (gh copilot)
#   claude_proxy  Any OpenAI-compatible model routed through Claude CLI
#   native      Use the agent name as the CLI command
#   manual      No CLI -- relay prompts only
#
# Available roles (add to any agent):
#   Human-title (developer) roles:
#     tech_lead | architect | backend_dev | frontend_dev | fullstack_dev
#     qa_engineer | devops_engineer | security_engineer | data_engineer
#     ml_engineer | technical_writer | code_reviewer | project_manager
#   AI-native (function-first) roles:
#     coordinator | model_router | explorer | implementer | verifier
#     guardian | context_keeper | spec
#   Both sets are supported and can be combined (e.g. [implementer, frontend_dev]).
#
# Common per-agent fields:
#   runner:         (required) Which CLI to invoke -- see list above
#   model:          Model name passed with --model (format varies by runner)
#   roles:          Developer role list -- adds behavioral guides at session start
#   env:            Env var NAMES (not values) to forward to the subprocess
#   yolo:           true = skip confirmation prompts (autonomous mode). Default: false
#   pilot:          true = human controls session start/resume. Default: false
#   principal:      true = marks the lead/orchestrator; at most one agent. Default: false
#   cli:            Absolute path to the binary (overrides PATH lookup; useful on WSL)
#   base_url:       Custom HTTP endpoint (claude_proxy custom providers only)
#   runner_options: Runner-specific map -- e.g. {{memory: false}} for Codex
#   hub_client:     auto | mcp | cli -- how agent talks to Hub. Default: auto
agents:

{active_agents_yaml}

  # -- Additional agent examples -- uncomment and adapt ------------

  # -- Claude (Anthropic Claude Code CLI) --
  # claude:
  #   runner: claude
  #   model: claude-sonnet-4-5        # optional; defaults to Anthropic's latest
  #   roles: [tech_lead, backend_dev]
  #   principal: true                 # this agent delegates to others
  #   yolo: false                     # true = no confirmation prompts
  #   pilot: false                    # true = you trigger sessions manually

  # -- Kimi (Kimi Code CLI) --
  # kimi:
  #   runner: kimi
  #   model: kimi-k2                  # optional; defaults to kimi-k2
  #   roles: [frontend_dev]
  #   pilot: true                     # recommended for Kimi -- session IDs must be registered
  #   # After activating, register the session ID:
  #   #   agentweave session register --agent kimi --session <id>

  # -- OpenAI Codex CLI --
  # codex:
  #   runner: codex
  #   model: gpt-5.5                  # optional; defaults to codex default
  #   roles: [backend_dev]
  #   yolo: true                      # codex works best with yolo enabled
  #   runner_options:
  #     memory: true                  # false = disable cross-session Codex memory

  # -- Codex as persistent MCP server --
  # codex-mcp:
  #   runner: codex_mcp
  #   model: gpt-5.5
  #   roles: [backend_dev]
  #   yolo: true
  #   runner_options:
  #     memory: false

  # -- OpenCode (terminal AI coding agent, local or cloud) --
  # opencode:
  #   runner: opencode
  #   # Model MUST be in 'provider/model' form (case-sensitive):
  #   model: anthropic/claude-sonnet-4-5
  #   # model: openai/gpt-4o
  #   # model: ollama/qwen2.5-coder:7b   # local, no API key needed
  #   # model: minimax-coding-plan/MiniMax-M3
  #   roles: [backend_dev]
  #   env: [MINIMAX_API_KEY]          # forward provider key to subprocess (if needed)
  #   # cli: /abs/path/to/opencode    # pin binary -- prevents WSL PATH confusion
  #   # Run `agentweave doctor` if you see ProviderModelNotFoundError

  # -- GitHub Copilot CLI --
  # copilot:
  #   runner: copilot
  #   model: claude-sonnet-4-5        # optional; choose e.g. claude-opus-4.5, gpt-5.5
  #   roles: [backend_dev]
  #   env: [COPILOT_GITHUB_TOKEN]     # fine-grained PAT with 'Copilot Requests' permission
  #   yolo: false
  #   # hub_client: cli               # uncomment if MCP is blocked by company policy

  # -- MiniMax via Claude-proxy (built-in provider) --
  # minimax:
  #   runner: claude_proxy
  #   model: MiniMax-M2.7             # optional; defaults to MiniMax-Text-01
  #   env: [MINIMAX_API_KEY]
  #   yolo: true

  # -- Zhipu GLM via Claude-proxy (built-in provider) --
  # glm:
  #   runner: claude_proxy
  #   model: glm-5
  #   env: [ZHIPU_API_KEY]
  #   yolo: true

  # -- Any OpenAI-compatible provider via Claude-proxy --
  # my-model:
  #   runner: claude_proxy
  #   model: custom-model-name
  #   base_url: https://api.example.com/v1
  #   env: [MY_MODEL_API_KEY]
  #   yolo: true

  # -- Manual relay (no CLI integration) --
  # gemini:
  #   runner: manual
  #   roles: [frontend_dev]
  #   # Use `agentweave relay --agent gemini` to generate relay prompts manually

# -- JOBS -------------------------------------------------------
# Scheduled recurring tasks (requires Hub / HTTP transport).
# Cron format: minute hour day month weekday
#   *  = any      */n = every n    n-m = range    n,m = list
#
# jobs:
#   morning-standup:
#     schedule: "0 9 * * 1-5"         # weekdays at 09:00
#     agent: claude
#     prompt: >
#       Review yesterday's completed tasks, check for blockers,
#       and post a standup summary to the team.
#     enabled: true
#
#   weekly-cleanup:
#     schedule: "0 17 * * 5"          # Fridays at 17:00
#     agent: kimi
#     prompt: "Archive completed tasks and generate a weekly summary."
#     enabled: false                   # disabled until needed
#
#   nightly-tests:
#     schedule: "0 2 * * *"           # every night at 02:00
#     agent: codex
#     prompt: "Run the full test suite and report any failures."
#     enabled: true
#
# CLI equivalents:
#   agentweave jobs create --name "..." --agent claude --message "..." --cron "0 9 * * 1-5"
#   agentweave jobs list
#   agentweave jobs pause <job_id>
#   agentweave jobs run <job_id>

# -- QUALITY GOVERNANCE -----------------------------------------
# Optional quality controls for AI-generated code.
#
# quality:
#   # Require a human or agent review before a task is marked done.
#   review_required: false
#
#   # Write ADR-lite decision docs for significant changes.
#   # docs_path: .agentweave/code-docs    # where to write them (default)
#   docs_threshold: never                 # all | non_trivial | never
#
#   # Prevent the same agent from both implementing and reviewing a task.
#   echo_chamber_guard: off               # off | warn | enforce
#
#   # Stamp completed tasks with the agent name and session ID.
#   attribution_tag: false
#
#   # Flag hallucinated or unresolvable package names during review.
#   dependency_check: false

# -- OPENCODE PROVIDER CONFIG -----------------------------------
# The top-level `opencode:` block is written verbatim to opencode.json
# by `agentweave activate`. Use this to version-control provider config
# instead of (or alongside) `opencode auth login`.
# Keys you declare overwrite; other keys in opencode.json are preserved.
#
# opencode:
#   provider:
#     minimax:
#       npm: "@ai-sdk/anthropic"
#       name: "MiniMax"
#       options:
#         baseURL: "https://api.minimaxi.com/v1"
#       models:
#         M3:
#           name: "MiniMax-M3"
#   # agent:
#   #   model: minimax-coding-plan/MiniMax-M3   # set a global default model
#   # instructions: "Always respond in English."
"""

    target_path.write_text(template, encoding="utf-8")
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
