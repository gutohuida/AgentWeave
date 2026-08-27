"""A posture chosen by the operator survives the hop to a run they did not start.

Overrides live on the conversation, and a trigger naming no conversation opens a new one. The
operator's interface always names one; a job and a peer message do not. Found by driving the loop
end to end: the operator set `workspace` in the composer, the builder handed work to the reviewer,
the reviewer replied — and the run that followed had `overrides=None` and could not execute
anything, silently, in the middle of work the operator had configured.
"""

from datetime import datetime, timezone

import pytest

from hub.conversations import (
    SCHEDULED_ORIGIN,
    UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE,
    UNINHERITED_PERMISSION_MODE,
    get_conversation_by_id,
    inherit_runtime_overrides,
    new_conversation,
)
from hub.db.engine import async_session_factory

PROJECT = "proj-test"


async def _conversation(agent, overrides=None, origin="operator"):
    async with async_session_factory() as session:
        row = new_conversation(project_id=PROJECT, agent=agent, origin=origin)
        row.runtime_overrides = overrides
        session.add(row)
        await session.commit()
        return row.id


async def _conversation_at(agent, overrides, created_at):
    """Like `_conversation`, but with an explicit `created_at` — so two rows can share a
    timestamp to the microsecond, the way two real conversations do inside one Windows clock
    tick (~15.6ms), without depending on real wall-clock timing to reproduce it."""
    async with async_session_factory() as session:
        row = new_conversation(project_id=PROJECT, agent=agent, origin="operator")
        row.created_at = created_at
        row.updated_at = created_at
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
async def test_the_most_recent_overrides_win_even_with_an_identical_created_at(app):
    """The direct regression test for the tie: two conversations sharing one `created_at` to the
    microsecond — as two real conversations can inside a single ~15.6ms Windows clock tick — must
    still resolve to whichever was actually committed second, not to whichever `created_at` ties
    happen to sort first. `sequence`, not `created_at`, is what makes this answerable at all."""
    tie = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await _conversation_at("simultaneous", {"permission_mode": "acceptEdits"}, tie)
    await _conversation_at("simultaneous", {"permission_mode": "workspace"}, tie)
    assert await _inherit("simultaneous") == {"permission_mode": "workspace"}


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
async def test_ask_me_first_is_not_carried_into_a_scheduled_firing(app):
    """A posture that waits for a person is not a posture for a turn that runs at 03:00.

    Measured live on 2026-08-28. An interactive drive left `manual` on a builder conversation; two
    hours later a loop fired, inherited it, and spent eight minutes opening permission cards and
    timing them out one at a time — `Edit`, then `Bash`, then `PowerShell`, each *"no operator
    answered within 120s"*. The turn then recorded `completed`, having been refused everything it
    tried, which is the worst shape the failure could take.

    Dropped rather than replaced, exactly as `bypassPermissions` is: the agent's own
    `default_permission_mode` and then the catalog default are what should decide an unwatched
    turn's posture.
    """
    await _conversation("nightly", {"permission_mode": UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE})
    assert await _inherit("nightly", origin=SCHEDULED_ORIGIN) is None


@pytest.mark.asyncio
async def test_ask_me_first_is_still_carried_into_a_peer_run(app):
    """The other direction, and the reason this is scoped by origin rather than dropped outright.

    A peer message usually follows something the operator just did, so they are there to answer;
    an extra card is cheap and losing their chosen posture mid-conversation is not.
    """
    await _conversation("relay", {"permission_mode": UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE})
    assert await _inherit("relay", origin="peer") == {
        "permission_mode": UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE
    }


@pytest.mark.asyncio
async def test_a_firing_still_inherits_a_posture_it_can_act_on(app):
    """Withholding one value must not turn into withholding the posture."""
    await _conversation("worker", {"permission_mode": "workspace"})
    assert await _inherit("worker", origin=SCHEDULED_ORIGIN) == {"permission_mode": "workspace"}


@pytest.mark.asyncio
async def test_a_firing_keeps_the_model_beside_a_withheld_posture(app):
    """The model the operator chose is not a permission decision and travels either way."""
    await _conversation(
        "tuned",
        {
            "permission_mode": UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE,
            "model": "claude-opus-5",
        },
    )
    assert await _inherit("tuned", origin=SCHEDULED_ORIGIN) == {"model": "claude-opus-5"}


@pytest.mark.asyncio
async def test_full_access_is_withheld_from_a_firing_too(app):
    """The original rule is unconditional and stays unconditional."""
    await _conversation("widejob", {"permission_mode": UNINHERITED_PERMISSION_MODE})
    assert await _inherit("widejob", origin=SCHEDULED_ORIGIN) is None


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
        source = await get_conversation_by_id(session, source_id)
        source.runtime_overrides = {"permission_mode": "acceptEdits"}
        await session.commit()

    assert inherited == {"permission_mode": "workspace"}


@pytest.mark.asyncio
async def test_another_agents_overrides_are_not_inherited(app):
    await _conversation("owner", {"permission_mode": "workspace"})
    assert await _inherit("stranger") is None
