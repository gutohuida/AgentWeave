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
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from .runner_events import AccountingSample
from .runner_parsing import _accounting_from_dimensions

logger = logging.getLogger(__name__)

# D7: snapshot keys that never gate credits, excluded before the lowest-remaining pick.
_EXCLUDED_QUOTA_KEYS = {"completions"}

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


#: The plausibility ceiling `checkpoint_totals` applies to both figures
#: (`a-copilot-one-shot-records-its-credits` D2). A row's own `BigInteger` columns hold `2**63 - 1`,
#: but `func.sum` over many rows overflows SQLite past `2**53 - 1`'s margin on only 1025 rows at
#: the ceiling -- the plausibility bound, not the column's own size, is what a single malformed
#: checkpoint must be held to.
_CHECKPOINT_CEILING = 2**53 - 1


def checkpoint_totals(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """(totalNanoAiu, totalPremiumRequests) of one `session.usage_checkpoint`, each through
    `_nonneg_number`, then refused (None) unless `value <= 2**53 - 1` (the review's plausibility
    ceiling, one constant for both figures). The comparison is the whole check: it is False
    for NaN and both infinities, and it never raises."""
    nano = _nonneg_number(data.get("totalNanoAiu"))
    if nano is not None and not nano <= _CHECKPOINT_CEILING:
        nano = None
    premium = _nonneg_number(data.get("totalPremiumRequests"))
    if premium is not None and not premium <= _CHECKPOINT_CEILING:
        premium = None
    return nano, premium


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


def _qualifying_snapshot(snapshots: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """D7: among *snapshots*, the lowest-`remainingPercentage` entry that is not `completions`,
    not an unlimited entitlement, and not already exhausted of entitlement (0 or fewer
    requests, as `premium_interactions` is on a Free account). None when nothing qualifies."""
    if not isinstance(snapshots, dict):
        return None
    best: Optional[Tuple[str, Dict[str, Any]]] = None
    best_remaining: Optional[float] = None
    for key, value in snapshots.items():
        if key in _EXCLUDED_QUOTA_KEYS or not isinstance(value, dict):
            continue
        if value.get("isUnlimitedEntitlement") is True:
            continue
        entitlement = value.get("entitlementRequests")
        if isinstance(entitlement, bool) or not isinstance(entitlement, (int, float)):
            continue
        if entitlement <= 0:
            continue
        remaining = value.get("remainingPercentage")
        if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
            continue
        if best_remaining is None or remaining < best_remaining:
            best, best_remaining = (key, value), remaining
    return best


def _resets_at_from(value: Dict[str, Any]) -> Optional[int]:
    """D7: `resetDate` as epoch seconds. No `resetDate`, no `resetsAt`."""
    reset_date = value.get("resetDate")
    if not isinstance(reset_date, str):
        return None
    try:
        parsed = datetime.fromisoformat(reset_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp())


def quota_reading(
    snapshots: Any,
    *,
    refused: bool,
    prior_reading: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """D7/D8: the allowance reading one Copilot run writes. Pure, stdlib-only (D2) -- this run's
    own qualifying snapshot, if any, plus (only when `refused`, review finding 2) `resetsAt`
    alone from `prior_reading`, when this run's own snapshot named none. A run that was not
    refused and saw no qualifying snapshot writes no reading at all, whatever `prior_reading`
    says (review finding 2): otherwise an ordinary non-quota failure after a hold would re-emit
    the earlier `rejected` reading and renew it.
    """
    qualifying = _qualifying_snapshot(snapshots)
    if qualifying is None and not refused:
        return None

    reading: Dict[str, Any] = {
        "status": "rejected" if refused else "allowed",
        "rateLimitType": "monthly",
        "provider": "copilot",
    }
    if qualifying is not None:
        key, value = qualifying
        reading["quota"] = key
        remaining = value.get("remainingPercentage")
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
            reading["remainingPercentage"] = remaining
        resets_at = _resets_at_from(value)
        if resets_at is not None:
            reading["resetsAt"] = resets_at

    if refused and "resetsAt" not in reading and isinstance(prior_reading, dict):
        prior_resets_at = prior_reading.get("resetsAt")
        if isinstance(prior_resets_at, (int, float)) and not isinstance(prior_resets_at, bool):
            reading["resetsAt"] = prior_resets_at

    return reading


class CopilotUsageLedger:
    """One per `run_turn` call (D2). Stdlib-only."""

    def __init__(self) -> None:
        self._seen_call_ids: Set[str] = set()
        self._calls: List[_Call] = []
        self._compactions: List[_Compaction] = []
        self._checkpoint: Optional[_Checkpoint] = None
        self._prompt_result: Optional[Dict[str, Any]] = None
        #: The newest `quotaSnapshots` map a call carried (D7). Last call observed wins.
        self._quota_snapshots: Optional[Dict[str, Any]] = None
        #: D8: recognised only by a `session.error`'s structured fields, never message text.
        self._refused = False

    def observe_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        if event_type == "assistant.usage":
            self._observe_call(data)
        elif event_type == "session.usage_checkpoint":
            nano_aiu, premium_requests = checkpoint_totals(data)
            self._checkpoint = _Checkpoint(nano_aiu=nano_aiu, premium_requests=premium_requests)
        elif event_type == "session.compaction_complete":
            self._observe_compaction(data)
        elif event_type == "session.error":
            self._observe_error(data)

    def _observe_error(self, data: Dict[str, Any]) -> None:
        if data.get("errorType") == "quota" and data.get("errorCode") == "quota_exceeded":
            self._refused = True

    @property
    def refused(self) -> bool:
        """Whether this run met D8's quota refusal (`run_turn` then returns `failed`)."""
        return self._refused

    def observe_prompt_error(self, data: Dict[str, Any]) -> None:
        """D8: the `data` of a JSON-RPC error answering `session/prompt`. The same structured
        quota fields count here as on a `session.error` notification (D8: "the same fields on a
        `session/prompt` JSON-RPC error's `data` count too") -- never message text."""
        if isinstance(data, dict):
            self._observe_error(data)

    def _observe_call(self, data: Dict[str, Any]) -> None:
        call_id = data.get("providerCallId") or data.get("apiCallId")
        if call_id is not None:
            if call_id in self._seen_call_ids:
                return
            self._seen_call_ids.add(call_id)
        snapshots = data.get("quotaSnapshots")
        if isinstance(snapshots, dict):
            self._quota_snapshots = snapshots
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
        """The run's one sample. Never raises (D11): malformed telemetry gives a sample with no
        tokens and no credits, logged, still carrying `credit_session_new` and a refusal."""
        try:
            return self._finish(session_was_new=session_was_new)
        except Exception:  # noqa: BLE001 - a run end never fails on its telemetry
            logger.warning("Copilot usage ledger could not finish this run", exc_info=True)
            return AccountingSample(
                source="copilot_calls",
                allowance=quota_reading(None, refused=self._refused, prior_reading=None),
                credit_session_new=session_was_new,
            )

    def _finish(self, *, session_was_new: bool) -> AccountingSample:
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
        # Provisional only: this run's own per-call sum (D11's fallback figure).
        # `settle_copilot_credits` is what applies D4's larger-of rule against the session
        # checkpoint; without it this is the best a database-free `finish()` can report.
        provisional_nano_aiu = per_call_nano_aiu
        provisional_premium_requests = session_premium_requests_total

        # D7/D8: this run's own reading. With no database (D2) it cannot fill `resetsAt` from
        # an earlier run when this run saw no qualifying snapshot of its own; that is
        # `settle_copilot_credits`'s job, at run end, against the project's last written reading.
        allowance = quota_reading(self._quota_snapshots, refused=self._refused, prior_reading=None)

        return AccountingSample(
            source=winner.source,
            input_tokens=winner.input_tokens,
            output_tokens=winner.output_tokens,
            total_tokens=winner.total_tokens,
            cache_read_tokens=winner.cache_read_tokens,
            cache_write_tokens=winner.cache_write_tokens,
            reasoning_tokens=winner.reasoning_tokens,
            model=model,
            allowance=allowance,
            ai_nano_aiu=provisional_nano_aiu,
            premium_requests=provisional_premium_requests,
            session_nano_aiu_total=session_nano_aiu_total,
            session_premium_requests_total=session_premium_requests_total,
            credit_session_new=session_was_new,
        )
