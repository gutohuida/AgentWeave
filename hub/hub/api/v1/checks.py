"""The project's known-failing list (`hub/hub/known_failing.py`).

`GET /checks/known-failing` is the list (`failures-already-known-are-on-a-list-not-re-argued`
FR-1, FR-11): each entry's check, test or whole check, kind, first and last seen, the run that
added it and its fix task. It replaced the flaky-tests list and its "handled" action: every entry
has its own fix task, so there is nothing left to hand on or dismiss.
"""

from __future__ import annotations

from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ... import known_failing
from ...auth import get_project
from ...db.engine import get_session

checks_router = APIRouter(prefix="/checks", tags=["checks"])


@checks_router.get("/known-failing")
async def list_known_failing(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await known_failing.view(session, project_id)


@checks_router.post("/known-failing/clear-stable")
async def clear_stable_fix_tasks(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Close every open Hub-filed flaky fix task whose test is off the list, each with a note;
    tasks whose test is still listed stay open. Says how many it closed and how many it left
    (`a-disturbed-check-run-is-not-a-pile-of-flaky-tests`, FR-6)."""
    project_id, _ = project
    result = await known_failing.clear_stable_fix_tasks(session, project_id)
    await session.commit()
    return result
