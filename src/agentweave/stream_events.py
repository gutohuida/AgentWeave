"""Canonical runner stream-event and context-usage contracts.

Every runner adapter (Claude, Codex, OpenCode, Copilot, Kimi) and auxiliary usage
collector produces these provider-neutral types. Raw provider dictionaries,
opaque reasoning blobs, and unbounded payloads never cross this boundary: the
constructors here are the only supported way to build an `AgentStreamEvent` or
`ContextUsageSample`, and they redact, bound, and validate before returning.

Context usage is intentionally a separate contract from stream events: it is a
replaceable latest-session snapshot, never an `AgentOutput` row or a stream kind.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from .diagnostics import redact_secrets

PAYLOAD_VERSION = 1

MAX_PAYLOAD_BYTES = 64 * 1024
MAX_TOOL_RESULT_BYTES = 8 * 1024

StreamEventKind = Literal[
    "text", "thinking", "tool_use", "tool_result", "status", "diagnostic", "error"
]

STREAM_EVENT_KINDS: Tuple[StreamEventKind, ...] = (
    "text",
    "thinking",
    "tool_use",
    "tool_result",
    "status",
    "diagnostic",
    "error",
)

StatusPhase = Literal["queued", "started", "plan", "compacting", "retrying", "completed", "skipped"]

STATUS_PHASES: Tuple[StatusPhase, ...] = (
    "queued",
    "started",
    "plan",
    "compacting",
    "retrying",
    "completed",
    "skipped",
)

ContextStatus = Literal["measured", "estimated", "unsupported", "unavailable"]

CONTEXT_STATUSES: Tuple[ContextStatus, ...] = (
    "measured",
    "estimated",
    "unsupported",
    "unavailable",
)

ContextBasis = Literal[
    "provider_context", "latest_request_input", "provider_reported_ratio", "cumulative_delta"
]

CONTEXT_BASES: Tuple[ContextBasis, ...] = (
    "provider_context",
    "latest_request_input",
    "provider_reported_ratio",
    "cumulative_delta",
)

# Numeric fields a context-usage breakdown may carry. Anything else is dropped:
# breakdowns must never hold raw provider objects, message content, or fields
# whose provider semantics we have not validated (e.g. Kimi's completion-only
# `llm.request.maxTokens`).
CONTEXT_BREAKDOWN_FIELDS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "reasoning_tokens",
        "cached_input_tokens",
    }
)


class StreamEventError(ValueError):
    """Raised when a stream event or context sample violates the canonical contract."""


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_utf8(value: str, max_bytes: int) -> Tuple[str, bool]:
    """Truncate `value` to at most `max_bytes` UTF-8 bytes without splitting a codepoint."""
    if max_bytes <= 0:
        return "", bool(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    chunk = encoded[:max_bytes]
    while chunk:
        try:
            return chunk.decode("utf-8"), True
        except UnicodeDecodeError:
            chunk = chunk[:-1]
    return "", True


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def _payload_size(payload: Dict[str, Any]) -> int:
    return _utf8_len(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))


def _enforce_payload_bound(payload: Dict[str, Any]) -> bool:
    """Shrink the largest string field in `payload` until it serializes within
    `MAX_PAYLOAD_BYTES`. Mutates `payload` in place. Returns True if anything was cut.
    """
    truncated = False
    overage = _payload_size(payload) - MAX_PAYLOAD_BYTES
    while overage > 0:
        candidates = [
            (key, val)
            for key, val in payload.items()
            if isinstance(val, str) and key not in ("version", "kind")
        ]
        if not candidates:
            break
        key, value = max(candidates, key=lambda kv: len(kv[1]))
        target_bytes = max(0, _utf8_len(value) - overage - 16)
        new_value, _ = _truncate_utf8(value, target_bytes)
        if new_value == value:
            break
        payload[key] = new_value
        truncated = True
        overage = _payload_size(payload) - MAX_PAYLOAD_BYTES
    if truncated:
        payload["truncated"] = True
    return truncated


@dataclass
class AgentStreamEvent:
    """One normalized, renderable unit of runner output."""

    kind: StreamEventKind
    content: str
    payload: Dict[str, Any]
    run_id: Optional[str] = None
    sequence: Optional[int] = None
    call_id: Optional[str] = None
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.kind not in STREAM_EVENT_KINDS:
            raise StreamEventError(f"unknown stream event kind: {self.kind!r}")
        if not self.content:
            raise StreamEventError("stream event content must be non-empty")
        if self.payload.get("version") != PAYLOAD_VERSION:
            raise StreamEventError("stream event payload must declare version=1")


@dataclass
class ContextUsageSample:
    """The latest non-cumulative context observation for one provider session."""

    status: ContextStatus
    source: str
    basis: Optional[ContextBasis] = None
    context_tokens: Optional[int] = None
    limit_tokens: Optional[int] = None
    percent: Optional[float] = None
    model: Optional[str] = None
    session_id: Optional[str] = None
    observed_at: float = field(default_factory=time.time)
    breakdown: Optional[Dict[str, int]] = None

    def __post_init__(self) -> None:
        if self.status not in CONTEXT_STATUSES:
            raise StreamEventError(f"unknown context status: {self.status!r}")
        if not self.source:
            raise StreamEventError("context sample source must be non-empty")
        if self.status in ("measured", "estimated") and self.basis is None:
            raise StreamEventError("measured/estimated samples require a basis")
        if self.basis is not None and self.basis not in CONTEXT_BASES:
            raise StreamEventError(f"unknown context basis: {self.basis!r}")
        if self.context_tokens is not None and self.context_tokens < 0:
            raise StreamEventError("context_tokens must be non-negative")
        if self.limit_tokens is not None and self.limit_tokens <= 0:
            raise StreamEventError("limit_tokens must be positive")

        if self.breakdown is not None:
            filtered = {
                key: int(value)
                for key, value in self.breakdown.items()
                if key in CONTEXT_BREAKDOWN_FIELDS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            }
            self.breakdown = filtered or None

        if self.percent is not None:
            if self.basis != "provider_reported_ratio":
                raise StreamEventError(
                    "percent may only be supplied directly when basis=provider_reported_ratio"
                )
            if not 0 <= self.percent <= 100:
                raise StreamEventError("percent must be within 0 through 100")
        elif self.context_tokens is not None and self.limit_tokens is not None:
            derived = (self.context_tokens / self.limit_tokens) * 100
            self.percent = round(min(100.0, max(0.0, derived)), 2)


def _legacy_number(data: Dict[str, Any], *names: str) -> Tuple[Optional[float], bool]:
    """Return the first present finite numeric alias and whether it was invalid."""
    for name in names:
        if name not in data or data[name] is None:
            continue
        value = data[name]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            return None, True
        return float(value), False
    return None, False


def normalize_context_usage(
    data: Any,
    *,
    source: str = "legacy",
    observed_at: Optional[float] = None,
) -> ContextUsageSample:
    """Normalize canonical or historical context dictionaries.

    Readers accept the aliases emitted by older AgentWeave versions while
    writers remain canonical. Ambiguous zeroes and contradictory percentages
    degrade to unavailable or token-only state instead of becoming a trusted
    zero-percent measurement.
    """

    def unavailable() -> ContextUsageSample:
        return ContextUsageSample(
            status="unavailable",
            source=str(data.get("source") or source) if isinstance(data, dict) else source,
            session_id=data.get("session_id") if isinstance(data, dict) else None,
            model=data.get("model") if isinstance(data, dict) else None,
            observed_at=observed_at if observed_at is not None else time.time(),
        )

    if not isinstance(data, dict):
        return unavailable()

    sample_source = str(data.get("source") or source)
    sample_observed_at = data.get("observed_at", observed_at)
    if (
        not isinstance(sample_observed_at, (int, float))
        or isinstance(sample_observed_at, bool)
        or not math.isfinite(sample_observed_at)
    ):
        sample_observed_at = observed_at if observed_at is not None else time.time()

    status = data.get("status")
    if status in CONTEXT_STATUSES:
        try:
            basis = data.get("basis")
            context_tokens = data.get("context_tokens")
            limit_tokens = data.get("limit_tokens")
            supplied_percent = data.get("percent")
            if status in ("unavailable", "unsupported"):
                if any(
                    value is not None
                    for value in (basis, context_tokens, limit_tokens, supplied_percent)
                ):
                    return unavailable()
            elif basis == "provider_reported_ratio":
                if supplied_percent is None:
                    return unavailable()
            elif context_tokens is None:
                return unavailable()
            percent = supplied_percent if basis == "provider_reported_ratio" else None
            sample = ContextUsageSample(
                status=status,
                source=sample_source,
                basis=basis,
                context_tokens=context_tokens,
                limit_tokens=limit_tokens,
                percent=percent,
                model=data.get("model"),
                session_id=data.get("session_id"),
                observed_at=float(sample_observed_at),
                breakdown=data.get("breakdown"),
            )
            if (
                supplied_percent is not None
                and sample.percent is not None
                and (
                    not isinstance(supplied_percent, (int, float))
                    or isinstance(supplied_percent, bool)
                    or abs(float(supplied_percent) - sample.percent) > 0.01
                )
            ):
                return unavailable()
            return sample
        except (StreamEventError, TypeError, ValueError):
            return unavailable()

    used, used_invalid = _legacy_number(data, "context_tokens", "tokens_used", "input_tokens")
    limit, limit_invalid = _legacy_number(
        data, "limit_tokens", "tokens_limit", "context_limit", "max_context_tokens"
    )
    ratio, ratio_invalid = _legacy_number(data, "context_usage", "context_usage_ratio")
    legacy_percent, percent_invalid = _legacy_number(data, "percent")
    if used_invalid or limit_invalid or ratio_invalid or percent_invalid:
        return unavailable()
    if used is not None and (used < 0 or not used.is_integer()):
        return unavailable()
    if limit is not None and (limit <= 0 or not limit.is_integer()):
        return unavailable()
    if ratio is not None:
        if not 0 <= ratio <= 1:
            return unavailable()
        ratio_percent = ratio * 100
        if legacy_percent is not None and abs(legacy_percent - ratio_percent) > 1:
            return unavailable()
        legacy_percent = ratio_percent
    if legacy_percent is not None and not 0 <= legacy_percent <= 100:
        return unavailable()

    context_tokens = int(used) if used is not None else None
    limit_tokens = int(limit) if limit is not None else None

    def legacy_sample(
        *,
        basis: ContextBasis,
        context_tokens: Optional[int] = None,
        limit_tokens: Optional[int] = None,
        percent: Optional[float] = None,
    ) -> ContextUsageSample:
        return ContextUsageSample(
            status="measured",
            source=sample_source,
            basis=basis,
            context_tokens=context_tokens,
            limit_tokens=limit_tokens,
            percent=percent,
            model=data.get("model"),
            session_id=data.get("session_id"),
            observed_at=float(sample_observed_at),
        )

    if context_tokens is not None:
        if context_tokens == 0 and limit_tokens is None:
            return unavailable()
        if limit_tokens is not None:
            derived_percent = round(min(100.0, (context_tokens / limit_tokens) * 100), 2)
            if legacy_percent is not None and abs(legacy_percent - derived_percent) > 1:
                # The token count is still useful, but the denominator/ratio pair
                # is contradictory and must not become a trusted percentage.
                return legacy_sample(
                    basis="provider_context",
                    context_tokens=context_tokens,
                )
        return legacy_sample(
            basis="provider_context",
            context_tokens=context_tokens,
            limit_tokens=limit_tokens,
        )

    if legacy_percent is not None and legacy_percent > 0:
        return legacy_sample(
            basis="provider_reported_ratio",
            percent=legacy_percent,
        )
    return unavailable()


def stream_event_transport_fields(event: AgentStreamEvent) -> Dict[str, Any]:
    """Return bounded, recursively redacted optional transport fields."""
    safe_content = _redact(event.content)
    if not isinstance(safe_content, str):
        safe_content = _stringify(safe_content)
    safe_content, content_truncated = _truncate_utf8(safe_content, MAX_PAYLOAD_BYTES)
    safe_payload = _redact(event.payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {"version": PAYLOAD_VERSION}
    payload_truncated = _enforce_payload_bound(safe_payload)
    if content_truncated or payload_truncated:
        safe_payload["truncated"] = True
    return {
        "content": safe_content,
        "kind": event.kind,
        "payload": safe_payload,
        "run_id": event.run_id,
        "sequence": event.sequence,
    }


@dataclass
class SessionChange:
    """A provider session boundary observed mid-stream (new or resumed session)."""

    session_id: str
    reason: Optional[str] = None


@dataclass
class ParserControl:
    """Parser-level signals that are not themselves display or usage data."""

    retry: bool = False
    stop: bool = False


@dataclass
class ParsedRunnerLine:
    """The result of normalizing one runner observation.

    `events` and `usage` are independent: a line may carry either, both, or
    neither. Neither field is fabricated to satisfy the other.
    """

    events: List[AgentStreamEvent] = field(default_factory=list)
    usage: Optional[ContextUsageSample] = None
    session_change: Optional[SessionChange] = None
    control: Optional[ParserControl] = None


def _redact(value: Any) -> Any:
    return redact_secrets(value)


def text_event(text: str, *, run_id: Optional[str] = None) -> AgentStreamEvent:
    """User-facing assistant prose."""
    bounded, truncated = _truncate_utf8(text, MAX_PAYLOAD_BYTES)
    payload: Dict[str, Any] = {"version": PAYLOAD_VERSION, "text": bounded}
    if truncated:
        payload["truncated"] = True
    return AgentStreamEvent(
        kind="text", content=bounded, payload=payload, run_id=run_id, truncated=truncated
    )


def thinking_event(text: str, *, run_id: Optional[str] = None) -> AgentStreamEvent:
    """Provider-exposed readable reasoning/status prose.

    Only readable text is accepted: there is no field to carry an opaque or
    encrypted reasoning blob, so adapters cannot smuggle one into content or
    payload through this constructor.
    """
    bounded, truncated = _truncate_utf8(text, MAX_PAYLOAD_BYTES)
    payload: Dict[str, Any] = {"version": PAYLOAD_VERSION, "text": bounded}
    if truncated:
        payload["truncated"] = True
    return AgentStreamEvent(
        kind="thinking", content=bounded, payload=payload, run_id=run_id, truncated=truncated
    )


def tool_use_event(
    *,
    tool: str,
    category: str,
    input_data: Any = None,
    call_id: Optional[str] = None,
    summary: Optional[str] = None,
    run_id: Optional[str] = None,
) -> AgentStreamEvent:
    """A tool invocation."""
    safe_input = _redact(input_data)
    input_text, input_truncated = _truncate_utf8(_stringify(safe_input), MAX_TOOL_RESULT_BYTES)
    readable_summary = summary or f"Called {tool}"
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "call_id": call_id,
        "tool": tool,
        "category": category,
        "input": input_text,
        "summary": readable_summary,
        "truncated": input_truncated,
    }
    bound_truncated = _enforce_payload_bound(payload)
    return AgentStreamEvent(
        kind="tool_use",
        content=readable_summary,
        payload=payload,
        run_id=run_id,
        call_id=call_id,
        truncated=input_truncated or bound_truncated,
    )


def tool_result_event(
    *,
    tool: str,
    output: Any = None,
    call_id: Optional[str] = None,
    summary: Optional[str] = None,
    is_error: bool = False,
    run_id: Optional[str] = None,
) -> AgentStreamEvent:
    """A tool completion, successful or failed."""
    safe_output = _redact(output)
    output_text, output_truncated = _truncate_utf8(_stringify(safe_output), MAX_TOOL_RESULT_BYTES)
    readable_summary = summary or (f"{tool} failed" if is_error else f"{tool} completed")
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "call_id": call_id,
        "tool": tool,
        "output": output_text,
        "summary": readable_summary,
        "is_error": is_error,
        "truncated": output_truncated,
    }
    bound_truncated = _enforce_payload_bound(payload)
    return AgentStreamEvent(
        kind="tool_result",
        content=readable_summary,
        payload=payload,
        run_id=run_id,
        call_id=call_id,
        truncated=output_truncated or bound_truncated,
    )


def status_event(
    phase: StatusPhase, *, summary: Optional[str] = None, run_id: Optional[str] = None
) -> AgentStreamEvent:
    """Run lifecycle or plan state."""
    if phase not in STATUS_PHASES:
        raise StreamEventError(f"unknown status phase: {phase!r}")
    readable_summary = summary or phase.replace("_", " ").capitalize()
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "phase": phase,
        "summary": readable_summary,
    }
    return AgentStreamEvent(kind="status", content=readable_summary, payload=payload, run_id=run_id)


def diagnostic_event(
    *, stream: str, severity: str, summary: str, run_id: Optional[str] = None
) -> AgentStreamEvent:
    """Operational detail that is not user-relevant output."""
    bounded_summary, truncated = _truncate_utf8(summary, MAX_TOOL_RESULT_BYTES)
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "stream": stream,
        "severity": severity,
        "summary": bounded_summary,
    }
    return AgentStreamEvent(
        kind="diagnostic",
        content=bounded_summary,
        payload=payload,
        run_id=run_id,
        truncated=truncated,
    )


def error_event(
    *,
    code: str,
    message: str,
    exit_code: Optional[int] = None,
    retryable: bool = False,
    run_id: Optional[str] = None,
) -> AgentStreamEvent:
    """A run-level failure."""
    bounded_message, truncated = _truncate_utf8(message, MAX_TOOL_RESULT_BYTES)
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "code": code,
        "message": bounded_message,
        "retryable": retryable,
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    return AgentStreamEvent(
        kind="error",
        content=bounded_message,
        payload=payload,
        run_id=run_id,
        truncated=truncated,
    )
