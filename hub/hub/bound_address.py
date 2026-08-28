"""Tracks the Hub's actually-bound socket address, observed from real connections.

`settings.aw_port` describes configured *intent* — a value uvicorn can be told to
override by CLI flag, env var, or `port=0`, none of which flow back through
`settings`. This module holds the port observed from an actually-accepted
connection instead, so an agent's callback address can be derived from fact
rather than from a configuration value that may have silently diverged from
where the Hub is really listening.

Populated by middleware in `main.py` on every request. Read by
`agent_trigger.py` when building a run's `HUB_URL`. A module-level global
(rather than `app.state`) because `trigger_agent_directly` is deliberately
decoupled from any FastAPI `Request` — the scheduler calls it directly with no
request in flight.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

_bound_address: Optional[Tuple[str, int]] = None


def observe(host: str, port: int) -> None:
    global _bound_address
    _bound_address = (host, port)


def get() -> Optional[Tuple[str, int]]:
    return _bound_address


def known() -> bool:
    """Can a spawned run be told where to call back?

    Either half is sufficient and they are not interchangeable: an explicit `HUB_URL` is
    configuration the Hub was given, and an observed address is fact it measured. `agent_trigger`
    prefers the first and falls back to the second, so anything asking *whether* a run can be
    spawned at all has to ask about both — which is why this lives here rather than being spelled
    out at each call site. It was spelled out at two of them, and a third (the startup re-drain in
    `run_reconciliation`) did not ask at all.

    Reads the observed half through `get()` rather than the global directly, so that the several
    tests which patch `get` to describe a Hub with no observed address keep describing one.
    """
    return bool(os.environ.get("HUB_URL")) or get() is not None
