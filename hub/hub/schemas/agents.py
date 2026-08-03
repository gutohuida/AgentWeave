"""Agent monitor schemas."""

import contextlib
import json
import time
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

StreamEventKind = Literal[
    "text",
    "thinking",
    "tool_use",
    "tool_result",
    "status",
    "diagnostic",
    "error",
]

MAX_STREAM_PAYLOAD_BYTES = 64 * 1024
# Matches the CLI's `stream_events.MAX_PAYLOAD_BYTES` content bound. The CLI
# truncates to 64 KiB of UTF-8, which is never more than 64 Ki characters, so
# anything it emits fits. A lower limit here silently 422s long text/thinking
# events, which are the only kinds not already bounded to 8 KiB.
MAX_STREAM_CONTENT_CHARS = 64 * 1024
CONTEXT_BREAKDOWN_FIELDS = {
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "reasoning_tokens",
    "cached_input_tokens",
}


class AgentSummary(BaseModel):
    name: str = Field(max_length=64)
    status: str = Field(max_length=64)
    latest_status_msg: Optional[str] = Field(default=None, max_length=10000)
    last_seen: Optional[datetime] = None
    message_count: int
    active_task_count: int
    role: Optional[str] = Field(
        default=None, max_length=64
    )  # "principal" | "delegate" | "collaborator"
    yolo: bool = False
    runner: str = Field(
        default="native", max_length=64
    )  # "native" | "claude_proxy" | "kimi" | "manual"
    display_model: Optional[str] = Field(
        default=None, max_length=128
    )  # e.g. "Claude", "Kimi", "Minimax" — derived from runner
    context_usage: Optional[Dict[str, Any]] = (
        None  # {percent, warning, model, threshold_warning, updated_at}
    )
    session_started_at: Optional[datetime] = None  # When the current session started
    self_registered: bool = False  # True if agent joined via self-registration
    liveness: Optional[str] = Field(
        default=None, max_length=64
    )  # "online" | "offline" for self-registered agents
    runner_options: Optional[Dict[str, Any]] = (
        None  # Runner-specific options (e.g., memory for Codex)
    )
    color_index: Optional[int] = None  # Stable palette index, assigned once at registration
    runner_id: Optional[str] = Field(default=None, max_length=64)  # Bound Runner record, if any
    charter_id: Optional[str] = Field(default=None, max_length=64)  # Bound Charter record, if any

    model_config = {"from_attributes": True}


class AgentTimelineEvent(BaseModel):
    id: str = Field(max_length=128)
    event_type: str = Field(max_length=64)
    timestamp: datetime
    summary: str = Field(max_length=10000)
    data: Dict[str, Any]

    model_config = {"from_attributes": True}


class AgentHeartbeatCreate(BaseModel):
    status: str = Field(default="active", max_length=64)
    message: Optional[str] = Field(default=None, max_length=10000)


class ContextUsageCreate(BaseModel):
    status: Literal["measured", "estimated", "unsupported", "unavailable"]
    source: str = Field(min_length=1, max_length=64)
    basis: Optional[
        Literal[
            "provider_context",
            "latest_request_input",
            "provider_reported_ratio",
            "cumulative_delta",
        ]
    ] = None
    context_tokens: Optional[int] = Field(default=None, ge=0)
    limit_tokens: Optional[int] = Field(default=None, gt=0)
    percent: Optional[float] = Field(default=None, ge=0, le=100)
    model: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    observed_at: float = Field(ge=0)
    breakdown: Optional[Dict[str, int]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "status" in value:
            return value
        data = dict(value)
        used = next(
            (data[key] for key in ("context_tokens", "tokens_used", "input_tokens") if key in data),
            None,
        )
        limit = next(
            (
                data[key]
                for key in ("limit_tokens", "tokens_limit", "context_limit", "max_context_tokens")
                if key in data
            ),
            None,
        )
        ratio = data.get("context_usage", data.get("context_usage_ratio"))
        percent = data.get("percent")
        if ratio is not None:
            percent = ratio * 100 if isinstance(ratio, (int, float)) else ratio
        observed_at = data.get("observed_at", data.get("updated_at", time.time()))
        if isinstance(observed_at, str):
            with contextlib.suppress(ValueError):
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).timestamp()
        normalized = {
            "status": "measured",
            "source": data.get("source") or "legacy",
            "basis": "provider_context",
            "context_tokens": used,
            "limit_tokens": limit,
            "model": data.get("model"),
            "session_id": data.get("session_id"),
            "observed_at": observed_at,
        }

        def degrade_to_unavailable() -> Dict[str, Any]:
            normalized.update(
                status="unavailable",
                basis=None,
                context_tokens=None,
                limit_tokens=None,
            )
            normalized.pop("percent", None)
            return normalized

        if used is None:
            # A legacy zero or absent percentage is not a measurement. Older
            # CLIs wrote `{"percent": 0}` on every session reset/compaction, so
            # trusting it here would paint a 0% bar for an unmeasured session.
            if isinstance(percent, (int, float)) and not isinstance(percent, bool) and percent > 0:
                normalized.update(basis="provider_reported_ratio", percent=percent)
            else:
                return degrade_to_unavailable()
        elif used == 0 and limit is None:
            return degrade_to_unavailable()
        elif (
            isinstance(used, (int, float))
            and not isinstance(used, bool)
            and isinstance(limit, (int, float))
            and not isinstance(limit, bool)
            and limit > 0
            and isinstance(percent, (int, float))
            and not isinstance(percent, bool)
        ):
            derived = min(100.0, (used / limit) * 100)
            if abs(float(percent) - derived) > 1:
                normalized["limit_tokens"] = None
        return normalized

    @field_validator("breakdown")
    @classmethod
    def validate_breakdown(cls, value: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        if value is None:
            return None
        if not set(value) <= CONTEXT_BREAKDOWN_FIELDS:
            raise ValueError("breakdown contains unsupported fields")
        if any(isinstance(item, bool) or item < 0 for item in value.values()):
            raise ValueError("breakdown values must be non-negative integers")
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> "ContextUsageCreate":
        if self.status in ("unsupported", "unavailable"):
            if any(
                value is not None
                for value in (self.basis, self.context_tokens, self.limit_tokens, self.percent)
            ):
                raise ValueError("unavailable/unsupported samples cannot contain usage operands")
            return self
        if self.basis is None:
            raise ValueError("measured/estimated samples require a basis")
        if self.basis == "provider_reported_ratio":
            if self.percent is None:
                raise ValueError("provider-reported ratio samples require percent")
            return self
        if self.context_tokens is None:
            raise ValueError("measured/estimated token samples require context_tokens")
        if self.limit_tokens is not None:
            derived = round(min(100.0, (self.context_tokens / self.limit_tokens) * 100), 2)
            if self.percent is not None and abs(self.percent - derived) > 0.01:
                raise ValueError("percent contradicts context_tokens and limit_tokens")
            self.percent = derived
        elif self.percent is not None:
            raise ValueError("percent requires a known limit")
        return self


class AgentOutputCreate(BaseModel):
    content: str = Field(max_length=MAX_STREAM_CONTENT_CHARS)
    session_id: Optional[str] = Field(default=None, max_length=128)
    kind: Optional[StreamEventKind] = None
    payload: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = Field(default=None, max_length=64)
    sequence: Optional[int] = Field(default=None, ge=0, le=2_147_483_647)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON serializable") from exc
        if len(serialized.encode("utf-8")) > MAX_STREAM_PAYLOAD_BYTES:
            raise ValueError(f"serialized payload must be at most {MAX_STREAM_PAYLOAD_BYTES} bytes")
        return payload


class AgentOutputResponse(BaseModel):
    id: str = Field(max_length=128)
    agent: str = Field(max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=128)
    content: str = Field(max_length=MAX_STREAM_CONTENT_CHARS)
    kind: Optional[StreamEventKind] = None
    payload: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = Field(default=None, max_length=64)
    sequence: Optional[int] = Field(default=None, ge=0, le=2_147_483_647)
    timestamp: datetime

    model_config = {"from_attributes": True}
