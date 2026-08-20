"""Spec manifest: safe path validation, recursive discovery, manifest structural
validation, and HTML `<head>` metadata parsing.

Stdlib only (json, re, pathlib, html.parser). Used by the watchdog, the HTTP
transport, and `agentweave spec push`. The Hub is a separate deployable and
repeats path/manifest validation itself rather than importing this module —
see `hub/hub/spec_manifest.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

MANIFEST_VERSION = 1
MANIFEST_MAX_BYTES = 256 * 1024
MANIFEST_MAX_DOCUMENTS = 1000
SPEC_PATH_MAX_LENGTH = 255
HTML_HEAD_MAX_BYTES = 64 * 1024

# Every kind `submit_spec_document` accepts. The two vocabularies were introduced at different
# times and diverged: `capability` shipped with the phase lifecycle on 2026-08-16 and was never
# added here, so a capability document the Hub itself rendered could not be described by an index
# the Hub itself validated. One list, deliberately.
VALID_KINDS = {"baseline", "system-map", "roadmap", "change-spec", "capability"}

# A document's index status is its lifecycle phase — the value the Hub's renderer writes into the
# rendered document's own `aw-spec-status`, and therefore the value `compute_intrinsic_conflicts`
# compares an entry against. These mirror `hub/hub/spec_lifecycle.py`; this module and its Hub twin
# deliberately have no import relationship, so a test asserts the two agree.
EXPLORING = "exploring"
PROPOSED = "proposed"
APPROVED = "approved"
ARCHIVED = "archived"
CURRENT = "current"

#: Phases reached by walking the Hub's transition table from a document's creation.
LIFECYCLE_PHASES = {EXPLORING, PROPOSED, APPROVED, ARCHIVED}

#: A capability document is created at `current` and never leaves it — the Hub's transition table
#: holds no pair whose source is `current`, and refuses it as a destination. So `current` is not
#: one phase among five for a capability; it is the only one it can ever have.
CAPABILITY_KIND = "capability"
CAPABILITY_PHASES = {CURRENT}

VALID_PHASES = LIFECYCLE_PHASES | CAPABILITY_PHASES

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")


class SpecPathError(ValueError):
    """A candidate spec path fails the safe-path contract."""


def validate_spec_path(path: str) -> str:
    """Validate a repo-relative spec HTML path.

    MUST be a normalized, lowercase, POSIX path beneath `spec/`, ending in
    `.html`, with no empty/dot/dot-dot/hidden/control-character segment and
    no backslash. Returns the path unchanged; raises SpecPathError otherwise.
    """
    if not isinstance(path, str) or not path:
        raise SpecPathError(f"path must be a non-empty string: {path!r}")
    if "\\" in path:
        raise SpecPathError(f"path must use POSIX separators: {path!r}")
    if path != path.lower():
        raise SpecPathError(f"path must be lowercase: {path!r}")
    if len(path) > SPEC_PATH_MAX_LENGTH:
        raise SpecPathError(f"path exceeds {SPEC_PATH_MAX_LENGTH} characters: {path!r}")
    if not path.startswith("spec/"):
        raise SpecPathError(f"path must begin with 'spec/': {path!r}")
    if not path.endswith(".html"):
        raise SpecPathError(f"path must end with '.html': {path!r}")
    for segment in path.split("/"):
        if not segment or segment in (".", ".."):
            raise SpecPathError(f"path has an empty or dot segment: {path!r}")
        if segment.startswith("."):
            raise SpecPathError(f"path has a hidden segment: {path!r}")
        if _CONTROL_CHAR_RE.search(segment):
            raise SpecPathError(f"path has a control character: {path!r}")
    return path


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    path: str
    reason: str


def discover_spec_files(
    root: Path = Path("spec"),
) -> Tuple[Dict[str, Path], List[DiscoveryDiagnostic]]:
    """Recursively discover safe `.html` files beneath `root`, sorted by path.

    Never raises. Returns (discovered path -> local Path, diagnostics for
    every rejected candidate) so unsafe or unreadable files degrade to
    visible drift instead of being silently dropped or aborting discovery.
    """
    discovered: Dict[str, Path] = {}
    diagnostics: List[DiscoveryDiagnostic] = []
    if not root.is_dir():
        return discovered, diagnostics
    try:
        root_resolved = root.resolve()
    except OSError:
        return discovered, diagnostics

    for candidate in sorted(root.rglob("*.html")):
        rel = candidate.as_posix()
        if not candidate.is_file():
            diagnostics.append(DiscoveryDiagnostic(path=rel, reason="not a regular file"))
            continue
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            diagnostics.append(DiscoveryDiagnostic(path=rel, reason=f"cannot resolve: {exc}"))
            continue
        if resolved != root_resolved and root_resolved not in resolved.parents:
            diagnostics.append(DiscoveryDiagnostic(path=rel, reason="resolves outside spec/"))
            continue
        try:
            validate_spec_path(rel)
        except SpecPathError as exc:
            diagnostics.append(DiscoveryDiagnostic(path=rel, reason=str(exc)))
            continue
        discovered[rel] = candidate

    return discovered, diagnostics


@dataclass(frozen=True)
class ManifestDocument:
    path: str
    title: str
    kind: str
    status: str
    parent: Optional[str]
    order: int


@dataclass(frozen=True)
class Manifest:
    version: int
    home: str
    documents: Tuple[ManifestDocument, ...]

    def by_path(self) -> Dict[str, ManifestDocument]:
        return {doc.path: doc for doc in self.documents}


@dataclass(frozen=True)
class ManifestDiagnostic:
    code: str
    path: Optional[str] = None
    field: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None


def permitted_phases(kind: str) -> Set[str]:
    """The phases a document of this kind can actually hold.

    Validating the pair rather than each field independently is what catches an entry that is
    individually well-formed but describes a document the product cannot produce — a capability
    marked `approved`, say, which reads as plausible and is unreachable.
    """
    return set(CAPABILITY_PHASES) if kind == CAPABILITY_KIND else set(LIFECYCLE_PHASES)


def load_manifest(raw_text: str) -> Tuple[Optional[Manifest], List[ManifestDiagnostic]]:
    """Parse and structurally validate `spec/index.json` text.

    Returns (manifest, diagnostics). `manifest` is None whenever any
    structural violation is found — an invalid manifest is never treated as
    partially authoritative. `diagnostics` reports every violation detected
    in a single pass, not just the first.
    """
    if len(raw_text.encode("utf-8")) > MANIFEST_MAX_BYTES:
        return None, [ManifestDiagnostic(code="manifest_too_large")]
    try:
        raw = json.loads(raw_text)
    except (ValueError, TypeError):
        return None, [ManifestDiagnostic(code="manifest_invalid_json")]
    if not isinstance(raw, dict):
        return None, [ManifestDiagnostic(code="manifest_invalid_json")]

    if raw.get("version") != MANIFEST_VERSION:
        return None, [
            ManifestDiagnostic(code="manifest_unsupported_version", actual=str(raw.get("version")))
        ]

    raw_documents = raw.get("documents")
    if not isinstance(raw_documents, list):
        return None, [ManifestDiagnostic(code="manifest_invalid_structure", field="documents")]
    if len(raw_documents) > MANIFEST_MAX_DOCUMENTS:
        return None, [ManifestDiagnostic(code="manifest_too_many_documents")]

    diagnostics: List[ManifestDiagnostic] = []
    documents: List[ManifestDocument] = []
    seen_paths: Set[str] = set()
    ok = True

    for entry in raw_documents:
        if not isinstance(entry, dict):
            diagnostics.append(ManifestDiagnostic(code="manifest_invalid_document"))
            ok = False
            continue

        raw_path = entry.get("path")
        try:
            path = validate_spec_path(raw_path) if isinstance(raw_path, str) else None
            if path is None:
                raise SpecPathError("missing path")
        except SpecPathError:
            diagnostics.append(ManifestDiagnostic(code="manifest_unsafe_path", path=str(raw_path)))
            ok = False
            continue

        if path in seen_paths:
            diagnostics.append(ManifestDiagnostic(code="manifest_duplicate_path", path=path))
            ok = False
            continue
        seen_paths.add(path)

        kind = entry.get("kind")
        if kind not in VALID_KINDS:
            diagnostics.append(
                ManifestDiagnostic(code="manifest_invalid_kind", path=path, actual=str(kind))
            )
            ok = False
            continue

        status = entry.get("status")
        if not isinstance(status, str) or status not in VALID_PHASES:
            diagnostics.append(
                ManifestDiagnostic(
                    code="manifest_invalid_phase",
                    path=path,
                    field="status",
                    expected="|".join(sorted(VALID_PHASES)),
                    actual=str(status),
                )
            )
            ok = False
            continue

        allowed = permitted_phases(kind)
        if status not in allowed:
            diagnostics.append(
                ManifestDiagnostic(
                    code="manifest_kind_status_mismatch",
                    path=path,
                    field="status",
                    expected="|".join(sorted(allowed)),
                    actual=status,
                )
            )
            ok = False
            continue

        order = entry.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            diagnostics.append(ManifestDiagnostic(code="manifest_invalid_order", path=path))
            ok = False
            continue

        title = entry.get("title")
        if not isinstance(title, str) or not title:
            diagnostics.append(ManifestDiagnostic(code="manifest_invalid_title", path=path))
            ok = False
            continue

        parent = entry.get("parent")
        if parent is not None and not isinstance(parent, str):
            diagnostics.append(ManifestDiagnostic(code="manifest_invalid_parent", path=path))
            ok = False
            continue
        if parent == path:
            diagnostics.append(ManifestDiagnostic(code="manifest_self_parent", path=path))
            ok = False
            continue

        documents.append(
            ManifestDocument(
                path=path, title=title, kind=kind, status=status, parent=parent, order=order
            )
        )

    if not ok:
        return None, diagnostics

    doc_paths = {doc.path for doc in documents}
    for doc in documents:
        if doc.parent is not None and doc.parent not in doc_paths:
            diagnostics.append(
                ManifestDiagnostic(code="manifest_unknown_parent", path=doc.path, actual=doc.parent)
            )
            ok = False
    if not ok:
        return None, diagnostics

    by_path = {doc.path: doc for doc in documents}
    for doc in documents:
        seen: Set[str] = set()
        current: Optional[str] = doc.path
        while current is not None:
            if current in seen:
                diagnostics.append(ManifestDiagnostic(code="manifest_parent_cycle", path=doc.path))
                ok = False
                break
            seen.add(current)
            parent_doc = by_path.get(current)
            current = parent_doc.parent if parent_doc else None
    if not ok:
        return None, diagnostics

    # `order` exists only to be compared against the other documents' orders, so a duplicate makes
    # the arrangement undefined for exactly the documents that collide — and it is invisible
    # otherwise, because each entry is individually well-formed. Checked last, with paths and
    # parents already known good, so the diagnostic names a real document.
    #
    # This was a live defect rather than a hypothetical: the writer placed a document added to an
    # already-arranged corpus at an order the corpus was using, and nothing caught it.
    by_order: Dict[int, List[str]] = {}
    for doc in documents:
        by_order.setdefault(doc.order, []).append(doc.path)
    for order, paths in sorted(by_order.items()):
        if len(paths) > 1:
            diagnostics.append(
                ManifestDiagnostic(
                    code="manifest_duplicate_order",
                    path=paths[0],
                    field="order",
                    expected="an order no other document holds",
                    actual=f"{order} is also held by {', '.join(sorted(paths[1:]))}",
                )
            )
            ok = False
    if not ok:
        return None, diagnostics

    home = raw.get("home")
    if not isinstance(home, str) or home not in doc_paths:
        diagnostics.append(ManifestDiagnostic(code="manifest_invalid_home", actual=str(home)))
        return None, diagnostics

    return Manifest(version=MANIFEST_VERSION, home=home, documents=tuple(documents)), diagnostics


def dump_manifest(manifest: Manifest) -> str:
    """Serialise a manifest to `spec/index.json` text.

    Pure: manifest in, text out, no filesystem. The Hub twin's
    `spec_documents.write_index` is what touches disk there; keeping serialisation separate is
    what lets the round trip (`load_manifest(dump_manifest(m)) == m`) be tested without a
    workspace, and lets this module carry it despite having no `ProjectWorkspace`.

    Output is byte-stable for a given manifest: documents keep the manifest's own order and keys
    are emitted in a fixed order. A rebuild that changed nothing must produce an identical file,
    or every rebuild looks like an edit to whatever is watching the tree.
    """
    payload = {
        "version": manifest.version,
        "home": manifest.home,
        "documents": [
            {
                "path": document.path,
                "title": document.title,
                "kind": document.kind,
                "status": document.status,
                "parent": document.parent,
                "order": document.order,
            }
            for document in manifest.documents
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def build_manifest(
    documents: Iterable[ManifestDocument], home: Optional[str]
) -> Optional[Manifest]:
    """A manifest from entries already carrying their arrangement, or None with no usable home.

    `home` is not defaulted here. The Hub's reader refuses to choose one, on the grounds that a
    guess is indistinguishable from an operator's decision; a writer that quietly picked one would
    smuggle in exactly the choice the reader declines to make.
    """
    ordered = tuple(documents)
    if not ordered:
        return None
    paths = {document.path for document in ordered}
    if home is None or home not in paths:
        return None
    return Manifest(version=MANIFEST_VERSION, home=home, documents=ordered)


class _SpecHeadParser(HTMLParser):
    """Extracts <title>, aw-spec-kind, and aw-spec-status; stops after </head>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: Optional[str] = None
        self.kind: Optional[str] = None
        self.status: Optional[str] = None
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self.done:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            attr_map = dict(attrs)
            name = attr_map.get("name")
            content = attr_map.get("content")
            if name == "aw-spec-kind" and content:
                self.kind = content
            elif name == "aw-spec-status" and content:
                self.status = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.done:
            self.title = (self.title or "") + data


def compute_intrinsic_conflicts(
    manifest: Manifest, discovered: Dict[str, Path]
) -> List[ManifestDiagnostic]:
    """Compare each manifest document's cached title/kind/status against the
    live HTML `<head>` of its discovered file (documents present in both).

    Missing documents (in the manifest but not discovered) are not reported
    here — that is the separate "missing" diagnostic, not an intrinsic
    conflict.
    """
    diagnostics: List[ManifestDiagnostic] = []
    for doc in manifest.documents:
        file_path = discovered.get(doc.path)
        if file_path is None:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        head = parse_html_head(text)
        for field, expected, actual in (
            ("title", doc.title, head["title"]),
            ("kind", doc.kind, head["kind"]),
            ("status", doc.status, head["status"]),
        ):
            if actual is not None and actual != expected:
                diagnostics.append(
                    ManifestDiagnostic(
                        code="intrinsic_metadata_conflict",
                        path=doc.path,
                        field=field,
                        expected=str(expected),
                        actual=str(actual),
                    )
                )
    return diagnostics


def parse_html_head(text: str) -> Dict[str, Optional[str]]:
    """Extract title/kind/status from an HTML document's `<head>`.

    Only the first HTML_HEAD_MAX_BYTES are parsed — bounded, since these
    three values always appear early and the rest of the document (often
    large, inlined CSS/JS) is irrelevant here.
    """
    bounded = text.encode("utf-8")[:HTML_HEAD_MAX_BYTES].decode("utf-8", errors="ignore")
    parser = _SpecHeadParser()
    try:
        parser.feed(bounded)
        parser.close()
    except Exception:
        pass
    title = parser.title.strip() if parser.title else None
    return {"title": title or None, "kind": parser.kind, "status": parser.status}
