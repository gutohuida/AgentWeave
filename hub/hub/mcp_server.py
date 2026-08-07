"""The single Hub-owned AgentWeave tool surface.

Turn-start state is injected by the Hub. This server therefore exposes only attributable
outbound intent: messaging, task-ledger work, operator questions, governed agent requests,
and operator-gated scheduled-work mutations.
"""

import json
import os
import re
import time
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
def ask_user(
    questions: List[Dict[str, Any]],
    blocking: bool = True,
) -> Dict[str, Any]:
    """Ask the operator one or more questions and wait for the answers.

    Ask everything you need in a single call. The operator steps through them in one sitting,
    which is one interruption instead of several, and your turn waits once instead of once per
    question.

    Args:
        questions: Between 1 and 4 questions, each a dict with:
            - "question": what you need the operator to decide or clarify.
            - "header": two or three words naming the decision, e.g. "Database".
            - "options": between 2 and 8 answers, each {"label": "...", "description": "..."}.
              The label is what comes back to you; the description is what lets the operator
              choose without already knowing the trade-off — write what picking it actually
              means, not a restatement of the label. There is no way to ask without options: if
              the decision feels open, offer the answers you consider most likely. The operator
              can always reply in their own words instead, so handle an answer that is none of
              yours.
            - "multi_select": True when several options can be chosen together, and that
              answer comes back as a list. False when exactly one applies.
        blocking: Leave this alone to wait for the answers, which is almost always what you
            want. Set it False only to ask something you genuinely do not need answered before
            continuing — you must then poll `get_answer` yourself, and a turn that ends first
            loses the questions.

    Returns a list under "answers", one entry per question, in the order you asked them.
    """
    asked = list(questions)
    result = _hub_request(
        "POST",
        "/questions/batch",
        {"questions": asked, "blocking": blocking},
    )
    rows = result.get("questions") or []
    question_ids = [row.get("id") for row in rows]
    pending = {
        row.get("id"): bool(asked[index].get("multi_select"))
        for index, row in enumerate(rows)
        if index < len(asked)
    }
    if not blocking:
        return {"success": True, "question_ids": question_ids, "answered": False}

    answers: Dict[str, Dict[str, Any]] = {}

    # Waiting is the point: an agent that asks and carries on regardless has guessed, and the
    # operator's answer arrives too late to matter. The wait is bounded for the same reason the
    # permission approver's is — a turn suspended forever is worse than one told nobody replied.
    # The whole batch shares one deadline; the operator is working through them in one sitting.
    deadline = time.monotonic() + QUESTION_ANSWER_TIMEOUT
    while time.monotonic() < deadline and len(answers) < len(question_ids):
        time.sleep(QUESTION_POLL_SECONDS)
        for question_id in question_ids:
            if question_id in answers:
                continue
            try:
                state = _hub_request("GET", f"/questions/{question_id}")
            except Exception:  # noqa: BLE001 - a blip must not end the wait; retry till deadline
                continue
            if state.get("answered"):
                labels = state.get("answer_labels") or []
                answers[question_id] = {
                    "question_id": question_id,
                    "question": state.get("question"),
                    "answered": True,
                    # A multi-select answer stays a list; everything else is the single string
                    # the operator chose or typed. Returning one shape for both would make every
                    # caller re-split a joined string.
                    "answer": labels if (pending.get(question_id) and labels) else state.get("answer"),
                }

    ordered = [
        answers.get(
            question_id,
            {
                "question_id": question_id,
                "question": asked[index].get("question") if index < len(asked) else None,
                "answered": False,
                "answer": None,
            },
        )
        for index, question_id in enumerate(question_ids)
    ]
    unanswered = [entry for entry in ordered if not entry["answered"]]
    payload: Dict[str, Any] = {
        "success": True,
        "question_ids": question_ids,
        "answered": not unanswered,
        "answers": ordered,
    }
    if unanswered:
        payload["note"] = (
            f"{len(unanswered)} of {len(ordered)} question(s) went unanswered within "
            f"{QUESTION_ANSWER_TIMEOUT}s. Continue as best you can and say plainly which "
            "decisions you made without an answer."
        )
    return payload


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


# --- Permission approval -------------------------------------------------------------------
#
# Claude calls the tool named by `--permission-prompt-tool` for each permission decision and
# honours its answer. The contract is undocumented (the flag is hidden from `--help`) and was
# measured against Claude Code 2.1.221; see the change's design.md. Three details are load-bearing:
#
#   1. Claude passes `tool_use_id`. A signature omitting it fails *every* call with a validation
#      error, which the model reports as a broken approval system rather than a denial.
#   2. The answer is a JSON string in a text content block.
#   3. `structuredContent` must be ABSENT. FastMCP derives an output schema from the return
#      annotation and emits `structuredContent: {"result": ...}` alongside the text; with it
#      present a correct "allow" is silently not honoured and the action is refused anyway.
#      This is why `approve_tool_call` has no return annotation. Do not add one.

# `AW_PERMISSION_POSTURE`'s value when the operator, not the Hub, decides each call.
OPERATOR_POSTURE = "operator"

# Bounds on a configured wait. Restated here rather than imported from `api/v1/agents.py`, for the
# same reason `OPERATOR_POSTURE` is: this module is spawned standalone and imports only stdlib and
# fastmcp. A test asserts the two agree.
MIN_WAITING_SECONDS = 10
MAX_WAITING_SECONDS = 600


def _configured_wait(env_name: str, default: int) -> int:
    """Read a per-agent wait from the environment, falling back to the default.

    The Hub puts these in the run's environment the way it already does the workspace boundary and
    the permission posture; there is no database from here. Anything absent, unparseable or out of
    range falls back rather than raising — a turn that dies because a setting was mistyped is worse
    than one that waits the standard time.
    """
    raw = os.environ.get(env_name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if MIN_WAITING_SECONDS <= value <= MAX_WAITING_SECONDS else default


# How long an operator has to answer before the request is denied, and how often the waiting run
# checks. Claude was measured holding a permission tool call open for at least 150s, so the default
# fits inside what the provider tolerates while leaving an operator time to read and click.
OPERATOR_DECISION_TIMEOUT = _configured_wait("AW_DECISION_TIMEOUT", 120)
OPERATOR_POLL_SECONDS = 2

# A question deserves a longer wait than a permission prompt: the operator has to read it and
# compose an answer, not click one of two buttons. 240s is what an ordinary MCP tool call was
# measured tolerating against Claude Code 2.1.221 — the tool answered at exactly 240s and the
# model used the result. The true ceiling is higher but unmeasured, so the default does not exceed
# what was proven. Still bounded: an unanswered wait must end.
QUESTION_ANSWER_TIMEOUT = _configured_wait("AW_QUESTION_TIMEOUT", 240)
QUESTION_POLL_SECONDS = 2

# Input keys whose value is a filesystem path across Claude's built-in tools.
_PATH_KEYS = ("file_path", "path", "notebook_path")

# Absolute paths appearing anywhere in a shell command: POSIX (/x) and Windows (C:\x, C:/x).
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'|;&><)]*")


def _decide(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Decide one permission request. Pure and total: every input maps to a decision.

    Mirrors `codex_appserver.decide_approval`'s contract for the Codex side — an unanswered
    request does not fail a turn, it suspends it forever, so there is no path here that declines
    to answer. Anything unrecognised denies rather than allows.
    """
    if tool_name.startswith("mcp__agentweave__"):
        return {"allow": True, "reason": "the Hub's own tools"}

    workspace = os.environ.get("AW_WORKSPACE_DIR", "").strip()
    if not workspace:
        return {
            "allow": False,
            "reason": (
                "your workspace could not be established, so no action can be checked "
                "against it"
            ),
        }
    try:
        root = os.path.realpath(workspace)
    except OSError:
        return {"allow": False, "reason": "your workspace directory could not be resolved"}

    candidates: List[str] = []
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    command = tool_input.get("command")
    if isinstance(command, str) and command:
        # A shell command carries no declared path argument, so absolute paths are read out of
        # the command text. Relative paths are left alone: they resolve against the run's cwd,
        # which is the workspace. This does not make shell escape impossible -- a command can
        # still build a path at runtime -- and is a boundary, not a sandbox.
        candidates.extend(_ABSOLUTE_PATH_RE.findall(command))

    for candidate in candidates:
        absolute = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
        try:
            resolved = os.path.realpath(absolute)
        except OSError:
            return {"allow": False, "reason": f"{candidate!r} could not be resolved"}
        # `commonpath` compares path components, so it cannot be fooled the way a string prefix
        # can (`/work-other` does not start inside `/work`). Both sides are already real paths,
        # so `..` and symlinks have been collapsed before this comparison.
        try:
            shared = os.path.commonpath([root, resolved])
        except ValueError:  # different drives on Windows
            return {"allow": False, "reason": f"{candidate!r} is outside your workspace"}
        if os.path.normcase(shared) != os.path.normcase(root):
            return {"allow": False, "reason": f"{candidate!r} is outside your workspace"}

    return {"allow": True, "reason": "inside your workspace"}


def _report_decision(tool_name: str, decision: Dict[str, Any], tool_use_id: str) -> None:
    """Tell the Hub what was decided. Observational only — never able to change or delay it.

    Every failure is swallowed, including an unset run token: a decision has already been reached
    by the time this runs, and a Hub that is down, slow, or unreachable must not turn an answered
    request into an unanswered one.
    """
    try:  # noqa: SIM105 - kept explicit; contextlib.suppress hides how deliberate this is
        _hub_request(
            "POST",
            "/permission-decisions",
            {
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "allowed": decision["allow"],
                "reason": decision["reason"],
            },
        )
    except Exception:  # noqa: BLE001, SIM105 - deliberately total and explicit; see docstring
        pass


def _ask_operator(tool_name: str, tool_input: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
    """Put the decision to the operator and block until they answer or the wait runs out.

    Blocking is the point: Claude holds the tool call open while this waits, which is what makes
    an operator prompt possible at all. Measured against Claude Code 2.1.221, it waits at least
    150s (the spike's own limit, not Claude's), so `OPERATOR_DECISION_TIMEOUT` is the budget an
    operator has to answer.

    Timing out denies. It never returns nothing and never waits forever: an unanswered request
    suspends the turn indefinitely, which is the failure this whole design exists to avoid. An
    operator who was away gets a denied action and a record of it, not a stuck agent.
    """
    try:
        opened = _hub_request(
            "POST",
            "/permission-requests",
            {"tool_name": tool_name, "tool_use_id": tool_use_id, "tool_input": tool_input},
        )
        request_id = opened["id"]
    except Exception:  # noqa: BLE001 - see docstring; an unreachable Hub must not hang the turn
        return {
            "allow": False,
            "reason": "the operator could not be asked (the Hub did not accept the request)",
        }

    deadline = time.monotonic() + OPERATOR_DECISION_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(OPERATOR_POLL_SECONDS)
        try:
            state = _hub_request("GET", f"/permission-requests/{request_id}")
        except Exception:  # noqa: BLE001 - a blip must not decide; keep waiting until the deadline
            continue
        if state.get("status") == "allowed":
            return {"allow": True, "reason": "the operator approved this action"}
        if state.get("status") in ("denied", "expired"):
            return {"allow": False, "reason": "the operator refused this action"}
    return {
        "allow": False,
        "reason": (
            f"no operator answered within {OPERATOR_DECISION_TIMEOUT}s, so this was not approved"
        ),
    }


@mcp.tool()
def approve_tool_call(
    tool_name: str,
    input: Dict[str, Any],  # noqa: A002 - Claude sends this key; the name is not ours to choose
    tool_use_id: str = "",
):
    """Runtime approval endpoint. Not an agent capability — the harness calls this, not you."""
    tool_input = input or {}
    if os.environ.get("AW_PERMISSION_POSTURE", "").strip() == OPERATOR_POSTURE:
        # The Hub's own tools are still decided here rather than put to the operator: asking a
        # human to approve each `send_message` would make collaboration unusable, and those calls
        # are already bounded by the run's own credential.
        if tool_name.startswith("mcp__agentweave__"):
            decision = {"allow": True, "reason": "the Hub's own tools"}
        else:
            decision = _ask_operator(tool_name, tool_input, tool_use_id)
    else:
        decision = _decide(tool_name, tool_input)
    _report_decision(tool_name, decision, tool_use_id)
    if decision["allow"]:
        return json.dumps({"behavior": "allow", "updatedInput": input})
    return json.dumps({"behavior": "deny", "message": f"Denied: {decision['reason']}."})


def main() -> None:
    """Run the canonical Hub-owned surface over stdio."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
