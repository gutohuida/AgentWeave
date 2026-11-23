"""The manager: the Hub's background jobs, and the record of every model they spawn.

A job is work the Hub does on its own, with a model, that no operator or agent started: today,
conversation titles. The registry below is code -- a job's key, title, description and trigger ship
with the Hub -- and a `ManagerJob` row holds only what the operator chose for it in one project:
on or off, which runner, which model (`the-hubs-background-jobs-are-configured-on-a-manager-page`
D6). A job with no row is disabled with nothing chosen.

**The manager is a Hub function, not an agent** -- with one exception, the mender, whose entry
here holds only the runner and model of the `mender` agent `stalls.py` makes and briefs. A firing
records no `Run` row and holds no agent name, for the reason `conversation_titles.py` states:
`turn_scheduler` gates an agent's queue on a running `Run` under its name. Each spawn is recorded
instead as one `manager_job_fired` event (D4), and only spawns are recorded -- a job that exits
before spawning anything records nothing (D5).

**A run is announced when it starts and ends exactly once** (`background-manager-work-you-can-see`
D1-D3). A job's background entry point does its work inside `manager_run`, which mints the run's
`mrun-` id, holds it in this process's registry of runs in progress (read by
`GET /manager/runs/running`; a restart empties it along with the work), publishes
`manager_run_started`, and on every exit -- a return, a refusal, an exception, no runner, nothing to
compare -- makes sure the run has at least one `manager_job_fired` event carrying its `run_id`,
`initiator` and `started_at`, then publishes `manager_run_ended` once. A firing recorded inside the
run joins it on its own (`record_firing` reads the run from a context variable), so the jobs'
recording is unchanged; a job that spawns more than once (a distillation's pieces, a long build's
parts) records several firings under one run. "Seen" is a `manager_run_seen` event per run (D3).
A job added later joins by entering `manager_run`; nothing else here names the jobs.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import EventLog, ManagerJob, Runner
from .model_catalog import default_model, get_provider
from .runner_adapters.one_shot import WorkerUsage
from .runner_provider import has_provider
from .sse import defer_broadcast, sse_manager
from .utils import persist_event

logger = logging.getLogger(__name__)

FIRED_EVENT = "manager_job_fired"
#: The live signals on the project stream, and the event that marks a run's failure seen (D3).
RUN_STARTED_EVENT = "manager_run_started"
RUN_ENDED_EVENT = "manager_run_ended"
SEEN_EVENT = "manager_run_seen"

# The outcomes a firing can record: the job's product was stored, the model answered and nothing
# needed storing (a report whose entry stands, F641), the model produced nothing usable, or the
# spawn itself failed (a non-zero exit, a timeout, an error the CLI reported).
OUTCOMES = ("written", "answered", "empty", "failed")

TITLES = "conversation-titles"
DISTILLATION = "vault-distillation"
REPORTS = "vault-reports"
SPEC_VAULT_CHECK = "spec-vault-check"
CHAPTERS = "chapters"
MENDER = "mender"
BUILD_RETROSPECTIVE = "build-retrospective"
PRE_MORTEM = "pre-mortem"
OVERVIEW_NOTE = "overview-note"


@dataclass(frozen=True)
class FiringChoice:
    """A job with a button beside its triggers, in the words the Manager page offers the choice."""

    button: str
    where: str
    automatic: str


@dataclass(frozen=True)
class JobSpec:
    key: str
    title: str
    description: str
    trigger: str
    # False: with no runner chosen the job borrows one (the titler uses the conversation's own
    # agent's). True: with none it does nothing. The Manager page words its empty choice from this.
    needs_runner: bool = True
    # Set: the job has a button, and `mode` chooses automatic firing or the button only.
    firing_choice: Optional[FiringChoice] = None


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
            "Reads a spec document's requirements against the vault's facts when the operator "
            "checks it, and "
            "warns on the spec page of a requirement that contradicts one. Needs a runner. Off: "
            "only the facts a requirement cites are checked."
        ),
        trigger="document_proposed",
    ),
    JobSpec(
        key=CHAPTERS,
        title="Thread chapters",
        description=(
            "Writes the Thread's chapters: titled, dated groups of the project's history, "
            "reaching back through its git history. Fires after a document is approved or "
            "archived and after a document's last task is approved (automatic), and when you "
            "press Weave the thread. It adds chapters on its own and rewrites existing ones "
            "only when you ask. Needs a runner. Off: the Thread shows its structural surface."
        ),
        trigger="document_approved",
        firing_choice=FiringChoice(
            button="Weave the thread",
            where="the Thread page",
            automatic="after a document is approved or archived and after its last task is approved",
        ),
    ),
    JobSpec(
        key=BUILD_RETROSPECTIVE,
        title="Build retrospective",
        description=(
            "Reviews a spec document's whole build: where the time went, what was sent back and "
            "why, what the spec missed, staffing, cost, friction, what worked and what to improve, "
            "every claim citing the records it rests on. Fires when a document's last task is "
            "approved (automatic), and when you press Review this build on its page. Its lessons "
            "are added to the vault as a tracked source. Needs a runner. Off: nothing reviews a "
            "build unless you ask."
        ),
        trigger="last_task_approved",
        firing_choice=FiringChoice(
            button="Review this build",
            where="a spec document's page",
            automatic="after a document's last task is approved",
        ),
    ),
    JobSpec(
        key=PRE_MORTEM,
        title="Pre-mortem",
        description=(
            "Reads a change document's drafted requirements and acceptance criteria and the code "
            "they touch, assumes the change shipped and failed, and writes down how. Fires when a "
            "document's acceptance criteria are written (automatic), and when you press Run a "
            "pre-mortem on its page. Its author reads the findings in its next turn on the "
            "document, fixes what it can and asks you about the rest. Needs a runner. Off: no "
            "draft is pre-mortemed."
        ),
        trigger="criteria_written",
        firing_choice=FiringChoice(
            button="Run a pre-mortem",
            where="a spec document's page",
            automatic="when a document's acceptance criteria are written",
        ),
    ),
    JobSpec(
        key=OVERVIEW_NOTE,
        title="Overview note",
        description=(
            "Writes the Briefing's short note on what changed since your last visit and anything "
            "that looks wrong, such as a build that stopped moving or spend well above its usual "
            "day. Fires when you open the Overview more than 30 minutes after your last visit and "
            "something changed since the last note (automatic), and when you press Refresh note. "
            "Never on a timer. Needs a runner. Off: the Briefing shows no new note."
        ),
        trigger="overview_visit",
        firing_choice=FiringChoice(
            button="Refresh note",
            where="the Overview's Briefing",
            automatic="when a new visit to the Overview starts and something changed",
        ),
    ),
    # The one entry that is an agent, not a one-shot spawn (`stalls.py`): its runner and model
    # become the `mender` agent's, and a stall briefs it through the ordinary queue.
    JobSpec(
        key=MENDER,
        title="Mender",
        description=(
            "When the project's work stalls -- a merge skipped or failed, a loop with nothing it "
            "can start, a refused turn, a dead run, or no progress for 30 minutes -- the mender "
            "reads the cause and unblocks the agents on its own: it resolves conflicts and lands "
            "the work without review. Before anything hardcore, such as touching changes it did "
            "not make, it leaves you a note under Needs you and does not do it; your answer wakes "
            "it later. Runs on the runner's CLI default model unless you choose one. Needs a "
            "runner. Off: stalls are only recorded."
        ),
        trigger="stall_recorded",
    ),
)

_BY_KEY = {spec.key: spec for spec in JOBS}
HAS_BUTTON = tuple(spec.key for spec in JOBS if spec.firing_choice is not None)


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
        "automatic": bool(row.automatic) if row is not None else True,
        "mode": "automatic" if row is None or row.automatic else "button",
        "firing_choice": asdict(spec.firing_choice) if spec.firing_choice is not None else None,
    }


async def _mender_default(
    db: AsyncSession, project_id: str, row: Optional[ManagerJob]
) -> Optional[Dict[str, str]]:
    """The model the mender runs on when the entry names none -- the catalog's default for its
    runner's CLI (`stalls.ensure_mender`) -- as `{id, label}`, or `None` with no runner or no default.
    Listed so the Manager page can say what the mender costs before it runs."""
    runner = await db.get(Runner, row.runner_id) if row is not None and row.runner_id else None
    if runner is None or runner.project_id != project_id:
        return None
    if has_provider(runner.provider_config):
        return None  # a provider runner keeps its own model (`stalls.ensure_mender`)
    model_id = default_model(runner.cli)
    if model_id is None:
        return None
    provider = get_provider(runner.cli)
    declared = provider.model(model_id) if provider is not None else None
    return {"id": model_id, "label": declared.label if declared is not None else model_id}


async def get_job(db: AsyncSession, project_id: str, key: str) -> Dict[str, Any]:
    """The job as the routes list it. *key* must be registered."""
    row = await get_job_row(db, project_id, key)
    job = _listed(_BY_KEY[key], row)
    if key == MENDER:
        job["default_model"] = await _mender_default(db, project_id, row)
    if key in HAS_BUTTON:
        job["usage_total"] = await usage_total(db, project_id, key)
    return job


#: The usage dimensions a job's total sums; one a runner never reported stays absent from it.
TOTALLED = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "cost_usd_micros",
)


async def usage_total(db: AsyncSession, project_id: str, key: str) -> Dict[str, Any]:
    """What every firing of job *key* in the project recorded, summed per dimension, with how
    many firings there were. Reads the same events `list_firings` lists, so the two agree."""
    rows = (
        (
            await db.execute(
                select(EventLog.data).where(
                    EventLog.project_id == project_id, EventLog.event_type == FIRED_EVENT
                )
            )
        )
        .scalars()
        .all()
    )
    total: Dict[str, Any] = {"firings": 0}
    for data in rows:
        if (data or {}).get("job") != key:
            continue
        total["firings"] += 1
        for name in TOTALLED:
            value = ((data or {}).get("usage") or {}).get(name)
            if isinstance(value, (int, float)):
                total[name] = total.get(name, 0) + int(value)
    return total


async def list_jobs(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    rows = (
        (await db.execute(select(ManagerJob).where(ManagerJob.project_id == project_id)))
        .scalars()
        .all()
    )
    by_key = {row.job: row for row in rows}
    listed = [_listed(spec, by_key.get(spec.key)) for spec in JOBS]
    for job in listed:
        if job["key"] in HAS_BUTTON:
            job["usage_total"] = await usage_total(db, project_id, job["key"])
        if job["key"] == MENDER:
            job["default_model"] = await _mender_default(db, project_id, by_key.get(MENDER))
    return listed


async def set_job(db: AsyncSession, project_id: str, key: str, **fields: Any) -> ManagerJob:
    """Store any of `enabled`, `automatic`, `runner_id` and `model` on the job's row, creating it if needed.

    Does not commit and does not validate the runner: the caller owns both, as the settings route
    and the manager route each do.
    """
    row = await get_job_row(db, project_id, key)
    if row is None:
        row = ManagerJob(project_id=project_id, job=key, enabled=False, automatic=True)
        db.add(row)
    for name in ("enabled", "automatic", "runner_id", "model"):
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
    (`answer_record`), kept so a judgement can be read afterwards (F581).

    Inside `manager_run` for the same project and job, the firing carries that run's `run_id`,
    `initiator` and `started_at`, and is part of the run's end (D2)."""
    run = current_run()
    if run is not None and (run.project_id != project_id or run.job != job):
        run = None
    await persist_event(
        db,
        project_id,
        FIRED_EVENT,
        {
            **(extra or {}),
            **(run.identity() if run is not None else {}),
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
    if run is not None:
        run.firings.append({"outcome": outcome, "detail": detail, "usage": usage})


async def record_no_runner(
    project_id: str, *, job: str, trigger: str, subject: Dict[str, Any], then: str = ""
) -> None:
    """A firing for a job that is on but has no runner: it did nothing, said where the operator
    looks (F626). Its background entries used to return silently, leaving the activity empty.
    `then` says what becomes of the work item meanwhile (F801). Never raises: it runs in a background task.
    """
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
                    "Manager page." + (f" {then}" if then else "")
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


# ---------------------------------------------------------------------------
# Runs: started, ended, running now and seen (`background-manager-work-you-can-see` D1-D3)
# ---------------------------------------------------------------------------

#: `worker.Initiator`'s vocabulary: a button or a request, or the Hub on its own.
OPERATOR = "operator"
AUTONOMOUS = "autonomous"

#: Which outcome stands for a run whose firings differ: any failure fails the run, else the most
#: productive one (a distillation's last firing is its contradiction check, often empty).
_OUTCOME_RANK = {"written": 0, "answered": 1, "empty": 2}

#: The subject keys that name the item a run works on: a run on the same item is that item's run
#: whatever else its subject carries (a content version, a build's approving task).
_ITEM_KEYS = ("document", "source", "report", "conversation_id", "stall")
_VOLATILE_KEYS = ("content_version",)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return f"mrun-{uuid.uuid4().hex[:12]}"


@dataclass
class ManagerRun:
    """One run in progress. *runner_id*, *cli* and *model* are what a firing the wrapper records
    itself names (`uses`); *outcome* and *detail* are how it ends when the job records no firing
    of its own (`ends`)."""

    project_id: str
    job: str
    trigger: str
    subject: Dict[str, Any]
    initiator: str
    run_id: str = field(default_factory=new_run_id)
    started_at: str = field(default_factory=_now_iso)
    runner_id: str = ""
    cli: str = ""
    model: Optional[str] = None
    firings: List[Dict[str, Any]] = field(default_factory=list)
    outcome: Optional[str] = None
    detail: Optional[str] = None
    closed: bool = False
    started_monotonic: float = field(default_factory=time.monotonic)

    def identity(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "initiator": self.initiator, "started_at": self.started_at}

    def listed(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job": self.job,
            "subject": self.subject,
            "trigger": self.trigger,
            "initiator": self.initiator,
            "started_at": self.started_at,
            "conversation_id": None,
        }

    def ends(self, outcome: str, detail: str) -> None:
        """How the run ends if it records no firing: nothing to compare (`empty`), a refusal
        (`failed`). A firing the job records takes precedence."""
        self.outcome, self.detail = outcome, detail

    def uses(self, *, runner_id: str, cli: str, model: Optional[str]) -> None:
        self.runner_id, self.cli, self.model = runner_id, cli, model


_CURRENT_RUN: contextvars.ContextVar[Optional[ManagerRun]] = contextvars.ContextVar(
    "manager_run", default=None
)
#: Runs in progress, by project then run id. This process's own, so a restart forgets them along
#: with the work they were doing and shows no ghost (D1). Insertion order is start order.
_running: Dict[str, Dict[str, ManagerRun]] = {}


def current_run() -> Optional[ManagerRun]:
    """The run this code is inside, if it is still open. A task started from inside a run copies
    the context; once that run has ended, its firings are no longer the run's."""
    run = _CURRENT_RUN.get()
    return run if run is not None and not run.closed else None


def running(project_id: str) -> List[Dict[str, Any]]:
    """The project's manager-job runs in progress, oldest first."""
    return [run.listed() for run in (_running.get(project_id) or {}).values()]


async def job_enabled(project_id: str, key: str) -> bool:
    """Whether job *key* is on in the project. A run starts only for a job that is on, so a job
    left off announces nothing on each of its triggers."""
    from .db.engine import async_session_factory

    async with async_session_factory() as db:
        row = await get_job_row(db, project_id, key)
    return row is not None and bool(row.enabled)


def summed_usage(firings: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    total: Dict[str, Any] = {}
    for firing in firings:
        for name, value in (firing.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                total[name] = total.get(name, 0) + value
    return total or None


def run_outcome(firings: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """A run's outcome and detail from its firings, oldest first: the first failure's, else the
    most productive firing's (the latest of those)."""
    for firing in firings:
        if firing.get("outcome") == "failed":
            return "failed", firing.get("detail")
    best = min(reversed(firings), key=lambda firing: _OUTCOME_RANK.get(firing.get("outcome"), 3))
    return str(best.get("outcome")), best.get("detail")


def publish(project_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """Push a run signal to the project's open views. Never raises into the work it describes."""
    try:
        sse_manager.publish(project_id, event_type, data)
    except Exception:  # noqa: BLE001
        logger.warning("could not publish %s", event_type, exc_info=True)


@contextlib.asynccontextmanager
async def manager_run(
    project_id: str,
    *,
    job: str,
    trigger: str,
    subject: Dict[str, Any],
    initiator: str,
) -> AsyncIterator[ManagerRun]:
    """Do one run of *job* inside this: announced as started on entry, ended exactly once on exit.

    A firing recorded inside it is the run's end. When the body records none, the run records one
    itself: the outcome the body set with `ends`, else a failure naming the exception, else a
    failure saying it ended with no outcome -- so no run is left in progress or unrecorded (D2). An
    exception is recorded, and raised again for the entry point's own handling."""
    run = ManagerRun(
        project_id=project_id, job=job, trigger=trigger, subject=dict(subject), initiator=initiator
    )
    _running.setdefault(project_id, {})[run.run_id] = run
    token = _CURRENT_RUN.set(run)
    started = run.listed()
    started.pop("conversation_id")
    publish(project_id, RUN_STARTED_EVENT, started)
    failure: Optional[BaseException] = None
    try:
        yield run
    except BaseException as exc:
        failure = exc
        raise
    finally:
        _CURRENT_RUN.reset(token)
        await _end(run, failure)


async def _end(run: ManagerRun, failure: Optional[BaseException]) -> None:
    from .db.engine import async_session_factory

    duration_ms = int((time.monotonic() - run.started_monotonic) * 1000)
    own: Optional[Tuple[str, str]] = None
    if failure is not None and not any(f.get("outcome") == "failed" for f in run.firings):
        own = ("failed", f"The run failed: {str(failure) or type(failure).__name__}")
    elif not run.firings:
        own = (
            (run.outcome, run.detail or "")
            if run.outcome
            else ("failed", "The run ended without recording an outcome.")
        )
    if own is not None:
        try:
            async with async_session_factory() as db:
                await record_firing(
                    db,
                    run.project_id,
                    job=run.job,
                    trigger=run.trigger,
                    subject=run.subject,
                    runner_id=run.runner_id,
                    cli=run.cli,
                    model=run.model,
                    outcome=own[0],
                    detail=own[1],
                    duration_ms=0,
                    usage=None,
                    extra=run.identity(),
                )
        except Exception:  # noqa: BLE001 -- the end is still announced below
            logger.warning("could not record the end of run %s", run.run_id, exc_info=True)
        run.firings.append({"outcome": own[0], "detail": own[1], "usage": None})
    run.closed = True
    project_runs = _running.get(run.project_id) or {}
    project_runs.pop(run.run_id, None)
    if not project_runs:
        _running.pop(run.project_id, None)
    outcome, detail = run_outcome(run.firings)
    publish(
        run.project_id,
        RUN_ENDED_EVENT,
        {
            "run_id": run.run_id,
            "job": run.job,
            "subject": run.subject,
            "trigger": run.trigger,
            "initiator": run.initiator,
            "started_at": run.started_at,
            "ended_at": _now_iso(),
            "duration_ms": duration_ms,
            "outcome": outcome,
            "detail": detail,
            "usage": summed_usage(run.firings),
        },
    )


def item_of(job: str, subject: Optional[Dict[str, Any]]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    """The item a run works on, as a key: its job and the subject keys that name the item."""
    subject = subject or {}
    named = {k: subject[k] for k in _ITEM_KEYS if k in subject}
    if not named:
        named = {k: v for k, v in subject.items() if k not in _VOLATILE_KEYS}
    return job, tuple(sorted((k, str(v)) for k, v in named.items()))


def _iso(moment: datetime) -> str:
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).isoformat()


async def ended_runs(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Every ended run with an id, oldest first, as `{run_id, job, subject, trigger, initiator,
    started_at, ended_at, outcome, detail}` drawn from its firings. A firing from before runs had
    ids is not a run here."""
    rows = (
        (
            await db.execute(
                select(EventLog)
                .where(
                    EventLog.project_id == project_id,
                    EventLog.event_type == FIRED_EVENT,
                    EventLog.data["run_id"].as_string().is_not(None),
                )
                .order_by(EventLog.timestamp, EventLog.id)
            )
        )
        .scalars()
        .all()
    )
    runs: Dict[str, Dict[str, Any]] = {}
    firings: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        data = row.data or {}
        run_id = data.get("run_id")
        if not isinstance(run_id, str):
            continue
        run = runs.setdefault(
            run_id,
            {
                "run_id": run_id,
                "job": data.get("job"),
                "subject": data.get("subject") or {},
                "trigger": data.get("trigger"),
                "initiator": data.get("initiator"),
                "started_at": data.get("started_at"),
            },
        )
        run["ended_at"] = _iso(row.timestamp)
        firings.setdefault(run_id, []).append(data)
    for run_id, run in runs.items():
        run["outcome"], run["detail"] = run_outcome(firings[run_id])
    return sorted(runs.values(), key=lambda run: (str(run["started_at"] or ""), run["ended_at"]))


async def _seen(db: AsyncSession, project_id: str) -> set:
    return set(
        (
            await db.execute(
                select(EventLog.data["run_id"].as_string()).where(
                    EventLog.project_id == project_id, EventLog.event_type == SEEN_EVENT
                )
            )
        )
        .scalars()
        .all()
    )


async def unseen_failures(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Each item's newest ended run, when it failed, has no `manager_run_seen`, and no run on the
    same item has started since -- one in progress included (D3). Oldest first."""
    seen = await _seen(db, project_id)
    newest: Dict[Any, Dict[str, Any]] = {}
    for run in await ended_runs(db, project_id):
        newest[item_of(run["job"], run["subject"])] = run
    busy = {item_of(run.job, run.subject) for run in (_running.get(project_id) or {}).values()}
    return [
        {
            "run_id": run["run_id"],
            "job": run["job"],
            "subject": run["subject"],
            "ended_at": run["ended_at"],
            "detail": run["detail"],
        }
        for item, run in newest.items()
        if run["outcome"] == "failed" and run["run_id"] not in seen and item not in busy
    ]


async def mark_seen(db: AsyncSession, project_id: str, run_ids: Iterable[str]) -> List[str]:
    """Record each named run as seen, once. An id naming no ended run of the project, or one
    already seen, is ignored. Answers the ids newly marked, and tells the open views."""
    wanted = {run_id for run_id in run_ids if isinstance(run_id, str)}
    if not wanted:
        return []
    known = {run["run_id"] for run in await ended_runs(db, project_id)}
    marked = sorted((wanted & known) - await _seen(db, project_id))
    for run_id in marked:
        await persist_event(db, project_id, SEEN_EVENT, {"run_id": run_id}, commit=False)
    if marked:
        defer_broadcast(db, project_id, SEEN_EVENT, {"run_ids": marked})
        await db.commit()
    return marked


# ---------------------------------------------------------------------------
# The run log (`background-manager-work-you-can-see` D6)
# ---------------------------------------------------------------------------

#: A firing from before runs had ids is a run of its own in the log, under this id prefix.
LEGACY_RUN_PREFIX = "firing-"


def _moment(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _no_cost_reason(usage: Optional[Dict[str, Any]], reached_model: bool) -> Optional[str]:
    """Why a run shows no cost: it never reached a model, or the runner reported none."""
    if usage is not None and usage.get("cost_usd_micros") is not None:
        return None
    return "the runner reported no cost" if reached_model else "never reached a model"


def _log_run(firings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One run of the log from its firing events, oldest first, each `{id, at, data}`."""
    first, last = firings[0], firings[-1]
    data = first["data"]
    run_id = data.get("run_id") or f"{LEGACY_RUN_PREFIX}{first['id']}"
    ended = last["at"]
    duration_ms = sum(int(f["data"].get("duration_ms") or 0) for f in firings)
    started = _moment(data.get("started_at"))
    if started is not None:
        duration_ms = max(0, int((ended - started).total_seconds() * 1000))
    else:
        started = ended - timedelta(milliseconds=duration_ms)
    outcome, detail = run_outcome([f["data"] for f in firings])
    usage = summed_usage(f["data"] for f in firings)
    reached = usage is not None or any(f["data"].get("runner_id") for f in firings)
    return {
        "run_id": run_id,
        "job": data.get("job"),
        "subject": data.get("subject") or {},
        "trigger": data.get("trigger"),
        "initiator": data.get("initiator"),
        "started_at": _iso(started),
        "ended_at": _iso(ended),
        "duration_ms": duration_ms,
        "outcome": outcome,
        "detail": detail,
        "usage": usage,
        "no_cost_reason": _no_cost_reason(usage, reached),
        "conversation_id": None,
    }


_LIGHT_FIELDS = (
    "run_id",
    "job",
    "trigger",
    "initiator",
    "started_at",
    "outcome",
    "detail",
    "runner_id",
    "duration_ms",
)


async def _log_runs(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Every run of the project's log, newest first: its jobs' runs from their `manager_job_fired`
    events, the mender's from its `runs` rows joined to their `turn_usage`. The model's answer is
    left out of the read (`get_run` brings it)."""
    columns = [EventLog.data[name].as_string() for name in _LIGHT_FIELDS]
    rows = (
        await db.execute(
            select(
                EventLog.id,
                EventLog.timestamp,
                EventLog.data["subject"].as_json(),
                EventLog.data["usage"].as_json(),
                *columns,
            )
            .where(EventLog.project_id == project_id, EventLog.event_type == FIRED_EVENT)
            .order_by(EventLog.timestamp, EventLog.id)
        )
    ).all()
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        data = dict(zip(_LIGHT_FIELDS, row[4:], strict=True))
        data["subject"], data["usage"] = row[2], row[3]
        data["duration_ms"] = int(data["duration_ms"] or 0)
        at = row[1] if row[1].tzinfo else row[1].replace(tzinfo=timezone.utc)
        key = data["run_id"] or f"{LEGACY_RUN_PREFIX}{row[0]}"
        groups.setdefault(key, []).append({"id": row[0], "at": at, "data": data})
    runs = [_log_run(firings) for firings in groups.values()]
    from . import stalls

    runs.extend(await stalls.ended_mender_runs(db, project_id))
    runs.sort(key=lambda run: (run["started_at"] or "", run["run_id"]), reverse=True)
    return runs


def _totals(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    totals: Dict[str, Dict[str, Any]] = {}
    for run in runs:
        total = totals.setdefault(run["job"], {"runs": 0, "failed": 0, "cost_usd_micros": None})
        total["runs"] += 1
        total["failed"] += run["outcome"] == "failed"
        cost = (run["usage"] or {}).get("cost_usd_micros")
        if cost is not None:
            total["cost_usd_micros"] = (total["cost_usd_micros"] or 0) + int(cost)
    return totals


async def list_runs(
    db: AsyncSession,
    project_id: str,
    *,
    job: Optional[str] = None,
    limit: int = 50,
    before: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The run log: *limit* runs newest first, narrowed to *job*, and those after run *before* in
    that order; with every job's totals whatever *job* narrows to, and whether more follow. None
    when *before* names no run."""
    everything = await _log_runs(db, project_id)
    shown = [run for run in everything if job is None or run["job"] == job]
    if before is not None:
        at = next((i for i, run in enumerate(shown) if run["run_id"] == before), None)
        if at is None:
            return None
        shown = shown[at + 1 :]
    return {
        "runs": shown[:limit],
        "totals": _totals(everything),
        "has_more": len(shown) > limit,
    }


async def get_run(db: AsyncSession, project_id: str, run_id: str) -> Optional[Dict[str, Any]]:
    """One run of the log with the model's `answer` (the last firing's that kept one); None for an
    unknown id."""
    run = next((r for r in await _log_runs(db, project_id) if r["run_id"] == run_id), None)
    if run is None:
        return None
    query = select(EventLog).where(
        EventLog.project_id == project_id, EventLog.event_type == FIRED_EVENT
    )
    if run_id.startswith(LEGACY_RUN_PREFIX):
        query = query.where(EventLog.id == run_id[len(LEGACY_RUN_PREFIX) :])
    else:
        query = query.where(EventLog.data["run_id"].as_string() == run_id)
    answer = None
    for row in (await db.execute(query.order_by(EventLog.timestamp, EventLog.id))).scalars():
        answer = (row.data or {}).get("answer") or answer
    return {**run, "answer": answer}
