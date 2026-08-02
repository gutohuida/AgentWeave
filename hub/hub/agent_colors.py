"""Stable per-agent colour assignment (task 8.1).

Assignment is by registration order into a fixed palette, with the index persisted on
the `Agent` row — never derived from the agent's name (see design.md's "Agent identity
colors" section). A name hash would collide, produce unpredictable adjacent pairs, and
change on rename; a persisted index survives all three.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent

# Matches the CSS palette in hub/ui/src/index.css (--agent-color-0 .. --agent-color-7).
# Beyond this many concurrently-registered agents, hues cycle and the name label
# (always rendered alongside colour, per the spec) disambiguates.
PALETTE_SIZE = 8


async def next_color_index(session: AsyncSession, project_id: str) -> int:
    """The colour index to assign to the next agent registered in this project.

    Monotonically increasing per project rather than reusing a gap left by a removed
    agent, so two agents never end up sharing a colour while both are registered.
    """
    result = await session.execute(
        select(func.max(Agent.color_index)).where(Agent.project_id == project_id)
    )
    current_max = result.scalar()
    return 0 if current_max is None else current_max + 1
