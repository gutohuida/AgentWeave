"""A checkpoint is handed over once, and says where it went.

`a-checkpoint-is-handed-over-once-and-says-where-it-went` (F293, F294). The hand-over is a fact on
the checkpoint (`cut_over_to_conversation_id`), claimed by a conditional UPDATE and backed by a
partial unique index on the conversation, not something inferred from the predecessor's lifecycle.
"""

import asyncio

import pytest
from sqlalchemy import select

from hub.checkpoint_cutover import CutoverRefusedError, cut_over
from hub.checkpoints import get_checkpoint_by_id
from hub.conversations import get_conversation_by_id, unarchive
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.inbound_queue import deliver_entries_with_run

from .test_checkpoint_cutover import AGENT, PROJECT, _conversation, _ready_checkpoint


async def _successors(db):
    return (
        (await db.execute(select(Conversation).where(Conversation.origin == "handoff")))
        .scalars()
        .all()
    )


async def _checkpoint_entries(db):
    return (
        (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "checkpoint")
            )
        )
        .scalars()
        .all()
    )


async def _reopen(db, conversation):
    unarchive(conversation)
    await db.commit()


@pytest.mark.asyncio
async def test_reopening_the_predecessor_does_not_re_arm_its_checkpoint(app):
    """F293: unarchiving cleared the only thing the guard read, so the checkpoint cut over again."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        checkpoint = await _ready_checkpoint(db, conversation)
        successor, _ = await cut_over(db, conversation, checkpoint)
        await _reopen(db, conversation)

        with pytest.raises(CutoverRefusedError, match=successor.id):
            await cut_over(db, conversation, checkpoint)

        assert [c.id for c in await _successors(db)] == [successor.id]
        assert len(await _checkpoint_entries(db)) == 1


@pytest.mark.asyncio
async def test_a_second_checkpoint_cannot_hand_the_conversation_over_again(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        first = await _ready_checkpoint(db, conversation)
        successor, _ = await cut_over(db, conversation, first)
        await _reopen(db, conversation)
        second = await _ready_checkpoint(db, conversation)

        with pytest.raises(CutoverRefusedError) as refused:
            await cut_over(db, conversation, second)

        assert successor.id in str(refused.value) and first.id in str(refused.value)
        assert [c.id for c in await _successors(db)] == [successor.id]


@pytest.mark.asyncio
async def test_the_checkpoint_records_where_it_went(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        cut = await _ready_checkpoint(db, conversation)
        other = await _conversation(db, "conv-2")
        untouched = await _ready_checkpoint(db, other)
        successor, _ = await cut_over(db, conversation, cut)
        cut_id, untouched_id, successor_id = cut.id, untouched.id, successor.id

    async with async_session_factory() as fresh:
        cut_row = await get_checkpoint_by_id(fresh, cut_id)
        assert cut_row.cut_over_to_conversation_id == successor_id
        untouched_row = await get_checkpoint_by_id(fresh, untouched_id)
        assert untouched_row.cut_over_to_conversation_id is None


@pytest.mark.asyncio
async def test_a_chain_is_still_handed_over_hop_by_hop(app):
    """Control. The index is keyed on `conversation_id`, so P -> S1 -> S2 must not trip it."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        first = await _ready_checkpoint(db, conversation)
        s1, entry_id = await cut_over(db, conversation, first)

        run = Run(
            id="run-s1", project_id=PROJECT, agent=AGENT, conversation_id=s1.id, status="running"
        )
        await deliver_entries_with_run(
            db, project_id=PROJECT, agent=AGENT, entry_ids=[entry_id], run=run
        )
        run.status = "completed"
        await db.commit()
        second = await _ready_checkpoint(db, s1)
        s2, _ = await cut_over(db, s1, second)

        assert s1.title == "Continued: Wire up the worker"
        assert s2.title == s1.title
        assert {s1.lineage_id, s2.lineage_id, conversation.lineage_id} == {conversation.lineage_id}
        assert len(await _successors(db)) == 2


class _BarrierArchivable:
    """Stands in for `archivable` so both presses are inside `cut_over`, past every pre-check,
    before either writes. A barrier before the call let the second press's pre-check read the
    first's commit and refuse sequentially, so the compare-and-set never ran (design D3)."""

    def __init__(self, real):
        self.barrier = asyncio.Barrier(2)
        self.real = real

    async def __call__(self, db, conversation):
        await self.barrier.wait()
        return await self.real(db, conversation)


async def _race(monkeypatch, checkpoint_ids, conversation_id):
    from hub import checkpoint_cutover

    monkeypatch.setattr(
        "hub.checkpoint_cutover.archivable", _BarrierArchivable(checkpoint_cutover.archivable)
    )
    rollbacks = []

    async def press(checkpoint_id):
        async with async_session_factory() as db:
            conversation = await get_conversation_by_id(db, conversation_id)
            checkpoint = await get_checkpoint_by_id(db, checkpoint_id)
            real_rollback = db.rollback

            async def spy():
                rollbacks.append(checkpoint_id)
                await real_rollback()

            db.rollback = spy
            return await cut_over(db, conversation, checkpoint)

    results = await asyncio.gather(*(press(c) for c in checkpoint_ids), return_exceptions=True)
    return results, rollbacks


@pytest.mark.asyncio
async def test_two_simultaneous_presses_mint_one_successor(app, monkeypatch):
    """F294: two presses of one checkpoint each passed the archive guard, then each wrote."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        checkpoint_id = (await _ready_checkpoint(db, conversation)).id

    results, rollbacks = await _race(monkeypatch, [checkpoint_id, checkpoint_id], "conv-1")

    wins = [r for r in results if not isinstance(r, BaseException)]
    refusals = [r for r in results if isinstance(r, CutoverRefusedError)]
    assert len(wins) == 1 and len(refusals) == 1, results
    assert wins[0][0].id in str(refusals[0])
    assert len(rollbacks) == 1  # the loser went through the claim, not a pre-check
    async with async_session_factory() as db:
        assert [c.id for c in await _successors(db)] == [wins[0][0].id]
        assert len(await _checkpoint_entries(db)) == 1


@pytest.mark.asyncio
async def test_two_checkpoints_raced_mint_one_successor(app, monkeypatch):
    """D2's backstop: two *different* checkpoints of one conversation. Each row's compare-and-set
    succeeds, so only the partial unique index can refuse the second."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        ids = [(await _ready_checkpoint(db, conversation)).id for _ in range(2)]

    results, rollbacks = await _race(monkeypatch, ids, "conv-1")

    wins = [r for r in results if not isinstance(r, BaseException)]
    refusals = [r for r in results if isinstance(r, CutoverRefusedError)]
    assert len(wins) == 1 and len(refusals) == 1, results
    assert len(rollbacks) == 1
    async with async_session_factory() as db:
        assert len(await _successors(db)) == 1
        assert len(await _checkpoint_entries(db)) == 1
