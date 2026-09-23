"""Whether a name a route was given is an agent this project has.

A route keyed by `{agent}` that never asks answers a typo with an honest-looking empty result: no
conversations, nothing queued, an idle agent, a workspace "not provisioned yet" (F192, F194, F199,
F247). The trigger route has always refused the same mistake by name; this is that question, asked
once, for every other route that takes an agent name.

**Known** means anything in this project recorded under the name — and it must stay a superset of
every source `GET /agents` lists a name from (`api/v1/agents.py` `list_agents`: the roster, message
senders and recipients, heartbeats, output, task assignees). A name the roster shows and these
routes refuse is the one thing worse than the empty answer this replaced (Round 4 review). The rows
beyond the roster matter for a second reason: session sync deletes the roster row of an agent the
session no longer declares and keeps its history. A name with none of these is a mistake.
"""

from fastapi import HTTPException, status
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import worktrees
from .db.models import (
    Agent,
    AgentHeartbeat,
    AgentOutput,
    Conversation,
    InboundQueueEntry,
    Message,
    Run,
    Task,
)


async def agent_is_known(session: AsyncSession, project_id: str, agent: str) -> bool:
    try:
        # `user` and `operator` are not agents whatever is recorded under them (F415).
        worktrees.validate_agent_name(agent)
    except ValueError:
        return False
    for model, predicate in (
        (Agent, Agent.name == agent),
        (Conversation, Conversation.agent == agent),
        (InboundQueueEntry, InboundQueueEntry.agent == agent),
        (Run, Run.agent == agent),
        (Task, Task.assignee == agent),
        (Message, or_(Message.sender == agent, Message.recipient == agent)),
        (AgentHeartbeat, AgentHeartbeat.agent == agent),
        (AgentOutput, AgentOutput.agent == agent),
    ):
        if await session.scalar(select(exists().where(model.project_id == project_id, predicate))):
            return True
    return False


async def require_known_agent(session: AsyncSession, project_id: str, agent: str) -> None:
    """404 naming the mistake, unless *agent* is known to this project (see the module)."""
    if not await agent_is_known(session, project_id, agent):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"{agent} is not an agent in this project: nothing here is recorded under that "
                "name. Correct the name, or create the agent in the Hub UI."
            ),
        )
