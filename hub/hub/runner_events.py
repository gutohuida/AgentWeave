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

from .workspace_writes import written_paths

PAYLOAD_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_TOOL_RESULT_BYTES = 8 * 1024

_SECRET_FIELD_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.I)

#: Two known credential prefixes, then a bounded high-entropy catch-all.
#:
#: The third alternative used to be `[A-Za-z0-9_=-]{32,}`, which matched **any** long identifier
#: (F31). Measured 2026-08-25, it redacted the Hub's own vocabulary:
#:
#:     41  <redacted>  <- spread-fairness-metric-fix-for-idle-staff
#:     37  <redacted>  <- mcp__agentweave__submit_spec_document
#:     32  <redacted>  <- mcp__agentweave__record_evidence
#:     42  <redacted>  <- this_is_a_perfectly_ordinary_function_name
#:
#: The Hub mints those document slugs itself from titles agents choose, and it names its own MCP
#: tools — so the rule was guaranteed to fire on the Hub's own words whenever a title ran long, and
#: the operator lost precisely the identifier saying *which* document an agent read.
#:
#: Excluding `_` and `-` is what separates the two populations. Raw credentials are hex or base64
#: and carry neither; identifiers a human or the Hub composed are made of joined words and carry
#: one or the other. A credential that does contain them is still caught whenever it wears a known
#: prefix, which is what the first two alternatives are for.
#:
#: **The two prefixes only count at the start of a word** (F118, driven live 2026-08-29). They were
#: unanchored, and `task-` ends in the literal `sk-` — so every task id the Hub has ever minted was
#: stored as `ta<redacted>`, in tool inputs, tool outputs, file paths under `.agentweave/tasks/`,
#: and snapshot commit messages. `subtask-1` became `subta<redacted>`; one trailing character was
#: enough. An operator reading a transcript could not tell which task any agent had worked on, and
#: since a task id is the join between a transcript and the board, that is the identifier the
#: reading exists to recover. The lookbehind rejects only `[A-Za-z0-9_]`, not `-`, because a
#: hyphen does not start a word: `x-sk-...` is still a key wearing its prefix, `task-...` is not.
#:
#: **A file path is not a credential, but a token inside one still is** (F278). `/` has to be in
#: the catch-all's class, because base64 uses it, so on a Linux host an ordinary path was eaten
#: whole: `/Users/operator/code/agentweave/hub/main.py` was stored as `<redacted>.py`, and the
#: agent's own checkout under `.agentweave/worktrees/` lost its name. A catch-all match is kept
#: when it splits on `/` into at least three non-empty segments that are each an ordinary word
#: (`_PATH_SEGMENT_RE`). Inside a kept match, a segment of 32 or more characters, or of 16 or more
#: holding both a letter and a digit, is still redacted: today a short token in a path is caught
#: only because the path around it brings the run to 32. Measured 2026-10-04: no fragment of
#: 400,000 random base64 keys containing `/` survives; of 20,000 random 16-23 character
#: lowercase-and-digit tokens in a URL path, 49 are stored (a letter-only draw reads as a word);
#: 28 of 200,205 real paths lose a segment (`contentsecuritypolicy2.js`). A path with a segment
#: that is not an ordinary word (`Claude2`, `README`) is still redacted whole.
_SECRET_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])aw_live_[A-Za-z0-9_=-]+|(?<![A-Za-z0-9_])sk-[A-Za-z0-9_=-]+"
    r"|(?P<entropy>[A-Za-z0-9+/=]{32,})"
)
_PATH_SEGMENT_RE = re.compile(r"[a-z0-9]+|[A-Z]?[a-z]+(?:[A-Z][a-z]+)*")
_TOKEN_SEGMENT_RE = re.compile(r"(?=.*[A-Za-z])(?=.*[0-9])")


def _redaction_for(match: "re.Match[str]") -> str:
    """What one `_SECRET_VALUE_RE` match is stored as: a path keeps its words (F278)."""
    text = match.group(0)
    segments = [segment for segment in text.split("/") if segment]
    if (
        match.lastgroup != "entropy"
        or len(segments) < 3
        or not all(_PATH_SEGMENT_RE.fullmatch(segment) for segment in segments)
    ):
        return "<redacted>"
    return "/".join(
        (
            "<redacted>"
            if len(segment) >= 32 or (len(segment) >= 16 and _TOKEN_SEGMENT_RE.match(segment))
            else segment
        )
        for segment in text.split("/")
    )


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
        return _SECRET_VALUE_RE.sub(_redaction_for, value)
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
    #: The path(s) this event's tool call declared it would write, raw and structured.
    #:
    #: Empty for every kind but `tool_use`, and empty for a `tool_use` that is not a write --
    #: which is why it defaults to `()` rather than being a required field: `text_event`,
    #: `thinking_event`, `tool_result_event` and the status/diagnostic/error builders are
    #: unchanged by its arrival, and so is every one of their call sites.
    #:
    #: **Never persisted.** `record_agent_output` stores `kind` and `payload` only, so this
    #: field lives exactly as long as the in-process hop from the parser to whatever consumes
    #: the event. Anything that must outlive the turn writes its own row.
    #:
    #: It is on `RunEvent` rather than on `ParsedLine` because the Codex app-server transport
    #: never builds a `ParsedLine` at all -- `map_item_to_events` returns events directly
    #: (design D2). One field on the event reaches all three transports; a field on
    #: `ParsedLine` would reach two.
    write_paths: Tuple[str, ...] = ()


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
    # Read the declared destination off the *structured* input, before the three transformations
    # below. This ordering is not defensive tidiness: both of the next two lines were measured
    # (2026-09-04) to destroy the path outright.
    #
    #   `redact_secrets` used to eat ordinary POSIX paths (F278). A path now survives, but one
    #   whose segment looks like a credential still loses that segment:
    #   `/workspace/project/<32 hex>/app.py` -> `/workspace/project/<redacted>/app.py`, and a
    #   path with a segment that is not an ordinary word is still redacted whole.
    #
    #   `_truncate_utf8` cuts the JSON text at 8 KiB, and `json.dumps(sort_keys=True)` puts
    #   `content` before `file_path`. A `Write` whose body exceeds 8 KiB therefore keeps the
    #   file it is writing and loses the name of it -- measured, 16 KiB body, `truncated=True`
    #   and no `file_path` anywhere in the blob.
    #
    # So the blob is not a fallback this field merely improves on. For the two commonest shapes
    # of the write this change exists to notice, the blob has nothing left to fall back to.
    declared_paths = written_paths(tool, input_data)
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
    return RunEvent(
        kind="tool_use",
        content=readable_summary,
        payload=payload,
        call_id=call_id,
        write_paths=declared_paths,
    )


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


def _fact_values(facts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """*facts* fit to merge into a payload: strings through the value rule, numbers kept.

    Never `redact_secrets(facts)` whole: its key rule matches any key containing `token`, so
    `pre_tokens`, `token_limit` and `total_tokens` would each be stored as `"<redacted>"` (slice 5
    D4). A count is not a secret because of its field's name. Absent facts are left out.
    """
    if not facts:
        return {}
    return {
        key: redact_secrets(value) if isinstance(value, str) else value
        for key, value in facts.items()
        if value is not None
    }


def status_event(
    phase: str, *, summary: Optional[str] = None, facts: Optional[Dict[str, Any]] = None
) -> RunEvent:
    readable_summary = summary or phase.replace("_", " ").capitalize()
    payload: Dict[str, Any] = {
        **_fact_values(facts),
        "version": PAYLOAD_VERSION,
        "phase": phase,
        "summary": readable_summary,
    }
    return RunEvent(kind="status", content=readable_summary, payload=payload)


def diagnostic_event(
    *,
    stream: str,
    severity: str,
    summary: str,
    code: Optional[str] = None,
    facts: Optional[Dict[str, Any]] = None,
) -> RunEvent:
    """Operational detail that is not the agent's output: a notice about how the run was set up
    or what the runner reported (`agent-stream-events`: *Diagnostic payloads SHALL identify stream
    and severity*).

    Mirrors the CLI's `agentweave.stream_events.diagnostic_event(*, stream, severity, summary)`,
    plus an optional stable `code` and structured `facts` (`a-copilot-agent-runs-over-acp` D10,
    the shape slice 5 builds on). `summary` is bounded like the CLI's and passed through the value
    rule of `redact_secrets`, as is every string inside `facts`.
    """
    safe_summary = redact_secrets(summary)
    bounded_summary, truncated = _truncate_utf8(safe_summary, MAX_TOOL_RESULT_BYTES)
    payload: Dict[str, Any] = {
        "version": PAYLOAD_VERSION,
        "stream": stream,
        "severity": severity,
        "summary": bounded_summary,
    }
    if code is not None:
        payload["code"] = code
    if facts is not None:
        payload["facts"] = redact_secrets(facts)
    if truncated:
        payload["truncated"] = True
    return RunEvent(kind="diagnostic", content=bounded_summary, payload=payload)


def error_event(
    *,
    code: str,
    message: str,
    exit_code: Optional[int] = None,
    retryable: bool = False,
    facts: Optional[Dict[str, Any]] = None,
) -> RunEvent:
    """An error, kept visible when diagnostics are hidden. Its `message` passes the value rule: an
    authentication error can quote the credential it refused (slice 5 D5)."""
    bounded_message, _truncated = _truncate_utf8(redact_secrets(message), MAX_TOOL_RESULT_BYTES)
    payload: Dict[str, Any] = {
        **_fact_values(facts),
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
    ai_nano_aiu: Optional[int] = None
    premium_requests: Optional[float] = None
    session_nano_aiu_total: Optional[int] = None
    session_premium_requests_total: Optional[float] = None
    #: Not persisted. Set only by CopilotUsageLedger.finish (design D2); settle_copilot_credits
    #: reads it to decide whether to act on a sample at all.
    credit_session_new: Optional[bool] = None

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
            "ai_nano_aiu",
            "premium_requests",
            "session_nano_aiu_total",
            "session_premium_requests_total",
            "credit_session_new",
        ):
            newer_value = getattr(newer, name)
            values[name] = newer_value if newer_value is not None else getattr(self, name)
        return AccountingSample(source=newer.source or self.source, **values)
