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

from typing import Optional, Tuple

_bound_address: Optional[Tuple[str, int]] = None


def observe(host: str, port: int) -> None:
    global _bound_address
    _bound_address = (host, port)


def get() -> Optional[Tuple[str, int]]:
    return _bound_address
