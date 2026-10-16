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

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import EventLog, ManagerJob
from .runner_adapters.one_shot import WorkerUsage
from .utils import persist_event

logger = logging.getLogger(__name__)

FIRED_EVENT = "manager_job_fired"

# The outcomes a firing can record: the job's product was stored, the model answered and nothing
# needed storing (a report whose entry stands, F641), the model produced nothing usable, or the
# spawn itself failed (a non-zero exit, a timeout, an error the CLI reported).
OUTCOMES = ("written", "answered", "empty", "failed")

TITLES = "conversation-titles"
DISTILLATION = "vault-distillation"
REPORTS = "vault-reports"
SPEC_VAULT_CHECK = "spec-vault-check"


@dataclass(frozen=True)
class JobSpec:
    key: str
    title: str
    description: str
    trigger: str
    # False: with no runner chosen the job borrows one (the titler uses the conversation's own
    # agent's). True: with none it does nothing. The Manager page words its empty choice from this.
    needs_runner: bool = True


JOBS = (
    JobSpec(
        key=TITLES,
        title="Conversation titles",
        description=(
            "Names a conversation after its first exchange, replacing the truncated first "
            "message. Off: conversations keep the truncated title."
        ),
        trigger="turn_completed",
        needs_runner=False,
    ),
    JobSpec(
        key=DISTILLATION,
        title="Vault distillation",
        description=(
            "Reads each new vault source and writes the facts it states, each citing the lines "
            "it rests on. Needs a runner. Off: sources stay in the vault without facts."
        ),
        trigger="source_uploaded",
    ),
    JobSpec(
        key=REPORTS,
        title="Vault reports",
        description=(
            "Looks into each report a working agent files on a vault entry: corrects the fact "
            "from its source, answers why it stands, or refers it to you. Needs a runner. Off: "
            "reports stay pending."
        ),
        trigger="report_filed",
    ),
    JobSpec(
        key=SPEC_VAULT_CHECK,
        title="Spec vault check",
        description=(
            "Reads each proposed spec document's requirements against the vault's facts and "
            "warns on the spec page of a requirement that contradicts one. Needs a runner. Off: "
            "only the facts a requirement cites are checked."
        ),
        trigger="document_proposed",
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
        "needs_runner": spec.needs_runner,
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


#: How much of a model's answer a firing keeps (`a-workers-answer-is-kept` D3).
ANSWER_CHARS = 8000
ANSWER_CUT = "\n[... cut: the answer was longer than 8,000 characters]"


def answer_record(result: Any) -> Optional[str]:
    """What a worker answered, as a firing keeps it (F581): its raw text, else its parsed answer as
    JSON, cut to `ANSWER_CHARS` with a marker; None when the spawn returned nothing. *result* is a
    `worker.WorkerResult` (not imported here: the worker module reads this one)."""
    text = getattr(result, "answer_text", None)
    if not text:
        parsed = getattr(result, "parsed", None)
        text = parsed.model_dump_json() if parsed is not None else None
    return cut_answer(text)


def cut_answer(text: Optional[str]) -> Optional[str]:
    """*text* as a firing keeps it: None when empty, cut to `ANSWER_CHARS` with a marker."""
    if not text:
        return None
    return text if len(text) <= ANSWER_CHARS else text[:ANSWER_CHARS] + ANSWER_CUT


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
    extra: Optional[Dict[str, Any]] = None,
    commit: bool = True,
    answer: Optional[str] = None,
) -> None:
    """One manager spawn. Deliberately no `agent`, in the payload or the event's column.

    *extra* is what a job keeps on its firing beside the standard fields (spec-vault-check: its
    conflicts); it never overrides one of them. *answer* is what the model answered
    (`answer_record`), kept so a judgement can be read afterwards (F581)."""
    await persist_event(
        db,
        project_id,
        FIRED_EVENT,
        {
            **(extra or {}),
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
            "answer": answer,
        },
        commit=commit,
    )


async def record_no_runner(
    project_id: str, *, job: str, trigger: str, subject: Dict[str, Any]
) -> None:
    """A firing for a job that is on but has no runner: it did nothing, said where the operator
    looks (F626). Its background entries used to return silently, leaving the activity empty.
    Never raises: it runs in a background task."""
    from .db.engine import async_session_factory

    spec = job_spec(job)
    title = spec.title if spec is not None else job
    try:
        async with async_session_factory() as db:
            await record_firing(
                db,
                project_id,
                job=job,
                trigger=trigger,
                subject=subject,
                runner_id="",
                cli="",
                model=None,
                outcome="failed",
                detail=(
                    f"Did nothing: the {title} job is on but has no runner. Choose one on the "
                    "Manager page."
                ),
                duration_ms=0,
                usage=None,
            )
    except Exception:  # noqa: BLE001 -- a background task must not raise
        logger.warning("could not record %s's missing runner", job, exc_info=True)


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
