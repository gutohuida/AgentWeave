"""AgentWeave MCP server.

Exposes AgentWeave messaging and task management as MCP tools so that
Claude Code and Kimi Code can send/receive messages and update tasks
natively, without manual relay prompts.

Usage:
    agentweave-mcp                         # stdio (default)

Configure in Claude Code:
    claude mcp add agentweave -- agentweave-mcp

Configure in Kimi Code:
    kimi mcp add --transport stdio agentweave -- agentweave-mcp
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from fastmcp import FastMCP  # type: ignore[import-not-found]
except ImportError as e:
    raise ImportError(
        "fastmcp is required for the MCP server. "
        "Install it with: pip install 'agentweave-ai[mcp]'"
    ) from e

from ..constants import MESSAGE_TYPES, PRIORITIES, TASK_STATUSES, TransportType
from ..locking import LockError, lock
from ..messaging import Message, MessageBus
from ..task import Task
from ..transport import get_transport

mcp = FastMCP(
    name="agentweave",
    instructions=(
        "AgentWeave collaboration tools. Use these to communicate with other AI agents "
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
    transport = get_transport()
    if transport.get_transport_type() == TransportType.HTTP:
        result = transport.get_task_by_id(task_id)  # type: ignore[attr-defined]
        if result is None:
            return {"error": f"Task '{task_id}' not found"}
        return result

    # local / git: file-based
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
        task_id: Task ID to update — use the 'id' field from list_tasks().
        status: New status value
        agent: Your agent name (e.g. "kimi"). Used for activity logging.

    Returns:
        Updated task dict, or {'error': '...'} on failure.
    """
    if status not in TASK_STATUSES:
        return {"error": f"Invalid status '{status}'. Valid: {', '.join(TASK_STATUSES)}"}

    transport = get_transport()
    if transport.get_transport_type() == TransportType.HTTP:
        ok = transport.update_task_status(task_id, status)  # type: ignore[attr-defined]
        if not ok:
            return {"error": f"Failed to update task '{task_id}' on Hub"}
        result = transport.get_task_by_id(task_id)  # type: ignore[attr-defined]
        return result if result else {"id": task_id, "status": status}

    # local / git: file-based with lock
    try:
        with lock(f"task-{task_id}"):
            task = Task.load(task_id)
            if task is None:
                return {"error": f"Task '{task_id}' not found"}

            task.update(agent=agent or None, status=status)

            if status in ("approved", "rejected"):
                task.move_to_completed()
            else:
                task.save()
    except LockError:
        return {"error": "Task is locked by another operation; retry shortly"}

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
    """Get a summary of the current AgentWeave session and active tasks.

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
# Agent roster tool
# ---------------------------------------------------------------------------


@mcp.tool()
def list_agents() -> Dict[str, Any]:
    """List all agents in the session with their roles and runners.

    Returns:
        Dict with 'agents' list. Each entry has:
        - name: agent name
        - session_role: principal / delegate / collaborator / reviewer
        - runner: native / claude_proxy / manual
        - dev_roles: list of role IDs from roles.json
        - is_principal: bool
    """
    from ..roles import get_agent_roles, load_roles_config
    from ..session import Session

    session = Session.load()
    if not session:
        return {"agents": []}

    roles_config = load_roles_config()
    agents = []
    for name in session.agent_names:
        runner_cfg = session.get_runner_config(name)
        agents.append(
            {
                "name": name,
                "session_role": session.get_agent_role(name),
                "runner": runner_cfg.get("runner", "native"),
                "dev_roles": get_agent_roles(name, roles_config),
                "is_principal": name == session.principal,
            }
        )

    return {"agents": agents}


# ---------------------------------------------------------------------------
# Checkpoint tool
# ---------------------------------------------------------------------------


@mcp.tool()
def save_checkpoint(
    agent: str,
    session_intent: str,
    files_modified: List[str],
    decisions: List[str],
    next_steps: List[str],
    reason: str = "manual",
    blockers: Optional[List[str]] = None,
    verification_commands: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Save a context checkpoint before compacting or ending a session.

    Write a structured summary to .agentweave/shared/checkpoints/<agent>-<timestamp>.md.
    Call this BEFORE using /compact or handing off to another agent.

    Args:
        agent: Your agent name (e.g. "claude")
        session_intent: One paragraph describing what this session was trying to accomplish
        files_modified: Files you modified, each as "path/to/file — what changed"
        decisions: Decisions made with rationale, e.g. "Use HS256 — simpler key management"
        next_steps: Ordered list of actions for the next session or handoff agent
        reason: Why checkpoint is being written. One of:
                token_threshold | phase_complete | pre_handoff | pre_sleep | manual
        blockers: Optional list of unresolved blockers or open questions
        verification_commands: Optional shell commands that confirm current state

    Returns:
        Dict with 'success' bool, 'path' str (checkpoint file path), or 'error' str.
    """
    from ..constants import SHARED_DIR
    from ..task import Task

    try:
        checkpoints_dir = SHARED_DIR / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate active tasks for this agent
        active_tasks = Task.list_all(active_only=True)
        agent_tasks = [t for t in active_tasks if t.assignee == agent]
        task_rows = (
            "\n".join(f"| {t.id} | {t.title[:60]} | {t.status} |" for t in agent_tasks)
            or "| (none) | | |"
        )

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        dt_display = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        filepath = checkpoints_dir / f"{agent}-{ts}.md"

        files_section = "\n".join(f"- `{f}`" for f in files_modified) or "- (none)"
        decisions_section = (
            "\n".join(f"{i + 1}. {d}" for i, d in enumerate(decisions)) or "1. (none recorded)"
        )
        next_steps_section = (
            "\n".join(f"{i + 1}. {s}" for i, s in enumerate(next_steps)) or "1. (none recorded)"
        )
        blockers_section = "\n".join(f"- [ ] {b}" for b in blockers) if blockers else "- (none)"
        verification_section = (
            "\n".join(f"```bash\n{c}\n```" for c in verification_commands)
            if verification_commands
            else "```bash\n# no verification commands recorded\n```"
        )

        content = f"""# Context Checkpoint — {agent} — {dt_display}

## Session Intent
{session_intent}

## Active Tasks at Checkpoint
| Task ID | Title | Status |
|---------|-------|--------|
{task_rows}

## Files Modified This Session
{files_section}

## Decisions Made
{decisions_section}

## Blockers and Open Questions
{blockers_section}

## Next Steps
{next_steps_section}

## Verification Commands
{verification_section}

---
*Checkpoint saved by: {agent}*
*Reason: {reason}*
"""
        filepath.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": str(filepath),
            "message": (
                f"Checkpoint saved to {filepath}. "
                "Now run /compact and re-read this file to resume."
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Human interaction tools
# ---------------------------------------------------------------------------


@mcp.tool()
def ask_user(
    from_agent: str,
    question: str,
    blocking: bool = False,
) -> Dict[str, Any]:
    """Ask the human user a question.

    If HTTP transport is active, the question is posted to the Hub and the user
    can answer via `agentweave reply --id <question_id> "..."`.
    If local/git transport is active, a message is sent to the 'user' agent as
    a fallback (the human must check their inbox manually).

    Args:
        from_agent: Name of the agent asking the question
        question: The question text
        blocking: If True, signals that the agent cannot continue until answered

    Returns:
        Dict with 'question_id' on success (http), or 'message_id' (local fallback).
    """
    transport = get_transport()
    if transport.get_transport_type() == "http":
        import json as _json
        import urllib.error as _uerr
        import urllib.request as _req

        from ..constants import TRANSPORT_CONFIG_FILE
        from ..utils import load_json as _load_json

        config = _load_json(TRANSPORT_CONFIG_FILE)
        if not config:
            return {"success": False, "error": "No transport config found"}

        url = config["url"].rstrip("/")
        api_key = config["api_key"]
        project_id = config.get("project_id", "")

        body = _json.dumps(
            {
                "from_agent": from_agent,
                "question": question,
                "blocking": blocking,
                "project_id": project_id,
            }
        ).encode()
        request = _req.Request(f"{url}/api/v1/questions", data=body, method="POST")
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        try:
            with _req.urlopen(request, timeout=10) as resp:
                result = _json.loads(resp.read())
            return {"success": True, "question_id": result.get("id")}
        except (_uerr.HTTPError, _uerr.URLError) as exc:
            return {"success": False, "error": str(exc)}
    else:
        # Local/git fallback: send a message to the 'user' agent
        msg = Message.create(
            sender=from_agent,
            recipient="user",
            subject="Question from agent",
            content=f"**Question** (blocking={blocking}):\n\n{question}\n\n"
            "Reply by sending a message back to this agent.",
            message_type="message",
        )
        ok = MessageBus.send(msg)
        if ok:
            return {
                "success": True,
                "message_id": msg.id,
                "note": (
                    "Local transport: question sent as message to 'user' agent. "
                    "Check inbox with: agentweave inbox --agent user"
                ),
            }
        return {"success": False, "error": "Failed to send question via local transport"}


@mcp.tool()
def get_answer(question_id: str) -> Dict[str, Any]:
    """Check if the human has answered a question posted via ask_user().

    Requires HTTP transport. Returns pending=True if not yet answered.

    Args:
        question_id: ID returned by ask_user() (e.g. "q-abc123")

    Returns:
        Dict with 'answered' bool, 'answer' string (if answered), 'pending' bool.
    """
    transport = get_transport()
    if transport.get_transport_type() != "http":
        return {
            "answered": False,
            "answer": None,
            "pending": True,
            "note": (
                "get_answer requires HTTP transport (AgentWeave Hub). "
                "Current transport: " + transport.get_transport_type()
            ),
        }

    import json as _json
    import urllib.error as _uerr
    import urllib.request as _req

    from ..constants import TRANSPORT_CONFIG_FILE
    from ..utils import load_json as _load_json

    config = _load_json(TRANSPORT_CONFIG_FILE)
    if not config:
        return {"answered": False, "answer": None, "pending": True, "error": "No transport config"}

    url = config["url"].rstrip("/")
    api_key = config["api_key"]
    request = _req.Request(f"{url}/api/v1/questions/{question_id}")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Accept", "application/json")
    try:
        with _req.urlopen(request, timeout=10) as resp:
            result = _json.loads(resp.read())
        return {
            "answered": result.get("answered", False),
            "answer": result.get("answer"),
            "pending": not result.get("answered", False),
        }
    except (_uerr.HTTPError, _uerr.URLError) as exc:
        return {"answered": False, "answer": None, "pending": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the AgentWeave MCP server (stdio transport)."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
