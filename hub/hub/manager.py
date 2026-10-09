"""The manager: the Hub's background jobs, and the record of every model they spawn.

A job is work the Hub does on its own, with a model, that no operator or agent started: today,
conversation titles. The registry below is code -- a job's key, title, description and trigger ship
with the Hub -- and a `ManagerJob` row holds only what the operator chose for it in one project:
on or off, which runner, which model (`the-hubs-background-jobs-are-configured-on-a-manager-page`
D6). A job with no row is disabled with nothing chosen.

**The manager is a Hub function, not an agent.** A firing records no `Run` row and holds no agent
name, for the reason `conversation_titles.py` states: `turn_scheduler` gates an agent's queue on a
running `Run` under its name. Each spawn is recorded instead as one `manager_job_fired` event (D4),
and only spawns are recorded -- a job that exits before spawning anything records nothing (D5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import EventLog, ManagerJob
from .runner_adapters.one_shot import WorkerUsage
from .utils import persist_event

FIRED_EVENT = "manager_job_fired"

# The outcomes a firing can record: the job's product was stored, the model produced nothing
# usable, or the spawn itself failed (a non-zero exit, a timeout, an error the CLI reported).
OUTCOMES = ("written", "empty", "failed")

TITLES = "conversation-titles"


@dataclass(frozen=True)
class JobSpec:
    key: str
    title: str
    description: str
    trigger: str


JOBS = (
    JobSpec(
        key=TITLES,
        title="Conversation titles",
        description=(
            "Names a conversation after its first exchange, replacing the truncated first "
            "message. Off: conversations keep the truncated title."
        ),
        trigger="turn_completed",
    ),
)

_BY_KEY = {spec.key: spec for spec in JOBS}


def job_spec(key: str) -> Optional[JobSpec]:
    return _BY_KEY.get(key)


async def get_job_row(db: AsyncSession, project_id: str, key: str) -> Optional[ManagerJob]:
    return await db.get(ManagerJob, (project_id, key))


def _listed(spec: JobSpec, row: Optional[ManagerJob]) -> Dict[str, Any]:
    return {
        "key": spec.key,
        "title": spec.title,
        "description": spec.description,
        "trigger": spec.trigger,
        "enabled": bool(row.enabled) if row is not None else False,
        "runner_id": row.runner_id if row is not None else None,
        "model": row.model if row is not None else None,
    }


async def get_job(db: AsyncSession, project_id: str, key: str) -> Dict[str, Any]:
    """The job as the routes list it. *key* must be registered."""
    return _listed(_BY_KEY[key], await get_job_row(db, project_id, key))


async def list_jobs(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    rows = (
        (await db.execute(select(ManagerJob).where(ManagerJob.project_id == project_id)))
        .scalars()
        .all()
    )
    by_key = {row.job: row for row in rows}
    return [_listed(spec, by_key.get(spec.key)) for spec in JOBS]


async def set_job(db: AsyncSession, project_id: str, key: str, **fields: Any) -> ManagerJob:
    """Store any of `enabled`, `runner_id` and `model` on the job's row, creating it if needed.

    Does not commit and does not validate the runner: the caller owns both, as the settings route
    and the manager route each do.
    """
    row = await get_job_row(db, project_id, key)
    if row is None:
        row = ManagerJob(project_id=project_id, job=key, enabled=False)
        db.add(row)
    for name in ("enabled", "runner_id", "model"):
        if name in fields:
            setattr(row, name, fields[name])
    return row


def usage_record(usage: Optional[WorkerUsage]) -> Optional[Dict[str, Any]]:
    """What a runner reported consuming, without the dimensions it did not report; None if none."""
    if usage is None:
        return None
    reported = {name: value for name, value in asdict(usage).items() if value is not None}
    return reported or None


async def record_firing(
    db: AsyncSession,
    project_id: str,
    *,
    job: str,
    trigger: str,
    subject: Dict[str, Any],
    runner_id: str,
    cli: str,
    model: Optional[str],
    outcome: str,
    detail: Optional[str],
    duration_ms: int,
    usage: Optional[Dict[str, Any]],
    commit: bool = True,
) -> None:
    """One manager spawn. Deliberately no `agent`, in the payload or the event's column."""
    await persist_event(
        db,
        project_id,
        FIRED_EVENT,
        {
            "job": job,
            "trigger": trigger,
            "subject": subject,
            "runner_id": runner_id,
            "cli": cli,
            "model": model,
            "outcome": outcome,
            "detail": detail,
            "duration_ms": duration_ms,
            "usage": usage,
        },
        commit=commit,
    )


async def list_firings(
    db: AsyncSession, project_id: str, *, job: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Newest first. Each firing is its event's payload plus its `id` and `at`."""
    query = select(EventLog).where(
        EventLog.project_id == project_id, EventLog.event_type == FIRED_EVENT
    )
    if job is not None:
        query = query.where(EventLog.data["job"].as_string() == job)
    rows = (
        (
            await db.execute(
                query.order_by(EventLog.timestamp.desc(), EventLog.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [{**(row.data or {}), "id": row.id, "at": row.timestamp.isoformat()} for row in rows]
