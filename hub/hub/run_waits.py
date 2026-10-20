"""The operator waits a run is blocked on, so a turn's deadline can stop counting them (F783).

`the-turn-clock-counts-work-not-waiting` D1. In memory, because the run and its clock live in this
process and a Hub restart ends both. A wait is begun where the Hub learns the run is waiting (the
agent ask route, for a blocking question; the Copilot permission bracket, for an Ask me card) and
ended where it learns it is not (answer, decline, the wait-ended report, the card's answer, the
turn's end). A wait that is never ended is harmless: `paused` never counts one past its `until`,
and `begin` drops expired waits as it goes.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

#: run id -> wait key -> wall-clock second the wait ends by itself.
_waits: Dict[str, Dict[str, float]] = {}


def begin(run_id: Optional[str], key: str, until: float) -> None:
    """Record that *run_id* is waiting on the operator for *key* until *until* (epoch seconds)."""
    if not run_id:
        return
    now = time.time()
    for other in list(_waits):
        live = {k: end for k, end in _waits[other].items() if end > now}
        if live:
            _waits[other] = live
        else:
            del _waits[other]
    _waits.setdefault(run_id, {})[key] = until


def end(run_id: Optional[str], key: str) -> None:
    """The wait on *key* is over: answered, declined, given up on, or its card answered."""
    if not run_id:
        return
    waits = _waits.get(run_id)
    if waits is None:
        return
    waits.pop(key, None)
    if not waits:
        _waits.pop(run_id, None)


def clear(run_id: Optional[str]) -> None:
    """The run's turn is over; nothing it waited on can pause it any more."""
    if run_id:
        _waits.pop(run_id, None)


def paused(run_id: Optional[str], now: Optional[float] = None) -> bool:
    """Whether *run_id* is waiting on the operator at *now* (epoch seconds, default the present)."""
    if not run_id:
        return False
    waits = _waits.get(run_id)
    if not waits:
        return False
    moment = time.time() if now is None else now
    return any(until > moment for until in waits.values())
