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

**Progress and assignment are the board's; what the work is, is the document's** (F535). An approval
that reset a task in progress, or reassigned it, would make re-approving a document something an
operator learns to fear — so status, assignee and priority are never touched. But freezing the whole
row froze the description of the work too: F532's amended document retired FR-3 and added FR-5, and
its open task kept the old title and the link to the retired requirement while FR-5 went unserved.
So an *open* task the document still declares is refreshed — title, description, criteria, and its
links to this document's requirements. A task that is approved or rejected records what was asked
when it was decided, and stays as it is. The approval report says what was refreshed, which closed
tasks still link a retired requirement, and which tasks the document no longer declares.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_links, spec_identity, spec_reading, task_dependency_writer
from .db.models import (
    Loop,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskDependency,
    TaskDependencyReference,
    TaskRequirementLink,
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

#: A task in one of these records what was delivered or turned down against what was asked then,
#: so a later approval leaves it exactly as it is (F535).
CLOSED_STATUSES = ("approved", "rejected")


def _natural(identifier: str) -> list:
    """`FR-2` before `FR-11`: digit runs compare as numbers."""
    return [
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.split(r"(\d+)", identifier)
    ]


@dataclass(frozen=True)
class CreatedTask:
    """A task approval created, as plain values: readable after any savepoint has rolled back."""

    id: str
    key: str
    title: str


@dataclass(frozen=True)
class ServedEntry:
    """A declared entry not created because hand-made tasks already serve every requirement it
    names. It is the entry that is skipped, so it is named by its key."""

    key: str
    requirements: Tuple[str, ...]


@dataclass(frozen=True)
class RefreshedTask:
    """An open task re-approval brought up to date: which of its fields changed, and the identifiers
    of this document's requirements it was linked to and unlinked from."""

    id: str
    key: str
    title: str
    fields: Tuple[str, ...]
    linked: Tuple[str, ...]
    unlinked: Tuple[str, ...]


@dataclass(frozen=True)
class ClosedLinkingRetired:
    """A closed task, left as delivered, that still links a requirement this document retired."""

    id: str
    key: str
    status: str
    requirements: Tuple[str, ...]


@dataclass(frozen=True)
class UndeclaredTask:
    """A task this document created under a key it no longer declares. Reported, never changed."""

    id: str
    key: str
    status: str


@dataclass
class BoardReport:
    """What approval found on the board for tasks that already existed (F535), collected by
    `materialise` the way `already_served` is."""

    refreshed: List[RefreshedTask] = field(default_factory=list)
    closed_linking_retired: List[ClosedLinkingRetired] = field(default_factory=list)
    no_longer_declared: List[UndeclaredTask] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialiseOutcome:
    """What approval's board did, in the payload's declaration order. Never ORM rows (design D7):
    rolling a savepoint back expires what was touched inside it, and reading an expired row in this
    async stack raises `MissingGreenlet`."""

    created: List[CreatedTask]
    already_served: List[ServedEntry]
    failed: Optional[str]
    board: BoardReport = field(default_factory=BoardReport)


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


def _render_criterion(criterion: Dict[str, Any]) -> Optional[str]:
    """One line per criterion, or `None` for one that states no standard (design D8).

    Never emits the literal `None`: a part that is absent or empty is left out rather than
    stringified, and a criterion missing all three parts is skipped by the caller.
    """
    parts: List[str] = []
    given = criterion.get("given")
    if isinstance(given, str) and given.strip():
        parts.append(f"Given {given}")
    when = criterion.get("when")
    if isinstance(when, str) and when.strip():
        parts.append(f"when {when}")
    then = criterion.get("then")
    if isinstance(then, str) and then.strip():
        parts.append(f"then {then}")
    if not parts:
        return None
    parts[0] = parts[0][:1].upper() + parts[0][1:]
    body = ", ".join(parts)

    key = criterion.get("key")
    if isinstance(key, str) and key.strip():
        return f"{key}: {body}"
    return body


def _criteria_for_entry(
    names: List[str],
    criteria_index: Dict[str, List[Dict[str, Any]]],
    position: Dict[str, int],
) -> List[str]:
    """The rendered criteria for a declared task's own `requirements` names (design D3/D4).

    Collected under each name the entry gave — a repeated name contributes its group once
    (`dict.fromkeys`, not a `set`: set iteration order for strings is not stable across processes,
    which would store two approvals of the same file in different orders). Then one stable sort by
    the position of the *name a criterion was grouped under* in the document's own requirement
    order, falling back to last place for a name the document's requirement list no longer holds —
    matching `spec_render._acceptance`.
    """
    collected: List[Tuple[int, Dict[str, Any]]] = []
    for name in dict.fromkeys(names):
        group = criteria_index.get(name)
        if not group:
            continue
        rank = position.get(name, len(position))
        for criterion in group:
            collected.append((rank, criterion))
    collected.sort(key=lambda item: item[0])

    rendered: List[str] = []
    for _, criterion in collected:
        line = _render_criterion(criterion)
        if line is not None:
            rendered.append(line)
    return rendered


async def materialise(
    session: AsyncSession,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    *,
    actor: Actor,
    already_served: Optional[List[ServedEntry]] = None,
    board: Optional[BoardReport] = None,
) -> List[Task]:
    """Create the tasks *document* declares that do not exist yet, and refresh the open ones that
    do (F535). Returns only what was created.

    *already_served*, when given, collects each declared entry skipped because hand-made tasks
    already serve every requirement it names, for approval's report. *board*, when given, collects
    what happened to tasks that already existed.

    A document declaring nothing creates nothing, and that is not an error — it is a document whose
    decomposition has not been written, which is a normal state for one that was approved for its
    requirements alone.
    """
    declared = (payload or {}).get("tasks")
    if not isinstance(declared, list) or not declared:
        return []

    # The live loop that declared this document as its source (design D1, `Loop.spec_document_id`)
    # owns every task this call creates from it. `materialise()` already runs with the document in
    # scope, so this needs no new parameter — the binding was fixed at loop-creation time, not
    # threaded through the approval call that reaches here. An archived loop is never stamped (F53):
    # at most one live loop can name a document (`ux_loops_spec_document_live`), and with none the
    # tasks are unowned until the next loop to claim the document adopts them.
    owning_loop = (
        (
            await session.execute(
                select(Loop).where(
                    Loop.project_id == document.project_id,
                    Loop.spec_document_id == document.id,
                    Loop.archived_at.is_(None),
                )
            )
        )
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
    # Every local task this document has ever materialised, by key — reused below to resolve edges
    # for a task this call did not itself create (4.4: a revision may add an edge to an existing
    # task). The query above already filters to `spec_task_key IS NOT NULL`; the `is not None` here
    # is only to satisfy the type checker.
    local_tasks: Dict[str, Task] = {
        row.spec_task_key: row for row in existing_task_rows if row.spec_task_key is not None
    }
    # What existed before this call: these are refreshed, never re-created.
    preexisting: Dict[str, Task] = dict(local_tasks)
    # Keys this call has dealt with. A key declared twice is dealt with once.
    seen: set = set()

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
    by_id = {row.id: row for row in rows}

    # Requirements a *hand-made* task already serves — one `spec_task_key IS NULL`, so not a task
    # this document's own decomposition produced. An entry whose every named requirement is already
    # covered that way restates work that exists rather than declaring work that does not;
    # materialising it would be the duplication `spec_completeness.check()`'s `board_served` credit
    # exists to make unnecessary. Deliberately not scoped to tasks *this* materialise call creates
    # (those carry a key and are tracked by `existing_keys` instead), so a later entry in the
    # document's own decomposition naming a requirement an earlier declared task already serves is
    # still created — see `test_re_approving_creates_no_duplicates`.
    served_by_hand = await requirement_links.hand_made_requirement_ids(session, document.project_id)

    # Built once, before the loop, through the same guarded helpers `criteria_by_requirement_key`
    # uses (design D6/D7): a payload this code cannot read must fail the same way for every entry,
    # not part-way through a committed partial board.
    position = {key: index for index, key in enumerate(spec_reading.statements_by_key(payload))}
    criteria_index = spec_reading.criteria_by_requirement_key(payload)

    created: List[Task] = []
    for entry in declared:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key or key in seen:
            continue
        seen.add(key)
        if isinstance(entry.get("from"), dict):
            # 4.2, the one new rule in this loop: an imported entry resolves to the task it names
            # and never creates one of its own. `_materialise_edges` below is what resolves it —
            # this loop is only for entries that declare new work.
            continue

        wanted = entry.get("requirements")
        requirements: List[SpecRequirement] = []
        unresolved: List[str] = []
        names: List[str] = []
        for named in wanted if isinstance(wanted, list) else []:
            if not isinstance(named, str) or not named:
                continue
            names.append(named)
            row = by_key.get(named) or by_identifier.get(identities.get(named, ""))
            if row is not None:
                requirements.append(row)
            else:
                unresolved.append(named)

        prior = preexisting.get(key)
        if prior is not None:
            if prior.status not in CLOSED_STATUSES:
                refreshed = await _refresh(
                    session,
                    prior,
                    entry,
                    requirements,
                    _criteria_for_entry(names, criteria_index, position),
                    document=document,
                    by_id=by_id,
                    actor=actor,
                )
                if refreshed is not None and board is not None:
                    board.refreshed.append(refreshed)
            continue

        if (
            requirements
            and not unresolved
            and all(row.id in served_by_hand for row in requirements)
        ):
            if already_served is not None:
                already_served.append(ServedEntry(key=key, requirements=tuple(names)))
            continue

        description = entry.get("description") or ""
        criteria = _criteria_for_entry(names, criteria_index, position)
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
            acceptance_criteria=criteria or None,
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

        local_tasks[key] = task
        created.append(task)

    await _materialise_edges(session, document, declared, local_tasks)

    if board is not None:
        await _report_unrefreshed(session, document, existing_task_rows, seen, board)

    return created


async def _refresh(
    session: AsyncSession,
    task: Task,
    entry: Dict[str, Any],
    requirements: List[SpecRequirement],
    criteria: List[str],
    *,
    document: SpecDocument,
    by_id: Dict[str, SpecRequirement],
    actor: Actor,
) -> Optional[RefreshedTask]:
    """Bring an open declared task's description of the work up to what *entry* now says.

    Title, description, criteria, and links to **this** document's requirements; nothing else.
    Links are set by difference, so a link the entry still names keeps its row and its actor, and a
    task nothing changed for is not reported. Unresolved names are left in the task's free-text
    references as they were: that record belongs to the approval that wrote it.
    """
    fields: List[str] = []
    title = _title_for(entry)
    if task.title != title:
        task.title = title
        fields.append("title")
    description = entry.get("description") or ""
    if task.description != description:
        task.description = description
        fields.append("description")
    if (task.acceptance_criteria or None) != (criteria or None):
        task.acceptance_criteria = criteria or None
        fields.append("acceptance_criteria")

    current = set(
        (
            await session.execute(
                select(TaskRequirementLink.requirement_id)
                .join(SpecRequirement, SpecRequirement.id == TaskRequirementLink.requirement_id)
                .where(
                    TaskRequirementLink.task_id == task.id,
                    SpecRequirement.document_id == document.id,
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = {row.id for row in requirements}
    linked = await requirement_links.link(
        session, task, [row for row in requirements if row.id not in current], actor=actor
    )
    removed = current - wanted
    if removed:
        await session.execute(
            delete(TaskRequirementLink).where(
                TaskRequirementLink.task_id == task.id,
                TaskRequirementLink.requirement_id.in_(removed),
            )
        )
    unlinked = [by_id[rid].identifier for rid in removed if rid in by_id]

    if not (fields or linked or removed):
        return None
    task.updated = datetime.now(timezone.utc)
    return RefreshedTask(
        id=task.id,
        key=task.spec_task_key or "",
        title=task.title,
        fields=tuple(fields),
        linked=tuple(sorted(linked, key=_natural)),
        unlinked=tuple(sorted(unlinked, key=_natural)),
    )


async def _report_unrefreshed(
    session: AsyncSession,
    document: SpecDocument,
    existing_task_rows: List[Task],
    declared_keys: set,
    board: BoardReport,
) -> None:
    """The tasks a re-approval left alone that the operator still needs to hear about: closed ones
    linking a requirement this document retired, and ones it no longer declares."""
    ordered = sorted(existing_task_rows, key=lambda row: (row.created_at, row.id))
    for row in ordered:
        if row.spec_task_key not in declared_keys:
            board.no_longer_declared.append(
                UndeclaredTask(id=row.id, key=row.spec_task_key or "", status=row.status)
            )

    closed = [row for row in ordered if row.status in CLOSED_STATUSES]
    if not closed:
        return
    retired: Dict[str, List[str]] = {}
    for task_id, identifier in (
        await session.execute(
            select(TaskRequirementLink.task_id, SpecRequirement.identifier)
            .join(SpecRequirement, SpecRequirement.id == TaskRequirementLink.requirement_id)
            .where(
                TaskRequirementLink.task_id.in_([row.id for row in closed]),
                SpecRequirement.document_id == document.id,
                SpecRequirement.state == "retired",
            )
        )
    ).all():
        retired.setdefault(task_id, []).append(identifier)
    for row in closed:
        if row.id in retired:
            board.closed_linking_retired.append(
                ClosedLinkingRetired(
                    id=row.id,
                    key=row.spec_task_key or "",
                    status=row.status,
                    requirements=tuple(sorted(retired[row.id], key=_natural)),
                )
            )


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
            # Through the shared writer since F36, so this path and the operator's build the graph
            # the same way — and so this path gains the cycle check it never had. A document
            # declaring `a -> b -> a` previously produced a graph on which `dependency_gate`
            # refused both tasks forever, each waiting on the other.
            outcome = await task_dependency_writer.add_dependency(
                session,
                document.project_id,
                task.id,
                target.id,
                known_edges=existing_edges,
            )
            if outcome in (
                task_dependency_writer.ADDED,
                task_dependency_writer.DUPLICATE,
                task_dependency_writer.SELF,
            ):
                continue
            # A refusal is recorded, never raised: an approval must not fail over the shape of a
            # dependency (`materialise_quietly`'s reasoning). This is the same channel an
            # unresolvable key already uses, so the operator sees one kind of "this `depends_on`
            # was not honoured" rather than two.
            session.add(
                TaskDependencyReference(
                    id=f"tdr-{short_id()}",
                    project_id=document.project_id,
                    task_id=task.id,
                    reference=dep_key,
                    reason=outcome,
                )
            )


async def materialise_quietly(
    session: AsyncSession,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    *,
    actor: Actor,
) -> MaterialiseOutcome:
    """`materialise` inside a SAVEPOINT; a failure is reported rather than raised.

    Approval is the operator's decision about the specification. Failing that decision because the
    board could not be populated would make an unrelated problem look like a refusal to approve —
    and the document would stay unapproved, which is the one outcome nobody wanted.

    The savepoint is what makes "the approval stands" true (design D7, measured): without it a
    flush error mid-way left the session needing a rollback, so the approval's own commit raised
    `PendingRollbackError`, and a non-database error after some `session.add` committed a partial
    board. Now a failure rolls back exactly the board, and `failed` says why.

    **Precondition:** the enclosing transaction has already written. Under pysqlite a SAVEPOINT
    issued before any write becomes the outermost transaction, and its RELEASE commits. In
    `set_phase` the transition's phase row and event are pending, and `begin_nested()` flushes
    them first, which satisfies it.
    """
    served: List[ServedEntry] = []
    board = BoardReport()
    try:
        async with session.begin_nested():
            rows = await materialise(
                session, document, payload, actor=actor, already_served=served, board=board
            )
            created = [
                CreatedTask(id=row.id, key=row.spec_task_key or "", title=row.title) for row in rows
            ]
    except Exception as exc:  # noqa: BLE001 - see docstring: never fail an approval over this
        logger.warning(
            "Could not create the tasks %s declares; the approval stands.",
            document.path,
            exc_info=True,
        )
        return MaterialiseOutcome(
            created=[], already_served=[], failed=f"{type(exc).__name__}: {exc}"
        )
    return MaterialiseOutcome(created=created, already_served=served, failed=None, board=board)


async def dependencies_not_honoured(
    session: AsyncSession, document: SpecDocument, payload: Optional[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """The declared `depends_on` entries of *document*'s tasks that did not become edges.

    Read from `TaskDependencyReference`, which `_materialise_edges` rewrites per task on every
    approval, so the rows describe this approval. Ordered by the task's declaration position, then
    by reference, so the report reads in the document's order rather than insertion order. Only
    meaningful when the board did not fail: otherwise the rows are the previous approval's.
    """
    declared = (payload or {}).get("tasks")
    order = {
        entry.get("key"): index
        for index, entry in enumerate(declared if isinstance(declared, list) else [])
        if isinstance(entry, dict)
    }
    rows = (
        await session.execute(
            select(
                Task.id,
                Task.spec_task_key,
                TaskDependencyReference.reference,
                TaskDependencyReference.reason,
            )
            .join(Task, Task.id == TaskDependencyReference.task_id)
            .where(
                Task.project_id == document.project_id,
                Task.spec_document_id == document.id,
            )
        )
    ).all()
    found = [
        {"task_id": task_id, "task_key": key or "", "reference": reference, "reason": reason}
        for task_id, key, reference, reason in rows
    ]
    found.sort(key=lambda item: (order.get(item["task_key"], len(order)), item["reference"]))
    return found
