"""The values a run must never have recorded, by run, scrubbed by exact value (slice 5 design D7).

A Copilot agent on a model-provider runner has its key in its run's environment
(`COPILOT_PROVIDER_API_KEY`). The pattern rules in `runner_events.redact_secrets` do not cover it:
they run on tool events only, so a reply that repeats the key was stored verbatim, and a key on a
localhost proxy can have any format at all, which no `sk-`/`aw_live_` rule matches (review
2026-09-28, finding 2). The Hub knows the resolved value at spawn, so it is matched by that value.

In-process and never persisted: the trigger registers a run's values just before its task starts
and forgets them when the task ends, however it ends. Every writer of a run's recorded text scrubs
through `scrub` before it stores or broadcasts: `record_agent_output`, the permission card, the
run's stored failure text and its lifecycle events.

That pass sees one event at a time, and a model's text is not one event: a runner records it as a
sequence of `text` and `thinking` events, with tool calls, errors and status cards between them,
so a value whose characters fall on both sides of a boundary passed it in two harmless-looking
halves that the timeline shows together (F488). `scrub_stream` therefore carries the end of the
run's text from one event to the next and redacts a value across the boundary
(`a-secret-split-across-two-events-is-still-scrubbed`, design D1). It is called once per event by
the two executors, beside the event's `sequence`, not inside `record_agent_output`, whose retry on
a locked database would feed the same text in twice; the per-event `scrub` stays as the floor.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

if TYPE_CHECKING:
    from .runner_events import RunEvent

REDACTED = "<redacted>"

#: The kinds whose content is the model's own prose, joined across events (design D2).
STREAM_KINDS = ("text", "thinking")

_by_run: Dict[str, Tuple[str, ...]] = {}
#: The last `L - 1` characters of each run's recorded text, unredacted, trailing whitespace
#: removed (`L` the longest registered value): what a value begun there can still complete.
_tail_by_run: Dict[str, str] = {}


def register(run_id: str, values: Iterable[Optional[str]]) -> None:
    """Hold *values* for *run_id*; empty and missing values are ignored, so a run with nothing to
    hide registers nothing. Longest first, so a value containing another is replaced whole.

    Each value is kept stripped, and as written too when that differs (design D7): a key resolved
    with a trailing newline is written by the model without it. A value that strips to nothing
    is dropped, since it would otherwise replace every run of spaces."""
    kept = set()
    for value in values:
        if not value or not value.strip():
            continue
        kept.add(value.strip())
        kept.add(value)
    if kept:
        _by_run[run_id] = tuple(sorted(kept, key=len, reverse=True))


def forget(run_id: str) -> None:
    _by_run.pop(run_id, None)
    _tail_by_run.pop(run_id, None)


def registered(run_id: Optional[str]) -> Tuple[str, ...]:
    return _by_run.get(run_id, ()) if run_id else ()


def scrub(run_id: Optional[str], value: Any) -> Any:
    """*value* with every literal occurrence of *run_id*'s registered values replaced, through
    dicts (keys and values), lists and tuples. Anything else is returned unchanged, as is
    everything for a run that registered nothing."""
    secrets = registered(run_id)
    if not secrets:
        return value
    return _scrub(value, secrets)


def _scrub(value: Any, secrets: Tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {_scrub(key, secrets): _scrub(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item, secrets) for item in value)
    return value


def dangling_minimum(value: str) -> int:
    """How many of a value's first characters an event must end with to lose them unseen of
    what follows (design D4): half the value, rounded down, but never more than 8."""
    return max(1, min(8, len(value) // 2))


def scrub_stream(run_id: Optional[str], event: "RunEvent") -> "RunEvent":
    """*event* with each registered value of *run_id* that crosses into it from the run's earlier
    text, or dangles from its end, replaced (design D1). Call once per recorded event, in
    `sequence` order. Any kind but `text`/`thinking` is returned as it is and leaves the carried
    text alone, so the join spans tool, error and status rows. A run with nothing registered gets
    its event back unchanged and leaves no state."""
    if event.kind not in STREAM_KINDS:
        return event
    secrets = registered(run_id)
    if not secrets or run_id is None:
        return event
    content = event.content
    tail = _tail_by_run.get(run_id, "")
    # Whitespace at an event boundary is skipped when joining: the reader cannot see it, and a
    # Copilot thought is not stripped (R3). It is kept as written in the output.
    body = content.lstrip()
    lead = len(content) - len(body)
    joined = tail + body
    marked = [False] * len(joined)
    for secret in secrets:
        at = joined.find(secret)
        while at >= 0:
            for index in range(at, at + len(secret)):
                marked[index] = True
            at = joined.find(secret, at + 1)
    trimmed = joined.rstrip()
    for secret in secrets:
        for size in range(len(secret) - 1, dangling_minimum(secret) - 1, -1):
            if trimmed.endswith(secret[:size]):
                for index in range(len(trimmed) - size, len(trimmed)):
                    marked[index] = True
                break
    pieces: List[str] = [content[:lead]]
    in_mark = False
    for index in range(len(tail), len(joined)):
        if marked[index]:
            if not in_mark:
                pieces.append(REDACTED)
            in_mark = True
        else:
            pieces.append(joined[index])
            in_mark = False
    keep = len(secrets[0]) - 1
    # Assigned last, from the unredacted text, so a raise above leaves the tail as it was and a
    # value split three ways is still found.
    _tail_by_run[run_id] = trimmed[-keep:] if keep > 0 else ""
    scrubbed = "".join(pieces)
    if scrubbed == content:
        return event
    payload = dict(event.payload)
    if "text" in payload:
        payload["text"] = scrubbed
    return replace(event, content=scrubbed, payload=payload)
