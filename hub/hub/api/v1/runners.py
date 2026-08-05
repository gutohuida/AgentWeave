"""Runner endpoints — CRUD for reusable execution capability records.

See openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md.
"""

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, Runner
from ...launchability import probe_agent
from ...model_catalog import get_provider
from ...schemas.runners import RunnerCreate, RunnerResponse, RunnerUpdate
from ...utils import short_id

router = APIRouter(prefix="/runners", tags=["runners"])


def _reject_undeclared_model(cli: str, model: Optional[str]) -> None:
    """Runner management offers catalog models, not free-typed text (runner-registry spec):
    a model is refused only when it is being newly *set* — an already-stored, unrecognised
    model (from before this catalog existed, or a future CLI release) is left alone."""
    if model is None:
        return
    provider_entry = get_provider(cli)
    if provider_entry is None or provider_entry.model(model) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{model!r} is not a model {cli!r} declares",
        )


@router.post("", response_model=RunnerResponse, status_code=status.HTTP_201_CREATED)
async def create_runner(
    body: RunnerCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    _reject_undeclared_model(body.cli, body.model)
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


@router.get("/launchability")
async def list_runner_launchability(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    result = await session.execute(select(Runner).where(Runner.project_id == project_id))
    return {
        "runners": {
            runner.id: probe_agent(
                runner.name,
                {"runner": runner.cli, "model": runner.model},
            )
            for runner in result.scalars().all()
        }
    }


@router.get("/launchability-by-provider")
async def list_provider_launchability(
    project: Tuple[str, str] = Depends(get_project),
):
    """Launchability per catalog provider, independent of whether a runner row exists yet.

    Backs agent creation by provider and model (2026-08-04-hub-model-control-and-provisioning
    design.md): the operator must see a provider's launchability *before* choosing a model, and
    no runner exists yet to probe at that point.
    """
    del project
    from ...db.models import RUNNER_CLIS

    return {"providers": {cli: probe_agent(cli, {"runner": cli}) for cli in RUNNER_CLIS}}


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
        _reject_undeclared_model(runner.cli, body.model)
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
