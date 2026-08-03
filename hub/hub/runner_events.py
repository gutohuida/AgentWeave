"""Canonical stream-event and context-usage construction for Hub-spawned runs.

Deliberately reimplemented rather than imported from the CLI's `stream_events.py` — the
Hub has no dependency on `agentweave-ai` (see `launchability.py`'s module docstring for the
same rationale). This mirrors that module's event taxonomy and payload shapes exactly
(`kind`, `content`, `payload`) so output from a Hub-spawned run is indistinguishable, once
stored, from output the watchdog already pushes via `POST /agents/{name}/output` — the same
`AgentOutputCreate` schema and the same frontend rendering already handle both.

Kinds match `hub.schemas.agents.StreamEventKind`: text, thinking, tool_use, tool_result,
status, diagnostic, error.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

PAYLOAD_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_TOOL_RESULT_BYTES = 8 * 1024

_SECRET_FIELD_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.I)
_SECRET_VALUE_RE = re.compile(r"(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})")


def redact_secrets(value: Any) -> Any:
    """Redact obvious secret-looking fields/values before they reach a payload.

    Same approach as the CLI's `agentweave.diagnostics.redact_secrets` (field-name match on
    api_key/token/secret/password/authorization, value match on known key prefixes or long
    opaque tokens) — tool inputs/outputs can carry env-var values or credentials verbatim.
    """
    if isinstance(value, dict):
        return {
            key: "<redacted>" if _SECRET_FIELD_RE.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return _SECRET_VALUE_RE.sub("<redacted>", value)
    return value


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_utf8(value: str, max_bytes: int) -> Tuple[str, bool]:
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


@dataclass
class RunEvent:
    kind: str
    content: str
    payload: Dict[str, Any]
    call_id: Optional[str] = None


def text_event(text: str) -> RunEvent:
    bounded, truncated = _truncate_utf8(text, MAX_PAYLOAD_BYTES)
    payload: Dict[str, Any] = {"version": PAYLOAD_VERSION, "text": bounded}
    if truncated:
        payload["truncated"] = True
    return RunEvent(kind="text", content=bounded, payload=payload)


def thinking_event(text: str) -> RunEvent:
    bounded, truncated = _truncate_utf8(text, MAX_PAYLOAD_BYTES)
    payload: Dict[str, Any] = {"version": PAYLOAD_VERSION, "text": bounded}
    if truncated:
        payload["truncated"] = True
    return RunEvent(kind="thinking", content=bounded, payload=payload)


def tool_use_event(
    *,
    tool: str,
    category: str,
    input_data: Any = None,
    call_id: Optional[str] = None,
    summary: Optional[str] = None,
) -> RunEvent:
    safe_input = redact_secrets(input_data)
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
    return RunEvent(kind="tool_use", content=readable_summary, payload=payload, call_id=call_id)


def tool_result_event(
    *,
    tool: str,
    output: Any = None,
    call_id: Optional[str] = None,
    summary: Optional[str] = None,
    is_error: bool = False,
) -> RunEvent:
    safe_output = redact_secrets(output)
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
    return RunEvent(kind="tool_result", content=readable_summary, payload=payload, call_id=call_id)


def status_event(phase: str, *, summary: Optional[str] = None) -> RunEvent:
    readable_summary = summary or phase.replace("_", " ").capitalize()
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "phase": phase,
        "summary": readable_summary,
    }
    return RunEvent(kind="status", content=readable_summary, payload=payload)


def error_event(
    *, code: str, message: str, exit_code: Optional[int] = None, retryable: bool = False
) -> RunEvent:
    bounded_message, _truncated = _truncate_utf8(message, MAX_TOOL_RESULT_BYTES)
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "code": code,
        "message": bounded_message,
        "retryable": retryable,
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    return RunEvent(kind="error", content=bounded_message, payload=payload)


@dataclass
class ContextUsageSample:
    """Mirrors `agentweave.stream_events.ContextUsageSample`'s canonical field names."""

    status: str
    source: str
    basis: Optional[str] = None
    context_tokens: Optional[int] = None
    limit_tokens: Optional[int] = None
    percent: Optional[float] = None
    model: Optional[str] = None
    session_id: Optional[str] = None
    observed_at: float = field(default_factory=time.time)
    breakdown: Optional[Dict[str, int]] = None

    def __post_init__(self) -> None:
        if (
            self.percent is None
            and self.context_tokens is not None
            and self.limit_tokens is not None
            and self.limit_tokens > 0
        ):
            derived = (self.context_tokens / self.limit_tokens) * 100
            self.percent = round(min(100.0, max(0.0, derived)), 2)

    def to_payload(self, agent: str) -> Dict[str, Any]:
        return {
            "agent": agent,
            "status": self.status,
            "context_tokens": self.context_tokens,
            "limit_tokens": self.limit_tokens,
            "percent": self.percent,
            "model": self.model,
            "session_id": self.session_id,
            "source": self.source,
            "basis": self.basis,
            "breakdown": self.breakdown,
            "observed_at": self.observed_at,
        }


@dataclass
class AccountingSample:
    """Runner-neutral totals for one turn, separate from context-window pressure."""

    source: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    model: Optional[str] = None
    api_equivalent_usd_micros: Optional[int] = None
    allowance: Optional[Dict[str, Any]] = None

    def merged(self, newer: "AccountingSample") -> "AccountingSample":
        """Overlay newer reported fields while retaining independent earlier telemetry."""
        values: Dict[str, Any] = {}
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "model",
            "api_equivalent_usd_micros",
            "allowance",
        ):
            newer_value = getattr(newer, name)
            values[name] = newer_value if newer_value is not None else getattr(self, name)
        return AccountingSample(source=newer.source or self.source, **values)
