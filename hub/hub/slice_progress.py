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
from typing import Any, Dict, List, Optional

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


async def _claimed_documents(
    session: AsyncSession, workspace, roadmap: SpecDocument
) -> Dict[str, SpecDocument]:
    """`{slice key: the furthest change document naming it}` for *roadmap*."""
    rows = list(
        (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.project_id == roadmap.project_id,
                    SpecDocument.kind == "change-spec",
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {}
    payloads = await spec_reading.payloads_for_documents(session, workspace, [r.id for r in rows])
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


async def _answered(
    session: AsyncSession, roadmap: SpecDocument, document_ids: List[str]
) -> set[str]:
    """Slice keys whose offer was taken or declined, on the roadmap or (before the offer moved to
    the roadmap) on the change document it was made from."""
    rows = await session.execute(
        select(SpecDocumentEvent.detail).where(
            SpecDocumentEvent.document_id.in_([roadmap.id, *document_ids]),
            SpecDocumentEvent.kind.in_((QUEUED, DECLINED)),
        )
    )
    return {
        str(d["next_slice"]) for (d,) in rows.all() if isinstance(d, dict) and d.get("next_slice")
    }


async def _facts(session: AsyncSession, document: SpecDocument) -> Dict[str, Any]:
    """The state-independent figures of one slice document: tasks, landing, cost, dates."""
    from . import builds, landing_queue

    tasks = list(
        (
            await session.execute(
                select(Task)
                .where(Task.spec_document_id == document.id)
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    unlanded = await landing_queue.unlanded(session, Task.spec_document_id == document.id)
    on_main = [t for t in tasks if t.status == "approved" and t.id not in unlanded]
    started = [t for t in tasks if t.status not in _NOT_STARTED]
    built_rows = list(
        (
            await session.execute(
                select(Build).where(Build.document_id == document.id).order_by(Build.created_at)
            )
        )
        .scalars()
        .all()
    )
    micros = unpriced = 0
    for build in built_rows:
        spent, missing = await builds.spend(session, build)
        micros += spent
        unpriced += missing
    landed_at = None
    if on_main:
        landed_at = await session.scalar(
            select(func.max(TaskLanding.updated_at)).where(
                TaskLanding.task_id.in_([t.id for t in on_main]), TaskLanding.state == "landed"
            )
        ) or max((t.updated for t in on_main if t.updated), default=None)
    first_start = (
        built_rows[0].created_at
        if built_rows
        else (min((t.created_at for t in started), default=None))
    )
    return {
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


async def _retrospective(session: AsyncSession, document: SpecDocument) -> Optional[Dict[str, Any]]:
    """The newest written build retrospective of *document*, as a link, or None."""
    from . import build_retrospective

    for firing in await build_retrospective.list_for_document(
        session, document.project_id, document.id
    ):
        if firing.get("outcome") == "written":
            return {
                "document": document.path,
                "at": firing.get("at"),
                "vault_source": firing.get("vault_source"),
            }
    return None


async def roadmap_view(session: AsyncSession, workspace, roadmap: SpecDocument) -> Dict[str, Any]:
    """`{slices, progress}` of *roadmap*: the figures its page shows and the offers both Overview
    and the page make."""
    stored = await blocking.run(spec_service.roadmap_slices, workspace, roadmap.path)
    claimed = await _claimed_documents(session, workspace, roadmap)
    answered = await _answered(session, roadmap, [d.id for d in claimed.values()])
    facts = {key: await _facts(session, doc) for key, doc in claimed.items()}
    states = {
        str(item["key"]): _state(claimed.get(str(item["key"])), facts.get(str(item["key"])))
        for item in stored
    }
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
                await _retrospective(session, document)
                if state == BUILT and document is not None
                else None
            ),
            "warning": item.get("warning"),
            "added_after_approval": bool(item.get("added_after_approval")),
            "added_by": item.get("added_by"),
        }
        if fact:
            micros += round(fact["cost_usd"] * 1_000_000)
            unpriced += fact["unpriced_turns"]
        slices.append(row)
    return {
        "slices": slices,
        "progress": {
            "built": sum(1 for s in slices if s["state"] == BUILT),
            "total": len(slices),
            "cost_usd": round(micros / 1_000_000, 4),
            "unpriced_turns": unpriced,
        },
    }
