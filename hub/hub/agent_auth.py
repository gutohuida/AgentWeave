"""Authentication for the run-bound, least-privilege agent API."""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import instance_identity
from .auth import bearer_scheme
from .db.engine import get_session
from .db.models import Run

_RUN_TOKEN_PREFIX = "aw_run_"


@dataclass(frozen=True)
class AgentActor:
    """Server-derived identity for one currently active run."""

    project_id: str
    agent: str
    run_id: str


def mint_run_token() -> str:
    """Create a high-entropy credential whose plaintext exists only in run memory."""
    return f"{_RUN_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_run_token(token: str) -> str:
    """Return the fixed-size digest persisted for a run credential."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_agent_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> AgentActor:
    """Resolve an active Run from its credential without trusting caller identity."""
    if not credentials or not credentials.credentials.startswith(_RUN_TOKEN_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid run credential",
        )

    digest = hash_run_token(credentials.credentials)
    result = await session.execute(
        select(Run).where(
            Run.capability_token_hash == digest,
            Run.status == "running",
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive run credential",
        )

    # A run whose instance_id was recorded (task 4 — see instance_identity.py) must match
    # this process's own identity. A run minted before this feature landed has
    # instance_id=None and is not rejected on that basis alone — only a recorded mismatch
    # is distinguishable from "unknown/expired" and worth its own diagnosable reason.
    this_instance = instance_identity.get()
    if run.instance_id is not None and this_instance is not None and run.instance_id != this_instance:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Run credential was issued by a different Hub instance",
        )

    return AgentActor(project_id=run.project_id, agent=run.agent, run_id=run.id)

