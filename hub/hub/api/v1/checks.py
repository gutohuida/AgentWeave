"""The project's known-failing list (`hub/hub/known_failing.py`).

`GET /checks/known-failing` is the list (`failures-already-known-are-on-a-list-not-re-argued`
FR-1, FR-11): each entry's check, test or whole check, kind, first and last seen, the run that
added it and its fix task. It replaced the flaky-tests list and its "handled" action: every entry
has its own fix task, so there is nothing left to hand on or dismiss.

`GET /checks/quarantine` is the project's quarantine (`the-slow-checks-run-once-per-landing-not-once-
per-task-and-flaky-tests-are-quarantined`, `hub/hub/quarantine.py`): each quarantined test, the
never-quarantine marks and the two settings, which are written through the project's settings
route. `PUT /checks/quarantine/marks` (body `{check, test}`) sets a mark and `DELETE` (query `check`, `test`)
removes it (FR-8).
"""

from __future__ import annotations

from typing import Tuple

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import known_failing, quarantine
from ...auth import get_project
from ...db.engine import get_session
from ...schemas.common import RequestModel

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


@checks_router.get("/quarantine")
async def list_quarantine(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await quarantine.view(session, project_id)


class QuarantineMark(RequestModel):
    """A check's test, as its report names it."""

    check: str = Field(min_length=1, max_length=255)
    test: str = Field(min_length=1, max_length=1024)


@checks_router.put("/quarantine/marks")
async def set_never_quarantine_mark(
    body: QuarantineMark,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Mark a test never to be quarantined; a quarantined one leaves at once (FR-8)."""
    project_id, _ = project
    released = await quarantine.set_mark(session, project_id, body.check, body.test)
    return {**await quarantine.view(session, project_id), "released": released}


@checks_router.delete("/quarantine/marks")
async def remove_never_quarantine_mark(
    check: str = Query(min_length=1, max_length=255),
    test: str = Query(min_length=1, max_length=1024),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Remove a test's never-quarantine mark: its next flip above the threshold may admit it."""
    project_id, _ = project
    removed = await quarantine.remove_mark(session, project_id, check, test)
    return {**await quarantine.view(session, project_id), "removed": removed}
