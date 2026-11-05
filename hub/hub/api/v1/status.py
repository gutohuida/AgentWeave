"""GET /api/v1/projects/{project_id}/status — project health snapshot.

GET /api/v1/work/running — the instance-wide answer to "what work is running", which the app
window asks before closing stops the Hub (change `agentweave-is-its-own-app-on-windows`, D4).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import builds as builds_module
from ... import landing_queue
from ...auth import get_operator, get_project
from ...db.engine import get_session
from ...db.models import (
    Build,
    InboundQueueEntry,
    Message,
    OperatorCredential,
    Project,
    Question,
    Run,
    SpecDocument,
    Task,
    TaskCheckRun,
    TaskLanding,
)
from ...schemas.common import StatusResponse
from ...schemas.messages import OPERATOR_SENDER

router = APIRouter(prefix="/status", tags=["status"])
instance_router = APIRouter(prefix="/work", tags=["status"])

_ACTIVE_TASK_STATUSES = ["in_progress", "assigned", "pending"]


@router.get("", response_model=StatusResponse)
async def get_status(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, project_name = project
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    (
        total_msgs,
        pending_msgs,
        task_rows,
        total_qs,
        unanswered_qs,
        sender_rows,
        assignee_rows,
    ) = await asyncio.gather(
        session.scalar(
            select(func.count()).select_from(Message).where(Message.project_id == project_id)
        ),
        # Pending mail is mail not yet delivered, which its inbound entry records; `Message.read`
        # is API bookkeeping nothing in the product sets (F259).
        session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.project_id == project_id,
                Message.id.in_(
                    select(InboundQueueEntry.message_id).where(
                        InboundQueueEntry.project_id == project_id,
                        InboundQueueEntry.state == "queued",
                        InboundQueueEntry.message_id.is_not(None),
                    )
                ),
            )
        ),
        session.execute(
            select(Task.status, func.count())
            .where(Task.project_id == project_id)
            .group_by(Task.status)
        ),
        session.scalar(
            select(func.count()).select_from(Question).where(Question.project_id == project_id)
        ),
        session.scalar(
            select(func.count())
            .select_from(Question)
            .where(Question.project_id == project_id, Question.answered == False)  # noqa: E712
        ),
        session.execute(
            select(Message.sender)
            .distinct()
            .where(
                Message.project_id == project_id,
                Message.timestamp >= cutoff,
                # `agents_active`: the operator sends mail too, and is not an agent (F261).
                Message.sender != OPERATOR_SENDER,
            )
        ),
        session.execute(
            select(Task.assignee)
            .distinct()
            .where(
                Task.project_id == project_id,
                Task.assignee.isnot(None),
                Task.status.in_(_ACTIVE_TASK_STATUSES),
            )
        ),
    )

    task_counts = {row[0]: row[1] for row in task_rows}
    senders = {r[0] for r in sender_rows}
    assignees = {r[0] for r in assignee_rows if r[0]}
    agents_active = sorted(senders | assignees)

    return StatusResponse(
        project_id=project_id,
        project_name=project_name,
        message_counts={"pending": pending_msgs or 0, "total": total_msgs or 0},
        task_counts=task_counts,
        question_counts={"unanswered": unanswered_qs or 0, "total": total_qs or 0},
        agents_active=agents_active,
    )


#: A landing in one of these is being worked on now: queued for the next batch, in a batch being
#: checked, or moving main. `held` is not: it waits on a prerequisite or the operator, and would
#: wait the same with the Hub stopped.
_LANDING_IN_PROGRESS = (landing_queue.QUEUED, landing_queue.CHECKING, landing_queue.LANDING)


@instance_router.get("/running")
async def get_work_running(
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
):
    """What work is running on this Hub, across every project (FR-9).

    Work is an agent turn, a check run, a landing, or a build that has not ended, even between its
    firings, because a build holds tasks in flight. An enabled job or loop that is not a build is
    not work: with no turn in progress it only misses firings while the Hub is stopped (operator,
    2026-11-04). Its turns, while one runs, are counted as turns.
    """
    del operator
    turns = (
        await session.execute(
            select(Run.agent, Project.name)
            .join(Project, Project.id == Run.project_id)
            .where(Run.status == "running")
            .order_by(Run.started_at)
        )
    ).all()
    check_runs = await session.scalar(
        select(func.count()).select_from(TaskCheckRun).where(TaskCheckRun.state == "running")
    )
    landings = await session.scalar(
        select(func.count())
        .select_from(TaskLanding)
        .where(TaskLanding.state.in_(_LANDING_IN_PROGRESS))
    )
    build_rows = (
        await session.execute(
            select(Build.id, SpecDocument.title, SpecDocument.path, Project.name)
            .join(Project, Project.id == Build.project_id)
            .outerjoin(SpecDocument, SpecDocument.id == Build.document_id)
            .where(Build.state == builds_module.RUNNING)
            .order_by(Build.created_at)
        )
    ).all()
    builds = [
        {"id": row[0], "title": row[1] or row[2] or row[0], "project": row[3]} for row in build_rows
    ]
    counts = {
        "turns": len(turns),
        "check_runs": check_runs or 0,
        "landings": landings or 0,
        "builds": len(builds),
    }
    return {
        "running": any(counts.values()),
        **counts,
        "turn_agents": [{"agent": row[0], "project": row[1]} for row in turns],
        "build_list": builds,
    }
