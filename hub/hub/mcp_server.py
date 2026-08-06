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
from typing import Any, Dict, List, Literal, Optional

try:
    from fastmcp import FastMCP
except ImportError as exc:
    raise ImportError("fastmcp is required. Install it with: pip install fastmcp") from exc

# Constrained parameter values, declared as `Literal` so the generated tool schema carries an
# `enum` every client can read before calling. A bare `str` advertises nothing: Codex agents
# repeatedly guessed `message_type="text"`, were rejected 422 by the Hub, and only succeeded on a
# retry (`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`). `update_task.status` is
# the sharpest case — no default and eight valid states, so a model must supply one blind.
#
# These mirror `hub.schemas.messages._MESSAGE_TYPES`, `hub.schemas.tasks._TASK_STATUSES` /
# `_PRIORITIES`, and `hub.schemas.jobs`'s session-mode check. They are *restated* rather than
# imported on purpose: this module is spawned as a standalone script from an arbitrary working
# directory by both the Claude and Codex transports, and its only imports are stdlib plus fastmcp.
# Importing the Hub package here would make the entire tool surface fail to start if the package
# layout ever changed. `test_mcp_tool_schemas.py` asserts these agree with the validators, so
# drift fails in CI rather than at an agent's first call.
MessageType = Literal["message", "delegation", "review", "discussion", "direct_trigger"]
TaskStatus = Literal[
    "pending",
    "assigned",
    "in_progress",
    "completed",
    "under_review",
    "revision_needed",
    "approved",
    "rejected",
]
TaskPriority = Literal["low", "medium", "high", "critical"]
JobSessionMode = Literal["new", "resume"]

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
    """The Hub was reached and rejected this request — a validation or policy failure,
    not a connectivity problem. Distinct from `HubUnreachableError` (task 5.2): a rejected
    request means the Hub is right there and said no; an unreachable one means nothing
    ever answered, possibly at the wrong address entirely."""

    def __init__(self, status_code: int, detail: str, method: str = "", path: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.path = path
        endpoint = f"{method} {path}".strip()
        prefix = f"Hub rejected {endpoint}" if endpoint else "Hub API error"
        super().__init__(f"{prefix} ({status_code}): {detail}")


class HubUnreachableError(RuntimeError):
    """No Hub answered at this run's configured `HUB_URL` at all — a connectivity or
    misconfiguration failure, distinguishable from `HubAPIError`'s "reached and rejected"
    (task 5.2)."""

    def __init__(self, url: str, method: str, path: str, reason: str) -> None:
        self.url = url
        self.method = method
        self.path = path
        self.reason = reason
        super().__init__(
            f"Cannot reach the Hub at {url} for {method} {path}: {reason}. "
            "Check this run's HUB_URL — it may point at the wrong instance."
        )


def _readable_detail(detail: Any) -> str:
    """Reduce a FastAPI error body to a sentence an agent can act on.

    A Pydantic validation failure arrives as a list of error dicts, and stringifying it verbatim
    produced tool errors like `[{'type': 'value_error', 'loc': ['body', 'type'], 'msg': "Value
    error, type must be one of [...]", 'ctx': {...}}]`. An agent trying to correct itself had to
    parse that. Keep the messages, and name the offending field when the body says which it was.
    """
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            message = str(item.get("msg", "")).removeprefix("Value error, ").strip()
            location = [str(piece) for piece in (item.get("loc") or []) if piece != "body"]
            if location and message:
                parts.append(f"{'.'.join(location)}: {message}")
            elif message:
                parts.append(message)
            else:
                parts.append(str(item))
        if parts:
            return "; ".join(parts)
    return str(detail)


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
            detail = _readable_detail(parsed.get("detail", detail))
        except (ValueError, AttributeError):
            pass
        raise HubAPIError(exc.code, detail, method, path) from exc
    except urllib.error.URLError as exc:
        raise HubUnreachableError(url, method, path, str(exc.reason)) from exc


@mcp.tool()
def send_message(
    to_agent: str,
    subject: str,
    content: str,
    message_type: MessageType = "message",
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an attributable message through the recipient's durable inbound queue.

    Args:
        to_agent: Exact name of a registered agent in this project, as listed in your context.
        subject: Short summary line.
        content: The message body.
        message_type: One of "message", "delegation", "review", "discussion",
            "direct_trigger". Leave unset for an ordinary message.
        task_id: Optional task this message relates to.
    """
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
    priority: TaskPriority = "medium",
    requirements: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a task attributed to the bound agent.

    Args:
        title: Short task title.
        description: What the task involves.
        assignee: Exact name of a registered agent, or unset to leave it unassigned.
        priority: One of "low", "medium", "high", "critical".
        requirements: Optional list of requirements.
        acceptance_criteria: Optional list of acceptance criteria.
    """
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
def update_task(task_id: str, status: TaskStatus) -> Dict[str, Any]:
    """Update a task's lifecycle status as the bound agent.

    Args:
        task_id: The task's ID.
        status: The new lifecycle status. One of "pending", "assigned", "in_progress",
            "completed", "under_review", "revision_needed", "approved", "rejected".
    """
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
    session_mode: JobSessionMode = "new",
) -> Dict[str, Any]:
    """Create recurring work only when the operator enabled the agent-job allowance.

    Args:
        name: Job name.
        agent: Exact name of the registered agent the job triggers.
        message: The message delivered to that agent on each run.
        cron: Cron expression for the schedule.
        session_mode: "new" to start a fresh conversation each run, "resume" to continue.
    """
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
