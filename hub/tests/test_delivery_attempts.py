"""A failed run cannot wedge its agent forever.

The loop-7 run hit this and could not get out of it without reaching past the product. A Codex
app-server died mid-turn; the run's queue entry went back to `queued`, keeping both its place in
arrival order and its binding to the conversation it arrived on. The scheduler adopts the oldest
queued entry's conversation for the turn, so that entry was served again immediately — and because
its conversation's provider session could not be resumed, the runtime died again. Four entries
stacked up and four consecutive runs failed. A request for a *fresh* conversation could not get
through either: it queued behind the entry that was doing the killing.

Nothing in the record distinguished an entry returned four times from one never tried.

The fix is two counts. At `RESUME_RETRY_LIMIT` the conversation gives up its provider session, so
the next delivery starts a new one — that is what actually breaks the loop. At
`DELIVERY_ATTEMPT_LIMIT` the Hub gives up on the entry and says so, because retrying without limit
is indistinguishable from being stuck.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run
from hub.inbound_queue import (
    DELIVERY_ATTEMPT_LIMIT,
    RESUME_RETRY_LIMIT,
    abandoned_for_run,
    deliver_entries_with_run,
    new_entry,
    queued_entries,
    return_run_entries,
)

AGENT = "wedge-target"


async def make_conversation(db, conversation_id="conv-wedge", provider_session_id="thread-dead"):
    conversation = Conversation(
        id=conversation_id,
        project_id="proj-test",
        agent=AGENT,
        title="Wedged",
        provider_session_id=provider_session_id,
    )
    db.add(conversation)
    await db.commit()
    return conversation


async def queue_one(db, *, conversation_id="conv-wedge", content="do the thing"):
    entry = new_entry(
        project_id="proj-test",
        agent=AGENT,
        origin_type="operator",
        content=content,
        hop_depth=0,
        conversation_id=conversation_id,
    )
    db.add(entry)
    await db.commit()
    return entry


async def fail_a_delivery(db, entry, run_id):
    """Deliver *entry* into a run, then fail that run — one full failed attempt."""
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=AGENT,
        status="running",
        turn_depth=0,
        conversation_id=entry.conversation_id,
    )
    await deliver_entries_with_run(
        db, project_id="proj-test", agent=AGENT, entry_ids=[entry.id], run=run
    )
    requeued = await return_run_entries(db, run_id)
    await db.commit()
    return requeued


@pytest.mark.asyncio
async def test_a_returned_entry_counts_the_attempt(app):
    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)

        assert await fail_a_delivery(db, entry, "run-w1") == [entry.id]
        await db.refresh(entry)
        assert entry.delivery_attempts == 1
        assert entry.state == "queued", "one failure must not lose the operator's message"


@pytest.mark.asyncio
async def test_the_second_failure_clears_the_conversations_provider_session(app):
    """The one change that actually breaks the loop.

    Resuming a dead provider thread is what kills the runtime, so the entry stays and the *session*
    is what gets given up on. Not on the first failure: a single one is routinely a Hub restart,
    and discarding a live session costs the agent its whole provider-side context.
    """
    async with async_session_factory() as db:
        conversation = await make_conversation(db)
        entry = await queue_one(db)

        await fail_a_delivery(db, entry, "run-w1")
        await db.refresh(conversation)
        assert conversation.provider_session_id == "thread-dead", "one failure is not enough"

        await fail_a_delivery(db, entry, "run-w2")
        await db.refresh(conversation)
        assert conversation.provider_session_id is None
        assert entry.delivery_attempts == RESUME_RETRY_LIMIT


@pytest.mark.asyncio
async def test_the_next_delivery_after_a_reset_starts_a_new_session(app):
    """`session_mode` is derived from whether the conversation holds a provider session.

    Clearing it is therefore not a flag anything has to read — the next turn simply starts fresh,
    and binds whatever session it gets.
    """
    async with async_session_factory() as db:
        conversation = await make_conversation(db)
        entry = await queue_one(db)

        for index in range(RESUME_RETRY_LIMIT):
            await fail_a_delivery(db, entry, f"run-reset-{index}")

        await db.refresh(conversation)
        resume_session_id = conversation.provider_session_id
        session_mode = "resume" if resume_session_id else "new"
        assert session_mode == "new"


@pytest.mark.asyncio
async def test_the_third_failure_abandons_the_entry_with_a_reason(app):
    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)

        for index in range(DELIVERY_ATTEMPT_LIMIT - 1):
            assert await fail_a_delivery(db, entry, f"run-a{index}") == [entry.id]

        assert await fail_a_delivery(db, entry, "run-final") == [], "no longer requeued"
        await db.refresh(entry)
        assert entry.state == "withdrawn"
        assert entry.delivery_attempts == DELIVERY_ATTEMPT_LIMIT
        assert "stopped retrying" in (entry.abandoned_reason or "")
        assert entry.withdrawn_at is not None


@pytest.mark.asyncio
async def test_an_abandoned_entry_stops_controlling_the_queue(app):
    """The wedge, and its release.

    While the poisoned entry is queued it is the oldest, so the scheduler adopts *its* conversation
    and everything else waits — which is why a fresh conversation could not get through. Once it is
    abandoned, the next input is the oldest and runs.
    """
    async with async_session_factory() as db:
        await make_conversation(db)
        poisoned = await queue_one(db, content="the one that kills the runtime")
        later = await queue_one(
            db, conversation_id=None, content="a fresh conversation's first message"
        )

        waiting = await queued_entries(db, "proj-test", AGENT)
        assert waiting[0].id == poisoned.id, "the poisoned entry is the one being served"

        for index in range(DELIVERY_ATTEMPT_LIMIT):
            await fail_a_delivery(db, poisoned, f"run-b{index}")

        waiting = await queued_entries(db, "proj-test", AGENT)
        assert [row.id for row in waiting] == [later.id], "the queue moves on"


@pytest.mark.asyncio
async def test_an_abandoned_entry_keeps_the_run_that_ate_it(app):
    """The operator's breadcrumb from a dropped message to what happened to it."""
    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)
        for index in range(DELIVERY_ATTEMPT_LIMIT):
            await fail_a_delivery(db, entry, f"run-c{index}")

        await db.refresh(entry)
        assert entry.delivered_in_run_id == f"run-c{DELIVERY_ATTEMPT_LIMIT - 1}"
        assert entry.conversation_id == "conv-wedge", "clearing it would make it unschedulable"

        abandoned = await abandoned_for_run(db, f"run-c{DELIVERY_ATTEMPT_LIMIT - 1}")
        assert [row.id for row in abandoned] == [entry.id]


@pytest.mark.asyncio
async def test_an_operator_withdrawal_is_not_reported_as_abandoned(app):
    """Both end `withdrawn`; the reason is what tells them apart.

    Reusing the state rather than adding a fourth is deliberate — it is CHECK-constrained, and
    rewriting that on SQLite means rebuilding the table whose `sequence` orders the whole queue.
    """
    from hub.inbound_queue import withdraw_entry

    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)
        withdrawn = await withdraw_entry(db, "proj-test", entry.id)

        assert withdrawn is not None
        assert withdrawn.state == "withdrawn"
        assert withdrawn.abandoned_reason is None
        assert await abandoned_for_run(db, "run-anything") == []


@pytest.mark.asyncio
async def test_return_run_entries_still_returns_only_requeued_ids(app):
    """Pins the preserved surface.

    Callers branch on this list — `run_reconciliation` skips a divergence when work went back to
    the queue — so an abandoned id appearing here would tell them work is coming that never is.
    """
    async with async_session_factory() as db:
        await make_conversation(db)
        first = await queue_one(db, content="one")
        second = await queue_one(db, content="two")

        run = Run(
            id="run-both",
            project_id="proj-test",
            agent=AGENT,
            status="running",
            turn_depth=0,
            conversation_id="conv-wedge",
        )
        await deliver_entries_with_run(
            db,
            project_id="proj-test",
            agent=AGENT,
            entry_ids=[first.id, second.id],
            run=run,
        )
        # Push only the first past the limit before this delivery's failure counts them both.
        first.delivery_attempts = DELIVERY_ATTEMPT_LIMIT - 1
        await db.commit()

        requeued = await return_run_entries(db, "run-both")
        await db.commit()

        assert requeued == [second.id], "the abandoned id must not be reported as coming back"


@pytest.mark.asyncio
async def test_queue_status_reports_attempts_only_when_nothing_else_explains_the_wait(
    app, auth_headers
):
    """Every existing reason explains the wait better than a retry count does.

    A missing CLI is the answer; "delivery failed twice" merely describes the symptom. This fires
    only when nothing else did — the case that used to show "1 waiting" and no explanation at all.
    """
    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)
        await fail_a_delivery(db, entry, "run-status")

    status = await app.get(f"/api/v1/projects/proj-test/queue/{AGENT}/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["delivery_attempts"] == 1
    assert body["waiting_count"] == 1
    # The agent is not launchable in the test environment, and that remains the better answer.
    assert body["waiting_reason"] is not None


@pytest.mark.asyncio
async def test_the_entry_list_exposes_attempts_and_the_reason(app, auth_headers):
    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)
        for index in range(DELIVERY_ATTEMPT_LIMIT):
            await fail_a_delivery(db, entry, f"run-d{index}")

    listed = await app.get(
        f"/api/v1/projects/proj-test/queue/{AGENT}?state=withdrawn", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["delivery_attempts"] == DELIVERY_ATTEMPT_LIMIT
    assert "stopped retrying" in rows[0]["abandoned_reason"]


@pytest.mark.asyncio
async def test_abandonment_persists_an_operator_visible_event(app):
    """A message dropped silently is worse than one dropped loudly."""
    from hub.api.v1.agent_trigger import _report_abandoned_entries
    from hub.db.models import EventLog

    async with async_session_factory() as db:
        await make_conversation(db)
        entry = await queue_one(db)
        for index in range(DELIVERY_ATTEMPT_LIMIT):
            await fail_a_delivery(db, entry, f"run-e{index}")

        await _report_abandoned_entries(
            db, "proj-test", AGENT, f"run-e{DELIVERY_ATTEMPT_LIMIT - 1}"
        )

        events = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "queue_entry_abandoned")
                )
            )
            .scalars()
            .all()
        )

    assert len(events) == 1
    assert events[0].severity == "warn"
    assert events[0].data["entry_id"] == entry.id
    assert events[0].data["attempts"] == DELIVERY_ATTEMPT_LIMIT
