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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_links, spec_identity
from .db.models import (
    Loop,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskDependency,
    TaskDependencyReference,
)
from .spec_lifecycle import APPROVED, Actor
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

    # A loop that declared this document as its source (design D1, `Loop.spec_document_id`) owns
    # every task this call creates from it. `materialise()` already runs with the document in
    # scope, so this needs no new parameter — the binding was fixed at loop-creation time, not
    # threaded through the approval call that reaches here.
    owning_loop = (
        (await session.execute(select(Loop).where(Loop.spec_document_id == document.id)))
        .scalars()
        .first()
    )

    existing_task_rows = (
        (
            await session.execute(
                select(Task).where(
                    Task.project_id == document.project_id,
                    Task.spec_document_id == document.id,
                    Task.spec_task_key.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    existing_keys = {row.spec_task_key for row in existing_task_rows}
    # Every local task this document has ever materialised, by key — reused below to resolve edges
    # for a task this call did not itself create (4.4: a revision may add an edge to an existing
    # task even though the task row itself is never touched). The query above already filters to
    # `spec_task_key IS NOT NULL`; the `is not None` here is only to satisfy the type checker.
    local_tasks: Dict[str, Task] = {
        row.spec_task_key: row for row in existing_task_rows if row.spec_task_key is not None
    }

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
        if isinstance(entry.get("from"), dict):
            # 4.2, the one new rule in this loop: an imported entry resolves to the task it names
            # and never creates one of its own. `_materialise_edges` below is what resolves it —
            # this loop is only for entries that declare new work.
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
            loop_id=owning_loop.id if owning_loop is not None else None,
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
        local_tasks[key] = task
        created.append(task)

    await _materialise_edges(session, document, declared, local_tasks)

    return created


async def _resolve_import(
    session: AsyncSession, project_id: str, imported: Any
) -> Tuple[Optional[Task], Optional[str]]:
    """The task an imported entry (`Task.from_`) names, or why it could not be found.

    Defensive, not redundant: `spec_completeness`'s `import_not_approved` check already refuses
    `propose()` for an import naming an unapproved document, but `materialise()` runs at `approve()`
    — a later moment — and nothing stops the referenced document being reopened in between (design
    D7's own note on this). This is the only place that race can actually surface.
    """
    if not isinstance(imported, dict):
        return None, "malformed_import"
    doc_path = imported.get("document")
    key = imported.get("key")
    if not isinstance(doc_path, str) or not doc_path or not isinstance(key, str) or not key:
        return None, "malformed_import"

    doc = (
        (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.project_id == project_id, SpecDocument.path == doc_path
                )
            )
        )
        .scalars()
        .first()
    )
    if doc is None:
        return None, "document_not_found"
    if doc.phase != APPROVED:
        return None, "document_not_approved"

    task = (
        (
            await session.execute(
                select(Task).where(Task.spec_document_id == doc.id, Task.spec_task_key == key)
            )
        )
        .scalars()
        .first()
    )
    if task is None:
        return None, "key_not_found"
    return task, None


async def _materialise_edges(
    session: AsyncSession,
    document: SpecDocument,
    declared: List[Any],
    local_tasks: Dict[str, Task],
) -> None:
    """The `depends_on` edges declared entries name, once every entry's task is known (or known
    unresolvable).

    Runs over **every** locally-declared entry, not only what this call's task-creation pass
    created — task 4.4's decision: `spec_tasks.py`'s "a task that already exists is never touched"
    rule (module docstring) is about the task row itself, not its incoming edges. Since the document
    is the only writer of edges at all (design D5), a revision that adds a new `depends_on` to an
    already-materialised task has nowhere else to declare that edge, so re-approving adds it. What
    the rule still protects: nothing here ever *removes* an edge a prior approval created, even if a
    revision's `depends_on` no longer names it — the same one-directional caution `existing_keys`
    already gives task creation.

    An imported entry (`from_` set) never gets edges of its own — it is a resolution target other
    entries' `depends_on` can name, not a node materialised here (4.2).
    """
    resolved: Dict[str, Tuple[Optional[Task], Optional[str]]] = {}
    for entry in declared:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            continue
        imported = entry.get("from")
        if isinstance(imported, dict):
            resolved[key] = await _resolve_import(session, document.project_id, imported)
        else:
            task = local_tasks.get(key)
            # A key this document declared but for which no task row exists — e.g. every
            # requirement it named was already served by a hand-made task (the `already_served`
            # skip above). It is still a legal `depends_on` target by name, per `spec_completeness`,
            # but there is no task to point an edge at.
            resolved[key] = (task, None if task is not None else "local_task_not_materialised")

    for entry in declared:
        if not isinstance(entry, dict) or isinstance(entry.get("from"), dict):
            continue
        key = entry.get("key")
        task = local_tasks.get(key) if isinstance(key, str) else None
        if task is None:
            continue

        # Replaced wholesale per task on every call (`absorb_free_text`'s `replace=True`
        # precedent) — a reference that resolves on a later approval must not linger.
        await session.execute(
            delete(TaskDependencyReference).where(TaskDependencyReference.task_id == task.id)
        )

        wanted = entry.get("depends_on")
        dep_keys = (
            [d for d in wanted if isinstance(d, str) and d] if isinstance(wanted, list) else []
        )
        if not dep_keys:
            continue

        existing_edges = set(
            (
                await session.execute(
                    select(TaskDependency.depends_on_task_id).where(
                        TaskDependency.task_id == task.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for dep_key in dep_keys:
            target, reason = resolved.get(dep_key, (None, "not_declared"))
            if target is None:
                session.add(
                    TaskDependencyReference(
                        id=f"tdr-{short_id()}",
                        project_id=document.project_id,
                        task_id=task.id,
                        reference=dep_key,
                        reason=reason or "unresolved",
                    )
                )
                continue
            if target.id == task.id or target.id in existing_edges:
                continue
            existing_edges.add(target.id)
            session.add(
                TaskDependency(
                    id=f"tdep-{short_id()}",
                    project_id=document.project_id,
                    task_id=task.id,
                    depends_on_task_id=target.id,
                )
            )


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
