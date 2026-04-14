"""Role management for AgentWeave agents.

This module handles adding, removing, and managing multiple roles per agent.
Roles are stored in .agentweave/roles.json and synced to the Hub when HTTP
transport is configured.
"""

from typing import Any, Dict, List, Optional, Tuple

from .constants import ROLES_CONFIG_FILE
from .templates import load_roles_template
from .utils import load_json, save_json

# Valid role IDs from the templates
VALID_ROLE_IDS = [
    "tech_lead",
    "architect",
    "backend_dev",
    "frontend_dev",
    "fullstack_dev",
    "qa_engineer",
    "devops_engineer",
    "security_engineer",
    "data_engineer",
    "ml_engineer",
    "technical_writer",
    "code_reviewer",
    "project_manager",
]


def load_roles_config() -> Optional[Dict[str, Any]]:
    """Load the roles.json config file.

    Returns:
        Parsed config dict, or None if file doesn't exist.
        The dict will have 'agent_roles' (list-based) normalized from
        legacy 'agent_assignments' (single role) if needed.
    """
    data = load_json(ROLES_CONFIG_FILE)
    if not data:
        return None

    # Normalize legacy format to new format
    # Old: "agent_assignments": { "agent": "role" }
    # New: "agent_roles": { "agent": ["role1", "role2"] }
    if "agent_assignments" in data and "agent_roles" not in data:
        data["agent_roles"] = {
            agent: [role] if isinstance(role, str) else role
            for agent, role in data.get("agent_assignments", {}).items()
        }

    # Ensure agent_roles exists
    if "agent_roles" not in data:
        data["agent_roles"] = {}

    return data


def save_roles_config(config: Dict[str, Any]) -> bool:
    """Save the roles.json config file.

    Args:
        config: The roles configuration dict

    Returns:
        True if saved successfully, False otherwise.
    """
    return save_json(ROLES_CONFIG_FILE, config)


def get_available_roles() -> List[Tuple[str, str, str]]:
    """Get list of available role definitions.

    Returns:
        List of tuples (role_id, label, responsibilities_short)
    """
    try:
        template_data = load_roles_template()
        roles_defs = template_data.get("roles", {})
        return [
            (role_id, info.get("label", role_id), info.get("responsibilities_short", ""))
            for role_id, info in roles_defs.items()
            if not role_id.startswith("_")
        ]
    except Exception:
        # Fallback to hardcoded list if template fails
        return [
            ("tech_lead", "Tech Lead", "Architecture decisions, code review, integration"),
            ("architect", "Architect", "System design, data models, API contracts"),
            ("backend_dev", "Backend Developer", "APIs, database, business logic"),
            ("frontend_dev", "Frontend Developer", "UI components, styling, client-side state"),
            ("fullstack_dev", "Full Stack Developer", "Backend and frontend features"),
            ("qa_engineer", "QA / Test Engineer", "Tests, quality assurance, edge cases"),
            ("devops_engineer", "DevOps Engineer", "CI/CD, infrastructure, deployment"),
            (
                "security_engineer",
                "Security Engineer",
                "Security review, auth/authz, vulnerability audit",
            ),
            ("data_engineer", "Data Engineer", "Data pipelines, ETL, analytics"),
            ("ml_engineer", "ML / AI Engineer", "ML models, training pipelines, inference"),
            ("technical_writer", "Technical Writer", "Documentation, READMEs, API docs"),
            ("code_reviewer", "Code Reviewer", "Pull request reviews, style enforcement"),
            ("project_manager", "Project Manager", "Task tracking, progress coordination"),
        ]


def validate_role(role_id: str) -> Tuple[bool, str]:
    """Validate a role ID.

    Args:
        role_id: The role ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not role_id:
        return False, "Role ID cannot be empty"

    valid_roles = [r[0] for r in get_available_roles()]
    if role_id not in valid_roles:
        return False, f"Invalid role '{role_id}'. Run 'agentweave roles available' for valid roles."

    return True, ""


def get_agent_roles(agent: str, config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Get all roles assigned to an agent.

    Args:
        agent: Agent name
        config: Optional pre-loaded config (will load if not provided)

    Returns:
        List of role IDs for the agent
    """
    if config is None:
        config = load_roles_config()

    if not config:
        return []

    roles = config.get("agent_roles", {}).get(agent, [])

    # Handle both list and string (legacy)
    if isinstance(roles, str):
        return [roles]
    return list(roles)


def add_role_to_agent(
    agent: str, role: str, config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Add a role to an agent.

    Args:
        agent: Agent name
        role: Role ID to add
        config: Optional pre-loaded config (will create new if not provided)

    Returns:
        Tuple of (success, message, updated_config)
    """
    # Validate role
    is_valid, error = validate_role(role)
    if not is_valid:
        return False, error, config

    # Load or create config
    if config is None:
        config = load_roles_config()

    if config is None:
        # Create new config
        config = {"version": 2, "agent_roles": {}, "roles": {}}
        # Copy role definitions from template
        try:
            template_data = load_roles_template()
            all_roles = template_data.get("roles", {})
            config["roles"] = {
                k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                for k, v in all_roles.items()
            }
        except Exception:
            pass

    # Ensure agent_roles exists
    if "agent_roles" not in config:
        config["agent_roles"] = {}

    # Get current roles
    current_roles = get_agent_roles(agent, config)

    # Check if already has this role
    if role in current_roles:
        return False, f"Agent '{agent}' already has role '{role}'", config

    # Add the role
    current_roles.append(role)
    config["agent_roles"][agent] = current_roles

    return True, f"Added '{role}' to '{agent}'", config


def remove_role_from_agent(
    agent: str, role: str, config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Remove a role from an agent.

    Args:
        agent: Agent name
        role: Role ID to remove
        config: Optional pre-loaded config (will load if not provided)

    Returns:
        Tuple of (success, message, updated_config)
    """
    # Load config
    if config is None:
        config = load_roles_config()

    if not config:
        return False, "No roles configuration found", None

    # Get current roles
    current_roles = get_agent_roles(agent, config)

    if not current_roles:
        return False, f"Agent '{agent}' has no roles assigned", config

    if role not in current_roles:
        return False, f"Agent '{agent}' does not have role '{role}'", config

    # Remove the role
    current_roles.remove(role)
    config["agent_roles"][agent] = current_roles

    return True, f"Removed '{role}' from '{agent}'", config


def remove_agent_from_roles(agent: str) -> bool:
    """Remove all role entries for an agent from roles.json.

    Called when an agent is removed from the session (orphaned by activate).
    """
    config = load_roles_config()
    if not config:
        return True  # Nothing to clean up

    changed = False
    if agent in config.get("agent_roles", {}):
        del config["agent_roles"][agent]
        changed = True
    if agent in config.get("agent_assignments", {}):
        del config["agent_assignments"][agent]
        changed = True

    if changed:
        save_roles_config(config)
    return True


def set_agent_roles(
    agent: str, roles: List[str], config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Set/replace all roles for an agent.

    Args:
        agent: Agent name
        roles: List of role IDs
        config: Optional pre-loaded config (will create new if not provided)

    Returns:
        Tuple of (success, message, updated_config)
    """
    # Validate all roles first
    for role in roles:
        is_valid, error = validate_role(role)
        if not is_valid:
            return False, error, config

    # Load or create config
    if config is None:
        config = load_roles_config()

    if config is None:
        # Create new config
        config = {"version": 2, "agent_roles": {}, "roles": {}}
        # Copy role definitions from template
        try:
            template_data = load_roles_template()
            all_roles = template_data.get("roles", {})
            config["roles"] = {
                k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                for k, v in all_roles.items()
            }
        except Exception:
            pass

    # Ensure agent_roles exists
    if "agent_roles" not in config:
        config["agent_roles"] = {}

    # Remove duplicates while preserving order
    seen = set()
    unique_roles = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            unique_roles.append(role)

    # Set the roles
    config["agent_roles"][agent] = unique_roles

    # Ensure role definitions exist for all assigned roles
    try:
        template_data = load_roles_template()
        all_role_defs = template_data.get("roles", {})
        if "roles" not in config:
            config["roles"] = {}
        for role_id in unique_roles:
            if role_id not in config["roles"] and role_id in all_role_defs:
                config["roles"][role_id] = {
                    k: v for k, v in all_role_defs[role_id].items() if not k.startswith("_")
                }
    except Exception:
        pass

    return True, f"Set roles for '{agent}': {', '.join(unique_roles)}", config


def sync_roles_to_hub(config: Dict[str, Any]) -> bool:
    """Push roles config to the Hub if HTTP transport is active.

    Args:
        config: The roles configuration to push

    Returns:
        True if sync succeeded or no HTTP transport, False if sync failed.
    """
    try:
        from .transport import get_transport

        transport = get_transport()
        if transport.get_transport_type() == "http":
            return transport.push_roles_config(config)
    except Exception:
        pass

    return True  # Non-fatal for non-HTTP transports


def format_agent_roles(agent: str, config: Optional[Dict[str, Any]] = None) -> str:
    """Format an agent's roles for display.

    Args:
        agent: Agent name
        config: Optional pre-loaded config

    Returns:
        Comma-separated list of role labels, or "none" if no roles
    """
    roles = get_agent_roles(agent, config)
    if not roles:
        return "none"

    # Try to get labels
    try:
        template_data = load_roles_template()
        roles_defs = template_data.get("roles", {})
        labels = []
        for role_id in roles:
            role_def = roles_defs.get(role_id, {})
            label = role_def.get("label", role_id)
            labels.append(label)
        return ", ".join(labels)
    except Exception:
        return ", ".join(roles)


def copy_role_md_file(role_id: str) -> bool:
    """Copy a role's markdown file to .agentweave/roles/.

    Args:
        role_id: The role ID (e.g., 'backend_dev', 'tech_lead')

    Returns:
        True if file was copied or already exists, False on error
    """
    from .constants import ROLES_DIR
    from .templates import get_role_md

    try:
        ROLES_DIR.mkdir(exist_ok=True)
        role_md_path = ROLES_DIR / f"{role_id}.md"

        # Skip if already exists
        if role_md_path.exists():
            return True

        # Get role markdown from templates
        role_md_content = get_role_md(role_id)
        role_md_path.write_text(role_md_content, encoding="utf-8")
        return True
    except FileNotFoundError:
        # Role template doesn't exist
        return False
    except Exception:
        return False
