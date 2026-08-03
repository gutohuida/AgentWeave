"""Run-scoped authentication for the least-privilege agent capability plane."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from hub.db.engine import async_session_factory
from hub.db.models import Run


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_active_run_token_resolves_server_owned_actor(app):
    from hub.agent_auth import get_agent_actor, hash_run_token

    token = "aw_run_test-active-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-auth-active",
                project_id="proj-test",
                agent="bound-agent",
                status="running",
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()

        actor = await get_agent_actor(_bearer(token), session)

    assert actor.project_id == "proj-test"
    assert actor.agent == "bound-agent"
    assert actor.run_id == "run-auth-active"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [None, "aw_run_unknown", "aw_live_testkey_abcdefgh"],
)
async def test_agent_auth_refuses_missing_unknown_and_project_credentials(app, token):
    from hub.agent_auth import get_agent_actor

    credentials = _bearer(token) if token else None
    async with async_session_factory() as session:
        with pytest.raises(HTTPException) as raised:
            await get_agent_actor(credentials, session)

    assert raised.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("run_status", ["completed", "failed", "stopped", "interrupted"])
async def test_terminal_run_immediately_revokes_credential(app, run_status):
    from hub.agent_auth import get_agent_actor, hash_run_token

    token = f"aw_run_terminal-{run_status}"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=f"run-auth-{run_status}",
                project_id="proj-test",
                agent="bound-agent",
                status=run_status,
                ended_at=datetime.now(timezone.utc),
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()

        with pytest.raises(HTTPException) as raised:
            await get_agent_actor(_bearer(token), session)

    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_operator_route_refuses_run_credential(app):
    response = await app.get(
        "/api/v1/status",
        headers={"Authorization": "Bearer aw_run_not-an-operator-key"},
    )

    assert response.status_code == 401

