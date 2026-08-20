"""Reading a document's identity from the file, so an existing file can become a row.

A specification document is a file plus a row. The file is committed and travels
between machines; the row is machine-local and does not. Every capability except
the read path is keyed on the row, so a corpus that arrives without one — a
clone, a migration, a restored machine — is readable and inert.

**This module never writes to disk, and that is structural rather than a
convention.** It imports nothing that writes: `read_document` and
`parse_html_head` read, `extract_payload` parses a string. The one function here
that reaches the database (`adopt`) calls `spec_lifecycle.create_document`, which
takes no workspace and therefore *cannot* touch the filesystem. A reviewer
checking that adoption is read-only does not have to read the whole call tree —
there is no writer in it to find.

Identity is read from two places in one file, because no single place carries all
of it:

    title, kind   <- the `aw-spec-payload` block; what the submission supplied
    phase         <- the `aw-spec-status` meta tag; the payload has no status key

The payload wins for `kind`, which appears in both: the meta tag is its display
copy. Where the status names no phase this Hub knows, the phase falls back to
what a newly created document of that kind would receive, and the fallback is
*reported* — a defaulted phase must never be mistaken for one that was read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import spec_documents, spec_lifecycle
from .db.models import SpecDocument
from .project_workspace import ProjectPathError, ProjectWorkspace
from .spec_manifest import SpecPathError, parse_html_head, validate_spec_path
from .spec_payload import KINDS, extract_payload, has_payload_block

#: Every phase a row may hold. `current` is included and `transition()` never
#: accepts it — a capability document reaches it through creation only, which is
#: exactly the door adoption comes through.
PHASES = (
    spec_lifecycle.EXPLORING,
    spec_lifecycle.PROPOSED,
    spec_lifecycle.APPROVED,
    spec_lifecycle.ARCHIVED,
    spec_lifecycle.CURRENT,
)

#: The phase was taken from the document's own status metadata.
READ = "read"
#: The phase was derived from the document's kind because the file did not
#: usably state one. Reported so the two are never confused.
DEFAULTED = "defaulted"


@dataclass(frozen=True)
class AdoptableIdentity:
    """What a file says it is, and how much of that had to be assumed."""

    path: str
    title: str
    kind: str
    phase: str
    #: `READ` or `DEFAULTED` — which of the two the phase above came from.
    phase_source: str
    #: The status the file carried when it named no phase this Hub knows. `None`
    #: when the status was absent entirely, so "said nothing" and "said something
    #: unrecognised" stay distinguishable in the response.
    unrecognised_phase: Optional[str] = None
    #: The file exactly as read. Carried so the caller can digest the bytes it
    #: actually adopted rather than re-reading and racing an editor.
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "kind": self.kind,
            "phase": self.phase,
            "phase_source": self.phase_source,
            "unrecognised_phase": self.unrecognised_phase,
        }


@dataclass(frozen=True)
class AdoptionRefusal:
    """Why a path was not adopted, in terms the operator can act on."""

    path: str
    code: str
    message: str
    #: Where a row already exists, every field the file and the row disagree on.
    #: Always a list, never omitted: an absent list and an empty one must not be
    #: ambiguous to a reader (`spec-document-adoption`, "Agreement is reported as
    #: no disagreement").
    differences: Tuple["FieldDifference", ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
            "differences": [difference.to_dict() for difference in self.differences],
        }


@dataclass(frozen=True)
class FieldDifference:
    """One field on which the file and the existing row disagree, with both values."""

    field: str
    file: Optional[str]
    row: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "file": self.file, "row": self.row}


Adoptable = AdoptableIdentity | AdoptionRefusal


def default_phase_for(kind: str) -> str:
    """The phase a newly created document of this kind receives.

    Deliberately the same rule as `spec_lifecycle.create_document`, and stated
    here rather than inferred, so a file that says nothing about its phase adopts
    exactly where creating it would have put it.
    """
    return spec_lifecycle.CURRENT if kind == "capability" else spec_lifecycle.EXPLORING


def read_identity(workspace: ProjectWorkspace, path: str) -> Adoptable:
    """A document's adoptable identity, or a stated reason it cannot be adopted.

    Read-only. Resolves the path through the workspace first, so a path that
    escapes is refused *before* the file is read rather than after.
    """
    try:
        safe = validate_spec_path(path)
    except SpecPathError as exc:
        return AdoptionRefusal(path=path, code="unsafe_document_path", message=str(exc))

    try:
        content = spec_documents.read_document(workspace, safe)
    except (SpecPathError, ProjectPathError) as exc:
        return AdoptionRefusal(path=safe, code="unsafe_document_path", message=str(exc))
    except OSError as exc:
        return AdoptionRefusal(path=safe, code="file_unreadable", message=str(exc))

    if content is None:
        return AdoptionRefusal(
            path=safe,
            code="file_missing",
            message=f"no file at {safe}",
        )

    return identity_from_content(safe, content)


def identity_from_content(path: str, content: str) -> Adoptable:
    """The identity a document's own text declares, or why it declares none.

    Split from `read_identity` so the interpretation can be tested against a
    string without a workspace, and so corpus-wide adoption can read each file
    once rather than once per concern.
    """
    payload = extract_payload(content)
    if payload is None:
        # The two ways a payload can be missing need different remedies — write
        # the document through the Hub, versus repair a block that is already
        # there — so they are refused separately rather than as one "no payload".
        if has_payload_block(content):
            return AdoptionRefusal(
                path=path,
                code="payload_unreadable",
                message=(
                    "the document's payload block is present but is not readable JSON "
                    "describing an object"
                ),
            )
        return AdoptionRefusal(
            path=path,
            code="payload_absent",
            message="the document carries no aw-spec-payload block",
        )

    head = parse_html_head(content)

    title = _text(payload.get("title"))
    if not title:
        # A row with no title is not an identity, and the path is not a title:
        # deriving one would put an invented name where a reader looks for the
        # subject, in a file that outlives the machine that invented it.
        return AdoptionRefusal(
            path=path,
            code="payload_identity_missing",
            message="the document's payload declares no title",
        )

    kind = _text(payload.get("kind")) or _text(head.get("kind"))
    if kind not in KINDS:
        return AdoptionRefusal(
            path=path,
            code="payload_identity_missing",
            message=(
                f"the document's payload declares kind {kind!r}, which is not one of "
                f"{', '.join(KINDS)}"
            ),
        )

    status = _text(head.get("status"))
    if status in PHASES:
        return AdoptableIdentity(
            path=path,
            title=title,
            kind=kind,
            phase=status,
            phase_source=READ,
            content=content,
        )

    return AdoptableIdentity(
        path=path,
        title=title,
        kind=kind,
        phase=default_phase_for(kind),
        phase_source=DEFAULTED,
        # Absent status and unrecognised status default identically but are not
        # the same event, and only one of them is worth an operator's attention.
        unrecognised_phase=status or None,
        content=content,
    )


def compare(identity: AdoptableIdentity, row: SpecDocument) -> Tuple[FieldDifference, ...]:
    """Every field on which the file and an existing row disagree.

    Reporting only. Resolving the disagreement means choosing whose version wins,
    and that is a separate operator decision — see design D4, which declines to
    take it here because "trust the file" collides with the rule that a gate whose
    value lives where the gated party can write it is not a gate.
    """
    differences: List[FieldDifference] = []
    for field, from_file, from_row in (
        ("title", identity.title, row.title),
        ("kind", identity.kind, row.kind),
        ("phase", identity.phase, row.phase),
    ):
        if from_file != from_row:
            differences.append(FieldDifference(field=field, file=from_file, row=from_row))
    return tuple(differences)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
