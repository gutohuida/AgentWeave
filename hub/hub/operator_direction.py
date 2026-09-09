"""Operator direction for actions the contract requires it for, whichever adapter asked.

`2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, §3.1-§3.3. Archiving scheduled work
always puts that exact request to the operator, regardless of the run's permission posture. Until
this module the rule lived in `mcp_server.archive_job` alone — so an agent reaching the same effect
over HTTP was governed by the standing `allow_agent_jobs` allowance and nothing else, and the answer
to "must a person direct this?" depended on which adapter the agent came through. The delta states
it the other way round: *a rule that governs one adapter's callers governs the contract's callers.*

**The mechanism, and why this one** (`design.md` D5 left it open). Two were offered: the route blocks
on the operator's answer, or it returns a typed failure carrying a request id the caller polls. This
is the second, for three reasons that are about this codebase rather than about taste.

1. `/permission-requests` already works this way (`api/v1/agent_actions.py`, `open_permission_request`
   / `poll_permission_request` / `expire_permission_request`), and the MCP adapter's `_ask_operator`
   is already a poll loop over exactly those routes. Choosing the same shape means one protocol on
   the plane rather than two, and it means the operator's card, its SSE event and its UI are the
   ones already shipped — nothing new to build on the human's side.
2. A blocking route would hold an `AsyncSession`, and therefore a pooled connection, for up to the
   whole operator budget (120s by default). On SQLite that pool is small, and F295 is a finding
   about what happens to it. A wait measured in minutes does not belong inside a request handler.
3. The waiting is then the *caller's*, which is the point: an HTTP agent performs the same protocol
   the injected tool performs on an MCP agent's behalf, from the same description
   (`api/v1/agents.py`, the operation's `http_note`). The rule is the Hub's either way.

**What is a rule and what is protocol.** The rule — direction is required for this job, now,
whatever the run's posture, and a standing allowance does not supply it — is here. The polling is
protocol, and a caller doing it in a helper is not a caller holding the rule: it cannot skip the
gate, because the gate is the route's and the route refuses without an `allowed` row.

**Posture cannot reach this.** The run's permission posture is an environment variable of the
spawned process (`AW_PERMISSION_POSTURE`, written at `api/v1/agent_trigger.py`); nothing carries it
back to the Hub, and no column holds it. So "regardless of posture" is not a check here — it is the
absence of one, and `test_agent_actions_governed.py` pins it against the most permissive posture an
agent can be given.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conversations import conversation_id_for_run
from .db.models import PermissionRequest
from .sse import sse_manager
from .utils import short_id

logger = logging.getLogger(__name__)

# The machine-readable code on a refusal that is not a refusal: nothing is wrong with the request,
# and repeating it once the operator has answered is the intended next move.
DIRECTION_REQUIRED = "operator_direction_required"

# Where a caller polls the request this module opened. Stated absolutely, because the caller reading
# it is an agent composing a URL and not a router mounting one.
POLL_PREFIX = "/api/v1/agent-actions/permission-requests"


async def require_operator_direction(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    run_id: Optional[str],
    tool_name: str,
    tool_use_id: str,
    tool_input: Dict[str, Any],
    action: str,
) -> None:
    """Return only if the operator has directed *this* action; otherwise refuse and say how.

    `action` is the phrase that names what was asked for, e.g. "archiving this job", and appears in
    every message this raises.

    The states, and what each one means to a caller:

    * **no request yet** — one is opened, the operator is told, and this raises `409` carrying its
      id. `409` rather than `403`: nothing has been denied, and the state that blocks the request is
      one the operator can change. A `403` would tell an agent it had been refused, and the
      difference between "not yet" and "no" is the whole content of the operator's answer.
    * **pending** — the same id is returned again. A second card is *not* opened: a caller that
      polls the effect rather than the request must not multiply the human's work.
    * **allowed** — returns, and the action proceeds.
    * **denied** — `403`, naming the refusal as the operator's.
    * **expired** — nobody answered. A fresh request is opened and `409` raised, because an agent
      re-asking after silence is asking for the first time as far as the operator is concerned; it
      is what the MCP adapter has always done (every `archive_job` call opened its own card).

    **An `allowed` row is not consumed**, and does not need to be: it is scoped to one project, one
    run, and one `tool_use_id` naming the exact job, and the only action it unlocks refuses a second
    time with *"job is already archived"*. There is no route that un-archives a job — checked across
    `hub/hub/api/` — so a replayed allowance cannot produce a second archive.
    """
    row = (
        await session.execute(
            select(PermissionRequest)
            .where(
                PermissionRequest.project_id == project_id,
                PermissionRequest.agent == agent,
                PermissionRequest.run_id == run_id,
                PermissionRequest.tool_use_id == tool_use_id,
            )
            .order_by(PermissionRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is not None and row.status == "allowed":
        return
    if row is not None and row.status == "denied":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "operator_refused",
                "message": (
                    f"the operator refused {action}. Nothing was changed, and this is an answer "
                    "rather than a timeout: do not ask again for the same thing."
                ),
                "permission_request_id": row.id,
            },
        )
    if row is not None and row.status == "pending":
        raise _direction_required(row.id, action)

    request_id = await _open_request(
        session,
        project_id=project_id,
        agent=agent,
        run_id=run_id,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        tool_input=tool_input,
    )
    raise _direction_required(request_id, action)


def _direction_required(request_id: str, action: str) -> HTTPException:
    """The typed failure a caller acts on: what is needed, where to watch for it, what to do then.

    `message` is what `mcp_server._readable_detail` surfaces from a dict detail, so an agent that
    only ever sees the sentence still sees the whole protocol. The id is carried separately as well
    so a client does not have to parse it out of prose.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": DIRECTION_REQUIRED,
            "message": (
                f"{action} needs the operator's explicit direction for this exact request, "
                "whatever this run's permission posture is, and a standing allowance to manage "
                f"scheduled work does not supply it. Nothing was changed. The request is now in "
                f"front of the operator as {request_id}: poll "
                f"`GET {POLL_PREFIX}/{request_id}` until its status leaves `pending`, then repeat "
                "this request if it is `allowed`."
            ),
            "permission_request_id": request_id,
            "poll": f"{POLL_PREFIX}/{request_id}",
        },
    )


async def _open_request(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    run_id: Optional[str],
    tool_name: str,
    tool_use_id: str,
    tool_input: Dict[str, Any],
) -> str:
    """Put one request in front of the operator and tell the UI it is there.

    Deliberately the same row, the same `pending` status and the same `permission_requested` event
    as `open_permission_request` — the operator's card is the shipped one, and a second kind of
    pending decision would be a second thing for them to learn.
    """
    request_id = f"perm-{short_id()}"
    session.add(
        PermissionRequest(
            id=request_id,
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=await conversation_id_for_run(session, run_id),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            tool_input=tool_input,
            status="pending",
        )
    )
    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "permission_requested",
        {"id": request_id, "agent": agent, "tool_name": tool_name, "run_id": run_id},
    )
    return request_id
