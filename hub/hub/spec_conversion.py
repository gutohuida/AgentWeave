"""Converting a project's spec documents between their legacy `.html` form and `spec.json`.

`a-spec-document-is-stored-as-its-payload` FR-7/8/9, design D5: a route, not a migration, because
migrations do not touch project files and only the Hub resolves a project's directory. Both
directions rewrite the same places a document's path is held: the file, `spec_documents.path`,
undelivered `inbound_queue_entries.spec_document`, the payload's references (`roadmap.document`, a
task's `from.document`) and `spec/index.json`. Document ids, requirement identifiers, evidence,
events and tasks are keyed by id and are not touched.

Everything that can be refused is refused, and every file's new text computed, before anything is
written: a half-converted corpus is the one outcome this must not leave behind. A second call
finds nothing in the source form and changes nothing.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_documents, spec_identity, spec_lifecycle, spec_service
from .db.models import InboundQueueEntry, Run, SpecDocument
from .project_workspace import ProjectPathError, ProjectWorkspace
from .spec_manifest import (
    DOCUMENT_SUFFIX,
    LEGACY_SUFFIX,
    Manifest,
    SpecPathError,
    html_path_for,
    json_path_for,
    parse_html_head,
)
from .spec_payload import PayloadError, validate_payload
from .spec_render import render_document

TARGETS = ("json", "html")


class ConversionRefusedError(Exception):
    """A conversion that changed nothing, with the reason the operator can act on."""

    def __init__(self, message: str, *, code: str, runs: Optional[List[str]] = None) -> None:
        self.code = code
        self.runs = runs or []
        super().__init__(message)


@dataclass
class ConversionResult:
    to: str
    converted: List[Dict[str, Optional[str]]] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)
    index_rewritten: bool = False
    queue_entries: int = 0


@dataclass
class _Step:
    source: str
    target: str
    row: Optional[SpecDocument]
    content: Optional[str]  # None: a row whose file was never written; only its path moves


def repoint_references(stored: Dict[str, Any], swap: Callable[[str], str]) -> Dict[str, Any]:
    """A copy of `stored` whose document references (`roadmap.document`, `from.document`) are swapped."""
    out = copy.deepcopy(stored)
    roadmap = out.get("roadmap")
    if isinstance(roadmap, dict) and isinstance(roadmap.get("document"), str):
        roadmap["document"] = swap(roadmap["document"])
    for task in out.get("tasks") or []:
        imported = task.get("from") if isinstance(task, dict) else None
        if isinstance(imported, dict) and isinstance(imported.get("document"), str):
            imported["document"] = swap(imported["document"])
    return out


async def convert(
    session: AsyncSession, workspace: ProjectWorkspace, project_id: str, to: str
) -> ConversionResult:
    """Convert every document of the project to `to` ("json" or "html"); the caller commits."""
    if to not in TARGETS:
        raise ConversionRefusedError(f"convert to one of {TARGETS}, not {to!r}", code="bad_target")
    await _refuse_while_running(session, project_id)

    rows = await spec_lifecycle.list_documents(session, project_id)
    by_path = {row.path: row for row in rows}
    result = ConversionResult(to=to)
    if to == "json":
        steps = _plan_to_json(workspace, rows, by_path, result)
    else:
        steps = _plan_to_html(workspace, rows, by_path, result)
    _refuse_occupied(workspace, steps, by_path)

    # The database first, then the files: the route commits after this returns, and a failed
    # write raises before that commit, so the rows roll back to the paths still on disk.
    for step in steps:
        if step.row is not None:
            previous_digest = step.row.content_digest
            step.row.path = step.target
            if step.content is not None and previous_digest == _digest_of(workspace, step.source):
                # A file the Hub wrote stays one the Hub wrote; one edited outside it stays diverged.
                step.row.content_digest = spec_lifecycle.digest(step.content)
        moved = await session.execute(
            update(InboundQueueEntry)
            .where(
                InboundQueueEntry.project_id == project_id,
                InboundQueueEntry.spec_document == step.source,
                InboundQueueEntry.delivered_at.is_(None),
            )
            .values(spec_document=step.target)
        )
        result.queue_entries += moved.rowcount or 0
    await session.flush()

    for step in steps:
        if step.content is not None:
            if to == "json":
                spec_documents.write_document(workspace, step.target, step.content)
            else:
                spec_documents.write_legacy(workspace, step.target, step.content)
            spec_documents.remove_converted(workspace, step.source)
        result.converted.append(
            {"from": step.source, "to": step.target, "id": step.row.id if step.row else None}
        )
    result.index_rewritten = spec_documents.repoint_index(
        workspace, json_path_for if to == "json" else html_path_for
    )
    return result


async def _refuse_while_running(session: AsyncSession, project_id: str) -> None:
    """FR-9: a running turn holds a document path in its context; renaming under it breaks it."""
    running = (
        await session.execute(
            select(Run.id, Run.agent)
            .where(Run.project_id == project_id, Run.status == "running")
            .order_by(Run.id)
        )
    ).all()
    if running:
        named = ", ".join(f"{run_id} ({agent})" for run_id, agent in running)
        raise ConversionRefusedError(
            f"runs are active in this project: {named}; stop them or let them finish, then convert",
            code="conversion_run_active",
            runs=[run_id for run_id, _ in running],
        )


def _plan_to_json(
    workspace: ProjectWorkspace,
    rows: List[SpecDocument],
    by_path: Dict[str, SpecDocument],
    result: ConversionResult,
) -> List[_Step]:
    _, diagnostics = spec_documents.discover(workspace)
    on_disk = [d["path"] for d in diagnostics if d["code"] == "legacy_html_document"]
    steps: List[_Step] = []
    for source in on_disk:
        try:
            content = spec_documents.read_legacy(workspace, source)
        except (SpecPathError, ProjectPathError, OSError) as exc:
            result.skipped.append({"path": source, "reason": f"unreadable: {exc}"})
            continue
        stored = spec_documents.parse_legacy(content)
        if stored is None:
            result.skipped.append({"path": source, "reason": "no_readable_payload"})
            continue
        row = by_path.get(source)
        hub = spec_service.hub_block(row) if row is not None else _hub_from_head(content or "")
        stored = repoint_references(stored, json_path_for)
        steps.append(
            _Step(source, json_path_for(source), row, spec_documents.serialize(stored, hub))
        )
    planned = {step.source for step in steps} | {item["path"] for item in result.skipped}
    steps.extend(
        _Step(row.path, json_path_for(row.path), row, None)
        for row in rows
        if row.path.endswith(LEGACY_SUFFIX) and row.path not in planned
    )
    return steps


def _plan_to_html(
    workspace: ProjectWorkspace,
    rows: List[SpecDocument],
    by_path: Dict[str, SpecDocument],
    result: ConversionResult,
) -> List[_Step]:
    on_disk, _ = spec_documents.discover(workspace)
    manifest, _, _ = spec_documents.read_index(workspace)
    summaries = spec_documents.corpus_summaries(workspace, manifest) if manifest else {}
    legacy_manifest = _legacy_manifest(manifest) if manifest else None
    legacy_summaries = {html_path_for(path): text for path, text in summaries.items()}

    steps: List[_Step] = []
    for source in on_disk:
        content = spec_documents.read_document(workspace, source)
        stored = spec_documents.parse_stored(content)
        try:
            payload = validate_payload(stored) if stored is not None else None
        except PayloadError:
            payload = None
        if stored is None or payload is None:
            result.skipped.append({"path": source, "reason": "no_readable_payload"})
            continue
        row = by_path.get(source)
        hub = spec_documents.parse_hub(content)
        target = html_path_for(source)
        legacy_stored = repoint_references(stored, html_path_for)
        identifiers, _ = spec_identity.read_identity(stored)
        corpus = None
        if legacy_manifest is not None and target in legacy_manifest.by_path():
            corpus = spec_documents.build_corpus_context(legacy_manifest, target, legacy_summaries)
        slice_of = spec_service.slice_of(workspace, payload)
        if slice_of is not None:
            slice_of = dataclasses.replace(
                slice_of, roadmap_path=html_path_for(slice_of.roadmap_path)
            )
        # The page a save wrote before storage moved to JSON, which `render_page` still serves,
        # with every path it names in its legacy form.
        page = render_document(
            validate_payload(legacy_stored),
            identifiers,
            phase=row.phase if row is not None else hub.get("phase") or spec_lifecycle.EXPLORING,
            stored_payload=legacy_stored,
            rigor=(row.rigor if row is not None else hub.get("rigor")) or "sketch",
            corpus=corpus,
            slice_of=slice_of,
        )
        steps.append(_Step(source, target, row, page))
    planned = {step.source for step in steps} | {item["path"] for item in result.skipped}
    steps.extend(
        _Step(row.path, html_path_for(row.path), row, None)
        for row in rows
        if row.path.endswith(DOCUMENT_SUFFIX) and row.path not in planned
    )
    return steps


def _legacy_manifest(manifest: Manifest) -> Manifest:
    """The index as a legacy corpus held it: the same arrangement at `.html` paths."""
    return dataclasses.replace(
        manifest,
        home=html_path_for(manifest.home),
        documents=tuple(
            dataclasses.replace(
                entry,
                path=html_path_for(entry.path),
                parent=html_path_for(entry.parent) if entry.parent else None,
            )
            for entry in manifest.documents
        ),
    )


def _hub_from_head(content: str) -> Dict[str, Any]:
    """A rowless legacy document's block: the phase its head declares, nothing guessed."""
    status = parse_html_head(content).get("status")
    return {
        "phase": status or spec_lifecycle.EXPLORING,
        "rigor": "sketch",
        "step": None,
        "size": None,
    }


def _digest_of(workspace: ProjectWorkspace, path: str) -> Optional[str]:
    try:
        if path.endswith(LEGACY_SUFFIX):
            content = spec_documents.read_legacy(workspace, path)
        else:
            content = spec_documents.read_document(workspace, path)
    except (SpecPathError, ProjectPathError, OSError):
        return None
    return spec_lifecycle.digest(content) if content is not None else None


def _refuse_occupied(
    workspace: ProjectWorkspace, steps: List[_Step], by_path: Dict[str, SpecDocument]
) -> None:
    """Refuse, before anything moves, a target another document or another file already holds."""
    for step in steps:
        occupant = by_path.get(step.target)
        if occupant is not None and occupant is not step.row:
            raise ConversionRefusedError(
                f"{step.source} converts to {step.target}, which document {occupant.id} holds",
                code="path_occupied",
            )
        if step.content is None:
            continue
        if step.target.endswith(LEGACY_SUFFIX):
            existing = spec_documents.read_legacy(workspace, step.target)
        else:
            existing = spec_documents.read_document(workspace, step.target)
        if existing is not None and existing != step.content:
            raise ConversionRefusedError(
                f"{step.source} converts to {step.target}, and a different file is already there",
                code="path_occupied",
            )
