"""Agent monitor schemas."""

import contextlib
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import RequestModel

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

# The legacy context-usage vocabulary, hoisted so `normalize_legacy` can subtract the
# WHOLE of it from a body rather than only the alias it happened to read.
#
# `next(...)` picks first-wins, so a rolling upgrade that emits two names for one operand
# — `tokens_used` *and* `input_tokens`, both named by `agent-context-usage`'s "Legacy
# context compatibility" — leaves the loser behind. Subtracting only the winner would
# hand that survivor to `extra="forbid"` and 422 a body the shipped requirement says the
# Hub SHALL normalize. Subtract the vocabulary, not the reading.
_USED = ("context_tokens", "tokens_used", "input_tokens")
_LIMIT = ("limit_tokens", "tokens_limit", "context_limit", "max_context_tokens")
_RATIO = ("context_usage", "context_usage_ratio")
_WHEN = ("observed_at", "updated_at")
# `source`, `model`, `session_id` and `percent` are read straight across rather than
# through an alias, so they are consumed too.
_CARRIED = ("source", "model", "session_id", "percent")
# And three the validator never reads, which is why enumerating the vocabulary from what
# it *reads* missed them: the deleted watchdog computed `warning`/`critical` from the
# percentage and pushed them with every sample, and the body repeated the agent's own name
# alongside the one already in the path. They are retired names, not missing fields —
# nothing here should start honouring them — but a body carrying them is the shape
# `agent-context-usage`'s "Legacy data claims zero without a limit" scenario is written
# about, and it SHALL degrade to `unavailable`, not 422.
_RETIRED = ("agent", "warning", "critical")
LEGACY_CONTEXT_VOCABULARY = frozenset(_USED + _LIMIT + _RATIO + _WHEN + _CARRIED + _RETIRED)


class AgentSummary(BaseModel):
    name: str = Field(max_length=64)
    # What this agent is for, in the operator's words. Absent, not empty, when unset — it is
    # normalized to NULL on write, so a caller never has to treat "" and null as the same thing.
    description: Optional[str] = Field(default=None, max_length=256)
    status: str = Field(max_length=64)
    latest_status_msg: Optional[str] = Field(default=None, max_length=10000)
    # The last moment the Hub observed this agent doing anything: a run starting or ending, a
    # line of output, or a heartbeat. Not heartbeats alone — only a self-registered agent posts
    # those, so a heartbeat-only reading was permanently NULL for every Hub-spawned agent and the
    # rail said "No activity yet" about an agent mid-run (F17). See `hub/hub/agent_activity.py`.
    last_seen: Optional[datetime] = None
    message_count: int
    active_task_count: int
    # "open" or "archived". An agent is archived, never deleted; the default listing excludes
    # archived ones, so this is only ever "archived" for a caller that asked for them.
    lifecycle: str = Field(default="open", max_length=16)
    # The CLI this agent runs as. Free-form, not an enum: a Runner record supplies its own `cli`
    # and any value the registry accepts can appear here. "native" is the no-binding fallback.
    runner: str = Field(default="native", max_length=64)
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
    # How long this agent waits on the operator. None means the built-in default.
    permission_timeout_seconds: Optional[int] = None
    question_timeout_seconds: Optional[int] = None
    # What this agent may do when the conversation has not said. One of the catalog's postures,
    # or None for the built-in default. The composer reads it so its Permissions pill shows what
    # will actually happen rather than the catalog default.
    default_permission_mode: Optional[str] = Field(default=None, max_length=32)
    # Per-agent checkpoint overrides. All None means this agent inherits the project's policy;
    # a stated threshold replaces the project's whole threshold, mode and value together.
    checkpoint_mode: Optional[str] = Field(default=None, max_length=16)
    checkpoint_threshold_mode: Optional[str] = Field(default=None, max_length=8)
    checkpoint_threshold_value: Optional[int] = None
    checkpoint_notes_value: Optional[int] = None
    # Two independent grants, both closed by default: reading a peer's checkpoint is not the same
    # permission as recalling the raw output behind it.
    can_read_checkpoints: bool = False
    can_recall: bool = False
    # Authority over what ships, not a widening of what can be read — accepted evidence is what
    # lets approval merge an agent's work. Closed by default; a project that grants no agent still
    # has the operator, who can always accept.
    can_accept_evidence: bool = False

    model_config = {"from_attributes": True}


class AgentTimelineEvent(BaseModel):
    id: str = Field(max_length=128)
    event_type: str = Field(max_length=64)
    timestamp: datetime
    summary: str = Field(max_length=10000)
    data: Dict[str, Any]

    model_config = {"from_attributes": True}


class RunFacts(BaseModel):
    """What a run's own row records about how it went.

    Read from `Run`, never derived from the names or timestamps of the lifecycle events that
    happen to be in the window. `status` is the run's status renamed at the boundary — `Run.status`
    is `{running, completed, failed, stopped, interrupted}` and the client's `RunLifecycleStatus`
    is the same set with `running` spelled `started` (design D5).
    """

    status: str = Field(max_length=32)
    exit_code: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentTimeline(BaseModel):
    """The timeline response: the events, and the facts of the runs those events name.

    Keyed by `run_id` rather than listed because every consumer is a lookup or an unordered scan;
    a list would make the client build the index, which is the client-side reduction over run
    state that `a-turn-says-how-it-ended` exists to delete. Precedent: `jobs.py`'s
    `queue: Dict[str, int]`.
    """

    events: List[AgentTimelineEvent]
    runs: Dict[str, RunFacts] = Field(default_factory=dict)


class AgentHeartbeatCreate(RequestModel):
    status: str = Field(default="active", max_length=64)
    message: Optional[str] = Field(default=None, max_length=10000)


class ContextUsageCreate(RequestModel):
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
        used = next((data[key] for key in _USED if key in data), None)
        limit = next((data[key] for key in _LIMIT if key in data), None)
        ratio = next((data[key] for key in _RATIO if key in data), None)
        percent = data.get("percent")
        if ratio is not None:
            percent = ratio * 100 if isinstance(ratio, (int, float)) else ratio
        observed_at = next((data[key] for key in _WHEN if key in data), time.time())
        if isinstance(observed_at, str):
            with contextlib.suppress(ValueError):
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).timestamp()
        # Start from the residue — everything this validator did not consume — so a field
        # the legacy vocabulary does not name reaches `extra="forbid"` and is refused by
        # name, instead of vanishing into a dict built only from keys we knew about. Same
        # shape as `tasks.normalize_assignee_aliases`. One deliberate consequence: a
        # declared field the old fresh-dict dropped (`breakdown`) now survives the legacy
        # path, which is what a declared field should do.
        normalized = {
            key: item for key, item in data.items() if key not in LEGACY_CONTEXT_VOCABULARY
        }
        normalized.update(
            {
                "status": "measured",
                "source": data.get("source") or "legacy",
                "basis": "provider_context",
                "context_tokens": used,
                "limit_tokens": limit,
                "model": data.get("model"),
                "session_id": data.get("session_id"),
                "observed_at": observed_at,
            }
        )

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


class AgentOutputCreate(RequestModel):
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
