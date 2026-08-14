"""Instance-operator project collection and project resource endpoints."""

from __future__ import annotations

import contextlib
import copy
from datetime import datetime
from typing import List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic.fields import FieldInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_status import effective_heartbeat_status
from ...auth import get_operator, get_operator_project
from ...checkpoint_policy import threshold_error, window_for
from ...db.engine import get_session
from ...db.models import Agent, AgentHeartbeat, OperatorCredential, Project, Run, Runner
from ...project_lifecycle import ProjectLifecycleService
from ...project_workspace import (
    ProjectPathError,
    ProjectWorkspaceError,
    raise_workspace_http_error,
    resolve_project_workspace,
)
from ...sse import sse_manager

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectAgentSummary(BaseModel):
    id: str
    name: str
    color_index: Optional[int]
    status: str
    last_seen: Optional[datetime]


class ProjectSummary(BaseModel):
    id: str
    name: str
    working_directory: Optional[str]
    path_display: Optional[str]
    directory_state: str
    last_opened_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    hop_budget: int
    turn_delivery_cap: int
    agent_budget: int
    token_budget: Optional[int]
    allow_agent_jobs: bool
    agents: List[ProjectAgentSummary]


class ProjectPathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    register_copy_as_new: bool = False

    model_config = {"extra": "forbid"}


class ProjectRelocateRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)

    model_config = {"extra": "forbid"}


class ProjectSettings(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    hop_budget: int = Field(ge=1, le=1000)
    turn_delivery_cap: int = Field(ge=1, le=1000)
    agent_budget: int = Field(ge=1, le=1000)
    token_budget: Optional[int] = Field(default=None, gt=0)
    allow_agent_jobs: bool
    # How conversations are named. `truncate` costs nothing and is the default; `generate`
    # spends the operator's tokens on a one-shot spawn, which is their choice to make.
    # Defaulted rather than required so a client written before this field still round-trips.
    conversation_title_mode: Literal["truncate", "generate"] = "truncate"
    # Which of the project's runners does the titling. Null falls back to the agent's own.
    conversation_title_runner_id: Optional[str] = Field(default=None, max_length=64)

    # --- Checkpointing ---
    # `off` by default. `offered` generates a checkpoint at the threshold and leaves the cutover
    # to the operator; `automatic` also opens the successor and archives the predecessor.
    # Generation happens under both, because the offer is "I made one, cut over?" rather than
    # "shall I make one?" — there is nothing to ask permission for, and asking would mean
    # generating later from a context that has degraded in the meantime.
    checkpoint_mode: Literal["off", "offered", "automatic"] = "off"
    checkpoint_threshold_mode: Optional[Literal["percent", "tokens"]] = None
    # Canonical units: 0-100 under `percent`, an actual token count under `tokens`. A surface
    # collecting thousands converts before sending.
    checkpoint_threshold_value: Optional[int] = Field(default=None, gt=0)
    checkpoint_notes_value: Optional[int] = Field(default=None, gt=0)
    checkpoint_runner_id: Optional[str] = Field(default=None, max_length=64)
    checkpoint_model: Optional[str] = Field(default=None, max_length=256)
    # Whether a successor starts working the moment it is handed its checkpoint. Off means an
    # explicit Continue button, not "type a message to get it moving".
    checkpoint_auto_continue: bool = False

    # --- Integration ---
    # The branch approval merges into. Null means "not chosen", and nothing merges. Deliberately
    # not defaulted from a detected name: guessing is safe for a report and unsafe for a write, so
    # a detected branch is offered as a suggestion and takes effect only once it is submitted here.
    main_branch: Optional[str] = Field(default=None, max_length=255)

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_threshold(self) -> "ProjectSettings":
        """A threshold is a mode and a value together, or neither.

        Half a threshold is not a partial setting to be completed from elsewhere — a value of
        `150` inheriting `percent` reads as 150% and never fires.
        """
        if (self.checkpoint_threshold_mode is None) != (self.checkpoint_threshold_value is None):
            raise ValueError(
                "checkpoint_threshold_mode and checkpoint_threshold_value must be set together"
            )
        if self.checkpoint_threshold_mode is not None:
            error = threshold_error(
                self.checkpoint_threshold_mode,
                self.checkpoint_threshold_value,
                context_window=window_for(self.checkpoint_model),
            )
            if error:
                raise ValueError(error)
        if self.checkpoint_notes_value is not None:
            if self.checkpoint_threshold_value is None:
                raise ValueError("a notes point needs a threshold to sit below")
            if self.checkpoint_notes_value >= self.checkpoint_threshold_value:
                raise ValueError(
                    "the notes point must be below the checkpoint threshold, or notes are "
                    "written from the context the checkpoint exists to escape"
                )
        return self


#: The body of a settings change: every field of `ProjectSettings`, all optional.
#:
#: The handler has always merged onto what is stored, so that omitting a field means "unchanged".
#: That merge was unreachable — `ProjectSettings` has five required fields, so a body naming only
#: what it wanted to change was refused by request validation before the handler ever ran, and the
#: comment promising otherwise described behaviour nothing could reach.
#:
#: **Derived from `ProjectSettings`, not retyped.** The handler writes back with `setattr` over the
#: merged model's fields, so a field present here and absent there would validate, merge, and
#: silently write nothing. Deriving makes that impossible rather than merely unlikely.
#:
#: Per-field constraints **are** carried over, so that a body with several bad values is answered
#: with all of them rather than with whichever one request validation reached first. Cross-field
#: rules are **not**: `validate_threshold` judges a whole settings object, and a lone notes value is
#: valid when the project already stores the threshold it sits below. Those are re-checked against
#: the merged object at the point of use, which is the only place they can be judged at all.
def _as_optional(field: FieldInfo) -> FieldInfo:
    """The same field, its constraints intact, no longer required."""
    relaxed = copy.deepcopy(field)
    relaxed.default = None
    relaxed.default_factory = None
    return relaxed


ProjectSettingsUpdate = create_model(  # type: ignore[call-overload]
    "ProjectSettingsUpdate",
    __config__=ConfigDict(extra="forbid"),
    **{
        name: (Optional[field.annotation], _as_optional(field))
        for name, field in ProjectSettings.model_fields.items()
    },
)


async def _project_summary(session: AsyncSession, project: Project) -> ProjectSummary:
    # The second roster, and the one the navigation rail actually draws from — `Sidebar` reads
    # `useProjects()`, not `useAgents()`. Archived agents are excluded here as well as in
    # `list_agents`; filtering only that one endpoint left an archived agent still listed in the
    # rail and counted in the project's agent total.
    agents = (
        (
            await session.execute(
                select(Agent)
                .where(Agent.project_id == project.id, Agent.lifecycle == "open")
                .order_by(Agent.name)
            )
        )
        .scalars()
        .all()
    )
    heartbeat_rows = (
        (
            await session.execute(
                select(AgentHeartbeat)
                .where(AgentHeartbeat.project_id == project.id)
                .order_by(AgentHeartbeat.agent, AgentHeartbeat.timestamp.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, AgentHeartbeat] = {}
    for heartbeat in heartbeat_rows:
        latest.setdefault(heartbeat.agent, heartbeat)
    # Agents with a direct-spawn run in progress. A Hub-triggered run
    # (agent_trigger.py) never posts a heartbeat, and nothing else in the
    # Hub-native runtime does either, so a heartbeat-only status would leave
    # the rail dot grey for the whole duration of a live run. This mirrors
    # agents.py's `agents_with_active_run`; the two must agree, or the rail
    # and the panels disagree about the same agent.
    running_run_rows = await session.execute(
        select(Run.agent).where(
            Run.project_id == project.id,
            Run.status == "running",
        )
    )
    agents_with_active_run = {name for (name,) in running_run_rows}
    agent_summaries = []
    for agent in agents:
        heartbeat = latest.get(agent.name)
        effective_status, _ = effective_heartbeat_status(heartbeat)
        if agent.name in agents_with_active_run:
            effective_status = "running"
        agent_summaries.append(
            ProjectAgentSummary(
                id=agent.id,
                name=agent.name,
                color_index=agent.color_index,
                status=effective_status,
                last_seen=heartbeat.timestamp if heartbeat else None,
            )
        )
    return ProjectSummary(
        id=project.id,
        name=project.name,
        working_directory=project.working_directory,
        path_display=project.working_directory,
        directory_state=project.directory_state,
        last_opened_at=project.last_opened_at,
        last_seen_at=project.last_seen_at,
        hop_budget=project.hop_budget,
        turn_delivery_cap=project.turn_delivery_cap,
        agent_budget=project.agent_budget,
        token_budget=project.token_budget,
        allow_agent_jobs=project.allow_agent_jobs,
        agents=agent_summaries,
    )


async def _refresh_project_observation(session: AsyncSession, project: Project) -> None:
    """Refresh directory state without making collection reads fail.

    Missing and conflicting projects remain listable so the operator can reach their
    repair action. The workspace resolver records the typed state before raising.
    """
    with contextlib.suppress(ProjectWorkspaceError):
        await resolve_project_workspace(session, project.id)


@router.get("", response_model=List[ProjectSummary])
async def list_projects(
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
) -> List[ProjectSummary]:
    del operator
    projects = (
        (await session.execute(select(Project).order_by(Project.last_opened_at.desc(), Project.id)))
        .scalars()
        .all()
    )
    for project in projects:
        await _refresh_project_observation(session, project)
    await session.commit()
    return [await _project_summary(session, project) for project in projects]


@router.post("/open", response_model=ProjectSummary)
async def open_project(
    body: ProjectPathRequest,
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
) -> ProjectSummary:
    del operator
    try:
        project = await ProjectLifecycleService(session).open_existing(
            body.path,
            name=body.name,
            register_copy_as_new=body.register_copy_as_new,
        )
    except ProjectWorkspaceError as exc:
        raise_workspace_http_error(exc)

    from ...turn_scheduler import redrain_queued_agents

    await redrain_queued_agents(project.id)
    await sse_manager.broadcast(
        project.id,
        "project_opened",
        {"id": project.id, "name": project.name, "directory_state": project.directory_state},
    )
    return await _project_summary(session, project)


@router.post("/create", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectPathRequest,
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
) -> ProjectSummary:
    del operator
    try:
        project = await ProjectLifecycleService(session).create_new(body.path, name=body.name)
    except ProjectWorkspaceError as exc:
        raise_workspace_http_error(exc)
    await sse_manager.broadcast(
        project.id,
        "project_created",
        {"id": project.id, "name": project.name, "directory_state": project.directory_state},
    )
    return await _project_summary(session, project)


async def _operator_project_row(project_id: str, session: AsyncSession) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=ProjectSummary)
async def get_project_detail(
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> ProjectSummary:
    project = await _operator_project_row(project_identity[0], session)
    await _refresh_project_observation(session, project)
    await session.commit()
    return await _project_summary(session, project)


@router.get("/{project_id}/settings", response_model=ProjectSettings)
async def get_project_settings(
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> ProjectSettings:
    project = await _operator_project_row(project_identity[0], session)
    return ProjectSettings.model_validate(project, from_attributes=True)


@router.get("/{project_id}/main-branch-suggestion")
async def suggest_main_branch(
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """A branch the operator might mean, and the one they have chosen.

    A suggestion, never an assignment. `chosen` being null is what stops anything merging, and this
    route exists so that state is a decision the operator makes once rather than a guess the system
    makes on their behalf every time.
    """
    from ... import project_workspace, task_integration

    project = await _operator_project_row(project_identity[0], session)
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project.id)
    except project_workspace.ProjectWorkspaceError:
        return {"suggestion": None, "chosen": project.main_branch, "is_repository": False}

    return {
        "suggestion": task_integration.detect_main_branch(workspace.root),
        "chosen": project.main_branch,
        "is_repository": task_integration.is_repository(workspace.root),
    }


@router.put("/{project_id}/settings", response_model=ProjectSettings)
async def update_project_settings(
    body: ProjectSettingsUpdate,  # type: ignore[valid-type]
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> ProjectSettings:
    resolved_project_id = project_identity[0]
    project = await _operator_project_row(resolved_project_id, session)

    # Merge onto what is stored, rather than replacing from the model's defaults.
    #
    # Every field here carries a default, so a client submitting only the fields it knows about
    # used to reset the rest — silently, with a 200. Observed: a settings save clearing a
    # project's entire checkpoint configuration, because the panel's `ProjectSettingsInput` is a
    # `Pick` of `ProjectSummary` and cannot see those fields at all. The note on
    # `conversation_title_mode` — "defaulted so a client written before this field still
    # round-trips" — was reaching for exactly this and did not achieve it.
    #
    # `exclude_unset` distinguishes "not sent" from "sent as null", so omission means unchanged
    # and a deliberate clear is still expressible.
    current = ProjectSettings.model_validate(project, from_attributes=True)
    submitted = body.model_dump(exclude_unset=True)
    try:
        # Validated against the *merged* state, not the fragment. Validating the fragment would
        # refuse a lone notes value for wanting a threshold the project already has.
        merged = ProjectSettings.model_validate({**current.model_dump(), **submitted})
    except PydanticValidationError as exc:
        # `include_context=False` because a `model_validator` failure carries the raised
        # `ValueError` itself in `ctx`, which cannot be JSON-encoded — FastAPI turns the 422 into a
        # 500 while serialising the refusal. Latent until a partial body made cross-field rules
        # reachable here at all; every earlier failure was a field error that request validation
        # had already caught and rendered.
        raise HTTPException(
            status_code=422, detail=exc.errors(include_url=False, include_context=False)
        ) from exc

    # Not ForeignKeys — `runners.project_id` already points at `projects`, and closing the loop
    # would make the two unsortable for DDL. Checked here instead, which is also where a
    # cross-project runner id has to be refused anyway.
    for field_name in ("conversation_title_runner_id", "checkpoint_runner_id"):
        runner_id = getattr(merged, field_name)
        if not runner_id:
            continue
        runner = await session.get(Runner, runner_id)
        if runner is None or runner.project_id != resolved_project_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown runner '{runner_id}': no runner by that id belongs to this project"
                ),
            )
    # A merge target that does not exist would fail silently at approval time, recorded as a skip
    # nobody expected. Refused here instead, where the operator is looking at the field.
    if merged.main_branch and merged.main_branch != project.main_branch:
        from ... import project_workspace, task_integration

        try:
            workspace = await project_workspace.resolve_project_workspace(
                session, resolved_project_id
            )
        except project_workspace.ProjectWorkspaceError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Project workspace is unavailable, so a branch cannot be checked: {exc}",
            ) from exc
        if not task_integration.branch_exists(workspace.root, merged.main_branch):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This project has no branch named '{merged.main_branch}'. "
                    "Approval merges into it, so it has to exist first."
                ),
            )

    for field, value in merged.model_dump().items():
        setattr(project, field, value)
    await session.commit()

    from ...turn_scheduler import redrain_queued_agents

    await redrain_queued_agents(resolved_project_id)
    await sse_manager.broadcast(
        resolved_project_id, "project_settings_updated", merged.model_dump()
    )
    return merged


@router.post("/{project_id}/relocate", response_model=ProjectSummary)
async def relocate_project(
    body: ProjectRelocateRequest,
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> ProjectSummary:
    try:
        project = await ProjectLifecycleService(session).relocate(project_identity[0], body.path)
    except ProjectPathError as exc:
        if exc.code == "project_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            ) from exc
        raise_workspace_http_error(exc)
    except ProjectWorkspaceError as exc:
        raise_workspace_http_error(exc)

    from ...turn_scheduler import redrain_queued_agents

    await redrain_queued_agents(project.id)
    await sse_manager.broadcast(
        project.id,
        "project_relocated",
        {"id": project.id, "name": project.name, "directory_state": project.directory_state},
    )
    return await _project_summary(session, project)
