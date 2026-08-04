"""Instance-operator project collection and project resource endpoints."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_status import effective_heartbeat_status
from ...auth import get_operator, get_operator_project
from ...db.engine import get_session
from ...db.models import Agent, AgentHeartbeat, OperatorCredential, Project
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

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


async def _project_summary(session: AsyncSession, project: Project) -> ProjectSummary:
    agents = (
        (
            await session.execute(
                select(Agent).where(Agent.project_id == project.id).order_by(Agent.name)
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
    agent_summaries = []
    for agent in agents:
        heartbeat = latest.get(agent.name)
        effective_status, _ = effective_heartbeat_status(heartbeat)
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


@router.put("/{project_id}/settings", response_model=ProjectSettings)
async def update_project_settings(
    body: ProjectSettings,
    project_identity: Tuple[str, str] = Depends(get_operator_project),
    session: AsyncSession = Depends(get_session),
) -> ProjectSettings:
    resolved_project_id = project_identity[0]
    project = await _operator_project_row(resolved_project_id, session)
    for field, value in body.model_dump().items():
        setattr(project, field, value)
    await session.commit()

    from ...turn_scheduler import redrain_queued_agents

    await redrain_queued_agents(resolved_project_id)
    await sse_manager.broadcast(resolved_project_id, "project_settings_updated", body.model_dump())
    return body


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
