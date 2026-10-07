"""The single Hub-owned AgentWeave tool surface.

Turn-start state is injected by the Hub. This server therefore exposes only attributable
outbound intent: messaging, task-ledger work, operator questions, governed agent requests,
and operator-gated scheduled-work mutations.
"""

import codecs
import contextlib
import fnmatch
import inspect
import json
import locale
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

# Call mode (`a-run-reaches-the-hub-without-mcp`, design D3/D4): the same file, spawned as
# `<python> -I -S <this file> --call <tool> [<args.json>]` by the `aw-tool` launcher, calls one
# tool function and prints one JSON envelope. It is decided **before** the fastmcp import, which
# alone costs ~1.4 s per process against ~0.1 s for the stdlib, and every call pays it. Tests
# import the module (`__name__ != "__main__"`), so they always take the fastmcp path.
_CALL_MODE = __name__ == "__main__" and sys.argv[1:2] == ["--call"]


class _CallRegistry:
    """The stdlib stand-in for `FastMCP` in call mode: `.tool()` registers nothing and returns the
    function unchanged, which is what fastmcp 3.1's own decorator returns too."""

    def __init__(self, name: str, instructions: str = "") -> None:
        self.name = name
        self.instructions = instructions

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return lambda fn: fn


if _CALL_MODE:
    FastMCP: Any = _CallRegistry
else:
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

#: Every tool an agent can call, by name: what `--list`, `call_main` and the approver's
#: recognition of the call command read (design D3, review note 12). Filled by `_tool()`, so a tool
#: added with it is callable through the call command automatically, and the set is a plain dict in
#: both modes -- enumerating fastmcp's registry is async or private. `approve_tool_call` is a
#: runtime endpoint, not an agent operation, and is left out by name.
_CALLABLE_TOOLS: Dict[str, Callable[..., Any]] = {}
_NOT_CALLABLE = frozenset({"approve_tool_call"})


def _tool() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """`@mcp.tool()`, recording the function as callable through the call command."""
    register = mcp.tool()

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if fn.__name__ not in _NOT_CALLABLE:
            _CALLABLE_TOOLS[fn.__name__] = fn
        return register(fn)

    return decorate


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

    def __init__(
        self,
        status_code: int,
        detail: str,
        method: str = "",
        path: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.path = path
        # The refusal's own body, when it had structure, alongside the sentence `_readable_detail`
        # reduced it to. Added for `archive_job`: a "direction required" failure carries the id of
        # the request the operator is now looking at, and an adapter that had only the prose would
        # have to parse an identifier back out of a sentence written for a person.
        self.data: Dict[str, Any] = data or {}
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

    **The same failure had a second shape (F152).** A refusal carrying structure arrives as a
    *dict* — the transition gate's is the one that matters most, since its whole value is a sentence
    the agent has to act on — and fell through to `str(detail)`, so the agent read
    `{'code': 'gate_unsatisfied', 'blocking': [], ..., 'message': 'This task ...'}` with the sentence
    buried in it. Every reachable producer on this plane composes the whole sentence into `message`,
    including the field path where there is one (`PayloadError` puts it there), so nothing is lost by
    returning it. Guarded on a non-empty string so a plain-string detail and any future messageless
    dict keep today's behaviour.
    """
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
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
        structured: Optional[Dict[str, Any]] = None
        try:
            parsed = json.loads(detail)
            body = parsed.get("detail", detail)
            if isinstance(body, dict):
                structured = body
            detail = _readable_detail(body)
        except (ValueError, AttributeError):
            pass
        raise HubAPIError(exc.code, detail, method, path, structured) from exc
    except urllib.error.URLError as exc:
        raise HubUnreachableError(url, method, path, str(exc.reason)) from exc


@_tool()
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

    The operator is not a message recipient: what you write in your reply is what they read in
    this conversation. Record a result on a task with update_task's notes; if you need their
    answer before you can continue, call ask_user.

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
    reply = {"success": True, "message_id": result.get("id")}
    if result.get("held_by_hop_budget"):
        # Recorded, so `success` stays true, but the sender must not report it delivered (F361).
        reply["held_by_hop_budget"] = True
        reply["delivery_note"] = result.get("delivery_note")
    return reply


@_tool()
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


@_tool()
def list_tasks(
    agent: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Dict[str, Any]:
    """Read the shared task ledger, optionally filtered by assignee.

    Answers `{"tasks": [...], "total": N, "has_more": bool}`. The ledger is returned oldest
    first, a page at a time — 100 by default, 1000 at most. **`has_more` true means the newest
    work is not in front of you**: ask again with `offset` set to how many you have, or narrow
    with `agent`.

    Args:
        agent: Only tasks assigned to this agent.
        limit: How many to return, 1 to 1000. Default 100.
        offset: How many to skip, for the next page. Default 0.
    """
    return _hub_request("GET", "/tasks", params={"agent": agent, "limit": limit, "offset": offset})


@_tool()
def get_task(task_id: str) -> Dict[str, Any]:
    """Read one task-ledger entry by ID."""
    return _hub_request("GET", f"/tasks/{task_id}")


@_tool()
def task_history(task_id: str) -> Dict[str, Any]:
    """Who moved this task, when, and from what status to what.

    Answers `{"transitions": [...]}`, oldest first. Each entry carries `from_status`, `to_status`,
    whether the operator or a run asked (`actor_kind`), which agent's run it was (`actor_agent`),
    whether the Hub moved it on that run's behalf (`origin: "runtime"`) or a scheduled loop or flow
    did (`origin: "job"`, with `job_id`, `job_name` and `job_kind`), and the digest of the policy
    that governed it. The task's own fields cannot answer this: they hold only the latest
    run that touched it, so "who completed this, and who approved it?" is unanswerable from them.

    Args:
        task_id: The task to read the history of.
    """
    return _hub_request("GET", f"/tasks/{task_id}/transitions")


@_tool()
def update_task(
    task_id: str,
    status: Optional[TaskStatus] = None,
    notes: Optional[str] = None,
    requirement_ids: Optional[List[str]] = None,
    spec_document: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a task's lifecycle status, notes, or the requirements it serves.

    Args:
        task_id: The task's ID.
        status: The new lifecycle status, or omit to leave the status unchanged. One of "pending",
            "assigned", "in_progress", "completed", "under_review", "revision_needed", "approved",
            "rejected".
        notes: Why, in your own words - required reading for whoever looks at this task next.
            Moving a task to "revision_needed" or "rejected" without notes leaves the author with
            only a status change and no reason; a message to another agent does not appear on the
            task record itself. Overwrites the task's existing notes, so restate anything from a
            prior round that still matters.
        requirement_ids: Requirement IDs this task serves, added to whatever it already serves.
        spec_document: Which spec document to resolve requirement_ids in, when it is ambiguous.
    """
    body: Dict[str, Any] = {}
    if status is not None:
        body["status"] = status
    if notes is not None:
        body["notes"] = notes
    if requirement_ids is not None:
        body["requirement_ids"] = requirement_ids
    if spec_document is not None:
        body["spec_document"] = spec_document
    return _hub_request("PATCH", f"/tasks/{task_id}", body)


@_tool()
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
        # Either spelling: the Hub also accepts Claude Code's `multiSelect` (F514).
        row.get("id"): bool(asked[index].get("multi_select", asked[index].get("multiSelect")))
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

    if expired:
        # Tell the Hub the wait is over, so the task it parked stops saying somebody is waiting and
        # this run can record the work it is about to do anyway.
        #
        # `expired`, not `unanswered`: a decline left the wait early and is a decision the operator
        # made and handed back, so reporting one as an expiry would mark the task as proceeded-
        # without-an-answer when an answer was in fact given.
        #
        # Failure must not raise. The agent is owed its answers whatever the Hub does with this,
        # and the whole turn dying because a report did not land would be a worse outcome than the
        # report being lost. The Hub sweeps at the run's end for exactly this case.
        try:  # noqa: SIM105 - kept explicit; contextlib.suppress hides how deliberate this is
            _hub_request(
                "POST",
                "/questions/wait-ended",
                {"question_ids": [entry["question_id"] for entry in expired]},
            )
        except Exception:  # noqa: BLE001 - the answers are owed regardless
            pass
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


@_tool()
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


@_tool()
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

    Keep it brief; a few hundred words in total is right. The Hub refuses more than: intent,
    1500 characters; suspicions and warnings, each a list of at most 8 strings of at most 400
    characters. Pass the two lists as lists, even for one entry. These notes are one input among
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


@_tool()
def list_checkpoints(agent: Optional[str] = None) -> List[Dict[str, Any]]:
    """The checkpoints you may open, newest first — yours, and any peer's you are granted.

    A checkpoint is the summary the Hub writes when a conversation is cut over: what its agent
    was doing, what it decided, what it ruled out and what it left unfinished. Reading a peer's
    before you review or continue their work is cheaper and more reliable than re-deriving it,
    and `agent` narrows the list to one of them.

    Each row carries the id `read_checkpoint` takes. An empty list means there is nothing you may
    read, which is not the same as nothing existing — access to a peer's history is a grant the
    operator confers.
    """
    query = "?" + urllib.parse.urlencode({"agent": agent}) if agent else ""
    return _hub_request("GET", f"/checkpoints{query}")


@_tool()
def read_checkpoint(checkpoint_id: str) -> Dict[str, Any]:
    """One checkpoint in full, exactly as an agent continuing that conversation receives it.

    Use `list_checkpoints` to find the id. A checkpoint you may not read answers not-found,
    whether or not it exists, so treat not-found on an id you were given as that boundary rather
    than as a missing record.
    """
    return _hub_request("GET", f"/checkpoints/{checkpoint_id}")


@_tool()
def recall(observation_id: str) -> Dict[str, Any]:
    """Retrieve one recorded observation a checkpoint cited, exactly as it was recorded.

    A checkpoint is a summary, and summaries lose detail. Where it lists ids under "Recorded
    observations", this returns the original text in full — use it instead of guessing at what a
    summary compressed away, and instead of re-running a tool to find out.

    Only observations cited by a checkpoint you are permitted to read are available. Anything
    else returns not-found, whether or not it exists.
    """
    return _hub_request("GET", f"/recall/{observation_id}")


@_tool()
def request_agent(name: str, template: str, task: str) -> Dict[str, Any]:
    """Request a new agent, modelled on an existing open agent of this project.

    `template` is that agent's exact name; the new agent takes its bound runner, charter and
    runner configuration, under the project agent budget. It inherits no grant, no permission
    posture, and no per-agent override — those stay the operator's to set on the new agent.
    """
    return _hub_request(
        "POST", "/agents/request", {"name": name, "template": template, "task": task}
    )


def _job_effect(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _hub_request(method, path, body)


@_tool()
def create_job(
    name: str,
    agent: str,
    message: str,
    cron: str,
    session_mode: JobSessionMode = "new",
) -> Dict[str, Any]:
    """Create recurring work.

    Needs the project setting `allow_agent_jobs`, which only the operator turns on. While it is
    off, this is refused at once (403) and the Hub asks the operator whether to enable it, on their
    Questions destination; the refusal names that question. It is a refusal, not a wait: do not poll
    and do not repeat the call. If they enable it, their answer reaches you as a message.

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


@_tool()
def create_loop(
    name: str,
    agent: str,
    message: str,
    cron: str = "*/5 * * * *",
    purpose: str = "",
    stop_at: Optional[str] = None,
    stop_when_queue_empties: bool = False,
    work_needs_evidence: Optional[bool] = None,
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

    Needs the project setting `allow_agent_jobs`, which only the operator turns on. While it is
    off, this is refused at once (403) and the Hub asks the operator whether to enable it, on their
    Questions destination; the refusal names that question. It is a refusal, not a wait: do not poll
    and do not repeat the call. If they enable it, their answer reaches you as a message.

    Args:
        name: Job name.
        agent: Exact name of the registered agent the loop triggers.
        message: The message delivered to that agent on each firing.
        cron: Cron expression for the schedule.
        purpose: What this loop exists to do — carried into every firing's briefing.
        stop_at: ISO-8601 timestamp after which the loop stops firing. At least one of
            stop_at or stop_when_queue_empties is required.
        stop_when_queue_empties: Stop once this loop's queue has no open task left.
        work_needs_evidence: Whether this loop's work must be demonstrated by evidence a reviewer
            accepted before approving a task writes it to the project's main branch. Leave it unset
            for the product's current default, which for a loop with no document is False: approving
            one of its tasks merges that task's own branch into the main branch. Set it True where
            the work should reach the main branch only once somebody has accepted evidence for it.
            Declared here and fixed for the loop's life — it cannot be changed afterwards.
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
            "work_needs_evidence": work_needs_evidence,
            "spec_document_id": spec_document_id,
            "initial_tasks": initial_tasks,
        },
    )


@_tool()
def create_flow(
    name: str,
    agent: str,
    message: str,
    spec_document_id: str,
    cron: str = "*/5 * * * *",
    purpose: str = "",
    stop_at: Optional[str] = None,
    stop_when_queue_empties: bool = False,
    work_needs_evidence: Optional[bool] = None,
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

    Needs the project setting `allow_agent_jobs`, which only the operator turns on. While it is
    off, this is refused at once (403) and the Hub asks the operator whether to enable it, on their
    Questions destination; the refusal names that question. It is a refusal, not a wait: do not poll
    and do not repeat the call. If they enable it, their answer reaches you as a message.

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
        work_needs_evidence: Not accepted here — a flow decomposes a document, so its requirements
            are the evidence chain and accepted evidence always decides what approval merges. Kept
            in the signature so the refusal can say that, rather than the call failing as an
            unexpected argument, which tells the caller nothing about what to do instead. Same
            reasoning as spec_document_id on create_loop.
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
    if work_needs_evidence is not None:
        raise HubAPIError(
            400,
            "a flow's work is always governed by evidence: its document's requirements are the "
            "chain, and approving one of its tasks merges the commit a reviewer accepted. Only a "
            "loop with no document declares this; call create_loop if that is what you want",
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
            "work_needs_evidence": work_needs_evidence,
            "spec_document_id": spec_document_id,
            "initial_tasks": initial_tasks,
        },
    )


@_tool()
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

    Refused before any of that if the project setting `allow_agent_jobs` is off: that refusal is
    the same as every other job tool's — the operator is asked about the setting, and this call
    does not wait for them. Only the direction request described above is waited on.

    **The rule above is the Hub's, not this tool's** (§3.2 of
    `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, 2026-09-09). This function used to
    ask the operator itself and only then call the route; the route asked nothing, so an agent on the
    HTTP access path was governed by the allowance alone. Now the route refuses with
    `operator_direction_required` and opens the request, and this waits on it — which is why the
    first call below is the archive and not a question. Do **not** reinstate an ask here: two
    independent confirmations for one archive is a worse product than none, and the second copy is
    how the rule silently diverges.
    """
    path = f"/jobs/{job_id}/archive"
    try:
        return _job_effect("POST", path)
    except HubAPIError as exc:
        request_id = exc.data.get("permission_request_id")
        if exc.data.get("code") != "operator_direction_required" or not request_id:
            # Any other refusal is this job's own — no such job, already archived, it has a loop,
            # the allowance is off. Those are answers, and re-raising is how the agent gets them.
            raise

    decision = _await_decision(str(request_id))
    if not decision["allow"]:
        raise HubAPIError(
            403,
            f"archiving this job was not approved: {decision['reason']}",
            "POST",
            path,
        )
    # The Hub decides again from the row the operator answered; this repeat is the caller doing what
    # the refusal told it to do, not a second grant.
    return _job_effect("POST", path)


@_tool()
def toggle_job(job_id: str, enabled: bool) -> Dict[str, Any]:
    """Enable or disable recurring work.

    Needs the project setting `allow_agent_jobs`, which only the operator turns on. While it is
    off, this is refused at once (403) and the Hub asks the operator whether to enable it, on their
    Questions destination; the refusal names that question. It is a refusal, not a wait: do not poll
    and do not repeat the call. If they enable it, their answer reaches you as a message.
    """
    return _job_effect("PATCH", f"/jobs/{job_id}", {"enabled": enabled})


@_tool()
def run_job(job_id: str) -> Dict[str, Any]:
    """Trigger recurring work immediately.

    Needs the project setting `allow_agent_jobs`, which only the operator turns on. While it is
    off, this is refused at once (403) and the Hub asks the operator whether to enable it, on their
    Questions destination; the refusal names that question. It is a refusal, not a wait: do not poll
    and do not repeat the call. If they enable it, their answer reaches you as a message.
    """
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

# The longest `reason` the Hub records for a decision (`PermissionDecisionCreate` in
# `api/v1/agent_actions.py`). Restated here for the same reason `OPERATOR_POSTURE` is; a test
# asserts the two agree. A longer reason is rejected by that schema, `_report_decision` swallows the
# rejection, and the refusal goes unrecorded.
MAX_REASON_CHARS = 1000


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

# --- Reading a shell command (a-url-is-not-a-path, design D1) ------------------------------------
#
# A shell command declares no path, so its text is read the way its shell will read it: lexed in
# the tool's dialect (quotes removed, what they join joined, substitutions marked), split into
# words at the characters that survive, and each word judged by the first of six rules that
# matches it. `shlex` is not used: it raises on an unbalanced quote, and every input must get an
# answer. Some quote forms (bash's `$'...'`) decode escapes into characters rather than only
# removing the quote, so the word judged is what the shell's decode actually produces
# (a-quote-can-spell-a-slash, design D1).

# `\` separates path components where the platform says so: on Windows `..\x` is a traversal, on
# POSIX it is a file name with a backslash in it. `os.path` answers the same way.
_SEPARATORS = "/\\" if os.sep == "\\" else "/"

# D9: the one platform key for a Windows-only rule -- the drive exception in D2 step 3, the device
# limit in D4, D12's physical reading below, and the sibling change's drive rules. Read at call
# time by every rule that consults it: never baked into a regex or default argument at import, so a
# test can monkeypatch it on Linux. `_SEPARATORS` and `_ABSOLUTE_PATH_RE` keep their own `os.sep`
# keys rather than this one.
_DRIVE_LETTERS = os.sep == "\\"

# Rule 6's backstop, and now its only use: a path glued to something no other rule accounts for
# (`-o/tmp/x`, `@/etc/passwd`, `host:/x`) is read out of one word at a time, the way whole commands
# once were. POSIX (/x) and Windows (C:\x, C:/x). On Windows a candidate also opens at a bare `\`,
# or a backslash traversal glued to an option (`sort -o"..\x"`) would pass unseen.
_ABSOLUTE_PATH_RE = re.compile(
    (r"(?:[A-Za-z]:[\\/]|[\\/])" if os.sep == "\\" else r"(?:[A-Za-z]:[\\/]|/)")
    + r"[^\s\"'|;&><)]*"
)

_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
# Word characters, `.`, `+`, `-` and separators, not starting with `-`, and `:` only after the
# first separator: a colon in the first segment is where a host (`host:/x`) or a revision
# (`HEAD:x`) goes, and those are left to the backstop.
# Everything `_WORD_TRIM` (below) treats as quote/bracket/pipe/control syntax, minus `:` (scoped
# separately below), plus `@` (curl's `name@filename` convention), `*`/`?` (bash glob expansion --
# `[`/`]` are already in `_WORD_TRIM`), `%` (`_CMD_VARIABLE_RE`'s own expansion syntax), and a NUL
# byte. Excluded at every position, not only leading: none of these reasons is position-specific
# (design D6).
_PLAIN_RELATIVE_EVERYWHERE = "\"'`{}[]()<>|;&@*?%\x00"
_PLAIN_RELATIVE_RE = re.compile(
    rf"^[^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}:\-]"
    rf"[^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}:]*"
    rf"(?:[{re.escape(_SEPARATORS)}][^{re.escape(_SEPARATORS)}{re.escape(_PLAIN_RELATIVE_EVERYWHERE)}]*)+$"
)
# A value an option carries in its own word (a-word-without-a-separator-can-still-leave, D7):
# joined by a colon, `-Destination:..`, `-o:..`, `--output:..` (checked for `..` in both dialects,
# and for `~` in PowerShell, whose provider cmdlets resolve it there), or a short option with its
# value glued on, `cp -t..`, `tar -xvC..` (checked for `..` only: bash does not expand a `~` there).
_COLON_OPTION_RE = re.compile(r"--?[A-Za-z_][A-Za-z0-9_-]*:")
_GLUED_OPTION_RE = re.compile(r"-[A-Za-z0-9]+")
# The home-directory shorthand in the shapes a shell substitutes for a word with no separator
# (D3): alone, with a sign, or with a user name. `~30%` and `~2x` are left alone.
_TILDE_PREFIX_RE = re.compile(r"~(?:[+-]|[A-Za-z_][A-Za-z0-9._-]*)?")
_CMD_VARIABLE_RE = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%")
_WORD_SPLIT_RE = re.compile(r"[\s=,]+")
_WORD_TRIM = "\"'`{}[]()<>|;&:"
# a-drive-or-a-home-variable-names-a-directory-by-itself, D1 (F402): a drive with no separator after
# it (`Z:`, `Z:foo`) names that drive's current directory, so `_words` keeps its colon rather than
# trimming it -- in the PowerShell reading, and in the bash reading on a drive-letter host (D4).
# `Temp:` is a drive of PowerShell's FileSystem provider only (R6, `B4-temp-dialect`).
_WORD_TRIM_KEEP_COLON = _WORD_TRIM.replace(":", "")
_PS_DRIVE_RE = re.compile(r"[A-Za-z]:[^:\\/]*")
_PS_TEMP_DRIVE_RE = re.compile(r"(?i)temp:[^:\\/]*")
_ARGUMENT_ENDS = "|;&<>()"

# D4: the null device and standard streams a bash-spawned msys maps, as a whole word only (the-
# shell-judge-reads-a-word-whole). `/dev/tcp/...`, `/dev/fd/N` and `/dev/sda` are not in this set,
# so they still fall through to being judged as paths.
_BASH_DEVICES = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr"}

# D5: a network address with no scheme, read on the whole word after rule 2 and before rule 3 (in
# both dialects), so a separator-less form (`git@github.com:repo`) is seen at all. The host in
# `_SCP_ADDRESS_RE` must be unmistakably a host (a domain, an IPv4/IPv6 literal, or `localhost`),
# so a dotless package-manager or digest form (`alpine@sha256:...`, `x@npm:y`) is left as a word.
_SCP_ADDRESS_RE = re.compile(
    r"^[A-Za-z0-9._-]+@(?:localhost|\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+):"
)
_HOST_PORT_RE = re.compile(r"^[A-Za-z0-9.-]{2,}:[0-9]+[/\\]")

# D2: rule 6's piece breaks. Each is also a name character the shell reads literally in some
# context (`@` and `'` everywhere, `(` `<>|;&` inside quotes, `:` glues a host/revision/curl
# `name@file`), so a link or traversal before one of these was never resolved by the old backstop.
# `)` is deliberately not a break (it would refuse every regex back-reference, `s/(foo)/\1/`).
_PIECE_BREAKS_RE = re.compile(r"[<>|;&(@:\s'\"`]+")
# The same breaks, captured, so a split keeps each run of break characters in the result -- D4's
# "a piece that directly follows a `<` or `>` break" (the device exemption) reads the delimiter
# just before a piece, which plain `.split()` throws away.
_PIECE_BREAKS_SPLIT_RE = re.compile(f"({_PIECE_BREAKS_RE.pattern})")
_PIECE_QUOTES = "'\"`"
# D2 step 3's drive exception (R2, R3, D9): on a drive-letter host, a `:` directly after a single
# ASCII letter that begins the value or a piece -- i.e. immediately preceded by a break or the
# start of the value -- is not a break. The alternation's break-char branch reuses
# `_PIECE_BREAKS_RE`'s own class so the two stay in agreement about what a break is.
_DRIVE_COLON_RE = re.compile(rf"(?:\A|{_PIECE_BREAKS_RE.pattern[:-1]})[A-Za-z]:")
# Distinct code point from `_EXTGLOB_*`/`_BRACKET_COLON_SENTINEL` above.
_DRIVE_COLON_SENTINEL = ""
# D2 step 5's second clause: tells `_judge_piece` whether a piece that survived the drive
# exception above IS such a drive piece, so it can check the text after the colon for a leading
# `~` (bash expands a tilde after `:` in an assignment-shaped argument: `echo of=c:~/y`).
_DRIVE_PIECE_RE = re.compile(r"\A[A-Za-z]:")

# A reference to the run's own Hub, in the spelling the tool's shell expands to the environment's
# value. Bash's variables are case-sensitive and PowerShell's are not, and a bare `$HUB_URL` in
# PowerShell is a shell variable that expands to nothing. `%HUB_URL%` is a reference in neither.
_HUB_REFERENCE_RE = {
    "bash": re.compile(r"^(?:\$HUB_URL(?![A-Za-z0-9_])|\$\{HUB_URL\})"),
    "powershell": re.compile(r"^(?i:\$env:HUB_URL)(?![A-Za-z0-9_])"),
}
# The dialect a tool's `command` is lexed in. Any other tool is read both ways, and refused if
# either reading refuses.
_TOOL_DIALECTS = {"Bash": ("bash",), "PowerShell": ("powershell",)}
_DEFAULT_PORTS = {"http": 80, "https": 443}

# What a lexed argument holds where the shell substitutes a command's output when it runs, and in
# place of a `$` the shell will not expand because it is quoted or escaped. The second keeps a
# literal `'$HUB_URL'/../../x` from being read as a reference, which would judge a longer path
# than the one the shell writes to. It still counts as an expansion for rule 3, and a refusal
# renders it back as `$`.
_SUBSTITUTION = "$(…)"
_LITERAL_DOLLAR = "\ue024"
_MAX_NESTING = 8

# D2 (F401): a bare reference to a variable the shell, the host or the platform sets for every
# process, whose value is one directory (one file for `PROFILE`, one drive for `HOMEDRIVE` and
# `SystemDrive`), is uncheckable by itself. Matched at the start of rule 4's `value` and directly
# after each `:` in it (R4: Git Bash expands `of=c:$HOMEPATH`). `\{?` reaches the brace form
# (`_words` trims the closing `}`, so `${HOME}` arrives as `${HOME`), and the lookahead -- "not
# followed by a name character" -- is what leaves `$HOMEDIR` alone while still refusing `$HOME.bak`
# and `$PWD..`, siblings of home and of the workspace (R2). `_LITERAL_DOLLAR` matches too (R4): a
# quoted reference is exactly what an inner shell expands. Tool-specific and user variables
# (`VIRTUAL_ENV`, `$tmp`) are the named residual, not judged.
_DIRECTORY_VARIABLE_NAMES = (
    "HOME",
    "USERPROFILE",
    "HOMEPATH",
    "HOMEDRIVE",
    "SystemDrive",
    "PWD",
    "OLDPWD",
    "TMPDIR",
    "TMP",
    "TEMP",
    "APPDATA",
    "LOCALAPPDATA",
    "PUBLIC",
    "OneDrive",
    "OneDriveConsumer",
    "OneDriveCommercial",
    "ProgramData",
    "ALLUSERSPROFILE",
    "SystemRoot",
    "windir",
    "ProgramFiles",
    "ProgramW6432",
    "CommonProgramFiles",
    "CommonProgramW6432",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR",
    "PSHOME",
    "PROFILE",
)
# PowerShell's own automatic variables; any other bare `$NAME` there is the script's, not the
# environment's (R6: `$TEMP` is empty in PowerShell 5.1), so it needs `env:`.
_POWERSHELL_DIRECTORY_VARIABLES = ("HOME", "PWD", "PSHOME", "PROFILE")
_ANY_DIRECTORY_VARIABLE = "|".join(sorted(_DIRECTORY_VARIABLE_NAMES, key=len, reverse=True))
_DIRECTORY_VARIABLE_RE = {
    # A POSIX name exactly; a Windows name as Windows spells it or in capitals, the two forms msys
    # keeps (`OneDrive`, `PROGRAMFILES`), so a lowercase user `$tmp` is not matched. (R6) Also
    # PowerShell's `env:` spelling, handed to a nested PowerShell, in any case.
    "bash": re.compile(
        "[$"
        + _LITERAL_DOLLAR
        + "]\\{?(?:(?i:env:(?:"
        + _ANY_DIRECTORY_VARIABLE
        + "))|"
        + "|".join(
            sorted(
                {
                    spelling
                    for name in _DIRECTORY_VARIABLE_NAMES
                    for spelling in (name, name.upper())
                },
                key=len,
                reverse=True,
            )
        )
        + ")(?![A-Za-z0-9_])"
    ),
    "powershell": re.compile(
        "(?i)[$"
        + _LITERAL_DOLLAR
        + "]\\{?(?:env:(?:"
        + _ANY_DIRECTORY_VARIABLE
        + ")|(?:(?:variable|global|local|script|private|using):)?(?:"
        + "|".join(_POWERSHELL_DIRECTORY_VARIABLES)
        + "))(?![A-Za-z0-9_])"
    ),
}
# The `%NAME%` form (a nested `cmd`) is read in either dialect and any case, the same way rule 3's
# `_expands` already treats it as an expansion regardless of dialect; cmd adds `%CD%`.
_CMD_DIRECTORY_VARIABLE_NAMES = {name.upper() for name in _DIRECTORY_VARIABLE_NAMES} | {"CD"}
# D3 (R4): what one expansion spells, removed to see whether the rest still names the parent: the
# substitution marker, `$NAME`, `${...}` (its closing `}` optional, since `_words` trims it), `$`
# and a special parameter, an inner shell's backtick span, and `%NAME%` -- each with a literal `$`
# too, since an inner shell expands that.
_EXPANSION_RE = re.compile(
    re.escape(_SUBSTITUTION)
    + "|[$"
    + _LITERAL_DOLLAR
    + "](?:\\{[^}]*\\}?|[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])|`[^`]*`?|%[A-Za-z_][A-Za-z0-9_]*%"
)

# D1: an unquoted, unescaped `{`, `,` and `}` in bash, marked so `_expand_braces` can tell one
# from a literal character the lexer already rendered plain (a quoted or escaped one, or one
# inside a `${...}` parameter expansion). Never produced for the PowerShell dialect: `{...}` is a
# script block there and `,` an array operator (design D1).
_BRACE_OPEN = "\ue025"
_BRACE_COMMA = "\ue026"
_BRACE_CLOSE = "\ue027"
_BRACE_SENTINELS = {"{": _BRACE_OPEN, ",": _BRACE_COMMA, "}": _BRACE_CLOSE}
_BRACE_RESTORE = {_BRACE_OPEN: "{", _BRACE_COMMA: ",", _BRACE_CLOSE: "}"}
# Past this many nested groups, or this many alternatives from one argument, `_expand_braces`
# returns None rather than build further (design D1, "The bounds"). `_BRACE_ARGUMENT_BUDGET` is
# per argument; `_BRACE_TOTAL_BUDGET` is spent across the whole `_decide` call by `_Budget` below,
# which also caps a single call at the argument bound.
_BRACE_MAX_NESTING = 32
_BRACE_ARGUMENT_BUDGET = 256
_BRACE_TOTAL_BUDGET = 1024
# Design "The bounds": directory entries examined by `_glob_links`, across the whole `_decide`
# call, charged on `budget` as each is read from `os.scandir` -- not after the listing is built,
# so an unbounded directory cannot be materialized into memory before the bound is checked.
_GLOB_ENTRY_BUDGET = 8192
# `_Budget.list_directory`'s own sentinel for "this directory went past `_GLOB_ENTRY_BUDGET` while
# being listed" -- distinct from `None` ("cannot be listed"), and never memoized (design "The
# bounds" only promises the memo serves a *listing*; a scan that never finished one is not a
# listing to reuse, and the budget it already spent keeps every later call over the bound anyway).
_LISTING_TOO_MANY = object()
_BRACE_INT_SEQUENCE_RE = re.compile(r"^([+-]?[0-9]+)\.\.([+-]?[0-9]+)$")
_BRACE_LETTER_SEQUENCE_RE = re.compile(r"^([A-Za-z])\.\.([A-Za-z])$")
_BRACE_MAX_LETTER_SPAN = 58
_TOO_MANY = (
    "expands to more words or files than can be checked against your workspace; name the files "
    "you mean, or write the payload to a file"
)


def _restore_brace_sentinels(text: str) -> str:
    """A brace sentinel rendered back to the literal character it came from, for a refusal that
    quotes an argument `_expand_braces` never finished (design D1)."""
    for sentinel, literal in _BRACE_RESTORE.items():
        text = text.replace(sentinel, literal)
    return text


# A refusal quotes at most this many characters, as rendered. `repr` expands what it cannot print
# (a NUL becomes four characters, some code points ten), so bounding the word before rendering
# would not bound the reason. The longest fixed wording is under 200 characters, so every reason
# stays well under `MAX_REASON_CHARS`.
_QUOTATION_MAX = 200

_OUTSIDE = "is outside your workspace"
_UNRESOLVED = "could not be resolved"
_NETWORK = (
    "is a network address. Under this posture a shell command may name only this run's own Hub "
    "($HUB_URL); if the task needs another address, ask the operator with ask_user"
)
_UNCHECKED = (
    "contains a variable, '~' or a command substitution that the shell expands when it runs, so "
    "where it points cannot be checked against your workspace; write a path relative to your "
    "workspace instead"
)


def _quote(text: str) -> str:
    """`text` as a refusal quotes it: rendered by `repr`, then cut to `_QUOTATION_MAX`."""
    shown = repr(text.replace(_LITERAL_DOLLAR, "$"))
    return shown if len(shown) <= _QUOTATION_MAX else shown[: _QUOTATION_MAX - 1] + "…"


def _refuse(text: str, why: str) -> Dict[str, Any]:
    return {"allow": False, "reason": f"{_quote(text)} {why}"}


# D12: `ntpath.realpath` normalises a `..` lexically, before it reads any link, so a `..` right
# after a link escapes `_where`'s one reading on a drive-letter host (measured: Git Bash and
# PowerShell both resolve it physically, from where the link really points). `_physical` makes at
# most one `os.path.realpath` call per `..` that follows a name; a path needing more is answered
# `_UNRESOLVED`, which refuses. No real path comes near it.
_PHYSICAL_MAX_STEPS = 64


def _physical(absolute: str) -> str:
    """D12: walk `absolute`'s components, resolving the current path (reading any link) before a
    `..` leaves a name that was appended since the last resolution, then moving to its parent.

    On POSIX this is `os.path.realpath` itself -- it already resolves `..` this way -- so `_where`
    calls this only on a drive-letter host (`_DRIVE_LETTERS`, read at call time).
    """
    drive, rest = os.path.splitdrive(absolute)
    anchor = drive + os.sep
    current = anchor
    appended = False
    steps = 0
    for component in re.split(f"[{re.escape(_SEPARATORS)}]", rest):
        if component in ("", "."):
            continue
        if component == "..":
            if appended:
                steps += 1
                if steps > _PHYSICAL_MAX_STEPS:
                    raise ValueError("too many '..' components to resolve physically")
                current = os.path.realpath(current)
                appended = False
            if current != anchor:
                current = os.path.dirname(current)
        else:
            current = os.path.join(current, component)
            appended = True
    return os.path.realpath(current)


def _judge_resolved(absolute: str, resolved: str, root: str) -> Optional[str]:
    """Why `resolved` -- a lexical or (D12) physical reading of `absolute` -- lands outside `root`,
    or None when it is inside."""
    # `commonpath` compares path components, so it cannot be fooled the way a string prefix
    # can (`/work-other` does not start inside `/work`). Both sides are already real paths,
    # so `..` and symlinks have been collapsed before this comparison.
    try:
        shared = os.path.commonpath([root, resolved])
    except ValueError:  # different drives on Windows
        return _resolves_elsewhere(absolute, resolved)
    if os.path.normcase(shared) != os.path.normcase(root):
        return _resolves_elsewhere(absolute, resolved)
    return None


def _where(path: str, root: str) -> Optional[str]:
    """Why `path` is not inside the workspace, or None when it is.

    A relative path is joined to the workspace root, which is where the run started. Total: a path
    the platform cannot resolve (on POSIX, a NUL byte raises `ValueError`) is refused, not raised.

    (D12) On a drive-letter host, a path holding a `..` after a name is also read physically
    (`_physical`): a refusal of either reading refuses, because the judge cannot tell whether the
    word reaches a native program (which resolves `..` lexically) or msys (which resolves it
    physically, the way `_physical` does).
    """
    absolute = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        resolved = os.path.realpath(absolute)
        physical = None
        if _DRIVE_LETTERS and ".." in re.split(f"[{re.escape(_SEPARATORS)}]", absolute):
            physical = _physical(absolute)
    except (OSError, ValueError):
        return _UNRESOLVED
    why = _judge_resolved(absolute, resolved, root)
    if why:
        return why
    if physical is not None:
        return _judge_resolved(absolute, physical, root)
    return None


def _resolves_elsewhere(absolute: str, resolved: str) -> str:
    """`_OUTSIDE`, plus where the path really lands when a link moved it (F282).

    A path reached through a link or junction reads as inside the workspace as written, and the
    refusal quoting only that left the verdict beside it unexplained. The declared path is still
    what the refusal quotes first; this adds the resolved one only when the two differ.
    """
    if os.path.normcase(os.path.abspath(absolute)) == os.path.normcase(resolved):
        return _OUTSIDE
    return f"{_OUTSIDE}: it resolves to {_quote(resolved)}"


# D3: `a-url-is-not-a-path` kept `*`/`?`/`[` out of rule 5 because bash's `.*` can match `..`
# (`globskipdots` is on in Git Bash 5.2.37 but off in bash before 5.2). A component is rewritten to
# `..` only when `fnmatch.fnmatchcase("..", component)` proves it can expand that way -- `*` and
# `?*` alone never match a dot-leading name, so `sub/..?/y` (a third character after the dot) is
# left alone.
_GLOB_CHARS = "*?["
_SEPARATOR_RE = re.compile(f"([{re.escape(_SEPARATORS)}])")

# D8 step 2, step 4 (R5): whether the command names the `globstar` shell option, read once per
# `_decide` from the whole command text (design: "so that the memo below cannot hold a result from
# a nested text read under different flags") -- not re-derived for a nested substitution's own text.
_GLOBSTAR_RE = re.compile(r"\bglobstar\b")

# D14: whether the command names the `dotglob` shell option, read the same way and for the same
# reason as `_GLOBSTAR_RE` above -- a nested substitution's own `shopt -s dotglob` is still a
# substring of the whole top-level command text, so the one regex search finds it there too.
_DOTGLOB_RE = re.compile(r"\bdotglob\b")

# D3, extglob: one of `@ ? * + !` directly followed by `(`, up to its matching `)`, with nesting
# counted -- an unbalanced `(` is not a group. `(`, `|` and `@` inside a group are glob syntax, not
# piece breaks or curl `name@file` glue, so D2 step 2 must not split there, and the group's
# alternatives feed D3's own `..`-capable test rather than being read as literal text.
_EXTGLOB_TRIGGERS = "@?*+!"
# Sentinels for the three break characters a group can itself contain (`)` is never a break, so it
# needs none). Distinct code points from `_BRACE_*`/`_LITERAL_DOLLAR` above, restored before a
# piece is judged or quoted.
_EXTGLOB_PAREN = ""
_EXTGLOB_AT = ""
_EXTGLOB_PIPE = ""
_EXTGLOB_SENTINELS = {"(": _EXTGLOB_PAREN, "@": _EXTGLOB_AT, "|": _EXTGLOB_PIPE}
_EXTGLOB_RESTORE = {sentinel: literal for literal, sentinel in _EXTGLOB_SENTINELS.items()}


def _extglob_span_at(text: str, index: int) -> Optional[int]:
    """`text[index]` is a trigger directly followed by `(` (checked by the caller): the position
    just past its matching `)`, with nesting counted, or None when the `(` never balances -- an
    unbalanced one is not a group (design D3)."""
    depth = 1
    scan = index + 2
    length = len(text)
    while scan < length and depth:
        if text[scan] == "(":
            depth += 1
        elif text[scan] == ")":
            depth -= 1
        scan += 1
    return scan if depth == 0 else None


def _extglob_group_spans(text: str) -> List[Tuple[int, int]]:
    """D3: the `(start, end)` span of each extglob group in `text`, `end` just past its matching
    `)`. A trigger whose `(` never balances is not a group, and scanning resumes one character
    later, as design D3 says."""
    spans = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] in _EXTGLOB_TRIGGERS and index + 1 < length and text[index + 1] == "(":
            end = _extglob_span_at(text, index)
            if end is not None:
                spans.append((index, end))
                index = end
                continue
        index += 1
    return spans


def _mask_extglob_groups(value: str) -> str:
    """D2 step 2: within each of `value`'s extglob groups (D3), `(`, `@` and `|` are replaced by
    sentinels so `_PIECE_BREAKS_RE` does not split there. `_restore_extglob_sentinels` undoes this
    once a piece is carved out."""
    spans = _extglob_group_spans(value)
    if not spans:
        return value
    chars = list(value)
    for start, end in spans:
        for position in range(start, end):
            sentinel = _EXTGLOB_SENTINELS.get(chars[position])
            if sentinel:
                chars[position] = sentinel
    return "".join(chars)


def _restore_extglob_sentinels(text: str) -> str:
    """The literal characters `_mask_extglob_groups` sentinel-marked, rendered back before a piece
    is judged or quoted in a refusal."""
    for sentinel, literal in _EXTGLOB_RESTORE.items():
        text = text.replace(sentinel, literal)
    return text


def _extglob_alternative_begins_with_dot(component: str, spans: List[Tuple[int, int]]) -> bool:
    """(D3, extglob) Any `|`-separated alternative of any group in `component` begins with `.` --
    nesting-aware, so a group inside another group's alternatives is read correctly."""
    for start, end in spans:
        inner = component[start + 2 : end - 1]
        alternative: List[str] = []
        depth = 0
        for char in inner:
            if char == "(":
                depth += 1
                alternative.append(char)
            elif char == ")":
                depth -= 1
                alternative.append(char)
            elif char == "|" and depth == 0:
                if "".join(alternative).startswith("."):
                    return True
                alternative = []
            else:
                alternative.append(char)
        if "".join(alternative).startswith("."):
            return True
    return False


def _mask_extglob_as_star(component: str, spans: List[Tuple[int, int]]) -> str:
    """Each extglob group in `component` replaced by one `*`, as D3's fallback test reads it."""
    masked = component
    for start, end in sorted(spans, reverse=True):
        masked = masked[:start] + "*" + masked[end:]
    return masked


def _holds_glob_character(text: str) -> bool:
    """Whether `text` is glob-holding for D8's purposes (R4): a bare `_GLOB_CHARS` character, or an
    extglob group (D3) -- `@(u)p` has none of `* ? [` of its own, so without this check `_glob_links`
    was never even reached for one, regardless of what it could do once there."""
    return any(char in text for char in _GLOB_CHARS) or bool(_extglob_group_spans(text))


def _rewrite_dotdot_globs(path: str) -> str:
    """Each component of `path` that some real bash could still expand to `..` (D3), rewritten to
    `..` before `_judge_path` resolves it. The refusal this feeds still quotes the word as written,
    not this rewritten value.

    (R6, D11) A component is also accepted when it opens with `[` rather than `.`: Git Bash 5.2.37
    measured does not match a leading dot that way (`globskipdots` off), but an older bash was not
    available to check, so this over-approximates rather than depend on it.

    (R4, extglob) A component holding an extglob group is `..`-capable when any `|`-separated
    alternative of a group in it begins with `.`, or when the component -- each group read as one
    `*` -- passes the test above (measured: `@(..)/x`, `?(..)/x` and `@(.|..)/x` all expand to
    `../x` in Git Bash 5.2.37 with `globskipdots` off).
    """
    components = _SEPARATOR_RE.split(path)
    for index, component in enumerate(components):
        spans = _extglob_group_spans(component)
        if spans and _extglob_alternative_begins_with_dot(component, spans):
            components[index] = ".."
            continue
        candidate = _mask_extglob_as_star(component, spans) if spans else component
        if (
            (candidate.startswith(".") or candidate.startswith("["))
            and any(char in candidate for char in _GLOB_CHARS)
            and fnmatch.fnmatchcase("..", candidate)
        ):
            components[index] = ".."
    return "".join(components)


def _judge_path(
    path: str, root: str, shown: str, argument: str, continues: bool
) -> Optional[Dict[str, Any]]:
    """Refuse `path` if it lands outside the workspace, quoting `shown`.

    A word its argument carries on past is also judged with its last name extended: `../ws` in
    `../ws=y/z` is the workspace, but the shell's path is `../ws=y/z`, a sibling of it. A refusal
    only the extension finds quotes the whole argument, because that is the path the shell uses.
    """
    why = _where(path, root)
    if why:
        return _refuse(shown, why)
    if continues:
        why = _where(path + "_", root)
        if why:
            return _refuse(argument, why)
    return None


def _is_link_entry(entry: "os.DirEntry[str]") -> bool:
    """Whether `entry` (from an `os.scandir` listing) is a link (D8 step 3). `is_symlink()` is
    False for a Windows junction on Python 3.11 (measured), so a reparse point served from the
    same listing is also read, on a drive-letter host only -- `st_file_attributes` does not exist
    on a POSIX `stat_result`."""
    try:
        if entry.is_symlink():
            return True
        if _DRIVE_LETTERS:
            attributes = entry.stat(follow_symlinks=False).st_file_attributes
            return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, ValueError):
        pass
    return False


def _is_link_path(path: str) -> bool:
    """Whether `path` is a link, read without following it (D8 step 4, R7): a literal (non-glob)
    component matched during the walk has no `DirEntry`, so the test is made on `os.lstat`
    directly -- the same two cases `_is_link_entry` reads from a listing. An `OSError` or
    `ValueError` (the name does not exist, or its directory cannot be searched) means "not a
    link", as the design's error table says, not a raise."""
    try:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            return True
        if _DRIVE_LETTERS:
            return bool(info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, ValueError):
        pass
    return False


_BRACKET_CLASS_OPENERS = {":": ":]", "=": "=]", ".": ".]"}


def _bracket_expression_end(pattern: str, start: int) -> Optional[int]:
    """The index of the `]` that closes the bracket expression opening at `pattern[start]` (D8
    step 2, "found as bash finds it"): past an optional leading `!` or `^` and a `]` directly
    after that, to the `]` that closes it, where a `[:`, `[=` or `[.` inside opens a POSIX class
    that runs to its own `:]`, `=]` or `.]` rather than closing the expression. None when
    `pattern[start]` is a `[` with no closing `]` -- bash and `fnmatch` both then read it as a
    literal character.
    """
    length = len(pattern)
    index = start + 1
    if index < length and pattern[index] in "!^":
        index += 1
    if index < length and pattern[index] == "]":
        index += 1
    while index < length:
        char = pattern[index]
        if char == "[" and index + 1 < length and pattern[index + 1] in _BRACKET_CLASS_OPENERS:
            closer = _BRACKET_CLASS_OPENERS[pattern[index + 1]]
            end = pattern.find(closer, index + 2)
            if end == -1:
                index += 1
                continue
            index = end + 2
            continue
        if char == "]":
            return index
        index += 1
    return None


def _relax_bracket_pattern(pattern: str) -> str:
    """`pattern` with each bracket expression (D8 step 2) relaxed to `?` where `fnmatch` cannot
    read it as the shell does -- it opens with `!` or `^`, or holds a `[`, a `\\` or a backtick --
    and kept as written otherwise, for `fnmatch` to match exactly. A `[` with no closing `]`, and
    every character outside a bracket expression (including `*` and `?`), passes through
    unchanged.
    """
    pieces = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "[":
            end = _bracket_expression_end(pattern, index)
            if end is not None:
                content = pattern[index + 1 : end]
                if content[:1] in "!^" or any(mark in content for mark in "[\\`"):
                    pieces.append("?")
                else:
                    pieces.append(pattern[index : end + 1])
                index = end + 1
                continue
        pieces.append(char)
        index += 1
    return "".join(pieces)


# D13: a sentinel for a bracket expression's own `:`, masked before `_judge_whole_value`'s
# drive-letter colon split so the split does not divide a POSIX class or any other bracket
# expression holding a literal `:`. Distinct code point from `_EXTGLOB_*` above.
_BRACKET_COLON_SENTINEL = ""


def _bracket_expression_spans(text: str) -> List[Tuple[int, int]]:
    """D13: every `(start, end)` span (end exclusive) of a bracket expression in `text`, found the
    same way `_relax_bracket_pattern` finds one (`_bracket_expression_end`), so the two stay in
    agreement about what counts as a bracket. A `[` with no closing `]` yields no span, left
    untouched, the same literal reading `_relax_bracket_pattern` and `fnmatch` already give it."""
    spans = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "[":
            end = _bracket_expression_end(text, index)
            if end is not None:
                spans.append((index, end + 1))
                index = end + 1
                continue
        index += 1
    return spans


def _mask_bracket_colons(value: str) -> str:
    """D13: within each of `value`'s bracket expressions, `:` is replaced by
    `_BRACKET_COLON_SENTINEL` so `_judge_whole_value`'s drive-letter colon split does not divide a
    bracket expression that holds its own `:` (a POSIX class, or an ordinary bracket with a
    literal `:` member). Outside every span, `value` is untouched. The sentinel is restored back
    to `:` in each surviving split segment before it reaches `_judge_piece`, so the text any
    refusal quotes is exactly the substring of `value` as written."""
    spans = _bracket_expression_spans(value)
    if not spans:
        return value
    chars = list(value)
    for start, end in spans:
        for position in range(start, end):
            if chars[position] == ":":
                chars[position] = _BRACKET_COLON_SENTINEL
    return "".join(chars)


def _mask_drive_colons(value: str) -> str:
    """D2 step 3's drive exception (R2, R3): on a drive-letter host (`_DRIVE_LETTERS`, D9, read at
    call time, not baked in at import), the `:` right after a single ASCII letter that begins
    `value` or a piece is replaced by `_DRIVE_COLON_SENTINEL` so `_PIECE_BREAKS_RE` does not split
    there -- `Z:foo\\bar` and `-Destination:Z:foo\\bar` each keep `Z:foo\\bar` as one piece, which
    `_where` then resolves on drive `Z` (outside). On a POSIX host `value` is returned unchanged:
    `:` is an ordinary name character there, not a break the drive exception needs to protect.
    `_DRIVE_COLON_RE`'s match already ends right after the colon (the drive letter is the single
    character the alternation's break-or-start branch requires before it), so replacing the match's
    last character is exactly the colon."""
    if not _DRIVE_LETTERS:
        return value
    return _DRIVE_COLON_RE.sub(lambda match: match.group(0)[:-1] + _DRIVE_COLON_SENTINEL, value)


def _glob_links(
    piece: str, shown: str, root: str, budget: "_Budget", bash: bool
) -> Optional[Dict[str, Any]]:
    """D8, a further slice: a `piece` (already rewritten by `_rewrite_dotdot_globs`) holding
    exactly one glob-holding component, anywhere in the piece, with every other component literal
    (no glob character, no `..`). The leading literal components -- the base -- are listed once
    with `os.scandir`, resolved first by `_physical` (D12) so a link in the base is followed; each
    entry matching the glob component's *relaxed* pattern (D8 step 2, `_relax_bracket_pattern`)
    under `fnmatch.fnmatchcase` (`os.path.normcase` of both sides) that is itself a link is judged
    by `_judge_path`, quoting `shown` (the word as written).

    **(D8 step 4) The literal components after the glob are then walked, one at a time**, without
    listing them (they hold no glob character to match): the branch moves to `<real>/<component>`
    and, when that is itself a link -- read by `os.lstat`, `_is_link_path`, since there is no
    `DirEntry` for a literal component -- the link is judged by `_judge_path` exactly as a matched
    entry is, then followed to its `os.path.realpath` so the walk continues from where it really
    is. A matched glob entry that is itself a link is followed the same way before its own tail is
    walked. A non-link directory is not re-resolved: it is real already, because a child of a real
    directory that is not a link is itself real (design, "Why only links are resolved").

    **(R6, R7) A tail component that is `..` moves the branch to its real parent and is judged
    there**, with the refusal (if any) naming where it lands through `_resolves_elsewhere`, even
    when the branch's own text would read as inside. This needs two paths per branch, not one: the
    **real** path (`real`, resolved through every link already followed) and the **listed** one
    (`listed`, built the same way but never resolved -- the base as written, D2, D8 step 1, R8),
    joined with the matched entry's name or each literal tail component in turn, exactly as the
    shell would spell it. The two coincide until a link is followed; after that, a `..` must be
    judged with `_judge_resolved(listed, real, root)` directly (not through `_judge_path`/`_where`,
    which would resolve `real` again and find it unchanged, naming nothing) so the refusal can say
    where the piece as spelled actually lands. `..` costs one confirming `os.path.realpath` on the
    already-real parent (D12's own wording: "one `realpath`, which returns it unchanged") rather
    than a filesystem read; a raise from it ends the branch like any other followed link's raise
    would. A `..` in the *base* (before the glob) needs none of this: `_physical` (step 1) already
    reads it physically, since that is what `_physical` is for.

    None when nothing refuses, including when the base cannot be listed (the shell cannot list it
    either, and the literal reading -- already judged by the caller -- stands alone), or when a
    step in the tail does not exist or cannot be read (`_is_link_path`/`os.path.realpath` then read
    as "not a link" or "end this branch", per design "What each changed route returns": a name that
    does not exist still moves the branch, and a raise from a followed link's `realpath` ends that
    branch rather than refusing or raising).

    **("The bounds") Each entry read from the listing is charged against `budget` as it is read**,
    not after the listing is built, and past `_GLOB_ENTRY_BUDGET` the call is refused with
    `_TOO_MANY`, quoting `shown` -- the same shared budget `_expand_braces` spends, so a directory
    larger than the bound cannot be materialized into memory first and counted after. The literal
    tail walk lists nothing, so it adds no further charge.

    **(D8 step 2, step 4; R5) A component that is exactly `**`, when `budget.globstar_named` says
    the command names `globstar`, is walked recursively** by `_globstar_walk` rather than matched
    as one `fnmatch` component: it stands for zero or more directory levels, so the tail is first
    tried straight from the base (the zero-levels reading), then `_globstar_walk` lists the base
    and, for every entry found at any depth, tries the tail from there too. **A `**` walk does not
    descend through a link**: a matched entry that is itself a link is judged (as any matched link
    is) and the tail is tried from where it resolves, but the walk does not then list the link's
    own target for further `**` matches -- without this, a link whose target reaches it again
    (`loop` -> the workspace itself) would recurse without end, since a real directory tree with no
    link in it cannot cycle back to an ancestor. When `budget.globstar_named` is false, or the
    component is `**` beside other characters (`a**b`), `**` is read as `*` (fnmatch does not
    tell the two apart), one level, as it already was before this was built.

    A piece holding more than one glob-holding component is left to a further slice of this same
    task -- this returns None for those rather than guess. An extglob group (D3) in the one
    glob-holding component is masked to `*` before matching (`_mask_extglob_as_star`, design D8
    step 2's own words, "each extglob group becomes `*`"): `fnmatch` cannot express the shell's own
    alternation, so this is wider than the shell's real expansion for `@(...)`/`?(...)` (an
    enumerable, narrower translation is possible but not what the design asks for) -- an accepted
    over-approximation (design, "Over-approximation, on purpose", which names extglob groups
    directly): it can only add a refusal, never miss one that the shell's own expansion would catch.

    **(D14) In the bash dialect, when the command does not name `dotglob`, an entry whose name
    begins with `.` is skipped unless the matched component itself can account for it**: the
    component (as written, before `_relax_bracket_pattern`/`_mask_extglob_as_star`) begins with `.`
    or `[` -- the same over-approximating hedge `_rewrite_dotdot_globs` already uses for its own,
    adjacent question (R6, D11) -- or the component holds an extglob group with a `|`-separated
    alternative that itself begins with `.` (`_extglob_alternative_begins_with_dot`), since real
    bash's own expansion there can still reach a dot-leading name. `bash` is false for every other
    dialect, which has no such rule. **("The bounds", R5) The directory listing itself is memoized
    on `budget`, keyed by the resolved directory** (`_Budget.list_directory`): a directory already
    listed for one word's glob, or by a deeper `**` level, is served from the memo for a different
    word's, charging nothing further, rather than listed again.
    """
    drive, rest = os.path.splitdrive(piece)
    anchor = drive + os.sep
    components = [
        component
        for component in re.split(f"[{re.escape(_SEPARATORS)}]", rest)
        if component and component != "."
    ]
    if not components:
        return None
    glob_positions = [
        index for index, component in enumerate(components) if _holds_glob_character(component)
    ]
    if len(glob_positions) != 1:
        return None
    glob_index = glob_positions[0]
    pattern = components[glob_index]
    tail = components[glob_index + 1 :]
    base_components = components[:glob_index]
    listed_base = os.path.join(anchor, *base_components) if base_components else anchor
    try:
        base = _physical(listed_base)
    except (OSError, ValueError):
        return None
    if pattern == "**" and budget.globstar_named:
        refusal = _glob_tail_walk(tail, base, listed_base, root, shown)
        if refusal:
            return refusal
        return _globstar_walk(base, listed_base, tail, root, shown, budget, bash)
    pattern_spans = _extglob_group_spans(pattern)
    normalized_pattern = os.path.normcase(
        _relax_bracket_pattern(_mask_extglob_as_star(pattern, pattern_spans))
    )
    dot_exempt = pattern.startswith((".", "[")) or (
        bool(pattern_spans) and _extglob_alternative_begins_with_dot(pattern, pattern_spans)
    )
    entries = budget.list_directory(base)
    if entries is _LISTING_TOO_MANY:
        return _refuse(shown, _TOO_MANY)
    if entries is None:
        return None
    for entry in entries:
        if bash and not budget.dotglob_named and entry.name.startswith(".") and not dot_exempt:
            continue
        if not fnmatch.fnmatchcase(os.path.normcase(entry.name), normalized_pattern):
            continue
        real = entry.path
        listed = os.path.join(listed_base, entry.name)
        if _is_link_entry(entry):
            refusal = _judge_path(real, root, shown, shown, False)
            if refusal:
                return refusal
            if not tail:
                continue
            try:
                real = os.path.realpath(real)
            except (OSError, ValueError):
                continue
        elif not tail:
            continue
        refusal = _glob_tail_walk(tail, real, listed, root, shown)
        if refusal:
            return refusal
    return None


def _glob_tail_walk(
    tail: List[str], real: str, listed: str, root: str, shown: str
) -> Optional[Dict[str, Any]]:
    """D8 step 4: walk the literal components after a matched (or globstar-skipped) glob
    component, one at a time, from `real`/`listed` (R7's two paths for the same branch, kept in
    step by the caller). Shared by the single-component match loop above and by each candidate
    `_globstar_walk` finds, so both read the design's one rule the same way. None ends the branch
    without a refusal -- a raise from a followed link's `realpath`, or from `..`'s, does the same,
    per design "What each changed route returns"."""
    for component in tail:
        listed = os.path.join(listed, component)
        if component == "..":
            try:
                real = os.path.realpath(os.path.dirname(real))
            except (OSError, ValueError):
                return None
            why = _judge_resolved(listed, real, root)
            if why:
                return _refuse(shown, why)
            continue
        real = os.path.join(real, component)
        if not _is_link_path(real):
            continue
        refusal = _judge_path(real, root, shown, shown, False)
        if refusal:
            return refusal
        try:
            real = os.path.realpath(real)
        except (OSError, ValueError):
            return None
    return None


def _globstar_walk(
    directory: str,
    listed_directory: str,
    tail: List[str],
    root: str,
    shown: str,
    budget: "_Budget",
    bash: bool,
) -> Optional[Dict[str, Any]]:
    """(D8 step 2, step 4; R5) `**` under `globstar`: every entry of `directory`, at any depth, is
    a candidate the tail is tried from -- the zero-levels reading (the tail tried straight from
    `directory` itself) is the caller's job, not this one's. A matched entry that is a link is
    judged, exactly as the single-component loop above judges one, and the tail is tried from
    where it resolves; the walk does **not** then list the link's own target for further `**`
    matches (the rule this task builds), so a link cycle (a link whose target reaches it again)
    ends every branch in one step rather than recursing without end -- a real directory tree holds
    no such cycle without a link in it. None when nothing refuses, including when a directory
    cannot be listed (the same as the single-component loop's own error reading).

    **(D14) In the bash dialect, when `dotglob` is not named, a dot-leading entry is skipped**
    before it is tried or descended into: `**` never itself begins with `.` or `[`, and holds no
    extglob group, so unlike the single-component loop above there is no written pattern that can
    exempt it -- a real shell's own `**` does not reach a dot-leading name or directory either,
    under the same default."""
    entries = budget.list_directory(directory)
    if entries is _LISTING_TOO_MANY:
        return _refuse(shown, _TOO_MANY)
    if entries is None:
        return None
    for entry in entries:
        if bash and not budget.dotglob_named and entry.name.startswith("."):
            continue
        real = entry.path
        listed = os.path.join(listed_directory, entry.name)
        is_link = _is_link_entry(entry)
        if is_link:
            refusal = _judge_path(real, root, shown, shown, False)
            if refusal:
                return refusal
            try:
                real = os.path.realpath(real)
            except (OSError, ValueError):
                continue
        refusal = _glob_tail_walk(tail, real, listed, root, shown)
        if refusal:
            return refusal
        if is_link:
            continue
        try:
            descend = entry.is_dir(follow_symlinks=False)
        except OSError:
            descend = False
        if descend:
            refusal = _globstar_walk(real, listed, tail, root, shown, budget, bash)
            if refusal:
                return refusal
    return None


def _expands(text: str) -> bool:
    """Whether `text` holds anything the shell may substitute when it runs: a `$` (or one it will
    not expand -- conservatively, still counted), a command substitution, a leading `~`, or a
    `%NAME%` that a nested `cmd /c` would expand."""
    return (
        "$" in text
        or _LITERAL_DOLLAR in text
        or text.startswith("~")
        or bool(_CMD_VARIABLE_RE.search(text))
    )


def _directory_variable_reference(value: str, dialect: str) -> bool:
    """Whether `value` holds a bare reference to a directory variable (D2, F401) at its start or
    directly after one of its `:` (R4): the dialect's own spelling, or a `%NAME%` form read in
    either dialect, each not followed by a name character."""
    for start in [0] + [index + 1 for index, char in enumerate(value) if char == ":"]:
        if _DIRECTORY_VARIABLE_RE[dialect].match(value, start):
            return True
        match = _CMD_VARIABLE_RE.match(value, start)
        if match and match.group()[1:-1].upper() in _CMD_DIRECTORY_VARIABLE_NAMES:
            tail = value[match.end() :]
            if not tail[:1].isalnum() and tail[:1] != "_":
                return True
    return False


def _first_expansion_start(value: str) -> int:
    """The index of the first mark `_expands` would count as an expansion in `value`, or -1 when
    there is none (design D3)."""
    starts = [index for index in (value.find("$"), value.find(_LITERAL_DOLLAR)) if index >= 0]
    match = _CMD_VARIABLE_RE.search(value)
    if match:
        starts.append(match.start())
    return min(starts) if starts else -1


def _names_the_parent_once_expanded(value: str) -> bool:
    """D3 (R4): an unset variable or an empty substitution leaves the rest in place, so a value
    (cut at a NUL) that is exactly `..` once every expansion is removed names the parent (`$x..`,
    `$(true)..`, `.$x.`). `_words` trims a backtick from a word's start, so an inner shell's
    `` `true`.. `` arrives as ``true`..``: it is also read with that backtick restored."""
    cut = value.partition("\x00")[0]
    readings = (cut, "`" + cut) if "`" in cut else (cut,)
    for text in readings:
        removed = _EXPANSION_RE.sub("", text)
        if removed != text and removed == "..":
            return True
    return False


def _judge_link_word(
    budget: "_Budget",
    value: str,
    glued_run: str,
    word: str,
    root: str,
    argument: str,
    continues: bool,
    dialect: str,
) -> Optional[Dict[str, Any]]:
    """D10 (R4): rule 4's premise, that a separator-less word names an entry of the directory the
    shell runs in, is false for a link out of it. So `value` (cut at a NUL) is judged as the entry
    it names when one exists (`_where` resolves a link, and the refusal names where it lands), or
    by the links it matches when it is a glob (the sibling's `_glob_links`, bracket-kept words
    included). A glued short option run with no value left (`-tup`) has each suffix after its
    first letter tried as a name, since which letters take a value is the program's business. On
    a drive-letter host a value with a `:` is D1's, not this check's."""
    value = value.partition("\x00")[0]
    if _DRIVE_LETTERS and ":" in value:
        return None
    if _holds_glob_character(value):
        return _glob_links(os.path.join(root, value), word, root, budget, dialect == "bash")
    names = [value] if value else [glued_run[index:] for index in range(1, len(glued_run))]
    for name in names:
        if os.path.lexists(os.path.join(root, name)):
            refusal = _judge_path(name, root, word, argument, continues)
            if refusal:
                return refusal
    return None


def _effective_port(parts: urllib.parse.SplitResult) -> Optional[int]:
    return parts.port if parts.port is not None else _DEFAULT_PORTS.get(parts.scheme.lower())


def _hub_base(hub_url: Optional[str]) -> str:
    """The run's own Hub address: the caller's `hub_url` when given, else this process's `HUB_URL`.

    The spawned MCP process has the run's environment, so the default is right there. The Hub
    process judging a Copilot request in-process (`copilot_acp.decide_permission`) does not: its
    environment names whatever the Hub itself was started with, so it passes the run's address.
    """
    return (hub_url if hub_url is not None else os.environ.get("HUB_URL", "")).strip()


def _is_own_hub(url: str, hub_url: Optional[str] = None) -> bool:
    """Whether a URL names the run's own Hub: the approver's `HUB_URL` scheme (ignoring case), host
    and effective port, with no userinfo.

    Any path, query or fragment is permitted: the Hub authenticates each request by the run's
    token, which reaches only the agent-action surface. `localhost` is not equated with
    `127.0.0.1`; that would be a DNS claim this cannot check.
    """
    base = _hub_base(hub_url)
    if not base:
        return False
    try:
        named, own = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
        return (
            named.scheme.lower() == own.scheme.lower()
            and named.hostname is not None
            and named.hostname == own.hostname
            and _effective_port(named) == _effective_port(own)
            and named.username is None
            and named.password is None
        )
    except ValueError:  # a port that does not parse, or a malformed IPv6 host
        return False


def _judge_url(
    word: str, root: str, argument: str, continues: bool, hub_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Rule 1. A `file:` URL is judged as the path it names. The run's own Hub may be named, and is
    still judged as the relative path it spells, because the shell does not know it is a URL
    (`echo hi > http://hub/../../x` writes through a directory called `http:`). Any other address
    is refused as what it is."""
    try:
        parts = urllib.parse.urlsplit(word)
    except ValueError:
        return _refuse(word, _NETWORK)
    if parts.scheme.lower() == "file":
        if parts.netloc.lower() not in ("", "localhost"):
            return _refuse(word, _OUTSIDE)
        try:
            path = urllib.request.url2pathname(parts.path)
        except (OSError, ValueError):
            return _refuse(word, _UNRESOLVED)
        return _judge_path(path, root, word, argument, continues)
    if not _is_own_hub(word, hub_url):
        return _refuse(word, _NETWORK)
    if _expands(word):
        return _refuse(word, _UNCHECKED)
    return _judge_path(word, root, word, argument, continues)


_BACKSLASH_ESCAPE_RE = re.compile(r"\\(.)", re.DOTALL)


def _escape_removed_levels(word: str) -> List[str]:
    """D7: every level besides `word` itself that an inner shell's own unquoted-backslash escaping
    can reach, each one `_BACKSLASH_ESCAPE_RE` applied to the previous level's text (every `\\c`
    becomes `c`, scanning left to right, so a run of backslashes at least halves each level --
    `_BACKSLASH_ESCAPE_RE` is `(?s)` so a literal newline after a backslash is consumed the same
    way). Stops at the level that changes nothing, rather than at "no backslash is left", so a
    trailing backslash (`src\\`, `x\\\\`) ends the loop instead of never answering (R5)."""
    levels: List[str] = []
    current = word
    while "\\" in current:
        rewritten = _BACKSLASH_ESCAPE_RE.sub(r"\1", current)
        if rewritten == current:
            break
        levels.append(rewritten)
        current = rewritten
    return levels


def _judge_drive_word(
    budget: "_Budget", word: str, root: str, argument: str, continues: bool, dialect: str
) -> Optional[Dict[str, Any]]:
    """D1: a separator-less word (or colon-joined option value) that names a drive, judged as that
    drive's current directory, quoting the word. On a drive-letter host only a drive that exists
    is judged (operator, `B4-drive-exists`); on POSIX (pwsh) `Z:` is a file name, judged as one.
    PowerShell's `Temp:` names the temporary directory, `_UNRESOLVED` when there is none usable."""
    if dialect != "powershell" and not _DRIVE_LETTERS:
        return None
    joined = _COLON_OPTION_RE.match(word)
    value = word[joined.end() :] if joined else word
    if dialect == "powershell" and _PS_TEMP_DRIVE_RE.fullmatch(value):
        try:
            temporary = tempfile.gettempdir()
        except Exception:
            return _refuse(word, _UNRESOLVED)
        return _judge_path(os.path.join(temporary, value[5:]), root, word, argument, continues)
    if not _PS_DRIVE_RE.fullmatch(value):
        return None
    if _DRIVE_LETTERS and not budget.drive_exists(value[0].upper()):
        return None
    return _judge_path(value, root, word, argument, continues)


def _judge_word(
    budget: "_Budget",
    word: str,
    argument: str,
    continues: bool,
    trailing_colon: bool,
    root: str,
    dialect: str,
    trusted: bool,
    hub_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Judge one word by the first of the six rules that matches it; None when it may stand."""
    if _URL_SCHEME_RE.match(word):  # 1: a URL
        return _judge_url(word, root, argument, continues, hub_url)
    reference = _HUB_REFERENCE_RE[dialect].match(word)
    if reference:  # 2: a reference to the run's own Hub
        rest = word[reference.end() :]
        base = _hub_base(hub_url)
        if trusted and base and (not rest or rest[0] in "/?#") and not _expands(rest):
            # Also the path it spells, once the shell has put the approver's value in its place.
            return _judge_path(base + rest, root, word, argument, continues)
        return _refuse(word, _UNCHECKED)
    if _SCP_ADDRESS_RE.match(word) or _HOST_PORT_RE.match(word):  # D5: a schemeless network address
        return _refuse(word, _NETWORK)
    if trailing_colon and _SCP_ADDRESS_RE.match(word + ":"):  # D5, R5: the colon `_words` trimmed
        return _refuse(word + ":", _NETWORK)
    has_separator = any(separator in word for separator in _SEPARATORS)
    if has_separator and _expands(word):  # 3: where it points is decided when the shell runs
        return _refuse(word, _UNCHECKED)
    if not has_separator:  # 4: a name in the directory the shell runs in -- unless it names another
        # F402 (D1, D4): a drive word names that drive's current directory. The check only ever
        # refuses; an inside or skipped answer goes on to the checks below. F401's checks follow
        # (D2, D3): D5's option (d), a bare directory variable and a surviving `..`, not every
        # expansion.
        refusal = _judge_drive_word(budget, word, root, argument, continues, dialect)
        if refusal:
            return refusal
        value, glued_run = word, ""
        joined = _COLON_OPTION_RE.match(word)
        if joined:
            value = word[joined.end() :]
            if dialect == "powershell" and _TILDE_PREFIX_RE.fullmatch(value):
                return _refuse(word, _UNCHECKED)
        else:
            if _TILDE_PREFIX_RE.fullmatch(word):
                return _refuse(word, _UNCHECKED)
            glued = _GLUED_OPTION_RE.match(word)
            if glued:
                value, glued_run = word[glued.end() :], glued.group()[1:]
        last_colon = value.rfind(":")
        if last_colon >= 0 and _TILDE_PREFIX_RE.fullmatch(value[last_colon + 1 :]):  # D4
            return _refuse(word, _UNCHECKED)
        if _directory_variable_reference(value, dialect):  # D2 (F401)
            return _refuse(word, _UNCHECKED)
        expansion_start = _first_expansion_start(value)
        if expansion_start >= 0 and value[:expansion_start] == "..":  # D3 (F401)
            return _refuse(word, _UNCHECKED)
        if _names_the_parent_once_expanded(value):  # D3 (R4)
            return _refuse(word, _UNCHECKED)
        cut = value.partition("\x00")[0]
        if cut == "..":
            return _judge_path("..", root, word, argument, continues)
        # D4: `.*`/`.?` are not rewritten -- as often a quoted regular expression (`grep '.*' f`).
        if (
            cut.startswith("..")
            and any(char in cut for char in _GLOB_CHARS)
            and fnmatch.fnmatchcase("..", cut)
        ):
            return _judge_path("..", root, word, argument, continues)
        return _judge_link_word(
            budget, value, glued_run, word, root, argument, continues, dialect
        )  # D10
    if dialect == "bash" and word in _BASH_DEVICES:  # D4: the null device, stdin/out/err
        return None
    if "::" not in word and (  # D7: a `::` word is not plain in either dialect -- rule 6 reads it
        os.path.isabs(word) or _PLAIN_RELATIVE_RE.match(word)
    ):  # 5: a path, resolved
        rewritten = _rewrite_dotdot_globs(word)
        refusal = _judge_path(rewritten, root, word, argument, continues)
        if refusal:
            return refusal
        # (R5, D8) An absolute word holding a glob character or an extglob group is also matched
        # against the links it finds, not only judged by its literal text -- `_PLAIN_RELATIVE_RE`
        # already keeps every relative glob out of this branch (D8, "Where it runs"). Matched on
        # `word`, not `rewritten`: D3's dot-rewrite only ever touches a component that already
        # holds a glob character (never a glob-free base or tail component), so handing
        # `_glob_links` the rewritten text would erase the very glob character it needs to find a
        # real entry (`.l`) through -- the literal `..` reading that rewrite feeds is
        # `_judge_path`'s job, just above, not this one's.
        if os.path.isabs(word) and _holds_glob_character(word):
            return _glob_links(word, word, root, budget, dialect == "bash")
        return None
    return _judge_pieces(
        word, root, argument, continues, dialect, budget
    )  # 6: the piece reading (D2)


def _judge_piece(
    piece: str, root: str, argument: str, continues: bool, dialect: str, budget: "_Budget"
) -> Optional[Dict[str, Any]]:
    """One piece of rule 6's reading, shared by both its readings (D2 step 6, R8): a NUL, a
    leading `~`, or (on a drive-letter host) a drive piece whose text after the colon begins with
    `~` refuses outright (D2 step 5 -- bash expands a tilde after `:` in an assignment-shaped
    argument); else it is judged as the relative or absolute path it spells. (R5, D8) A piece
    holding a glob character or an extglob group is also matched
    against the links it finds, not only judged by its literal text -- mirroring rule 5's own
    `_glob_links` call, but joined to `root` first when relative, since `_glob_links` reads its
    piece as rooted at a drive (or, with none, at the filesystem root) rather than at the
    workspace. `dialect` (D14) is only ever used to tell `_glob_links` whether the bash dot rule
    applies; it changes no other reading here.

    `_glob_links` is matched on `piece`, not on D3's `..`-rewrite of it: that rewrite only ever
    touches a component that already holds a glob character (a glob-free component never
    satisfies its own `_GLOB_CHARS` check), so handing `_glob_links` the rewritten text would
    erase the one glob character it needs to find a real entry through -- the literal `..`
    reading the rewrite feeds is `_judge_path`'s job, just above, not this one's."""
    if "\x00" in piece:
        return _refuse(piece, _UNRESOLVED)
    if _TILDE_PREFIX_RE.match(piece):
        return _refuse(piece, _UNCHECKED)
    if _DRIVE_LETTERS and _DRIVE_PIECE_RE.match(piece) and _TILDE_PREFIX_RE.match(piece, 2):
        return _refuse(piece, _UNCHECKED)
    rewritten = _rewrite_dotdot_globs(piece)
    refusal = _judge_path(rewritten, root, piece, argument, continues)
    if refusal:
        return refusal
    if _holds_glob_character(piece):
        absolute = piece if os.path.isabs(piece) else os.path.join(root, piece)
        return _glob_links(absolute, piece, root, budget, dialect == "bash")
    return None


def _judge_pieces_reading(
    value: str, root: str, argument: str, continues: bool, dialect: str, budget: "_Budget"
) -> Optional[Dict[str, Any]]:
    """D2 steps 2-5: mask each extglob group (D3) so splitting at `_PIECE_BREAKS_RE` does not break
    inside one, split (keeping each delimiter, so a piece can be told apart from a redirect
    target), restore the group's own text in each surviving piece, and judge each non-empty
    piece, the last one carrying `continues` on to `_judge_path`.

    D4: in the bash dialect, a piece naming a mapped device (`_BASH_DEVICES`) stands rather than
    being judged as a path -- on a host with drive letters, only when it is a redirect target (the
    piece directly after a `<`/`>` break; a native program given the name as a plain argument word
    opens a real `C:\\dev\\...` path, which msys does not map), and on every other host for any
    piece, since there `/dev/null` is a real device for every program.
    """
    split = _PIECE_BREAKS_SPLIT_RE.split(_mask_drive_colons(_mask_extglob_groups(value)))
    pieces = [
        (split[index], split[index - 1] if index > 0 else "") for index in range(0, len(split), 2)
    ]
    pieces = [(piece, delimiter) for piece, delimiter in pieces if piece]
    for index, (piece, delimiter) in enumerate(pieces):
        restored = _restore_extglob_sentinels(piece).replace(_DRIVE_COLON_SENTINEL, ":")
        redirect_target = delimiter[-1:] in ("<", ">")
        if (
            dialect == "bash"
            and restored in _BASH_DEVICES
            and (not _DRIVE_LETTERS or redirect_target)
        ):
            continue
        refusal = _judge_piece(
            restored, root, argument, continues and index == len(pieces) - 1, dialect, budget
        )
        if refusal:
            return refusal
    return None


def _whole_value(word: str) -> str:
    """D2 step 6: the value rule 6 judges whole is the word after its option run, as step 1 strips
    it, except a colon-joined option (`-Destination:`) is dropped first -- the same split rule 4
    already makes between the two option forms (D7). Needed because, unlike step 1, step 6 never
    splits the value at `:` itself (that would reintroduce the piece break step 6 exists to avoid).
    """
    joined = _COLON_OPTION_RE.match(word)
    if joined:
        return word[joined.end() :]
    if word.startswith("-"):
        glued = _GLUED_OPTION_RE.match(word)
        if glued:
            return word[glued.end() :]
    return word


def _judge_whole_value(
    value: str, root: str, argument: str, continues: bool, dialect: str, budget: "_Budget"
) -> Optional[Dict[str, Any]]:
    """D2 step 6 (R8): after the pieces, the value is also judged as the path it spells, undivided
    by the breaks that only glue it to a host, a revision or a curl `name@file` -- a link or a
    physical `..` just before one of those was never resolved by the piece split alone
    (`sub/@s/p/w1`, `"../ws(a"`). On a drive-letter host the value is not judged with its colons
    kept, only divided at them (D9): `ntpath.realpath` misreads a bare `X:` as a drive, which would
    wrongly refuse a line reference or a regular expression that never names a path
    (`sed 's/::.*//'`). On POSIX `:` is an ordinary name character, so the value is judged whole
    with its colons as well as divided -- `cp n t:d/up/x` reaches a directory literally named
    `t:d`. Each reading goes through the same per-piece checks a piece already does (`_judge_piece`:
    a NUL, a leading `~`, D3's `..`-rewrite, `_judge_path`).

    (D13) The split is made on `value` with each bracket expression's own `:` masked
    (`_mask_bracket_colons`), so a POSIX class or any other bracket expression holding a literal
    `:` is not torn apart before `_glob_links` ever sees it as a bracket; the sentinel is restored
    in each surviving segment before it is judged, so the text judged and quoted is exactly the
    substring of `value` as written."""
    if not _DRIVE_LETTERS:
        refusal = _judge_piece(value, root, argument, continues, dialect, budget)
        if refusal:
            return refusal
    segments = [segment for segment in _mask_bracket_colons(value).split(":") if segment]
    if _DRIVE_LETTERS or len(segments) > 1:
        for index, segment in enumerate(segments):
            restored = segment.replace(_BRACKET_COLON_SENTINEL, ":")
            refusal = _judge_piece(
                restored,
                root,
                argument,
                continues and index == len(segments) - 1,
                dialect,
                budget,
            )
            if refusal:
                return refusal
    return None


def _judge_pieces(
    word: str, root: str, argument: str, continues: bool, dialect: str, budget: "_Budget"
) -> Optional[Dict[str, Any]]:
    """Rule 6, replaced (D2, F362): a word that reached here holds a separator, no expansion, is
    not plain and is not absolute. It is split at path-component breaks rather than scanned for an
    absolute tail, and judged once more with its quote characters removed -- the reading an inner
    shell joins (`sh -c "echo hi > '.'./stray.txt"` hands its inner shell `../stray.txt`). The
    undivided value is then judged too, in both readings (D2 step 6, R8)."""
    value = word
    if value.startswith("-"):  # D2 step 1: drop a short option's own letters, judge its value
        glued = _GLUED_OPTION_RE.match(value)
        if glued:
            value = value[glued.end() :]
    refusal = _judge_pieces_reading(value, root, argument, continues, dialect, budget)
    if refusal:
        return refusal
    whole_value = _whole_value(word)
    refusal = _judge_whole_value(whole_value, root, argument, continues, dialect, budget)
    if refusal:
        return refusal
    if any(quote in value for quote in _PIECE_QUOTES):
        unquoted = value.translate(str.maketrans("", "", _PIECE_QUOTES))
        refusal = _judge_pieces_reading(unquoted, root, argument, continues, dialect, budget)
        if refusal:
            return refusal
        refusal = _judge_whole_value(
            whole_value.translate(str.maketrans("", "", _PIECE_QUOTES)),
            root,
            argument,
            continues,
            dialect,
            budget,
        )
        if refusal:
            return refusal
    return None


# Escapes ANSI-C quoting decodes outright, independent of `reading`: bash renders each of these
# identically in every locale (a-quote-can-spell-a-slash, design D1).
_ANSI_C_SIMPLE_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
_HEX_DIGITS = "0123456789abcdefABCDEF"


def _hex_digits(text: str, index: int, max_len: int) -> str:
    """Up to `max_len` consecutive hex digits of `text` starting at `index`; "" if none."""
    end = index
    while end < len(text) and end - index < max_len and text[end] in _HEX_DIGITS:
        end += 1
    return text[index:end]


def _ansi_c_escape(text: str, index: int, reading: str) -> Tuple[str, int]:
    """Decode the ANSI-C escape at `text[index]` (a backslash), for `reading` ("c" or "utf8").

    Returns the decoded text and the index just past what the escape consumes. Total: never
    raises, including on an out-of-range `\\u`/`\\U` value (design D1/D5). An escape decodes to a
    character only when that character's contribution to the word's path-component structure is
    determined for `reading`; every other case keeps the backslash literal, because bash may keep
    it, and on Windows a kept backslash is itself a path separator.
    """
    letter_index = index + 1
    if letter_index >= len(text):
        return "\\", letter_index  # a trailing backslash is literal
    letter = text[letter_index]
    simple = _ANSI_C_SIMPLE_ESCAPES.get(letter)
    if simple is not None:
        return simple, letter_index + 1
    if letter in "01234567":
        digits = letter
        pos = letter_index + 1
        while len(digits) < 3 and pos < len(text) and text[pos] in "01234567":
            digits += text[pos]
            pos += 1
        return chr(int(digits, 8) % 256), pos
    if letter == "x":
        digits = _hex_digits(text, letter_index + 1, 2)
        if not digits:
            return "\\x", letter_index + 1  # digitless: keep the backslash literal
        return chr(int(digits, 16)), letter_index + 1 + len(digits)
    if letter in "uU":
        width = 4 if letter == "u" else 8
        digits = _hex_digits(text, letter_index + 1, width)
        if not digits:
            return "\\" + letter, letter_index + 1  # digitless: keep the backslash literal
        end = letter_index + 1 + len(digits)
        value = int(digits, 16)
        if value <= 0xFF:
            return chr(value), end  # a byte escape: locale-independent, decode outright
        if value >= 0x80000000:
            return "", end  # bash emits nothing here, in every locale (design D1, Round 4)
        # 0x100..0x7FFFFFFF renders differently by locale -- judge both readings (design D1).
        if reading == "c":
            return "\\" + letter + digits.upper(), end  # bash uppercases a kept-literal escape
        # utf8 reading: chr() is bounded by U+10FFFF; above it, a fixed non-separator stand-in
        # (design D5) -- never derived from the input, and never the dropped-empty-string R2 used,
        # which would lose the "c" reading's kept backslash where one is real.
        return (chr(value) if value <= 0x10FFFF else "z"), end
    if letter == "c":
        body_index = letter_index + 1
        if body_index >= len(text) or text[body_index] == "'":
            # nothing to control: keep literal, and never consume the closing quote as the target
            return "\\c", letter_index + 1
        body_bytes = text[body_index].encode("utf-8", "surrogatepass")
        control = "".join(
            chr(byte & 0x1F if position == 0 else byte) for position, byte in enumerate(body_bytes)
        )
        return control, body_index + 1
    return "\\" + letter, letter_index + 1  # an unrecognized escape keeps its backslash


def _ansi_c_string(command: str, start: int, reading: str) -> Tuple[str, int]:
    """The decoded text of a bash ANSI-C `$'...'` string, `start` just past the opening `$'`.

    Returns the decoded text and the index just past the closing `'` -- or past the end of the
    text if it never closes, keeping the lexer total (design D1). A produced literal `$` is not
    re-expanded by ANSI-C quoting, so it becomes the same sentinel an ordinary single-quoted `$`
    already does.
    """
    decoded: List[str] = []
    index = start
    while index < len(command):
        char = command[index]
        if char == "'":
            return "".join(decoded), index + 1
        if char == "\\":
            piece, index = _ansi_c_escape(command, index, reading)
            # A `$` an escape decodes to (`\x24`, `\044`, or a low-codepoint `\u`/`\U`) is just as
            # literal as one typed directly, so it gets the same sentinel (design D1).
            decoded.append(piece.replace("$", _LITERAL_DOLLAR))
            continue
        decoded.append(_LITERAL_DOLLAR if char == "$" else char)
        index += 1
    return "".join(decoded), index


_SUBSTITUTION_OPENERS = {")": "(", "}": "{"}  # the opener a `closer` nests on (design D1 for `}`)


def _substitution(text: str, start: int, closer: str) -> Tuple[str, int]:
    """The command text of a substitution opened just before `start`, and where lexing resumes.
    Unbalanced, it runs to the end of the text."""
    opener = _SUBSTITUTION_OPENERS.get(closer)
    depth, index = 1, start
    while index < len(text):
        char = text[index]
        if opener is not None and char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    return text[start:], len(text)


def _brace_sequence(content: str) -> Optional[List[str]]:
    """A bare `{x..y}` sequence's alternatives, or None when `content` is not one (design D1).

    An integer sequence is replaced by one representative, its first endpoint: none of its
    elements can hold a separator or `~`, and each would be judged alike. A letter sequence is
    expanded in full, over bash's ASCII-code range between its endpoints (so `{Z..a}` runs
    through the punctuation between them too), bounded at `_BRACE_MAX_LETTER_SPAN` elements.
    """
    integers = _BRACE_INT_SEQUENCE_RE.match(content)
    if integers:
        return [integers.group(1)]
    letters = _BRACE_LETTER_SEQUENCE_RE.match(content)
    if letters:
        start, end = ord(letters.group(1)), ord(letters.group(2))
        step = 1 if end >= start else -1
        if abs(end - start) + 1 > _BRACE_MAX_LETTER_SPAN:
            return None
        return [chr(code) for code in range(start, end + step, step)]
    return None


def _brace_frame() -> Dict[str, Any]:
    return {"results": [""], "chains": [], "literal": []}


def _brace_flush(frame: Dict[str, Any]) -> None:
    if frame["literal"]:
        text = "".join(frame["literal"])
        frame["results"] = [prefix + text for prefix in frame["results"]]
        frame["literal"] = []


def _brace_absorb(parent: Dict[str, Any], alternatives: List[str], budget: int) -> bool:
    """Cross `alternatives` into `parent`'s results, budget-checked before building (design D1,
    "The bounds" -- counted before any alternative is built). False past `budget`."""
    if len(alternatives) > budget or len(parent["results"]) * len(alternatives) > budget:
        return False
    parent["results"] = [prefix + alt for prefix in parent["results"] for alt in alternatives]
    return True


def _expand_braces(argument: str, budget: int) -> Optional[List[str]]:
    """Every alternative `argument` expands to under bash's brace rule (design D1), with each
    `{...}` group marked by `_lex` -- a top-level sentinel comma makes it a real group, a bare
    `x..y` (no sentinel inside) a sequence, anything else restored as literal characters, with any
    group nested inside it still expanded. None past `_BRACE_MAX_NESTING` groups deep or past
    `budget` alternatives from this argument -- `_decide` then refuses with `_TOO_MANY`.

    Built iteratively, an explicit stack of open groups, so there is no recursion (design D1,
    Totality): a run of thousands of `{` with no matching `}` pushes only up to the nesting cap
    before this returns None, and never recurses on depth.
    """
    stack: List[Dict[str, Any]] = [_brace_frame()]
    index = 0
    while index < len(argument):
        char = argument[index]
        if char == _BRACE_OPEN:
            _brace_flush(stack[-1])
            if len(stack) > _BRACE_MAX_NESTING:
                return None
            stack.append(_brace_frame())
            index += 1
            continue
        if char == _BRACE_COMMA and len(stack) > 1:
            _brace_flush(stack[-1])
            stack[-1]["chains"].append(stack[-1]["results"])
            stack[-1]["results"] = [""]
            index += 1
            continue
        if char == _BRACE_CLOSE and len(stack) > 1:
            _brace_flush(stack[-1])
            frame = stack.pop()
            frame["chains"].append(frame["results"])
            if len(frame["chains"]) == 1:
                sole = frame["chains"][0]
                sequence = _brace_sequence(sole[0]) if len(sole) == 1 else None
                alternatives = sequence if sequence is not None else ["{" + s + "}" for s in sole]
            else:
                alternatives = [alt for chain in frame["chains"] for alt in chain]
            if not _brace_absorb(stack[-1], alternatives, budget):
                return None
            index += 1
            continue
        stack[-1]["literal"].append(_BRACE_RESTORE.get(char, char))
        index += 1
    while len(stack) > 1:  # unbalanced: the rest of the text (already scanned) stays literal
        _brace_flush(stack[-1])
        frame = stack.pop()
        if not _brace_absorb(stack[-1], ["{" + s for s in frame["results"]], budget):
            return None
    _brace_flush(stack[0])
    return stack[0]["results"]


def _drive_exists(letter: str) -> bool:
    """D1 (operator, `B4-drive-exists`): `os.stat(letter + ":\\")`, wrapped. A clean
    `FileNotFoundError` answers False -- measured: `E:\\`, `A:\\` and `Z:\\` on a machine with only
    `C:` each raise it (errno 2, winerror 3). Any other outcome, a return or any other exception,
    answers True: counting a raise other than "not found" as absent could allow a word naming a
    real, reachable drive outside the workspace (a permission error, a not-ready card reader, an
    unreachable network drive), so the wrapper fails closed rather than delegating to bare
    `os.path.exists`, which treats every `OSError`/`ValueError` as absent."""
    try:
        os.stat(letter + ":\\")
    except FileNotFoundError:
        return False
    except Exception:
        return True
    return True


class _Budget:
    """One per `_decide` call, shared across both dialects, both readings and every nested
    substitution `_read_command` recurses into (design "The bounds", R4) -- so the same text read
    more than once for that reason is charged, and judged, only once.

    Two memos, neither keyed by `reading`: where the `c` and `utf8` readings render a word or an
    argument the same text, sharing the key is exactly what lets the second reading reuse the
    first's answer instead of paying for it again; where they differ (an ANSI-C escape above
    0x100), the text itself differs, so the key still separates them without naming `reading`.

    `globstar_named` (D8 step 2, step 4) is read once from the whole top-level `command`, by the
    caller, before any nested substitution's own text is read -- so a nested command cannot flip
    the flag a `_glob_links` call made on the outer text's say-so. `dotglob_named` (D14) is read
    the same way, for the same reason.
    """

    def __init__(self, globstar_named: bool = False, dotglob_named: bool = False) -> None:
        self.alternatives_spent = 0
        self.glob_entries_examined = 0
        self.globstar_named = globstar_named
        self.dotglob_named = dotglob_named
        self._expansions: Dict[Tuple[str, str], Optional[List[str]]] = {}
        self.judgements: Dict[Tuple[str, str, bool, bool, str, bool], Optional[Dict[str, Any]]] = {}
        self._listings: Dict[str, Optional[List["os.DirEntry[str]"]]] = {}
        self._drive_exists: Dict[str, bool] = {}

    def list_directory(self, directory: str) -> Any:
        """`os.scandir(directory)`, materialized and memoized by `directory` (design "The bounds",
        R5: "directory listings keyed by the resolved directory") -- a base `_glob_links` resolved
        with `_physical`, or a branch `_globstar_walk` recurses into, which is itself real because a
        non-link child of a real directory is real (design, "Why only links are resolved"). A
        second glob word, or a deeper `**` level, that lands on the same real directory is served
        from the memo and charges nothing; only a miss reads `os.scandir` and spends the budget,
        one entry at a time, exactly as before this memo existed.

        Returns the entry list on a hit or a clean miss; `None`, memoized, when the directory
        itself cannot be listed (`OSError`/`ValueError`, including the iterator raising partway,
        per design "What each changed route returns" -- deterministic for that path, so caching it
        costs nothing later); or `_LISTING_TOO_MANY`, **not** memoized, when the scan now reading
        this directory pushed `glob_entries_examined` past `_GLOB_ENTRY_BUDGET` -- the caller turns
        that into the same `_TOO_MANY` refusal a direct `os.scandir` loop would have given.
        """
        if directory in self._listings:
            return self._listings[directory]
        entries: List["os.DirEntry[str]"] = []
        try:
            with os.scandir(directory) as listing:
                for entry in listing:
                    self.glob_entries_examined += 1
                    if self.glob_entries_examined > _GLOB_ENTRY_BUDGET:
                        return _LISTING_TOO_MANY
                    entries.append(entry)
        except (OSError, ValueError):
            self._listings[directory] = None
            return None
        self._listings[directory] = entries
        return entries

    def expand_braces(self, marked: str, dialect: str) -> Optional[List[str]]:
        """`_expand_braces(marked, ...)`, memoized by the marked argument text and dialect (design
        "The bounds": "brace alternatives keyed by the marked argument text and dialect"). Charges
        `alternatives_spent` only on a miss, and caps the call at whichever of the per-argument and
        per-`_decide` bounds is tighter -- "past either bound" (D1) from one scalar cap.
        """
        key = (marked, dialect)
        if key in self._expansions:
            return self._expansions[key]
        cap = min(_BRACE_ARGUMENT_BUDGET, _BRACE_TOTAL_BUDGET - self.alternatives_spent)
        result = _expand_braces(marked, cap) if cap > 0 else None
        if result is not None:
            self.alternatives_spent += len(result)
        self._expansions[key] = result
        return result

    def drive_exists(self, letter: str) -> bool:
        """`_drive_exists(letter)`, memoized once per letter for the whole `_decide` call (design
        D1, `B4-drive-exists`): a drive word repeated in the same command pays for one probe."""
        if letter not in self._drive_exists:
            self._drive_exists[letter] = _drive_exists(letter)
        return self._drive_exists[letter]


def _memo_judge_word(
    budget: "_Budget",
    word: str,
    argument: str,
    continues: bool,
    trailing_colon: bool,
    root: str,
    dialect: str,
    trusted: bool,
    hub_url: Optional[str],
) -> Optional[Dict[str, Any]]:
    r"""`_judge_word`, memoized per `_decide` call by every per-word input the judgement reads
    (design "The bounds": "the key must carry every per-word input the judgement reads") -- so the
    same word reached twice (another reading, or another brace alternative) is judged once.

    D7: once the word itself stands, it is also judged at each of `_escape_removed_levels`'s
    levels -- each one *as a word*, through `_judge_word`'s own rules, not through this escape
    reading again (`_judge_word` is called directly, not `_memo_judge_word`, so a level's own
    backslashes are never re-leveled). An extra reading only adds a refusal; it never removes one,
    so the loop stops at the first level that refuses.

    POSIX only (`not _DRIVE_LETTERS`, read fresh so a test can monkeypatch it, D9's own rule).
    On a drive-letter host `\` is already a separator D2/rule 3/5 read directly, so a backslash
    there has two live meanings at once -- separator and candidate escape -- and they can
    disagree: `$'A\x/../../y1'` keeps a literal `\` (`_ansi_c_escape`'s own, final decode of that
    quote form; no further shell ever re-escapes it), read today as two real components `A`, `x`
    that exactly cancel the two `..` after them (inside). Escape-reducing that same `\` first
    merges `A` and `x` into one component, leaving a `..` with nothing left to cancel (outside) --
    a wrong, new refusal (measured: `test_a_quote_is_judged_by_what_it_decodes_to[P5a/P5b/P5c]`
    went from green to a false refusal before this guard). The grep cost example design names
    (`grep -rn '\.\./' src`) is the POSIX case this reading is for; its own "Cost (R5)" labels the
    new refusal POSIX only, and "already refused today [on Windows]... because `\` opens a root
    path there" is the other half of that sentence. The literal-backslash/separator conflict above
    is F487, accepted for a drive-letter host (operator, 2026-10-04: the escape levels stay POSIX
    only). Resolving it would need a sentinel for "this `\` is a quote's own final decode, not raw
    text" in the style of `_LITERAL_DOLLAR`, threaded through every `_SEPARATORS` site -- its own
    change if ever wanted.
    """
    key = (word, argument, continues, trailing_colon, dialect, trusted)
    if key in budget.judgements:
        return budget.judgements[key]
    refusal = _judge_word(
        budget, word, argument, continues, trailing_colon, root, dialect, trusted, hub_url
    )
    if refusal is None and not _DRIVE_LETTERS and "\\" in word:
        for level in _escape_removed_levels(word):
            refusal = _judge_word(
                budget, level, argument, continues, trailing_colon, root, dialect, trusted, hub_url
            )
            if refusal:
                break
    budget.judgements[key] = refusal
    return refusal


def _mark_inner_brace_sentinels(text: str) -> str:
    """`text` (already lexed) with every `{`, `,` and `}` marked as `_lex` marks an unquoted bash
    one (design D1, R2) -- the blanket worst case run over any argument, quoted or not, proven to
    reach a nested shell or not: a brace an inner shell would expand reaches `_words` literal, and
    under D2 its own piece would read as a name inside. A `{` directly after a real `$` or a
    `_LITERAL_DOLLAR` still opens a parameter expansion, exactly as `_lex` treats it, so it and its
    matching `}` are carried over literally rather than marked.
    """
    marked: List[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in ("$", _LITERAL_DOLLAR) and text[index + 1 : index + 2] == "{":
            inner, end = _substitution(text, index + 2, "}")
            marked.append(char + "{" + inner + "}")
            index = end
            continue
        marked.append(_BRACE_SENTINELS.get(char, char))
        index += 1
    return "".join(marked)


def _lex(command: str, bash: bool, reading: str) -> Tuple[List[str], List[str]]:
    """The arguments the shell will produce from `command`, and its substitutions' command texts.

    Bash: single quotes are literal; inside double quotes a backslash escapes only `$`, a
    backtick, `"`, a backslash and a newline, and is kept before anything else; outside quotes
    `\\c` is `c`. PowerShell: single quotes are literal (`''` is one quote), and the escape is a
    backtick, not a backslash. Unquoted whitespace and `| ; & < > ( )` end an argument. Bash also
    decodes a `$'...'` ANSI-C string when no quote is open, judged under `reading` (design D1) --
    `"$'...'"` is a literal `$` then a literal `'`, not this branch, because a quote is already
    open there. Total: an unbalanced quote runs to the end of the text, and nothing raises.
    """
    escape = "\\" if bash else "`"
    arguments: List[str] = []
    nested: List[str] = []
    current: List[str] = []
    started = False
    quote: Optional[str] = None
    index = 0
    while index < len(command):
        char, following = command[index], command[index + 1 : index + 2]
        if quote == "'":
            if char == "'" and not bash and following == "'":
                current.append("'")
                index += 2
                continue
            if char == "'":
                quote = None
            else:
                current.append(_LITERAL_DOLLAR if char == "$" else char)
            index += 1
            continue
        if char == "$" and following == "(":
            text, index = _substitution(command, index + 2, ")")
            nested.append(text)
            current.append(_SUBSTITUTION)
            started = True
            continue
        if bash and char == "`":
            text, index = _substitution(command, index + 1, "`")
            nested.append(text)
            current.append(_SUBSTITUTION)
            started = True
            continue
        if char == escape:
            if bash and quote == '"' and following not in ("$", "`", '"', "\\", "\n"):
                current.append(char)
                index += 1
            else:
                if not (bash and following == "\n"):  # a bash line continuation leaves nothing
                    current.append(_LITERAL_DOLLAR if following == "$" else following)
                index += 2
            started = True
            continue
        if quote == '"':
            if char == '"' and not bash and following == '"':
                current.append('"')
                index += 2
                continue
            if char == '"':
                quote = None
            else:
                current.append(char)
            index += 1
            continue
        if bash and char == "$" and following == "'":  # quote is None here (design D1)
            text, index = _ansi_c_string(command, index + 2, reading)
            current.append(text)
            started = True
            continue
        if bash and char == "$" and following == "{":  # quote is None here (design D1)
            # A `{` directly after a real `$` opens a parameter expansion, not a brace pattern:
            # its contents up to the matching `}` are literal, never marked as brace sentinels.
            text, index = _substitution(command, index + 2, "}")
            current.append("${" + text + "}")
            started = True
            continue
        if bash and char in _BRACE_SENTINELS:  # quote is None here (design D1)
            current.append(_BRACE_SENTINELS[char])
            started = True
            index += 1
            continue
        if bash and char in _EXTGLOB_TRIGGERS and following == "(":  # quote is None (D3)
            # Unquoted `(` and `|` are in `_ARGUMENT_ENDS` -- a bare subshell or pipe ends the
            # argument there -- but inside a balanced extglob group they are glob syntax, so the
            # whole group is kept as one run of literal characters in the current argument. An
            # unbalanced `(` (`_extglob_span_at` returns None) is not a group, and falls through to
            # the ordinary `_ARGUMENT_ENDS` handling below, ending the argument as before.
            end = _extglob_span_at(command, index)
            if end is not None:
                current.append(command[index:end])
                started = True
                index = end
                continue
        if char in "'\"":
            quote, started = char, True
            index += 1
            continue
        if char.isspace() or char in _ARGUMENT_ENDS:
            if started:
                arguments.append("".join(current))
            current, started = [], False
            index += 1
            continue
        current.append(char)
        started = True
        index += 1
    if started:
        arguments.append("".join(current))
    return arguments, nested


# (R6, D11) The trim `_words` also applies to recover a bracket a narrower trim would have lost:
# `[../x]` is refused today as `../x`, and a trim that removed the brackets by matching them as a
# pair, rather than as edge delimiters, would change that literal reading. So this is a second word
# alongside the ordinary one, never a replacement.
_WORD_TRIM_KEEP_BRACKETS = _WORD_TRIM.translate(str.maketrans("", "", "[]"))


def _bracket_kept_word(piece: str, ordinary: str) -> Optional[Tuple[str, str]]:
    """D11: for a `piece` whose ordinary trim removed a `[` or `]`, the same piece trimmed of
    `_WORD_TRIM` with the brackets left in -- when that still holds a `[` with a later `]`, so it
    is a word a glob reading can use. None otherwise (including when the brackets sat in the
    middle of the piece untouched by either trim, so `kept == ordinary`).

    Returns the word and the text it was left-trimmed to, so a trailing colon can be read off it
    the same way `_words` reads one off the ordinary word.
    """
    left = piece.lstrip(_WORD_TRIM_KEEP_BRACKETS)
    kept = left.rstrip(_WORD_TRIM_KEEP_BRACKETS)
    if not kept or kept == ordinary:
        return None
    open_index = kept.find("[")
    if open_index < 0 or "]" not in kept[open_index + 1 :]:
        return None
    return kept, left


def _drive_word(piece: str, dialect: str) -> Optional[str]:
    """D1: `piece` trimmed with its colon kept, when that names a drive (`Z:`, `Z:foo`, PowerShell's
    `Temp:`) or a colon-joined option whose value does (`-Destination:Z:`); else None, and the
    ordinary trim applies. The PowerShell reading on any host; the bash reading only where
    `_DRIVE_LETTERS` (read at call time, D9)."""
    if dialect != "powershell" and not _DRIVE_LETTERS:
        return None
    word = piece.strip(_WORD_TRIM_KEEP_COLON)
    joined = _COLON_OPTION_RE.match(word)
    value = word[joined.end() :] if joined else word
    if _PS_DRIVE_RE.fullmatch(value):
        return word
    if dialect == "powershell" and _PS_TEMP_DRIVE_RE.fullmatch(value):
        return word
    return None


def _words(arguments: List[str], dialect: str) -> List[Tuple[str, str, bool, bool]]:
    """Each argument's words, as (word, its argument, whether the argument carries on past it,
    whether a `:` was trimmed directly after the word).

    Split only at what stays in the string -- the whitespace, `=` and `,` that survived lexing --
    and trimmed of delimiters at both ends. A quote in the middle of a word is not split there:
    `sh -c "echo > '.'./x"` hands its inner shell `'.'./x`, which that shell joins into `../x`. The
    trailing-colon flag (D5, R5) lets `scp n user@example.com:` be matched with its colon restored,
    since `_WORD_TRIM` removes it before the word ever reaches a judge.

    (R6, D11) A piece whose trim removed a `[` or `]` also yields the bracket-kept word alongside
    it (`_bracket_kept_word`), so a bracket expression at a word's edge (`[u]p/x`, `u[p]`) is judged
    with its brackets intact too, not only with them stripped.

    A piece naming a drive keeps its colon (`_drive_word`, D1), so rule 4 can judge the drive.
    """
    words: List[Tuple[str, str, bool, bool]] = []
    for argument in arguments:
        pieces = _WORD_SPLIT_RE.split(argument)
        for position, piece in enumerate(pieces):
            drive = _drive_word(piece, dialect)
            if drive is not None:
                continues = (
                    position < len(pieces) - 1 or piece.rstrip(_WORD_TRIM_KEEP_COLON) != piece
                )
                words.append((drive, argument, continues, False))
                continue
            left_trimmed = piece.lstrip(_WORD_TRIM)
            word = left_trimmed.rstrip(_WORD_TRIM)
            if word:
                continues = position < len(pieces) - 1 or piece.rstrip(_WORD_TRIM) != piece
                trailing_colon = left_trimmed[len(word) : len(word) + 1] == ":"
                words.append((word, argument, continues, trailing_colon))
                kept = _bracket_kept_word(piece, word)
                if kept is not None:
                    kept_word, kept_left = kept
                    kept_trailing_colon = kept_left[len(kept_word) : len(kept_word) + 1] == ":"
                    words.append((kept_word, argument, continues, kept_trailing_colon))
    return words


def _read_command(
    command: str,
    root: str,
    dialect: str,
    reading: str,
    budget: "_Budget",
    depth: int = 0,
    hub_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The first refusal that reading `command` in `dialect` under `reading` finds, or None.

    `reading` ("c" or "utf8") picks which rendering a `$'...'` ANSI-C escape from 0x100 to
    0x7FFFFFFF decodes to (design D1) -- every other decode rule renders the same in both. It must
    reach a nested substitution's own recursive call, or a reading that stops at the top level
    would judge that substitution's ANSI-C content in one reading only.

    `budget` is the one `_Budget` for the whole `_decide` call (design "The bounds", R4): shared
    across both dialects, both readings and every nested substitution, so the same brace argument
    or word judged more than once for that reason is charged, and judged, only once.
    """
    if depth > _MAX_NESTING:
        # Nested past what is lexed: the backstop over the whole text, which is how every command
        # was once read, so nesting cannot hide a path from both readings.
        for match in _ABSOLUTE_PATH_RE.finditer(command):
            refusal = _judge_path(match.group(), root, match.group(), command, False)
            if refusal:
                return refusal
        return None
    arguments, nested = _lex(command, dialect == "bash", reading)
    if dialect == "bash":
        # D1: each alternative a brace argument expands to is handed on to `_words` as its own
        # argument, the way bash hands each alternative on as its own word. Most arguments carry
        # no sentinel at all, so they are passed through untouched.
        expanded_arguments: List[str] = []
        for argument in arguments:
            if any(sentinel in argument for sentinel in _BRACE_RESTORE):
                alternatives = budget.expand_braces(argument, dialect)
                if alternatives is None:
                    return _refuse(_restore_brace_sentinels(argument), _TOO_MANY)
                expanded_arguments.extend(alternatives)
            else:
                expanded_arguments.append(argument)
        arguments = expanded_arguments
    words = _words(arguments, dialect)
    references = sum(1 for word, _, _, _ in words if _HUB_REFERENCE_RE[dialect].match(word))
    # A reference is trusted only when the command names `HUB_URL` nowhere else. That refuses
    # every way of reassigning it first (`HUB_URL=`, `export`, `$env:HUB_URL =`) without a list.
    trusted = 0 < references == len(re.findall(r"(?i)HUB_URL", command))
    for word, argument, continues, trailing_colon in words:
        refusal = _memo_judge_word(
            budget, word, argument, continues, trailing_colon, root, dialect, trusted, hub_url
        )
        if refusal:
            return refusal
    # D1, R2: a brace an inner shell will expand is judged as expanded too -- the blanket worst
    # case applied to every argument holding a literal brace, whether the outer shell left it
    # literal by quoting or escaping it (bash) or never marks one at all (PowerShell).
    for argument in arguments:
        if "{" not in argument and "}" not in argument:
            continue
        marked = _mark_inner_brace_sentinels(argument)
        if not any(sentinel in marked for sentinel in _BRACE_RESTORE):
            continue
        inner_alternatives = budget.expand_braces(marked, dialect)
        if inner_alternatives is None:
            return _refuse(argument, _TOO_MANY)
        for word, inner_argument, continues, trailing_colon in _words(inner_alternatives, dialect):
            refusal = _memo_judge_word(
                budget,
                word,
                inner_argument,
                continues,
                trailing_colon,
                root,
                dialect,
                trusted,
                hub_url,
            )
            if refusal:
                return refusal
    for inner in nested:
        refusal = _read_command(inner, root, dialect, reading, budget, depth + 1, hub_url)
        if refusal:
            return refusal
    return None


# --- The Hub's own call command (`a-run-reaches-the-hub-without-mcp`, design D8) -----------------
# Four cases have standing: the MCP tools, one `aw-tool` invocation, a file-tool write of an
# arguments file, and (`an-arguments-file-written-from-powershell-is-the-hubs-own`) one PowerShell
# `Set-Content` of an arguments file, the notice's fallback route for the same write.

_HUB_OWN_REASON = "the Hub's own tools"

# Claude's write tools and the key each names its file by. Restated, not imported -- see the note
# at the top of this file; `test_hub_own_call.py` asserts it equals
# `hub.workspace_writes.CLAUDE_WRITE_TOOLS`. Every `_PATH_KEYS` entry present is read, so slice 2's
# `("Write", {"path": p})` judging of a Copilot edit is read too.
_HUB_OWN_WRITE_TOOLS = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}

# Every character an invocation of the call command needs, and nothing else (R2): an allow-list,
# never a list of refused syntax, which fails open the next time it misses something (`(...)` was
# such a miss). Explicit ASCII: `isalnum`, `isspace` and regex classes accept non-ASCII letters,
# digits and spaces, and `_lex` splits at any `isspace` character.
_PLAIN_COMMAND_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/ "
)
_PLAIN_COMMAND_CHARS_POWERSHELL = _PLAIN_COMMAND_CHARS | {"\\"}
_CALL_COMMAND_FLAGS = ("--list", "--help")


def _hub_calls_root(workspace: str) -> Optional[str]:
    """The calls root, or None when it is not itself (review fix 1).

    Built on the workspace's realpath and **not resolved further**: when `.agentweave` or `calls`
    is a link or a junction, the root differs from its own realpath and nothing is inside it. The
    workspace itself may be a link -- its realpath is what the root is built on. Compared this way
    rather than with `os.path.islink`, which is False for a directory junction on 3.11.
    """
    root = os.path.join(os.path.realpath(workspace), ".agentweave", "calls")
    if os.path.normcase(os.path.realpath(root)) != os.path.normcase(root):
        return None
    return root


def _inside_hub_calls_root(path: str, workspace: str) -> bool:
    """A `.json` file whose real path is inside the calls root (the calls-root rule). A relative
    path resolves against the workspace; a file-level link out, `..` and another drive fail."""
    root = _hub_calls_root(workspace)
    if root is None:
        return False
    base = os.path.realpath(workspace)
    real = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    normal_real, normal_root = os.path.normcase(real), os.path.normcase(root)
    return (
        normal_real != normal_root
        and os.path.commonpath([normal_real, normal_root]) == normal_root
        and normal_real.endswith(".json")
    )


def _plain_calls_path(word: str, workspace: str) -> bool:
    """Case 2's file word: a plain relative path (no leading separator or `-`, no drive, no `~`,
    no `..`), inside the calls root. The leading `-` is refused because PowerShell 5.1 splits a
    native argument that starts with `-` and holds a `.` into two (R3)."""
    if not word or word[0] in "-/\\~" or ":" in word:
        return False
    if ".." in re.split(r"[/\\]", word):
        return False
    return _inside_hub_calls_root(word, workspace)


def _hub_own_command(tool_name: str, command: str, workspace: str) -> bool:
    """Case 2: exactly one invocation of the call command, in the tool's own dialect."""
    dialects = _TOOL_DIALECTS.get(tool_name)
    if not dialects or not command:
        return False
    powershell = dialects[0] == "powershell"
    plain = _PLAIN_COMMAND_CHARS_POWERSHELL if powershell else _PLAIN_COMMAND_CHARS
    if any(char not in plain for char in command):
        return False
    words, nested = _lex(command, not powershell, "c")
    if nested or not 2 <= len(words) <= 3:
        return False
    # PowerShell compares command names case-insensitively and bash case-sensitively. A path to
    # the launcher does not match: the Hub cannot tell it from a file the agent wrote.
    names = ("aw-tool", "aw-tool.cmd") if powershell else ("aw-tool",)
    if (words[0].lower() if powershell else words[0]) not in names:
        return False
    if words[1] == "--help" and len(words) == 3:
        return words[2] in _CALLABLE_TOOLS
    if words[1] in _CALL_COMMAND_FLAGS:
        return len(words) == 2
    if words[1] not in _CALLABLE_TOOLS:
        return False
    return len(words) == 2 or _plain_calls_path(words[2], workspace)


# Case 4 (`an-arguments-file-written-from-powershell-is-the-hubs-own`, design D2): the notice's
# PowerShell route for the arguments file. Parameter names by their full name only; `-Path` and
# `-LiteralPath` are one parameter (wildcards cannot differ: the path's characters exclude them).
_PS_WRITE_PARAMETERS = {
    "-path": "path",
    "-literalpath": "path",
    "-value": "value",
    "-encoding": "encoding",
}
# What ends or poisons a single-quoted literal on PowerShell 5.1: the typographic single quotes,
# which close it like `'` (R3's tokenizer sweep: exactly U+2018-U+201B), and every C0 control but
# TAB, LF and CR, plus DEL (review). RFC 8259 allows none of them raw in a JSON text.
_PS_LITERAL_EXCLUDED = frozenset(
    [chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)]
    + [chr(c) for c in (0x7F, 0x2018, 0x2019, 0x201A, 0x201B)]
)
_PS_PATH_CHARS = _PLAIN_COMMAND_CHARS_POWERSHELL - {" "}


def _ps_bare_word(command: str, start: int) -> Tuple[str, int]:
    """The text from `start` to the next ASCII space or the end, and where it stops."""
    end = command.find(" ", start)
    end = len(command) if end < 0 else end
    return command[start:end], end


def _ps_single_quoted(command: str, start: int) -> Optional[Tuple[str, int]]:
    """The content of the `'...'` literal at `start` (a doubled `''` is one quote) and the index
    after its closing quote, or None when there is no literal or it holds an excluded character."""
    if command[start : start + 1] != "'":
        return None
    content: List[str] = []
    i = start + 1
    while i < len(command):
        char = command[i]
        if char in _PS_LITERAL_EXCLUDED:
            return None
        if char == "'":
            if command[i + 1 : i + 2] == "'":
                content.append("'")
                i += 2
                continue
            return "".join(content), i + 1
        content.append(char)
        i += 1
    return None


def _hub_own_powershell_write(command: str, workspace: str) -> bool:
    """Case 4: exactly `Set-Content -Path <p> -Value '<literal>' -Encoding utf8`, the parameters
    once each in any order, parts separated by ASCII spaces only (design D2).

    Every part must end at an ASCII space or the end of the text: text joined to any part is a
    further argument that PowerShell evaluates before the binding fails (review, measured). The
    path is held to an allow-list of characters, because `_plain_calls_path` alone resolves a name
    and would accept `.agentweave/calls/$(...).json`. The literal is never read."""
    if not command:
        return False
    i = len(command) - len(command.lstrip(" "))
    name, i = _ps_bare_word(command, i)
    if name.lower() != "set-content":
        return False
    seen: Dict[str, str] = {}
    while True:
        while i < len(command) and command[i] == " ":
            i += 1
        if i == len(command):
            break
        token, i = _ps_bare_word(command, i)
        parameter = _PS_WRITE_PARAMETERS.get(token.lower())
        if parameter is None or parameter in seen or i == len(command):
            return False
        while i < len(command) and command[i] == " ":
            i += 1
        if i == len(command):
            return False
        if parameter == "value":
            literal = _ps_single_quoted(command, i)
            if literal is None:
                return False
            value, i = literal
        elif command[i] == "'":
            quoted = _ps_single_quoted(command, i)
            if quoted is None:
                return False
            value, i = quoted
        else:
            value, i = _ps_bare_word(command, i)
        if i < len(command) and command[i] != " ":
            return False
        if parameter == "path" and (
            any(char not in _PS_PATH_CHARS for char in value)
            or not _plain_calls_path(value, workspace)
        ):
            return False
        if parameter == "encoding" and value.lower() != "utf8":
            return False
        seen[parameter] = value
    return set(seen) == {"path", "value", "encoding"}


def _hub_own_write(tool_name: str, tool_input: Dict[str, Any], workspace: str) -> bool:
    """Case 3: a write tool whose declared paths are all `.json` files inside the calls root, and
    that declares at least one (every path of none is vacuously true, R3)."""
    if tool_name not in _HUB_OWN_WRITE_TOOLS or "command" in tool_input:
        return False
    paths = [tool_input[key] for key in _PATH_KEYS if key in tool_input]
    if not paths or not all(isinstance(path, str) and path for path in paths):
        return False
    return all(_inside_hub_calls_root(path, workspace) for path in paths)


def _hub_own_call(
    tool_name: str, tool_input: Dict[str, Any], *, workspace: Optional[str] = None
) -> Optional[str]:
    """`"the Hub's own tools"` when this request is the Hub's own, else None (design D8).

    True in exactly four cases: the Hub's MCP tools; a `Bash`/`PowerShell` command that is
    exactly one `aw-tool` invocation (a callable tool, at most one plain relative `.json` path in
    the calls root); a write tool writing only `.json` files in the calls root; and a `PowerShell`
    command that is exactly one `Set-Content` of such a file from one single-quoted literal (case
    4, `an-arguments-file-written-from-powershell-is-the-hubs-own`). Those operations were never
    subject to the posture -- they are bounded by the run's own credential -- and the call command
    reaches exactly them. Case 4 alone allows what the workspace judge would refuse: the judge
    reads the literal's text as paths, and PowerShell writes it verbatim. Anything else is None, and the caller decides as it always
    has: a near miss is never denied by this rule. Total: any failure is None, because a raise
    would turn a fall-through into a refusal in both callers. `workspace` defaults to
    `AW_WORKSPACE_DIR`; a caller in the Hub process passes the run's.
    """
    try:
        if tool_name.startswith("mcp__agentweave__"):
            return _HUB_OWN_REASON
        if not isinstance(tool_input, dict):
            return None
        workspace = (
            workspace if workspace is not None else os.environ.get("AW_WORKSPACE_DIR", "")
        ).strip()
        if not workspace:
            return None
        if tool_name in _TOOL_DIALECTS:
            command = tool_input.get("command")
            if not isinstance(command, str):
                return None
            if _hub_own_command(tool_name, command, workspace):
                return _HUB_OWN_REASON
            if _TOOL_DIALECTS[tool_name][0] == "powershell" and _hub_own_powershell_write(
                command, workspace
            ):
                return _HUB_OWN_REASON
            return None
        if _hub_own_write(tool_name, tool_input, workspace):
            return _HUB_OWN_REASON
        return None
    except Exception:  # noqa: BLE001 -- total by contract
        return None


def _decide(
    tool_name: str,
    tool_input: Dict[str, Any],
    *,
    workspace: Optional[str] = None,
    hub_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide one permission request. Pure and total: every input maps to a decision.

    Mirrors `codex_appserver.decide_approval`'s contract for the Codex side — an unanswered
    request does not fail a turn, it suspends it forever, so there is no path here that declines
    to answer. Anything unrecognised denies rather than allows.

    A file tool's path is resolved against the workspace. A shell command's text is read as the
    tool's shell will read it, then word by word: a path is resolved against the workspace root,
    which is where the run started, and a URL may name only the run's own Hub. A `cd` in an
    earlier call is not seen, and a path built at run time never appears as a word, so this is a
    boundary, not a sandbox. Nor does it govern network access: it rules only on which address a
    shell command's text may name, and a fetch tool's URL is not read at all.

    A variable that names a directory (`$HOME`, `$env:USERPROFILE`, `%CD%`, ...; F401, design D2)
    and a drive that exists (`D:`, `Temp:`; F402, D1) are judged. A bare reference to any other
    variable, and a substitution, are not: `cp x $tmp` and `cp x $(git rev-parse --show-toplevel)`
    are allowed, with a reason saying the shell decides that value when it runs.

    `workspace` and `hub_url` default to this process's `AW_WORKSPACE_DIR` and `HUB_URL`, which are
    the run's own in the spawned MCP process. A caller judging in the Hub process (Copilot's ACP
    client, `a-copilot-agent-runs-over-acp` D8) passes the run's values instead: the Hub's own
    environment names neither. `hub_url` is threaded to every reader of `HUB_URL` below.
    """
    own = _hub_own_call(tool_name, tool_input, workspace=workspace)
    if own:
        return {"allow": True, "reason": own}

    workspace = (
        workspace if workspace is not None else os.environ.get("AW_WORKSPACE_DIR", "")
    ).strip()
    if not workspace:
        return {
            "allow": False,
            "reason": (
                "your workspace could not be established, so no action can be checked " "against it"
            ),
        }
    try:
        root = os.path.realpath(workspace)
    except (OSError, ValueError):
        return {"allow": False, "reason": "your workspace directory could not be resolved"}

    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            why = _where(value, root)
            if why:
                return _refuse(value, why)
    command = tool_input.get("command")
    expands = False
    if isinstance(command, str) and command:
        # A shell command declares no path, so its text is read in the tool's dialect and judged
        # word by word (the reader above). Relative words resolve against the workspace root,
        # which is where the run started; the shell's current directory is not seen.
        # One `_Budget` for the whole decision (design "The bounds", R4): shared across both
        # dialects and both readings below, so the same brace argument or word read more than
        # once for that reason is charged, and judged, only once. `globstar_named` (D8 step 2,
        # step 4, R5) is read once here, from the whole top-level command text, not re-derived
        # for a nested substitution's own text.
        budget = _Budget(
            globstar_named=bool(_GLOBSTAR_RE.search(command)),
            dotglob_named=bool(_DOTGLOB_RE.search(command)),
        )
        for dialect in _TOOL_DIALECTS.get(tool_name, ("bash", "powershell")):
            # Two passes, unconditionally: a `$'...'` escape from 0x100 to 0x7FFFFFFF renders
            # differently by locale, and both renderings must be judged (design D1, Round 4).
            for reading in ("c", "utf8"):
                refusal = _read_command(command, root, dialect, reading, budget, hub_url=hub_url)
                if refusal:
                    return refusal
                expands = expands or _names_a_runtime_value(command, dialect, reading)

    if expands:
        # The text was inside; what the shell substitutes when it runs was not seen. An allow is
        # read by an operator on an "Ask me" card, so it must not claim more than was checked
        # (`an-ask-me-card-says-what-workspace-only-would-decide`, D4).
        return {
            "allow": True,
            "reason": (
                "inside your workspace as far as its text shows; it names a value the shell "
                "decides when it runs"
            ),
        }
    return {"allow": True, "reason": "inside your workspace"}


def _names_a_runtime_value(command: str, dialect: str, reading: str) -> bool:
    """Whether any word of `command`, or a substitution nested in it, holds something the shell
    decides when it runs -- which the judge above cannot see."""
    arguments, nested = _lex(command, dialect == "bash", reading)
    return bool(nested) or any(_expands(word) for word, _, _, _ in _words(arguments, dialect))


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
    body: Dict[str, Any] = {
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "tool_input": tool_input,
    }
    verdict = _workspace_verdict(tool_name, tool_input)
    try:
        try:
            opened = _hub_request(
                "POST",
                "/permission-requests",
                {**body, "workspace_verdict": verdict} if verdict is not None else body,
            )
        except HubAPIError as exc:
            # A Hub not yet restarted onto the field refuses it in validation, before any row
            # exists, so asking once more without it opens exactly one card (design D2).
            if exc.status_code != 422 or verdict is None:
                raise
            opened = _hub_request("POST", "/permission-requests", body)
        request_id = opened["id"]
    except Exception:  # noqa: BLE001 - see docstring; an unreachable Hub must not hang the turn
        return {
            "allow": False,
            "reason": "the operator could not be asked (the Hub did not accept the request)",
        }

    return _await_decision(request_id)


def _workspace_verdict(tool_name: str, tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What "Workspace only" would decide for this call, shown to the operator as advice
    (`an-ask-me-card-says-what-workspace-only-would-decide`, D1/D3). None when it cannot be worked
    out: advice that fails must never stop the operator being asked.

    A shell command's allow says the text was read, not the command sandboxed."""
    try:
        verdict = dict(_decide(tool_name, tool_input))
    except Exception:  # noqa: BLE001 - the ask goes ahead without advice rather than failing
        return None
    if verdict.get("allow") and isinstance(tool_input.get("command"), str):
        verdict["reason"] = f"{verdict['reason']}; a shell command is read, not sandboxed"
    return verdict


def _await_decision(request_id: str) -> Dict[str, Any]:
    """Wait out one already-open permission request and report what the operator did.

    Split from `_ask_operator` so `archive_job` can wait on a request it did not open: the Hub's
    own route opens that one, because the rule that it must exist is the contract's
    (`hub/hub/operator_direction.py`). Waiting is protocol and may be shared; opening is not, and
    is why this half took the request id rather than the tool name.

    Reports the wait ended on a timeout, for the same reason `ask_user` does: the operator must
    stop being offered a card whose answer can no longer reach anybody.
    """
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


@_tool()
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
        # are already bounded by the run's own credential. The call command and its arguments
        # file are the same operations by another route (D8), so they are decided here too.
        own = _hub_own_call(tool_name, tool_input)
        if own:
            decision = {"allow": True, "reason": own}
        else:
            decision = _ask_operator(tool_name, tool_input, tool_use_id)
    else:
        try:
            decision = _decide(tool_name, tool_input)
        except Exception as exc:  # noqa: BLE001 - D6: fail closed, visibly, on any judge failure
            decision = {
                "allow": False,
                "reason": (
                    f"the workspace check failed on this call ({type(exc).__name__}); "
                    "ask the operator with ask_user"
                ),
            }
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
# The kinds an agent may begin. Restated from `api/v1/agent_actions.py` `AGENT_CREATABLE_KINDS`
# (this module imports nothing from the Hub); `test_mcp_tool_schemas.py` asserts the two agree.
CreatableSpecKind = Literal["change-spec", "roadmap"]
SPEC_SCHEMA_VERSION = 1

# The one closed vocabulary in the evidence surface, restated for the same reason as the rest.
#
# `kind` is deliberately **not** constrained here: `db.models.EVIDENCE_KINDS` is open at the edges
# on purpose — the list is what the surfaces know how to label, not what they accept — and a
# `Literal` would make this tool narrower than the route it calls, which
# `agent-capability-plane` forbids in either direction.
EvidenceDecision = Literal["accepted", "rejected"]


@_tool()
def create_spec_document(
    title: Optional[str] = None, kind: Optional[CreatableSpecKind] = None
) -> Dict[str, Any]:
    """Start a specification document when you need one — you do not need the operator to start it.

    Use this the moment you have something worth writing up: a finding, a proposal, a design
    worth recording. It creates the document and returns immediately so you keep working in the
    same turn — there is nothing to wait for and nobody to ask.

    This is step one of a three-call flow: `create_spec_document` → work out the subject →
    `rename_spec_document` → `submit_spec_document`. The `path` this returns is a placeholder —
    a colour and a mythic animal, meaning nothing about the document's actual subject. Call
    `rename_spec_document` as soon as you know what the document is about, and use the path it
    returns for everything after, including `submit_spec_document`.

    There is no `path` argument: the Hub always mints the path. `kind` is `change-spec` (the
    default) or `roadmap` — the two kinds whose lifecycle (exploring, proposed, approved,
    archived) is meant to be filled in by you and then gated by the operator. `title` is optional
    and only cosmetic — it shows in the operator's list before the rename lands, and does not
    affect the path.

    **Size it as a slice.** A request larger than one demonstrable outcome is written as a
    `roadmap` plus the first slice's change document, not as one large document. A slice is
    about a dozen requirements or fewer, as a few tasks; later slices are recorded in the
    roadmap as `slices`, not specified, and each is drafted once the one before it is
    approved.

    A roadmap carries `slices` and no requirements or tasks. Each slice's change document names it
    with `roadmap: {"document": <roadmap path>, "slice": <key>}`, and can be proposed only once
    the operator has approved the roadmap.

    Returns the minted `path` and the `phase` it starts in (`exploring`).
    """
    body: Dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if kind is not None:
        body["kind"] = kind
    return _hub_request("POST", "/spec/documents/create", body)


@_tool()
def submit_spec_document(
    path: str,
    title: str,
    kind: SpecKind,
    schema_version: int = SPEC_SCHEMA_VERSION,
    summary: str = "",
    problem: str = "",
    design: str = "",
    lifecycle: str = "",
    # Precise, so the advertised JSON schema says `object`/`array` for these seven fields.
    #
    # These carried `Any` between 2026-08-25 12:41 (`29ab883`) and this change, to route a wrong
    # shape past the framework's own validation and into `_check_submit_shapes`, which named the
    # field and showed a call that works — F35, measured at 718,650 input tokens across ten
    # retries of one malformed call. **The operator reversed that trade on 2026-08-25**, preferring
    # the schema, and the refusal machinery was removed with it rather than left in place
    # unreachable: the framework validates before this body runs, so with these annotations
    # restored nothing could ever have reached it. (F41, found the same day, is what that costs
    # when it is not noticed.)
    #
    # Reversing again means restoring `_check_submit_shapes` and `_SUBMIT_SHAPES` from `29ab883`
    # together with `Any` here — they only work as a pair. A way to keep both halves needs either a
    # fastmcp input-schema override (absent in 3.1.0: `Tool.from_function` takes `output_schema`
    # and no input equivalent) or `pydantic.Field`, which this module may not import.
    scope: Optional[Dict[str, Any]] = None,
    requirements: Optional[List[Dict[str, Any]]] = None,
    acceptance_criteria: Optional[List[Dict[str, Any]]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    algorithms: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    open_questions: Optional[List[Dict[str, Any]]] = None,
    delivery: Optional[Dict[str, Any]] = None,
    slices: Optional[List[Dict[str, Any]]] = None,
    roadmap: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write a specification document. You supply structure; the Hub renders the document.

    Never write specification HTML yourself — it will not be treated as a document. Submit the
    structure here and the Hub produces the markup, the anchors, and the identifiers.

    **Size it as a slice.** A request larger than one demonstrable outcome is written as a
    `roadmap` plus the first slice's change document, not as one large document. A slice is
    about a dozen requirements or fewer, as a few tasks; later slices are recorded in the
    roadmap as `slices`, not specified, and each is drafted once the one before it is
    approved.

    The document must already exist — call `create_spec_document` first if you don't have one yet.
    Submitting repeatedly is normal and expected — a document under discussion is incomplete, and
    saving an incomplete one is not an error. The response lists what still blocks it from being
    proposed.

    You cannot approve a document, propose it, or set its phase. There is no argument here that
    does so. Approval is the operator's decision and is taken elsewhere.

    At `sketch` rigor (the default) this writes the document immediately, as above. At `contract`
    or `gate` rigor it does not: your submission is diffed against what is stored and recorded as
    one pending proposal per changed requirement plus one for everything else, for an operator to
    accept or reject. The response then carries `proposals`/`unchanged`/`already_pending` instead
    of `identifiers`/`divergence` — check which shape came back rather than assuming a write
    happened. A unit you submit again unchanged is recorded once: it is named in `already_pending`,
    not proposed twice. A different edit to a unit replaces your earlier pending proposal for it,
    and a unit you put back as stored withdraws yours.

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
      `given`/`when`/`then`. One per behaviour, binary pass or fail. A requirement's criteria
      become the standard rendered into the implementer's and the reviewer's turn once a task
      satisfying it is materialised.

    `tasks` — objects with `key`, `description` (one concrete unit of work, not "build the whole
      thing"), `requirements` (keys this task satisfies; at least one, or it is work nobody
      asked for), and optionally `title`. Approving the document creates these as real tasks, and
      `title` is the name the board shows — a few words, not the sentence. Without one a name is
      derived from the description, which reads as prose because that is what it is. A task may
      also name sibling task keys in `depends_on`; it is not started until they are done. Tasks
      expected to edit the same file are chained with `depends_on`, so same-file tasks are built
      in order rather than in parallel. `files` optionally lists the repo-relative paths (never
      empty or absolute; a directory covers what is beneath it) a task expects to edit; two tasks
      with overlapping `files` and no `depends_on` path between them draw a `warnings` entry in
      the response, which never blocks a proposal. A test and its fix are one task: approval runs
      the project's checks, so a task whose work is a test left red for a later task can never
      pass them, and draws a `warnings` entry too.

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

    `delivery` — how the work gets built, for a change-spec document only. Either
      `{"mode": "flow", "agent": "<name>", "stop_when_queue_empties": true, "stop_at": None,
      "cron": "*/5 * * * *"}` (a flow: at least one of `stop_when_queue_empties`/`stop_at` must be
      set, `agent` is the default agent's name from the open roster, and `stop_at` is an ISO-8601
      timestamp carrying a timezone) or `{"mode": "none"}` (no flow: the tasks go on the board and
      are started by hand). **Include `delivery` in every later submission of this document**, not
      only the first one that answers it: a submission replaces the whole document, so one without
      it drops the answer and proposing is refused again.

    `slices` — a `roadmap` document's slices, in the order they are built: objects with `key`
      (lowercase, hyphenated, unique), `title`, `intent` (the outcome the operator could see
      working), `done` (a sentence: the outcome that shows it is finished, not whether it is
      finished yet) and `builds_after` (keys of earlier
      slices). Only on a roadmap, which carries no `requirements`, `acceptance_criteria` or
      `tasks` — those go in each slice's change document.

    `roadmap` — on a change document that specifies a roadmap slice:
      `{"document": "<roadmap path>", "slice": "<slice key>"}`. Proposing it is refused until that
      roadmap is approved and holds that slice. Include it in every later submission.

    Returns the path, the phase, the identifier assigned to each requirement key, `blocking` —
    what would refuse a proposal right now — and `ready_to_propose`, which is false while anything
    blocks. A saved document is not a ready one: say it is ready only when that field is true.
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
        "delivery": delivery,
        "slices": slices,
        "roadmap": roadmap,
    }
    # Before anything is sent. These are annotated `Any` so that a wrong shape reaches this check
    # rather than being refused by the framework's own validator, whose message was the finding
    # (F35) — the Hub still validates the contents server-side and remains the authority.
    for name, value in optional.items():
        if value is not None:
            document[name] = value

    return _hub_request("POST", "/spec/documents", {"path": path, "document": document})


@_tool()
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


@_tool()
def read_spec_document(
    path: str,
    include: Literal[
        "requirements",
        "outline",
        "full",
        "design",
        "tasks",
        "algorithms",
        "evidence",
        "lifecycle",
        "summary",
        "problem",
        "scope",
        "open_questions",
    ] = "requirements",
    identifiers: str = "",
) -> Dict[str, Any]:
    """Read the specification document you were told to implement.

    **Use this before writing code against a document.** The document lives in the project
    directory, not in your working copy, so you almost certainly cannot open it as a file. Working
    from a summary, or from another agent's description of it, is how an implementation quietly
    stops matching what was approved.

    Args:
        path: The document's path, as given in your turn context, or its id (`spdoc-…`).
        include: `requirements` (the default) returns the problem, scope and the requirements.
            `outline` returns each requirement's identifier, key, modal, statement and state only.
            `full` adds the design, declared tasks, algorithms and evidence sections where they
            fit. A section's name (`design`, `problem`, …) reads that one section on its own.
        identifiers: Comma-separated requirement identifiers (`FR-3,FR-7`) to read only those.
            A requirement with no identifier is named by its key.

    **A large read comes back as a file.** When the document is too large for one tool result, the
    Hub writes all of it, as wrapped text, into your own workspace and answers with `written_to`
    (for example `.agentweave/reads/spdoc-….requirements.md`), `requirement_identifiers` and
    `read_with`: open that file with your file-reading tool, a part at a time if it is long. Where
    there is no workspace to write into, the answer is bounded instead: `truncated: true`, the
    requirements left out in `remaining_identifiers`, sections left out in `omitted_sections`, and
    `continue_with`, which says the call to make next. A read by `identifiers` does not repeat the
    summary, problem, scope or open questions.

    Each requirement carries the `identifier` the Hub minted for it — `FR-1`, `FR-2` — along with
    its `statement`, its `modal` (MUST/SHOULD/MAY/SHALL) and its own `acceptance_criteria`. **Quote
    those identifiers**: they are what tasks, evidence and completion gates refer to, so naming them
    is how your work is traceable to what it satisfies.

    **This view is not the shape `submit_spec_document` takes.** To resubmit, put acceptance
    criteria in the top-level `acceptance_criteria` list, each naming its requirement's `key`, and
    leave out the Hub's `identifier`, `state` and `anchor` (F452).

    Also returns `phase` and `rigor`, which say how settled this document is. Readable at any phase
    — an unapproved document is still worth reading, and its phase tells you not to build on it yet.

    A `diagnostics` entry appears where the document and the Hub's index disagree, or where the
    document carries no structured content at all.
    """
    params = {"path": path, "include": include}
    if identifiers:
        # Sent only when given, so this tool works unchanged against a Hub that predates it (D5).
        params["identifiers"] = identifiers
    return _hub_request("GET", "/spec/documents", params=params)


@_tool()
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

    Recording the same requirement again in the same turn, on the same task, **revises** your
    undecided row rather than adding a second: the answer carries the same `id` and
    `revised: true`.

    Returns the evidence `id`, its `identifier`, its `review_state` and the `footprint` captured for
    it — the branch and commit your evidence has been attached to. Read it. If its
    `outside_workspace_writes` is a non-empty list, your turn wrote into a directory that footprint
    does not describe, so the tree your evidence names is missing part of your own work; say so in
    the summary while somebody can still act on it.
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


@_tool()
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


@_tool()
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

    **A decision waits for the run that recorded the evidence.** While that run is still running its
    commit is about to be replaced, so the Hub refuses with `recording_run_live` (HTTP 409). Decide
    after the run has ended; the Hub sends you a note in this conversation when it does.

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


def _announce_adapter_online() -> None:
    """Tell the Hub this harness actually started us, before serving anything.

    The Hub puts its canonical server on the runner's command line and, until this call existed,
    had no way to learn whether the harness did anything with it. A deployment that forbids MCP by
    policy takes the configuration and starts nothing — and the run was told, in its first line, to
    call tools that were not there. This process existing *is* the measurement, so it is made here
    rather than inferred from a later tool call: a model told to use HTTP may never reach for a
    tool, and evidence gathered that way would leave a permitted harness permanently undescribed.

    Best-effort in every direction. A Hub that is unreachable, a credential that is missing, a
    route that predates this call — none of them are reasons to refuse to serve. The cost of
    failing is that the *next* run reads the HTTP form, which works.
    """
    with contextlib.suppress(Exception):
        _hub_request("POST", "/mcp-adapter-online")


def main() -> None:
    """Run the canonical Hub-owned surface over stdio."""
    _announce_adapter_online()
    mcp.run(transport="stdio", show_banner=False)


# --- Call mode: `aw-tool <tool> [<args.json>]` (design D3, D4, D6, D7) ----------------------------

#: Exit codes by envelope kind. 64 and 70 are sysexits' EX_USAGE and EX_SOFTWARE.
_CALL_EXIT_CODES = {"rejected": 1, "unreachable": 2, "unbound": 2, "usage": 64, "internal": 70}

_CALL_HELP = (
    "aw-tool <tool> [<args-file>]  call one AgentWeave tool; <args-file> is a .json file inside "
    "this workspace's .agentweave/calls/ directory holding a JSON object of the tool's arguments. "
    "aw-tool --list  print the callable tools and their parameters. The run's credential is read "
    "from the environment; there is no option for it. The result is one JSON object, the last line "
    "of output."
)


class _CallUsageError(Exception):
    """The call itself is malformed; nothing was sent to the Hub."""


def _call_emit(payload: Dict[str, Any]) -> None:
    # `ensure_ascii` stays on (R3): PowerShell 5.1 decodes a native command's stdout with the
    # console code page, so escaped output is the only form identical in every shell.
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def _call_fail(kind: str, detail: str, **extra: Any) -> int:
    _call_emit({"ok": False, "error": {"kind": kind, "detail": detail, **extra}})
    return _CALL_EXIT_CODES[kind]


def _calls_root() -> Optional[str]:
    """`<realpath(AW_WORKSPACE_DIR)>/.agentweave/calls`, not resolved further: a link at either
    component must show up as a difference between this and its own realpath (design D8)."""
    workspace = os.environ.get("AW_WORKSPACE_DIR", "").strip()
    if not workspace:
        return None
    return os.path.join(os.path.realpath(workspace), ".agentweave", "calls")


def _decode_args_file(data: bytes) -> str:
    """D3's order: a BOM decides; else strict UTF-8; else, on Windows only, the ANSI code page --
    what a bare PowerShell 5.1 `Set-Content` writes (review fix 3); else a usage error."""
    try:
        if data.startswith(codecs.BOM_UTF8):
            return data[len(codecs.BOM_UTF8) :].decode("utf-8")
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return data.decode("utf-16")
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if os.name == "nt":
        with contextlib.suppress(UnicodeDecodeError, LookupError):
            return data.decode(locale.getencoding())
    raise _CallUsageError(
        "The arguments file could not be decoded as text. Write it with your file tool, or from "
        "PowerShell with exactly "
        "`Set-Content -Path '.agentweave/calls/<file>.json' -Value '<json>' -Encoding utf8`."
    )


def _read_call_args(arg: str) -> Dict[str, Any]:
    """The arguments file, read only from inside the calls directory (design D3, review fix 8).

    Resolved against this process's working directory, as the shell meant it. Refused when the
    workspace is unknown, when `.agentweave` or `calls` is a link or junction, when the file's real
    path is not inside the calls directory, or when it is not a `.json` file -- the same rule the
    approver applies, so both mean the same thing and a drifted `cd` fails closed.
    """
    root = _calls_root()
    where = (
        "The arguments file must be a .json file inside this workspace's .agentweave/calls/ "
        "directory, named by a relative path such as .agentweave/calls/1.json, from the "
        "workspace root."
    )
    if root is None:
        raise _CallUsageError(f"{where} AW_WORKSPACE_DIR is not set, so there is none.")
    try:
        normal_root = os.path.normcase(root)
        if os.path.normcase(os.path.realpath(root)) != normal_root:
            raise _CallUsageError(f"{where} .agentweave/calls is a link, not that directory.")
        real = os.path.realpath(os.path.abspath(arg))
        normal_real = os.path.normcase(real)
        inside = (
            normal_real != normal_root
            and os.path.commonpath([normal_real, normal_root]) == normal_root
        )
    except (OSError, ValueError) as exc:
        raise _CallUsageError(where) from exc
    if not inside or not normal_real.endswith(".json"):
        raise _CallUsageError(f"{where} {arg!r} is not.")
    try:
        with open(real, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise _CallUsageError(f"{where} {arg!r} could not be read: {exc.strerror}.") from exc
    try:
        parsed = json.loads(_decode_args_file(data))
    except ValueError as exc:
        raise _CallUsageError(f"The arguments file {arg!r} is not valid JSON: {exc}.") from exc
    if not isinstance(parsed, dict):
        raise _CallUsageError(f"The arguments file {arg!r} must hold a JSON object.")
    return parsed


def _call_parameters(fn: Callable[..., Any]) -> Tuple[List[str], List[str]]:
    params = inspect.signature(fn).parameters
    names = list(params)
    required = [name for name, p in params.items() if p.default is inspect.Parameter.empty]
    return names, required


def _call_listing() -> Dict[str, Any]:
    tools = []
    for name in sorted(_CALLABLE_TOOLS):
        fn = _CALLABLE_TOOLS[name]
        parameters, required = _call_parameters(fn)
        summary = (inspect.getdoc(fn) or "").split("\n", 1)[0]
        tools.append(
            {"name": name, "parameters": parameters, "required": required, "summary": summary}
        )
    return {"tools": tools}


def call_main(argv: List[str]) -> int:
    """Call one tool and print one envelope; return the exit code (design D3).

    Reads `AW_RUN_TOKEN`/`HUB_URL` from the environment only, never from argv or a file (D6), and
    never announces: an announce from here would record `connected` for a harness that refused the
    MCP server (D4). No exception escapes as a traceback.
    """
    try:
        if not argv:
            raise _CallUsageError(_CALL_HELP)
        if argv[0] in ("--help", "-h"):
            if len(argv) > 1:
                topic = argv[1]
                topic_fn = _CALLABLE_TOOLS.get(topic)
                if topic_fn is None:
                    raise _CallUsageError(
                        f"{topic!r} is not a callable tool; `aw-tool --list` names them."
                    )
                parameters, required = _call_parameters(topic_fn)
                _call_emit(
                    {
                        "ok": True,
                        "result": {
                            "name": topic,
                            "parameters": parameters,
                            "required": required,
                            "description": inspect.getdoc(topic_fn) or "",
                        },
                    }
                )
                return 0
            _call_emit({"ok": True, "result": {"usage": _CALL_HELP}})
            return 0
        if argv[0] == "--list":
            _call_emit({"ok": True, "result": _call_listing()})
            return 0
        name, rest = argv[0], argv[1:]
        if name.startswith("-") or any(arg.startswith("-") for arg in rest):
            raise _CallUsageError(
                "aw-tool takes no options besides --list and --help; the run's credential is read "
                f"from the environment. {_CALL_HELP}"
            )
        if len(rest) > 1:
            raise _CallUsageError(f"aw-tool takes one arguments file at most. {_CALL_HELP}")
        fn = _CALLABLE_TOOLS.get(name)
        if fn is None:
            raise _CallUsageError(f"{name!r} is not a callable tool; `aw-tool --list` names them.")
        args = _read_call_args(rest[0]) if rest else {}
        parameters, required = _call_parameters(fn)
        accepted = (
            f"{name} accepts {', '.join(parameters) or 'no arguments'}"
            f"{'; required: ' + ', '.join(required) if required else ''}."
        )
        unknown = sorted(set(args) - set(parameters))
        if unknown:
            raise _CallUsageError(f"Unknown argument(s) {', '.join(unknown)}. {accepted}")
        try:
            bound = inspect.signature(fn).bind(**args)
        except TypeError as exc:
            raise _CallUsageError(f"{exc}. {accepted}") from exc
    except _CallUsageError as exc:
        return _call_fail("usage", str(exc))
    try:
        result = fn(*bound.args, **bound.kwargs)
    except HubAPIError as exc:
        return _call_fail("rejected", exc.detail, status=exc.status_code, data=exc.data)
    except HubUnreachableError as exc:
        return _call_fail("unreachable", str(exc))
    except UnboundIdentityError as exc:
        return _call_fail("unbound", str(exc))
    except Exception as exc:  # noqa: BLE001 -- the envelope is the contract; no traceback leaks
        return _call_fail(
            "internal",
            f"{type(exc).__name__}: {exc}. The outcome is unknown: the Hub may have recorded "
            "this call. Check with `aw-tool list_tasks` or `aw-tool get_task` before retrying.",
        )
    _call_emit({"ok": True, "result": result})
    return 0


# MUST stay the last thing in this file. `mcp.run()` does not return, so anything defined below
# this guard is never reached when the server is spawned as a script — which is exactly how the
# Hub spawns it. `submit_spec_document` was added after this block and was therefore invisible to
# every agent while being perfectly visible to every test, because tests import the module and an
# import runs the whole file. An agent spent three rounds interviewing an operator, settled the
# scope, and reported the tool "not available in this session".
#
# `test_mcp_server_stdio_surface.py` spawns this file the way the Hub does and lists the tools over
# the wire, which is the only check that can see this class of mistake. Call mode (`--call`) is
# dispatched here too, for the same reason: `call_main` and every tool must be defined above.
if __name__ == "__main__":
    if _CALL_MODE:
        sys.exit(call_main(sys.argv[2:]))
    main()
