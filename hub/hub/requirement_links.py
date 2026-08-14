"""Linking work to the requirements it serves, and refusing to guess.

Two callers with different obligations share this module, and the difference
between them is the whole design:

**A reference field is checked.** When a caller says "this task serves FR-8", an
identifier the project does not have is an error, stated with the identifier that
failed. Accepting it as text is what `Task.requirements` did, and it produced a
string that looked like a reference and resolved to nothing.

**A free-text field is preserved.** Legacy values and prose are converted where
they resolve and kept verbatim where they do not. Nothing is discarded, and no
requirement is created to match a value — a migration that invented one would
answer "what work serves this?" with work nobody wrote for it.

Ambiguity is refused rather than resolved. Identifiers are minted per document,
so a bare `FR-8` names one requirement only when one document declares it;
picking the newer of two would link work to the wrong requirement, and being
wrong there is invisible until somebody reads both documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_index
from .db.models import (
    SpecDocument,
    SpecRequirement,
    Task,
    TaskRequirementLink,
    TaskRequirementReference,
)
from .spec_lifecycle import Actor
from .utils import short_id

# Only a *leading* identifier is trusted. The observed legacy shape is
# `"FR-8 — initialize-members"`, which one agent happened to write that way; an
# identifier appearing mid-sentence is prose about a requirement, not a claim to
# serve it.
LEADING_IDENTIFIER = re.compile(r"^\s*(FR-\d+)\b")
EXACT_IDENTIFIER = re.compile(r"^\s*(FR-\d+)\s*$")

#: Why a free-text value did not become a link. **None of these is a fault.**
#:
#: `requirements` is a free-text field and agents use it as one — for prose constraints and design
#: notes as well as for identifiers. Reporting "Keep the deliverable to one runnable file" as an
#: *unresolved requirement* made every task on a real board look like it had three problems when
#: nothing was wrong. `not_a_reference` says what is true: it is a note, kept because B3 §2.4
#: forbids discarding anything a caller wrote.
UNKNOWN = "unknown"
AMBIGUOUS = "ambiguous"
#: Names an identifier this project does not have. Worth an operator's attention.
UNPARSED = "unparsed"
#: Carries no identifier at all — prose, not a claim to serve anything. Kept, not flagged.
NOT_A_REFERENCE = "not_a_reference"


class LinkRefusedError(ValueError):
    """A named identifier that does not resolve, with which one and why."""

    def __init__(self, message: str, *, code: str, identifier: str) -> None:
        self.code = code
        self.identifier = identifier
        super().__init__(message)


@dataclass
class LinkOutcome:
    linked: List[str] = field(default_factory=list)
    #: Named an identifier and it did not resolve. Worth an operator's attention.
    unresolved: List[str] = field(default_factory=list)
    #: Named no identifier at all — prose the caller put in a free-text field. Kept, not a problem.
    notes: List[str] = field(default_factory=list)


async def _requirement_by_identifier(
    session: AsyncSession,
    project_id: str,
    identifier: str,
    *,
    document_id: Optional[str] = None,
) -> tuple[Optional[SpecRequirement], str]:
    return await spec_index.resolve(session, project_id, identifier, document_id=document_id)


async def _document_for_path(
    session: AsyncSession, project_id: str, path: Optional[str]
) -> Optional[SpecDocument]:
    if not path:
        return None
    result = await session.execute(
        select(SpecDocument).where(SpecDocument.project_id == project_id, SpecDocument.path == path)
    )
    return result.scalars().first()


async def resolve_identifiers(
    session: AsyncSession,
    project_id: str,
    identifiers: Sequence[str],
    *,
    document_path: Optional[str] = None,
) -> List[SpecRequirement]:
    """Every named identifier, or a refusal naming the first that failed.

    Refusing the whole set rather than linking what resolved is deliberate: a
    task that silently serves two of the three requirements it named is a task
    whose author believes it serves three.
    """
    document = await _document_for_path(session, project_id, document_path)
    resolved: List[SpecRequirement] = []
    for raw in identifiers:
        match = EXACT_IDENTIFIER.match(raw or "")
        if match is None:
            raise LinkRefusedError(
                f"{raw!r} is not a requirement identifier; expected a value like 'FR-8'",
                code="identifier_malformed",
                identifier=str(raw),
            )
        identifier = match.group(1)
        row, status = await _requirement_by_identifier(
            session,
            project_id,
            identifier,
            document_id=document.id if document is not None else None,
        )
        if status == AMBIGUOUS:
            raise LinkRefusedError(
                f"{identifier} is declared by more than one document in this project; "
                "name the document it belongs to",
                code="identifier_ambiguous",
                identifier=identifier,
            )
        if row is None:
            raise LinkRefusedError(
                f"this project has no requirement {identifier}",
                code="identifier_unknown",
                identifier=identifier,
            )
        resolved.append(row)
    return resolved


async def link(
    session: AsyncSession,
    task: Task,
    requirements: Iterable[SpecRequirement],
    *,
    actor: Actor,
) -> List[str]:
    """Create the links a task does not already have. Existing ones are left alone."""
    existing = {
        row.requirement_id
        for row in (
            await session.execute(
                select(TaskRequirementLink).where(TaskRequirementLink.task_id == task.id)
            )
        )
        .scalars()
        .all()
    }
    created: List[str] = []
    for requirement in requirements:
        if requirement.id in existing:
            continue
        existing.add(requirement.id)
        session.add(
            TaskRequirementLink(
                id=f"trl-{short_id()}",
                project_id=task.project_id,
                task_id=task.id,
                requirement_id=requirement.id,
                actor_kind=actor.kind,
                actor=actor.name or "",
                run_id=actor.run_id,
            )
        )
        created.append(requirement.identifier)
    return created


async def absorb_free_text(
    session: AsyncSession,
    task: Task,
    values: Optional[Sequence],
    *,
    actor: Actor,
    replace: bool = True,
) -> LinkOutcome:
    """Convert what resolves, keep what does not, drop nothing.

    Used for the free-text `requirements` list, which agents have been filling
    with strings like `"FR-8 — initialize-members"` since before identifiers were
    checkable. A value that resolves becomes a real link; everything else is kept
    with its original text so the conversion is inspectable and reversible.
    """
    outcome = LinkOutcome()
    if values is None:
        return outcome

    if replace:
        await session.execute(
            delete(TaskRequirementReference).where(TaskRequirementReference.task_id == task.id)
        )

    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        match = LEADING_IDENTIFIER.match(value)
        if match is None:
            # Prose, not a broken reference. Kept verbatim as §2.4 requires, and reported as the
            # note it is: a value that never claimed to name a requirement is not an unresolved one,
            # and calling it that made every task on a real board look faulty.
            session.add(_reference(task, value, NOT_A_REFERENCE))
            outcome.notes.append(value)
            continue

        row, status = await _requirement_by_identifier(session, task.project_id, match.group(1))
        if row is None:
            session.add(_reference(task, value, AMBIGUOUS if status == AMBIGUOUS else UNKNOWN))
            outcome.unresolved.append(value)
            continue

        outcome.linked.extend(await link(session, task, [row], actor=actor))

    return outcome


def _reference(task: Task, value: str, reason: str) -> TaskRequirementReference:
    return TaskRequirementReference(
        id=f"trr-{short_id()}",
        project_id=task.project_id,
        task_id=task.id,
        reference=value,
        reason=reason,
    )


async def for_task(session: AsyncSession, task_id: str) -> List[SpecRequirement]:
    """The requirements a task serves, as index rows.

    These carry identity and a digest and **no wording** — by design, so a row cannot come to
    disagree with the document about what a requirement says. The wording lives in the document and
    is read through `spec_reading`; a caller that needs statements wants that, not this.
    """
    result = await session.execute(
        select(SpecRequirement)
        .join(TaskRequirementLink, TaskRequirementLink.requirement_id == SpecRequirement.id)
        .where(TaskRequirementLink.task_id == task_id)
        .order_by(SpecRequirement.identifier)
    )
    return list(result.scalars().all())


async def unresolved_for_task(
    session: AsyncSession, task_id: str
) -> List[TaskRequirementReference]:
    result = await session.execute(
        select(TaskRequirementReference)
        .where(TaskRequirementReference.task_id == task_id)
        .order_by(TaskRequirementReference.created_at, TaskRequirementReference.id)
    )
    return list(result.scalars().all())


async def tasks_for_requirement(session: AsyncSession, requirement_id: str) -> List[Task]:
    result = await session.execute(
        select(Task)
        .join(TaskRequirementLink, TaskRequirementLink.task_id == Task.id)
        .where(TaskRequirementLink.requirement_id == requirement_id)
        .order_by(Task.created_at)
    )
    return list(result.scalars().all())


async def linked_requirement_ids(session: AsyncSession, project_id: str) -> set:
    result = await session.execute(
        select(TaskRequirementLink.requirement_id).where(
            TaskRequirementLink.project_id == project_id
        )
    )
    return set(result.scalars().all())


async def unserved(
    session: AsyncSession, project_id: str, *, document_id: Optional[str] = None
) -> List[SpecRequirement]:
    """Active requirements with no work linked to them.

    The question the end-to-end run needed and could not ask: nine requirements,
    six tasks, and no way to tell whether every requirement had somewhere to be
    built. Retired requirements are excluded — a requirement nobody has to build
    any more is not unserved, it is over.
    """
    query = select(SpecRequirement).where(
        SpecRequirement.project_id == project_id,
        SpecRequirement.state == spec_index.ACTIVE,
    )
    if document_id is not None:
        query = query.where(SpecRequirement.document_id == document_id)

    linked = await linked_requirement_ids(session, project_id)
    rows = list((await session.execute(query.order_by(SpecRequirement.identifier))).scalars().all())
    return [row for row in rows if row.id not in linked]


async def backfill_project(session: AsyncSession, project_id: str) -> Dict[str, int]:
    """Retry the unresolved references now that the index may know more.

    A project whose documents predate the requirement index converts nothing at
    migration time, because there was nothing to resolve against. Reindexing then
    makes those identifiers real, and this converts the references that now
    resolve — without ever having guessed in the meantime.
    """
    references = list(
        (
            await session.execute(
                select(TaskRequirementReference).where(
                    TaskRequirementReference.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    actor = Actor(kind="system", name="backfill")
    converted = 0

    for reference in references:
        match = LEADING_IDENTIFIER.match(reference.reference)
        if match is None:
            continue
        row, status = await _requirement_by_identifier(session, project_id, match.group(1))
        if row is None:
            if status == AMBIGUOUS and reference.reason != AMBIGUOUS:
                reference.reason = AMBIGUOUS
            continue
        task = await session.get(Task, reference.task_id)
        if task is None:
            continue
        await link(session, task, [row], actor=actor)
        await session.delete(reference)
        converted += 1

    return {"converted": converted, "remaining": len(references) - converted}
