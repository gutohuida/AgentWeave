"""Operator-facing backstop for questions an agent ended a turn on without asking.

The rows are written by `agent_trigger._flag_unasked_question` when a run completes on a trailing
question having opened no question of record. These are the two things the operator can do about
one: have the agent ask it properly, or decide it was not a real question.

There is deliberately no "answer it here" action. The turn has ended and no tool call is waiting on
a value, so an answer typed here would go nowhere. Re-prompting is the only honest option.
"""

from datetime import datetime, timezone
from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...conversations import get_open_conversation, latest_open_conversation
from ...db.engine import get_session
from ...db.models import UnaskedQuestion
from ...sse import sse_manager

router = APIRouter(prefix="/unasked-questions", tags=["unasked-questions"])


# What the agent is told when the operator presses "Ask this properly". The wording is the
# mechanism, not decoration: it has to convert prose into a tool call, which is precisely what the
# agent failed to do unprompted. It names the exact text, says why text was not enough, and states
# the structure the tool requires — the same three things that made Codex do it correctly when
# asked explicitly during testing.
REPROMPT_TEMPLATE = (
    "You ended your last turn with this question, written as ordinary text:\n\n"
    "    {question}\n\n"
    "Written that way it reached nobody — the operator is not reading your output as it streams, "
    "and a question that is not asked through the tool is a question no one can answer.\n\n"
    "Ask it now by calling the `ask_user` tool. It requires a `header`, at least two `options` "
    "(each with a `label` and a `description` explaining the trade-off), and `multi_select`. The "
    "call blocks until the operator answers, and the answer comes back as the tool's result — so "
    "call it and wait, rather than restating the question as text and stopping again."
)


class UnaskedQuestionResponse(BaseModel):
    id: str
    agent: str
    run_id: str | None
    conversation_id: str | None
    question: str
    status: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


async def _pending_row(
    session: AsyncSession, project_id: str, record_id: str
) -> UnaskedQuestion:
    """Fetch one record, refusing anything already acted on.

    Acting twice would produce two turns racing on one question, which is worse than an error the
    operator can see.
    """
    row = (
        await session.execute(
            select(UnaskedQuestion).where(
                UnaskedQuestion.id == record_id,
                UnaskedQuestion.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such unasked question")
    if row.status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"this question was already {row.status}",
        )
    return row


@router.get("", response_model=List[UnaskedQuestionResponse])
async def list_unasked_questions(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    pending_only: bool = True,
):
    """List detected unasked questions, newest first. Pending-only by default — that is what the
    operator can still act on."""
    project_id, _ = project
    query = select(UnaskedQuestion).where(UnaskedQuestion.project_id == project_id)
    if pending_only:
        query = query.where(UnaskedQuestion.status == "pending")
    query = query.order_by(UnaskedQuestion.created_at.desc()).limit(100)
    return list((await session.execute(query)).scalars().all())


@router.post("/{record_id}/dismiss", response_model=UnaskedQuestionResponse)
async def dismiss_unasked_question(
    record_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Mark one as not worth acting on. The detection rule is deliberately permissive about
    rhetorical questions, so this is the expected cost of catching the real ones."""
    project_id, _ = project
    row = await _pending_row(session, project_id, record_id)
    row.status = "dismissed"
    row.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    await sse_manager.broadcast(
        project_id,
        "unasked_question_resolved",
        {"id": row.id, "agent": row.agent, "status": row.status},
    )
    return row


@router.post("/{record_id}/ask", response_model=UnaskedQuestionResponse)
async def ask_unasked_question(
    record_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Re-prompt the agent to ask its question through the tool.

    The status is flipped *before* the trigger and is not rolled back if the trigger fails: the
    endpoint reports the failure, and the operator can act again deliberately. Leaving it pending
    on a partial failure invites a second press that starts a second turn on the same question.
    """
    from .agent_trigger import TriggerAgentError, trigger_agent_directly

    project_id, _ = project
    row = await _pending_row(session, project_id, record_id)

    # The conversation the question was asked in, if it is still open; otherwise the agent's
    # current one. A re-prompt landing in the wrong conversation would ask the question somewhere
    # the operator is not looking, which is the failure this whole change is about.
    conversation = None
    if row.conversation_id:
        conversation = await get_open_conversation(
            session, project_id=project_id, agent=row.agent, conversation_id=row.conversation_id
        )
    if conversation is None:
        conversation = await latest_open_conversation(
            session, project_id=project_id, agent=row.agent
        )
    if conversation is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{row.agent} has no open conversation to ask in",
        )

    row.status = "asked"
    row.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    await sse_manager.broadcast(
        project_id,
        "unasked_question_resolved",
        {"id": row.id, "agent": row.agent, "status": row.status},
    )

    try:
        await trigger_agent_directly(
            project_id=project_id,
            agent=row.agent,
            message=REPROMPT_TEMPLATE.format(question=row.question),
            conversation_id=conversation.id,
            session=session,
        )
    except TriggerAgentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    return row
