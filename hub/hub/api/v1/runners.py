"""Runner endpoints — CRUD for reusable execution capability records.

See openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md.
"""

from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, Runner
from ...launchability import probe_agent
from ...model_catalog import get_provider, undeclared_model_reason
from ...runner_adapters import ADAPTERS
from ...runner_provider import (
    has_provider,
    normalised_provider_config,
    provider_config_problem,
    provider_flags_problem,
    provider_model_problem,
)
from ...schemas.runners import RunnerCreate, RunnerResponse, RunnerUpdate
from ...utils import short_id

router = APIRouter(prefix="/runners", tags=["runners"])


def _reject_undeclared_model(cli: str, model: Optional[str], current: Optional[str] = None) -> None:
    """Runner management offers catalog models, not free-typed text (runner-registry spec):
    a model is refused only when it is being newly *set* — an already-stored, unrecognised
    model (from before this catalog existed, or a future CLI release) is left alone.

    `current` is the model the runner already records, and passing it is what makes that
    second sentence true rather than accidentally true. It used to hold only because the
    free-text field dropped an untouched model from the request body; a picker's selected
    value *is* the stored model, so every save of a legacy runner carries it back here.
    Refusing that would make such a runner uneditable in every other respect as well
    (runner-registry: "A legacy runner can still be saved"). Moving it to a *different*
    undeclared model, and any undeclared model on create, stay refused.
    """
    if model is None or model == current:
        return
    provider_entry = get_provider(cli)
    if provider_entry is None or provider_entry.model(model) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=undeclared_model_reason(cli, model),
        )


def _refuse(problem: Optional[str]) -> None:
    if problem is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)


def _checked_provider(
    cli: str, provider_config: Any, model: Optional[str], flags: Optional[List[str]]
) -> dict:
    """A submitted provider, judged with the model and flags the runner will be left with.

    Design D7: the provider's model is sent to its API as is, so it must be a Claude API model id
    (never an alias, never null), and no `--model` in `flags` may override it.
    """
    _refuse(provider_config_problem(cli, provider_config))
    _refuse(provider_model_problem(model))
    _refuse(provider_flags_problem(flags))
    return normalised_provider_config(provider_config)


@router.post("", response_model=RunnerResponse, status_code=status.HTTP_201_CREATED)
async def create_runner(
    body: RunnerCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    provider_config = None
    if body.provider_config is not None:
        provider_config = _checked_provider(body.cli, body.provider_config, body.model, body.flags)
    else:
        _reject_undeclared_model(body.cli, body.model)
    runner = Runner(
        id=f"runner-{short_id()}",
        project_id=project_id,
        name=body.name,
        cli=body.cli,
        model=body.model,
        flags=body.flags,
        provider_config=provider_config,
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
    # `ADAPTERS` is `RUNNER_CLIS`, in its order (design D2; `CopilotAdapter` closed F471/F475), so
    # every runner a `Runner` row can name is listed here.
    return {"providers": {cli: probe_agent(cli, {"runner": cli}) for cli in ADAPTERS}}


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

    model_sent = "model" in body.model_fields_set
    model = body.model if model_sent else runner.model
    flags = body.flags if body.flags is not None else runner.flags
    provider_sent = "provider_config" in body.model_fields_set and (
        body.provider_config is not None or has_provider(runner.provider_config)
    )
    # Every check runs before any attribute is assigned, so a refusal stores nothing.
    if provider_sent and body.provider_config is not None:
        # Adding or replacing a provider changes which catalog the *stored* model must come from,
        # so the pair it leaves behind is judged as on create, with no legacy exemption (D7, R3).
        provider_config = _checked_provider(runner.cli, body.provider_config, model, flags)
    elif provider_sent:
        # Removing it: the model left behind must be the CLI's own again, or null.
        try:
            _reject_undeclared_model(runner.cli, model)
        except HTTPException as exc:
            exc.detail = (
                f"Without its model provider this runner runs on {runner.cli}'s own models, so "
                f"choose one of them (or none) in the same change. {exc.detail}"
            )
            raise
        provider_config = None
    elif has_provider(runner.provider_config):
        provider_config = runner.provider_config
        if model_sent:
            _refuse(provider_model_problem(model))
        if body.flags is not None:
            _refuse(provider_flags_problem(flags))
    else:
        provider_config = runner.provider_config
        # `model` is gated on whether the field was *sent*, not on whether it is non-None:
        # a picker's unset option sends an explicit `null` to mean "the provider's default",
        # and Pydantic gives that the same value as an absent key. `name` and `flags` keep
        # the `is not None` gate deliberately — design.md, "The fix distinguishes absent from
        # explicit-null ... for `model` only".
        if model_sent:
            _reject_undeclared_model(runner.cli, body.model, current=runner.model)

    if body.name is not None:
        runner.name = body.name
    if model_sent:
        runner.model = body.model
    if body.flags is not None:
        runner.flags = body.flags
    runner.provider_config = provider_config

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
        select(Agent.name, Agent.lifecycle).where(
            Agent.project_id == project_id, Agent.runner_id == runner_id
        )
    )
    bound_rows = bound.all()
    if bound_rows:
        labels = [
            f"{name} (archived)" if lifecycle == "archived" else name
            for name, lifecycle in bound_rows
        ]
        if any(lifecycle == "archived" for _, lifecycle in bound_rows):
            detail = (
                f"Runner is bound to agent(s): {', '.join(labels)}. Unbind before deleting; "
                "an archived agent is listed under Agents with the archived filter."
            )
        else:
            detail = f"Runner is bound to agent(s): {', '.join(labels)}. Unbind before deleting."
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    await session.delete(runner)
    await session.commit()
    return None
