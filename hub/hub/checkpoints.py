"""Building a checkpoint: the half the Hub computes, and the record that carries both halves.

The division is verifiability, not style (design.md, "Deterministic fields are computed,
generated fields are written"). What the Hub can check, it must not delegate — the observed
failures are concrete: an agent asked for a timestamp it could not obtain **invented** one, and
an agent asked for pending work reported none from a worktree that is *always* clean, because
the Hub commits everything at the end of every turn.

So everything here is read out of the database and out of git. Nothing in this module asks a
model for anything; `worker.py` does that, and only for judgement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import worktrees
from .db.models import (
    Checkpoint,
    Conversation,
    JobRun,
    Loop,
    PermissionRequest,
    Question,
    Run,
    Task,
)
from .task_transitions import LIVE_STATUSES
from .utils import short_id

logger = logging.getLogger(__name__)

# Task 5.4. `tasks` is project-scoped and carries no `conversation_id`, so the list a checkpoint
# carries is the agent's whole list — identical across every conversation it is running
# concurrently. Stated on the record rather than left for a reader to infer, because a list that
# looks conversation-specific and is not is exactly the kind of quiet wrongness this change
# exists to remove. Binding tasks to conversations is a separate change.
TASK_SCOPE_NOTE = (
    "These are every task assigned to this agent across the project. Tasks carry no "
    "conversation, so this list is identical for all of this agent's concurrent conversations "
    "and is not specific to this one."
)

# Task 7.3. The loop-scoped counterpart to TASK_SCOPE_NOTE, same "explicit scope hides nothing"
# reasoning: a loop firing's queue is its whole task list, in every status, not just the live
# ones — a checkpoint that quietly dropped a rejected or approved task would misstate the queue
# the next firing is briefed on.
LOOP_TASK_SCOPE_NOTE = (
    "These are every task belonging to this loop, in every status. This is the loop's whole "
    "queue, not just what is currently active."
)

# Questions still owed an answer when the checkpoint was taken.
_OPEN_QUESTION_STATES = (False,)

# Task states that are still work. Anything else is history and only bloats the envelope.
# The same derived set `agents._ACTIVE_TASK_STATUSES` reads — these were two identical literals in
# two files until `loop-notices-and-reacts` 3.8.
_LIVE_TASK_STATUSES = tuple(sorted(LIVE_STATUSES))


@dataclass
class CheckpointEnvelope:
    """The computed half. Every field is derived; none is ever solicited from a model."""

    files_changed: List[str] = field(default_factory=list)
    tasks: Dict[str, Any] = field(default_factory=dict)
    open_questions: List[Dict[str, Any]] = field(default_factory=list)
    permission_decisions: List[Dict[str, Any]] = field(default_factory=list)
    runtime_overrides: Dict[str, Any] = field(default_factory=dict)
    covers_from_run_id: Optional[str] = None
    covers_through_run_id: Optional[str] = None


async def get_checkpoint_by_id(db, checkpoint_id: Optional[str]) -> Optional[Checkpoint]:
    """Look a checkpoint up by its stable `ckpt-` id.

    Not `session.get(Checkpoint, checkpoint_id)`: the primary key is `sequence`, an autoincrement
    integer, not `id` (F55) — `session.get()` looks up by primary key, so it would compare a
    `ckpt-…` string against an integer column and never match. Every call site that used to read
    `db.get(Checkpoint, ...)` reads this instead.
    """
    if checkpoint_id is None:
        return None
    result = await db.execute(select(Checkpoint).where(Checkpoint.id == checkpoint_id))
    return result.scalar_one_or_none()


async def latest_checkpoint(db, conversation_id: str) -> Optional[Checkpoint]:
    """The checkpoint a new one anchors on, or None for a conversation's first."""
    return (
        (
            await db.execute(
                select(Checkpoint)
                .where(Checkpoint.conversation_id == conversation_id)
                .order_by(Checkpoint.sequence.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def latest_checkpoint_for_loop(db: AsyncSession, loop_id: str) -> Optional[Checkpoint]:
    """The checkpoint a loop's next firing briefs from — its most recent across EVERY
    conversation it has ever fired into, not just the one about to run.

    Mirrors `latest_checkpoint`'s shape exactly (task 7.2, design D4 item 2): every firing
    creates a new conversation (`scheduler.py:338`), so continuity for a loop has to be found by
    `Checkpoint.loop_id`, never by `conversation_id` — a same-conversation query would only ever
    find None, since a loop's *next* firing is, by construction, a conversation that does not
    exist yet.

    Ordered by `sequence`, not `created_at` (F55): two firings completing in the same clock tick
    used to tie-break on a random id and could return the older checkpoint as "latest", silently.
    """
    return (
        (
            await db.execute(
                select(Checkpoint)
                .where(Checkpoint.loop_id == loop_id)
                .order_by(Checkpoint.sequence.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def loop_for_conversation(db: AsyncSession, conversation_id: str) -> Optional[Loop]:
    """The `Loop` a conversation was fired into, or None for a conversation that is not a loop
    firing at all (a directly-run conversation, or a plain job's).

    Task 7.1's join, `JobRun.conversation_id` -> `job_id` -> `Loop.job_id`, the same one
    `2026-08-18-many-named-loops` D7 already uses in `_batch_loop_summaries`
    (`api/v1/jobs.py:98`). Derived once here so a caller needing it for both `compute_envelope`
    and `create_checkpoint` (`generate_checkpoint`, `checkpoint_generation.py`) does it a single
    time rather than re-querying per call.
    """
    job_id = (
        await db.execute(
            select(JobRun.job_id).where(JobRun.conversation_id == conversation_id).limit(1)
        )
    ).scalar_one_or_none()
    if job_id is None:
        return None
    return (await db.execute(select(Loop).where(Loop.job_id == job_id))).scalars().first()


async def runs_to_cover(db, conversation_id: str, anchor: Optional[Checkpoint]) -> List[Run]:
    """The turns a new checkpoint accounts for: those after the anchor, or all of them.

    Anchoring is why this is a slice rather than the whole list. Regenerating from the entire
    transcript loses information gradually and costs the worker full price every time; reading
    the predecessor plus what came after does neither.

    Falls back to *all* runs when the anchor names a run this conversation no longer has —
    covering a turn twice is a redundancy, whereas silently covering none is a hole.
    """
    runs = list(
        (
            await db.execute(
                select(Run)
                .where(Run.conversation_id == conversation_id)
                .order_by(Run.started_at, Run.id)
            )
        )
        .scalars()
        .all()
    )
    if anchor is None or anchor.covers_through_run_id is None:
        return runs

    for index, run in enumerate(runs):
        if run.id == anchor.covers_through_run_id:
            return runs[index + 1 :]

    logger.warning(
        "checkpoint %s anchors on run %s, which conversation %s no longer has; covering all turns",
        anchor.id,
        anchor.covers_through_run_id,
        conversation_id,
    )
    return runs


def _files_from_runs(runs: List[Run], repo_root: Optional[Path]) -> List[str]:
    """Every path the covered turns committed, deduplicated.

    Reads the per-run auto-snapshot SHAs. Before those were recorded (`Run.snapshot_commit_sha`,
    migration 0043) there was nothing to read, so a conversation whose turns predate it reports
    no changed files rather than a plausible guess.

    **The project repo root, not the workspace a run used — task 6.6, and the reason is measured.**
    Linked worktrees share one object database, so `git show` from the repo root reads a commit
    made in any of them, *including one whose checkout has since been removed*. Resolving each
    run to the checkout it ran in would therefore be strictly worse under per-task isolation: a
    task checkout is released when the task is approved (design D5), so exactly the runs belonging
    to finished work — the ones a checkpoint most wants to describe — would resolve to a directory
    that no longer exists and report nothing. One root that always exists answers for every run.
    """
    if repo_root is None or not repo_root.exists():
        return []
    paths: set = set()
    for run in runs:
        if not run.snapshot_commit_sha:
            continue
        try:
            paths.update(worktrees.files_changed_in(repo_root, run.snapshot_commit_sha))
        except worktrees.GitCommandError:
            logger.warning(
                "could not read files for snapshot %s", run.snapshot_commit_sha, exc_info=True
            )
    return sorted(paths)


async def _tasks_for(db, project_id: str, agent: str) -> Dict[str, Any]:
    rows = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.assignee == agent,
                    Task.status.in_(_LIVE_TASK_STATUSES),
                )
                .order_by(Task.updated.desc(), Task.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "scope": "agent",
        "note": TASK_SCOPE_NOTE,
        "items": [
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "assigner": task.assigner,
            }
            for task in rows
        ],
    }


async def _tasks_for_loop(db: AsyncSession, loop_id: str) -> Dict[str, Any]:
    """Task 7.3. Every status, unlike `_tasks_for`'s `_LIVE_TASK_STATUSES` filter — a loop's
    queue includes what it has already finished, rejected or approved, and a briefing that
    silently dropped those would misstate the queue the next firing is picking up from."""
    rows = list(
        (
            await db.execute(
                select(Task).where(Task.loop_id == loop_id).order_by(Task.updated.desc(), Task.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "scope": "loop",
        "note": LOOP_TASK_SCOPE_NOTE,
        "items": [
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "assigner": task.assigner,
            }
            for task in rows
        ],
    }


async def _open_questions_for(db, conversation_id: str) -> List[Dict[str, Any]]:
    """What the operator was asked and has not settled, for the successor agent.

    **A question whose wait ended is kept, and marked** — the opposite decision from every other
    reader of this idea (`a-task-waits-while-its-run-waits`, design D6). The conversation rail and
    the loop's open-question count both stop saying somebody is waiting, because their audience is
    the operator and a count they read as "these still need me" must not include waits nobody is
    in. This list's audience is the successor *agent*, which needs to know the question was asked,
    never answered, and decided without the operator — the most useful thing on the list, not the
    thing to drop.

    It also keeps `LIVE_STATUSES` honest. That collection deliberately excludes `blocked`, so a
    checkpoint omits the task a wait parked, and the stated cover for that omission is this list.
    If the ended wait were dropped here instead of marked, that omission would have no cover left
    and the roster's "active task" derivation would have to be reopened.
    """
    rows = list(
        (
            await db.execute(
                select(Question)
                .where(
                    Question.conversation_id == conversation_id,
                    Question.answered.in_(_OPEN_QUESTION_STATES),
                )
                .order_by(Question.created_at, Question.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "question": row.question,
            "blocking": row.blocking,
            "asked_at": row.created_at.isoformat() if row.created_at else None,
            # Named rather than omitted, and named rather than left to read as merely open: the
            # successor must be able to tell "nobody has answered this yet" from "nobody answered
            # this and your predecessor decided without them".
            "wait_ended": row.wait_ended_at is not None,
        }
        for row in rows
    ]


async def _permission_decisions_for(db, conversation_id: str) -> List[Dict[str, Any]]:
    """What the operator allowed and denied. Denials are the load-bearing half: an agent that
    was refused a tool call and worked around it has a successor that needs to know."""
    rows = list(
        (
            await db.execute(
                select(PermissionRequest)
                .where(PermissionRequest.conversation_id == conversation_id)
                .order_by(PermissionRequest.created_at, PermissionRequest.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "tool": row.tool_name,
            "status": row.status,
            "decided_by": row.decided_by,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        }
        for row in rows
    ]


async def compute_envelope(
    db,
    conversation: Conversation,
    *,
    repo_root: Optional[Path] = None,
    anchor: Optional[Checkpoint] = None,
    loop: Optional[Loop] = None,
) -> CheckpointEnvelope:
    """Everything a checkpoint knows without asking anybody.

    Task 7.3. `loop`, when supplied, means this conversation is a firing of that loop: `tasks`
    becomes the loop's whole queue (`_tasks_for_loop`) instead of the agent-wide list
    (`_tasks_for`). The caller (`generate_checkpoint`) is the one that decides whether a loop
    applies, via `loop_for_conversation` — this function does not re-derive it.
    """
    runs = await runs_to_cover(db, conversation.id, anchor)
    return CheckpointEnvelope(
        files_changed=_files_from_runs(runs, repo_root),
        tasks=(
            await _tasks_for_loop(db, loop.id)
            if loop is not None
            else await _tasks_for(db, conversation.project_id, conversation.agent)
        ),
        open_questions=await _open_questions_for(db, conversation.id),
        permission_decisions=await _permission_decisions_for(db, conversation.id),
        # An inherited `{"permission_mode": "manual"}` is what failed run-9058966b. A successor
        # inherits whatever is in force, so a checkpoint that omits it hides the cause.
        runtime_overrides=dict(conversation.runtime_overrides or {}),
        covers_from_run_id=runs[0].id if runs else None,
        covers_through_run_id=runs[-1].id if runs else None,
    )


async def create_checkpoint(
    db,
    conversation: Conversation,
    *,
    trigger: str,
    envelope: CheckpointEnvelope,
    body: Optional[str],
    anchor: Optional[Checkpoint] = None,
    worker_invocation_id: Optional[str] = None,
    runner: Optional[str] = None,
    model: Optional[str] = None,
    visibility: str = "project",
    loop: Optional[Loop] = None,
) -> Checkpoint:
    """Persist a checkpoint. The envelope is written whether or not a body exists.

    That is the whole point of task 5.3: generation failing must degrade the record, not prevent
    it. A checkpoint with no body is `unwritten` — it still carries the computed half, which is
    the verifiable half — and `unwritten` is never presented as something to resume from, which
    the `ck_checkpoints_ready_has_a_body` constraint enforces at the schema level.

    Task 7.1. `loop`, when supplied, stamps `Checkpoint.loop_id` — the column
    `latest_checkpoint_for_loop` reads to find a loop's continuity across the new conversation
    every firing creates (design D4 item 1). Not derived here from `conversation`: the caller
    already has it (or knows it does not apply) from `loop_for_conversation`, and deriving it
    twice per checkpoint would be the same redundant join `loop_for_conversation`'s own docstring
    argues against.
    """
    checkpoint_id = f"ckpt-{short_id()}"
    # Whitespace is not a body. Collapsing blank to NULL keeps "cleared" and "never written" one
    # state, the same rule `Agent.description` follows — and stops a worker that returned a
    # newline from producing a checkpoint that claims to be readable.
    written = (body or "").strip() or None
    checkpoint = Checkpoint(
        id=checkpoint_id,
        project_id=conversation.project_id,
        conversation_id=conversation.id,
        agent=conversation.agent,
        trigger=trigger,
        status="ready" if written else "unwritten",
        visibility=visibility,
        previous_checkpoint_id=anchor.id if anchor else None,
        # The first checkpoint founds the lineage and names it after itself.
        lineage_id=anchor.lineage_id if anchor else checkpoint_id,
        covers_from_run_id=envelope.covers_from_run_id,
        covers_through_run_id=envelope.covers_through_run_id,
        worker_invocation_id=worker_invocation_id,
        runner=runner,
        model=model,
        loop_id=loop.id if loop else None,
        files_changed=envelope.files_changed,
        tasks=envelope.tasks,
        open_questions=envelope.open_questions,
        permission_decisions=envelope.permission_decisions,
        runtime_overrides=envelope.runtime_overrides,
        body=written,
    )
    db.add(checkpoint)
    await db.commit()
    return checkpoint


async def checkpoint_by_task_author(
    db: AsyncSession, task_id: str, *, loop_id: Optional[str] = None
) -> Optional[Checkpoint]:
    """The checkpoint written by the agent that **completed** *task_id*, not the loop's newest.

    Finding F44. `latest_checkpoint_for_loop` filters on `loop_id` alone and takes the most recent,
    which is the right answer for a loop's *next firing* — its docstring reasons about exactly that,
    and in a one-agent loop "latest for the loop" and "the author's" are the same row.

    A flow breaks the identity. With three agents working concurrently the newest checkpoint belongs
    to whoever finished last, so the reviewer of task X could be briefed with an unrelated agent's
    account of task Y while being told it is what a reviewer will need. Measured on the live
    database when F43 was recorded: three notes on one loop from three different agents, of which
    exactly one concerned the task actually queued for review — so two firings in three would have
    briefed the wrong author's work.

    Resolved through the transition history rather than through `Task.updated_by_run_id`, for the
    reason `agent_that_completed` gives about that column: it is a single mutable field that the
    next write overwrites, and being unable to answer this question is why the append-only table
    exists. By `sequence` and not `created_at`, likewise — transitions staged in one flush share a
    timestamp, and after a revision cycle an earlier completion by another run is exactly what must
    not be chosen.

    `loop_id`, when given, is a guard rather than a filter: it refuses a checkpoint that belongs to
    a different loop, which would otherwise be reachable if a task moved between loops. Returns
    None when the author left no checkpoint, which is the ordinary case until F43's trigger has run
    and stays the case for an agent that recorded no notes.
    """
    from .db.models import TaskTransition

    run_id = (
        await db.execute(
            select(TaskTransition.run_id)
            .where(TaskTransition.task_id == task_id)
            .where(TaskTransition.to_status == "completed")
            .where(TaskTransition.run_id.is_not(None))
            .order_by(TaskTransition.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run_id is None:
        return None

    conversation_id = (
        await db.execute(select(Run.conversation_id).where(Run.id == run_id).limit(1))
    ).scalar_one_or_none()
    if conversation_id is None:
        return None

    query = (
        select(Checkpoint)
        .where(Checkpoint.conversation_id == conversation_id)
        .order_by(Checkpoint.sequence.desc())
        .limit(1)
    )
    if loop_id is not None:
        query = query.where(Checkpoint.loop_id == loop_id)
    return (await db.execute(query)).scalars().first()
