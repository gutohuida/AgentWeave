"""The requirement index — derived from documents, authoritative over nothing.

Rebuilt from a document on every save, in the same transaction that writes the
file, so the index is never newer or older than the document it describes. Drop
both tables and a reindex restores them; that is the property that keeps this an
index rather than a second source of truth about what a requirement says.

Two rules do most of the work here:

**A removed requirement is retired, not deleted.** Its links and evidence stay
pointed at it. "What did this once demand, and what was built for it?" is asked
about work that is finished, which is exactly when the requirement is most likely
to be gone from the document.

**Every digest change is recorded before it is applied.** A revision cannot be
backfilled — once the row carries the new digest, the old meaning is unrecoverable
— so the append happens on the same pass that overwrites it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_digest, spec_identity, spec_lifecycle
from .db.models import SpecDocument, SpecRequirement, SpecRequirementRevision
from .project_workspace import ProjectWorkspace
from .spec_payload import PayloadError, extract_payload, validate_payload
from .spec_render import requirement_anchor
from .utils import short_id

ACTIVE = "active"
RETIRED = "retired"

SOURCE_HUB = "hub"
SOURCE_EXTERNAL = "external"

CREATED = "created"
REWORDED = "reworded"
RETIRED_CLASSIFICATION = "retired"
RESTORED = "restored"


@dataclass
class IndexResult:
    """What one reindex changed, for a caller that wants to report it."""

    created: List[str] = field(default_factory=list)
    reworded: List[str] = field(default_factory=list)
    retired: List[str] = field(default_factory=list)
    restored: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.reworded or self.retired or self.restored)


@dataclass(frozen=True)
class IndexedRequirement:
    """One requirement as the document currently declares it."""

    identifier: str
    key: str
    digest: str
    state: str = ACTIVE
    anchor: str = ""


def requirements_from_payload(
    payload_dict: Optional[dict],
) -> Optional[List[IndexedRequirement]]:
    """Everything a stored payload says about its requirements, live and retired.

    Returns `None` when the payload cannot be read at all — a file that was
    hand-written, or damaged mid-edit. That is deliberately distinct from "a
    document with no requirements": one is unknown and the other is empty, and
    treating the first as the second would retire every requirement in it.
    """
    if payload_dict is None:
        return None
    try:
        payload = validate_payload(payload_dict)
    except PayloadError:
        return None

    identifiers, _ = spec_identity.read_identity(payload_dict)
    retired = spec_identity.read_retired(payload_dict)
    stored_digests = spec_identity.read_digests(payload_dict)
    live_digests = spec_digest.payload_digests(payload, identifiers)

    indexed: List[IndexedRequirement] = []
    for requirement in payload.requirements:
        identifier = identifiers.get(requirement.key)
        if identifier is None:
            # No identifier means the Hub has not minted for this key yet, which
            # only happens on a payload that never went through `save_document`.
            # Indexing it under an invented handle is how a link would come to
            # point at the wrong requirement.
            continue
        indexed.append(
            IndexedRequirement(
                identifier=identifier,
                key=requirement.key,
                digest=live_digests.get(identifier, ""),
                state=ACTIVE,
                anchor=requirement_anchor(identifier),
            )
        )

    for key, identifier in sorted(retired.items()):
        digest = stored_digests.get(identifier)
        if digest is None:
            # Retired before digests were carried in the file. The row still
            # exists and still holds its links; it simply cannot claim to know
            # what it meant, and an invented digest would make stale evidence
            # look current.
            digest = ""
        indexed.append(
            IndexedRequirement(
                identifier=identifier, key=key, digest=digest, state=RETIRED, anchor=""
            )
        )

    return indexed


async def _existing(session: AsyncSession, document_id: str) -> Dict[str, SpecRequirement]:
    result = await session.execute(
        select(SpecRequirement).where(SpecRequirement.document_id == document_id)
    )
    return {row.identifier: row for row in result.scalars().all()}


def _revision(
    row: SpecRequirement,
    *,
    previous_digest: Optional[str],
    classification: str,
    actor: spec_lifecycle.Actor,
    source: str,
) -> SpecRequirementRevision:
    return SpecRequirementRevision(
        id=f"sprev-{short_id()}",
        project_id=row.project_id,
        requirement_id=row.id,
        document_id=row.document_id,
        previous_digest=previous_digest,
        digest=row.digest,
        digest_version=row.digest_version,
        source=source,
        classification=classification,
        actor_kind=actor.kind,
        actor=actor.name or "",
        run_id=actor.run_id,
    )


async def reindex_document(
    session: AsyncSession,
    document: SpecDocument,
    requirements: Sequence[IndexedRequirement],
    *,
    actor: spec_lifecycle.Actor,
    source: str = SOURCE_HUB,
) -> IndexResult:
    """Bring the index for one document into agreement with what it declares.

    `requirements` is the whole truth for this document: anything indexed under
    it and absent here is retired. Callers that could not read the document pass
    nothing at all rather than an empty list — see `reindex_from_file`.
    """
    result = IndexResult()
    observed = datetime.now(timezone.utc)
    existing = await _existing(session, document.id)
    seen: set = set()

    for declared in requirements:
        seen.add(declared.identifier)
        row = existing.get(declared.identifier)

        if row is None:
            row = SpecRequirement(
                id=f"spreq-{short_id()}",
                project_id=document.project_id,
                document_id=document.id,
                identifier=declared.identifier,
                key=declared.key,
                state=declared.state,
                digest=declared.digest,
                digest_version=spec_digest.CANONICALIZATION_VERSION,
                anchor=declared.anchor,
                observed_at=observed,
            )
            session.add(row)
            await session.flush()
            session.add(
                _revision(
                    row,
                    previous_digest=None,
                    classification=CREATED,
                    actor=actor,
                    source=source,
                )
            )
            result.created.append(declared.identifier)
            continue

        previous_digest = row.digest
        was_retired = row.state == RETIRED
        # The key can move: an agent may rename its handle while the statement
        # stands. The identifier is what everything points at, so following the
        # key here keeps re-resolution working without touching a single link.
        row.key = declared.key
        row.state = declared.state
        # A retirement recorded before digests were carried in the file declares
        # no digest. Keeping the one the row already holds is the only way the
        # meaning it had when it was removed survives; overwriting it with
        # nothing would quietly unpin every piece of evidence against it.
        if declared.digest or declared.state == ACTIVE:
            row.digest = declared.digest
            row.digest_version = spec_digest.CANONICALIZATION_VERSION
        row.anchor = declared.anchor
        row.observed_at = observed

        # One revision, classified by what actually happened to it. A requirement
        # that comes back reworded is still, first, a requirement that came back —
        # and the same in reverse, which is why the state change outranks the
        # digest change here.
        if was_retired and declared.state == ACTIVE:
            session.add(
                _revision(
                    row,
                    previous_digest=previous_digest,
                    classification=RESTORED,
                    actor=actor,
                    source=source,
                )
            )
            result.restored.append(declared.identifier)
        elif not was_retired and declared.state == RETIRED:
            session.add(
                _revision(
                    row,
                    previous_digest=previous_digest,
                    classification=RETIRED_CLASSIFICATION,
                    actor=actor,
                    source=source,
                )
            )
            result.retired.append(declared.identifier)
        elif previous_digest != declared.digest:
            session.add(
                _revision(
                    row,
                    previous_digest=previous_digest,
                    classification=REWORDED,
                    actor=actor,
                    source=source,
                )
            )
            result.reworded.append(declared.identifier)
        else:
            result.unchanged.append(declared.identifier)

    for identifier, row in existing.items():
        if identifier in seen or row.state == RETIRED:
            continue
        # Retirement keeps the last digest: it is what the requirement meant when
        # it was removed, and evidence pinned to it stays interpretable.
        row.state = RETIRED
        row.anchor = ""
        row.observed_at = observed
        session.add(
            _revision(
                row,
                previous_digest=row.digest,
                classification=RETIRED_CLASSIFICATION,
                actor=actor,
                source=source,
            )
        )
        result.retired.append(identifier)

    return result


async def reindex_from_file(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    *,
    actor: spec_lifecycle.Actor,
    source: str = SOURCE_EXTERNAL,
) -> Optional[IndexResult]:
    """Reindex one document from what is on disk right now.

    Returns `None` when the file carries no readable payload. The previous index
    is then left exactly as it was: a document being saved by an editor is
    momentarily unreadable, and retiring every requirement in it because a write
    was caught half-finished would be a data loss dressed up as an observation.
    """
    from . import spec_documents  # local: spec_documents imports nothing from here

    content = spec_documents.read_document(workspace, document.path)
    if content is None:
        return None
    requirements = requirements_from_payload(extract_payload(content))
    if requirements is None:
        return None
    return await reindex_document(session, document, requirements, actor=actor, source=source)


async def reindex_project(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    *,
    actor: Optional[spec_lifecycle.Actor] = None,
) -> Dict[str, Optional[IndexResult]]:
    """Rebuild a project's index from its files alone, keyed by document path."""
    actor = actor or spec_lifecycle.Actor(kind="system", name="reindex")
    documents = await spec_lifecycle.list_documents(session, project_id)
    return {
        document.path: await reindex_from_file(session, workspace, document, actor=actor)
        for document in documents
    }


async def document_requirements(
    session: AsyncSession, document_id: str, *, include_retired: bool = True
) -> List[SpecRequirement]:
    query = select(SpecRequirement).where(SpecRequirement.document_id == document_id)
    if not include_retired:
        query = query.where(SpecRequirement.state == ACTIVE)
    result = await session.execute(query.order_by(SpecRequirement.identifier))
    return list(result.scalars().all())


async def resolve(
    session: AsyncSession, project_id: str, identifier: str, *, document_id: Optional[str] = None
) -> Tuple[Optional[SpecRequirement], str]:
    """A requirement by identifier, and why it could not be found if it was not.

    Identifiers are minted per document, so a bare `FR-8` names one requirement
    only when one document in the project declares it. Where two do, this
    refuses rather than choosing: picking the newer one would silently link work
    to the wrong requirement, and being wrong here is invisible until someone
    reads both documents.
    """
    query = select(SpecRequirement).where(
        SpecRequirement.project_id == project_id,
        SpecRequirement.identifier == identifier,
    )
    if document_id is not None:
        query = query.where(SpecRequirement.document_id == document_id)
    rows = list((await session.execute(query)).scalars().all())

    if not rows:
        return None, "unknown"
    if len(rows) > 1:
        return None, "ambiguous"
    return rows[0], "ok"
