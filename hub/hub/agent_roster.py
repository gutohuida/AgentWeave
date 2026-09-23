"""Whether a name a route was given is an agent this project has.

A route keyed by `{agent}` that never asks answers a typo with an honest-looking empty result: no
conversations, nothing queued, an idle agent, a workspace "not provisioned yet" (F192, F194, F199,
F247). The trigger route has always refused the same mistake by name; this is that question, asked
once, for every other route that takes an agent name.

**Known** means on the roster *or* recorded under that name. Session sync deletes the roster row of
an agent the session no longer declares and keeps its conversations, queue and runs, so a roster-only
check would hide a removed agent's history behind a 404. A name with neither is a mistake.
"""

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent, Conversation, InboundQueueEntry, Run


async def agent_is_known(session: AsyncSession, project_id: str, agent: str) -> bool:
    for model in (Agent, Conversation, InboundQueueEntry, Run):
        column = model.name if model is Agent else model.agent
        found = await session.scalar(
            select(exists().where(model.project_id == project_id, column == agent))
        )
        if found:
            return True
    return False


async def require_known_agent(session: AsyncSession, project_id: str, agent: str) -> None:
    """404 naming the mistake, unless *agent* is known to this project (see the module)."""
    if not await agent_is_known(session, project_id, agent):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"{agent} is not an agent in this project: it is not on the roster and nothing is "
                "recorded under that name. Correct the name, or create the agent in the Hub UI."
            ),
        )
