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
# Every status an agent may *request* — which is every status except "blocked". That one is
# withheld deliberately: a run does not declare itself to be waiting on a person, the runtime
# observes that it is, by seeing the run end with an unanswered blocking question. An agent that
# could assert "blocked" could claim to be waiting on someone it never asked, which is the one
# claim a completion gate would most reward. Do not add it here to "complete the list" —
# `test_task_transitions.py` asserts this omission on purpose.
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


class MalformedCallError(RuntimeError):
    """A tool argument is the wrong shape, refused here so the agent is told what would work.

    F35. `submit_spec_document` was called **ten times in one turn** before it succeeded, the agent
    guessing a nested schema from raw validator output and a link to a validator's website:

        3 validation errors for call[submit_spec_document]
        scope
          Input should be a valid dictionary [type=dict_type, input_value='The rota/allocate...']
          For further information visit https://errors.pydantic.dev/2.12/v/dict_type

    The cost is the finding: that turn recorded **718,650 input tokens** against 73,622 for the turn
    before it, because every retry resends the whole conversation. One malformed call cost an order
    of magnitude more than the work around it.

    This applies the standard the rest of the surface already meets. `task_transitions.refusal_detail`
    exists because *"an agent told merely 'forbidden' retries the same call"* — it names the current
    state and every reachable one. The tool carrying the largest payload was the one that did not
    follow it.
    """


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
    conversation_id: Optional[str] = None,
    start_new_thread: bool = False,
) -> Dict[str, Any]:
    """Send an attributable message through the recipient's durable inbound queue.

    Args:
        to_agent: Exact name of a registered agent in this project, as listed in your context.
        subject: Short summary line.
        content: The message body.
        message_type: One of "message", "delegation", "review", "discussion",
            "direct_trigger". Leave unset for an ordinary message.
        task_id: Optional task this message relates to.
        conversation_id: Which of the recipient's conversations to send into. Leave unset to
            continue the thread already bound between you and them, or to start one if none is
            bound yet. Sending to an archived conversation fails and returns your content back,
            so you can retry without it.
        start_new_thread: Bypass the bound thread and start a fresh one with this recipient,
            which becomes the new bound thread for later messages. Refused together with an
            explicit conversation_id — naming a thread and asking for a new one are
            contradictory.
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
            "conversation_id": conversation_id,
            "start_new_thread": start_new_thread,
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
    requirement_ids: Optional[List[str]] = None,
    spec_document: Optional[str] = None,
    acceptance_criteria: Optional[List[str]] = None,
    loop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task attributed to the bound agent.

    Args:
        title: Short task title.
        description: What the task involves.
        assignee: Exact name of a registered agent, or unset to leave it unassigned.
        priority: One of "low", "medium", "high", "critical".
        requirements: Free text describing what the task must satisfy. Not a reference — use
            requirement_ids to say which specification requirements this task serves.
        requirement_ids: Identifiers of the specification requirements this task serves, like
            ["FR-3", "FR-7"]. Checked: an identifier the project does not have is refused, naming
            it. This is what makes "which requirements have no work?" answerable.
        spec_document: The document path whose identifiers to resolve against. Only needed when
            more than one document in the project declares the same identifier.
        acceptance_criteria: Optional list of acceptance criteria.
        loop_id: Add this task directly to a loop's queue. Only the loop's own agent, before it
            has fired, may do this — send_message to the loop's agent otherwise.
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
            "requirement_ids": requirement_ids or [],
            "spec_document": spec_document,
            "acceptance_criteria": acceptance_criteria or [],
            "loop_id": loop_id,
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

    Returns a list under "answers", one entry per question, in the order you asked them. Each entry
    says which of three things happened, and they mean different things:

      answered=True                — the operator answered; "answer" holds it.
      declined=True                — the operator saw it and chose not to answer. Nothing further
                                     is coming, so do not ask the same thing again. Decide it
                                     yourself and say plainly which way you went and why.
      answered=False, declined=False — nobody responded before the wait ran out. Unlike a decline,
                                     this does not mean the operator saw it.
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
                    "declined": False,
                    # A multi-select answer stays a list; everything else is the single string
                    # the operator chose or typed. Returning one shape for both would make every
                    # caller re-split a joined string.
                    "answer": (
                        labels if (pending.get(question_id) and labels) else state.get("answer")
                    ),
                }
            elif state.get("declined"):
                # The operator closed it without answering, so there is nothing further to wait
                # for. Ending here rather than at the deadline is the point: waiting out the
                # timeout would spend the interval on a decision already made and arrive at a
                # weaker conclusion than the one available now.
                #
                # Reported as a decline, not as an expiry. An expiry means nobody was there; a
                # decline means someone was and chose not to answer, which says the call is yours.
                answers[question_id] = {
                    "question_id": question_id,
                    "question": state.get("question"),
                    "answered": False,
                    "declined": True,
                    "answer": None,
                }

    ordered = [
        answers.get(
            question_id,
            {
                "question_id": question_id,
                "question": asked[index].get("question") if index < len(asked) else None,
                "answered": False,
                # Nothing was recorded for this one before the deadline, so it expired rather than
                # being declined — a distinction the caller is entitled to.
                "declined": False,
                "answer": None,
            },
        )
        for index, question_id in enumerate(question_ids)
    ]
    unanswered = [entry for entry in ordered if not entry["answered"]]
    declined = [entry for entry in ordered if entry.get("declined")]
    expired = [entry for entry in unanswered if not entry.get("declined")]
    payload: Dict[str, Any] = {
        "success": True,
        "question_ids": question_ids,
        "answered": not unanswered,
        "answers": ordered,
    }
    if unanswered:
        # Said separately because the two call for the same action but rest on different facts: a
        # decline is a decision the operator made and handed back, an expiry is silence. Reporting
        # both as "went unanswered" would lose that, and it is the more useful half.
        parts = []
        if declined:
            parts.append(
                f"{len(declined)} of {len(ordered)} question(s) were declined — the operator saw "
                "them and chose not to answer. Do not re-ask those."
            )
        if expired:
            parts.append(
                f"{len(expired)} of {len(ordered)} question(s) went unanswered within "
                f"{QUESTION_ANSWER_TIMEOUT}s."
            )
        parts.append(
            "Continue as best you can and say plainly which decisions you made without an answer."
        )
        payload["note"] = " ".join(parts)
    return payload


@mcp.tool()
def get_answer(question_id: str) -> Dict[str, Any]:
    """Check whether the operator answered a previously asked question.

    A question can also be *declined* — the operator closed it without answering. That is settled,
    not pending: nothing further is coming, and the decision is yours to make.
    """
    question = _hub_request("GET", f"/questions/{question_id}")
    answered = bool(question.get("answered"))
    declined = bool(question.get("declined"))
    return {
        "answered": answered,
        "declined": declined,
        "answer": question.get("answer"),
        # A declined question is not waiting on anyone, so reporting it as pending would have a
        # poller wait forever for something that has already been decided.
        "pending": not answered and not declined,
    }


@mcp.tool()
def submit_checkpoint_notes(
    intent: str,
    suspicions: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record what you know that this conversation's record does not, for its next checkpoint.

    The Hub writes the checkpoint itself from the conversation record, and already knows which
    files changed, which tasks are assigned, what is unanswered, and when everything happened.
    Do not restate any of that here.

    Write for somebody else. The checkpoint these notes feed is read by whichever agent the
    Hub picks up the work next, which may not be you and may not even be working your task —
    a reviewer of what you just finished reads it too. Anything you would only understand
    yourself is lost at that handover, so name the file, the task and the decision in full
    rather than referring back to them.

    Give only what cannot be read back from the transcript:
      intent     — what was in the middle of being done, and what comes next.
      suspicions — what is believed but unverified, and what would confirm or refute it.
      warnings   — what the next agent should not repeat, assume, or waste time re-deriving.

    Keep it brief; a few hundred words in total is right. These notes are one input among
    several, not the checkpoint — the checkpoint is produced whether or not you call this.
    """
    return _hub_request(
        "POST",
        "/checkpoint-notes",
        {
            "intent": intent,
            "suspicions": list(suspicions or []),
            "warnings": list(warnings or []),
        },
    )


@mcp.tool()
def recall(observation_id: str) -> Dict[str, Any]:
    """Retrieve one recorded observation a checkpoint cited, exactly as it was recorded.

    A checkpoint is a summary, and summaries lose detail. Where it lists ids under "Recorded
    observations", this returns the original text in full — use it instead of guessing at what a
    summary compressed away, and instead of re-running a tool to find out.

    Only observations cited by a checkpoint you are permitted to read are available. Anything
    else returns not-found, whether or not it exists.
    """
    return _hub_request("GET", f"/recall/{observation_id}")


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
        cron: Cron expression for the schedule. Defaults to every five minutes, which is cheap:
            a firing whose agent is already running is refused before it claims or queues
            anything and records nothing at all, and a firing against a stalled queue counts on
            the existing record rather than adding another. So a frequent schedule costs a query
            and no rows, and it bounds how long a finished step waits before the next one starts.
            Choose a slower one only when the work itself is periodic — nightly, weekly — rather
            than to avoid waste.
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
def create_loop(
    name: str,
    agent: str,
    message: str,
    cron: str = "*/5 * * * *",
    purpose: str = "",
    stop_at: Optional[str] = None,
    stop_when_queue_empties: bool = False,
    spec_document_id: Optional[str] = None,
    initial_tasks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a loop: recurring work with a stated purpose and a stop condition.

    One agent, one task at a time. Use create_flow instead when the work comes from an approved
    specification document and should be decomposed across several agents, with finished work
    reviewed by somebody other than whoever did it.

    Continuity across firings is by checkpoint (see submit_checkpoint_notes), never by a
    resumed session — every firing starts fresh. Refused outright with no stop condition: a
    loop that cannot stop is not created, and refused with a document: that is a flow.

    Args:
        name: Job name.
        agent: Exact name of the registered agent the loop triggers.
        message: The message delivered to that agent on each firing.
        cron: Cron expression for the schedule.
        purpose: What this loop exists to do — carried into every firing's briefing.
        stop_at: ISO-8601 timestamp after which the loop stops firing. At least one of
            stop_at or stop_when_queue_empties is required.
        stop_when_queue_empties: Stop once this loop's queue has no open task left.
        spec_document_id: Not accepted here — declaring a document makes this a flow. Kept in
            the signature so the refusal can name create_flow rather than the call failing as an
            unexpected argument, which tells the caller nothing about what to do instead.
        initial_tasks: Tasks to seed the queue with, created in this same call. Each entry is
            a dict with "title" required and the same optional fields create_task accepts:
            description, assignee, priority, requirements, requirement_ids, spec_document,
            acceptance_criteria.
    """
    if stop_at is None and not stop_when_queue_empties:
        raise HubAPIError(
            400,
            "a loop needs a stop condition: supply stop_at or stop_when_queue_empties=True",
            "POST",
            "/jobs",
        )
    if spec_document_id is not None:
        raise HubAPIError(
            400,
            "a loop that declares a specification document is a flow: call create_flow instead, "
            "which decomposes the document across several agents and has finished work reviewed "
            "by somebody other than whoever did it",
            "POST",
            "/jobs",
        )
    return _job_effect(
        "POST",
        "/jobs",
        {
            "name": name,
            "agent": agent,
            "message": message,
            "cron": cron,
            "purpose": purpose,
            "stop_at": stop_at,
            "stop_when_queue_empties": stop_when_queue_empties,
            "spec_document_id": spec_document_id,
            "initial_tasks": initial_tasks,
        },
    )


@mcp.tool()
def create_flow(
    name: str,
    agent: str,
    message: str,
    spec_document_id: str,
    cron: str = "*/5 * * * *",
    purpose: str = "",
    stop_at: Optional[str] = None,
    stop_when_queue_empties: bool = False,
    initial_tasks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a flow: a loop that decomposes an approved specification document.

    A flow differs from a loop in what it does with its queue, not in what it is. Each firing
    starts every task whose prerequisites are met and for which an agent is available, so
    independent work runs in parallel; and a task somebody finished becomes claimable by anybody
    except its author, which is how work gets reviewed without anyone being asked to hand it over.

    `agent` is the default, not the mandate — the agent a firing uses when nothing else has said
    otherwise. Reviewers are resolved per task: the document's declared reviewer if it names one
    and that name resolves, otherwise any agent that is idle and holding no work. A step nobody can
    review is surfaced to the operator; the rest of the queue carries on.

    Everything else is a loop's: one stop condition is required, continuity across firings is by
    checkpoint rather than a resumed session, and the checkpoint is the flow's rather than any one
    agent's — so a reviewer starts from what the implementer recorded.

    Args:
        name: Job name.
        agent: Exact name of the registered agent this flow fires by default.
        message: The message delivered on each firing, after the briefing.
        spec_document_id: The specification document this flow decomposes. Required — a flow
            without one is a loop. Tasks materialised from the document, once it is approved, are
            added to this flow's queue automatically.
        cron: Cron expression for the schedule.
        purpose: What this flow exists to do — carried into every firing's briefing.
        stop_at: ISO-8601 timestamp after which the flow stops firing. At least one of
            stop_at or stop_when_queue_empties is required.
        stop_when_queue_empties: Stop once this flow's queue has no open task left.
        initial_tasks: Tasks to seed the queue with, created in this same call. Each entry is
            a dict with "title" required and the same optional fields create_task accepts:
            description, assignee, priority, requirements, requirement_ids, spec_document,
            acceptance_criteria.
    """
    # Both refusals are client-side and precede any HTTP call, matching `create_loop`'s own
    # stop-condition check. The document one is **not** made redundant by the `str` annotation:
    # the annotation is what a well-behaved client enforces before calling, and this is what
    # catches an empty string, or a `None` arriving from a client that did not.
    if stop_at is None and not stop_when_queue_empties:
        raise HubAPIError(
            400,
            "a flow needs a stop condition: supply stop_at or stop_when_queue_empties=True",
            "POST",
            "/jobs",
        )
    if not spec_document_id:
        raise HubAPIError(
            400,
            "a flow decomposes a specification document: supply spec_document_id, or call "
            "create_loop for recurring work that has no document behind it",
            "POST",
            "/jobs",
        )
    # Byte-identical to `create_loop`'s body but for the document, and deliberately so: design D1
    # says a flow is a configuration rather than a record, so there is one route and one row. If
    # these two payloads ever diverge, a `Flow` table has grown in all but name.
    return _job_effect(
        "POST",
        "/jobs",
        {
            "name": name,
            "agent": agent,
            "message": message,
            "cron": cron,
            "purpose": purpose,
            "stop_at": stop_at,
            "stop_when_queue_empties": stop_when_queue_empties,
            "spec_document_id": spec_document_id,
            "initial_tasks": initial_tasks,
        },
    )


@mcp.tool()
def archive_job(job_id: str) -> Dict[str, Any]:
    """Archive recurring work. Nothing is deleted; the job simply stops running.

    Every call puts this exact request to the operator and waits for an explicit answer,
    regardless of this run's permission posture (design D18) — the standing scheduled-work
    allowance (`project.allow_agent_jobs`) grants the *capability* to reach this tool at all,
    it does not supply the *direction* to use it on this job, right now. An `auto` posture
    would otherwise wave every call through unattended, which is the opposite of what
    "explicit direction from the operator" means. This is the first tool on this surface with
    an always-confirm rule — do not treat it as a precedent for any other tool.

    Refused if the job has a loop: a loop is archived by the operator only, never an agent
    (mirrors `create_loop`'s "continuity is by checkpoint, not resume" rule).
    """
    decision = _ask_operator("archive_job", {"job_id": job_id}, tool_use_id=f"archive-{job_id}")
    if not decision["allow"]:
        raise HubAPIError(
            403,
            f"archiving this job was not approved: {decision['reason']}",
            "POST",
            f"/jobs/{job_id}/archive",
        )
    return _job_effect("POST", f"/jobs/{job_id}/archive")


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
                "your workspace could not be established, so no action can be checked " "against it"
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


def _report_wait_ended(request_id: str) -> None:
    """Tell the Hub this run has stopped waiting on a request, so the card stops pretending.

    Best-effort on exactly the terms `_report_decision` sets out, and for the same reason: the
    decision is already made by the time this runs. A Hub that is down must not delay the answer,
    change it, or raise — the run's end sweeps what this fails to report (design D1).
    """
    try:  # noqa: SIM105 - kept explicit; contextlib.suppress hides how deliberate this is
        _hub_request("POST", f"/permission-requests/{request_id}/expire")
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
        if state.get("status") == "denied":
            return {"allow": False, "reason": "the operator refused this action"}
        if state.get("status") == "expired":
            # Someone else closed the request — the run-end sweep, or a previous report. Saying
            # "the operator refused" here would attribute a refusal to a person who never made one.
            return {
                "allow": False,
                "reason": "this request is no longer open, so it was not approved",
            }

    _report_wait_ended(request_id)
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


# ---------------------------------------------------------------------------
# Specification documents
# ---------------------------------------------------------------------------

# Restated, not imported — see the note at the top of this file. `test_mcp_tool_schemas.py`
# asserts these agree with `hub.spec_payload`, so drift fails in CI rather than at an agent's
# first call.
SpecKind = Literal["baseline", "system-map", "roadmap", "change-spec", "capability"]
SPEC_SCHEMA_VERSION = 1

# The one closed vocabulary in the evidence surface, restated for the same reason as the rest.
#
# `kind` is deliberately **not** constrained here: `db.models.EVIDENCE_KINDS` is open at the edges
# on purpose — the list is what the surfaces know how to label, not what they accept — and a
# `Literal` would make this tool narrower than the route it calls, which
# `agent-capability-plane` forbids in either direction.
EvidenceDecision = Literal["accepted", "rejected"]


@mcp.tool()
def create_spec_document(title: Optional[str] = None) -> Dict[str, Any]:
    """Start a specification document when you need one — you do not need the operator to start it.

    Use this the moment you have something worth writing up: a finding, a proposal, a design
    worth recording. It creates the document and returns immediately so you keep working in the
    same turn — there is nothing to wait for and nobody to ask.

    This is step one of a three-call flow: `create_spec_document` → work out the subject →
    `rename_spec_document` → `submit_spec_document`. The `path` this returns is a placeholder —
    a colour and a mythic animal, meaning nothing about the document's actual subject. Call
    `rename_spec_document` as soon as you know what the document is about, and use the path it
    returns for everything after, including `submit_spec_document`.

    There is no `path` and no `kind` argument: the Hub always mints the path and the document is
    always a `change-spec` — the one kind whose lifecycle (exploring, proposed, approved,
    archived) is meant to be filled in and then gated by the operator. `title` is optional and
    only cosmetic — it shows in the operator's list before the rename lands, and does not affect
    the path.

    Returns the minted `path` and the `phase` it starts in (`exploring`).
    """
    body: Dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    return _hub_request("POST", "/spec/documents/create", body)


#: What each structured field of `submit_spec_document` must be, and one call that works. Keyed in
#: the order the tool declares them, because the refusal names the first thing wrong and an agent
#: fixing them top to bottom converges rather than ping-ponging.
#:
#: The example is the load-bearing half. An agent told "expected object, got string" still has to
#: invent the object; one shown `{"in": [...], "out": [...]}` does not. Restated here rather than
#: imported: this module is spawned standalone and imports only stdlib plus fastmcp (see the module
#: docstring), and `test_mcp_server_shapes_agree.py` asserts this table and the Hub's own contract
#: do not drift apart.
_SUBMIT_SHAPES = (
    ("scope", dict, "an object", '{"in": ["allocate.py"], "out": ["the CLI"]}'),
    (
        "requirements",
        list,
        "a list of objects",
        '[{"key": "fair-spread", "statement": "spread() counts every staff member", '
        '"modal": "MUST"}]',
    ),
    (
        "acceptance_criteria",
        list,
        "a list of objects",
        '[{"requirement": "fair-spread", "given": "a member with no shifts", '
        '"when": "spread() runs", "then": "they are counted"}]',
    ),
    (
        "tasks",
        list,
        "a list of objects",
        '[{"key": "fix-spread", "title": "Count idle staff", "satisfies": ["fair-spread"]}]',
    ),
    (
        "algorithms",
        list,
        "a list of objects",
        '[{"key": "spread", "steps": ["sum shifts", "divide by headcount"]}]',
    ),
    ("evidence", dict, "an object", '{"commands": ["pytest -q"]}'),
    (
        "open_questions",
        list,
        "a list of objects",
        '[{"question": "Does an absent member count?", "blocking": true}]',
    ),
)


def _check_submit_shapes(supplied: Dict[str, Any]) -> None:
    """Refuse a malformed `submit_spec_document` call by naming the field, the shape and an example.

    Raises `MalformedCallError` on the first field that is wrong. One at a time deliberately: the
    measured failure was an agent working through *eleven* simultaneous validation errors, which is
    a wall to parse rather than an instruction to follow.

    A string where an object or list is wanted is by far the common case — it is what the agent did
    on its first attempt, putting prose into `scope` — so it is named explicitly rather than left to
    be inferred from a type name.
    """
    for name, want_type, want_label, example in _SUBMIT_SHAPES:
        value = supplied.get(name)
        if value is None or isinstance(value, want_type):
            continue
        got = "text" if isinstance(value, str) else type(value).__name__
        raise MalformedCallError(
            f"`{name}` must be {want_label}, but {got} was supplied. "
            f"Write it as, for example: {name}={example}. "
            f"Prose belongs in `summary`, `problem` or `design`, which are plain strings — "
            f"every other field here is structured, and the Hub renders it into the document."
        )


@mcp.tool()
def submit_spec_document(
    path: str,
    title: str,
    kind: SpecKind,
    schema_version: int = SPEC_SCHEMA_VERSION,
    summary: str = "",
    problem: str = "",
    design: str = "",
    lifecycle: str = "",
    # `Any` rather than `Dict[...]`/`List[...]`, and this is a trade-off rather than a tidy win.
    # A precise annotation makes the framework refuse a wrong shape before this function runs, with
    # the message F35 measured at 718,650 input tokens across ten retries. `Any` routes the same
    # call to `_check_submit_shapes`, which names the field and shows one that works.
    #
    # What it costs: the advertised JSON schema for these seven fields becomes untyped, where it
    # previously said `object`/`array`. Accepted because the docstring below is where this tool's
    # shape guidance actually lives — it documents every field key by key, which is strictly more
    # than a bare type — and because in the one measured instance the precise schema did not
    # prevent the mistake while the resulting error dominated the turn's cost.
    #
    # Revisit if fastmcp gains a way to override a parameter's schema, or if this module's
    # stdlib-plus-fastmcp rule is relaxed enough to reach `pydantic.Field`. Either would give both
    # halves instead of the better one.
    scope: Optional[Any] = None,
    requirements: Optional[Any] = None,
    acceptance_criteria: Optional[Any] = None,
    tasks: Optional[Any] = None,
    algorithms: Optional[Any] = None,
    evidence: Optional[Any] = None,
    open_questions: Optional[Any] = None,
) -> Dict[str, Any]:
    """Write a specification document. You supply structure; the Hub renders the document.

    Never write specification HTML yourself — it will not be treated as a document. Submit the
    structure here and the Hub produces the markup, the anchors, and the identifiers.

    The document must already exist — call `create_spec_document` first if you don't have one yet.
    Submitting repeatedly is normal and expected — a document under discussion is incomplete, and
    saving an incomplete one is not an error. The response lists what still blocks it from being
    proposed.

    You cannot approve a document, propose it, or set its phase. There is no argument here that
    does so. Approval is the operator's decision and is taken elsewhere.

    At `sketch` rigor (the default) this writes the document immediately, as above. At `contract`
    or `gate` rigor it does not: your submission is diffed against what is stored and recorded as
    one pending proposal per changed requirement plus one for everything else, for an operator to
    accept or reject. The response then carries `proposals`/`unchanged` instead of `identifiers`/
    `divergence` — check which shape came back rather than assuming a write happened.

    `requirements` — objects with:
      `key`      stable handle, lowercase and hyphenated, unique in this document. Keep it across
                 rewordings: it is how the requirement's permanent identifier survives an edit.
                 It is not the identifier and never appears in a link. The Hub assigns identifiers.
      `statement` what the system does, observable from outside, specific enough to be wrong.
                 "a search returns within 200ms for a corpus under 10k documents", not "it is fast".
      `modal`    MUST, SHOULD, MAY or SHALL. A requirement with no obligation cannot be satisfied
                 or violated, and is refused.
      `rationale` optional: why the rule exists, when that is not obvious. A rule with a stated
                 reason survives an edge case nobody listed.
      `party`    optional: "producer" (what a sender may emit) or "consumer" (what a receiver must
                 do with it). Collapsing them hides which side of a boundary a defect is on.

    `acceptance_criteria` — objects with `key`, `requirement` (a requirement's key), and
      `given`/`when`/`then`. One per behaviour, binary pass or fail.

    `tasks` — objects with `key`, `description` (one concrete unit of work, not "build the whole
      thing"), `requirements` (keys this task satisfies; at least one, or it is work nobody
      asked for), and optionally `title`. Approving the document creates these as real tasks, and
      `title` is the name the board shows — a few words, not the sentence. Without one a name is
      derived from the description, which reads as prose because that is what it is.

    `algorithms` — objects with `name` and `steps`. Ordered or conditional behaviour goes here
      rather than in a paragraph, where the order has to be guessed at.

    `scope` — `{"in_scope": [...], "non_goals": [...]}`. Non-goals are required before a document
      can be proposed: omission is silence, not a non-goal.

    `evidence` — `{"checked": [...], "limits": [...]}`. What you inspected and what it validates,
      and what remains untested or inferred. A green suite says the code satisfies the tests that
      exist, not that the tests correspond to the requirements.

    `open_questions` — objects with `question` and `resolved`. An unresolved one blocks the
      document: a guess written in the voice of a requirement is built on as though it were a
      decision.

    Returns the path, the phase, the identifier assigned to each requirement key, and `blocking` —
    what would refuse a proposal right now.
    """
    document: Dict[str, Any] = {
        "schema_version": schema_version,
        "kind": kind,
        "title": title,
        "summary": summary,
        "problem": problem,
        "design": design,
        "lifecycle": lifecycle,
    }
    # Only send what was supplied. A key present with a null value is not the same as an absent
    # one to a validator, and `send_message`'s conversation_id outage came from exactly that.
    optional = {
        "scope": scope,
        "requirements": requirements,
        "acceptance_criteria": acceptance_criteria,
        "tasks": tasks,
        "algorithms": algorithms,
        "evidence": evidence,
        "open_questions": open_questions,
    }
    # Before anything is sent. These are annotated `Any` so that a wrong shape reaches this check
    # rather than being refused by the framework's own validator, whose message was the finding
    # (F35) — the Hub still validates the contents server-side and remains the authority.
    _check_submit_shapes(optional)
    for name, value in optional.items():
        if value is not None:
            document[name] = value

    return _hub_request("POST", "/spec/documents", {"path": path, "document": document})


@mcp.tool()
def rename_spec_document(path: str, subject: str) -> Dict[str, Any]:
    """Rename the specification document once you know what it is about.

    A document is created before anyone knows its subject, so it starts with a deliberately
    meaningless name — a colour and a mythic animal. As soon as the interview establishes what
    the document actually covers, call this.

    Args:
        path: The document's current path, as given in your turn context.
        subject: What the document is about, in plain words — "Personal houseplant watering
            tracker". Not a path and not a slug: the Hub derives the path from this.

    Returns the new `path` and the `previous_path`. **Use the new path for anything else you do
    with this document in this turn**, including `submit_spec_document` — the old one no longer
    resolves.

    Refused when the document is approved, when the subject contains no usable words, or when
    another document already occupies the name.
    """
    return _hub_request("POST", "/spec/documents/rename", {"path": path, "subject": subject})


@mcp.tool()
def read_spec_document(
    path: str, include: Literal["requirements", "full"] = "requirements"
) -> Dict[str, Any]:
    """Read the specification document you were told to implement.

    **Use this before writing code against a document.** The document lives in the project
    directory, not in your working copy, so you almost certainly cannot open it as a file. Working
    from a summary, or from another agent's description of it, is how an implementation quietly
    stops matching what was approved.

    Args:
        path: The document's path, as given in your turn context.
        include: `requirements` (the default) returns the problem, scope and every requirement.
            `full` adds the design, declared tasks, algorithms and evidence sections.

    Each requirement carries the `identifier` the Hub minted for it — `FR-1`, `FR-2` — along with
    its `statement`, its `modal` (MUST/SHOULD/MAY/SHALL) and its own `acceptance_criteria`. **Quote
    those identifiers**: they are what tasks, evidence and completion gates refer to, so naming them
    is how your work is traceable to what it satisfies.

    Also returns `phase` and `rigor`, which say how settled this document is. Readable at any phase
    — an unapproved document is still worth reading, and its phase tells you not to build on it yet.

    A `diagnostics` entry appears where the document and the Hub's index disagree, or where the
    document carries no structured content at all.
    """
    return _hub_request("GET", "/spec/documents", params={"path": path, "include": include})


@mcp.tool()
def record_evidence(
    identifier: str,
    summary: str = "",
    kind: str = "test_result",
    locator: str = "",
    document: str = "",
    task_id: str = "",
) -> Dict[str, Any]:
    """Record what demonstrates that a requirement is satisfied.

    **This is what lets approved work merge.** Approving a task integrates nothing until some
    evidence for its requirements has been accepted — without it the operator is told there is
    nothing to merge, and you are the one who could have prevented that.

    Evidence enters `awaiting`, never `accepted`. A careful agent and a careless one report success
    in the same words with the same authority, so what you record is a claim until somebody else
    decides on it.

    Args:
        identifier: The requirement this demonstrates, as `FR-1`. Read the document if you are not
            sure which one your work satisfies.
        summary: What you did and what it showed, in your own words. Anything that would let
            somebody else judge whether the requirement is met.
        kind: What sort of thing this is — `test_result`, `manual_observation`, and so on. Not a
            closed list; use a word that describes it.
        locator: Where the artifact lives, if it has one — a path, a command, a run id.
        document: Only needed when the same identifier exists in more than one document.
        task_id: The task this came out of, when there is one.

    Returns the evidence `id`, its `identifier` and its `review_state`.
    """
    return _hub_request(
        "POST",
        "/spec/evidence",
        {
            "identifier": identifier,
            "summary": summary,
            "kind": kind,
            "locator": locator,
            **({"document": document} if document else {}),
            **({"task_id": task_id} if task_id else {}),
        },
    )


@mcp.tool()
def list_evidence(
    identifier: str = "", document: str = "", review_state: str = ""
) -> Dict[str, Any]:
    """Read the evidence this project holds.

    Use this before deciding on anything: a decision names one specific piece of evidence, so this
    is how you find out what there is. Each row says who produced it, what requirement it is
    against, and — where the project is a repository — which branch and commit it was taken from,
    which is how you can tell whether it describes the work you think it does.

    Args:
        identifier: Narrow to one requirement, as `FR-1`.
        document: Only needed when the same identifier exists in more than one document.
        review_state: Narrow to `awaiting`, `accepted` or `rejected`. `awaiting` is what is waiting
            on somebody.

    Returns `{"evidence": [...]}`.
    """
    return _hub_request(
        "GET",
        "/spec/evidence",
        params={
            "identifier": identifier or None,
            "document": document or None,
            "review_state": review_state or None,
        },
    )


@mcp.tool()
def decide_evidence(
    evidence_id: str, decision: EvidenceDecision, reason: str = ""
) -> Dict[str, Any]:
    """Accept or reject evidence somebody else recorded.

    Accepting is a judgement that the evidence really demonstrates the requirement — and accepted
    evidence is what allows approving a task to merge the work. Rejecting says it does not, and is
    the same operation: use it rather than staying silent about evidence that does not hold up.

    Refused unless the operator has granted you this. It is authority over what ships, not a
    reading permission, so it is conferred deliberately or not at all.

    **You cannot decide evidence you produced yourself.** Another agent, or the operator, decides
    on yours.

    Args:
        evidence_id: From `list_evidence`.
        decision: `accepted` or `rejected`.
        reason: Why. This is the durable record of the judgement, so say what you checked.

    Returns the evidence `id` and its new `review_state`.
    """
    return _hub_request(
        "POST",
        f"/spec/evidence/{evidence_id}/decision",
        {"decision": decision, "reason": reason},
    )


def main() -> None:
    """Run the canonical Hub-owned surface over stdio."""
    mcp.run(transport="stdio", show_banner=False)


# MUST stay the last thing in this file. `mcp.run()` does not return, so anything defined below
# this guard is never reached when the server is spawned as a script — which is exactly how the
# Hub spawns it. `submit_spec_document` was added after this block and was therefore invisible to
# every agent while being perfectly visible to every test, because tests import the module and an
# import runs the whole file. An agent spent three rounds interviewing an operator, settled the
# scope, and reported the tool "not available in this session".
#
# `test_mcp_server_stdio_surface.py` spawns this file the way the Hub does and lists the tools over
# the wire, which is the only check that can see this class of mistake.
if __name__ == "__main__":
    main()
