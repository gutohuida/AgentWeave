"""Project settings API - YOLO mode configuration."""

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from hub.db.engine import get_session
from hub.db.models import Project

router = APIRouter()


class YoloSettings(BaseModel):
    """YOLO mode settings for agents."""

    claude: bool = False
    kimi: bool = False
    gemini: bool = False
    codex: bool = False
    opencode: bool = False


class ProjectSettings(BaseModel):
    """Project settings response."""

    project_id: str
    allow_add_agents: bool
    yolo: YoloSettings


class UpdateYoloRequest(BaseModel):
    """Request to update YOLO settings."""

    agent: str
    enabled: bool


async def _get_project(
    project_auth: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> Project:
    """Get Project from auth tuple."""
    project_id, _ = project_auth
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/settings", response_model=ProjectSettings)
async def get_settings(
    project: Project = Depends(_get_project),
) -> Dict[str, Any]:
    """Get project settings including YOLO mode configuration."""
    proj_settings = project.settings or {}
    yolo_settings = proj_settings.get("yolo", {})

    return {
        "project_id": project.id,
        "allow_add_agents": proj_settings.get("allow_add_agents", True),
        "yolo": {
            "claude": yolo_settings.get("claude", False),
            "kimi": yolo_settings.get("kimi", False),
            "gemini": yolo_settings.get("gemini", False),
            "codex": yolo_settings.get("codex", False),
            "opencode": yolo_settings.get("opencode", False),
        },
    }


@router.post("/settings/yolo", response_model=ProjectSettings)
async def update_yolo(
    request: UpdateYoloRequest,
    session: AsyncSession = Depends(get_session),
    project: Project = Depends(_get_project),
) -> Dict[str, Any]:
    """Enable or disable YOLO mode for an agent."""
    valid_agents = {"claude", "kimi", "gemini", "codex", "opencode"}
    agent = request.agent.lower()

    if agent not in valid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent. Must be one of: {', '.join(valid_agents)}",
        )

    # Get current settings
    settings = project.settings or {}
    yolo_settings = settings.get("yolo", {})

    # Update YOLO setting for the agent
    yolo_settings[agent] = request.enabled
    settings["yolo"] = yolo_settings
    project.settings = settings

    await session.commit()

    return {
        "project_id": project.id,
        "allow_add_agents": settings.get("allow_add_agents", True),
        "yolo": {
            "claude": yolo_settings.get("claude", False),
            "kimi": yolo_settings.get("kimi", False),
            "gemini": yolo_settings.get("gemini", False),
            "codex": yolo_settings.get("codex", False),
            "opencode": yolo_settings.get("opencode", False),
        },
    }


@router.get("/settings/yolo/{agent}")
async def get_yolo_status(
    agent: str,
    project: Project = Depends(_get_project),
) -> Dict[str, Any]:
    """Get YOLO mode status for a specific agent."""
    valid_agents = {"claude", "kimi", "gemini", "codex", "opencode"}
    agent = agent.lower()

    if agent not in valid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent. Must be one of: {', '.join(valid_agents)}",
        )

    settings = project.settings or {}
    yolo_settings = settings.get("yolo", {})

    return {
        "agent": agent,
        "enabled": yolo_settings.get(agent, False),
    }
