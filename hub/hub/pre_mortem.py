"""The manager's pre-mortem: a fresh reader assumes a drafted change shipped and failed, and says how.

`the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions` (FR-11, D7). Modelled on
`build_retrospective.py`: one firing reads the document's drafted requirements and criteria, spawns
the manager's model once (with the Read tool in the project's directory where its CLI can read, so
it reads the code the change touches), and keeps what it answered as `findings` on one
`manager_job_fired` event -- **no table and no migration**: a job with no row is off, and
`list_for_document` reads a document's firings, newest first.

It fires when the operator presses Run a pre-mortem (`request`, only while the job is on with a
runner) and, while the job is on with automatic firing, when a change document leaves the step that
writes its acceptance criteria (`fire_after_commit`, staged by `spec_journey.set_step` and run after
the move commits). One runs per document at a time. The findings reach the document's author in its
next turn on the document (`briefing_lines`), which fixes what it can and asks the operator the rest.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import event, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import manager, project_workspace, spec_documents
from .db.engine import async_session_factory
from .db.models import EventLog, Runner, SpecDocument, SpecRequirement
from .runner_adapters import get_adapter
from .worker import WorkerResult, run_worker

logger = logging.getLogger(__name__)

JOB = manager.PRE_MORTEM
REQUESTED = "requested"
CRITERIA_WRITTEN = "criteria_written"
PROMPT_VERSION = "pre-mortem-1"
TIMEOUT_SECONDS = 15 * 60
HEADING = "### Pre-mortem findings"

#: The steps that write a change document's acceptance criteria: leaving one fires the job.
#: Named here, not imported, because `spec_journey` imports this module lazily inside `set_step`.
CRITERIA_STEPS = ("acceptance", "requirements-and-acceptance")


class Finding(BaseModel):
    story: str = Field(description="How the shipped change failed, told as what happened.")
    requirement: Optional[str] = Field(
        default=None, description="The FR-n identifier of the requirement it breaks, or null."
    )
    cites: List[str] = Field(
        default_factory=list,
        description="What the story rests on: file:line, a criterion key, a requirement.",
    )


class PreMortemAnswer(BaseModel):
    findings: List[Finding] = Field(default_factory=list)


class CannotRunError(Exception):
    """Why no pre-mortem starts now, with the status the run route answers."""

    def __init__(self, reason: str, *, status: int = 409, no_runner: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.no_runner = no_runner


_READING = (
    "You are running a pre-mortem on a drafted change specification. Assume the change was built "
    "exactly as the requirements and acceptance criteria below say, shipped, and failed: it did "
    "not do what the operator needed, broke existing behaviour, or passed its checks while the "
    "behaviour could not fire in production. Write down how it failed.\n\n"
    "Read the code the change touches before you write: you may open files in the project with "
    "the Read tool, and the document's design names where to start. Each story is one concrete "
    "way it failed -- a requirement that misses a case, a criterion that passes for the wrong "
    "reason, a conflict with behaviour that exists today, a seam between two features nobody "
    "checks. Name the requirement it breaks by its FR identifier where there is one, and cite "
    "what the story rests on (file:line, a criterion key). Prefer the three to six most likely "
    "failures to a long list; leave findings empty if you honestly find none.\n\n"
    'Reply with one JSON object only: {"findings": [{"story": str, "requirement": "FR-n" or '
    'null, "cites": [str]}]}.\n\n'
    "The document:\n\n"
)


@dataclass(frozen=True)
class Plan:
    project_id: str
    document_id: str
    document_path: str
    runner_id: str
    cli: str
    model: Optional[str]


def subject_of(plan: Plan) -> Dict[str, Any]:
    return {"document": plan.document_id, "path": plan.document_path}


async def find_document(db: AsyncSession, project_id: str, path: str) -> Optional[SpecDocument]:
    return (
        (
            await db.execute(
                select(SpecDocument).where(
                    SpecDocument.project_id == project_id,
                    or_(SpecDocument.path == path, SpecDocument.id == path),
                )
            )
        )
        .scalars()
        .first()
    )


async def gate(db: AsyncSession, project_id: str, trigger: str) -> Tuple[Any, Runner]:
    """The job's row and runner if a firing for *trigger* may go ahead, else `CannotRunError`.

    Both the button and the automatic firing need the job on with a runner (the contract's 409
    when it is off); the automatic one also needs its mode to be automatic."""
    job = await manager.get_job_row(db, project_id, JOB)
    if job is None or not job.enabled:
        raise CannotRunError(
            "The Pre-mortem job is off. Switch it on under Project settings → Manager."
        )
    if trigger != REQUESTED and not job.automatic:
        raise CannotRunError("The Pre-mortem job fires only on the button.")
    runner = await db.get(Runner, job.runner_id) if job.runner_id else None
    if runner is None or runner.project_id != project_id:
        raise CannotRunError(
            "The Pre-mortem job has no runner. Choose one under Project settings → Manager.",
            no_runner=True,
        )
    return job, runner


def _plan(document: SpecDocument, job: Any, runner: Runner) -> Plan:
    return Plan(
        project_id=document.project_id,
        document_id=document.id,
        document_path=document.path,
        runner_id=runner.id,
        cli=runner.cli,
        model=job.model or runner.model,
    )


async def _identifiers(db: AsyncSession, project_id: str, document_id: str) -> Dict[str, str]:
    """The document's active requirements, key to minted identifier."""
    rows = (
        await db.execute(
            select(SpecRequirement.key, SpecRequirement.identifier).where(
                SpecRequirement.project_id == project_id,
                SpecRequirement.document_id == document_id,
                SpecRequirement.state == "active",
            )
        )
    ).all()
    return dict(rows)


def document_input(payload: Dict[str, Any], identifiers: Dict[str, str]) -> Dict[str, Any]:
    """What the reader is given: the drafted document, each requirement under its identifier and
    each criterion under the requirement it checks."""
    criteria: Dict[str, List[Dict[str, Any]]] = {}
    for criterion in payload.get("acceptance_criteria") or []:
        criteria.setdefault(criterion.get("requirement") or "", []).append(
            {
                name: criterion.get(name)
                for name in ("key", "given", "when", "then", "how_to_check", "checked_by")
                if criterion.get(name)
            }
        )
    return {
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "problem": payload.get("problem"),
        "scope": payload.get("scope"),
        "design": payload.get("design"),
        "requirements": [
            {
                "identifier": identifiers.get(requirement.get("key", "")),
                "key": requirement.get("key"),
                "modal": requirement.get("modal"),
                "statement": requirement.get("statement"),
                "criteria": criteria.get(requirement.get("key", ""), []),
            }
            for requirement in payload.get("requirements") or []
        ],
    }


def kept_findings(answer: PreMortemAnswer, identifiers: Dict[str, str]) -> List[Dict[str, Any]]:
    """The findings with a story, each naming a requirement only by one of the document's
    identifiers (a key is turned into its identifier; anything else is dropped to null)."""
    known = set(identifiers.values())
    kept = []
    for finding in answer.findings:
        story = finding.story.strip()
        if not story:
            continue
        requirement = finding.requirement
        if requirement not in known:
            requirement = identifiers.get(requirement or "")
        kept.append(
            {
                "story": story,
                "requirement": requirement,
                "cites": [cite.strip() for cite in finding.cites if cite and cite.strip()],
            }
        )
    return kept


async def _read(plan: Plan) -> Tuple[Optional[Dict[str, Any]], Dict[str, str], Optional[str]]:
    """The document's payload, its identifiers and the project's root, read in one session."""
    async with async_session_factory() as db:
        identifiers = await _identifiers(db, plan.project_id, plan.document_id)
        workspace = await project_workspace.resolve_project_workspace(db, plan.project_id)
    payload = spec_documents.read_payload(workspace, plan.document_path)
    return payload, identifiers, str(workspace.root)


async def _ask(plan: Plan, trigger: str, prompt: str, root: Optional[str]) -> WorkerResult:
    adapter = get_adapter(plan.cli)
    reading = bool(root) and adapter is not None and adapter.one_shot_reads_files
    return await run_worker(
        project_id=plan.project_id,
        kind=JOB,
        prompt=prompt,
        prompt_version=PROMPT_VERSION,
        output_model=PreMortemAnswer,
        cli=plan.cli,
        model=plan.model,
        runner_id=plan.runner_id,
        timeout_seconds=TIMEOUT_SECONDS,
        cwd=root if reading else None,
        reading=reading,
        initiator="operator" if trigger == REQUESTED else "autonomous",
    )


async def run(plan: Plan, *, trigger: str) -> str:
    """One firing: read the document, spawn the model, keep its findings and record the firing.
    Answers the outcome."""
    payload, identifiers, root = await _read(plan)
    result: Optional[WorkerResult] = None
    findings: List[Dict[str, Any]] = []
    if not payload:
        outcome, detail = "failed", "The document's file has no readable payload."
    else:
        prompt = _READING + json.dumps(document_input(payload, identifiers), indent=2)
        result = await _ask(plan, trigger, prompt, root)
        if not result.ok or not isinstance(result.parsed, PreMortemAnswer):
            outcome, detail = "failed", str(result.error or result.outcome)
        else:
            findings = kept_findings(result.parsed, identifiers)
            if findings:
                outcome = "written"
                detail = f"Found {len(findings)} ways the change could fail."
            else:
                outcome, detail = "empty", "The reader found no way the change fails."
    async with async_session_factory() as db:
        await manager.record_firing(
            db,
            plan.project_id,
            job=JOB,
            trigger=trigger,
            subject=subject_of(plan),
            runner_id=plan.runner_id,
            cli=plan.cli,
            model=plan.model,
            outcome=outcome,
            detail=detail,
            duration_ms=(result.duration_ms or 0) if result is not None else 0,
            usage=manager.usage_record(result.usage) if result is not None else None,
            answer=manager.answer_record(result) if result is not None else None,
            extra={"findings": findings},
        )
    return outcome


#: Documents with a firing under way, by (project, document): one Hub process owns its firings.
_running: Set[Tuple[str, str]] = set()
_in_flight: set = set()


def _spawn(work: Any) -> None:
    task = asyncio.get_running_loop().create_task(work)
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


async def _run_claimed(plan: Plan, trigger: str) -> None:
    """A firing that holds its document's claim, and gives it up however it ends."""
    try:
        await run(plan, trigger=trigger)
    except Exception as exc:  # noqa: BLE001 -- a background task must not raise
        logger.warning("pre-mortem failed for %s", plan.document_id, exc_info=True)
        try:
            async with async_session_factory() as db:
                await manager.record_firing(
                    db,
                    plan.project_id,
                    job=JOB,
                    trigger=trigger,
                    subject=subject_of(plan),
                    runner_id=plan.runner_id,
                    cli=plan.cli,
                    model=plan.model,
                    outcome="failed",
                    detail=f"The firing failed: {exc}",
                    duration_ms=0,
                    usage=None,
                    extra={"findings": []},
                )
        except Exception:  # noqa: BLE001
            logger.warning("could not record a failed pre-mortem", exc_info=True)
    finally:
        _running.discard((plan.project_id, plan.document_id))


async def request(db: AsyncSession, project_id: str, path: str) -> None:
    """Run a pre-mortem: start a firing for the document now, or `CannotRunError`. The claim is
    taken with no await after the check, so a second press cannot get past it."""
    document = await find_document(db, project_id, path)
    if document is None:
        raise CannotRunError(f"No document '{path}'", status=404)
    job, runner = await gate(db, project_id, REQUESTED)
    if not await _identifiers(db, project_id, document.id):
        raise CannotRunError(
            "This document has no requirements yet, so there is nothing to run a pre-mortem on."
        )
    plan = _plan(document, job, runner)
    if (project_id, document.id) in _running:
        raise CannotRunError("A pre-mortem of this document is in progress.")
    _running.add((project_id, document.id))
    _spawn(_run_claimed(plan, REQUESTED))


async def _fire_automatic(project_id: str, document_id: str) -> None:
    """The automatic entry: a document not reviewed now is simply not reviewed, and nothing here
    raises into the event loop."""
    subject = {"document": document_id}
    try:
        async with async_session_factory() as db:
            job, runner = await gate(db, project_id, CRITERIA_WRITTEN)
            document = await db.get(SpecDocument, document_id)
            if document is None:
                return
            plan = _plan(document, job, runner)
    except CannotRunError as refusal:
        if refusal.no_runner:
            await manager.record_no_runner(
                project_id, job=JOB, trigger=CRITERIA_WRITTEN, subject=subject
            )
        return
    except Exception:  # noqa: BLE001 -- a background task must not raise
        logger.warning("pre-mortem could not start for %s", document_id, exc_info=True)
        return
    if (project_id, document_id) in _running:
        return
    _running.add((project_id, document_id))
    await _run_claimed(plan, CRITERIA_WRITTEN)


_PENDING_KEY = "pre_mortem_pending"


def leaves_criteria(move_from: Optional[str], move_to: str, order: List[str]) -> bool:
    """Whether a step move leaves a criteria-writing step forward: moving back to rework the
    requirements is not the criteria being written."""
    if move_from not in CRITERIA_STEPS or move_to == move_from:
        return False
    if move_to not in order or move_from not in order:
        return False
    return order.index(move_to) > order.index(move_from)


def fire_after_commit(session: AsyncSession, document: SpecDocument) -> None:
    """Fire for *document* once the session's root transaction commits, and never if it does not.
    Whether the job is on and automatic is judged when it fires."""
    pending = session.sync_session.info.setdefault(_PENDING_KEY, set())
    pending.add((document.project_id, document.id))


@event.listens_for(Session, "after_commit")
def _fire_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING_KEY, set())
    if not pending:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("no event loop to fire the pre-mortem; it will not fire for this move")
        return
    for project_id, document_id in pending:
        _spawn(_fire_automatic(project_id, document_id))


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)


async def settled() -> None:
    """Wait for the firings under way (tests, and a clean shutdown)."""
    while _in_flight:
        await asyncio.gather(*list(_in_flight), return_exceptions=True)


async def _events(db: AsyncSession, project_id: str, document_id: str) -> List[EventLog]:
    return list(
        (
            await db.execute(
                select(EventLog)
                .where(
                    EventLog.project_id == project_id,
                    EventLog.event_type == manager.FIRED_EVENT,
                    EventLog.data["job"].as_string() == JOB,
                    EventLog.data["subject"]["document"].as_string() == document_id,
                )
                .order_by(EventLog.timestamp.desc(), EventLog.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def list_for_document(
    db: AsyncSession, project_id: str, document_id: str
) -> List[Dict[str, Any]]:
    """The document's pre-mortems, written or not, newest first (the contract's `PreMortem`)."""
    listed = []
    for row in await _events(db, project_id, document_id):
        data = row.data or {}
        listed.append(
            {
                "id": row.id,
                "at": row.timestamp.isoformat(),
                "trigger": data.get("trigger"),
                "model": data.get("model"),
                "outcome": data.get("outcome"),
                "detail": data.get("detail"),
                "cost_usd_micros": (data.get("usage") or {}).get("cost_usd_micros"),
                "findings": data.get("findings") or [],
            }
        )
    return listed


async def briefing_lines(db: AsyncSession, project_id: str, document_id: str) -> List[str]:
    """The `### Pre-mortem findings` block of a turn with the document open: the latest written
    firing's findings and what to do with them. Empty when the document has no written firing."""
    latest = next(
        (
            row
            for row in await _events(db, project_id, document_id)
            if (row.data or {}).get("outcome") == "written" and (row.data or {}).get("findings")
        ),
        None,
    )
    if latest is None:
        return []
    lines = [
        HEADING,
        f"- A pre-mortem of this document ({latest.timestamp.date().isoformat()}) assumed the "
        "change shipped and failed, and found these ways it fails:",
    ]
    for finding in latest.data["findings"]:
        tag = f"{finding['requirement']}: " if finding.get("requirement") else ""
        cites = f" (cites: {', '.join(finding['cites'])})" if finding.get("cites") else ""
        lines.append(f"  - {tag}{finding.get('story', '')}{cites}")
    lines.append(
        "- **Fix what you can in the document yourself** -- a missing case, a criterion that would "
        "pass for the wrong reason, a conflict the design does not name -- and say what you "
        "changed. **Bring the rest to the operator as questions**, under the questioning rule, "
        "where only they can decide."
    )
    lines.append("")
    return lines
