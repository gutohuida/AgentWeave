"""The single Hub-owned AgentWeave tool surface.

Turn-start state is injected by the Hub. This server therefore exposes only attributable
outbound intent: messaging, task-ledger work, operator questions, governed agent requests,
and operator-gated scheduled-work mutations.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from fastmcp import FastMCP
except ImportError as exc:
    raise ImportError("fastmcp is required. Install it with: pip install fastmcp") from exc

mcp = FastMCP(
    name="agentweave",
    instructions=(
        "AgentWeave outbound collaboration tools. Turn-start state and queued input are "
        "already present in the prompt; no coordination-state retrieval is necessary. "
        "Identity is bound by the Hub process that started this connection."
    ),
)


class UnboundIdentityError(RuntimeError):
    """Raised when an effect is attempted outside a Hub-bound agent run."""


def _bound_token() -> str:
    token = os.environ.get("AW_RUN_TOKEN", "").strip()
    if not token:
        raise UnboundIdentityError(
            "No bound run credential (AW_RUN_TOKEN is unset); the Hub must start "
            "this tool connection."
        )
    return token


class HubAPIError(RuntimeError):
    """Typed application failure preserved across the MCP adapter."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Hub API error {status_code}: {detail}")


def _hub_request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """Make one authenticated request to the Hub API with bound run attribution."""
    base_url = os.environ.get("HUB_URL", "http://127.0.0.1:8000").rstrip("/")
    token = _bound_token()
    url = f"{base_url}/api/v1/agent-actions{path}"
    if params:
        url += "?" + urllib.parse.urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(detail)
            detail = str(parsed.get("detail", detail))
        except (ValueError, AttributeError):
            pass
        raise HubAPIError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Hub connection error: {exc.reason}") from exc


@mcp.tool()
def send_message(
    to_agent: str,
    subject: str,
    content: str,
    message_type: str = "message",
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an attributable message through the recipient's durable inbound queue."""
    result = _hub_request(
        "POST",
        "/messages",
        {
            "recipient": to_agent,
            "subject": subject,
            "content": content,
            "type": message_type,
            "task_id": task_id,
        },
    )
    return {"success": True, "message_id": result.get("id")}


@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    assignee: Optional[str] = None,
    priority: str = "medium",
    requirements: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a task attributed to the bound agent."""
    return _hub_request(
        "POST",
        "/tasks",
        {
            "title": title,
            "description": description,
            "assignee": assignee,
            "priority": priority,
            "requirements": requirements or [],
            "acceptance_criteria": acceptance_criteria or [],
        },
    )


@mcp.tool()
def list_tasks(agent: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read the shared task ledger, optionally filtered by assignee."""
    return _hub_request("GET", "/tasks", params={"agent": agent})


@mcp.tool()
def get_task(task_id: str) -> Dict[str, Any]:
    """Read one task-ledger entry by ID."""
    return _hub_request("GET", f"/tasks/{task_id}")


@mcp.tool()
def update_task(task_id: str, status: str) -> Dict[str, Any]:
    """Update a task's lifecycle status as the bound agent."""
    return _hub_request("PATCH", f"/tasks/{task_id}", {"status": status})


@mcp.tool()
def ask_user(question: str, blocking: bool = False) -> Dict[str, Any]:
    """Ask the operator a question attributed to the bound agent."""
    result = _hub_request(
        "POST", "/questions", {"question": question, "blocking": blocking}
    )
    return {"success": True, "question_id": result.get("id")}


@mcp.tool()
def get_answer(question_id: str) -> Dict[str, Any]:
    """Check whether the operator answered a previously asked question."""
    question = _hub_request("GET", f"/questions/{question_id}")
    answered = bool(question.get("answered"))
    return {
        "answered": answered,
        "answer": question.get("answer"),
        "pending": not answered,
    }


@mcp.tool()
def request_agent(name: str, template: str, task: str) -> Dict[str, Any]:
    """Request a new agent from a pre-approved template under the project agent budget."""
    return _hub_request(
        "POST", "/agents/request", {"name": name, "template": template, "task": task}
    )


def _job_effect(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _hub_request(method, path, body)


@mcp.tool()
def create_job(
    name: str,
    agent: str,
    message: str,
    cron: str,
    session_mode: str = "new",
) -> Dict[str, Any]:
    """Create recurring work only when the operator enabled the agent-job allowance."""
    return _job_effect(
        "POST",
        "/jobs",
        {
            "name": name,
            "agent": agent,
            "message": message,
            "cron": cron,
            "session_mode": session_mode,
        },
    )


@mcp.tool()
def delete_job(job_id: str) -> Dict[str, Any]:
    """Delete recurring work only when the operator enabled the allowance."""
    return _job_effect("DELETE", f"/jobs/{job_id}")


@mcp.tool()
def toggle_job(job_id: str, enabled: bool) -> Dict[str, Any]:
    """Enable or disable recurring work only under operator allowance."""
    return _job_effect("PATCH", f"/jobs/{job_id}", {"enabled": enabled})


@mcp.tool()
def run_job(job_id: str) -> Dict[str, Any]:
    """Trigger recurring work immediately only under operator allowance."""
    return _job_effect("POST", f"/jobs/{job_id}/run")


def main() -> None:
    """Run the canonical Hub-owned surface over stdio."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
