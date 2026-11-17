"""A roadmap's slice is offered for drafting by one rule, and drafted only when the operator takes
the offer (`a-roadmap-that-is-recognisably-a-roadmap`, RTRR-2; before it
`amendments-main-watch-and-the-next-slice` D6, F496, F501, F1047).

**An offer is derived, never stored.** Every Not drafted slice whose builds-after slices are all
Built is offered, unless its offer was taken or declined (`slice_progress.roadmap_view`: Overview's
list here and the roadmap's own read are the same rule). Answers (`next_slice_queued`,
`next_slice_declined`) are events on the roadmap, naming the slice. When a task's closing or
landing makes a slice offered, the operator is notified once (`next_slice_offered`). **Nothing is
queued then.**

Taking the offer (`take_offer`) queues one drafting turn, as the operator, to the agent the operator
chooses (by default the roadmap's author), carrying the roadmap, the slice, each prior slice's
document, tasks' outcomes (F501) and a link to its retrospective, or the fact that none has been
written. It goes in the conversation where the roadmap was written while that is still open and the
chosen agent is its author; otherwise in a new one named for the slice (F1047). A second take
queues nothing. Declining (`decline_offer`) hides the offer in every view.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import slice_progress, spec_documents, spec_lifecycle, spec_service
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


async def _roadmap_of(
    session: AsyncSession, workspace, document: SpecDocument
) -> Optional[tuple[SpecDocument, str]]:
    """The roadmap row and slice key a change document names, or None."""
    from . import blocking

    if document.kind != "change-spec":
        return None
    payload = await blocking.run(spec_documents.read_payload, workspace, document.path) or {}
    link = payload.get("roadmap")
    if not isinstance(link, dict) or not link.get("document") or not link.get("slice"):
        return None
    roadmap = await spec_lifecycle.get_document(session, document.project_id, str(link["document"]))
    if roadmap is None or roadmap.kind != "roadmap":
        return None
    return roadmap, str(link["slice"])


async def _document_at(session: AsyncSession, project_id: str, path: Optional[str]):
    if not path:
        return None
    return await session.scalar(
        select(SpecDocument).where(SpecDocument.project_id == project_id, SpecDocument.path == path)
    )


async def _offer(
    session: AsyncSession, roadmap: SpecDocument, row: Dict[str, Any], view: Dict[str, Any]
) -> Dict[str, Any]:
    """The offer for the slice *row* of *roadmap*: what the operator is asked, and who is asked."""
    by_key = {s["key"]: s for s in view["slices"]}
    prior = [by_key[k] for k in row["builds_after"] if k in by_key]
    last = prior[-1] if prior else None
    last_doc = await _document_at(session, roadmap.project_id, last["document"] if last else None)
    agent, conversation_id = await _author_and_conversation(session, roadmap, [])
    task_ids: List[str] = []
    for item in prior:
        doc = await _document_at(session, roadmap.project_id, item["document"])
        if doc is not None:
            task_ids.extend(t.id for t in await _tasks(session, doc.id))
    return {
        "document": last["document"] if last else None,
        "document_id": last_doc.id if last_doc is not None else None,
        "title": last["document_title"] if last else None,
        "roadmap": roadmap.path,
        "roadmap_title": roadmap.title,
        "approved_slice": {k: last.get(k) for k in ("key", "title")} if last else None,
        "next_slice": {k: row.get(k) for k in ("key", "title", "intent", "done")},
        "built_slices": [
            {
                k: item.get(k)
                for k in (
                    "key",
                    "title",
                    "document",
                    "tasks_on_main",
                    "tasks_total",
                    "retrospective",
                )
            }
            for item in prior
        ],
        "agent": agent,
        "conversation_id": conversation_id,
        "requested": False,
        "tasks": task_ids,
    }


async def offers_of(
    session: AsyncSession, workspace, roadmap: SpecDocument
) -> List[Dict[str, Any]]:
    """Every slice of *roadmap* offered for drafting now (`slice_progress`: the one rule)."""
    view = await slice_progress.roadmap_view(session, workspace, roadmap)
    return [await _offer(session, roadmap, r, view) for r in view["slices"] if r["offers_drafting"]]


async def offer_for_slice(
    session: AsyncSession, workspace, roadmap: SpecDocument, key: str
) -> Optional[Dict[str, Any]]:
    return next(
        (o for o in await offers_of(session, workspace, roadmap) if o["next_slice"]["key"] == key),
        None,
    )


async def resolve(
    session: AsyncSession, workspace, document: SpecDocument, slice_key: Optional[str]
) -> tuple[SpecDocument, str]:
    """The roadmap and slice a take or decline names: a roadmap with *slice_key*, or a change
    document (the slice that follows its own, unless *slice_key* says). Raises `OfferRefused`."""
    from . import blocking

    if document.kind == "roadmap":
        if not slice_key:
            raise OfferRefused("name the slice to answer: a roadmap offers several", 422)
        return document, slice_key
    found = await _roadmap_of(session, workspace, document)
    if found is None:
        raise OfferRefused(f"{document.path} names no roadmap slice, so it offers no next slice")
    roadmap, key = found
    if slice_key:
        return roadmap, slice_key
    slices = await blocking.run(spec_service.roadmap_slices, workspace, roadmap.path)
    keys = [str(item["key"]) for item in slices]
    if key not in keys or keys.index(key) + 1 >= len(keys):
        raise OfferRefused(f"{document.path} offers no next slice to draft")
    return roadmap, keys[keys.index(key) + 1]


async def list_offers(session: AsyncSession, workspace, project_id: str) -> List[Dict[str, Any]]:
    """Every offer in the project, oldest roadmap first."""
    roadmaps = (
        (
            await session.execute(
                select(SpecDocument)
                .where(
                    SpecDocument.project_id == project_id,
                    SpecDocument.kind == "roadmap",
                    SpecDocument.phase == spec_lifecycle.APPROVED,
                )
                .order_by(SpecDocument.created_at, SpecDocument.id)
            )
        )
        .scalars()
        .all()
    )
    offers: List[Dict[str, Any]] = []
    for roadmap in roadmaps:
        offers.extend(await offers_of(session, workspace, roadmap))
    return offers


async def _notify(session: AsyncSession, roadmap: SpecDocument, workspace) -> None:
    """Tell the operator once about each slice now offered on *roadmap*."""
    from .utils import persist_event

    offers = await offers_of(session, workspace, roadmap)
    if not offers:
        return
    told = {
        str((e.detail or {}).get("next_slice"))
        for e in await _events(session, roadmap.id)
        if e.kind == OFFERED
    }
    for offer in offers:
        key = offer["next_slice"]["key"]
        if key in told:
            continue
        await spec_lifecycle.record_event(
            session,
            roadmap,
            kind=OFFERED,
            actor=spec_lifecycle.Actor(kind="system"),
            detail={"next_slice": key, "tasks": offer["tasks"]},
        )
        await persist_event(
            session, roadmap.project_id, OFFER_EVENT, offer, agent=None, commit=False
        )
        defer_broadcast(session, roadmap.project_id, OFFER_EVENT, offer)


async def on_task_closed(session: AsyncSession, task: Task) -> None:
    """Notify the operator if *task* closing makes a slice offered. Queues nothing.

    Called by `apply_transition` inside the caller's transaction."""
    if task.status not in TERMINAL_STATUSES or not task.spec_document_id:
        return
    await notify_for_document(session, task.spec_document_id)


async def notify_for_document(session: AsyncSession, document_id: str) -> None:
    """Notify for the roadmap *document_id*'s slice belongs to. Runs in a savepoint and never
    raises: a task's approval is a judgement about the task, and this is not grounds to undo it."""
    from .project_workspace import resolve_project_workspace

    try:
        async with session.begin_nested():
            document = await session.get(SpecDocument, document_id)
            if document is None:
                return
            workspace = await resolve_project_workspace(session, document.project_id)
            found = await _roadmap_of(session, workspace, document)
            if found is not None:
                await _notify(session, found[0], workspace)
    except Exception:  # noqa: BLE001 -- never fail the transition
        logger.warning("could not offer slices after %s moved", document_id, exc_info=True)


async def take_offer(
    session: AsyncSession,
    workspace,
    roadmap: SpecDocument,
    slice_key: str,
    *,
    agent: Optional[str],
) -> Dict[str, Any]:
    """Queue the drafting turn the offer for *slice_key* stands for, to *agent* (the roadmap's
    author by default). Returns the offer with the entry queued; the caller commits and then
    schedules the agent. Raises `OfferRefused`: no offer (already taken, declined, claimed, or a
    slice it builds after is not built), no agent to ask, or an agent that is not open."""
    from .builds import open_agents

    offer = await offer_for_slice(session, workspace, roadmap, slice_key)
    if offer is None:
        raise OfferRefused(
            f"{roadmap.path} offers no drafting of slice {slice_key!r}: it is claimed, waits on a "
            "slice that is not built, or the offer was taken or declined"
        )
    chosen = (agent or "").strip() or offer["agent"]
    if not chosen:
        raise OfferRefused(
            "this roadmap has no agent author to ask; choose the agent that drafts the slice", 422
        )
    if chosen not in await open_agents(session, roadmap.project_id):
        raise OfferRefused(f"{chosen} is not an open agent of this project", 422)
    tasks = await _tasks_by_id(session, offer["tasks"])
    content = next_slice_message(offer, tasks=tasks, outcomes=await _task_outcomes(session, tasks))
    conversation_id = offer["conversation_id"] if chosen == offer["agent"] else None
    if (
        conversation_id is None
        or await get_open_conversation(
            session, project_id=roadmap.project_id, agent=chosen, conversation_id=conversation_id
        )
        is None
    ):
        # F1047: the conversation the roadmap was written in is archived (or is not the chosen
        # agent's): the turn opens a conversation of its own, named for the slice.
        conversation = new_conversation(
            project_id=roadmap.project_id, agent=chosen, origin="operator"
        )
        name_conversation(
            conversation, f"Draft {offer['next_slice'].get('title') or 'the next slice'}"
        )
        session.add(conversation)
        conversation_id = conversation.id
    entry = new_entry(
        project_id=roadmap.project_id,
        agent=chosen,
        origin_type="operator",
        content=content,
        hop_depth=0,
        conversation_id=conversation_id,
        spec_document=roadmap.path,
    )
    session.add(entry)
    await spec_lifecycle.record_event(
        session,
        roadmap,
        kind=QUEUED,
        actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        detail={"next_slice": slice_key, "agent": chosen, "tasks": [t.id for t in tasks]},
    )
    defer_broadcast(
        session, roadmap.project_id, ANSWERED_EVENT, {"document": roadmap.path, "taken": True}
    )
    return {**offer, "agent": chosen, "conversation_id": conversation_id, "entry_id": entry.id}


async def decline_offer(
    session: AsyncSession, workspace, roadmap: SpecDocument, slice_key: str
) -> Dict[str, Any]:
    """Hide the offer for that slice (`next_slice_declined`). The caller commits."""
    offer = await offer_for_slice(session, workspace, roadmap, slice_key)
    if offer is None:
        raise OfferRefused(f"{roadmap.path} offers no drafting of slice {slice_key!r} to decline")
    await spec_lifecycle.record_event(
        session,
        roadmap,
        kind=DECLINED,
        actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        detail={"next_slice": slice_key},
    )
    defer_broadcast(
        session, roadmap.project_id, ANSWERED_EVENT, {"document": roadmap.path, "taken": False}
    )
    return offer


async def _tasks_by_id(session: AsyncSession, ids: List[str]) -> List[Task]:
    if not ids:
        return []
    return list(
        (
            await session.execute(
                select(Task).where(Task.id.in_(ids)).order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )


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
    tasks: List[Task],
    outcomes: Optional[Dict[str, List[str]]] = None,
) -> str:
    """The fixed Hub text of the drafting turn: the roadmap, the slice, what the slices it builds
    after produced (F501: each task's outcomes) and where their retrospectives are."""
    roadmap_path = detail["roadmap"]
    following = detail.get("next_slice") or {}
    link = f'{{"document": "{roadmap_path}", "slice": "{following.get("key")}"}}'
    lines = [
        f"The operator has asked you to draft slice `{following.get('key')}` "
        f"({following.get('title') or ''}) of the roadmap {detail.get('roadmap_title')!r} "
        f"(`{roadmap_path}`).",
        f"- Intent: {following.get('intent') or '(not stated)'}",
        f"- Done when: {following.get('done') or '(not stated)'}",
    ]
    prior = detail.get("built_slices") or []
    lines.append(
        "The slices it builds after are built. Their outcomes:"
        if prior
        else "It builds after no other slice."
    )
    for item in prior:
        lines.append(
            f"- Slice `{item.get('key')}` ({item.get('title') or ''}), specified by "
            f"`{item.get('document')}`: {item.get('tasks_on_main')} of {item.get('tasks_total')} "
            "tasks on the main branch."
        )
        retro = item.get("retrospective")
        if retro:
            lines.append(
                f"  - Retrospective: written{' ' + str(retro['at']) if retro.get('at') else ''}; "
                f"read it on `{retro['document']}`."
            )
        else:
            lines.append("  - Retrospective: none has been written yet.")
    for task in tasks:
        lines.append(f"- `{task.display_id}` {task.title}: {task.status}")
        lines.extend(f"  - {line}" for line in (outcomes or {}).get(task.id, []))
    lines += [
        "Before drafting, read the roadmap with `read_spec_document`, and read those tasks with "
        "`get_task` and `list_evidence`. Work that did not reach the main branch is not done, "
        "whatever its status says, and a rejection's reason is something this slice must not "
        "repeat: what building those slices taught you belongs in this one.",
        "Then create a change document with `create_spec_document` and submit it with "
        f"`roadmap: {link}`. Keep it to about a dozen requirements or fewer, as a few tasks. Do "
        "not implement anything.",
    ]
    return "\n".join(lines)
