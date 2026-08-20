"""Spec manifest: safe path validation, manifest structural validation, and
HTML `<head>` metadata parsing — the Hub's own copy.

The Hub is a separate deployable from the CLI and is the actual security
boundary for spec sync, so it repeats this validation independently rather
than importing `agentweave.spec_manifest`. Keep the two in sync by hand;
they intentionally have no import relationship. See
`src/agentweave/spec_manifest.py` for the CLI-side twin (used for local
discovery, which the Hub does not do — it only ever sees uploaded content).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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

# A document's index status is its lifecycle phase — the value `spec_render` writes into the
# rendered document's own `aw-spec-status`, and therefore the value `compute_intrinsic_conflicts`
# compares an entry against. These mirror `hub/hub/spec_lifecycle.py` and are restated rather than
# imported: this module is carried verbatim in the CLI twin, which has no lifecycle module. The
# twin-agreement test is what holds the two copies together.
EXPLORING = "exploring"
PROPOSED = "proposed"
APPROVED = "approved"
ARCHIVED = "archived"
CURRENT = "current"

#: Phases reached by walking `spec_lifecycle.TRANSITIONS` from a document's creation.
LIFECYCLE_PHASES = {EXPLORING, PROPOSED, APPROVED, ARCHIVED}

#: A capability document is created at `current` and never leaves it — `TRANSITIONS` holds no pair
#: whose source is `current`, and `transition()` refuses it as a destination. So `current` is not
#: one phase among five for a capability; it is the only one it can ever have.
CAPABILITY_KIND = "capability"
CAPABILITY_PHASES = {CURRENT}

VALID_PHASES = LIFECYCLE_PHASES | CAPABILITY_PHASES

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")


class SpecPathError(ValueError):
    """A candidate spec path fails the safe-path contract."""


def validate_spec_path(path: str) -> str:
    """Validate a repo-relative spec HTML path (see CLI twin for full contract)."""
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
        }


def permitted_phases(kind: str) -> Set[str]:
    """The phases a document of this kind can actually hold.

    Validating the pair rather than each field independently is what catches an entry that is
    individually well-formed but describes a document the product cannot produce — a capability
    marked `approved`, say, which reads as plausible and is unreachable.
    """
    return set(CAPABILITY_PHASES) if kind == CAPABILITY_KIND else set(LIFECYCLE_PHASES)


def load_manifest(raw_text: str) -> Tuple[Optional[Manifest], List[ManifestDiagnostic]]:
    """Parse and structurally validate `spec/index.json` text.

    Identical contract to the CLI twin: returns (manifest, diagnostics);
    `manifest` is None on any structural violation, `diagnostics` reports
    every violation found in a single pass.
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

    home = raw.get("home")
    if not isinstance(home, str) or home not in doc_paths:
        diagnostics.append(ManifestDiagnostic(code="manifest_invalid_home", actual=str(home)))
        return None, diagnostics

    return Manifest(version=MANIFEST_VERSION, home=home, documents=tuple(documents)), diagnostics


def dump_manifest(manifest: Manifest) -> str:
    """Serialise a manifest to `spec/index.json` text.

    Pure: manifest in, text out, no filesystem — `spec_documents.write_index` is the only thing
    that touches disk. That split is what lets the round trip
    (`load_manifest(dump_manifest(m)) == m`) be tested without a workspace, and lets the CLI twin
    carry the same serialisation despite having no `ProjectWorkspace`.

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

    `home` is not defaulted here. `spec_documents._select_home` refuses to choose one on read,
    on the grounds that a guess is indistinguishable from an operator's decision; a writer that
    quietly picked one would smuggle in exactly the choice the reader declines to make.
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


def parse_html_head(text: str) -> Dict[str, Optional[str]]:
    """Extract title/kind/status from an HTML document's `<head>` (bounded)."""
    bounded = text.encode("utf-8")[:HTML_HEAD_MAX_BYTES].decode("utf-8", errors="ignore")
    parser = _SpecHeadParser()
    try:
        parser.feed(bounded)
        parser.close()
    except Exception:
        pass
    title = parser.title.strip() if parser.title else None
    return {"title": title or None, "kind": parser.kind, "status": parser.status}


def compute_intrinsic_conflicts(
    manifest: Manifest, content_by_path: Dict[str, str]
) -> List[ManifestDiagnostic]:
    """Compare each manifest document's cached title/kind/status against the
    live HTML `<head>` of its synced content (documents present in both).
    """
    diagnostics: List[ManifestDiagnostic] = []
    for doc in manifest.documents:
        content = content_by_path.get(doc.path)
        if content is None:
            continue
        head = parse_html_head(content)
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
