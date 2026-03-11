"""InterAgent MCP server.

Exposes InterAgent messaging and task management as MCP tools so that
Claude Code and Kimi Code can send/receive messages and update tasks
natively, without manual relay prompts.

Usage:
    interagent-mcp                         # stdio (default)

Configure in Claude Code:
    claude mcp add interagent -- interagent-mcp

Configure in Kimi Code:
    kimi mcp add --transport stdio interagent -- interagent-mcp
"""

from typing import Any, Dict, List, Optional

try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError(
        "fastmcp is required for the MCP server. "
        "Install it with: pip install 'interagent-framework[mcp]'"
    ) from e

from ..constants import MESSAGE_TYPES, PRIORITIES, TASK_STATUSES
from ..locking import lock
from ..messaging import Message, MessageBus
from ..task import Task
from ..transport import get_transport

mcp = FastMCP(
    name="interagent",
    instructions=(
        "InterAgent collaboration tools. Use these to communicate with other AI agents "
        "and manage shared tasks. Always mark messages as read after processing them."
    ),
)


# ---------------------------------------------------------------------------
# Messaging tools
# ---------------------------------------------------------------------------


@mcp.tool()
def send_message(
    from_agent: str,
    to_agent: str,
    subject: str,
    content: str,
    message_type: str = "message",
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a message from one agent to another agent.

    Args:
        from_agent: Name of the sending agent (e.g. "claude")
        to_agent: Name of the receiving agent (e.g. "kimi")
        subject: Short summary of the message
        content: Full message body
        message_type: One of: message, delegation, review, discussion
        task_id: Associated task ID (optional)

    Returns:
        Dict with 'success' bool and 'message_id' on success, or 'error' on failure.
    """
    if message_type not in MESSAGE_TYPES:
        message_type = "message"

    msg = Message.create(
        sender=from_agent,
        recipient=to_agent,
        content=content,
        subject=subject,
        message_type=message_type,
        task_id=task_id,
    )
    ok = MessageBus.send(msg)
    if ok:
        return {"success": True, "message_id": msg.id}
    return {"success": False, "error": "Failed to send message via active transport"}


@mcp.tool()
def get_inbox(agent: str) -> List[Dict[str, Any]]:
    """Get all unread messages for an agent.

    Args:
        agent: Agent name to fetch messages for (e.g. "claude")

    Returns:
        List of message dicts with fields: id, from, to, subject, content,
        type, timestamp, task_id.
    """
    messages = MessageBus.get_inbox(agent)
    return [m.to_dict() for m in messages]


@mcp.tool()
def mark_read(message_id: str) -> Dict[str, Any]:
    """Mark a message as read and archive it.

    Args:
        message_id: ID of the message to archive (e.g. "msg-abc123")

    Returns:
        Dict with 'success' bool.
    """
    ok = MessageBus.mark_read(message_id)
    return {"success": ok}


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_tasks(agent: Optional[str] = None) -> List[Dict[str, Any]]:
    """List active tasks, optionally filtered by assignee.

    Args:
        agent: Filter by assignee name. Omit to list all active tasks.

    Returns:
        List of task dicts with fields: id, title, status, priority,
        assignee, assigner, description, created_at.
    """
    task_dicts = get_transport().get_active_tasks(agent)
    return task_dicts


@mcp.tool()
def get_task(task_id: str) -> Dict[str, Any]:
    """Get full details of a specific task.

    Args:
        task_id: Task ID (e.g. "task-abc123")

    Returns:
        Task dict with all fields, or {'error': '...'} if not found.
    """
    task = Task.load(task_id)
    if task is None:
        return {"error": f"Task '{task_id}' not found"}
    return task.to_dict()


@mcp.tool()
def update_task(task_id: str, status: str, agent: str = "") -> Dict[str, Any]:
    """Update a task's status.

    Valid statuses: pending, assigned, in_progress, completed,
    under_review, revision_needed, approved, rejected.

    Args:
        task_id: Task ID to update
        status: New status value
        agent: Your agent name (e.g. "kimi"). Used for activity logging.

    Returns:
        Updated task dict, or {'error': '...'} on failure.
    """
    if status not in TASK_STATUSES:
        return {"error": f"Invalid status '{status}'. Valid: {', '.join(TASK_STATUSES)}"}

    with lock(f"task-{task_id}"):
        task = Task.load(task_id)
        if task is None:
            return {"error": f"Task '{task_id}' not found"}

        task.update(agent=agent or None, status=status)

        if status in ("approved", "rejected"):
            task.move_to_completed()
        else:
            task.save()

    return task.to_dict()


@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    assignee: Optional[str] = None,
    assigner: Optional[str] = None,
    priority: str = "medium",
    requirements: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new task and save it.

    Args:
        title: Short task title
        description: Full task description
        assignee: Agent to assign the task to (optional)
        assigner: Agent creating the task (optional)
        priority: One of: low, medium, high, critical
        requirements: List of requirement strings (optional)
        acceptance_criteria: List of acceptance criteria strings (optional)

    Returns:
        Created task dict with generated ID.
    """
    if priority not in PRIORITIES:
        priority = "medium"

    task = Task.create(
        title=title,
        description=description,
        assignee=assignee,
        assigner=assigner,
        priority=priority,
        requirements=requirements or [],
        acceptance_criteria=acceptance_criteria or [],
    )

    with lock(f"task-{task.id}"):
        ok = get_transport().send_task(task.to_dict())

    if not ok:
        return {"error": "Failed to save task via active transport"}
    return task.to_dict()


# ---------------------------------------------------------------------------
# Status tool
# ---------------------------------------------------------------------------


@mcp.tool()
def get_status() -> Dict[str, Any]:
    """Get a summary of the current InterAgent session and active tasks.

    Returns:
        Dict with session info and task counts by status and assignee.
    """
    from ..session import Session

    result: Dict[str, Any] = {"session": None, "tasks": [], "task_counts": {}}

    session = Session.load()
    if session:
        result["session"] = {
            "id": session.id,
            "name": session.name,
            "mode": session.mode,
            "principal": session.principal,
            "agents": session.agent_names,
        }

    task_dicts = get_transport().get_active_tasks()
    result["tasks"] = task_dicts

    counts: Dict[str, int] = {}
    for t in task_dicts:
        s = t.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    result["task_counts"] = counts

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the InterAgent MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
