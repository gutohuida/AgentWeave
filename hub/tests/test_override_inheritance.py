"""A posture chosen by the operator survives the hop to a run they did not start.

Overrides live on the conversation, and a trigger naming no conversation opens a new one. The
operator's interface always names one; a job and a peer message do not. Found by driving the loop
end to end: the operator set `workspace` in the composer, the builder handed work to the reviewer,
the reviewer replied — and the run that followed had `overrides=None` and could not execute
anything, silently, in the middle of work the operator had configured.
"""

import pytest

from hub.conversations import (
    UNINHERITED_PERMISSION_MODE,
    inherit_runtime_overrides,
    new_conversation,
)
from hub.db.engine import async_session_factory
from hub.db.models import Conversation

PROJECT = "proj-test"


async def _conversation(agent, overrides=None, origin="operator"):
    async with async_session_factory() as session:
        row = new_conversation(project_id=PROJECT, agent=agent, origin=origin)
        row.runtime_overrides = overrides
        session.add(row)
        await session.commit()
        return row.id


async def _inherit(agent, origin="peer"):
    async with async_session_factory() as session:
        row = new_conversation(project_id=PROJECT, agent=agent, origin=origin)
        session.add(row)
        await inherit_runtime_overrides(session, row)
        await session.commit()
        return row.runtime_overrides


@pytest.mark.asyncio
async def test_a_new_conversation_inherits_the_chosen_posture(app):
    await _conversation("carrier", {"permission_mode": "workspace"})
    assert await _inherit("carrier") == {"permission_mode": "workspace"}


@pytest.mark.asyncio
async def test_an_agent_with_no_earlier_overrides_inherits_nothing(app):
    await _conversation("blank", None)
    assert await _inherit("blank") is None


@pytest.mark.asyncio
async def test_the_most_recent_overrides_win(app):
    await _conversation("recent", {"permission_mode": "acceptEdits"})
    await _conversation("recent", {"permission_mode": "workspace"})
    assert await _inherit("recent") == {"permission_mode": "workspace"}


@pytest.mark.asyncio
async def test_full_access_is_not_carried_into_a_run_the_operator_did_not_start(app):
    """Removing every check is a deliberate choice for a thread being watched. Reaching runs
    started by a peer or a job, by a route the operator cannot see, is not what it meant."""
    await _conversation("wide", {"permission_mode": UNINHERITED_PERMISSION_MODE})
    assert await _inherit("wide") is None


@pytest.mark.asyncio
async def test_other_overrides_survive_alongside_a_dropped_posture(app):
    await _conversation(
        "mixed", {"permission_mode": UNINHERITED_PERMISSION_MODE, "model": "claude-opus-5"}
    )
    assert await _inherit("mixed") == {"model": "claude-opus-5"}


@pytest.mark.asyncio
async def test_a_conversation_that_states_its_own_overrides_inherits_nothing(app):
    await _conversation("stated", {"permission_mode": "workspace"})
    async with async_session_factory() as session:
        row = new_conversation(project_id=PROJECT, agent="stated", origin="peer")
        row.runtime_overrides = {"permission_mode": "manual"}
        session.add(row)
        await inherit_runtime_overrides(session, row)
        await session.commit()
        assert row.runtime_overrides == {"permission_mode": "manual"}


@pytest.mark.asyncio
async def test_inheriting_does_not_couple_the_two_conversations(app):
    """A starting point, not a shared setting — the values are copied."""
    source_id = await _conversation("decoupled", {"permission_mode": "workspace"})
    inherited = await _inherit("decoupled")

    async with async_session_factory() as session:
        source = await session.get(Conversation, source_id)
        source.runtime_overrides = {"permission_mode": "acceptEdits"}
        await session.commit()

    assert inherited == {"permission_mode": "workspace"}


@pytest.mark.asyncio
async def test_another_agents_overrides_are_not_inherited(app):
    await _conversation("owner", {"permission_mode": "workspace"})
    assert await _inherit("stranger") is None
