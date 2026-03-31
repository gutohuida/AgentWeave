"""AgentWeave Hub MCP server — 10 tools backed by the Hub DB.

Can be run as stdio (default) or mounted at /mcp via sse_app().

Usage (stdio):
    python -m hub.mcp_server

Usage (mounted in FastAPI):
    from hub.mcp_server import mcp
    app.mount("/mcp", mcp.sse_app())
"""

import os
import urllib.request
import urllib.parse
import urllib.error
import json as _json
from typing import Any, Dict, List, Optional

try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError("fastmcp is required. Install it with: pip install fastmcp") from e

mcp = FastMCP(
    name="agentweave-hub",
    instructions=(
        "AgentWeave Hub collaboration tools. Use these to communicate with other AI agents, "
        "manage shared tasks, and ask questions to the human user. "
        "Always mark messages as read after processing them."
    ),
)

# ---------------------------------------------------------------------------
# Internal helper — makes authenticated requests to the Hub REST API
# ---------------------------------------------------------------------------


def _hub_request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """Make an authenticated request to the Hub REST API.

    Reads HUB_URL, HUB_API_KEY, and HUB_PROJECT_ID lazily from the environment
    on each call so that the server process can set/override them after import.
    Raises RuntimeError on non-2xx responses.
    """
    base_url = os.environ.get("HUB_URL", "http://localhost:8000")
    api_key = os.environ.get("HUB_API_KEY", "")
    project_id = os.environ.get("HUB_PROJECT_ID", "proj-default")

    url = f"{base_url}/api/v1{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    payload: Optional[bytes] = None
    if body is not None:
        if "project_id" not in body:
            body = {"project_id": project_id, **body}
        payload = _json.dumps(body).encode()

    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Hub API error {exc.code}: {exc.read().decode()}")


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
    """Send a message from one agent to another.

    Args:
        from_agent: Sending agent name (e.g. "claude")
        to_agent: Receiving agent name (e.g. "kimi")
        subject: Short summary
        content: Full message body
        message_type: One of: message, delegation, review, discussion
        task_id: Associated task ID (optional)

    Returns:
        Dict with 'id' of the created message.
    """
    try:
        result = _hub_request(
            "POST",
            "/messages",
            {
                "from": from_agent,
                "to": to_agent,
                "subject": subject,
                "content": content,
                "type": message_type,
                "task_id": task_id,
            },
        )
        return {"success": True, "message_id": result.get("id")}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_inbox(agent: str) -> List[Dict[str, Any]]:
    """Get all unread messages for an agent.

    Args:
        agent: Agent name (e.g. "claude")

    Returns:
        List of message dicts.
    """
    try:
        return _hub_request("GET", "/messages", params={"agent": agent})
    except RuntimeError:
        return []


@mcp.tool()
def mark_read(message_id: str) -> Dict[str, Any]:
    """Mark a message as read.

    Args:
        message_id: ID of the message (e.g. "msg-abc123")

    Returns:
        Dict with 'success' bool.
    """
    try:
        _hub_request("PATCH", f"/messages/{message_id}/read")
        return {"success": True}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------


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
    """Create a new task.

    Args:
        title: Short task title
        description: Full description
        assignee: Agent to assign to
        assigner: Agent creating the task
        priority: low, medium, high, or critical
        requirements: List of requirement strings
        acceptance_criteria: List of acceptance criteria

    Returns:
        Created task dict.
    """
    try:
        return _hub_request(
            "POST",
            "/tasks",
            {
                "title": title,
                "description": description,
                "assignee": assignee,
                "assigner": assigner,
                "priority": priority,
                "requirements": requirements or [],
                "acceptance_criteria": acceptance_criteria or [],
            },
        )
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool()
def list_tasks(agent: Optional[str] = None) -> List[Dict[str, Any]]:
    """List active tasks, optionally filtered by assignee.

    Args:
        agent: Filter by assignee name. Omit to list all tasks.

    Returns:
        List of task dicts.
    """
    try:
        return _hub_request("GET", "/tasks", params={"agent": agent})
    except RuntimeError:
        return []


@mcp.tool()
def get_task(task_id: str) -> Dict[str, Any]:
    """Get full details of a specific task.

    Args:
        task_id: Task ID (e.g. "task-abc123")

    Returns:
        Task dict, or {'error': '...'} if not found.
    """
    try:
        return _hub_request("GET", f"/tasks/{task_id}")
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool()
def update_task(task_id: str, status: str, agent: str = "") -> Dict[str, Any]:
    """Update a task's status.

    Valid statuses: pending, assigned, in_progress, completed,
    under_review, revision_needed, approved, rejected.

    Args:
        task_id: Task ID to update — must be the 'id' field from list_tasks() or
                 create_task() (e.g. "task-abc123"). Do NOT use status names like
                 "pending" as task IDs.
        status: New status value
        agent: Your agent name (for logging)

    Returns:
        Updated task dict, or {'error': '...'} on failure.
    """
    try:
        return _hub_request("PATCH", f"/tasks/{task_id}", {"status": status})
    except RuntimeError as e:
        return {"error": str(e)}


@mcp.tool()
def get_status() -> Dict[str, Any]:
    """Get project status: message counts, task counts, active agents.

    NOTE: task_counts is a dict of {status_name: count} (e.g. {"pending": 2}).
    The keys are status names, NOT task IDs. To get task IDs and details,
    call list_tasks() instead, then use the returned 'id' field with update_task().

    Returns:
        StatusResponse dict with task_counts, message_counts, agents_active, etc.
    """
    try:
        return _hub_request("GET", "/status")
    except RuntimeError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Agent configuration tool
# ---------------------------------------------------------------------------


@mcp.tool()
def get_agent_config(agent: str) -> Dict[str, Any]:
    """Get runner configuration for an agent.

    Returns runner type and, for claude_proxy agents, the base URL and the
    name of the env var that holds the API key. Actual API key values are
    never stored or returned.

    Args:
        agent: Agent name (e.g. "minimax")

    Returns:
        Dict with 'runner', and for claude_proxy agents also 'base_url' and
        'api_key_var'. Returns {'error': '...'} if agent not found.
    """
    try:
        agents = _hub_request("GET", "/agents")
        match = next((a for a in agents if a.get("name") == agent), None)
        if not match:
            return {"error": f"Agent '{agent}' not found"}

        result: Dict[str, Any] = {
            "name": agent,
            "runner": match.get("runner", "native"),
        }

        # For proxy agents, include connection details from the full session blob
        if result["runner"] == "claude_proxy":
            session = _hub_request("GET", "/session/sync")
            agent_cfg = (session.get("data") or {}).get("agents", {}).get(agent, {})
            env_vars = agent_cfg.get("env_vars", {})
            result["base_url"] = env_vars.get("ANTHROPIC_BASE_URL", "")
            result["api_key_var"] = env_vars.get("ANTHROPIC_API_KEY_VAR", "")

        return result
    except RuntimeError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Human interaction tools (NEW)
# ---------------------------------------------------------------------------


@mcp.tool()
def ask_user(
    from_agent: str,
    question: str,
    blocking: bool = False,
) -> Dict[str, Any]:
    """Ask the human user a question via the Hub dashboard.

    The user can answer using `agentweave reply --id <question_id> "..."`.

    Args:
        from_agent: Name of the agent asking the question
        question: The question text
        blocking: If True, signals that the agent cannot continue until answered

    Returns:
        Dict with 'question_id' for use in get_answer().
    """
    try:
        result = _hub_request(
            "POST",
            "/questions",
            {
                "from_agent": from_agent,
                "question": question,
                "blocking": blocking,
            },
        )
        return {"success": True, "question_id": result.get("id")}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_answer(question_id: str) -> Dict[str, Any]:
    """Check if the human has answered a question.

    Args:
        question_id: ID returned by ask_user() (e.g. "q-abc123")

    Returns:
        Dict with 'answered' bool, 'answer' string (if answered), and 'pending' bool.
    """
    try:
        q = _hub_request("GET", f"/questions/{question_id}")
        return {
            "answered": q.get("answered", False),
            "answer": q.get("answer"),
            "pending": not q.get("answered", False),
        }
    except RuntimeError as e:
        return {"answered": False, "answer": None, "pending": True, "error": str(e)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Hub MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
