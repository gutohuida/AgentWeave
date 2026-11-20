"""Which profile an agent name counts as (`fold-duplicate-agents-into-one-profile-with-their-
history-kept`, design D3).

A folded agent counts as the profile it was folded into (`Agent.folded_into`); every other name
counts as itself. One level only: a profile is never itself folded (the fold refuses
`fold_profile_folded` and `fold_source_is_profile`), so resolving is a single lookup, never a chain.

Every check that an agent is not reviewing its own work compares what these return, never raw
names, so a folded name cannot open a hole in review independence.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Set

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


async def shared_profile(
    session: AsyncSession, project_id: str, name: Optional[str], other: Optional[str]
) -> Optional[str]:
    """The profile *name* and *other* both count as, or None where they count as two (or either is
    empty). Two equal names share their own profile, folded or not."""
    if not name or not other:
        return None
    folded = await folded_map(session, project_id, [name, other])
    profile = folded.get(name, name)
    return profile if profile == folded.get(other, other) else None


def folded_message(name: str, profile: str) -> str:
    """The sentence every refusal of something addressed to a folded name carries (design D4)."""
    return f"{name} was folded into {profile}; address {profile} instead."


def folded_detail(name: str, profile: str) -> Dict[str, str]:
    """The 409 detail for something newly addressed to a folded name (design D4)."""
    return {
        "code": "agent_folded",
        "message": folded_message(name, profile),
        "agent": name,
        "folded_into": profile,
    }


async def folded_refusal(session: AsyncSession, project_id: str, name: str) -> Optional[str]:
    """The D4 message when *name* is a folded agent, else None."""
    profile = (await folded_map(session, project_id, [name])).get(name)
    return folded_message(name, profile) if profile else None


async def require_not_folded(session: AsyncSession, project_id: str, name: Optional[str]) -> None:
    """409 `agent_folded` naming the profile when *name* is a folded agent; a no-op otherwise.

    Raised for anything newly addressed to the name (FR-12) or launched under it (FR-5).
    """
    if not name:
        return
    profile = (await folded_map(session, project_id, [name])).get(name)
    if profile:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail=folded_detail(name, profile))


def counts_as(name: str, other: str, profile: str) -> str:
    """The clause saying *name* and *other* are one profile, naming it: the words every refusal on
    a fold's account quotes, so each names the profile (FR-9)."""
    return f"{name!r} and {other!r} both count as profile {profile!r}"


async def widen_to_profiles(
    session: AsyncSession, project_id: str, exclude: Mapping[str, str]
) -> Dict[str, str]:
    """*exclude* (`{agent: why it may not review}`) widened to every name of each excluded agent's
    profile: the profile itself and every name folded into it, each with its reason naming the
    profile. Names already excluded keep their own reason; with nothing folded this is *exclude*."""
    folded = await folded_map(session, project_id)
    if not folded:
        return dict(exclude)
    members: Dict[str, Set[str]] = {}
    for source, profile in folded.items():
        members.setdefault(profile, {profile}).add(source)
    widened = dict(exclude)
    for name, why in exclude.items():
        profile = folded.get(name, name)
        for other in sorted(members.get(profile, ())):
            if other not in widened:
                widened[other] = (
                    f"counts as profile {profile!r}, as {name!r} does, and {name!r} {why}"
                )
    return widened
