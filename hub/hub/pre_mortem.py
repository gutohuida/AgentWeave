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

`the-spec-process-uses-what-the-hub-already-knows` (FR-3 to FR-6): the automatic firing happens only
while the document has no completed firing (written or empty; a failed one does not count), so a
later one is the operator's button. The author (`spec_amendments.authors`) answers the newest written
firing's findings, one or every unanswered one at once, each with a note (`answer`). An answer is an
appended `pre_mortem_answered` event naming its firing -- still no table -- so findings are read with
their answers (`list_for_document`), the briefing lists only the unanswered ones, and the document
check reports them as the `pre_mortem_unanswered` gap (`unanswered`).
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
ANSWER_EVENT = "pre_mortem_answered"
#: The outcomes that count as the document's one automatic pre-mortem: the firing completed.
COMPLETED = ("written", "empty")
NOTE_CHARS = 4000

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


class AnswerRefusedError(Exception):
    """Why an answer is not recorded, with the status and code the answer route refuses it with.
    Nothing is written when it is raised; `newest` names the firing that is answerable now."""

    def __init__(
        self, reason: str, *, code: str, status: int = 422, newest: Optional[str] = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.status = status
        self.newest = newest

    def detail(self) -> Dict[str, Any]:
        detail: Dict[str, Any] = {"message": self.reason, "code": self.code}
        if self.newest is not None:
            detail["newest"] = self.newest
        return detail


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
    """A firing that holds its document's claim, and gives it up however it ends. It is one run,
    announced when it starts and ended with a record however it ends (`manager.manager_run`)."""
    try:
        async with manager.manager_run(
            plan.project_id,
            job=JOB,
            trigger=trigger,
            subject=subject_of(plan),
            initiator=manager.OPERATOR if trigger == REQUESTED else manager.AUTONOMOUS,
        ) as current:
            current.uses(runner_id=plan.runner_id, cli=plan.cli, model=plan.model)
            await _run_recorded(plan, trigger)
    except Exception:  # noqa: BLE001 -- a background task must not raise
        logger.warning("pre-mortem run failed for %s", plan.document_id, exc_info=True)
    finally:
        _running.discard((plan.project_id, plan.document_id))


async def _run_recorded(plan: Plan, trigger: str) -> None:
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
            # Automatic only until one has completed; after that a re-run is the button's (FR-6).
            if await has_completed(db, project_id, document_id):
                return
            plan = _plan(document, job, runner)
    except CannotRunError as refusal:
        if refusal.no_runner:
            async with manager.manager_run(
                project_id,
                job=JOB,
                trigger=CRITERIA_WRITTEN,
                subject=subject,
                initiator=manager.AUTONOMOUS,
            ):
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


def _newest_written(rows: List[EventLog]) -> Optional[EventLog]:
    """The newest firing that wrote findings, of *rows* newest first: the one to answer (FR-6)."""
    return next(
        (
            row
            for row in rows
            if (row.data or {}).get("outcome") == "written" and (row.data or {}).get("findings")
        ),
        None,
    )


async def has_completed(db: AsyncSession, project_id: str, document_id: str) -> bool:
    """Whether the document has a firing that wrote findings or found none; a failed one does not
    count, so the automatic firing tries again (FR-6)."""
    return any(
        (row.data or {}).get("outcome") in COMPLETED
        for row in await _events(db, project_id, document_id)
    )


async def answers_by_firing(
    db: AsyncSession, project_id: str, document_id: str
) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Each firing's answers, by firing id then finding number (1-based), as `{note, by, at}`. A
    later answer to the same finding replaces an earlier one."""
    rows = (
        (
            await db.execute(
                select(EventLog)
                .where(
                    EventLog.project_id == project_id,
                    EventLog.event_type == ANSWER_EVENT,
                    EventLog.data["document"].as_string() == document_id,
                )
                .order_by(EventLog.timestamp, EventLog.id)
            )
        )
        .scalars()
        .all()
    )
    answers: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for row in rows:
        data = row.data or {}
        firing = data.get("firing")
        if not firing:
            continue
        given = {
            "note": data.get("note") or "",
            "by": row.agent or data.get("by") or "",
            "at": row.timestamp.isoformat(),
        }
        for number in data.get("findings") or []:
            if isinstance(number, int):
                answers.setdefault(firing, {})[number] = given
    return answers


async def list_for_document(
    db: AsyncSession, project_id: str, document_id: str
) -> List[Dict[str, Any]]:
    """The document's pre-mortems, written or not, newest first (the contract's `PreMortem`). Each
    finding carries its `answer` (the contract's `PreMortemAnswer`), or null while unanswered."""
    answers = await answers_by_firing(db, project_id, document_id)
    listed = []
    for row in await _events(db, project_id, document_id):
        data = row.data or {}
        given = answers.get(row.id, {})
        listed.append(
            {
                "id": row.id,
                "at": row.timestamp.isoformat(),
                "trigger": data.get("trigger"),
                "model": data.get("model"),
                "outcome": data.get("outcome"),
                "detail": data.get("detail"),
                "cost_usd_micros": (data.get("usage") or {}).get("cost_usd_micros"),
                "findings": [
                    {**finding, "answer": given.get(number)}
                    for number, finding in enumerate(data.get("findings") or [], start=1)
                ],
            }
        )
    return listed


@dataclass(frozen=True)
class OpenFindings:
    """The newest written firing of a document and which of its findings are unanswered."""

    firing: EventLog
    findings: List[Dict[str, Any]]
    unanswered: List[int]


async def open_findings(
    db: AsyncSession, project_id: str, document_id: str
) -> Optional[OpenFindings]:
    """The newest written firing and its unanswered finding numbers, or None with no written one."""
    latest = _newest_written(await _events(db, project_id, document_id))
    if latest is None:
        return None
    findings = list(latest.data["findings"])
    given = (await answers_by_firing(db, project_id, document_id)).get(latest.id, {})
    left = [number for number in range(1, len(findings) + 1) if number not in given]
    return OpenFindings(latest, findings, left)


async def unanswered(db: AsyncSession, document: SpecDocument) -> Optional[Tuple[int, int]]:
    """`(unanswered, total)` of the document's newest written pre-mortem, or None with none
    written: what the check's `pre_mortem_unanswered` gap reports (FR-5)."""
    found = await open_findings(db, document.project_id, document.id)
    if found is None:
        return None
    return len(found.unanswered), len(found.findings)


async def answer(
    db: AsyncSession,
    document: SpecDocument,
    *,
    agent: str,
    firing: str,
    note: str,
    finding: Optional[int] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Record the author's answer to finding *finding* of *firing*, or to every unanswered finding
    of it when *finding* is None (FR-4). Refused with `AnswerRefusedError`, writing nothing: an
    empty note (422 `note_required`), an agent that is not one of the document's authors (403
    `not_author`), a document with no written pre-mortem (404 `no_written_pre_mortem`), a firing
    that is not the newest written one, unknown ids included (409 `firing_not_newest`, naming the
    newest), a finding number the firing does not have (422 `finding_unknown`), and an answer to
    all when none is left (409 `nothing_unanswered`). The caller commits."""
    from . import spec_amendments
    from .utils import persist_event

    text = (note or "").strip()
    if not text:
        raise AnswerRefusedError(
            "an answer needs a note saying what you did about the finding (what you changed in "
            "the document, or why it needs no change); nothing was recorded",
            code="note_required",
        )
    if len(text) > NOTE_CHARS:
        raise AnswerRefusedError(
            f"the note is longer than {NOTE_CHARS} characters", code="note_too_long"
        )
    writers = await spec_amendments.authors(db, document)
    if agent not in writers:
        named = ", ".join(writers) or "nobody yet"
        raise AnswerRefusedError(
            "only the document's author answers its pre-mortem (a profile that saved its "
            f"content before its first approval: {named}); tell the author what you found "
            "instead",
            code="not_author",
            status=403,
        )
    found = await open_findings(db, document.project_id, document.id)
    if found is None:
        raise AnswerRefusedError(
            "this document has no written pre-mortem, so there is nothing to answer",
            code="no_written_pre_mortem",
            status=404,
        )
    if firing != found.firing.id:
        raise AnswerRefusedError(
            f"'{firing}' is not this document's newest written pre-mortem: answer "
            f"'{found.firing.id}', whose findings are the ones still to answer",
            code="firing_not_newest",
            status=409,
            newest=found.firing.id,
        )
    if finding is not None:
        if finding < 1 or finding > len(found.findings):
            raise AnswerRefusedError(
                f"the pre-mortem '{firing}' has findings 1 to {len(found.findings)}, not {finding}",
                code="finding_unknown",
            )
        numbers = [finding]
    else:
        numbers = list(found.unanswered)
        if not numbers:
            raise AnswerRefusedError(
                f"every finding of the pre-mortem '{firing}' is already answered",
                code="nothing_unanswered",
                status=409,
            )
    await persist_event(
        db,
        document.project_id,
        ANSWER_EVENT,
        {
            "document": document.id,
            "path": document.path,
            "firing": firing,
            "findings": numbers,
            "note": text,
            "by": agent,
            "run_id": run_id,
        },
        agent=agent,
        commit=False,
    )
    return {
        "path": document.path,
        "firing": firing,
        "answered": numbers,
        "unanswered": [number for number in found.unanswered if number not in numbers],
        "total": len(found.findings),
    }


async def briefing_lines(
    db: AsyncSession, project_id: str, document_id: str, agent: Optional[str] = None
) -> List[str]:
    """The `### Pre-mortem findings` block of the author's turn with the document open: the newest
    written firing's unanswered findings and how to answer them (FR-3). Empty when the document has
    no written firing, when every finding is answered, and for an *agent* that is not its author."""
    found = await open_findings(db, project_id, document_id)
    if found is None or not found.unanswered:
        return []
    document = await db.get(SpecDocument, document_id)
    if document is None:
        return []
    if agent is not None:
        from . import spec_amendments

        if agent not in await spec_amendments.authors(db, document):
            return []
    latest = found.firing
    lines = [
        HEADING,
        f"- A pre-mortem of this document (`{latest.id}`, "
        f"{latest.timestamp.date().isoformat()}) assumed the change shipped and failed. "
        f"{len(found.unanswered)} of its {len(found.findings)} findings are unanswered:",
    ]
    for number in found.unanswered:
        finding = found.findings[number - 1]
        tag = f"{finding['requirement']}: " if finding.get("requirement") else ""
        cites = f" (cites: {', '.join(finding['cites'])})" if finding.get("cites") else ""
        lines.append(f"  {number}. {tag}{finding.get('story', '')}{cites}")
    lines.append(
        "- **Fix what you can in the document yourself** -- a missing case, a criterion that would "
        "pass for the wrong reason, a conflict the design does not name -- and say what you "
        "changed. **Bring the rest to the operator as questions**, under the questioning rule, "
        "where only they can decide."
    )
    lines.append(
        "- **Answer each finding once you have dealt with it**, with a note of what you did: "
        f'`answer_pre_mortem(path="{document.path}", firing="{latest.id}", note=...)` with '
        "`finding=<number>` for one, or without `finding` for every unanswered one at once. Until "
        "each is answered, the document's check reports a `pre_mortem_unanswered` gap and it is "
        "not ready to approve."
    )
    lines.append("")
    return lines
