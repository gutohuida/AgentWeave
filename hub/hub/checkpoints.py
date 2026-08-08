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

from . import worktrees
from .db.models import Checkpoint, Conversation, PermissionRequest, Question, Run, Task
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

# Questions still owed an answer when the checkpoint was taken.
_OPEN_QUESTION_STATES = (False,)

# Task states that are still work. Anything else is history and only bloats the envelope.
_LIVE_TASK_STATUSES = (
    "pending",
    "assigned",
    "in_progress",
    "under_review",
    "revision_needed",
)


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


async def latest_checkpoint(db, conversation_id: str) -> Optional[Checkpoint]:
    """The checkpoint a new one anchors on, or None for a conversation's first."""
    return (
        await db.execute(
            select(Checkpoint)
            .where(Checkpoint.conversation_id == conversation_id)
            .order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())
            .limit(1)
        )
    ).scalars().first()


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


def _files_from_runs(runs: List[Run], worktree: Optional[Path]) -> List[str]:
    """Every path the covered turns committed, deduplicated.

    Reads the per-run auto-snapshot SHAs. Before those were recorded (`Run.snapshot_commit_sha`,
    migration 0043) there was nothing to read, so a conversation whose turns predate it reports
    no changed files rather than a plausible guess.
    """
    if worktree is None or not worktree.exists():
        return []
    paths: set = set()
    for run in runs:
        if not run.snapshot_commit_sha:
            continue
        try:
            paths.update(worktrees.files_changed_in(worktree, run.snapshot_commit_sha))
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


async def _open_questions_for(db, conversation_id: str) -> List[Dict[str, Any]]:
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
    worktree: Optional[Path] = None,
    anchor: Optional[Checkpoint] = None,
) -> CheckpointEnvelope:
    """Everything a checkpoint knows without asking anybody."""
    runs = await runs_to_cover(db, conversation.id, anchor)
    return CheckpointEnvelope(
        files_changed=_files_from_runs(runs, worktree),
        tasks=await _tasks_for(db, conversation.project_id, conversation.agent),
        open_questions=await _open_questions_for(db, conversation.id),
        permission_decisions=await _permission_decisions_for(db, conversation.id),
        # An inherited `{"permission_mode": "manual"}` is what failed run-9058966b. A successor
        # inherits whatever is in force, so a checkpoint that omits it hides the cause.
        runtime_overrides=dict(conversation.runtime_overrides or {}),
        covers_from_run_id=runs[0].id if runs else None,
        covers_through_run_id=runs[-1].id if runs else None,
    )


def agent_worktree(repo_root: Optional[Path], agent: str) -> Optional[Path]:
    """Where the agent's commits live, without provisioning anything.

    `worktree_path` is a pure path computation; `ensure_worktree` would create one. Computing a
    checkpoint must never have the side effect of building a workspace for an agent that never
    ran.
    """
    if repo_root is None:
        return None
    try:
        return worktrees.worktree_path(repo_root, agent)
    except Exception:  # noqa: BLE001 — an unusable path is "no files", never a failed checkpoint
        logger.debug("could not resolve worktree for %r", agent, exc_info=True)
        return None


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
    visibility: str = "private",
) -> Checkpoint:
    """Persist a checkpoint. The envelope is written whether or not a body exists.

    That is the whole point of task 5.3: generation failing must degrade the record, not prevent
    it. A checkpoint with no body is `unwritten` — it still carries the computed half, which is
    the verifiable half — and `unwritten` is never presented as something to resume from, which
    the `ck_checkpoints_ready_has_a_body` constraint enforces at the schema level.
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
