"""Tests for hub.hub.copilot_usage.CopilotUsageLedger (a-copilot-run-shows-its-credits, group 1).

The fixture replays the acp4 transcript (archived
`openspec/changes/archive/2026-09-30-a-copilot-agent-runs-over-acp/evidence/
acp4-turn-mcp-shell-1.0.88.log`) in the order Copilot emitted it: three `assistant.usage`
notifications, one `session.usage_checkpoint`, then the `session/prompt` result's own `usage`.
"""

from typing import Any, Dict, List, Tuple

from hub.copilot_usage import CopilotUsageLedger

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
