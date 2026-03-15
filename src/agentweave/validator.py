"""JSON schema validation for AgentWeave."""

from typing import Any, Dict, List, Tuple

from .constants import AGENT_NAME_RE, MESSAGE_TYPES, PRIORITIES, TASK_STATUSES


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def _valid_agent(name: Any) -> bool:
    """Return True if name is a valid agent identifier.

    Accepts plain agent names (e.g. "claude") and cluster-prefixed names
    (e.g. "alice.claude") used by the git transport.
    """
    if not isinstance(name, str):
        return False
    # Strip optional cluster prefix
    agent_part = name.split(".")[-1] if "." in name else name
    return bool(AGENT_NAME_RE.match(agent_part))


def validate_task(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate task data.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    required = ["id", "title", "status", "created_at"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate status
    if "status" in data and data["status"] not in TASK_STATUSES:
        errors.append(f"Invalid status: {data['status']}")

    # Validate priority
    if "priority" in data and data["priority"] not in PRIORITIES:
        errors.append(f"Invalid priority: {data['priority']}")

    # Validate assignee/assigner — any valid agent name, not just known ones
    if "assignee" in data and data["assignee"] and not _valid_agent(data["assignee"]):
        errors.append(f"Invalid assignee name: {data['assignee']!r}")

    if "assigner" in data and data["assigner"] and not _valid_agent(data["assigner"]):
        errors.append(f"Invalid assigner name: {data['assigner']!r}")

    # Validate types
    if "title" in data and not isinstance(data["title"], str):
        errors.append("Title must be a string")

    if "description" in data and not isinstance(data["description"], str):
        errors.append("Description must be a string")

    if "requirements" in data and not isinstance(data["requirements"], list):
        errors.append("Requirements must be a list")

    return len(errors) == 0, errors


def validate_message(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate message data.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Required fields
    required = ["id", "from", "to", "content", "timestamp"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate sender/recipient — accept plain names and cluster.agent form
    if "from" in data and not _valid_agent(data["from"]):
        errors.append(f"Invalid sender: {data['from']!r}")

    if "to" in data and not _valid_agent(data["to"]):
        errors.append(f"Invalid recipient: {data['to']!r}")

    # Validate type
    if "type" in data and data["type"] not in MESSAGE_TYPES:
        errors.append(f"Invalid message type: {data['type']}")

    # Validate types
    if "content" in data and not isinstance(data["content"], str):
        errors.append("Content must be a string")

    if "subject" in data and not isinstance(data["subject"], str):
        errors.append("Subject must be a string")

    return len(errors) == 0, errors


def validate_session(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate session data."""
    errors = []

    required = ["id", "name", "created", "mode", "principal"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if "mode" in data and data["mode"] not in ["hierarchical", "peer", "review"]:
        errors.append(f"Invalid mode: {data['mode']}")

    if "principal" in data and not _valid_agent(data["principal"]):
        errors.append(f"Invalid principal: {data['principal']!r}")

    return len(errors) == 0, errors


def sanitize_string(value: Any, max_length: int = 1000) -> str:
    """Sanitize a string value."""
    if not isinstance(value, str):
        return str(value)[:max_length]
    return value[:max_length]


def sanitize_task_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize task data before saving."""
    sanitized: Dict[str, Any] = {}

    # Copy allowed fields with sanitization
    if "id" in data:
        sanitized["id"] = sanitize_string(data["id"], 50)
    if "title" in data:
        sanitized["title"] = sanitize_string(data["title"], 200)
    if "description" in data:
        sanitized["description"] = sanitize_string(data["description"], 5000)
    if "status" in data and data["status"] in TASK_STATUSES:
        sanitized["status"] = data["status"]
    if "priority" in data and data["priority"] in PRIORITIES:
        sanitized["priority"] = data["priority"]

    # Accept any valid agent name
    if "assignee" in data and _valid_agent(data.get("assignee", "")):
        sanitized["assignee"] = data["assignee"]
    if "assigner" in data and _valid_agent(data.get("assigner", "")):
        sanitized["assigner"] = data["assigner"]

    # Lists
    if "requirements" in data and isinstance(data["requirements"], list):
        sanitized["requirements"] = [sanitize_string(r, 500) for r in data["requirements"]]
    if "acceptance_criteria" in data and isinstance(data["acceptance_criteria"], list):
        sanitized["acceptance_criteria"] = [
            sanitize_string(c, 500) for c in data["acceptance_criteria"]
        ]
    if "deliverables" in data and isinstance(data["deliverables"], list):
        sanitized["deliverables"] = [sanitize_string(d, 500) for d in data["deliverables"]]

    # Timestamps
    if "created_at" in data:
        sanitized["created_at"] = data["created_at"]
    if "updated" in data:
        sanitized["updated"] = data["updated"]

    return sanitized
