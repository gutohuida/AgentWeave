"""Turning the tasks a document declares into work on the board.

The convention already existed and nothing consumed it. A specification's payload carries `tasks` —
a `key`, a `description`, and the requirement **keys** each serves — `spec_payload` validates that
those keys resolve, and `spec_completeness` reads them to judge whether the decomposition covers the
requirements. Then approval happened and the board stayed empty.

What that cost, from the run that found it: an operator approved nineteen requirements and got
nothing. The authoring agent had written six tasks into the document *and then created three
different ones by hand*, because the document's own were inert. Two decompositions, no relationship
between them, and the one that was reviewed and approved was the one nobody worked from.

Two rules shape this:

**Idempotent, by `(document, key)`.** Re-approving a revised document adds what is new. Without that
the second approval duplicates the whole decomposition, and re-approving after a revision is exactly
what a document earns by being revisable.

**A task that already exists is never touched.** The document declares that work *exists* — not what
has happened to it since. An approval that reset a task in progress, or reassigned it, would make
re-approving a document something an operator learns to fear.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_links, spec_identity
from .db.models import SpecDocument, SpecRequirement, Task
from .spec_lifecycle import Actor
from .utils import short_id

logger = logging.getLogger(__name__)

#: Where a declared task enters the lifecycle. The entry status, unassigned: the document says the
#: work exists, and who performs it is a roster decision a specification has no business making.
ENTRY_STATUS = "pending"

#: A declared description is one sentence of intent, not a title. Titles are what a board shows, so
#: the first sentence becomes the title and the whole thing stays as the description.
MAX_TITLE = 200


def _title_from(description: str) -> str:
    text = (description or "").strip()
    if not text:
        return "Untitled task"
    head, separator, _ = text.partition(". ")
    candidate = head if separator else text
    return candidate[:MAX_TITLE].rstrip().rstrip(".") or "Untitled task"


async def materialise(
    session: AsyncSession,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    *,
    actor: Actor,
) -> List[Task]:
    """Create the tasks *document* declares that do not exist yet. Returns only what was created.

    A document declaring nothing creates nothing, and that is not an error — it is a document whose
    decomposition has not been written, which is a normal state for one that was approved for its
    requirements alone.
    """
    declared = (payload or {}).get("tasks")
    if not isinstance(declared, list) or not declared:
        return []

    existing_keys = set(
        (
            await session.execute(
                select(Task.spec_task_key).where(
                    Task.project_id == document.project_id,
                    Task.spec_document_id == document.id,
                    Task.spec_task_key.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    # The document's own key→identifier map. `spec_index` rebuilds the whole index from this, so it
    # is the same source of truth, read the same way — not a second interpretation of the file.
    identities, _ = spec_identity.read_identity(payload)

    rows = (
        (
            await session.execute(
                select(SpecRequirement).where(SpecRequirement.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    by_identifier = {row.identifier: row for row in rows}
    by_key = {row.key: row for row in rows}

    created: List[Task] = []
    for entry in declared:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key or key in existing_keys:
            continue

        description = entry.get("description") or ""
        task = Task(
            id=f"task-{short_id()}",
            project_id=document.project_id,
            title=_title_from(description),
            description=description,
            status=ENTRY_STATUS,
            priority="medium",
            assignee=None,
            assigner=None,
            spec_document_id=document.id,
            spec_task_key=key,
        )
        session.add(task)
        await session.flush()

        wanted = entry.get("requirements")
        requirements: List[SpecRequirement] = []
        unresolved: List[str] = []
        for named in wanted if isinstance(wanted, list) else []:
            if not isinstance(named, str) or not named:
                continue
            row = by_key.get(named) or by_identifier.get(identities.get(named, ""))
            if row is not None:
                requirements.append(row)
            else:
                unresolved.append(named)

        if requirements:
            await requirement_links.link(session, task, requirements, actor=actor)
        if unresolved:
            # Preserved rather than dropped, and never a refusal. A declared task naming a
            # requirement the index does not have is still work somebody asked for, and the
            # unrecognised name is the evidence of what went wrong.
            await requirement_links.absorb_free_text(
                session, task, unresolved, actor=actor, replace=False
            )

        existing_keys.add(key)
        created.append(task)

    return created


async def materialise_quietly(
    session: AsyncSession,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    *,
    actor: Actor,
) -> List[Task]:
    """`materialise`, but a failure is logged rather than raised.

    Approval is the operator's decision about the specification. Failing that decision because the
    board could not be populated would make an unrelated problem look like a refusal to approve —
    and the document would stay unapproved, which is the one outcome nobody wanted.
    """
    try:
        return await materialise(session, document, payload, actor=actor)
    except Exception:  # noqa: BLE001 - see docstring: never fail an approval over this
        logger.warning(
            "Could not create the tasks %s declares; the approval stands.",
            document.path,
            exc_info=True,
        )
        return []
