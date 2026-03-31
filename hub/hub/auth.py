"""API key authentication dependency."""

from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import get_session
from .db.models import ApiKey, Project

bearer_scheme = HTTPBearer(auto_error=False)


async def get_project(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    token: Optional[str] = Query(None),  # for EventSource SSE connections
    session: AsyncSession = Depends(get_session),
) -> Tuple[str, str]:
    """Validate Bearer token and return (project_id, project_name).

    Accepts token via Authorization header or ?token= query param (for SSE/EventSource).
    Raises 401 if the key is missing, malformed, revoked, or unknown.
    """
    api_key = (credentials.credentials if credentials else None) or token
    if not api_key or not api_key.startswith("aw_live_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key must start with 'aw_live_'",
        )

    result = await session.execute(
        select(ApiKey).where(ApiKey.id == api_key, ApiKey.revoked == False)  # noqa: E712
    )
    key_row = result.scalar_one_or_none()
    if key_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    proj_result = await session.execute(select(Project).where(Project.id == key_row.project_id))
    project = proj_result.scalar_one_or_none()
    project_name = project.name if project else key_row.project_id

    return key_row.project_id, project_name
