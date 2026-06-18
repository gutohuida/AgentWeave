"""API key authentication dependency."""

import hashlib
import hmac
import secrets
import time
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db.engine import get_session
from .db.models import ApiKey, Project

bearer_scheme = HTTPBearer(auto_error=False)

_TICKET_PREFIX = "aw_ticket_"
# Use a configured secret or generate an ephemeral one per process.
_TICKET_SECRET = settings.aw_ticket_secret or secrets.token_hex(32)
_TICKET_TTL = settings.aw_ticket_ttl


def _make_ticket(project_id: str) -> Tuple[str, int]:
    """Return a short-lived signed token and its expiration timestamp."""
    expires = int(time.time()) + _TICKET_TTL
    msg = f"{project_id}:{expires}".encode()
    signature = hmac.new(_TICKET_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
    token = f"{_TICKET_PREFIX}{project_id}:{expires}:{signature}"
    return token, expires


def _verify_ticket(token: str) -> Optional[str]:
    """Verify a signed ticket and return the project_id, or None if invalid/expired."""
    if not token.startswith(_TICKET_PREFIX):
        return None
    rest = token[len(_TICKET_PREFIX) :]
    parts = rest.split(":")
    if len(parts) != 3:
        return None
    project_id, expires_str, signature = parts
    try:
        expires = int(expires_str)
    except ValueError:
        return None
    if int(time.time()) > expires:
        return None
    msg = f"{project_id}:{expires}".encode()
    expected = hmac.new(_TICKET_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        return None
    return project_id


async def _project_from_api_key(api_key: str, session: AsyncSession) -> Tuple[str, str]:
    """Validate a Bearer API key and return (project_id, project_name)."""
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


async def get_project(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Tuple[str, str]:
    """Validate Bearer token and return (project_id, project_name).

    Regular REST endpoints require the API key in the Authorization header.
    Query-param fallbacks are intentionally not accepted.
    Raises 401 if the key is missing, malformed, revoked, or unknown.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return await _project_from_api_key(credentials.credentials, session)


async def get_project_for_sse(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Tuple[str, str]:
    """Authentication dependency for the SSE stream.

    EventSource cannot set custom headers, so this dependency accepts either:
      - Authorization: Bearer <aw_live_...> header, or
      - ?token=<aw_ticket_...> signed short-lived ticket from /events/ticket.

    Raw API keys in ?token= are rejected; tickets must be used for SSE.
    """
    if credentials:
        return await _project_from_api_key(credentials.credentials, session)

    if token:
        project_id = _verify_ticket(token)
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired SSE ticket",
            )
        proj_result = await session.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        project_name = project.name if project else project_id
        return project_id, project_name

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing Authorization header or SSE ticket",
    )
