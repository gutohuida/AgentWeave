"""Pure helpers behind a one-shot (worker/title) call, moved out of `worker.py` (design D8).

They had to move: `worker.py` imports `hub.db.engine` for `WorkerInvocation` bookkeeping, and
`runner_adapters` must not reach the database (D1). None of the three needs anything from
`worker.py` — they only read the text a CLI already printed. `worker.py` keeps its own copies
until task 3.5 re-points it at these and deletes them, so this file can land on its own without
moving any caller yet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class WorkerUsage:
    """What one invocation consumed, normalised across providers. All fields optional.

    A provider that does not report a dimension leaves it None rather than reporting zero:
    "no reasoning tokens" and "this CLI does not tell us about reasoning tokens" are different
    facts, and only the second one should stop anybody trying to add up a bill.
    """

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cost_usd_micros: Optional[int] = None
    #: Copilot's own charge (`a-copilot-run-shows-its-credits` D5). No other runner reports them.
    ai_nano_aiu: Optional[int] = None
    premium_requests: Optional[float] = None


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """The last balanced **top-level** JSON object in *text*, or None.

    Models append rather than prepend: asked for JSON and nothing else, one that disobeys says
    "Here is the object:" first, or wraps it in a fenced block. Taking the last complete object
    handles both, and handles neither being present by returning None. Same instinct as
    `conversation_titles.title_from_output` taking the last non-empty line.

    "Top-level" is the whole difficulty. A scan that considers every `{` finds the *nested* ones
    too, and since they come later, "last" would return the innermost trailing object — for
    `{"a": {"b": 1}}` it would answer `{"b": 1}`. So a candidate that parses advances the cursor
    past its own end rather than to the next character.
    """
    decoder = json.JSONDecoder()
    found: Optional[Dict[str, Any]] = None
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            candidate, end = decoder.raw_decode(text, index)
        except ValueError:
            index += 1
            continue
        if isinstance(candidate, dict):
            found = candidate
            index = end
        else:  # pragma: no cover — raw_decode at a "{" yields a dict or raises
            index += 1
    return found


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
