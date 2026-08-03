"""Charter endpoints — CRUD for authored agent behavior records."""

from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, Charter
from ...schemas.charters import CharterCreate, CharterResponse, CharterUpdate
from ...utils import short_id

router = APIRouter(prefix="/charters", tags=["charters"])


@router.post("", response_model=CharterResponse, status_code=status.HTTP_201_CREATED)
async def create_charter(
    body: CharterCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    charter = Charter(
        id=f"charter-{short_id()}",
        project_id=project_id,
        name=body.name,
        content=body.content,
    )
    session.add(charter)
    await session.commit()
    await session.refresh(charter)
    return charter


@router.get("", response_model=List[CharterResponse])
async def list_charters(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    result = await session.execute(
        select(Charter).where(Charter.project_id == project_id).order_by(Charter.created_at)
    )
    return result.scalars().all()


@router.get("/{charter_id}", response_model=CharterResponse)
async def get_charter(
    charter_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    charter = await session.get(Charter, charter_id)
    if charter is None or charter.project_id != project_id:
        raise HTTPException(status_code=404, detail="Charter not found")
    return charter


@router.patch("/{charter_id}", response_model=CharterResponse)
async def update_charter(
    charter_id: str,
    body: CharterUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    charter = await session.get(Charter, charter_id)
    if charter is None or charter.project_id != project_id:
        raise HTTPException(status_code=404, detail="Charter not found")

    if body.name is not None:
        charter.name = body.name
    if body.content is not None:
        charter.content = body.content

    await session.commit()
    await session.refresh(charter)
    return charter


@router.delete("/{charter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_charter(
    charter_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    charter = await session.get(Charter, charter_id)
    if charter is None or charter.project_id != project_id:
        raise HTTPException(status_code=404, detail="Charter not found")

    bound = await session.execute(
        select(Agent.name).where(Agent.project_id == project_id, Agent.charter_id == charter_id)
    )
    bound_names = bound.scalars().all()
    if bound_names:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Charter is bound to agent(s): {', '.join(bound_names)}. Unbind before deleting.",
        )

    await session.delete(charter)
    await session.commit()
    return None
