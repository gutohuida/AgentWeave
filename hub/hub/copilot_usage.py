"""Per-run Copilot usage ledger (design D2 of a-copilot-run-shows-its-credits).

Copilot reports usage on two streams that cannot be merged by `AccountingSample.merged`'s
newer-overlays-older rule: per-call `assistant.usage` notifications (summed) and the
session-cumulative `session.usage_checkpoint` (last wins). `CopilotUsageLedger` accumulates
both over one run and `finish()` reduces them to a single `AccountingSample`. Stdlib-only, as
slice 1's D1 requires of adapter code: nothing here reaches the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .runner_events import AccountingSample
from .runner_parsing import _accounting_from_dimensions

logger = logging.getLogger(__name__)

# github.com/copilot/sessionEvent assistant.usage -> the normaliser's own dimension names
# (runner_parsing._accounting_from_dimensions), so the shared key lists stay untouched (D3).
_CALL_KEY_MAP = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cacheReadTokens": "cache_read_tokens",
    "cacheWriteTokens": "cache_write_tokens",
    "reasoningTokens": "reasoning_output_tokens",
}

# The session/prompt result's own usage object uses different spellings for the same things.
_RESULT_KEY_MAP = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cachedReadTokens": "cache_read_tokens",
    "cachedWriteTokens": "cache_write_tokens",
    "thoughtTokens": "reasoning_output_tokens",
    "totalTokens": "total_tokens",
}


def _mapped(data: Dict[str, Any], key_map: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for src, dst in key_map.items():
        if src in data:
            out[dst] = data[src]
    return out


def _nonneg_number(value: Any) -> Optional[float]:
    """As `_token_int` treats a bad token count: ignore bool, non-numeric and negative (D4)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return value


@dataclass
class _Call:
    dimensions: Dict[str, Any]
    model: Optional[str]
    total_tokens: int
    nano_aiu: Optional[float]


@dataclass
class _Checkpoint:
    nano_aiu: Optional[float]
    premium_requests: Optional[float]


@dataclass
class _Compaction:
    dimensions: Dict[str, Any]
    nano_aiu: Optional[float]
    request_id: Optional[str]


class CopilotUsageLedger:
    """One per `run_turn` call (D2). Stdlib-only."""

    def __init__(self) -> None:
        self._seen_call_ids: Set[str] = set()
        self._calls: List[_Call] = []
        self._compactions: List[_Compaction] = []
        self._checkpoint: Optional[_Checkpoint] = None
        self._prompt_result: Optional[Dict[str, Any]] = None

    def observe_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        if event_type == "assistant.usage":
            self._observe_call(data)
        elif event_type == "session.usage_checkpoint":
            self._checkpoint = _Checkpoint(
                nano_aiu=_nonneg_number(data.get("totalNanoAiu")),
                premium_requests=_nonneg_number(data.get("totalPremiumRequests")),
            )
        elif event_type == "session.compaction_complete":
            self._observe_compaction(data)

    def _observe_call(self, data: Dict[str, Any]) -> None:
        call_id = data.get("providerCallId") or data.get("apiCallId")
        if call_id is not None:
            if call_id in self._seen_call_ids:
                return
            self._seen_call_ids.add(call_id)
        dims = _mapped(data, _CALL_KEY_MAP)
        sample = _accounting_from_dimensions(dims, source="copilot_calls")
        total_tokens = sample.total_tokens if sample is not None else 0
        nano_aiu = None
        usage = data.get("copilotUsage")
        if isinstance(usage, dict):
            nano_aiu = _nonneg_number(usage.get("totalNanoAiu"))
        self._calls.append(
            _Call(
                dimensions=dims,
                model=data.get("model"),
                total_tokens=total_tokens or 0,
                nano_aiu=nano_aiu,
            )
        )

    def _observe_compaction(self, data: Dict[str, Any]) -> None:
        """A successful compaction's own `compactionTokensUsed` (D3). Kept separate from
        `_calls` and resolved against them in `_effective_calls` -- not here -- because whether
        a matching `assistant.usage` exists can only be known once every event has arrived
        (the compaction's own call, if Copilot emits one, may reach the ledger before or after
        this event; the dedup must be order-independent)."""
        compaction_tokens = data.get("compactionTokensUsed")
        if not isinstance(compaction_tokens, dict):
            return
        request_id = data.get("requestId") or data.get("serviceRequestId")
        dims = _mapped(compaction_tokens, _CALL_KEY_MAP)
        nano_aiu = None
        usage = compaction_tokens.get("copilotUsage")
        if isinstance(usage, dict):
            nano_aiu = _nonneg_number(usage.get("totalNanoAiu"))
        self._compactions.append(
            _Compaction(dimensions=dims, nano_aiu=nano_aiu, request_id=request_id)
        )

    def _effective_calls(self) -> List[_Call]:
        """`_calls` plus each compaction whose `requestId` matches no observed call's
        `providerCallId`/`apiCallId` (D3) -- a compaction that does match is already counted
        through that call, so it contributes nothing here."""
        calls = list(self._calls)
        for comp in self._compactions:
            if comp.request_id is not None and comp.request_id in self._seen_call_ids:
                continue
            sample = _accounting_from_dimensions(comp.dimensions, source="copilot_calls")
            total_tokens = sample.total_tokens if sample is not None else 0
            calls.append(
                _Call(
                    dimensions=comp.dimensions,
                    model=None,
                    total_tokens=total_tokens or 0,
                    nano_aiu=comp.nano_aiu,
                )
            )
        return calls

    def observe_prompt_result(self, usage: Optional[Dict[str, Any]]) -> None:
        if isinstance(usage, dict):
            self._prompt_result = usage  # last result in the process wins (D3)

    def _calls_sample(self) -> Optional[AccountingSample]:
        calls = self._effective_calls()
        if not calls:
            return None
        summed: Dict[str, int] = {}
        for call in calls:
            for key, value in call.dimensions.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    continue
                summed[key] = summed.get(key, 0) + int(value)
        model = max(calls, key=lambda c: c.total_tokens).model
        sample = _accounting_from_dimensions(summed, source="copilot_calls", model=model)
        return sample

    def _result_sample(self) -> Optional[AccountingSample]:
        if self._prompt_result is None:
            return None
        return _accounting_from_dimensions(
            _mapped(self._prompt_result, _RESULT_KEY_MAP), source="copilot_prompt_result"
        )

    def finish(self, *, session_was_new: bool) -> AccountingSample:
        calls_sample = self._calls_sample()
        result_sample = self._result_sample()

        calls_total = calls_sample.total_tokens if calls_sample is not None else None
        result_total = result_sample.total_tokens if result_sample is not None else None

        winner: AccountingSample
        if calls_total is None and result_total is None:
            winner = calls_sample or result_sample or AccountingSample(source="copilot_calls")
        elif result_total is None or (calls_total is not None and calls_total >= result_total):
            assert calls_sample is not None
            winner = calls_sample
        else:
            assert result_sample is not None
            winner = result_sample
            if calls_total is not None and result_total:
                disagreement = abs(calls_total - result_total) / result_total
                if disagreement > 0.01:
                    logger.warning(
                        "Copilot per-call sum (%s tokens) disagrees with the prompt result "
                        "(%s tokens) by %.1f%%",
                        calls_total,
                        result_total,
                        disagreement * 100,
                    )

        calls = self._effective_calls()
        model = None
        if calls:
            model = max(calls, key=lambda c: c.total_tokens).model

        per_call_nano_aiu: Optional[int] = None
        if calls:
            reported = [c.nano_aiu for c in calls if c.nano_aiu is not None]
            if reported:
                per_call_nano_aiu = int(sum(reported))

        session_nano_aiu_total: Optional[int] = (
            int(self._checkpoint.nano_aiu)
            if self._checkpoint and self._checkpoint.nano_aiu is not None
            else None
        )
        session_premium_requests_total = (
            self._checkpoint.premium_requests if self._checkpoint else None
        )
        provisional_nano_aiu = (
            session_nano_aiu_total if session_nano_aiu_total is not None else per_call_nano_aiu
        )
        provisional_premium_requests = session_premium_requests_total

        return AccountingSample(
            source=winner.source,
            input_tokens=winner.input_tokens,
            output_tokens=winner.output_tokens,
            total_tokens=winner.total_tokens,
            cache_read_tokens=winner.cache_read_tokens,
            cache_write_tokens=winner.cache_write_tokens,
            reasoning_tokens=winner.reasoning_tokens,
            model=model,
            ai_nano_aiu=provisional_nano_aiu,
            premium_requests=provisional_premium_requests,
            session_nano_aiu_total=session_nano_aiu_total,
            session_premium_requests_total=session_premium_requests_total,
            credit_session_new=session_was_new,
        )
