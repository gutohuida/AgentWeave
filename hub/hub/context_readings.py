"""Choosing which `context_warning` row to report as *the* context reading.

One definition, because the rule is subtle and two surfaces need it: the agent roster reports a
reading per agent, and a conversation reports its own. A second copy would drift, and the drift
would be invisible — both would still return a plausible percentage.
"""

from typing import Any, List


def usable_context_reading(rows: List[Any]) -> Any:
    """Pick the reading to report from a set of `context_warning` rows, newest first.

    Taking the newest row alone is what made Claude agents report nothing for 329 samples: the
    end-of-turn message reports a context window with no token count, so the last row to arrive
    routinely carried no usable percentage and hid the complete one behind it.

    The newest row still wins whenever it carries a percentage. Otherwise the newest row **from
    the same provider session** that does is used — scoped to the session because a compaction or
    a fresh session resets usage, and reporting a pre-reset percentage as current would be worse
    than reporting none. An unscoped fallback would do exactly that.
    """
    if not rows:
        return None
    newest = rows[0]
    if not isinstance(newest, dict) or newest.get("percent") is not None:
        return newest
    session_id = newest.get("session_id")
    if session_id is None:
        return newest
    for row in rows[1:]:
        if (
            isinstance(row, dict)
            and row.get("percent") is not None
            and row.get("session_id") == session_id
        ):
            return row
    return newest
