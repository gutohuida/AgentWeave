"""Whether a name a route was given is an agent this project has.

A route keyed by `{agent}` that never asks answers a typo with an honest-looking empty result: no
conversations, nothing queued, an idle agent, a workspace "not provisioned yet" (F192, F194, F199,
F247). The trigger route has always refused the same mistake by name; this is that question, asked
once, for every other route that takes an agent name.

**Known** means anything in this project recorded under the name — and it must stay a superset of
every source `GET /agents` lists a name from (`api/v1/agents.py` `list_agents`: since F618, the
`agents` table alone). A name the roster shows and these
routes refuse is the one thing worse than the empty answer this replaced (Round 4 review). The rows
beyond the roster matter for a second reason: session sync deletes the roster row of an agent the
session no longer declares and keeps its history. A name with none of these is a mistake.
"""

from typing import Optional

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


def _not_an_agent(agent: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"{agent} is not an agent in this project: nothing here is recorded under that "
            "name. Correct the name, or create the agent in the Hub UI."
        ),
    )


async def require_known_agent(session: AsyncSession, project_id: str, agent: str) -> None:
    """404 naming the mistake, unless *agent* is known to this project (see the module)."""
    if not await agent_is_known(session, project_id, agent):
        raise _not_an_agent(agent)


async def require_agent_row(session: AsyncSession, project_id: str, agent: str) -> None:
    """404 naming the mistake, unless this project has an agent row under *agent*.

    For a route that *writes* under the name. It cannot ask `agent_is_known`: its own write is
    what would make the name known, so one call to a typo minted an agent (F618).
    """
    try:
        worktrees.validate_agent_name(agent)
    except ValueError:
        raise _not_an_agent(agent) from None
    found = await session.scalar(
        select(exists().where(Agent.project_id == project_id, Agent.name == agent))
    )
    if not found:
        raise _not_an_agent(agent)


async def assignee_refusal(session: AsyncSession, project_id: str, assignee: str) -> Optional[str]:
    """Why *assignee* cannot hold a task of this project, or None when it is an open agent.

    A task's holder is who its turns run as and who the roster counts it against; a name with no
    row was stored as given, and an archived agent is one nothing will run (F642).
    """
    lifecycle = await session.scalar(
        select(Agent.lifecycle).where(Agent.project_id == project_id, Agent.name == assignee)
    )
    if lifecycle is None:
        return (
            f"'{assignee}' is not an agent in this project, so it cannot hold a task. Assign one "
            f"of the project's agents, or create '{assignee}' in the Hub UI first."
        )
    if lifecycle == "archived":
        return (
            f"'{assignee}' is archived, so it cannot hold a task. Unarchive it, or assign one of "
            "the project's open agents."
        )
    return None
