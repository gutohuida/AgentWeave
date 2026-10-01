"""Waiting, in process, for one run's tool server to announce itself.

`a-run-reaches-the-hub-without-mcp`, design D9. A runner whose harness starts its MCP servers
before the Hub sends the first prompt (Copilot over ACP: inside `session/new`) can compose that
prompt from this run's own answer instead of a guess. The adapter posts
`POST /agent-actions/mcp-adapter-online` before it serves; the route commits the stamp and then
calls `notify`; the transport `wait`s, bounded.

`wait` **registers before it checks** the row (review fix 5). The announce is expected about the
moment `session/new` returns, so an announce committed between a check and a later registration
would notify no one, and the run would be told it has no tool server while holding one. It also
re-checks the row every poll step, so a notification lost any other way costs one poll, and it is
total: a failing check counts as "not yet", ending at the timeout as `absent` -- the safe
direction, since the call command still works.

In-process only, by design: the route and the transport run in the same Hub process.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

#: How long a runner that tests before its first prompt waits for its run's announce. The pinned
#: server's fastmcp import alone is ~1.4 s and the announce is expected ~2-2.5 s after
#: `session/new` is sent (design D9, measured on Copilot 1.0.88), so this is a margin of ~6x.
MCP_ANNOUNCE_WAIT_SECONDS = 15.0

#: The longest the wait goes between checks of the row and of `should_interrupt`.
POLL_SECONDS = 0.25

_waiters: Dict[str, asyncio.Event] = {}


def notify(run_id: str) -> None:
    """Wake a wait on *run_id*, if one is registered. Called after the announce's commit.

    Never raises: by then the route's write has landed, and a 500 would tell the adapter the
    announce failed when it did not. A lost notification costs the waiter one poll.
    """
    try:
        event = _waiters.get(run_id)
        if event is not None:
            event.set()
    except Exception:  # noqa: BLE001
        logger.warning("waking the announce wait for run %s failed", run_id, exc_info=True)


async def _stamped(run_id: str) -> bool:
    from .db.engine import async_session_factory
    from .db.models import Run

    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        return run is not None and run.mcp_adapter_online_at is not None


async def _check(run_id: str) -> bool:
    try:
        return await _stamped(run_id)
    except Exception:  # noqa: BLE001 -- total by contract: a failed check is "not yet"
        logger.warning(
            "checking run %s for its tool server's announce failed", run_id, exc_info=True
        )
        return False


async def wait(
    run_id: str,
    timeout: float,
    *,
    should_interrupt: Optional[Callable[[], bool]] = None,
) -> bool:
    """True once *run_id*'s tool server has announced, False at *timeout* or on interrupt.

    Never raises. Honours *should_interrupt* within one poll interval.
    """
    event = _waiters.setdefault(run_id, asyncio.Event())
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if event.is_set() or await _check(run_id):
                return True
            if should_interrupt is not None:
                try:
                    if should_interrupt():
                        return False
                except Exception:  # noqa: BLE001 -- an interrupt check that fails is not a stop
                    logger.warning("interrupt check failed during the announce wait", exc_info=True)
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=min(POLL_SECONDS, remaining))
    finally:
        if _waiters.get(run_id) is event:
            del _waiters[run_id]
