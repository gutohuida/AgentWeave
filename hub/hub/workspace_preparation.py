"""Which turns' checkouts the Hub is preparing right now, so the app can say so.

Preparing a checkout (`git worktree add`, a catch-up merge) runs before a turn's run exists, and on
a large repository it takes tens of seconds. Until this module nothing showed it: a new thread sat
on an empty composer and a flow's task read "Not started" while git wrote six thousand files.

Held in memory and never stored: a preparation lives inside one call of `trigger_agent_directly`,
and a restart ends every one of them. The route reads the live set, so a reload shows what is still
being prepared; the two events tell an open view when one starts and ends.

A checkout written is not yet a turn started: the run's row is written some way further into the
trigger, and until it is a task with neither reads "Not started", between "Preparing checkout" and
"Building" (TSBVD-10). So inside `holding_until_started` -- the trigger's whole call -- a preparation
that succeeds stays live until that call ends, when the run exists or the trigger was refused.
"""

from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

from .sse import sse_manager


@dataclass(frozen=True)
class Preparation:
    id: str
    project_id: str
    agent: str
    task_id: Optional[str]
    conversation_id: Optional[str]
    started_at: datetime

    def payload(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "started_at": self.started_at.isoformat(),
        }


_live: Dict[str, Preparation] = {}
_counter = 0
#: The preparations the trigger call in progress holds until it ends (`holding_until_started`).
_held: contextvars.ContextVar[Optional[List[Preparation]]] = contextvars.ContextVar(
    "workspace_preparation_held", default=None
)


def current(project_id: str) -> List[Preparation]:
    """This project's preparations in progress, oldest first."""
    return sorted(
        (p for p in _live.values() if p.project_id == project_id), key=lambda p: p.started_at
    )


def preparing_task_ids(project_id: str) -> Dict[str, datetime]:
    """Task id -> when its checkout began being prepared, for `task_stage`."""
    return {p.task_id: p.started_at for p in current(project_id) if p.task_id}


@contextlib.asynccontextmanager
async def preparing(
    project_id: str,
    *,
    agent: str,
    task_id: Optional[str],
    conversation_id: Optional[str],
) -> AsyncIterator[Preparation]:
    """Record a preparation for the duration of the block, and announce its start and end."""
    global _counter
    _counter += 1
    preparation = Preparation(
        id=f"prep-{_counter}",
        project_id=project_id,
        agent=agent,
        task_id=task_id,
        conversation_id=conversation_id,
        started_at=datetime.now(timezone.utc),
    )
    _live[preparation.id] = preparation
    await _announce("workspace_preparing", preparation)
    ok = False
    try:
        yield preparation
        ok = True
    finally:
        held = _held.get()
        if ok and held is not None:
            held.append(preparation)
        else:
            await _end(preparation, ok=ok)


@contextlib.asynccontextmanager
async def holding_until_started() -> AsyncIterator[None]:
    """Keep each preparation that succeeds inside this block live until the block ends."""
    held: List[Preparation] = []
    token = _held.set(held)
    try:
        yield
    finally:
        _held.reset(token)
        for preparation in held:
            await _end(preparation, ok=True)


async def _end(preparation: Preparation, *, ok: bool) -> None:
    _live.pop(preparation.id, None)
    await _announce("workspace_prepared", preparation, ok=ok)


async def _announce(event: str, preparation: Preparation, **extra) -> None:
    # An announcement that cannot be sent must not fail the turn it describes.
    with contextlib.suppress(Exception):
        await sse_manager.broadcast(
            preparation.project_id, event, {**preparation.payload(), **extra}
        )
