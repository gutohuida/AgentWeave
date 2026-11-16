"""Changing an approved roadmap's slices (`a-roadmap-that-is-recognisably-a-roadmap`, RTRR-3:
FR-7, FR-8, FR-9).

An approved roadmap refuses submissions, and approvals are scarce: an order change or a removal is
the operator's own act, applied at once with no re-approval and recorded as a document event naming
them. A slice is *added* only by an agent, in a conversation the operator opened with it
(`start_conversation`), through `spec_amendments` (`add_slice`); there is no route that takes a
slice from a hand-filled form.

Which slices may be touched is the slice's state (`slice_progress`), derived on every call:

- moved: Not drafted or Drafting; never Approved, Building or Built;
- removed: Not drafted and named by no change document (archived ones included) -- the refusal
  names that document.

A move that puts a slice ahead of one it builds after is allowed; the roadmap's read carries a
warning on it (`slice_progress.roadmap_view`, derived from the order, not stored).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_identity, spec_lifecycle, spec_service
from .db.models import SpecDocument
from .spec_payload import PayloadError, validate_payload

MOVED_EVENT = "slice_moved"
REMOVED_EVENT = "slice_removed"
ADDED_EVENT = "slice_added"
CONVERSATION_EVENT = "slice_conversation_started"

#: The states a slice may be moved from.
MOVABLE = ("Not drafted", "Drafting")


class SliceEditRefused(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """An edit that may not happen. `status` is the HTTP answer the route gives."""

    def __init__(self, message: str, *, code: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


def _approved_roadmap(document: SpecDocument) -> None:
    if document.kind != "roadmap":
        raise SliceEditRefused(
            f"{document.path} is not a roadmap", code="not_a_roadmap", status=422
        )
    if document.phase != spec_lifecycle.APPROVED:
        raise SliceEditRefused(
            f"{document.path} is {document.phase}; its slices are edited directly until it is "
            "approved",
            code="roadmap_not_approved",
        )


async def _write(
    session: AsyncSession,
    workspace: Any,
    document: SpecDocument,
    mutate,
    *,
    actor: spec_lifecycle.Actor,
    extra_detail: Dict[str, Any],
):
    """Read the roadmap's stored payload, apply `mutate` to a copy, validate and write it."""
    content = spec_documents.read_document(workspace, document.path)
    stored = spec_documents.parse_stored(content)
    if not isinstance(stored, dict):
        raise SliceEditRefused(
            "this roadmap has no readable payload", code="payload_unreadable", status=409
        )
    current = {k: v for k, v in stored.items() if k != spec_identity.IDENTITY_FIELD}
    new_payload = mutate(dict(current))
    try:
        payload = validate_payload(new_payload)
    except PayloadError as exc:
        raise SliceEditRefused(str(exc), code="payload_invalid", status=422) from exc
    await spec_service._apply_and_write(
        session,
        workspace,
        document,
        payload,
        stored,
        content,
        actor=actor,
        extra_detail=extra_detail,
    )


def _slices(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [dict(s) for s in payload.get("slices") or [] if isinstance(s, dict)]


async def move_slice(
    session: AsyncSession,
    workspace: Any,
    roadmap: SpecDocument,
    slice_key: str,
    position: int,
    *,
    actor: spec_lifecycle.Actor,
) -> Dict[str, Any]:
    """Move a slice to the 1-based `position`. The caller commits."""
    from . import slice_progress

    _approved_roadmap(roadmap)
    view = await slice_progress.roadmap_view(session, workspace, roadmap)
    keys = [s["key"] for s in view["slices"]]
    row = next((s for s in view["slices"] if s["key"] == slice_key), None)
    if row is None:
        raise SliceEditRefused(
            f"{roadmap.path} has no slice {slice_key!r}", code="unknown_slice", status=404
        )
    if not 1 <= position <= len(keys):
        raise SliceEditRefused(
            f"position must be from 1 to {len(keys)}", code="position_out_of_range", status=422
        )
    if row["state"] not in MOVABLE:
        raise SliceEditRefused(
            f"slice {slice_key!r} is {row['state']}; only a slice that is Not drafted or Drafting "
            "is moved",
            code="slice_not_movable",
        )
    before = keys.index(slice_key) + 1
    if before == position:
        return {"moved": False, "slice": slice_key, "from": before, "to": position}

    def mutate(payload: Dict[str, Any]) -> Dict[str, Any]:
        items = _slices(payload)
        item = items.pop(before - 1)
        items.insert(position - 1, item)
        payload["slices"] = items
        return payload

    await _write(
        session,
        workspace,
        roadmap,
        mutate,
        actor=actor,
        extra_detail={"slice_edit": MOVED_EVENT, "slice": slice_key},
    )
    await spec_lifecycle.record_event(
        session,
        roadmap,
        kind=MOVED_EVENT,
        actor=actor,
        detail={"slice": slice_key, "from": before, "to": position},
    )
    return {"moved": True, "slice": slice_key, "from": before, "to": position}


async def remove_slice(
    session: AsyncSession,
    workspace: Any,
    roadmap: SpecDocument,
    slice_key: str,
    *,
    actor: spec_lifecycle.Actor,
) -> Dict[str, Any]:
    """Remove a Not drafted slice no document names. The caller commits."""
    from . import slice_progress

    _approved_roadmap(roadmap)
    view = await slice_progress.roadmap_view(session, workspace, roadmap)
    row = next((s for s in view["slices"] if s["key"] == slice_key), None)
    if row is None:
        raise SliceEditRefused(
            f"{roadmap.path} has no slice {slice_key!r}", code="unknown_slice", status=404
        )
    claimed = await slice_progress._claimed_documents(session, workspace, roadmap)
    named = claimed.get(slice_key)
    if named is not None:
        raise SliceEditRefused(
            f"slice {slice_key!r} is named by {named.path}; a slice a document names is not removed",
            code="slice_named_by_document",
        )
    if row["state"] != slice_progress.NOT_DRAFTED:
        raise SliceEditRefused(
            f"slice {slice_key!r} is {row['state']}; only a slice that is Not drafted is removed",
            code="slice_not_removable",
        )
    dropped = [s["key"] for s in view["slices"] if slice_key in (s["builds_after"] or [])]

    def mutate(payload: Dict[str, Any]) -> Dict[str, Any]:
        items = [s for s in _slices(payload) if s.get("key") != slice_key]
        for item in items:
            if slice_key in (item.get("builds_after") or []):
                item["builds_after"] = [k for k in item["builds_after"] if k != slice_key]
        payload["slices"] = items
        questions = []
        for question in payload.get("open_questions") or []:
            if isinstance(question, dict) and question.get("slice") == slice_key:
                question = {k: v for k, v in question.items() if k != "slice"}
            questions.append(question)
        if payload.get("open_questions"):
            payload["open_questions"] = questions
        return payload

    await _write(
        session,
        workspace,
        roadmap,
        mutate,
        actor=actor,
        extra_detail={"slice_edit": REMOVED_EVENT, "slice": slice_key},
    )
    await spec_lifecycle.record_event(
        session,
        roadmap,
        kind=REMOVED_EVENT,
        actor=actor,
        detail={"slice": slice_key, "title": row["title"], "dropped_from_builds_after": dropped},
    )
    return {"removed": True, "slice": slice_key, "dropped_from_builds_after": dropped}


def add_slice_to_payload(
    payload: Dict[str, Any], change: Optional[Dict[str, Any]], *, added_by: str
) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    """`payload` with one slice added: (new payload, the slice's key, detail). Pure.

    `change` is `{title, intent?, done?, builds_after?, key?, position?}`; the key is derived from
    the title when left out, the position is 1-based and defaults to the end.
    """
    import re

    from .spec_amendments import AmendmentRefused, _text

    if not isinstance(change, dict):
        raise AmendmentRefused(
            "add_slice needs the slice under change", code="amendment_invalid", field="change"
        )
    title = _text(change.get("title"), "change.title")
    key = change.get("key")
    if not (isinstance(key, str) and key.strip()):
        key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64].strip("-") or "slice"
    key = key.strip()
    items = _slices(payload)
    if any(s.get("key") == key for s in items):
        raise AmendmentRefused(
            f"this roadmap already has a slice {key!r}", code="duplicate_key", field="change.key"
        )
    after = change.get("builds_after") or []
    keys = {s.get("key") for s in items}
    if not isinstance(after, list) or any(k not in keys for k in after):
        raise AmendmentRefused(
            "builds_after names only slices the roadmap holds",
            code="amendment_invalid",
            field="change.builds_after",
        )
    position = change.get("position")
    if position is None:
        position = len(items) + 1
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or not (1 <= position <= len(items) + 1)
    ):
        raise AmendmentRefused(
            f"position must be from 1 to {len(items) + 1}",
            code="amendment_invalid",
            field="change.position",
        )
    entry = {
        "key": key,
        "title": title,
        "intent": _text(change.get("intent"), "change.intent", required=False),
        "done": _text(change.get("done"), "change.done", required=False),
        "builds_after": list(after),
        "added_after_approval": True,
        "added_by": added_by,
    }
    items.insert(position - 1, entry)
    new = dict(payload)
    new["slices"] = items
    return new, key, {"change": {**entry, "position": position}}


def seed_message(roadmap: SpecDocument, slices: List[Dict[str, Any]]) -> str:
    """What the conversation opens with: the roadmap and how an added slice is recorded."""
    lines = [
        f"The operator wants to add a slice to the approved roadmap {roadmap.title!r} "
        f"({roadmap.path}). Work out with them what the slice delivers, then add it with "
        "`amend_spec_document`:",
        "",
        f'  path="{roadmap.path}", op="add_slice", reason=<why it is needed>,',
        '  change={"title", "intent", "done", "builds_after": [<slice keys>], "position": <1-based>}',
        "",
        "Add one slice. It shows on the roadmap at once, marked as added after approval with your "
        "name, and waits among the roadmap's amendments for the operator to review.",
        "",
        "The roadmap's slices now:",
    ]
    for number, item in enumerate(slices, start=1):
        after = ", ".join(item.get("builds_after") or []) or "nothing"
        lines.append(
            f"{number}. {item['key']} -- {item.get('title')} [{item.get('state')}]; "
            f"builds after {after}. {item.get('intent') or ''}".rstrip()
        )
    return "\n".join(lines)


async def start_conversation(
    session: AsyncSession,
    workspace: Any,
    roadmap: SpecDocument,
    *,
    agent: Optional[str],
) -> Dict[str, Any]:
    """Open a conversation with `agent` (default: the roadmap's author) seeded with the roadmap.
    The caller commits, then schedules the agent. No slice is written here."""
    from . import slice_progress, spec_amendments
    from .builds import open_agents
    from .conversations import name_conversation, new_conversation
    from .inbound_queue import new_entry

    _approved_roadmap(roadmap)
    chosen = (agent or "").strip()
    if not chosen:
        writers = await spec_amendments.authors(session, roadmap)
        chosen = writers[0] if writers else ""
    if not chosen:
        raise SliceEditRefused(
            "this roadmap has no agent author to ask; choose the agent that works the slice out "
            "with the operator",
            code="no_agent",
            status=422,
        )
    if chosen not in await open_agents(session, roadmap.project_id):
        raise SliceEditRefused(
            f"{chosen} is not an open agent of this project", code="agent_not_open", status=422
        )
    view = await slice_progress.roadmap_view(session, workspace, roadmap)
    conversation = new_conversation(project_id=roadmap.project_id, agent=chosen, origin="operator")
    name_conversation(conversation, f"Add a slice to {roadmap.title}")
    session.add(conversation)
    entry = new_entry(
        project_id=roadmap.project_id,
        agent=chosen,
        origin_type="operator",
        content=seed_message(roadmap, view["slices"]),
        hop_depth=0,
        conversation_id=conversation.id,
        spec_document=roadmap.path,
    )
    session.add(entry)
    await spec_lifecycle.record_event(
        session,
        roadmap,
        kind=CONVERSATION_EVENT,
        actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        detail={"agent": chosen, "conversation_id": conversation.id},
    )
    return {"agent": chosen, "conversation_id": conversation.id, "entry_id": entry.id}


async def asked_agents(session: AsyncSession, roadmap: SpecDocument) -> List[str]:
    """The agents the operator opened a slice conversation with."""
    from sqlalchemy import select

    from .db.models import SpecDocumentEvent

    rows = await session.execute(
        select(SpecDocumentEvent.detail).where(
            SpecDocumentEvent.document_id == roadmap.id,
            SpecDocumentEvent.kind == CONVERSATION_EVENT,
        )
    )
    return [str(d["agent"]) for (d,) in rows.all() if isinstance(d, dict) and d.get("agent")]
