"""A change names the capabilities it changes (`a-change-names-the-capabilities-it-changes`).

The link is content: a change document's `capabilities` field, `{"changes": [<capability path>],
"creates": [{"title"}]}` (D1). Nothing here stores a reverse index (D2): each capability's waiting
list is computed on read from the changes' stored payloads, and `spec_document_merges` says which
changes are already folded.

What this module answers:

- `named(stored)` -- the link a stored payload carries, normalised.
- `require_known(...)` -- every named path is a current capability of the same project, or the
  save is refused `capability_unknown`, naming the path.
- `set_link(...)` -- change the link without touching anything else, so an approved document stays
  approved with the same requirement digests (D3). Refused `change_folded` after a fold.
- `waiting_lists(...)` -- every capability's open changes, in the stated total order (FR-5).
- `folded_into(...)` -- the capability a change was folded into, from its merge rows (FR-8).
- `default_fold_target(...)` -- the capability a fold starts from (FR-7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_lifecycle
from .db.models import SpecDocument, SpecDocumentMerge, Task
from .project_workspace import ProjectWorkspace

FIELD = "capabilities"

CAPABILITY_UNKNOWN = "capability_unknown"
CAPABILITY_UNNAMED = "capability_unnamed"
CAPABILITY_AMBIGUOUS = "capability_ambiguous"
CHANGE_FOLDED = "change_folded"
CHANGE_ARCHIVED = "change_archived"
FOLD_TARGET_NOT_NAMED = "fold_target_not_named"

#: The event a change to the link records on the change's history.
LINK_EVENT = "capabilities_link"


class LinkRefusedError(Exception):
    """A link the Hub will not store, with its code and the status a route answers."""

    def __init__(self, message: str, *, code: str, status: int = 422, field: str = FIELD):
        super().__init__(message)
        self.code = code
        self.status = status
        self.field = field


def named(stored: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """`{"changes": [path], "creates": [{"title"}]}` from a stored payload, or None when it names
    none. Entries that are not what the field holds are left out rather than guessed at."""
    link = (stored or {}).get(FIELD)
    if not isinstance(link, dict):
        return None
    changes = [p.strip() for p in link.get("changes") or [] if isinstance(p, str) and p.strip()]
    creates = [
        {"title": c["title"].strip()}
        for c in link.get("creates") or []
        if isinstance(c, dict) and isinstance(c.get("title"), str) and c["title"].strip()
    ]
    if not changes and not creates:
        return None
    return {"changes": changes, "creates": creates}


def names_title(link: Optional[Dict[str, Any]], title: str) -> bool:
    folded = (title or "").strip().casefold()
    return any(c["title"].casefold() == folded for c in (link or {}).get("creates") or [])


def unnamed_note() -> Dict[str, Any]:
    """The warning a change naming no capability draws, on save and at approval (FR-3)."""
    return {
        "code": CAPABILITY_UNNAMED,
        "where": FIELD,
        "message": (
            "this change names no capability it changes or creates; name them in `capabilities` "
            '({"changes": [<capability path>], "creates": [{"title": ...}]}) so it is on its '
            "capability's waiting list and its fold starts there. A change that changes no "
            "capability may leave it empty"
        ),
    }


async def require_known(
    session: AsyncSession, project_id: str, link: Optional[Dict[str, Any]]
) -> None:
    """Refuse `capability_unknown`, naming the path, for a path that is not a current capability
    of `project_id` (FR-2). Another project's capability is unknown here, whatever its path."""
    for path in (link or {}).get("changes") or []:
        row = await spec_lifecycle.get_document(session, project_id, path)
        if row is None or row.kind != "capability" or row.phase != spec_lifecycle.CURRENT:
            found = (
                "names no document of this project"
                if row is None
                else (
                    f"is a {row.kind} document"
                    if row.kind != "capability"
                    else f"is a {row.phase} capability"
                )
            )
            raise LinkRefusedError(
                f"{path} is not a current capability of this project: it {found}. Name a "
                "capability path from the project's spec list, or name a new one by title in "
                "`creates`",
                code=CAPABILITY_UNKNOWN,
                field=f"{FIELD}.changes",
            )


async def folded_into(session: AsyncSession, document: SpecDocument) -> Optional[str]:
    """The capability a change was first folded into, or None. A merge row is the record, so a
    change folded before the link existed reads the same way (FR-8)."""
    if document.kind != "change-spec":
        return None
    rows = await session.execute(
        select(SpecDocument.path)
        .join(SpecDocumentMerge, SpecDocumentMerge.capability_document_id == SpecDocument.id)
        .where(SpecDocumentMerge.change_document_id == document.id)
        .order_by(SpecDocumentMerge.created_at, literal_column("spec_document_merges.rowid"))
    )
    return rows.scalars().first()


async def folded_into_by_id(session: AsyncSession, document_ids: Sequence[str]) -> Dict[str, str]:
    """`folded_into` for many changes at once: `{change id: capability path}`."""
    if not document_ids:
        return {}
    rows = await session.execute(
        select(SpecDocumentMerge.change_document_id, SpecDocument.path)
        .join(SpecDocument, SpecDocument.id == SpecDocumentMerge.capability_document_id)
        .where(SpecDocumentMerge.change_document_id.in_(list(document_ids)))
        .order_by(SpecDocumentMerge.created_at, literal_column("spec_document_merges.rowid"))
    )
    found: Dict[str, str] = {}
    for change_id, path in rows:
        found.setdefault(change_id, path)
    return found


async def set_link(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    raw: Dict[str, Any],
    *,
    actor: spec_lifecycle.Actor,
    reason: str = "",
) -> Dict[str, Any]:
    """Replace the change's named capabilities at any phase until it is folded or archived (FR-4).

    A metadata write, like `spec_service.link_roadmap_slice`: the `capabilities` field alone is
    rewritten, so no requirement, digest or phase moves and an approval stands. Returns
    `{"capabilities": <new link or None>, "previous": <old>, "changed": bool}`.
    """
    from .spec_payload import CapabilityLink, PayloadError, check_capability_link

    if document.kind != "change-spec":
        raise LinkRefusedError(
            "only a change document names the capabilities it changes",
            code="not_a_change_document",
        )
    into = await folded_into(session, document)
    if into is not None:
        raise LinkRefusedError(
            f"{document.path} is folded into {into}; a folded change's capabilities are fixed",
            code=CHANGE_FOLDED,
            status=409,
        )
    if document.phase == spec_lifecycle.ARCHIVED:
        raise LinkRefusedError(
            f"{document.path} is archived; an archived change's capabilities are fixed",
            code=CHANGE_ARCHIVED,
            status=409,
        )
    try:
        link = CapabilityLink.model_validate(
            {"changes": raw.get("changes") or [], "creates": raw.get("creates") or []}
        )
        check_capability_link(link)
    except PayloadError as exc:
        raise LinkRefusedError(str(exc), code="payload_invalid", field=exc.field) from exc
    except ValueError as exc:  # pydantic's ValidationError
        raise LinkRefusedError(str(exc), code="payload_invalid") from exc
    wanted = named({FIELD: link.model_dump(mode="json")})
    await require_known(session, document.project_id, wanted)

    content = spec_documents.read_document(workspace, document.path)
    stored = spec_documents.parse_stored(content)
    if stored is None:
        raise LinkRefusedError(
            f"{document.path} holds no payload to link", code="document_unreadable", status=409
        )
    previous = named(stored)
    if previous == wanted:
        return {"capabilities": wanted, "previous": previous, "changed": False}
    if wanted is None:
        stored.pop(FIELD, None)
    else:
        stored[FIELD] = wanted
    rewritten = spec_documents.write_payload(
        workspace, document.path, stored, spec_documents.parse_hub(content)
    )
    document.content_digest = spec_lifecycle.digest(rewritten)
    await spec_lifecycle.record_event(
        session,
        document,
        kind=LINK_EVENT,
        actor=actor,
        detail={"capabilities": wanted, "previous": previous, "reason": reason},
    )
    return {"capabilities": wanted, "previous": previous, "changed": True}


@dataclass
class _Change:
    id: str
    path: str
    title: str
    phase: str
    first_approved_at: Any
    order: int
    link: Dict[str, Any]


async def waiting_lists(
    session: AsyncSession,
    workspace: Optional[ProjectWorkspace],
    project_id: str,
    payloads: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """`{capability path: [entry]}` for every capability some open change names (FR-5).

    An open change is a change-spec neither archived nor folded. Each entry is `{path, title,
    phase, built, first_approved_at}`, where `built` is whether it has tasks and every one is
    approved. Ordered by first approval, oldest first, never-approved last; then by the order the
    documents were created (insertion order, since `created_at` ties within a clock tick), then
    path. `payloads` maps a path to its stored payload where the caller has read it already.
    """
    rows = (
        await session.execute(
            select(SpecDocument, literal_column("spec_documents.rowid")).where(
                SpecDocument.project_id == project_id,
                SpecDocument.kind == "change-spec",
                SpecDocument.phase != spec_lifecycle.ARCHIVED,
            )
        )
    ).all()
    if not rows:
        return {}
    ids = [document.id for document, _ in rows]
    folded = set(
        (
            await session.execute(
                select(SpecDocumentMerge.change_document_id).where(
                    SpecDocumentMerge.change_document_id.in_(ids)
                )
            )
        ).scalars()
    )
    known = payloads or {}
    missing = [d.id for d, _ in rows if d.id not in folded and d.path not in known]
    if missing and workspace is not None:
        from . import spec_reading

        read = await spec_reading.payloads_for_documents(session, workspace, missing)
        by_id = {d.id: d.path for d, _ in rows}
        known = {**known, **{by_id[i]: p for i, p in read.items()}}

    changes: List[_Change] = []
    for document, order in rows:
        if document.id in folded:
            continue
        link = named(known.get(document.path))
        if link is None or not link["changes"]:
            continue
        changes.append(
            _Change(
                document.id,
                document.path,
                document.title,
                document.phase,
                document.first_approved_at,
                int(order or 0),
                link,
            )
        )
    if not changes:
        return {}
    built = await _built(session, [c.id for c in changes])
    changes.sort(
        key=lambda c: (
            c.first_approved_at is None,
            c.first_approved_at.isoformat() if c.first_approved_at is not None else "",
            c.order,
            c.path,
        )
    )
    lists: Dict[str, List[Dict[str, Any]]] = {}
    for change in changes:
        entry = {
            "path": change.path,
            "title": change.title,
            "phase": change.phase,
            "built": built.get(change.id, False),
            "first_approved_at": (
                change.first_approved_at.isoformat() if change.first_approved_at else None
            ),
        }
        for capability in change.link["changes"]:
            lists.setdefault(capability, []).append(entry)
    return lists


async def _built(session: AsyncSession, document_ids: Iterable[str]) -> Dict[str, bool]:
    """Whether each document has tasks and every one of them is approved."""
    seen: Dict[str, bool] = {}
    rows = await session.execute(
        select(Task.spec_document_id, Task.status).where(
            Task.spec_document_id.in_(list(document_ids))
        )
    )
    for document_id, state in rows:
        seen[document_id] = seen.get(document_id, True) and state == "approved"
    return seen


async def waiting_for(
    session: AsyncSession,
    workspace: Optional[ProjectWorkspace],
    project_id: str,
    capability_path: str,
) -> List[Dict[str, Any]]:
    """One capability's waiting list."""
    return (await waiting_lists(session, workspace, project_id)).get(capability_path, [])


def default_fold_target(link: Optional[Dict[str, Any]]) -> Optional[str]:
    """The capability path a fold with no target starts from: the one existing capability the
    change names, when it names exactly one and creates none. None otherwise."""
    if link is None:
        return None
    if len(link["changes"]) == 1 and not link["creates"]:
        return link["changes"][0]
    return None


def require_default_target(link: Optional[Dict[str, Any]], path: str) -> str:
    """The fold target for an agent's fold naming none, or a refusal saying what to name (FR-7)."""
    target = default_fold_target(link)
    if target is not None:
        return target
    if link is None:
        raise LinkRefusedError(
            f"{path} names no capability, so a fold must name `capability`",
            code=CAPABILITY_UNNAMED,
        )
    if not link["changes"]:
        titles = ", ".join(repr(c["title"]) for c in link["creates"])
        raise LinkRefusedError(
            f"{path} names only new capabilities ({titles}), none existing: create it with "
            "create_capability and fold_from, or name `capability`",
            code=CAPABILITY_UNNAMED,
        )
    named_all = link["changes"] + [repr(c["title"]) for c in link["creates"]]
    raise LinkRefusedError(
        f"{path} names several capabilities ({', '.join(named_all)}); name `capability` to say "
        "which this fold goes into",
        code=CAPABILITY_AMBIGUOUS,
    )


def target_is_named(link: Optional[Dict[str, Any]], capability: SpecDocument) -> bool:
    """Whether a fold into `capability` goes where the change said it would: a path it names, or
    a capability titled as one it said it would create."""
    if link is None:
        return False
    return capability.path in link["changes"] or names_title(link, capability.title)
