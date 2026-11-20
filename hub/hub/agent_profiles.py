"""Which profile an agent name counts as (`fold-duplicate-agents-into-one-profile-with-their-
history-kept`, design D3).

A folded agent counts as the profile it was folded into (`Agent.folded_into`); every other name
counts as itself. One level only: a profile is never itself folded (the fold refuses
`fold_profile_folded` and `fold_source_is_profile`), so resolving is a single lookup, never a chain.

Every check that an agent is not reviewing its own work compares what these return, never raw
names, so a folded name cannot open a hole in review independence.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent


async def folded_map(
    session: AsyncSession, project_id: str, names: Optional[Iterable[str]] = None
) -> Dict[str, str]:
    """`{folded name: profile}` for the project's folded agents, limited to *names* when given."""
    query = select(Agent.name, Agent.folded_into).where(
        Agent.project_id == project_id, Agent.folded_into.is_not(None)
    )
    if names is not None:
        wanted = [name for name in names if name]
        if not wanted:
            return {}
        query = query.where(Agent.name.in_(wanted))
    rows = (await session.execute(query)).all()
    return {name: profile for name, profile in rows if profile}


async def profile_of(session: AsyncSession, project_id: str, name: str) -> str:
    """The profile *name* counts as: the one it was folded into, else *name* itself."""
    return (await folded_map(session, project_id, [name])).get(name, name)


async def profiles_of(session: AsyncSession, project_id: str, names: Iterable[str]) -> Set[str]:
    """The profiles *names* count as, empty names left out."""
    wanted = [name for name in names if name]
    folded = await folded_map(session, project_id, wanted)
    return {folded.get(name, name) for name in wanted}
