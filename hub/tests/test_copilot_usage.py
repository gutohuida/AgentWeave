"""Tests for hub.hub.copilot_usage.CopilotUsageLedger (a-copilot-run-shows-its-credits, group 1).

The fixture replays the acp4 transcript (archived
`openspec/changes/archive/2026-09-30-a-copilot-agent-runs-over-acp/evidence/
acp4-turn-mcp-shell-1.0.88.log`) in the order Copilot emitted it: three `assistant.usage`
notifications, one `session.usage_checkpoint`, then the `session/prompt` result's own `usage`.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

from hub.copilot_usage import CopilotUsageLedger
from hub.db.engine import async_session_factory
from hub.db.models import Project, Run
from hub.runner_events import AccountingSample
from hub.usage_accounting import record_turn_usage, settle_copilot_credits

MODEL = "mai-code-1.1-flash"


def acp4_events() -> Tuple[List[Tuple[str, Dict[str, Any]]], Dict[str, Any]]:
    """Returns (raw_events, prompt_result_usage) in the order Copilot emitted them."""

    def call(
        provider_call_id: str, input_tokens: int, output_tokens: int, cache_read: int, nano_aiu: int
    ) -> Dict[str, Any]:
        return {
            "model": MODEL,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadTokens": cache_read,
            "cacheWriteTokens": 0,
            "reasoningTokens": 0,
            "providerCallId": provider_call_id,
            "copilotUsage": {"totalNanoAiu": nano_aiu},
        }

    events: List[Tuple[str, Dict[str, Any]]] = [
        ("assistant.usage", call("C3D0:1ACB84:95A88E:CFC8BD:6AB95457", 10988, 21, 0, 222280000)),
        ("assistant.usage", call("C3D0:1ACB84:95ABB8:CFCD4F:6AB9545A", 11028, 38, 10880, 29280000)),
        ("assistant.usage", call("C3D0:1ACB84:95B065:CFD3AD:6AB9545C", 11092, 5, 11008, 24296000)),
        (
            "session.usage_checkpoint",
            {"totalNanoAiu": 275856000, "totalPremiumRequests": 1},
        ),
    ]
    prompt_result_usage = {
        "inputTokens": 33108,
        "outputTokens": 64,
        "totalTokens": 33172,
        "thoughtTokens": 0,
        "cachedReadTokens": 21888,
        "cachedWriteTokens": 0,
    }
    return events, prompt_result_usage


def test_acp4_calls_and_checkpoint_give_tokens_and_provisional_credits() -> None:
    events, prompt_result_usage = acp4_events()
    ledger = CopilotUsageLedger()
    for event_type, data in events:
        ledger.observe_event(event_type, data)
    ledger.observe_prompt_result(prompt_result_usage)

    sample = ledger.finish(session_was_new=True)

    assert sample.input_tokens == 33108
    assert sample.output_tokens == 64
    assert sample.total_tokens == 33172
    assert sample.cache_read_tokens == 21888
    assert sample.reasoning_tokens == 0
    assert sample.model == MODEL
    assert sample.ai_nano_aiu == 275856000
    assert sample.premium_requests == 1.0
    assert sample.session_nano_aiu_total == 275856000
    assert sample.session_premium_requests_total == 1.0
    # The calls and the prompt result tie at 33172 tokens; a tie goes to the calls (D3).
    assert sample.source == "copilot_calls"


def test_sum_is_not_doubled_whichever_side_arrives_first() -> None:
    events, prompt_result_usage = acp4_events()

    events_first = CopilotUsageLedger()
    for event_type, data in events:
        events_first.observe_event(event_type, data)
    events_first.observe_prompt_result(prompt_result_usage)
    sample_events_first = events_first.finish(session_was_new=True)

    result_first = CopilotUsageLedger()
    result_first.observe_prompt_result(prompt_result_usage)
    for event_type, data in events:
        result_first.observe_event(event_type, data)
    sample_result_first = result_first.finish(session_was_new=True)

    for sample in (sample_events_first, sample_result_first):
        assert sample.total_tokens == 33172
        assert sample.total_tokens != 66344


def test_dropped_calls_fall_back_to_the_prompt_result(caplog: Any) -> None:
    events, prompt_result_usage = acp4_events()
    call_events = [(t, d) for t, d in events if t == "assistant.usage"]

    ledger = CopilotUsageLedger()
    ledger.observe_event(*call_events[0])  # call 1
    ledger.observe_event(*call_events[2])  # call 3; call 2 dropped
    ledger.observe_prompt_result(prompt_result_usage)

    with caplog.at_level(logging.WARNING):
        sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == 33172
    assert sample.source == "copilot_prompt_result"
    assert sample.cache_read_tokens == 21888
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("22106" in w and "33172" in w for w in warnings)


def test_second_prompt_result_replaces_the_first_not_summed() -> None:
    events, first_result = acp4_events()
    second_result = {
        "inputTokens": 39900,
        "outputTokens": 76,
        "totalTokens": 40000,
        "thoughtTokens": 0,
        "cachedReadTokens": 26000,
        "cachedWriteTokens": 0,
    }

    ledger = CopilotUsageLedger()
    for event_type, data in events:
        ledger.observe_event(event_type, data)
    ledger.observe_prompt_result(first_result)
    ledger.observe_prompt_result(second_result)

    sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == 40000
    assert sample.total_tokens != 73172
    assert sample.source == "copilot_prompt_result"


def test_subagent_call_counted_once_and_duplicate_notification_deduped() -> None:
    events, _ = acp4_events()
    top_call = next(
        d for t, d in events if t == "assistant.usage"
    )  # call 1: 10988/21/0, nano 222280000

    subagent_call = {
        "model": MODEL,
        "inputTokens": 500,
        "outputTokens": 10,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "reasoningTokens": 0,
        "providerCallId": "SUBAGENT:0001",
        "parentToolCallId": "TOOL:0001",
        "initiator": "sub-agent",
        "copilotUsage": {"totalNanoAiu": 5000000},
    }

    ledger = CopilotUsageLedger()
    ledger.observe_event("assistant.usage", top_call)
    ledger.observe_event("assistant.usage", subagent_call)
    # A repeated notification with the same providerCallId: counted once, not twice.
    ledger.observe_event("assistant.usage", dict(subagent_call))

    sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == 11009 + 510
    assert sample.ai_nano_aiu == 222280000 + 5000000


def _compaction_event(
    request_id: str, input_tokens: int, output_tokens: int, cache_read: int, nano_aiu: int
) -> Dict[str, Any]:
    return {
        "requestId": request_id,
        "compactionTokensUsed": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadTokens": cache_read,
            "copilotUsage": {"totalNanoAiu": nano_aiu},
        },
    }


def test_compaction_adds_its_tokens_and_nano_aiu_when_no_call_shares_its_request_id() -> None:
    top_call = {
        "model": MODEL,
        "inputTokens": 10988,
        "outputTokens": 21,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "reasoningTokens": 0,
        "providerCallId": "C3D0:1ACB84:95A88E:CFC8BD:6AB95457",
        "copilotUsage": {"totalNanoAiu": 222280000},
    }

    ledger = CopilotUsageLedger()
    ledger.observe_event("assistant.usage", top_call)
    ledger.observe_event(
        "session.compaction_complete", _compaction_event("COMPACT:0001", 2000, 50, 100, 40000000)
    )

    sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == (10988 + 21) + (2000 + 50)
    assert sample.ai_nano_aiu == 222280000 + 40000000


def test_compaction_adds_nothing_when_a_call_shares_its_request_id() -> None:
    shared_id = "C3D0:1ACB84:95A88E:CFC8BD:6AB95457"
    top_call = {
        "model": MODEL,
        "inputTokens": 10988,
        "outputTokens": 21,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "reasoningTokens": 0,
        "providerCallId": shared_id,
        "copilotUsage": {"totalNanoAiu": 222280000},
    }

    ledger = CopilotUsageLedger()
    ledger.observe_event("assistant.usage", top_call)
    ledger.observe_event(
        "session.compaction_complete", _compaction_event(shared_id, 2000, 50, 100, 40000000)
    )

    sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == 10988 + 21
    assert sample.ai_nano_aiu == 222280000

    # And in the other order: the compaction arrives first, the matching call second.
    ledger_reversed = CopilotUsageLedger()
    ledger_reversed.observe_event(
        "session.compaction_complete", _compaction_event(shared_id, 2000, 50, 100, 40000000)
    )
    ledger_reversed.observe_event("assistant.usage", top_call)

    sample_reversed = ledger_reversed.finish(session_was_new=True)

    assert sample_reversed.total_tokens == 10988 + 21
    assert sample_reversed.ai_nano_aiu == 222280000


def test_all_calls_with_no_prompt_result_uses_the_calls() -> None:
    events, _ = acp4_events()
    call_events = [(t, d) for t, d in events if t == "assistant.usage"]

    ledger = CopilotUsageLedger()
    for event_type, data in call_events:
        ledger.observe_event(event_type, data)

    sample = ledger.finish(session_was_new=True)

    assert sample.total_tokens == 33172
    assert sample.source == "copilot_calls"


def test_second_usage_checkpoint_replaces_the_first() -> None:
    first = {"totalNanoAiu": 100000000, "totalPremiumRequests": 0}
    second = {"totalNanoAiu": 275856000, "totalPremiumRequests": 1}

    in_order = CopilotUsageLedger()
    in_order.observe_event("session.usage_checkpoint", first)
    in_order.observe_event("session.usage_checkpoint", second)
    sample_in_order = in_order.finish(session_was_new=True)

    assert sample_in_order.session_nano_aiu_total == 275856000
    assert sample_in_order.session_premium_requests_total == 1.0

    reversed_order = CopilotUsageLedger()
    reversed_order.observe_event("session.usage_checkpoint", second)
    reversed_order.observe_event("session.usage_checkpoint", first)
    sample_reversed_order = reversed_order.finish(session_was_new=True)

    assert sample_reversed_order.session_nano_aiu_total == 100000000
    assert sample_reversed_order.session_premium_requests_total == 0.0


# --- Task 1.8: credits (design D4, R3's larger-of rule) --------------------------------------
#
# `settle_copilot_credits` reads its baseline from a seeded `turn_usage`/`runs` row, so these
# cases go through a real database session rather than the ledger alone.


def _ledger_with_one_call(
    nano_aiu: int, *, checkpoint: Optional[Tuple[int, float]] = None
) -> CopilotUsageLedger:
    ledger = CopilotUsageLedger()
    ledger.observe_event(
        "assistant.usage",
        {
            "model": MODEL,
            "inputTokens": 100,
            "outputTokens": 10,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "reasoningTokens": 0,
            "providerCallId": f"CALL:{nano_aiu}",
            "copilotUsage": {"totalNanoAiu": nano_aiu},
        },
    )
    if checkpoint is not None:
        total, premium = checkpoint
        ledger.observe_event(
            "session.usage_checkpoint", {"totalNanoAiu": total, "totalPremiumRequests": premium}
        )
    return ledger


async def _seed_baseline_row(
    session: Any,
    *,
    project_id: str,
    run_id: str,
    agent: str,
    session_id: str,
    nano_aiu_total: Optional[int],
    premium_total: Optional[float],
) -> None:
    """A prior run's stored session totals -- the next run's baseline (design D4)."""
    if await session.get(Project, project_id) is None:
        session.add(Project(id=project_id, name=project_id))
        await session.flush()
    session.add(Run(id=run_id, project_id=project_id, agent=agent, session_id=session_id))
    await session.flush()
    await record_turn_usage(
        session,
        run_id=run_id,
        project_id=project_id,
        agent=agent,
        runner="copilot",
        sample=AccountingSample(
            source="copilot_calls",
            session_nano_aiu_total=nano_aiu_total,
            session_premium_requests_total=premium_total,
        ),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_credits_loaded_run_charged_the_checkpoint_difference(app: Any) -> None:
    # (a) loaded, baseline 275856000/1, checkpoint 400000000/2, one call of 124144000 gives
    # 124144000 and premium 1.0, and stores 400000000/2.
    project_id, agent, session_id = "proj-credits-a", "copilot", "sess-credits-a"
    async with async_session_factory() as session:
        await _seed_baseline_row(
            session,
            project_id=project_id,
            run_id="run-credits-a-0",
            agent=agent,
            session_id=session_id,
            nano_aiu_total=275856000,
            premium_total=1.0,
        )
        session.add(
            Run(id="run-credits-a-1", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()

        sample = _ledger_with_one_call(124144000, checkpoint=(400000000, 2)).finish(
            session_was_new=False
        )
        settled = await settle_copilot_credits(
            session, sample, project_id=project_id, agent=agent, session_id=session_id
        )

    assert settled is not None
    assert settled.ai_nano_aiu == 124144000
    assert settled.premium_requests == 1.0
    assert settled.session_nano_aiu_total == 400000000
    assert settled.session_premium_requests_total == 2.0


@pytest.mark.asyncio
async def test_credits_loaded_run_with_no_baseline_falls_back_to_the_calls(app: Any) -> None:
    # (b) loaded with no baseline, the acp4 calls (275856000), checkpoint 400000000/2 gives
    # 275856000 and `premium_requests is None`, and stores 400000000/2.
    project_id, agent, session_id = "proj-credits-b", "copilot", "sess-credits-b"
    events, _ = acp4_events()
    ledger = CopilotUsageLedger()
    for event_type, data in events:
        if event_type == "assistant.usage":
            ledger.observe_event(event_type, data)
    ledger.observe_event(
        "session.usage_checkpoint", {"totalNanoAiu": 400000000, "totalPremiumRequests": 2}
    )
    sample = ledger.finish(session_was_new=False)

    async with async_session_factory() as session:
        session.add(Project(id=project_id, name=project_id))
        await session.flush()
        session.add(
            Run(id="run-credits-b-0", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()
        settled = await settle_copilot_credits(
            session, sample, project_id=project_id, agent=agent, session_id=session_id
        )

    assert settled is not None
    assert settled.ai_nano_aiu == 275856000
    assert settled.premium_requests is None
    assert settled.session_nano_aiu_total == 400000000
    assert settled.session_premium_requests_total == 2.0


@pytest.mark.asyncio
async def test_credits_counter_reset_falls_back_to_the_calls_not_none(app: Any) -> None:
    # (c) counter reset: baseline 275856000/1, checkpoint 124144000/1, one call of 124144000
    # gives 124144000 (not None, R2's rule), `premium_requests is None`, and stores 124144000/1.
    project_id, agent, session_id = "proj-credits-c", "copilot", "sess-credits-c"
    async with async_session_factory() as session:
        await _seed_baseline_row(
            session,
            project_id=project_id,
            run_id="run-credits-c-0",
            agent=agent,
            session_id=session_id,
            nano_aiu_total=275856000,
            premium_total=1.0,
        )
        session.add(
            Run(id="run-credits-c-1", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()

        sample = _ledger_with_one_call(124144000, checkpoint=(124144000, 1)).finish(
            session_was_new=False
        )
        settled = await settle_copilot_credits(
            session, sample, project_id=project_id, agent=agent, session_id=session_id
        )

    assert settled is not None
    assert settled.ai_nano_aiu == 124144000
    assert settled.premium_requests is None
    assert settled.session_nano_aiu_total == 124144000
    assert settled.session_premium_requests_total == 1.0


@pytest.mark.asyncio
async def test_credits_counter_restarted_per_process_uses_the_larger_call_sum(app: Any) -> None:
    # (d) counter restarted per process: baseline 100000000/1, checkpoint 124144000/1, one call
    # of 124144000 gives 124144000, not the difference 24144000, and `premium_requests is None`.
    project_id, agent, session_id = "proj-credits-d", "copilot", "sess-credits-d"
    async with async_session_factory() as session:
        await _seed_baseline_row(
            session,
            project_id=project_id,
            run_id="run-credits-d-0",
            agent=agent,
            session_id=session_id,
            nano_aiu_total=100000000,
            premium_total=1.0,
        )
        session.add(
            Run(id="run-credits-d-1", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()

        sample = _ledger_with_one_call(124144000, checkpoint=(124144000, 1)).finish(
            session_was_new=False
        )
        settled = await settle_copilot_credits(
            session, sample, project_id=project_id, agent=agent, session_id=session_id
        )

    assert settled is not None
    assert settled.ai_nano_aiu == 124144000
    assert settled.ai_nano_aiu != 24144000
    assert settled.premium_requests is None


@pytest.mark.asyncio
async def test_credits_fallback_stores_what_it_charged(app: Any) -> None:
    # (e) the fallback stores what it charged: a new-session run with the acp4 calls and no
    # checkpoint records 275856000 and session_nano_aiu_total == 275856000,
    # session_premium_requests_total is None. The following loaded run, checkpoint 400000000/2
    # and one call of 124144000, is charged 124144000 with premium_requests is None. This fails
    # if the fallback stores nothing.
    project_id, agent, session_id = "proj-credits-e", "copilot", "sess-credits-e"
    events, _ = acp4_events()
    call_events = [(t, d) for t, d in events if t == "assistant.usage"]

    async with async_session_factory() as session:
        session.add(Project(id=project_id, name=project_id))
        await session.flush()

        session.add(
            Run(id="run-credits-e-1", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()
        ledger1 = CopilotUsageLedger()
        for event_type, data in call_events:
            ledger1.observe_event(event_type, data)
        sample1 = ledger1.finish(session_was_new=True)
        settled1 = await settle_copilot_credits(
            session, sample1, project_id=project_id, agent=agent, session_id=session_id
        )
        assert settled1 is not None
        assert settled1.ai_nano_aiu == 275856000
        assert settled1.session_nano_aiu_total == 275856000
        assert settled1.session_premium_requests_total is None
        await record_turn_usage(
            session,
            run_id="run-credits-e-1",
            project_id=project_id,
            agent=agent,
            runner="copilot",
            sample=settled1,
        )
        await session.commit()

        session.add(
            Run(id="run-credits-e-2", project_id=project_id, agent=agent, session_id=session_id)
        )
        await session.flush()
        sample2 = _ledger_with_one_call(124144000, checkpoint=(400000000, 2)).finish(
            session_was_new=False
        )
        settled2 = await settle_copilot_credits(
            session, sample2, project_id=project_id, agent=agent, session_id=session_id
        )

    assert settled2 is not None
    assert settled2.ai_nano_aiu == 124144000
    assert settled2.premium_requests is None


@pytest.mark.asyncio
async def test_credits_settled_as_a_no_op_rather_than_skipped(app: Any) -> None:
    # (f) a run whose sample has `credit_session_new` set but no checkpoint and no calls is
    # settled (a no-op on credits) rather than skipped. A sample without `credit_session_new` is
    # returned unchanged. No events at all gives `total_tokens is None`.
    empty_sample = CopilotUsageLedger().finish(session_was_new=True)
    assert empty_sample.total_tokens is None
    assert empty_sample.credit_session_new is True

    async with async_session_factory() as session:
        settled = await settle_copilot_credits(
            session,
            empty_sample,
            project_id="proj-credits-f",
            agent="copilot",
            session_id="sess-credits-f",
        )
        # Settled, not skipped: a fresh object comes back, even though nothing changed.
        assert settled is not empty_sample
        assert settled.ai_nano_aiu is None
        assert settled.session_nano_aiu_total is None

        non_copilot_sample = AccountingSample(source="claude_api", total_tokens=500)
        assert non_copilot_sample.credit_session_new is None
        unchanged = await settle_copilot_credits(
            session,
            non_copilot_sample,
            project_id="proj-credits-f",
            agent="claude",
            session_id="sess-credits-f",
        )
        assert unchanged is non_copilot_sample


@pytest.mark.asyncio
async def test_credits_ignore_a_negative_per_call_value(app: Any) -> None:
    # (g) (review finding 12) the acp4 calls plus one call whose `totalNanoAiu` is -5000000 give
    # 275856000: the negative value is ignored.
    events, _ = acp4_events()
    ledger = CopilotUsageLedger()
    for event_type, data in events:
        if event_type == "assistant.usage":
            ledger.observe_event(event_type, data)
    ledger.observe_event(
        "assistant.usage",
        {
            "model": MODEL,
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "reasoningTokens": 0,
            "providerCallId": "NEGATIVE:0001",
            "copilotUsage": {"totalNanoAiu": -5000000},
        },
    )
    sample = ledger.finish(session_was_new=True)

    async with async_session_factory() as session:
        settled = await settle_copilot_credits(
            session,
            sample,
            project_id="proj-credits-g",
            agent="copilot",
            session_id="sess-credits-g",
        )

    assert settled is not None
    assert settled.ai_nano_aiu == 275856000


@pytest.mark.asyncio
async def test_credits_baseline_uses_insertion_order_not_a_clock_stepping_backwards(
    app: Any,
) -> None:
    # (h) (review finding 3) a clock that steps backwards: four runs of one session (the first
    # new, the rest loaded), spending 275856000, 124144000, 100000000 and 50000000 through their
    # checkpoints (each with its own calls), recorded in that order with `observed_at` 10, 20, 10
    # and 15 seconds past a fixed instant. Run 4 is charged 50000000 and the four sum to
    # 550000000. Ordered by `observed_at`, run 4 would be charged 150000000 against run 2's
    # total, so this fails on the R3 rule.
    project_id, agent, session_id = "proj-credits-h", "copilot", "sess-credits-h"
    spends = [275856000, 124144000, 100000000, 50000000]
    offsets = [10, 20, 10, 15]
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    charges: List[Optional[int]] = []

    async with async_session_factory() as session:
        session.add(Project(id=project_id, name=project_id))
        await session.flush()

        cumulative = 0
        for index, (spend, offset) in enumerate(zip(spends, offsets, strict=True), start=1):
            cumulative += spend
            run_id = f"run-credits-h-{index}"
            session.add(Run(id=run_id, project_id=project_id, agent=agent, session_id=session_id))
            await session.flush()

            sample = _ledger_with_one_call(spend, checkpoint=(cumulative, 0)).finish(
                session_was_new=(index == 1)
            )
            settled = await settle_copilot_credits(
                session, sample, project_id=project_id, agent=agent, session_id=session_id
            )
            assert settled is not None
            charges.append(settled.ai_nano_aiu)

            row = await record_turn_usage(
                session,
                run_id=run_id,
                project_id=project_id,
                agent=agent,
                runner="copilot",
                sample=settled,
            )
            row.observed_at = base + timedelta(seconds=offset)
            await session.commit()

    assert charges[3] == 50000000
    assert sum(c or 0 for c in charges) == 550000000
