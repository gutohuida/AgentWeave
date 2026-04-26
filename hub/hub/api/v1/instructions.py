"""Project-wide instructions endpoints."""

from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import ProjectInstructions

router = APIRouter(prefix="/project", tags=["instructions"])


@router.get("/instructions")
async def get_instructions(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return project-wide instructions content (empty string if none set)."""
    project_id, _ = project
    result = await session.execute(
        select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
    )
    row = result.scalars().first()
    if row:
        return {"content": row.content}
    return {"content": ""}


@router.put("/instructions")
async def put_instructions(
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Upsert project-wide instructions content."""
    project_id, _ = project
    content = body.get("content", "")

    result = await session.execute(
        select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
    )
    row = result.scalars().first()
    if row:
        row.content = content
    else:
        row = ProjectInstructions(project_id=project_id, content=content)
        session.add(row)

    await session.commit()
    return {"content": content}
