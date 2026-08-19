"""A loop created into a project that cannot checkpoint says so, at creation.

A loop's continuity between firings *is* its checkpoint (design D5, tasks 7.1-7.3, 9.1). With
checkpointing off, or with no runner able to generate one, every firing starts blank. Nothing said
so until three firings later when human-only check 13.2 was driven against a real agent on
2026-08-19, and only then because the agent volunteered it: "no prior checkpoint output was
provided to me in this firing."

Advisory, never a refusal — a loop with no memory is a legitimate thing to want.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project


async def _set_checkpointing(project_id: str, *, mode: str, runner_id=None) -> None:
    async with async_session_factory() as db:
        project = await db.get(Project, project_id)
        project.checkpoint_mode = mode
        project.checkpoint_runner_id = runner_id
        await db.commit()


def _loop_body(name: str) -> dict:
    return {
        "name": name,
        "agent": "continuity-agent",
        "message": "work the queue",
        "cron": "0 9 * * *",
        "purpose": "continuity warning coverage",
        "stop_when_queue_empties": True,
    }


@pytest.mark.asyncio
async def test_loop_created_with_checkpointing_off_is_told_it_has_no_memory(app, auth_headers):
    await _set_checkpointing("proj-test", mode="off")

    created = await app.post(
        "/api/v1/projects/proj-test/jobs", json=_loop_body("no-memory loop"), headers=auth_headers
    )

    assert created.status_code == 201, created.text
    warning = created.json()["continuity_warning"]
    assert warning, "a loop with no checkpointing must say so at creation"
    assert "no memory" in warning.lower()
    # It must name where to fix it, not merely state the problem — the same "name the route out"
    # rule the D7 refusal was corrected for on the same day.
    assert "project settings" in warning.lower()


@pytest.mark.asyncio
async def test_loop_created_with_no_checkpoint_runner_is_told_why(app, auth_headers):
    # Enabled, but nothing can actually generate a checkpoint: the endpoint 409s on this exact
    # gap, so a loop created here has no continuity either.
    await _set_checkpointing("proj-test", mode="offered", runner_id=None)

    created = await app.post(
        "/api/v1/projects/proj-test/jobs", json=_loop_body("no-runner loop"), headers=auth_headers
    )

    assert created.status_code == 201
    warning = created.json()["continuity_warning"]
    assert warning and "runner" in warning.lower()


@pytest.mark.asyncio
async def test_a_project_that_can_checkpoint_gets_no_warning(app, auth_headers):
    await _set_checkpointing("proj-test", mode="offered", runner_id="runner-abc")

    created = await app.post(
        "/api/v1/projects/proj-test/jobs", json=_loop_body("has-memory loop"), headers=auth_headers
    )

    assert created.status_code == 201
    assert created.json()["continuity_warning"] is None


@pytest.mark.asyncio
async def test_a_plain_job_is_never_warned_because_it_has_no_continuity_to_lose(app, auth_headers):
    """The warning is about *loops*. A job with no loop has no between-firings memory to miss."""
    await _set_checkpointing("proj-test", mode="off")

    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "plain job",
            "agent": "continuity-agent",
            "message": "just run",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201
    assert created.json()["loop"] is None
    assert created.json()["continuity_warning"] is None


@pytest.mark.asyncio
async def test_a_new_project_can_checkpoint_by_default():
    """The mode a *new* project starts at. `server_default` stays "off" so an existing row is
    untouched by this — the upgrade-safety guarantee the original comment describes is about rows
    that already exist, and no migration rewrites them."""
    async with async_session_factory() as db:
        project = Project(id="proj-default-ckpt", name="Defaults")
        db.add(project)
        await db.commit()
        await db.refresh(project)
        assert project.checkpoint_mode == "offered"
