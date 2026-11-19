"""One run, read by its id (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`,
FR-12).

What a run launched with — its runner record, model and reasoning effort — is the run row's own,
written at spawn; this route answers it with the run's facts, on the project credential. The
timeline's run facts (`GET /agents/{name}/timeline`) carry the same fields.
"""

from __future__ import annotations

from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Run, Runner
from ...schemas.agents import RunRead, fit_run_error

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> RunRead:
    project_id, _ = project
    run = await session.get(Run, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    runner = await session.get(Runner, run.runner_id) if run.runner_id else None
    return RunRead(
        id=run.id,
        agent=run.agent,
        conversation_id=run.conversation_id,
        task_id=run.task_id,
        initiator=run.initiator,
        # D5 of `a-turn-says-how-it-ended`: one rename at the boundary, as the timeline's facts.
        status="started" if run.status == "running" else run.status,
        exit_code=run.exit_code,
        started_at=run.started_at,
        ended_at=run.ended_at,
        outside_workspace_writes=run.outside_workspace_writes,
        harness_mcp_status=run.harness_mcp_status,
        plane_surface=run.plane_surface,
        error=fit_run_error(run.error),
        runner_id=run.runner_id,
        model=run.model,
        effort=run.effort,
        cli=runner.cli if runner is not None and runner.project_id == project_id else None,
        runner_name=runner.name if runner is not None and runner.project_id == project_id else None,
    )
