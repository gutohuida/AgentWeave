"""Runner endpoints — CRUD for reusable execution capability records.

See openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md.
"""

from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, Runner
from ...schemas.runners import RunnerCreate, RunnerResponse, RunnerUpdate
from ...utils import short_id

router = APIRouter(prefix="/runners", tags=["runners"])


@router.post("", response_model=RunnerResponse, status_code=status.HTTP_201_CREATED)
async def create_runner(
    body: RunnerCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    runner = Runner(
        id=f"runner-{short_id()}",
        project_id=project_id,
        name=body.name,
        cli=body.cli,
        model=body.model,
        flags=body.flags,
    )
    session.add(runner)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Runner with that ID already exists"
        ) from e
    await session.refresh(runner)
    return runner


@router.get("", response_model=List[RunnerResponse])
async def list_runners(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    result = await session.execute(
        select(Runner).where(Runner.project_id == project_id).order_by(Runner.created_at)
    )
    return result.scalars().all()


@router.get("/{runner_id}", response_model=RunnerResponse)
async def get_runner(
    runner_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    runner = await session.get(Runner, runner_id)
    if runner is None or runner.project_id != project_id:
        raise HTTPException(status_code=404, detail="Runner not found")
    return runner


@router.patch("/{runner_id}", response_model=RunnerResponse)
async def update_runner(
    runner_id: str,
    body: RunnerUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    runner = await session.get(Runner, runner_id)
    if runner is None or runner.project_id != project_id:
        raise HTTPException(status_code=404, detail="Runner not found")

    if body.name is not None:
        runner.name = body.name
    if body.model is not None:
        runner.model = body.model
    if body.flags is not None:
        runner.flags = body.flags

    await session.commit()
    await session.refresh(runner)
    return runner


@router.delete("/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runner(
    runner_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    runner = await session.get(Runner, runner_id)
    if runner is None or runner.project_id != project_id:
        raise HTTPException(status_code=404, detail="Runner not found")

    bound = await session.execute(
        select(Agent.name).where(Agent.project_id == project_id, Agent.runner_id == runner_id)
    )
    bound_names = bound.scalars().all()
    if bound_names:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Runner is bound to agent(s): {', '.join(bound_names)}. Unbind before deleting.",
        )

    await session.delete(runner)
    await session.commit()
    return None
