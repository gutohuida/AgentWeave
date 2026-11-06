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
