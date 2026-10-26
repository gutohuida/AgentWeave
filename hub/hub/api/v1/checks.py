"""The project's flaky tests, as the approval checks found them (`hub/hub/flaky_tests.py`).

`GET /checks/flaky` lists them; `POST /checks/flaky/handled` is the operator dealing with the list —
handing it to a new task (`create_task`) or dismissing it — so it stays quiet until a test flakes
again.
"""

from __future__ import annotations

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ... import flaky_tests
from ...auth import get_project
from ...db.engine import get_session
from ...schemas.tasks import TaskCreate
from ...task_transitions import operator
from .tasks import create_task_for_actor

checks_router = APIRouter(prefix="/checks", tags=["checks"])


class FlakyHandled(BaseModel):
    #: Make a pending task asking for the listed flakes to be fixed; otherwise just dismiss them.
    create_task: bool = True
    #: Who the task goes to; unassigned when absent.
    assignee: Optional[str] = None

    model_config = {"extra": "forbid"}


@checks_router.get("/flaky")
async def list_flaky_tests(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await flaky_tests.report(session, project_id)


@checks_router.post("/flaky/handled")
async def handle_flaky_tests(
    body: FlakyHandled,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    current = await flaky_tests.report(session, project_id)
    flaky = current["flaky"]
    if not flaky:
        raise HTTPException(status.HTTP_409_CONFLICT, "No flaky tests are open")
    through = max(f["last_seen"] for f in flaky if f["last_seen"])
    task_id = None
    if body.create_task:
        title, description = flaky_tests.fix_task_text(flaky)
        task = await create_task_for_actor(
            TaskCreate(title=title, description=description, assignee=body.assignee),
            project_id=project_id,
            assigner=None,
            created_by_run_id=None,
            actor=operator(),
            session=session,
        )
        task_id = task.id
    await flaky_tests.mark_handled(
        session, project_id, through=through, task_id=task_id, count=len(flaky)
    )
    return {"task_id": task_id, "count": len(flaky), "through": through}
