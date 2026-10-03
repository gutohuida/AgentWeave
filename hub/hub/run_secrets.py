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
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

REDACTED = "<redacted>"

_by_run: Dict[str, Tuple[str, ...]] = {}


def register(run_id: str, values: Iterable[Optional[str]]) -> None:
    """Hold *values* for *run_id*; empty and missing values are ignored, so a run with nothing to
    hide registers nothing. Longest first, so a value containing another is replaced whole."""
    kept = tuple(sorted({value for value in values if value}, key=len, reverse=True))
    if kept:
        _by_run[run_id] = kept


def forget(run_id: str) -> None:
    _by_run.pop(run_id, None)


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
