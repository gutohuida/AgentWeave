"""A capability refused because of project state the agent cannot change reaches the operator.

`a-refused-capability-reaches-the-operator` (finding F376). An agent refused `create_flow` because
`projects.allow_agent_jobs` was off got a sentence promising an approval nobody was asked for, and
the operator came back to nothing: the refusal lived only in the agent's transcript. Here the
refusal opens a **question of record** (design D1) — never swept, rendered on the operator's
Questions destination, and answered through the shipped late-answer path that queues the answer and
wakes the agent even after its run has ended — and the refusal says so, truthfully (D6).

The call does not wait (D2). The 403 is raised at once whatever happens to the record, and opening
the record is best-effort: a record that fails to open degrades the refusal to "tell the operator
yourself", it never costs the agent its refusal (D16).

The record carries **no run and no conversation** (D10): the refused call waits for nothing, so a
record bound to its run would make every surface report that run as waiting on the operator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, NoReturn, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Question
from .schemas.questions import QuestionCreate, QuestionOption

logger = logging.getLogger(__name__)

REFUSAL_CODE = "project_setting_blocks_capability"

# How much of the operator's own answer a refusal or a follow-up question quotes back.
_QUOTE_LIMIT = 200


@dataclass(frozen=True)
class SettingGate:
    """One project setting that gates an agent capability, with the words both surfaces use.

    Everything here is project-level: nothing names the refused agent, its run or the call's
    arguments (D5), because the record is one question about the project and naming one caller in
    it would be false.
    """

    # Structural dedupe identifier written to `questions.subject_key`; never derived from prose
    # (D15), so the wording below can be edited without re-opening resolved records.
    subject_key: str
    setting: str
    current_value: str
    # "Agents cannot <refused_action> in this project".
    refused_action: str
    ask: str
    consequence: str
    what_enabling_allows: str
    where_changed: str
    header: str
    first_options: Tuple[Tuple[str, str], ...]
    last_options: Tuple[Tuple[str, str], ...]
    # What an agent may do once the setting is on, for the tail of the refusal.
    retry_hint: str


# The one caller in this change: `jobs._require_agent_job_allowance`. Its branch is
# `not project.allow_agent_jobs`, so the value is "off" at every call that can reach here.
AGENT_JOBS = SettingGate(
    subject_key="capability-refusal:allow_agent_jobs",
    setting="allow_agent_jobs",
    current_value="off",
    refused_action="create or change scheduled work",
    ask="May agents schedule work in this project?",
    consequence=(
        "the Hub refuses every attempt by an agent to create or change scheduled work — loops, "
        "flows and jobs."
    ),
    what_enabling_allows=(
        "Enabling it lets agents create and run recurring work, which commits repeated model spend "
        "without asking again."
    ),
    where_changed="Environment › Settings",
    header="Scheduled work",
    # Answering does not flip the setting (D4); the descriptions say so rather than implying it.
    first_options=(
        (
            "Enabled it — go ahead",
            "Turn the setting on yourself at Environment › Settings; agents may then schedule "
            "recurring work here.",
        ),
        ("Leave it off", "Agents keep being refused."),
    ),
    last_options=(
        (
            "I'll enable it now",
            "Turn the setting on yourself at Environment › Settings; agents may then schedule "
            "recurring work here.",
        ),
        (
            "Leave it off — stop asking",
            "Agents keep being refused, and the Hub will not ask about this again.",
        ),
    ),
    retry_hint="create the job then",
)


@dataclass(frozen=True)
class _Outcome:
    """What happened to the record, which decides the refusal's second sentence.

    `opened`: the first record for this state. `pending`: one is open and unanswered.
    `reopened`: the previous one was resolved and this is the last the Hub will open (D17).
    `settled`: two have been resolved, and nothing more is opened.
    """

    kind: str
    record: Optional[Question]
    previous: Optional[Question] = None


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _QUOTE_LIMIT else text[: _QUOTE_LIMIT - 1].rstrip() + "…"


def _what_they_said(question: Question) -> str:
    """The operator's resolution in their own words, never judged for polarity (D13).

    A typed answer stores no labels (`AnswerForm`, `AgentOutputPanel` send labels only when the text
    is empty), so reading the answer's intent is not something the Hub can do. It reports instead.
    """
    if question.declined:
        return "declined to answer"
    said = (question.answer or "").strip() or ", ".join(question.answer_labels or [])
    if not said:
        return "gave an empty answer"
    return f"answered: “{_quote(said)}”"


async def _records(session: AsyncSession, project_id: str, subject_key: str) -> List[Question]:
    result = await session.execute(
        select(Question)
        .where(Question.project_id == project_id)
        .where(Question.subject_key == subject_key)
        .order_by(Question.created_at.desc(), Question.id.desc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def _is_resolved(question: Question) -> bool:
    # `_completed_batch`'s own definition: an answer or a decline both hand the decision back.
    return bool(question.answered or question.declined)


def _question_body(gate: SettingGate, agent: str, previous: Optional[Question]) -> QuestionCreate:
    if previous is None:
        text = (
            f"{gate.ask} The project setting `{gate.setting}` is **{gate.current_value}**, so "
            f"{gate.consequence} {gate.what_enabling_allows} You change it yourself at "
            f"{gate.where_changed}."
        )
        options = gate.first_options
    else:
        text = (
            f"You were asked this before and {_what_they_said(previous)}. The project setting "
            f"`{gate.setting}` is still **{gate.current_value}**, and an agent has been refused "
            f"again. {gate.ask} {gate.what_enabling_allows} You change it yourself at "
            f"{gate.where_changed}. This is the last time the Hub will ask about this setting."
        )
        options = gate.last_options
    return QuestionCreate(
        # Discarded by `ask_question_for_actor` in favour of its own keyword; passed the same value
        # so the two cannot disagree (task 1.5).
        from_agent=agent,
        question=text,
        blocking=False,
        options=[QuestionOption(label=label, description=desc) for label, desc in options],
        header=gate.header,
        multi_select=False,
    )


async def _open(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    gate: SettingGate,
    previous: Optional[Question],
) -> Question:
    from .api.v1.questions import ask_question_for_actor

    return await ask_question_for_actor(
        _question_body(gate, agent, previous),
        project_id=project_id,
        from_agent=agent,
        # D10: no run, and therefore no conversation. The refused call waits for nothing.
        created_by_run_id=None,
        session=session,
        subject_key=gate.subject_key,
    )


async def _record_refusal(
    session: AsyncSession, *, project_id: str, agent: str, gate: SettingGate
) -> _Outcome:
    """Find or open the record for this state. At most two are ever opened per project (D17).

    The bound is a row count, never a reading of what an answer said (D13): it is the same whether
    the operator clicked an option, typed, or declined.
    """
    records = await _records(session, project_id, gate.subject_key)
    if records and not _is_resolved(records[0]):
        return _Outcome("pending", records[0])
    if len(records) >= 2:
        return _Outcome("settled", None, previous=records[0])
    previous = records[0] if records else None
    try:
        opened = await _open(
            session, project_id=project_id, agent=agent, gate=gate, previous=previous
        )
    except IntegrityError:
        # Another refusal opened the record between our read and our insert; the partial unique
        # index refused this one (D15). Both callers report the same record.
        await session.rollback()
        records = await _records(session, project_id, gate.subject_key)
        if records and not _is_resolved(records[0]):
            return _Outcome("pending", records[0])
        raise
    return _Outcome("reopened" if previous is not None else "opened", opened, previous=previous)


def _refusal(gate: SettingGate, agent: str, outcome: Optional[_Outcome]) -> dict:
    lead = (
        f"Agents cannot {gate.refused_action} in this project: the project setting "
        f"`{gate.setting}` is {gate.current_value}."
    )
    no_wait = "This is a refusal, not a wait: do not poll, and do not repeat this call."
    record = outcome.record if outcome is not None else None

    if outcome is None:
        # D16: the record could not be opened. Say so; never name a record that does not exist.
        parts = [
            lead,
            f"The operator could not be asked automatically — tell them it needs enabling at "
            f"{gate.where_changed}.",
            no_wait,
        ]
    elif outcome.kind == "settled":
        assert outcome.previous is not None
        parts = [
            lead,
            f"The operator was asked twice and {_what_they_said(outcome.previous)}. The setting is "
            f"still {gate.current_value} and nothing further will be opened for it — raise it with "
            f"them in a message rather than repeating this call.",
            no_wait,
        ]
    else:
        assert record is not None
        if outcome.kind == "opened":
            asked = (
                f"The operator has been asked whether to enable it — question `{record.id}`, on "
                f"their Questions destination; the setting itself is at {gate.where_changed}."
            )
        elif outcome.kind == "reopened":
            assert outcome.previous is not None
            asked = (
                f"The operator was asked and {_what_they_said(outcome.previous)}. They have been "
                f"asked once more (`{record.id}`) — this is the last time."
            )
        else:
            asked = f"The operator was asked and has not answered yet (`{record.id}`)."
        if record.from_agent == agent:
            then = (
                f"If they enable it, their answer will reach you as a message and you can "
                f"{gate.retry_hint}; until then, do the work directly or say in a message that you "
                f"are blocked on it."
            )
        else:
            # The answer wakes the agent named on the record, not every agent refused while it was
            # open (D5's known limit, pinned by the spec).
            then = (
                f"Their answer goes to `{record.from_agent}`, who was refused first, not to you; "
                f"once the setting is on, this call will succeed. Until then, do the work directly "
                f"or say in a message that you are blocked on it."
            )
        parts = [lead, asked, no_wait, then]

    detail: dict = {
        "code": REFUSAL_CODE,
        "message": " ".join(parts),
        "setting": gate.setting,
        "current_value": gate.current_value,
    }
    if record is not None:
        detail["question_id"] = record.id
    return detail


async def refuse_for_project_state(
    session: AsyncSession, *, project_id: str, agent: str, gate: SettingGate
) -> NoReturn:
    """Refuse the call with a 403, having opened (or found) the operator's record of it.

    Always raises. Opening the record is best-effort (D16): SQLite `database is locked` is a live
    failure in exactly the concurrency F376 measured, and letting it escape would turn the refusal
    into a 500, leaving the agent with less than the sentence this replaces.

    Callers must invoke this before doing any work of their own: the record's commit would make
    anything already pending in the session durable (task 2.2).
    """
    outcome: Optional[_Outcome]
    try:
        outcome = await _record_refusal(session, project_id=project_id, agent=agent, gate=gate)
    except Exception:
        logger.exception(
            "Could not open the operator's record for a refused capability "
            "(project %s, key %s); refusing without one",
            project_id,
            gate.subject_key,
        )
        outcome = await _record_after_failure(session, project_id, gate)
    raise HTTPException(status_code=403, detail=_refusal(gate, agent, outcome))


async def _record_after_failure(
    session: AsyncSession, project_id: str, gate: SettingGate
) -> Optional[_Outcome]:
    """What is actually on record after opening one failed partway, or None if nothing is.

    `ask_question_for_actor` commits the row and broadcasts it *before* writing its event, so a
    failure there (SQLite `database is locked`, the live case) leaves a record the operator can
    already see. Saying "the operator could not be asked" then would deny a record that exists, the
    mirror of naming one that does not. So re-read, and report an open record as the pending one.
    """
    try:
        await session.rollback()
        records = await _records(session, project_id, gate.subject_key)
    except Exception:  # pragma: no cover - the refusal matters more than the re-read
        logger.exception("Re-reading the refusal record after a failure also failed")
        return None
    if records and not _is_resolved(records[0]):
        return _Outcome("pending", records[0])
    return None
