"""The next slice of a roadmap is offered once a slice is built, and drafted only when the operator
takes the offer (`amendments-main-watch-and-the-next-slice`, task `next-slice-offer`, design D6;
before it C1a D4/D4a and F496, F501, F1047).

**An offer is derived, never stored.** A change document that specifies a roadmap slice is offered
when no task linked to it is open, the roadmap's following slice is claimed by no document, and no
`next_slice_queued` or `next_slice_declined` event answers it. Only an approved document with at
least one task is offered, or one carrying a `next_slice_requested` event from before this change
(the approval-time request it replaces): that unanswered request shows as an offer by the same rule,
with no data migration. Approval no longer accepts a request to draft the next slice.

When the last open task closes (`on_task_closed`, inside the transition's transaction) and that
makes the document offered, the operator is notified once (`next_slice_offered`, an event on the
document so a reopen and rebuild does not notify twice for the same slice, and a persisted,
broadcast Hub event for the app). **Nothing is queued then.**

Taking the offer (`take_offer`) queues one drafting turn, as the operator, to the agent the operator
chooses (by default the document's author: the first agent that wrote its content before approval),
carrying each task's outcome (F501). It goes in the conversation where the document was written
while that is still open and the chosen agent is its author; otherwise in a new conversation named
for the next slice (F1047: input queued into an archived conversation is never delivered). The
`next_slice_queued` event it records answers the offer, so a second take queues nothing. Declining
(`decline_offer`) records `next_slice_declined` and hides the offer for that slice.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_lifecycle, spec_service
from .conversations import get_open_conversation, name_conversation, new_conversation
from .db.models import Run, SpecDocument, SpecDocumentEvent, Task
from .inbound_queue import new_entry
from .sse import defer_broadcast
from .task_transitions import TERMINAL_STATUSES

logger = logging.getLogger(__name__)

REQUESTED = "next_slice_requested"
QUEUED = "next_slice_queued"
DECLINED = "next_slice_declined"
OFFERED = "next_slice_offered"
_KINDS = (REQUESTED, QUEUED, DECLINED, OFFERED)

#: The Hub event (persisted and broadcast) that notifies the operator of a new offer.
OFFER_EVENT = "next_slice_offered"
#: Broadcast when an offer is taken or declined, so every view drops it.
ANSWERED_EVENT = "next_slice_answered"

#: Why approval refuses `draft_next_slice` (D6): the request is the offer now.
REQUEST_RETIRED = (
    "draft_next_slice is retired: approval no longer asks for the next slice. When this slice's "
    "last task closes, drafting its roadmap's next slice is offered on the Overview and on this "
    "document; take the offer there (POST /project/documents/next-slice/take?path=...), choosing "
    "the agent"
)

#: Strong references to the scheduling tasks an `after_commit` listener starts, so none is
#: collected before it runs.
_in_flight: Set["asyncio.Task[Any]"] = set()


class OfferRefused(Exception):  # noqa: N818 -- "refused" is the outcome, not a fault
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _events(session: AsyncSession, document_id: str) -> List[SpecDocumentEvent]:
    return list(
        (
            await session.execute(
                select(SpecDocumentEvent)
                .where(
                    SpecDocumentEvent.document_id == document_id,
                    SpecDocumentEvent.kind.in_(_KINDS),
                )
                .order_by(SpecDocumentEvent.created_at, SpecDocumentEvent.id)
            )
        )
        .scalars()
        .all()
    )


async def _tasks(session: AsyncSession, document_id: str) -> List[Task]:
    return list(
        (
            await session.execute(
                select(Task)
                .where(Task.spec_document_id == document_id)
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )


async def _author_and_conversation(
    session: AsyncSession, document: SpecDocument, requests: List[SpecDocumentEvent]
) -> tuple[Optional[str], Optional[str]]:
    """The agent the drafting turn goes to by default, and the conversation it wrote the document
    in. A pre-change request names both; otherwise the first agent that wrote its content before
    approval, else the agent that created it."""
    from . import spec_amendments

    if requests:
        detail = requests[-1].detail or {}
        if detail.get("agent"):
            return str(detail["agent"]), (
                str(detail["conversation_id"]) if detail.get("conversation_id") else None
            )
    authors = await spec_amendments.authors(session, document)
    rows = (
        (
            await session.execute(
                select(SpecDocumentEvent)
                .where(
                    SpecDocumentEvent.document_id == document.id,
                    SpecDocumentEvent.kind.in_(("created", "content")),
                    SpecDocumentEvent.actor_kind == "agent",
                )
                .order_by(SpecDocumentEvent.created_at, SpecDocumentEvent.id)
            )
        )
        .scalars()
        .all()
    )
    agent = (
        authors[0]
        if authors
        else next((e.actor for e in rows if e.kind == "created" and e.actor), None)
    )
    if not agent:
        return None, None
    for row in rows:
        if row.actor == agent and row.run_id:
            run = await session.get(Run, row.run_id)
            if run is not None and run.conversation_id:
                return agent, run.conversation_id
    return agent, None


async def offer_for(
    session: AsyncSession,
    workspace,
    document: SpecDocument,
    *,
    claims: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """The offer *document* makes now, or None (D6: derived from the record)."""
    if document.kind != "change-spec":
        return None
    payload = spec_documents.read_payload(workspace, document.path) or {}
    link = payload.get("roadmap")
    if not isinstance(link, dict) or not link.get("document") or not link.get("slice"):
        return None
    events = await _events(session, document.id)
    requests = [e for e in events if e.kind == REQUESTED]
    tasks = await _tasks(session, document.id)
    if any(t.status not in TERMINAL_STATUSES for t in tasks):
        return None
    if not requests and not (document.phase == spec_lifecycle.APPROVED and tasks):
        return None
    roadmap_path, approved_key = str(link["document"]), str(link["slice"])
    slices = spec_service.roadmap_slices(workspace, roadmap_path)
    keys = [str(item["key"]) for item in slices]
    if approved_key not in keys or keys.index(approved_key) + 1 >= len(keys):
        return None
    approved_slice, following = (
        slices[keys.index(approved_key)],
        slices[keys.index(approved_key) + 1],
    )
    next_key = str(following["key"])
    for e in events:
        if e.kind in (QUEUED, DECLINED) and (e.detail or {}).get("next_slice") in (None, next_key):
            return None
    if claims is None:
        claims = await spec_service.slice_claims(session, workspace, document.project_id)
    if next_key in claims.get(roadmap_path, {}):
        return None
    agent, conversation_id = await _author_and_conversation(session, document, requests)
    roadmap_row = await spec_lifecycle.get_document(session, document.project_id, roadmap_path)
    return {
        "document": document.path,
        "document_id": document.id,
        "title": document.title,
        "roadmap": roadmap_path,
        "roadmap_title": roadmap_row.title if roadmap_row is not None else roadmap_path,
        "approved_slice": {k: approved_slice.get(k) for k in ("key", "title")},
        "next_slice": {k: following.get(k) for k in ("key", "title", "intent", "done")},
        "agent": agent,
        "conversation_id": conversation_id,
        "requested": bool(requests),
        "tasks": [t.id for t in tasks],
    }


async def list_offers(session: AsyncSession, workspace, project_id: str) -> List[Dict[str, Any]]:
    """Every offer in the project, oldest document first."""
    requested = select(SpecDocumentEvent.document_id).where(
        SpecDocumentEvent.project_id == project_id, SpecDocumentEvent.kind == REQUESTED
    )
    rows = (
        (
            await session.execute(
                select(SpecDocument)
                .where(
                    SpecDocument.project_id == project_id,
                    SpecDocument.kind == "change-spec",
                    (SpecDocument.phase == spec_lifecycle.APPROVED)
                    | SpecDocument.id.in_(requested),
                )
                .order_by(SpecDocument.created_at, SpecDocument.id)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    claims = await spec_service.slice_claims(session, workspace, project_id)
    offers = []
    for row in rows:
        offer = await offer_for(session, workspace, row, claims=claims)
        if offer is not None:
            offers.append(offer)
    return offers


async def on_task_closed(session: AsyncSession, task: Task) -> None:
    """Notify the operator if *task* closing makes its slice document offered. Queues nothing.

    Called by `apply_transition` inside the caller's transaction. Runs in a savepoint and never
    raises: a task's approval is a judgement about the task, and this is not grounds to undo it.
    """
    from .project_workspace import resolve_project_workspace

    if task.status not in TERMINAL_STATUSES or not task.spec_document_id:
        return
    try:
        async with session.begin_nested():
            document = await session.get(SpecDocument, task.spec_document_id)
            if document is None:
                return
            workspace = await resolve_project_workspace(session, document.project_id)
            offer = await offer_for(session, workspace, document)
            if offer is None:
                return
            key = offer["next_slice"]["key"]
            events = await _events(session, document.id)
            if any(e.kind == OFFERED and (e.detail or {}).get("next_slice") == key for e in events):
                return
            await spec_lifecycle.record_event(
                session,
                document,
                kind=OFFERED,
                actor=spec_lifecycle.Actor(kind="system"),
                detail={"next_slice": key, "tasks": offer["tasks"]},
            )
            from .utils import persist_event

            await persist_event(
                session, document.project_id, OFFER_EVENT, offer, agent=None, commit=False
            )
            defer_broadcast(session, document.project_id, OFFER_EVENT, offer)
    except Exception:  # noqa: BLE001 -- never fail the transition
        logger.warning("could not offer the next slice after %s closed", task.id, exc_info=True)


async def take_offer(
    session: AsyncSession,
    workspace,
    document: SpecDocument,
    *,
    agent: Optional[str],
) -> Dict[str, Any]:
    """Queue the drafting turn the offer stands for, to *agent* (the offer's author by default).
    Returns the offer with the entry queued; the caller commits and then schedules the agent.
    Raises `OfferRefused`: no offer (already taken, declined, claimed, or the slice not built),
    no agent to ask, or an agent that is not open."""
    from .builds import open_agents

    offer = await offer_for(session, workspace, document)
    if offer is None:
        raise OfferRefused(
            f"{document.path} offers no next slice to draft: it is not a built roadmap slice, its "
            "next slice is already claimed, or the offer was taken or declined"
        )
    chosen = (agent or "").strip() or offer["agent"]
    if not chosen:
        raise OfferRefused(
            "this slice has no agent author to ask; choose the agent that drafts the next slice",
            422,
        )
    if chosen not in await open_agents(session, document.project_id):
        raise OfferRefused(f"{chosen} is not an open agent of this project", 422)
    tasks = await _tasks(session, document.id)
    content = next_slice_message(
        offer,
        approved_path=document.path,
        tasks=tasks,
        outcomes=await _task_outcomes(session, tasks),
    )
    conversation_id = offer["conversation_id"] if chosen == offer["agent"] else None
    if (
        conversation_id is None
        or await get_open_conversation(
            session, project_id=document.project_id, agent=chosen, conversation_id=conversation_id
        )
        is None
    ):
        # F1047: the conversation the slice was written in is archived (or is not the chosen
        # agent's): the turn opens a conversation of its own, named for the next slice.
        conversation = new_conversation(
            project_id=document.project_id, agent=chosen, origin="operator"
        )
        name_conversation(
            conversation, f"Draft {offer['next_slice'].get('title') or 'the next slice'}"
        )
        session.add(conversation)
        conversation_id = conversation.id
    entry = new_entry(
        project_id=document.project_id,
        agent=chosen,
        origin_type="operator",
        content=content,
        hop_depth=0,
        conversation_id=conversation_id,
        spec_document=offer["roadmap"],
    )
    session.add(entry)
    events = await _events(session, document.id)
    request = next((e for e in reversed(events) if e.kind == REQUESTED), None)
    await spec_lifecycle.record_event(
        session,
        document,
        kind=QUEUED,
        actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        detail={
            "next_slice": offer["next_slice"]["key"],
            "agent": chosen,
            "tasks": [t.id for t in tasks],
            "request": request.id if request is not None else None,
        },
    )
    defer_broadcast(
        session, document.project_id, ANSWERED_EVENT, {"document": document.path, "taken": True}
    )
    return {**offer, "agent": chosen, "conversation_id": conversation_id, "entry_id": entry.id}


async def decline_offer(session: AsyncSession, workspace, document: SpecDocument) -> Dict[str, Any]:
    """Hide the offer for that slice (`next_slice_declined`). The caller commits."""
    offer = await offer_for(session, workspace, document)
    if offer is None:
        raise OfferRefused(f"{document.path} offers no next slice to decline")
    await spec_lifecycle.record_event(
        session,
        document,
        kind=DECLINED,
        actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        detail={"next_slice": offer["next_slice"]["key"]},
    )
    defer_broadcast(
        session, document.project_id, ANSWERED_EVENT, {"document": document.path, "taken": False}
    )
    return offer


async def _task_outcomes(session: AsyncSession, tasks: List[Task]) -> Dict[str, List[str]]:
    """Per task, the lines saying what reached main and what the operator rejected (F501).

    Carried in the turn rather than left to `list_evidence`: the real drafting run read only the
    task statuses, and `approved` said nothing about work that never merged or evidence rejected
    twice before a later approval.
    """
    from .db.models import EvidenceReview, RequirementEvidence, SpecRequirement, TaskIntegration

    ids = [t.id for t in tasks]
    if not ids:
        return {}
    lines: Dict[str, List[str]] = {task_id: [] for task_id in ids}
    integrations = (
        (
            await session.execute(
                select(TaskIntegration)
                .where(TaskIntegration.task_id.in_(ids))
                .order_by(TaskIntegration.created_at)
            )
        )
        .scalars()
        .all()
    )
    latest = {row.task_id: row for row in integrations}
    for task_id in ids:
        row = latest.get(task_id)
        if row is None:
            lines[task_id].append("no merge into the main branch is recorded")
        elif row.outcome == "merged":
            lines[task_id].append(f"merged into {row.target_branch or 'the main branch'}")
        else:
            lines[task_id].append(f"not merged ({row.outcome}): {row.reason}")
    rejected = await session.execute(
        select(RequirementEvidence.id, RequirementEvidence.task_id, SpecRequirement.identifier)
        .join(SpecRequirement, SpecRequirement.id == RequirementEvidence.requirement_id)
        .where(RequirementEvidence.task_id.in_(ids), RequirementEvidence.review_state == "rejected")
        .order_by(RequirementEvidence.produced_at)
    )
    for evidence_id, task_id, identifier in rejected.all():
        reason = await session.scalar(
            select(EvidenceReview.reason)
            .where(EvidenceReview.evidence_id == evidence_id, EvidenceReview.decision == "rejected")
            .order_by(EvidenceReview.sequence.desc())
            .limit(1)
        )
        lines[task_id].append(f"{identifier} evidence rejected: {reason or '(no reason given)'}")
    return lines


def next_slice_message(
    detail: Dict[str, Any],
    *,
    approved_path: str,
    tasks: List[Task],
    outcomes: Optional[Dict[str, List[str]]] = None,
) -> str:
    """The fixed Hub text of the drafting turn (C1a D4, D4a; F501 adds each task's outcomes)."""
    roadmap_path = detail["roadmap"]
    approved = detail.get("approved_slice") or {}
    following = detail.get("next_slice") or {}
    link = f'{{"document": "{roadmap_path}", "slice": "{following.get("key")}"}}'
    task_lines: List[str] = []
    for t in tasks:
        task_lines.append(f"- `{t.id}` {t.title}: {t.status}")
        task_lines.extend(f"  - {line}" for line in (outcomes or {}).get(t.id, []))
    lines = [
        f"Slice `{approved.get('key')}` ({approved.get('title') or ''}) of the roadmap "
        f"{detail.get('roadmap_title')!r} (`{roadmap_path}`), specified by `{approved_path}`, is "
        "built: none of its tasks is still open. The operator has asked you to draft the next slice "
        "now.",
        "Its tasks and how they ended:",
        *(task_lines or ["- none: no task was linked to it"]),
        f"The next slice is `{following.get('key')}`: {following.get('title') or ''}.",
        f"- Intent: {following.get('intent') or '(not stated)'}",
        f"- Done when: {following.get('done') or '(not stated)'}",
        "Before drafting, read the roadmap with `read_spec_document`, and read those tasks with "
        "`get_task` and `list_evidence`. Work that did not reach the main branch is not done, "
        "whatever its status says, and a rejection's reason is something the next slice must not "
        "repeat: what building that slice taught you belongs in this one.",
        "Then create a change document with `create_spec_document` and submit it with "
        f"`roadmap: {link}`. Keep it to about a dozen requirements or fewer, as a few tasks. Do "
        "not implement anything.",
    ]
    return "\n".join(lines)
