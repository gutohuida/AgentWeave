"""API key authentication dependency."""

import hashlib
import hmac
import secrets
import time
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db.engine import get_session
from .db.models import OperatorCredential, Project

bearer_scheme = HTTPBearer(auto_error=False)

_TICKET_PREFIX = "aw_ticket_"
_OPERATOR_TICKET_PREFIX = "aw_optick_"
# Use a configured secret or generate an ephemeral one per process.
_TICKET_SECRET = settings.aw_ticket_secret or secrets.token_hex(32)
_TICKET_TTL = settings.aw_ticket_ttl


def _make_operator_ticket() -> Tuple[str, int]:
    """Return a short-lived signed token for the one instance-level operator
    stream — scoped to the operator, not to any single project."""
    expires = int(time.time()) + _TICKET_TTL
    msg = f"operator:{expires}".encode()
    signature = hmac.new(_TICKET_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
    token = f"{_OPERATOR_TICKET_PREFIX}{expires}:{signature}"
    return token, expires


def _verify_operator_ticket(token: str) -> bool:
    """Verify a signed operator ticket. Returns True if valid and unexpired."""
    if not token.startswith(_OPERATOR_TICKET_PREFIX):
        return False
    rest = token[len(_OPERATOR_TICKET_PREFIX) :]
    parts = rest.split(":")
    if len(parts) != 2:
        return False
    expires_str, signature = parts
    try:
        expires = int(expires_str)
    except ValueError:
        return False
    if int(time.time()) > expires:
        return False
    msg = f"operator:{expires}".encode()
    expected = hmac.new(_TICKET_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, signature)


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


async def _operator_from_credential(api_key: str, session: AsyncSession) -> OperatorCredential:
    if not api_key or not api_key.startswith("aw_live_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator credential must start with 'aw_live_'",
        )
    credential = await session.scalar(
        select(OperatorCredential).where(
            OperatorCredential.id == api_key,
            OperatorCredential.revoked.is_(False),
        )
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked operator credential",
        )
    return credential


async def get_operator(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> OperatorCredential:
    """Authenticate the instance-local operator without selecting a project."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return await _operator_from_credential(credentials.credentials, session)


async def get_operator_project(
    project_id: str,
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
) -> Tuple[str, str]:
    """Resolve explicit path identity after instance-operator authentication."""
    del operator
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project.id, project.name


async def get_project(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Tuple[str, str]:
    """Validate Bearer token and return (project_id, project_name).

    Operator REST endpoints require both instance authentication and a project ID
    in the route. Query-param and implicit credential-derived selection are rejected.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    explicit_project_id = request.path_params.get("project_id")
    if not explicit_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit project route is required",
        )
    await _operator_from_credential(credentials.credentials, session)
    project = await session.get(Project, explicit_project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project.id, project.name


async def get_project_for_sse(
    request: Request,
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
    explicit_project_id = request.path_params.get("project_id")
    if credentials and explicit_project_id:
        await _operator_from_credential(credentials.credentials, session)
        project = await session.get(Project, explicit_project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project.id, project.name

    if credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit project route is required",
        )

    if token:
        project_id = _verify_ticket(token)
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired SSE ticket",
            )
        if explicit_project_id and explicit_project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSE ticket is bound to another project",
            )
        proj_result = await session.execute(select(Project).where(Project.id == project_id))
        project = proj_result.scalar_one_or_none()
        project_name = project.name if project else project_id
        return project_id, project_name

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing Authorization header or SSE ticket",
    )


async def get_operator_for_sse(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> OperatorCredential:
    """Authentication dependency for the one instance-level operator SSE stream.

    Accepts either the instance credential (`Authorization: Bearer aw_live_...`)
    or a short-lived operator ticket from `/events/ticket` (`?token=aw_optick_...`).
    A project-scoped ticket (`aw_ticket_...`) or a raw API key in `?token=` is
    rejected — those only unlock a project's own stream.
    """
    if credentials:
        return await _operator_from_credential(credentials.credentials, session)

    if token and _verify_operator_ticket(token):
        credential = await session.scalar(
            select(OperatorCredential).where(OperatorCredential.revoked.is_(False)).limit(1)
        )
        if credential is not None:
            return credential

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing Authorization header or operator SSE ticket",
    )
