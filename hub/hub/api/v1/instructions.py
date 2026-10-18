"""Project-wide instructions endpoints."""

from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import ProjectInstructions
from ...schemas.common import RequestModel

router = APIRouter(prefix="/project", tags=["instructions"])

#: The most characters project instructions may hold (F686). They are prepended to every agent
#: turn, so their size is paid in input tokens on each one: 300,000 characters were accepted and
#: carried by every later turn (~70k input tokens for a Haiku first turn). 40,000 is the size at
#: which Claude Code itself warns that a CLAUDE.md is large enough to hurt.
MAX_INSTRUCTIONS_CHARS = 40_000


class InstructionsUpdate(RequestModel):
    """The body of a PUT that replaces the project's instructions.

    It used to be an untyped `dict` read with `body.get("content", "")`, which meant a
    body naming the field anything else — `contents`, `text`, a typo — answered 200 and
    **blanked the project's instructions**, because the default was the empty string and
    the empty string is a legitimate value. There is no field name a caller can send that
    is now silently discarded: `RequestModel` names it instead.

    `content` is required (F647): `{}` used to clear the instructions too, bypassing the app's
    "no history and no undo" confirmation. Clearing is an explicit `{"content": ""}`.
    """

    content: str


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
    return {"content": row.content if row else "", "max_chars": MAX_INSTRUCTIONS_CHARS}


@router.put("/instructions")
async def put_instructions(
    body: InstructionsUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Upsert project-wide instructions content."""
    project_id, _ = project
    content = body.content
    if len(content) > MAX_INSTRUCTIONS_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "instructions_too_long",
                "message": (
                    f"These instructions are {len(content):,} characters; the limit is "
                    f"{MAX_INSTRUCTIONS_CHARS:,}. They are sent with every agent turn, so their "
                    "size is paid on each one. Shorten them, or keep reference material in the "
                    "project's files or knowledge vault and point to it from here."
                ),
                "max_chars": MAX_INSTRUCTIONS_CHARS,
            },
        )

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
    return {"content": content, "max_chars": MAX_INSTRUCTIONS_CHARS}
