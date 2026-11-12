"""`spec/index.json` and each document's hub block follow the rows, after every document write.

The rows are the authority on what documents a project has and what phase each is in; the index
file and the hub block a stored document carries are copies for whoever reads the files. They were
refreshed only by some writes: a reindex, creating a capability, a phase move of that one document.
So `spec/index.json` listed 11 of 62 approved change documents until a capability was created
(F1158), and four documents migration `0149` moved from `proposed` back to `exploring` still said
`proposed` in their own files (F1157), since a migration writes rows and never files.

Here, any commit that changes a `SpecDocument` row schedules one refresh of its project: the index
is rebuilt from the rows (`spec_documents.build_index`, which keeps the operator's home, parents and
order), and every indexed document whose hub block disagrees with its row is re-rendered, as
`spec_service.rerender_corpus` does on a reindex. Only a project that already has an index is
touched: choosing a home is the operator's (`spec_documents._select_home`).

**After the commit, in the background, off the loop.** The rows are read after the commit that
changed them, so a rolled-back write refreshes nothing; the walk and the file reads run on the
blocking pool (`blocking.run`), since a corpus is hundreds of files. Refreshes of one project never
overlap: one asked for while another runs is run once after it.

**Never at start-up.** Nothing is scheduled until `enable()`, which the lifespan calls once the
Hub is serving, so a restart never rewrites a project's files on its own; the first document write
after it does. A refresh that fails is logged and changes nothing the next one cannot repair.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import event
from sqlalchemy.orm import Session

from .db.models import SpecDocument

logger = logging.getLogger(__name__)

_PROJECTS_KEY = "aw_spec_index_projects"
#: Set on the refresh's own session, whose commit changes rows and must not schedule another.
_REFRESHING_KEY = "aw_spec_index_refreshing"

_enabled = False
_running: Dict[str, "asyncio.Task[None]"] = {}
_again: Set[str] = set()


def enable() -> None:
    """Start refreshing after document writes. Called by the lifespan once the Hub is serving."""
    global _enabled
    _enabled = True


def disable() -> None:
    global _enabled
    _enabled = False
    _again.clear()


async def settle() -> None:
    """Wait for every scheduled refresh to finish. For tests and shutdown."""
    while True:
        pending = [task for task in _running.values() if not task.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


@event.listens_for(Session, "before_flush")
def _note_written_documents(session: Session, _context: Any, _instances: Any) -> None:
    if not _enabled or session.info.get(_REFRESHING_KEY):
        return
    projects: Optional[Set[str]] = None
    for instance in (*session.new, *session.dirty, *session.deleted):
        if isinstance(instance, SpecDocument) and instance.project_id:
            if projects is None:
                projects = session.info.setdefault(_PROJECTS_KEY, set())
            projects.add(instance.project_id)


@event.listens_for(Session, "after_commit")
def _schedule_after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return
    projects = session.info.pop(_PROJECTS_KEY, None)
    if not projects or not _enabled:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # a synchronous session outside the Hub's loop: nothing to schedule on
        return
    for project_id in sorted(projects):
        schedule(project_id)


@event.listens_for(Session, "after_transaction_end")
def _forget_at_transaction_end(session: Session, transaction: Any) -> None:
    if transaction.parent is None:  # a rolled-back write refreshes nothing
        session.info.pop(_PROJECTS_KEY, None)


def schedule(project_id: str) -> None:
    """Refresh `project_id` soon; once more after the running refresh when one is running."""
    running = _running.get(project_id)
    if running is not None and not running.done():
        _again.add(project_id)
        return
    _running[project_id] = asyncio.get_running_loop().create_task(_drive(project_id))


async def _drive(project_id: str) -> None:
    while True:
        _again.discard(project_id)
        try:
            await refresh(project_id)
        except Exception:  # noqa: BLE001 -- the next write refreshes again
            logger.warning("could not refresh the spec index of %s", project_id, exc_info=True)
        if project_id not in _again:
            return


async def refresh(project_id: str) -> List[str]:
    """Rebuild `project_id`'s index from its rows and re-render stale hub blocks. Answers the
    paths whose file was rewritten."""
    from . import blocking, project_workspace, spec_lifecycle
    from .db.engine import async_session_factory

    async with async_session_factory() as session:
        session.info[_REFRESHING_KEY] = True
        try:
            workspace = await project_workspace.resolve_project_workspace(session, project_id)
        except project_workspace.ProjectWorkspaceError:
            return []
        rows = await spec_lifecycle.list_documents(session, project_id)
        snapshot = [
            SimpleNamespace(
                id=row.id,
                path=row.path,
                title=row.title,
                kind=row.kind,
                phase=row.phase,
                step=row.step,
                size=row.size,
            )
            for row in rows
        ]
        rewritten = await blocking.run(_refresh_files, workspace, snapshot)
        if not rewritten:
            return []
        by_path = {row.path: row for row in rows}
        actor = spec_lifecycle.Actor(kind="system", name="index")
        for path, digest in rewritten:
            document = by_path[path]
            document.content_digest = digest
            await spec_lifecycle.record_event(
                session, document, kind="rerendered", actor=actor, detail={"path": path}
            )
        await session.commit()
    from .sse import sse_manager

    await sse_manager.broadcast(project_id, "spec_updated", {"path": None})
    return [path for path, _ in rewritten]


def _refresh_files(workspace: Any, rows: List[SimpleNamespace]) -> List[Tuple[str, str]]:
    """The file half of `refresh`, on the blocking pool: `[(path, new digest)]` per rewrite."""
    from . import spec_documents, spec_lifecycle, spec_service
    from .spec_manifest import dump_manifest

    existing, _, _ = spec_documents.read_index(workspace)
    if existing is None:
        return []
    on_disk, _ = spec_documents.discover(workspace)
    manifest, _ = spec_documents.build_index(
        on_disk, [(row.path, row.title, row.kind, row.phase) for row in rows], existing
    )
    if manifest is None:
        return []
    if dump_manifest(manifest) != dump_manifest(existing):
        spec_documents.write_index(workspace, manifest)

    by_path = {row.path: row for row in rows}
    rewritten: List[Tuple[str, str]] = []
    for entry in manifest.documents:
        row = by_path.get(entry.path)
        if row is None:
            continue
        try:
            current = spec_documents.read_listed_document(workspace, entry.path)
        except Exception:  # noqa: BLE001 -- an unreadable file is the reindex's to report
            continue
        stored = spec_documents.parse_stored(current)
        if stored is None:
            continue
        hub = spec_documents.parse_hub(current)
        if all(hub.get(field) == getattr(row, field) for field in ("phase", "step", "size")):
            continue
        rendered = spec_documents.serialize(stored, spec_service.hub_block(row, current))
        # A request may have written this file since it was read: its write wins, and carries
        # the row's block anyway.
        if spec_documents.read_document(workspace, entry.path) != current:
            continue
        try:
            spec_documents.write_document(workspace, entry.path, rendered)
        except OSError as exc:
            logger.warning("could not re-render %s: %s", entry.path, exc)
            continue
        rewritten.append((entry.path, spec_lifecycle.digest(rendered)))
    return rewritten
