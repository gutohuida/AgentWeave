"""Deleting a specification document or a task, and everything that exists only because of it.

`the-operator-can-delete-a-document-a-task-or-an-archived-agent` (F532). The operator's, never an
agent's: the routes sit on the project credential. What the corpus or a live run depends on is
refused before anything is written — a capability, an archived or folded change, a document whose
flow is running, a task (or a document's task) with a run in progress.

**What goes, and what only loses a pointer.** Rows that exist *for* the deleted thing go with it:
a task's dependencies, links, transitions, checks, integrations, evidence and queued input; a
document's requirements, their revisions and evidence, its events, its tasks and its stopped flows.
Rows that only *mention* it are history and stay, with the pointer cleared: a run that worked the
task, a conversation bound to it, a message about it, a delivered queue entry. An agent is never
deleted here (`agent_lifecycle`: its name attributes that history).

**The maps are the cascade.** `PRAGMA foreign_keys` is never on for this app's SQLite, so nothing
fails when a table is forgotten; the rows just keep naming something that is gone. Every column that
points at a task, requirement, evidence row, document, loop or job is listed below, and
`test_every_reference_column_is_covered_by_a_cascade` fails when a new one is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    AIJob,
    Base,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecDocumentMerge,
    SpecRequirement,
    Task,
)

#: The row goes with the deleted thing.
DELETE = "delete"
#: The row is history that only mentions it: kept, pointer cleared.
CLEAR = "clear"
#: Input still waiting to be delivered goes; a delivered entry is history and is cleared.
QUEUED = "queued"
#: Deleted through its own cascade (a document's tasks and flows), not by a bulk statement.
CASCADE = "cascade"
#: Its existence refuses the delete (a merge names the document).
REFUSE = "refuse"

Reference = Tuple[str, str, str]

TASK_REFERENCES: List[Reference] = [
    ("task_dependencies", "task_id", DELETE),
    ("task_dependencies", "depends_on_task_id", DELETE),
    ("task_dependency_references", "task_id", DELETE),
    ("task_integrations", "task_id", DELETE),
    ("task_requirement_references", "task_id", DELETE),
    ("task_transitions", "task_id", DELETE),
    ("task_check_runs", "task_id", DELETE),
    ("task_requirement_links", "task_id", DELETE),
    ("run_divergences", "task_id", CLEAR),
    ("requirement_evidence", "task_id", DELETE),
    ("inbound_queue_entries", "task_id", QUEUED),
    ("inbound_queue_entries", "review_task_id", QUEUED),
    ("runs", "task_id", CLEAR),
    ("conversations", "task_id", CLEAR),
    ("messages", "task_id", CLEAR),
    ("questions", "blocked_task_id", CLEAR),
]

EVIDENCE_REFERENCES: List[Reference] = [
    ("evidence_footprints", "evidence_id", DELETE),
    ("evidence_reviews", "evidence_id", DELETE),
    ("requirement_drift", "evidence_id", DELETE),
]

REQUIREMENT_REFERENCES: List[Reference] = [
    ("requirement_evidence", "requirement_id", DELETE),
    ("spec_requirement_revisions", "requirement_id", DELETE),
    ("task_requirement_links", "requirement_id", DELETE),
    ("requirement_drift", "requirement_id", DELETE),
]

DOCUMENT_REFERENCES: List[Reference] = [
    ("spec_document_merges", "change_document_id", REFUSE),
    ("spec_document_merges", "capability_document_id", REFUSE),
    ("tasks", "spec_document_id", CASCADE),
    ("loops", "spec_document_id", CASCADE),
    ("spec_document_events", "document_id", DELETE),
    ("spec_edit_proposals", "document_id", DELETE),
    ("spec_rigor_events", "document_id", DELETE),
    ("spec_requirement_revisions", "document_id", DELETE),
    ("spec_requirements", "document_id", DELETE),
]

LOOP_REFERENCES: List[Reference] = [
    ("tasks", "loop_id", CLEAR),
    ("event_logs", "loop_id", CLEAR),
    ("checkpoints", "loop_id", CLEAR),
]

JOB_REFERENCES: List[Reference] = [
    ("loops", "job_id", DELETE),
    ("job_runs", "job_id", DELETE),
    ("agent_job_deletions", "job_id", DELETE),
    ("inbound_queue_entries", "job_id", CLEAR),
    ("task_transitions", "job_id", CLEAR),
]


def all_references() -> List[Reference]:
    return [
        *TASK_REFERENCES,
        *EVIDENCE_REFERENCES,
        *REQUIREMENT_REFERENCES,
        *DOCUMENT_REFERENCES,
        *LOOP_REFERENCES,
        *JOB_REFERENCES,
    ]


class DeletionRefusedError(Exception):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


@dataclass
class DeletedDocument:
    path: str
    tasks: List[str]
    requirements: int


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


async def _apply(session: AsyncSession, references: Iterable[Reference], ids: Set[str]) -> None:
    if not ids:
        return
    for table_name, column_name, action in references:
        table = _table(table_name)
        column = table.c[column_name]
        if action == DELETE:
            await session.execute(table.delete().where(column.in_(ids)))
        elif action == CLEAR:
            await session.execute(table.update().where(column.in_(ids)).values({column_name: None}))
        elif action == QUEUED:
            await session.execute(table.delete().where(column.in_(ids), table.c.state == "queued"))
            await session.execute(table.update().where(column.in_(ids)).values({column_name: None}))


async def _delete_evidence(session: AsyncSession, evidence_ids: Set[str]) -> None:
    await _apply(session, EVIDENCE_REFERENCES, evidence_ids)
    if evidence_ids:
        await session.execute(
            _table("requirement_evidence").delete().where(RequirementEvidence.id.in_(evidence_ids))
        )


async def _refuse_active_runs(session: AsyncSession, task_ids: Sequence[str]) -> None:
    if not task_ids:
        return
    running = await session.scalar(
        select(Run.id).where(Run.task_id.in_(task_ids), Run.status == "running").limit(1)
    )
    if running is not None:
        raise DeletionRefusedError(
            f"run {running} is working on this task right now; stop it or let it finish first",
            code="delete_run_active",
        )


async def _delete_tasks(session: AsyncSession, task_ids: Set[str]) -> None:
    if not task_ids:
        return
    evidence = set(
        (
            await session.execute(
                select(RequirementEvidence.id).where(RequirementEvidence.task_id.in_(task_ids))
            )
        ).scalars()
    )
    await _delete_evidence(session, evidence)
    await _apply(session, TASK_REFERENCES, task_ids)
    await session.execute(_table("tasks").delete().where(Task.id.in_(task_ids)))


async def delete_task(session: AsyncSession, task: Task) -> None:
    """Delete one task. Refused while a run bound to it is in progress."""
    await _refuse_active_runs(session, [task.id])
    await _delete_tasks(session, {task.id})


async def delete_document(session: AsyncSession, document: SpecDocument) -> DeletedDocument:
    """Delete a document's rows and everything it produced. The caller removes the file afterwards,
    once the transaction has committed: a transaction rolls back and a file delete does not."""
    if document.kind == "capability":
        raise DeletionRefusedError(
            "a capability is the corpus; change it through a merge instead",
            code="delete_capability",
        )
    if document.phase == "archived":
        raise DeletionRefusedError(
            "an archived document is the record of what shipped and is kept", code="delete_archived"
        )
    merged = await session.scalar(
        select(SpecDocumentMerge.id)
        .where(
            (SpecDocumentMerge.change_document_id == document.id)
            | (SpecDocumentMerge.capability_document_id == document.id)
        )
        .limit(1)
    )
    if merged is not None:
        raise DeletionRefusedError(
            "this change has been folded into a capability, so the corpus cites it; archive it "
            "instead",
            code="delete_folded",
        )
    task_ids = set(
        (
            await session.execute(select(Task.id).where(Task.spec_document_id == document.id))
        ).scalars()
    )
    await _refuse_active_runs(session, sorted(task_ids))
    flows = (
        await session.execute(
            select(Loop.id, Loop.job_id, Loop.stopped_at, Loop.archived_at, AIJob.enabled)
            .join(AIJob, AIJob.id == Loop.job_id, isouter=True)
            .where(Loop.spec_document_id == document.id)
        )
    ).all()
    if any(
        stopped is None and archived is None and enabled
        for _, _, stopped, archived, enabled in flows
    ):
        raise DeletionRefusedError(
            "this document's flow is still running; stop it first", code="delete_flow_running"
        )

    requirement_ids = set(
        (
            await session.execute(
                select(SpecRequirement.id).where(SpecRequirement.document_id == document.id)
            )
        ).scalars()
    )
    evidence = set(
        (
            await session.execute(
                select(RequirementEvidence.id).where(
                    RequirementEvidence.requirement_id.in_(requirement_ids)
                )
            )
        ).scalars()
    )
    await _delete_evidence(session, evidence)
    await _delete_tasks(session, task_ids)
    loop_ids = {loop_id for loop_id, *_ in flows}
    job_ids = {job_id for _, job_id, *_ in flows if job_id}
    await _apply(session, LOOP_REFERENCES, loop_ids)
    await _apply(session, JOB_REFERENCES, job_ids)
    await session.execute(_table("loops").delete().where(Loop.id.in_(loop_ids)))
    await session.execute(_table("ai_jobs").delete().where(AIJob.id.in_(job_ids)))
    await _apply(session, REQUIREMENT_REFERENCES, requirement_ids)
    await _apply(
        session,
        [ref for ref in DOCUMENT_REFERENCES if ref[2] == DELETE],
        {document.id},
    )
    await session.execute(_table("spec_documents").delete().where(SpecDocument.id == document.id))
    return DeletedDocument(
        path=document.path, tasks=sorted(task_ids), requirements=len(requirement_ids)
    )
