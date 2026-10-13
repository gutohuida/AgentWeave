"""F589 and F595: deleting a runner refuses every holder, not only agents.

`delete_runner` checked `Agent.runner_id` alone. A runner a manager job named (the conversation
titler, the vault jobs) or the project's checkpoint runner was deleted with 204, leaving a dangling
id: the job silently did nothing, every later settings save answered 400, and checkpoints said no
runner was configured while settings showed one.
"""

import pytest
from sqlalchemy import select

from hub import manager
from hub.db.engine import async_session_factory
from hub.db.models import Project, Runner

BASE = "/api/v1/projects/proj-test"


async def _runner(app, auth_headers, name: str) -> str:
    created = await app.post(
        f"{BASE}/runners", json={"name": name, "cli": "claude"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _exists(runner_id: str) -> bool:
    async with async_session_factory() as session:
        return (
            await session.execute(select(Runner.id).where(Runner.id == runner_id))
        ).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_a_runner_a_manager_job_uses_cannot_be_deleted(app, auth_headers):
    runner_id = await _runner(app, auth_headers, "distiller")
    patched = await app.patch(
        f"{BASE}/manager/jobs/{manager.DISTILLATION}",
        json={"enabled": True, "runner_id": runner_id},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text

    resp = await app.delete(f"{BASE}/runners/{runner_id}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    assert manager.DISTILLATION in resp.json()["detail"]
    assert await _exists(runner_id)


@pytest.mark.asyncio
async def test_the_checkpoint_runner_cannot_be_deleted(app, auth_headers):
    runner_id = await _runner(app, auth_headers, "checkpointer")
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checkpoint_runner_id = runner_id
        await session.commit()

    resp = await app.delete(f"{BASE}/runners/{runner_id}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    assert "checkpoint" in resp.json()["detail"].lower()
    assert await _exists(runner_id)


@pytest.mark.asyncio
async def test_a_runner_nothing_names_is_still_deleted(app, auth_headers):
    runner_id = await _runner(app, auth_headers, "unused")
    resp = await app.delete(f"{BASE}/runners/{runner_id}", headers=auth_headers)
    assert resp.status_code == 204, resp.text
    assert not await _exists(runner_id)
