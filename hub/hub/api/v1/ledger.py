"""The project's ledger: merges, spend, divergences, messages, origins and folded notices."""

from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...project_ledger import ledger

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("")
async def get_ledger(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await ledger(session, project_id)
