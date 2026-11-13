"""Project-wide instructions endpoints.

Instructions come from the `project_instructions` row, or, where the project has chosen it, from
its AGENTS.md (`instructions_file`, spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`).
"""

from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import instructions_file
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Project, ProjectInstructions
from ...instructions_file import MAX_INSTRUCTIONS_CHARS, InstructionsSaveRefusedError
from ...project_workspace import ProjectWorkspaceError, raise_workspace_http_error
from ...schemas.common import RequestModel

__all__ = ["MAX_INSTRUCTIONS_CHARS", "router"]

router = APIRouter(prefix="/project", tags=["instructions"])


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


class InstructionsSourceUpdate(RequestModel):
    """Switch 'Use AGENTS.md as this project's instructions' on or off (FR-11)."""

    agents_md: bool


async def _project(session: AsyncSession, project_id: str) -> Project:
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def _refused(exc: InstructionsSaveRefusedError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/instructions")
async def get_instructions(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The project's instructions from their chosen source, which source that is, and whether
    using AGENTS.md is offered."""
    project_id, _ = project
    return await instructions_file.instructions_state(session, await _project(session, project_id))


@router.put("/instructions")
async def put_instructions(
    body: InstructionsUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Replace the project's instructions in their chosen source."""
    project_id, _ = project
    content = body.content
    if len(content) > MAX_INSTRUCTIONS_CHARS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "instructions_too_long",
                "message": instructions_file.too_long_message(len(content)),
                "max_chars": MAX_INSTRUCTIONS_CHARS,
            },
        )

    project_row = await _project(session, project_id)
    if project_row.instructions_in_agents_md:
        try:
            outcome = await instructions_file.save_to_agents_md(session, project_row, content)
        except InstructionsSaveRefusedError as exc:
            raise _refused(exc) from exc
        except ProjectWorkspaceError as exc:
            raise_workspace_http_error(exc)
        state = await instructions_file.instructions_state(session, project_row)
        return {**state, "committed": outcome.committed, "notice": outcome.notice}

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
    return {"content": content, "max_chars": MAX_INSTRUCTIONS_CHARS, "source": "hub"}


@router.put("/instructions/source")
async def put_instructions_source(
    body: InstructionsSourceUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Switch AGENTS.md on as the project's instructions (moving the database instructions into it
    once, FR-10), or back off to the database instructions, which were kept unchanged."""
    project_id, _ = project
    project_row = await _project(session, project_id)
    outcome = None
    if body.agents_md and not project_row.instructions_in_agents_md:
        try:
            outcome = await instructions_file.use_agents_md(session, project_row)
        except InstructionsSaveRefusedError as exc:
            raise _refused(exc) from exc
        except ProjectWorkspaceError as exc:
            raise_workspace_http_error(exc)
    elif not body.agents_md and project_row.instructions_in_agents_md:
        await instructions_file.stop_using_agents_md(session, project_row)
    state = await instructions_file.instructions_state(session, project_row)
    return {
        **state,
        "committed": bool(outcome and outcome.committed),
        "notice": outcome.notice if outcome else None,
    }
