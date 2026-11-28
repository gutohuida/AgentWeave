"""Where each slice of a roadmap stands, what it cost, and which are offered for drafting
(`a-roadmap-that-is-recognisably-a-roadmap`, RTRR-2: FR-1..FR-6, FR-11).

**Derived on every read, never stored.** A slice is in exactly one state:

- `Not drafted` -- no change document names it;
- `Drafting` -- its document is exploring or proposed;
- `Approved` -- its document is approved and none of its tasks has started;
- `Building` -- a build of its document is running, or a task has started and is not on main;
- `Built` -- its document has at least one task and every one is approved and on the main branch
  (`landing_queue.unlanded` is the one rule of "on main"; a task closed as already built has no
  landing to wait for, so it counts).

**The one offer rule** (FR-4, FR-5): a slice is offered for drafting when it is Not drafted, every
slice it builds after is Built, and its offer was neither taken nor declined. Overview's offers
(`slice_drafting.list_offers`) and the roadmap's own read both come from `roadmap_view`, so they
cannot disagree.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, spec_lifecycle, spec_reading, spec_service
from .db.models import Build, SpecDocument, SpecDocumentEvent, Task, TaskLanding

NOT_DRAFTED = "Not drafted"
DRAFTING = "Drafting"
APPROVED = "Approved"
BUILDING = "Building"
BUILT = "Built"

#: Events that answer an offer of a slice: taken (a turn queued) or declined. Recorded on the
#: roadmap document, naming the slice in `detail.next_slice`.
QUEUED = "next_slice_queued"
DECLINED = "next_slice_declined"

#: A task that has not begun: waiting for somebody, or not yet picked up.
_NOT_STARTED = ("pending", "assigned")

#: How far a slice's change document has come; where several name one slice, the furthest wins.
_PHASE_RANK = {
    spec_lifecycle.EXPLORING: 1,
    spec_lifecycle.PROPOSED: 2,
    spec_lifecycle.APPROVED: 3,
    spec_lifecycle.ARCHIVED: 4,
}


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


async def change_specs(
    session: AsyncSession, workspace, project_id: str
) -> Tuple[List[SpecDocument], Dict[str, Optional[Dict[str, Any]]]]:
    """The project's change documents and their payloads: read once and handed to every roadmap
    view of one request (`_claimed_documents`), so the files are not read again per roadmap."""
    rows = list(
        (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.project_id == project_id,
                    SpecDocument.kind == "change-spec",
                )
            )
        )
        .scalars()
        .all()
    )
    payloads = (
        await spec_reading.payloads_for_documents(session, workspace, [r.id for r in rows])
        if rows
        else {}
    )
    return rows, payloads


async def _claimed_documents(
    session: AsyncSession, workspace, roadmap: SpecDocument, shared=None
) -> Dict[str, SpecDocument]:
    """`{slice key: the furthest change document naming it}` for *roadmap*."""
    rows, payloads = shared or await change_specs(session, workspace, roadmap.project_id)
    if not rows:
        return {}
    claimed: Dict[str, SpecDocument] = {}
    for row in sorted(rows, key=lambda r: (r.created_at, r.id)):
        link = (payloads.get(row.id) or {}).get("roadmap")
        if (
            not isinstance(link, dict)
            or link.get("document") != roadmap.path
            or not link.get("slice")
        ):
            continue
        key = str(link["slice"])
        current = claimed.get(key)
        if current is None or _PHASE_RANK.get(row.phase, 0) > _PHASE_RANK.get(current.phase, 0):
            claimed[key] = row
    return claimed


async def _answered_by(
    session: AsyncSession,
    claimed_by: Dict[str, Dict[str, SpecDocument]],
    roadmaps: List[SpecDocument],
) -> Dict[str, set[str]]:
    """`{roadmap id: slice keys whose offer was taken or declined}`, on the roadmap or (before the
    offer moved to the roadmap) on the change document it was made from. One read for all."""
    owner: Dict[str, str] = {}
    for roadmap in roadmaps:
        owner[roadmap.id] = roadmap.id
        for doc in claimed_by[roadmap.id].values():
            owner[doc.id] = roadmap.id
    answered: Dict[str, set[str]] = {r.id: set() for r in roadmaps}
    if not owner:
        return answered
    rows = await session.execute(
        select(SpecDocumentEvent.document_id, SpecDocumentEvent.detail).where(
            SpecDocumentEvent.document_id.in_(list(owner)),
            SpecDocumentEvent.kind.in_((QUEUED, DECLINED)),
        )
    )
    for document_id, detail in rows.all():
        if isinstance(detail, dict) and detail.get("next_slice"):
            answered[owner[document_id]].add(str(detail["next_slice"]))
    return answered


async def _facts(session: AsyncSession, documents: List[SpecDocument]) -> Dict[str, Dict[str, Any]]:
    """`{document id: figures}` for *documents*: tasks, landing, cost, dates. Each figure is read
    once for all the documents, so the statement count does not grow with the slices."""
    from . import builds, landing_queue

    ids = [d.id for d in documents]
    if not ids:
        return {}
    tasks_of: Dict[str, List[Task]] = {i: [] for i in ids}
    for task in (
        (
            await session.execute(
                select(Task)
                .where(Task.spec_document_id.in_(ids))
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    ):
        tasks_of[task.spec_document_id].append(task)
    unlanded = await landing_queue.unlanded(session, Task.spec_document_id.in_(ids))
    builds_of: Dict[str, List[Build]] = {i: [] for i in ids}
    for build in (
        (
            await session.execute(
                select(Build).where(Build.document_id.in_(ids)).order_by(Build.created_at)
            )
        )
        .scalars()
        .all()
    ):
        builds_of[build.document_id].append(build)
    spent_by = await builds.spends(session, [b for rows in builds_of.values() for b in rows])
    on_main_of = {
        i: [t for t in tasks_of[i] if t.status == "approved" and t.id not in unlanded] for i in ids
    }
    landed_ids = [t.id for rows in on_main_of.values() for t in rows]
    landed_when: Dict[str, Any] = {}
    if landed_ids:
        landed_when = dict(
            (
                await session.execute(
                    select(TaskLanding.task_id, func.max(TaskLanding.updated_at))
                    .where(TaskLanding.task_id.in_(landed_ids), TaskLanding.state == "landed")
                    .group_by(TaskLanding.task_id)
                )
            ).all()
        )
    found: Dict[str, Dict[str, Any]] = {}
    for document_id in ids:
        tasks, on_main, built_rows = (
            tasks_of[document_id],
            on_main_of[document_id],
            builds_of[document_id],
        )
        started = [t for t in tasks if t.status not in _NOT_STARTED]
        micros = sum(spent_by[b.id][0] for b in built_rows)
        unpriced = sum(spent_by[b.id][1] for b in built_rows)
        landed_at = None
        if on_main:
            landed_at = max(
                (landed_when[t.id] for t in on_main if landed_when.get(t.id)), default=None
            ) or max((t.updated for t in on_main if t.updated), default=None)
        first_start = (
            built_rows[0].created_at
            if built_rows
            else (min((t.created_at for t in started), default=None))
        )
        found[document_id] = {
            "tasks": tasks,
            "tasks_total": len(tasks),
            "tasks_on_main": len(on_main),
            "started_off_main": any(t.id not in {o.id for o in on_main} for t in started),
            "build_running": any(b.state == "running" for b in built_rows),
            "cost_usd": round(micros / 1_000_000, 4),
            "unpriced_turns": unpriced,
            "has_cost": bool(built_rows),
            "built_at": _iso(landed_at),
            "started_at": _iso(first_start),
        }
    return found


def _state(document: Optional[SpecDocument], facts: Optional[Dict[str, Any]]) -> str:
    if document is None or facts is None:
        return NOT_DRAFTED
    if (
        facts["tasks_total"]
        and facts["tasks_on_main"] == facts["tasks_total"]
        and not (facts["build_running"])
    ):
        return BUILT
    if document.phase in (spec_lifecycle.EXPLORING, spec_lifecycle.PROPOSED):
        return DRAFTING
    if document.phase == spec_lifecycle.ARCHIVED and not facts["tasks_total"]:
        return NOT_DRAFTED
    if facts["build_running"] or facts["started_off_main"]:
        return BUILDING
    return APPROVED


def _order_warning(key: str, after: List[str], order: List[str]) -> Optional[str]:
    """A slice listed ahead of one it builds after (RTRR-3, FR-7): allowed, and said so."""
    mine = order.index(key)
    later = [k for k in after if k in order and order.index(k) > mine]
    if not later:
        return None
    return "Builds after " + ", ".join(later) + ", which comes later in the roadmap"


async def _retrospectives(
    session: AsyncSession, documents: List[SpecDocument]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """`{document id: the newest written build retrospective as a link, or None}`; one read."""
    from . import build_retrospective

    if not documents:
        return {}
    firings = await build_retrospective.list_for_documents(
        session, documents[0].project_id, [d.id for d in documents]
    )
    found: Dict[str, Optional[Dict[str, Any]]] = {}
    for document in documents:
        found[document.id] = next(
            (
                {
                    "document": document.path,
                    "at": firing.get("at"),
                    "vault_source": firing.get("vault_source"),
                }
                for firing in firings.get(document.id, [])
                if firing.get("outcome") == "written"
            ),
            None,
        )
    return found


class Ahead:
    """What the views of several roadmaps need from the database, read once for all of them."""

    def __init__(self, claimed, answered, facts, retros):
        self.claimed: Dict[str, Dict[str, SpecDocument]] = claimed
        self.answered: Dict[str, set[str]] = answered
        self.facts: Dict[str, Dict[str, Any]] = facts
        self.retros: Dict[str, Optional[Dict[str, Any]]] = retros


async def ahead(
    session: AsyncSession, workspace, roadmaps: List[SpecDocument], shared=None
) -> Ahead:
    """Read, for every roadmap in *roadmaps*, the claims, answers, figures and retrospectives its
    view needs: the statement count does not grow with the roadmaps."""
    if not roadmaps:
        return Ahead({}, {}, {}, {})
    shared = shared or await change_specs(session, workspace, roadmaps[0].project_id)
    claimed = {r.id: await _claimed_documents(session, workspace, r, shared) for r in roadmaps}
    answered = await _answered_by(session, claimed, roadmaps)
    documents = list({d.id: d for by_key in claimed.values() for d in by_key.values()}.values())
    facts = await _facts(session, documents)
    built = [d for d in documents if _state(d, facts[d.id]) == BUILT]
    return Ahead(claimed, answered, facts, await _retrospectives(session, built))


async def roadmap_view(
    session: AsyncSession, workspace, roadmap: SpecDocument, shared=None, prefetched=None
) -> Dict[str, Any]:
    """`{slices, progress}` of *roadmap*: the figures its page shows and the offers both Overview
    and the page make."""
    return (await view_with_documents(session, workspace, roadmap, shared, prefetched))[0]


async def view_with_documents(
    session: AsyncSession, workspace, roadmap: SpecDocument, shared=None, prefetched=None
) -> Tuple[Dict[str, Any], Dict[str, SpecDocument], Dict[str, Dict[str, Any]]]:
    """`roadmap_view` with the change document and the figures behind each slice, by slice key."""
    stored = await blocking.run(spec_service.roadmap_slices, workspace, roadmap.path)
    ready = prefetched or await ahead(session, workspace, [roadmap], shared)
    claimed = ready.claimed[roadmap.id]
    answered = ready.answered[roadmap.id]
    facts = {key: ready.facts[doc.id] for key, doc in claimed.items()}
    states = {
        str(item["key"]): _state(claimed.get(str(item["key"])), facts.get(str(item["key"])))
        for item in stored
    }
    order = [str(item["key"]) for item in stored]
    slices: List[Dict[str, Any]] = []
    micros = unpriced = 0
    for item in stored:
        key = str(item["key"])
        document, fact, state = claimed.get(key), facts.get(key), states[key]
        after = [str(k) for k in item.get("builds_after") or []]
        waits = [k for k in after if states.get(k) != BUILT] if state == NOT_DRAFTED else []
        row: Dict[str, Any] = {
            "key": key,
            "title": item.get("title"),
            "intent": item.get("intent"),
            "done": item.get("done"),
            "builds_after": after,
            "state": state,
            "document": document.path if document is not None else None,
            "document_title": document.title if document is not None else None,
            "tasks_on_main": fact["tasks_on_main"] if fact else 0,
            "tasks_total": fact["tasks_total"] if fact else 0,
            "cost_usd": fact["cost_usd"] if fact and fact["has_cost"] else None,
            "unpriced_turns": fact["unpriced_turns"] if fact else 0,
            "built_at": fact["built_at"] if fact and state == BUILT else None,
            "started_at": fact["started_at"] if fact else None,
            "waits_for": waits,
            "offers_drafting": state == NOT_DRAFTED and not waits and key not in answered,
            "retrospective": (
                ready.retros.get(document.id) if state == BUILT and document is not None else None
            ),
            "warning": _order_warning(key, after, order),
            "added_after_approval": bool(item.get("added_after_approval")),
            "added_by": item.get("added_by"),
        }
        if fact:
            micros += round(fact["cost_usd"] * 1_000_000)
            unpriced += fact["unpriced_turns"]
        slices.append(row)
    view = {
        "slices": slices,
        "progress": {
            "built": sum(1 for s in slices if s["state"] == BUILT),
            "total": len(slices),
            "cost_usd": round(micros / 1_000_000, 4),
            "unpriced_turns": unpriced,
        },
    }
    return view, claimed, facts
