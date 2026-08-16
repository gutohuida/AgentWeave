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

#: A declared description is a sentence of intent, written to be read in the document. A board shows
#: names. Where the author states a title, that is what the board gets; this is the fallback for a
#: document that states only the description.
#:
#: Sized to be read as a name rather than as prose. At 200 the fallback returned whole descriptions —
#: observed at 170, 112 and a 200-character title clipped mid-word to "…explici", which reads as a
#: defect in the board rather than as an abbreviation.
MAX_TITLE = 80

#: Marks a title as shortened. Only ever appended when something was actually dropped, so a
#: description already short enough to be a name comes through byte-for-byte.
ELLIPSIS = "…"


def _title_from(description: str) -> str:
    """Derive a board-sized name from a declared description.

    First sentence, then a word boundary. Never mid-word: these descriptions are routinely a single
    long sentence, so the sentence split alone does nothing for exactly the inputs that need it.
    """
    text = (description or "").strip()
    if not text:
        return "Untitled task"
    head, separator, _ = text.partition(". ")
    candidate = (head if separator else text).strip()
    if len(candidate) <= MAX_TITLE:
        return candidate.rstrip().rstrip(".") or "Untitled task"

    # Cut at the last whitespace that fits, so the title ends on a whole word.
    clipped = candidate[:MAX_TITLE].rsplit(" ", 1)[0].rstrip()
    clipped = clipped.rstrip(",;:.-—([{").rstrip()
    if not clipped:
        # A single word longer than the limit. There is no boundary to find, so this is the one
        # place a hard cut is the only honest answer.
        clipped = candidate[:MAX_TITLE].rstrip()
    return f"{clipped}{ELLIPSIS}"


def _title_for(entry: Dict[str, Any]) -> str:
    """The title the board shows: what the document declared, or what we can derive."""
    declared = entry.get("title")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()[:MAX_TITLE].rstrip()
    return _title_from(entry.get("description") or "")


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

    # Requirements a *hand-made* task already serves — one `spec_task_key IS NULL`, so not a task
    # this document's own decomposition produced. An entry whose every named requirement is already
    # covered that way restates work that exists rather than declaring work that does not;
    # materialising it would be the duplication `spec_completeness.check()`'s `board_served` credit
    # exists to make unnecessary. Deliberately not scoped to tasks *this* materialise call creates
    # (those carry a key and are tracked by `existing_keys` instead), so a later entry in the
    # document's own decomposition naming a requirement an earlier declared task already serves is
    # still created — see `test_re_approving_creates_no_duplicates`.
    already_served = await requirement_links.hand_made_requirement_ids(session, document.project_id)

    created: List[Task] = []
    for entry in declared:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key or key in existing_keys:
            continue

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

        if (
            requirements
            and not unresolved
            and all(row.id in already_served for row in requirements)
        ):
            existing_keys.add(key)
            continue

        description = entry.get("description") or ""
        task = Task(
            id=f"task-{short_id()}",
            project_id=document.project_id,
            title=_title_for(entry),
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
