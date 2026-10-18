"""A task's whole story, in the order it happened (`a-tasks-whole-story-is-in-its-drawer`).

Everything the Hub records about one task already exists in its own table -- transitions, the runs
bound to it and what they cost, evidence and every review of it, check runs, merges, divergences,
the questions it waited on -- and until this the app drew each in a different place, or not at all
(the visibility map of 2026-10-17: `override_reason`, per-task cost, review history and divergences
were never shown). This module joins them into one list of events, oldest first, with a summary on
top, so the drawer can answer "is this done, and how did it get here?" without a second request.

The order is the route's contract: events sorted by their time, ties broken by `KIND_ORDER`, so a
transition and the run that made it read cause before effect. Never raises for a missing optional
part (a project whose directory moved still has a story; the evidence wording is then null).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    AIJob,
    EventLog,
    EvidenceReview,
    InboundQueueEntry,
    Question,
    RequirementEvidence,
    Run,
    RunDivergence,
    Task,
    TaskCheckRun,
    TaskIntegration,
    TaskTransition,
    TurnUsage,
)

#: Tie-break for events stamped in the same instant: what caused a thing reads before the thing.
KIND_ORDER = {
    "created": 0,
    "transition": 1,
    "run": 2,
    "question": 3,
    "evidence": 4,
    "check": 5,
    "integration": 6,
    "divergence": 7,
    "turn": 8,
    "workspace": 9,
}

#: Event-log entries about a task's checkout that the story tells (F711). Only the failure: a
#: release that worked is the ordinary end of a decided task and says nothing new.
_WORKSPACE_EVENTS = {"task_worktree_release_failed": "release_failed"}


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _sort_key(event: Dict[str, Any]):
    return (event["at"] or "", KIND_ORDER.get(event["kind"], 99), event.get("id") or "")


async def _all(session: AsyncSession, query) -> List[Any]:
    return list((await session.execute(query)).scalars().all())


async def story_for(session: AsyncSession, task: Task) -> Dict[str, Any]:
    """`{task, summary, events}` for *task*. Read-only."""
    from .api.v1.spec import _evidence_views

    transitions = await _all(
        session,
        select(TaskTransition)
        .where(TaskTransition.task_id == task.id)
        .order_by(TaskTransition.sequence),
    )
    runs = await _all(session, select(Run).where(Run.task_id == task.id))
    usage_by_run: Dict[str, List[TurnUsage]] = {}
    if runs:
        for row in await _all(
            session, select(TurnUsage).where(TurnUsage.run_id.in_([run.id for run in runs]))
        ):
            usage_by_run.setdefault(row.run_id, []).append(row)
    evidence = await _all(
        session,
        select(RequirementEvidence)
        .where(RequirementEvidence.task_id == task.id)
        .order_by(RequirementEvidence.produced_at, RequirementEvidence.id),
    )
    reviews_by_piece: Dict[str, List[EvidenceReview]] = {}
    if evidence:
        for review in await _all(
            session,
            select(EvidenceReview)
            .where(EvidenceReview.evidence_id.in_([piece.id for piece in evidence]))
            .order_by(EvidenceReview.sequence),
        ):
            reviews_by_piece.setdefault(review.evidence_id, []).append(review)
    views = await _evidence_views(session, task.project_id, evidence)
    checks = await _all(session, select(TaskCheckRun).where(TaskCheckRun.task_id == task.id))
    integrations = await _all(
        session, select(TaskIntegration).where(TaskIntegration.task_id == task.id)
    )
    divergences = await _all(
        session,
        select(RunDivergence)
        .where(RunDivergence.task_id == task.id)
        .order_by(RunDivergence.sequence),
    )
    questions = await _all(session, select(Question).where(Question.blocked_task_id == task.id))
    # Turns for this task the Hub refused, gave up on or withdrew (F711): "Could not prepare the
    # checkout" lived only on the queue entry, so a jammed task's story skipped the jam. A turn
    # that ran is already its run; only an entry with a refusal or an ending on it is told here.
    held_turns = await _all(
        session,
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == task.project_id,
            or_(InboundQueueEntry.task_id == task.id, InboundQueueEntry.review_task_id == task.id),
            or_(
                InboundQueueEntry.waiting_reason.is_not(None),
                InboundQueueEntry.abandoned_reason.is_not(None),
            ),
        )
        .order_by(InboundQueueEntry.sequence),
    )
    workspace_events = await _all(
        session,
        select(EventLog).where(
            EventLog.project_id == task.project_id,
            EventLog.event_type.in_(list(_WORKSPACE_EVENTS)),
            EventLog.data["task_id"].as_string() == task.id,
        ),
    )
    job_names: Dict[str, str] = {}
    job_ids = {row.job_id for row in transitions if row.job_id}
    if job_ids:
        job_names = {
            job.id: job.name
            for job in await _all(session, select(AIJob).where(AIJob.id.in_(job_ids)))
        }

    events: List[Dict[str, Any]] = [
        {
            "kind": "created",
            "id": task.id,
            "at": _iso(task.created_at),
            "by": task.assigner,
        }
    ]
    for row in transitions:
        events.append(
            {
                "kind": "transition",
                "id": row.id,
                "at": _iso(row.created_at),
                "from": row.from_status,
                "to": row.to_status,
                "actor_kind": row.actor_kind,
                "actor": row.actor_agent
                or (job_names.get(row.job_id or "") if row.job_id else None)
                or ("operator" if row.actor_kind == "operator" else None),
                "origin": row.origin,
                "job": job_names.get(row.job_id or "") if row.job_id else None,
                "run_id": row.run_id,
                "override_reason": row.override_reason,
            }
        )

    total_usd_micros = 0
    total_tokens = 0
    premium = 0.0
    for run in runs:
        rows = usage_by_run.get(run.id, [])
        usd = sum(row.api_equivalent_usd_micros or 0 for row in rows)
        tokens = sum(row.total_tokens or 0 for row in rows)
        requests = sum(row.premium_requests or 0 for row in rows)
        total_usd_micros += usd
        total_tokens += tokens
        premium += requests
        duration = None
        if run.started_at and run.ended_at:
            duration = max(0, int((run.ended_at - run.started_at).total_seconds()))
        events.append(
            {
                "kind": "run",
                "id": run.id,
                "at": _iso(run.started_at),
                "agent": run.agent,
                "status": run.status,
                "ended_at": _iso(run.ended_at),
                "duration_seconds": duration,
                "model": next((row.model for row in rows if row.model), None),
                "runner": next((row.runner for row in rows if row.runner), None),
                "cost_usd": round(usd / 1_000_000, 4) if rows else None,
                "tokens": tokens if rows else None,
                "premium_requests": requests or None,
                "conversation_id": run.conversation_id,
                "error": run.error,
            }
        )

    counts = {"accepted": 0, "rejected": 0, "awaiting": 0}
    for piece, view in zip(evidence, views, strict=True):
        counts[piece.review_state] = counts.get(piece.review_state, 0) + 1
        events.append(
            {
                "kind": "evidence",
                "id": piece.id,
                "at": _iso(piece.produced_at),
                "evidence": view,
                "reviews": [
                    {
                        "decision": review.decision,
                        "actor_kind": review.actor_kind,
                        "actor": review.actor,
                        "reason": review.reason,
                        "at": _iso(review.created_at),
                    }
                    for review in reviews_by_piece.get(piece.id, [])
                ],
            }
        )

    for row in checks:
        results = list(row.results or []) if isinstance(row.results, list) else []
        events.append(
            {
                "kind": "check",
                "id": row.id,
                "at": _iso(row.started_at),
                "state": row.state,
                "ended_at": _iso(row.ended_at),
                "results": results,
                "error": row.error or None,
                "merged_sha": row.merged_sha,
            }
        )

    merged: List[str] = []
    for row in integrations:
        if row.outcome == "merged" and row.commit_sha:
            merged.append(row.commit_sha)
        events.append(
            {
                "kind": "integration",
                "id": row.id,
                "at": _iso(row.created_at),
                "outcome": row.outcome,
                "commit_sha": row.commit_sha,
                "source_branch": row.source_branch,
                "target_branch": row.target_branch,
                "reason": row.reason or None,
                "mechanism": row.mechanism,
                "actor_kind": row.actor_kind,
                "actor": row.actor,
            }
        )

    for row in divergences:
        events.append(
            {
                "kind": "divergence",
                "id": row.id,
                "at": _iso(row.created_at),
                "agent": row.agent,
                "run_id": row.run_id,
                "policy": row.policy_applied,
                "outcome": row.outcome,
                "task_status_at_end": row.task_status_at_end,
                "resolved_at": _iso(row.resolved_at),
            }
        )

    for row in questions:
        events.append(
            {
                "kind": "question",
                "id": row.id,
                "at": _iso(row.created_at),
                "agent": row.from_agent,
                "question": row.question,
                "answered": row.answered,
                "answer": row.answer,
                "declined": row.declined,
                "wait_ended_at": _iso(row.wait_ended_at),
            }
        )

    for row in held_turns:
        events.append(
            {
                "kind": "turn",
                "id": row.id,
                # The refusal itself carries no time of its own; the turn's arrival does.
                "at": _iso(row.arrived_at),
                "agent": row.agent,
                "review": row.review_task_id == task.id,
                "state": row.state,
                "refusal": row.waiting_reason,
                "ended_reason": row.abandoned_reason,
                "attempts": row.delivery_attempts,
                "run_id": row.delivered_in_run_id,
            }
        )

    for row in workspace_events:
        data = row.data if isinstance(row.data, dict) else {}
        events.append(
            {
                "kind": "workspace",
                "id": row.id,
                "at": _iso(row.timestamp),
                "outcome": _WORKSPACE_EVENTS[row.event_type],
                "reason": data.get("reason"),
            }
        )

    events.sort(key=_sort_key)
    return {
        "task": {"id": task.id, "title": task.title, "status": task.status},
        "summary": {
            "runs": len(runs),
            "cost_usd": round(total_usd_micros / 1_000_000, 4) if usage_by_run else None,
            "tokens": total_tokens if usage_by_run else None,
            "premium_requests": premium or None,
            "evidence": counts,
            "merged": merged,
            "overrides": sum(1 for row in transitions if row.override_reason),
        },
        "events": events,
    }
