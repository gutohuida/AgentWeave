"""Saving a submitted payload: validate, mint, render, write, record.

One function does the whole write because the steps are not independently
useful and half of them leaving a trace would be worse than none. A payload that
fails validation must leave the file exactly as it was — no partial document —
so nothing touches disk until everything that can be refused has been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_completeness, spec_documents, spec_identity, spec_lifecycle
from .db.models import SpecDocument
from .project_workspace import ProjectWorkspace
from .spec_payload import PayloadError, extract_payload, payload_to_dict, validate_payload
from .spec_render import render_document


@dataclass
class SaveResult:
    path: str
    phase: str
    identifiers: Dict[str, str] = field(default_factory=dict)
    blocking: List[Dict[str, Any]] = field(default_factory=list)
    divergence: Optional[Dict[str, str]] = None


class SaveRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """The submission cannot be stored, with the reason and where it applies."""

    def __init__(self, message: str, *, code: str, field_path: str = "") -> None:
        self.code = code
        self.field_path = field_path
        super().__init__(message)


async def save_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    raw_payload: Any,
    *,
    actor: spec_lifecycle.Actor,
) -> SaveResult:
    """Store a submission against an existing document.

    Incompleteness is reported, not refused: a document under discussion is
    incomplete by definition, and it is the transition to `proposed` that cares.
    What *is* refused is a submission against an approved document — silently
    rewriting what an operator approved would make the approval meaningless.
    """
    if document.phase == spec_lifecycle.APPROVED:
        raise SaveRefusedError(
            "this document is approved; reopen it before changing what was approved",
            code="document_approved",
        )

    try:
        payload = validate_payload(raw_payload)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    # Identity carries forward from whatever is on disk, so a key that already
    # holds an identifier keeps it. A file that has been replaced by hand simply
    # has no identity block, and every key is then new — which is why the
    # divergence below is reported rather than swallowed.
    existing_content = spec_documents.read_document(workspace, document.path)
    stored_before = extract_payload(existing_content) if existing_content else None
    previous_map, high_water = spec_identity.read_identity(stored_before)

    keys = [requirement.key for requirement in payload.requirements]
    identifiers, mark = spec_identity.mint(keys, previous_map, high_water)
    retired = spec_identity.retained(previous_map, keys)

    stored = payload_to_dict(payload)
    # Hub-owned, and overwritten unconditionally. An agent that submits an
    # identity block does not get to keep it.
    stored[spec_identity.IDENTITY_FIELD] = spec_identity.identity_block(identifiers, mark, retired)

    content = render_document(
        payload,
        identifiers,
        phase=document.phase,
        stored_payload=stored,
    )

    divergence = spec_lifecycle.divergence(document, existing_content)

    spec_documents.write_document(workspace, document.path, content)

    statements = {
        identifiers[requirement.key]: requirement.statement
        for requirement in payload.requirements
        if requirement.key in identifiers
    }
    await spec_lifecycle.record_content(
        session,
        document,
        actor=actor,
        content=content,
        statements=statements,
        title=payload.title,
        kind=payload.kind,
    )

    return SaveResult(
        path=document.path,
        phase=document.phase,
        identifiers=identifiers,
        blocking=[finding.to_dict() for finding in spec_completeness.check(payload)],
        divergence=({"recorded": divergence[0], "found": divergence[1]} if divergence else None),
    )


async def propose(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    *,
    actor: spec_lifecycle.Actor,
) -> List[Dict[str, Any]]:
    """Move a document to `proposed`, or return what is blocking it.

    The completeness checks run against the payload the document actually
    carries, not against a claim about it. A document whose file no longer
    parses cannot be proposed at all — there is nothing to check.
    """
    content = spec_documents.read_document(workspace, document.path)
    stored = extract_payload(content) if content else None
    if stored is None:
        raise SaveRefusedError(
            "this document carries no payload to check; it has not been written by the Hub",
            code="no_payload",
        )

    try:
        payload = validate_payload(stored)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    findings = spec_completeness.check(payload)
    if findings:
        return [finding.to_dict() for finding in findings]

    await spec_lifecycle.transition(
        session, document, to_phase=spec_lifecycle.PROPOSED, actor=actor
    )
    await rerender_phase(session, workspace, document)
    return []


async def rerender_phase(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
) -> None:
    """Rewrite the document so its visible status matches the phase.

    The metadata in the file is a copy for whoever reads it, never the
    authority. It is refreshed here so the two do not disagree in front of an
    operator — but if this fails, the phase in the database is still what
    counts.
    """
    content = spec_documents.read_document(workspace, document.path)
    stored = extract_payload(content) if content else None
    if stored is None:
        return
    try:
        payload = validate_payload(stored)
    except PayloadError:
        return
    identifiers, _ = spec_identity.read_identity(stored)
    rewritten = render_document(payload, identifiers, phase=document.phase, stored_payload=stored)
    spec_documents.write_document(workspace, document.path, rewritten)
    document.content_digest = spec_lifecycle.digest(rewritten)
