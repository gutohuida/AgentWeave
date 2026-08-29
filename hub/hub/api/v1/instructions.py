"""Project-wide instructions endpoints."""

from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import ProjectInstructions
from ...schemas.common import RequestModel

router = APIRouter(prefix="/project", tags=["instructions"])


class InstructionsUpdate(RequestModel):
    """The body of a PUT that replaces the project's instructions.

    It used to be an untyped `dict` read with `body.get("content", "")`, which meant a
    body naming the field anything else — `contents`, `text`, a typo — answered 200 and
    **blanked the project's instructions**, because the default was the empty string and
    the empty string is a legitimate value. There is no field name a caller can send that
    is now silently discarded: `RequestModel` names it instead.
    """

    content: str = ""


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
    body: InstructionsUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Upsert project-wide instructions content."""
    project_id, _ = project
    content = body.content

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
