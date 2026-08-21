"""The specification document tree, read from the project working directory.

This module replaces the ``project_specs`` content cache and the
``project_spec_snapshots`` reconciliation record. Both existed for one stated
reason — the Hub could not see a project's files — and that reason is gone:
``ProjectWorkspace`` resolves a registered project's directory in both
deployment modes, so the file on disk is the document and there is no second
copy to reconcile with.

Every path is resolved through ``ProjectWorkspace.resolve_relative``, which
refuses absolute paths, traversal, control characters and symlink escapes, and
then validated against ``validate_spec_path``'s repo-relative contract. A path
that fails either is **excluded and reported** — never silently skipped, because
a document missing from a list looks identical to a document that was never
written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .project_workspace import ProjectPathError, ProjectWorkspace
from .spec_manifest import (
    HTML_HEAD_MAX_BYTES,
    MANIFEST_MAX_BYTES,
    Manifest,
    ManifestDocument,
    SpecPathError,
    build_manifest,
    compute_intrinsic_conflicts,
    dump_manifest,
    load_manifest,
    validate_spec_path,
)
from .spec_payload import extract_payload
from .spec_render import CorpusChild, CorpusContext

SPEC_DIR = "spec"
INDEX_RELATIVE = "spec/index.json"

# A tree far past this is a sign of something other than a specification tree —
# a vendored directory, a build output. Discovery stops and says so rather than
# walking an unbounded filesystem on every request.
MAX_DISCOVERED_DOCUMENTS = 1000


@dataclass
class DocumentTreeState:
    """What the Hub can say about a project's specification tree right now."""

    specs: List[Dict[str, Any]] = field(default_factory=list)
    home: Optional[str] = None
    index: Optional[Dict[str, Any]] = None
    missing: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)


def _diag(code: str, **kwargs: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "code": code,
        "path": None,
        "field": None,
        "expected": None,
        "actual": None,
        "source_ids": None,
    }
    base.update(kwargs)
    return base


def _mtime_iso(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def discover(workspace: ProjectWorkspace) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Every safe document beneath ``spec/``, plus a diagnostic for each excluded one.

    Nested archives, roadmaps and system maps are documents; discovery is not
    limited to ``spec/changes/*/spec.html``.
    """
    diagnostics: List[Dict[str, Any]] = []
    try:
        root = workspace.resolve_relative(SPEC_DIR)
    except ProjectPathError as exc:  # pragma: no cover - SPEC_DIR is a constant
        return [], [_diag("unsafe_document_path", path=SPEC_DIR, actual=str(exc))]

    if not root.is_dir():
        return [], diagnostics

    found: List[str] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        # A hidden directory is not part of the specification tree, and walking
        # one invites `.git` on a large repository.
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(filenames):
            if not filename.lower().endswith(".html"):
                continue
            if len(found) >= MAX_DISCOVERED_DOCUMENTS:
                truncated = True
                break
            absolute = Path(dirpath) / filename
            try:
                relative = absolute.relative_to(workspace.root).as_posix()
            except ValueError:  # pragma: no cover - walk stays under root
                continue
            try:
                validate_spec_path(relative)
                workspace.resolve_relative(relative)
            except (SpecPathError, ProjectPathError) as exc:
                diagnostics.append(_diag("unsafe_document_path", path=relative, actual=str(exc)))
                continue
            found.append(relative)
        if truncated:
            break

    if truncated:
        diagnostics.append(
            _diag(
                "discovery_truncated",
                expected=MAX_DISCOVERED_DOCUMENTS,
                actual=f"more than {MAX_DISCOVERED_DOCUMENTS} documents beneath {SPEC_DIR}/",
            )
        )
    return sorted(found), diagnostics


def read_document(workspace: ProjectWorkspace, path: str) -> Optional[str]:
    """A document's content, or ``None`` when there is no such file."""
    validate_spec_path(path)
    resolved = workspace.resolve_relative(path)
    if not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8")


def document_updated_at(workspace: ProjectWorkspace, path: str) -> str:
    """When the document was last written, as an ISO timestamp."""
    validate_spec_path(path)
    return _mtime_iso(workspace.resolve_relative(path))


def document_exists(workspace: ProjectWorkspace, path: str) -> bool:
    try:
        validate_spec_path(path)
        return workspace.resolve_relative(path).is_file()
    except (SpecPathError, ProjectPathError):
        return False


def write_document(workspace: ProjectWorkspace, path: str, content: str) -> Path:
    """Write a rendered document, creating its parent directories."""
    validate_spec_path(path)
    resolved = workspace.resolve_relative(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return resolved


def move_document(workspace: ProjectWorkspace, old_path: str, new_path: str) -> Path:
    """Move a document's file, creating the destination's parents.

    A document whose file has not been written yet is not an error: the row is
    what is being renamed, and there is simply nothing on disk to carry with it.

    The old directory is pruned when the move empties it, because a document
    lives alone in its directory and leaving the husk behind would put a name
    the document no longer has back into discovery.
    """
    validate_spec_path(old_path)
    validate_spec_path(new_path)
    source = workspace.resolve_relative(old_path)
    destination = workspace.resolve_relative(new_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        source.replace(destination)
    _prune_if_empty(workspace, source.parent)
    return destination


def _prune_if_empty(workspace: ProjectWorkspace, directory: Path) -> None:
    """Remove a directory the move emptied, and never anything else.

    Deliberately not recursive and deliberately bounded to inside `spec/`: this
    deletes, so the conditions under which it deletes are the whole of what it
    does. A failure to prune is not worth failing a rename over.
    """
    spec_root = workspace.resolve_relative(SPEC_DIR)
    try:
        if directory == spec_root or spec_root not in directory.parents:
            return
        if any(directory.iterdir()):
            return
        directory.rmdir()
    except OSError:
        return


def read_index(
    workspace: ProjectWorkspace,
) -> Tuple[Optional[Manifest], str, List[Dict[str, Any]]]:
    """The document index, its state, and the diagnostics from parsing it.

    State is one of ``valid``, ``absent``, ``unreadable`` or ``invalid``. An
    index that cannot be parsed never silences the documents around it — the
    caller still lists what discovery found.
    """
    try:
        resolved = workspace.resolve_relative(INDEX_RELATIVE)
    except ProjectPathError as exc:  # pragma: no cover - INDEX_RELATIVE is a constant
        return None, "unreadable", [_diag("index_unreadable", actual=str(exc))]

    if not resolved.is_file():
        return None, "absent", []

    try:
        if resolved.stat().st_size > MANIFEST_MAX_BYTES:
            return (
                None,
                "unreadable",
                [
                    _diag(
                        "index_unreadable",
                        expected=MANIFEST_MAX_BYTES,
                        actual="index exceeds the maximum size",
                    )
                ],
            )
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "unreadable", [_diag("index_unreadable", actual=str(exc))]

    manifest, parse_diagnostics = load_manifest(raw)
    if manifest is None:
        return None, "invalid", [d.to_dict() for d in parse_diagnostics]
    return manifest, "valid", [d.to_dict() for d in parse_diagnostics]


def build_index(
    on_disk: List[str],
    documents: List[Tuple[str, str, str, str]],
    existing: Optional[Manifest],
    home: Optional[str] = None,
) -> Tuple[Optional[Manifest], List[Dict[str, Any]]]:
    """Assemble the manifest for a project, preserving whatever arrangement is already recorded.

    Takes plain data rather than a database session on purpose: this module resolves paths and
    reads files, and has never reached the database. `documents` is ``(path, title, kind, phase)``
    per row, and the caller does the query.

    **Only documents that are both on disk and known to the Hub are filed.** A row whose file is
    gone would become a `missing_document` the moment it was written, and a file with no row has
    no title or kind to record — neither is something to invent here.

    Preservation is the whole point of reading `existing` first: `parent` and `order` are the
    operator's arrangement, they have no column to live in, and a rebuild that recomputed them
    would silently discard the only copy.
    """
    diagnostics: List[Dict[str, Any]] = []
    known = {path: (title, kind, phase) for path, title, kind, phase in documents}
    available = [path for path in on_disk if path in known]

    for path in on_disk:
        if path not in known:
            # Reported rather than filed: the Hub has no title or kind for it, and guessing one
            # would put an invented name into a file that outlives this machine.
            diagnostics.append(_diag("unindexable_document", path=path))

    previous = existing.by_path() if existing is not None else {}
    ordered_paths = sorted(available)

    # A document added to an already-arranged corpus is placed *after* everything the operator has
    # ordered, not renumbered from one. Numbering from position alone let a new document collide
    # with an existing order — adding a 34th document to a 33-document corpus produced three
    # entries all claiming order 10, and `order` carries no uniqueness constraint to catch it, so
    # the display order among the tie was arbitrary. Found by adding a system map to an imported
    # corpus, 2026-08-20.
    carried_orders = [
        previous[path].order for path in ordered_paths if previous.get(path) is not None
    ]
    next_order = (max(carried_orders) + 10) if carried_orders else 10

    entries: List[ManifestDocument] = []
    for path in ordered_paths:
        title, kind, phase = known[path]
        carried = previous.get(path)
        if carried is not None:
            order = carried.order
        else:
            order = next_order
            next_order += 10
        entries.append(
            ManifestDocument(
                path=path,
                title=title,
                kind=kind,
                status=phase,
                # `parent` is carried or left unset — never derived from directory nesting.
                # `spec/capabilities/a/spec.html` and `spec/changes/b/spec.html` share no
                # meaningful parent document, and inventing one writes a hierarchy the operator
                # never chose into a file that travels with the folder.
                parent=carried.parent if carried is not None else None,
                # Order is carried where recorded, otherwise derived from a stable sort by path.
                # Deliberately not creation order: that would make the file's contents depend on
                # database rows which do not travel with it, so the same corpus would order
                # differently on another machine.
                order=order,
            )
        )

    if not entries:
        return None, diagnostics

    paths = [entry.path for entry in entries]
    if home is not None:
        # The operator is answering the question `_select_home` refuses to answer, so their answer
        # wins over anything recorded. It still has to name a document that exists.
        if home not in paths:
            diagnostics.append(_diag("home_missing", path=home))
            home = None
    else:
        home, home_diagnostics = _select_home(existing, paths)
        diagnostics.extend(home_diagnostics)

    manifest = build_manifest(entries, home)
    if manifest is None:
        # `build_manifest` refuses without a usable home, and `_select_home` refuses to invent one
        # when the choice is the operator's. Nothing is written rather than a home being guessed.
        diagnostics.append(_diag("index_home_required", actual="no home is recorded"))
    return manifest, diagnostics


def write_index(workspace: ProjectWorkspace, manifest: Manifest) -> Path:
    """Write `spec/index.json`. The only thing here that puts a manifest on disk."""
    resolved = workspace.resolve_relative(INDEX_RELATIVE)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(dump_manifest(manifest), encoding="utf-8")
    return resolved


def corpus_summaries(workspace: ProjectWorkspace, manifest: Manifest) -> Dict[str, str]:
    """Every manifest document's summary, read once per rebuild.

    corpus-aware-documents §1.5: a rebuild re-renders a bounded set of documents (design D2), and
    each one's map can list several children — so summaries are read in a single pass over the
    corpus here, keyed by path, rather than once per child per document rendered. A document with
    no file, no payload, or no non-empty `summary` field is simply absent from the result; the
    renderer decides what an absent summary looks like (§3.4), not this function.
    """
    summaries: Dict[str, str] = {}
    for document in manifest.documents:
        content = read_document(workspace, document.path)
        if content is None:
            continue
        stored = extract_payload(content)
        if stored is None:
            continue
        summary = stored.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries[document.path] = summary.strip()
    return summaries


def _children_of(
    manifest: Manifest, path: str, summaries: Dict[str, str], *, recursive: bool
) -> Tuple[CorpusChild, ...]:
    """Direct children of `path`, each carrying its own descendant tree only when `recursive`.

    §3.6, decision D-S2-recursive: the home's map is the whole corpus; everywhere else it is one
    level. `build_corpus_context` is the only caller and decides which this is — this function
    just recurses or doesn't. `context.children` itself is always direct children regardless
    (`test_a_grandchild_is_not_a_child` pins that for navigation, §1/§2); recursion only ever adds
    depth *inside* a child's own `.children`, never widens the top level.
    """
    return tuple(
        CorpusChild(
            path=child.path,
            title=child.title,
            kind=child.kind,
            phase=child.status,
            summary=summaries.get(child.path, ""),
            children=(
                _children_of(manifest, child.path, summaries, recursive=True) if recursive else ()
            ),
        )
        for child in sorted(
            (doc for doc in manifest.documents if doc.parent == path),
            key=lambda doc: doc.order,
        )
    )


def build_corpus_context(manifest: Manifest, path: str, summaries: Dict[str, str]) -> CorpusContext:
    """The corpus context `render_document` takes for the document at `path`.

    Pure over data already in hand — the manifest and a summaries map built once by
    `corpus_summaries` — so building context for every document a rebuild re-renders costs no
    additional file reads beyond that one pass (§1.5).

    `path` need not itself be in the manifest (a document being rendered for the first time, before
    its own row and index entry exist, still has a home and can still be somebody's child once
    filed); it can then have no parent and no children of its own.
    """
    by_path = manifest.by_path()

    parent: Optional[Tuple[str, str]] = None
    entry = by_path.get(path)
    if entry is not None and entry.parent is not None:
        parent_entry = by_path.get(entry.parent)
        if parent_entry is not None:
            parent = (parent_entry.path, parent_entry.title)

    children = _children_of(manifest, path, summaries, recursive=(path == manifest.home))

    return CorpusContext(path=path, home=manifest.home, parent=parent, children=children)


def _read_head(workspace: ProjectWorkspace, path: str) -> Optional[str]:
    try:
        resolved = workspace.resolve_relative(path)
    except ProjectPathError:  # pragma: no cover - path already validated
        return None
    if not resolved.is_file():
        return None
    try:
        with resolved.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(HTML_HEAD_MAX_BYTES)
    except OSError:
        return None


def _select_home(
    manifest: Optional[Manifest], on_disk: List[str]
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Preserve an explicit home; ask rather than choose when it is ambiguous.

    The previous implementation fell back to ``spec/spec.html`` and then to the
    first document alphabetically. That is a choice made on the operator's
    behalf, and it is indistinguishable from a home they set. The shell still
    resolves a document to display; what it must not do is call the result an
    editorial decision.
    """
    available = set(on_disk)

    if manifest is not None:
        if manifest.home in available:
            return manifest.home, []
        # The index names a home that is not on disk. Substituting another
        # document would make a broken index look like an editorial decision,
        # which is the failure this requirement exists to prevent.
        return None, [_diag("home_missing", path=manifest.home)]

    # No usable index, so `home` was never recorded. A single document is the
    # only candidate there is; more than one is a choice, and the choice is the
    # operator's. The shell still resolves something to display — what it must
    # not do is report that resolution as a home the operator set.
    if not available:
        return None, []
    if len(available) == 1:
        return on_disk[0], []
    return None, [_diag("home_ambiguous", actual=", ".join(sorted(available)))]


def compute_state(workspace: ProjectWorkspace) -> DocumentTreeState:
    """The tree as it is on disk, with the index's own state reported alongside."""
    on_disk, diagnostics = discover(workspace)
    manifest, index_state, index_diagnostics = read_index(workspace)
    diagnostics = list(diagnostics) + list(index_diagnostics)

    by_path = manifest.by_path() if manifest is not None else {}

    specs: List[Dict[str, Any]] = []
    for relative in on_disk:
        resolved = workspace.resolve_relative(relative)
        entry: Dict[str, Any] = {"path": relative, "updated_at": _mtime_iso(resolved)}
        document = by_path.get(relative)
        if document is not None:
            entry.update(
                title=document.title,
                kind=document.kind,
                status=document.status,
                parent=document.parent,
                order=document.order,
                state="filed",
            )
        elif manifest is None:
            # There is no usable index to be unfiled from. The document is
            # available; saying it has drifted would be reporting the index's
            # absence twice.
            entry["state"] = "unindexed"
        else:
            entry["state"] = "unfiled"
            diagnostics.append(_diag("unfiled_document", path=relative))
        specs.append(entry)

    missing: List[Dict[str, Any]] = []
    if manifest is not None:
        available = set(on_disk)
        for document in manifest.documents:
            if document.path in available:
                continue
            # Retained, never discarded: an entry with no file could be a
            # deliberate deletion, a rename the index missed, or a document
            # that was never written. The Hub cannot tell them apart, so it
            # reports rather than decides.
            missing.append(
                {
                    "path": document.path,
                    "title": document.title,
                    "kind": document.kind,
                    "status": document.status,
                    "parent": document.parent,
                    "order": document.order,
                }
            )
            diagnostics.append(_diag("missing_document", path=document.path))

        heads: Dict[str, str] = {}
        for document in manifest.documents:
            if document.path not in available:
                continue
            head = _read_head(workspace, document.path)
            if head is not None:
                heads[document.path] = head
        for conflict in compute_intrinsic_conflicts(manifest, heads):
            diagnostics.append(conflict.to_dict())

    home, home_diagnostics = _select_home(manifest, on_disk)
    diagnostics.extend(home_diagnostics)

    def _sort_key(entry: Dict[str, Any]) -> Tuple[int, Any, str]:
        if entry.get("state") == "filed":
            return (0, entry["order"], entry["path"])
        return (1, entry["path"] != "spec/spec.html", entry["path"])

    specs.sort(key=_sort_key)

    index_summary: Dict[str, Any] = {
        "state": index_state,
        "version": manifest.version if manifest is not None else None,
    }

    return DocumentTreeState(
        specs=specs,
        home=home,
        index=index_summary,
        missing=missing,
        diagnostics=diagnostics,
    )
