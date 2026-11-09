"""An agent the operator trusts tidies the specification corpus (`tidy_spec_document`).

`an-agent-the-operator-trusts-can-tidy-the-specs` (spdoc-d9f38f8d3017). An agent whose
`can_admin_specs` switch the operator turned on may fold an approved change into a capability, create
a capability, edit one (rewriting or retiring a requirement the code contradicts), mark a document
superseded or clear the mark, and set or correct a change's roadmap slice. Each act applies at once,
through the same functions the operator's own acts use, and is recorded as a `tidy` event the
operator reviews (`spec_lifecycle.record_tidy_act`).

What an act is refused for, checked in this order, before anything is written:

1. `operators_act` -- the op names one of the operator's acts (approve, archive, hold, ...). The
   switch never reaches them (FR-12), so this is answered whatever the switch says.
2. `spec_admin_off` -- the agent's switch is off (FR-4). Read from its row on every call.
3. `reason_required` -- the reason is empty or blank (FR-7).
4. `document_held` -- a document the act touches is held by the operator (FR-11).
5. `live_work` -- a document the act touches has a running build or open tasks (FR-5).

An agent's fold never archives: archive cannot be undone and is the operator's, so the change is
marked superseded by its capability instead (D3, FR-9).

Nothing here commits: the route commits once the act and its record are both in the session, so a
refusal raised part-way leaves nothing behind. The one write that is not transactional, a file, is
undone by hand where an act can fail after writing one (`_create_capability`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import builds, spec_documents, spec_lifecycle, spec_service
from .db.models import Agent, SpecDocument, Task
from .project_workspace import ProjectWorkspace
from .spec_manifest import ManifestDocument, SpecPathError, build_manifest, validate_spec_path
from .spec_payload import SCHEMA_VERSION

logger = logging.getLogger(__name__)

FOLD = "fold"
CREATE_CAPABILITY = "create_capability"
EDIT_CAPABILITY = "edit_capability"
SUPERSEDE = "supersede"
CLEAR_SUPERSEDED = "clear_superseded"
SET_SLICE = "set_slice"

OPS = (FOLD, CREATE_CAPABILITY, EDIT_CAPABILITY, SUPERSEDE, CLEAR_SUPERSEDED, SET_SLICE)

#: The operator's acts, by the op an agent might name them with, and how a refusal names each.
#: Refused `operators_act` whatever the agent's switch says (FR-12).
OPERATOR_OPS: Dict[str, str] = {
    "approve": "approving a document",
    "close_exploration": "closing an exploration",
    "archive": "archiving a document",
    "hold": "holding a document",
    "release": "releasing a held document",
    "accept_amendment": "accepting a proposed amendment",
    "decline_amendment": "declining a proposed amendment",
    "answer_cannot_satisfy": "answering a cannot-satisfy report",
    "decide_evidence": "deciding evidence",
}

SPEC_ADMIN_OFF = "spec_admin_off"
DOCUMENT_HELD = "document_held"
LIVE_WORK = "live_work"
REASON_REQUIRED = "reason_required"
OPERATORS_ACT = "operators_act"


class TidyRefusedError(Exception):
    """A tidy act the Hub will not perform, with the code and status the route answers."""

    def __init__(self, message: str, *, code: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class TidyResult:
    """What an applied act answers: its record's id, and every document it changed."""

    act_id: str
    act: str
    path: str
    touched: List[SpecDocument]
    detail: Dict[str, Any]


# ------------------------------------------------------------------ the gates


async def switch_is_on(session: AsyncSession, project_id: str, agent: str) -> bool:
    """The agent's `can_admin_specs`, from its row. An agent with no row has no switch."""
    value = await session.scalar(
        select(Agent.can_admin_specs).where(Agent.project_id == project_id, Agent.name == agent)
    )
    return bool(value)


def _refuse_operators_act(op: str) -> None:
    what = OPERATOR_OPS.get(op)
    if what is not None:
        raise TidyRefusedError(
            f"{what} is the operator's act; the spec-admin switch never lets an agent do it",
            code=OPERATORS_ACT,
            status=403,
        )


def _refuse_held(documents: Sequence[SpecDocument]) -> None:
    for document in documents:
        hold = spec_lifecycle.held_view(document)
        if hold is not None:
            note = f" ({hold['note']})" if hold["note"] else ""
            raise TidyRefusedError(
                f"{document.path} is held by the operator{note}; no tidy act touches it until they "
                "release it. You may ask the operator whether to supersede it",
                code=DOCUMENT_HELD,
            )


async def _refuse_live(session: AsyncSession, documents: Sequence[SpecDocument]) -> None:
    """FR-5: a document with a running build or open tasks is left alone, naming what is open."""
    for document in documents:
        running = await builds.running_build(session, document.id)
        if running is not None:
            raise TidyRefusedError(
                f"{document.path} has a build running ({running.id}); a document is tidied once "
                "its build has ended",
                code=LIVE_WORK,
            )
        open_ids = await spec_lifecycle.open_task_ids(session, document)
        if open_ids:
            rows = await session.execute(
                select(Task.id, Task.readable_id, Task.status).where(Task.id.in_(open_ids))
            )
            named = {
                task_id: (f"{readable} ({task_id})" if readable else task_id) + f", {state}"
                for task_id, readable, state in rows
            }
            raise TidyRefusedError(
                f"{document.path} has open tasks: "
                + "; ".join(named.get(task_id, task_id) for task_id in open_ids)
                + ". A document is tidied once its work is decided",
                code=LIVE_WORK,
            )


async def _document(
    session: AsyncSession, project_id: str, raw: Any, *, field: str
) -> SpecDocument:
    if not isinstance(raw, str) or not raw.strip():
        raise TidyRefusedError(f"`{field}` names no document", code="field_required", status=422)
    try:
        path = validate_spec_path(raw.strip())
    except SpecPathError as exc:
        raise TidyRefusedError(str(exc), code="unsafe_document_path", status=400) from exc
    document = await spec_lifecycle.get_document(session, project_id, path)
    if document is None:
        raise TidyRefusedError(
            f"no specification document at {path}", code="document_not_found", status=404
        )
    return document


def _strings(fields: Dict[str, Any], name: str) -> List[str]:
    value = fields.get(name)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise TidyRefusedError(f"`{name}` is a list of keys", code="field_invalid", status=422)
    return list(value)


def _objects(fields: Dict[str, Any], name: str, cls: type) -> Optional[List[Any]]:
    value = fields.get(name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise TidyRefusedError(f"`{name}` is a list", code="field_invalid", status=422)
    try:
        return [cls(**item) for item in value]
    except TypeError as exc:
        raise TidyRefusedError(
            f"`{name}` has an entry this op does not take: {exc}", code="field_invalid", status=422
        ) from exc


def _fold_options(fields: Dict[str, Any]) -> Tuple[Optional[List[Any]], Dict[str, Any]]:
    """The operator's fold choices (`spec_service.fold`), read from an act's fields."""
    retire = fields.get("retire")
    if isinstance(retire, bool):
        raise TidyRefusedError(
            "`retire` on a fold is the list of capability requirement keys it retires",
            code="field_invalid",
            status=422,
        )
    items = _objects(fields, "items", spec_service.FoldItem)
    return items, {
        "retire": _strings(fields, "retire"),
        "retire_criteria": _strings(fields, "retire_criteria"),
        "algorithms": _objects(fields, "algorithms", spec_service.FoldAlgorithm),
        "retire_algorithms": _strings(fields, "retire_algorithms"),
        "criteria": _objects(fields, "criteria", spec_service.FoldCriterion) or [],
    }


# ------------------------------------------------------------------ the entry point


async def tidy(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    *,
    actor: spec_lifecycle.Actor,
    path: str,
    op: str,
    reason: str,
    fields: Optional[Dict[str, Any]] = None,
) -> TidyResult:
    """Apply one tidy act for an agent run in `project_id` (the run's, never the request's), or
    refuse it before anything is written."""
    fields = dict(fields or {})
    _refuse_operators_act(op)
    if op not in OPS:
        raise TidyRefusedError(
            f"unknown tidy op {op!r}; the ops are: {', '.join(OPS)}", code="unknown_op", status=422
        )
    if actor.kind != "agent" or not actor.run_id:
        raise TidyRefusedError("a tidy act is an agent run's", code="tidy_needs_a_run", status=403)
    if not await switch_is_on(session, project_id, actor.name):
        raise TidyRefusedError(
            "your spec-admin switch is off, so you may not tidy the specs; only the operator can "
            "turn it on, on your agent's settings page",
            code=SPEC_ADMIN_OFF,
            status=403,
        )
    reason = (reason or "").strip()
    if not reason:
        raise TidyRefusedError(
            "a tidy act needs a reason: say why, in a sentence the operator reads in the tidy list",
            code=REASON_REQUIRED,
            status=422,
        )
    handler = _HANDLERS[op]
    return await handler(session, workspace, project_id, actor, path, reason, fields)


def capability_path_hint(title: str) -> str:
    """How a refusal names a capability not created yet."""
    return f"a new capability {title!r}"


async def _record(
    session: AsyncSession,
    document: SpecDocument,
    *,
    actor: spec_lifecycle.Actor,
    act: str,
    reason: str,
    touched: List[SpecDocument],
    detail: Dict[str, Any],
    code_wins: Optional[Dict[str, Any]] = None,
) -> TidyResult:
    event = await spec_lifecycle.record_tidy_act(
        session, document, actor=actor, act=act, reason=reason, code_wins=code_wins, detail=detail
    )
    return TidyResult(act_id=event.id, act=act, path=document.path, touched=touched, detail=detail)


# ------------------------------------------------------------------ the acts


async def _fold(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    change = await _document(session, project_id, path, field="path")
    capability = await _document(session, project_id, fields.get("capability"), field="capability")
    items, options = _fold_options(fields)
    _refuse_held([change, capability])
    await _refuse_live(session, [change, capability])
    await _apply_fold(session, workspace, change, capability, items, options, actor, reason)
    return await _record(
        session,
        change,
        actor=actor,
        act=FOLD,
        reason=reason,
        touched=[capability, change],
        detail={"capability": capability.path},
    )


async def _apply_fold(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    change: SpecDocument,
    capability: SpecDocument,
    items: Optional[List[Any]],
    options: Dict[str, Any],
    actor: spec_lifecycle.Actor,
    reason: str,
) -> None:
    """The operator's fold with archive off, then the superseded mark naming the capability (D3)."""
    try:
        await spec_service.fold(
            session,
            workspace,
            change,
            capability,
            items,
            actor=actor,
            archive=False,
            note=reason,
            **options,
        )
    except spec_service.FoldRefusedError as exc:
        raise TidyRefusedError(str(exc), code=exc.code) from exc
    except spec_service.SaveRefusedError as exc:
        raise TidyRefusedError(str(exc), code=exc.code, status=422) from exc
    except spec_lifecycle.PhaseError as exc:
        raise TidyRefusedError(str(exc), code=exc.code) from exc
    spec_lifecycle.mark_superseded(change, actor=actor, reason=reason, successor=capability.path)


async def _create_capability(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    title = fields.get("title")
    if not isinstance(title, str) or not title.strip():
        raise TidyRefusedError("a capability needs a title", code="field_required", status=422)
    title = title.strip()
    change = None
    if fields.get("fold_from"):
        change = await _document(session, project_id, fields["fold_from"], field="fold_from")
    area = None
    if fields.get("area"):
        area = await _document(session, project_id, fields["area"], field="area")
    items, options = _fold_options(fields)
    if change is not None:
        _refuse_held([change])
        await _refuse_live(session, [change])
        # Refused before the capability exists, so a change that cannot be folded does not leave
        # an empty capability behind.
        try:
            spec_service._require_approved_change(
                change,
                capability_path_hint(title),
                await spec_lifecycle.merged_into(session, change),
            )
        except spec_service.FoldRefusedError as exc:
            raise TidyRefusedError(str(exc), code=exc.code) from exc

    capability_path = await spec_service.mint_document_path(
        session, project_id, workspace, kind="capability", title=title
    )
    try:
        capability = await spec_lifecycle.create_document(
            session, project_id, capability_path, actor=actor, title=title, kind="capability"
        )
        scaffold = {"schema_version": SCHEMA_VERSION, "kind": "capability", "title": title}
        await spec_service.save_document(
            session, workspace, capability, scaffold, actor=actor, via="create"
        )
        if change is not None:
            await _apply_fold(session, workspace, change, capability, items, options, actor, reason)
    except BaseException as exc:
        # The rows roll back with the session; the file the scaffold wrote does not.
        try:
            spec_documents.delete_document_file(workspace, capability_path)
        except OSError:
            logger.warning("could not remove %s after a refused create", capability_path)
        if isinstance(exc, spec_service.SaveRefusedError):
            raise TidyRefusedError(str(exc), code=exc.code, status=422) from exc
        if isinstance(exc, spec_lifecycle.PhaseError):
            raise TidyRefusedError(str(exc), code=exc.code) from exc
        raise
    index = await _file_in_index(session, workspace, project_id, capability, area)
    touched = [capability] + ([change] if change is not None else [])
    detail: Dict[str, Any] = {"capability": capability.path, "index": index}
    if change is not None:
        detail["fold_from"] = change.path
    if area is not None:
        detail["area"] = area.path
    return await _record(
        session,
        capability,
        actor=actor,
        act=CREATE_CAPABILITY,
        reason=reason,
        touched=touched,
        detail=detail,
    )


async def _file_in_index(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    capability: SpecDocument,
    area: Optional[SpecDocument],
) -> str:
    """Put a new capability in `spec/index.json`, under `area` when one is named.

    Only an index that exists is rebuilt: with none, the project has no map yet, and choosing its
    home is the operator's (`spec_documents._select_home`). Answers `filed`, `no_index` or why not.
    """
    existing, state, _ = spec_documents.read_index(workspace)
    if existing is None:
        return "no_index" if state == "absent" else f"index_{state}"
    on_disk, _ = spec_documents.discover(workspace)
    rows = await spec_lifecycle.list_documents(session, project_id)
    manifest, _ = spec_documents.build_index(
        on_disk, [(row.path, row.title, row.kind, row.phase) for row in rows], existing
    )
    if manifest is None:
        return "index_not_rebuilt"
    if area is not None:
        entries = [
            (
                ManifestDocument(
                    path=entry.path,
                    title=entry.title,
                    kind=entry.kind,
                    status=entry.status,
                    parent=area.path,
                    order=entry.order,
                )
                if entry.path == capability.path
                else entry
            )
            for entry in manifest.documents
        ]
        manifest = build_manifest(entries, manifest.home) or manifest
    try:
        spec_documents.write_index(workspace, manifest)
    except OSError as exc:
        logger.warning("could not write the index after creating %s: %s", capability.path, exc)
        return "index_write_failed"
    return "filed"


async def _edit_capability(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    capability = await _document(session, project_id, path, field="path")
    if capability.kind != "capability":
        raise TidyRefusedError(
            f"{capability.path} is not a capability document", code="not_a_capability"
        )
    key = fields.get("requirement")
    if not isinstance(key, str) or not key.strip():
        raise TidyRefusedError(
            "`requirement` names the capability requirement to change",
            code="field_required",
            status=422,
        )
    key = key.strip()
    retire = fields.get("retire") is True
    statement = fields.get("statement")
    if retire == bool(isinstance(statement, str) and statement.strip()):
        raise TidyRefusedError(
            "edit_capability takes a new `statement` or `retire: true`, one of the two",
            code="field_required",
            status=422,
        )
    code_wins_in = fields.get("code_wins")
    cited = None
    if code_wins_in is not None:
        cited = code_wins_in.get("cited") if isinstance(code_wins_in, dict) else None
        if not isinstance(cited, str) or not cited.strip():
            raise TidyRefusedError(
                "`code_wins.cited` names the code or test you read to decide",
                code="field_required",
                status=422,
            )
        cited = cited.strip()
    _refuse_held([capability])
    await _refuse_live(session, [capability])
    if capability.phase != spec_lifecycle.CURRENT:
        raise TidyRefusedError(
            f"{capability.path} is retired; a retired capability is not edited",
            code="capability_retired",
        )

    payload = spec_documents.read_payload(workspace, capability.path)
    if payload is None:
        raise TidyRefusedError(
            f"{capability.path} has no readable content", code="document_unreadable"
        )
    key = _requirement_key(payload, key)
    requirements = [dict(r) for r in payload.get("requirements") or []]
    found = next((r for r in requirements if r.get("key") == key), None)
    if found is None:
        raise TidyRefusedError(
            f"{capability.path} has no requirement {key!r}; its requirements are: "
            + ", ".join(str(r.get("key")) for r in requirements),
            code="unknown_requirement",
            status=422,
        )
    before = found.get("statement", "")
    if retire:
        after = None
        payload["requirements"] = [r for r in requirements if r.get("key") != key]
        payload["acceptance_criteria"] = [
            c for c in payload.get("acceptance_criteria") or [] if c.get("requirement") != key
        ]
    else:
        after = statement.strip()
        found["statement"] = after
        payload["requirements"] = requirements
    try:
        await spec_service.merge_document(
            session, workspace, capability, [], payload, actor=actor, note=reason
        )
    except spec_service.SaveRefusedError as exc:
        raise TidyRefusedError(str(exc), code=exc.code, status=422) from exc
    code_wins = (
        {"requirement": key, "before": before, "after": after, "cited": cited}
        if cited is not None
        else None
    )
    return await _record(
        session,
        capability,
        actor=actor,
        act=EDIT_CAPABILITY,
        reason=reason,
        touched=[capability],
        detail={"requirement": key, "before": before, "after": after, "retired": retire},
        code_wins=code_wins,
    )


def _requirement_key(payload: Dict[str, Any], named: str) -> str:
    """A requirement named by its key or by its `FR-n` identifier, as its key."""
    from . import spec_identity

    identifiers, _ = spec_identity.read_identity(payload)
    for key, identifier in identifiers.items():
        if identifier == named:
            return key
    return named


async def _supersede(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    document = await _document(session, project_id, path, field="path")
    successor = None
    if fields.get("successor"):
        successor = await _document(session, project_id, fields["successor"], field="successor")
        if successor.id == document.id:
            raise TidyRefusedError(
                "a document is not superseded by itself", code="successor_is_itself", status=422
            )
    _refuse_held([document])
    await _refuse_live(session, [document])
    if document.phase == spec_lifecycle.ARCHIVED:
        raise TidyRefusedError(
            f"{document.path} is archived; there is nothing left to mark", code="document_archived"
        )
    spec_lifecycle.mark_superseded(
        document, actor=actor, reason=reason, successor=successor.path if successor else None
    )
    return await _record(
        session,
        document,
        actor=actor,
        act=SUPERSEDE,
        reason=reason,
        touched=[document],
        detail={"successor": successor.path if successor else None},
    )


async def _clear_superseded(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    document = await _document(session, project_id, path, field="path")
    _refuse_held([document])
    await _refuse_live(session, [document])
    mark = spec_lifecycle.superseded_view(document)
    if mark is None:
        raise TidyRefusedError(f"{document.path} is not marked superseded", code="not_superseded")
    spec_lifecycle.clear_superseded(document)
    return await _record(
        session,
        document,
        actor=actor,
        act=CLEAR_SUPERSEDED,
        reason=reason,
        touched=[document],
        detail={"was": mark},
    )


async def _set_slice(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    actor: spec_lifecycle.Actor,
    path: str,
    reason: str,
    fields: Dict[str, Any],
) -> TidyResult:
    document = await _document(session, project_id, path, field="path")
    roadmap = await _document(session, project_id, fields.get("roadmap"), field="roadmap")
    slice_key = fields.get("slice")
    if not isinstance(slice_key, str) or not slice_key.strip():
        raise TidyRefusedError(
            "`slice` names the roadmap's slice", code="field_required", status=422
        )
    _refuse_held([document])
    await _refuse_live(session, [document])
    try:
        changed = await spec_service.link_roadmap_slice(
            session, workspace, document, roadmap.path, slice_key.strip(), actor=actor, replace=True
        )
    except spec_service.SaveRefusedError as exc:
        raise TidyRefusedError(str(exc), code=exc.code, status=422) from exc
    return await _record(
        session,
        document,
        actor=actor,
        act=SET_SLICE,
        reason=reason,
        touched=[document],
        detail={"roadmap": roadmap.path, "slice": slice_key.strip(), "changed": changed},
    )


_HANDLERS = {
    FOLD: _fold,
    CREATE_CAPABILITY: _create_capability,
    EDIT_CAPABILITY: _edit_capability,
    SUPERSEDE: _supersede,
    CLEAR_SUPERSEDED: _clear_superseded,
    SET_SLICE: _set_slice,
}
