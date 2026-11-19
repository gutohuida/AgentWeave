"""Stop and live state per run (`one-profile-runs-many-turns-at-once-on-different-tasks`, task
`stop-and-live`: FR-10, FR-11).

With the project's "profiles run in parallel" switch on, one profile has two running runs, each on
its own task and in its own conversation. Stopping one stops only that one (FR-10); the agents API
lists both with their conversation and task, and each conversation reads as running from its own
turn (FR-11).
"""

from __future__ import annotations

import threading
from typing import List

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Run

from .test_agent_trigger import _await_background_run
from .test_start_gate import (
    TASK_A,
    TASK_B,
    _await_ended,
    _patched,
    _post,
    _repo_project,
    _running,
    _set_project,
    _Spawns,
    _tasks,
)


class _StoppableSpawns(_Spawns):
    """`_Spawns` whose processes also end when terminated, as a stopped PTY does."""

    def __call__(self, *args, **kwargs):
        hanging = super().__call__(*args, **kwargs)
        release: threading.Event = self.releases[-1]
        hanging.terminate.side_effect = lambda force=False: release.set()
        return hanging


async def _two_running(app, auth_headers, spawns: _Spawns) -> List[dict]:
    first = await _post(app, auth_headers, message="one", task_id=TASK_A)
    second = await _post(app, auth_headers, message="two", task_id=TASK_B)
    assert first["status"] == "running" and second["status"] == "running", second
    await spawns.wait_for(2)
    assert len(await _running(agent="writer")) == 2
    return [first, second]


async def _status(run_id: str) -> str:
    async with async_session_factory() as session:
        return (await session.execute(select(Run.status).where(Run.id == run_id))).scalar_one()


@pytest.mark.asyncio
async def test_stopping_one_of_two_runs_leaves_the_other_to_finish(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-stop-one: the stopped run ends `stopped`, the other ends `completed`."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _tasks(TASK_A, TASK_B)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _StoppableSpawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first, second = await _two_running(app, auth_headers, spawns)

            # Unnamed, the stop would have to guess between two turns: it refuses instead.
            ambiguous = await app.post(
                "/api/v1/projects/proj-test/agent/writer/stop", headers=auth_headers
            )
            assert ambiguous.status_code == 409, ambiguous.text
            assert "name the one to stop" in ambiguous.json()["detail"]

            # Stopped from its conversation, as the app's Stop button does — the *older* run, so
            # "the newest" (the old rule) would have stopped the wrong one.
            stop = await app.post(
                "/api/v1/projects/proj-test/agent/writer/stop",
                params={"conversation_id": first["conversation_id"]},
                headers=auth_headers,
            )
            assert stop.status_code == 200, stop.text
            assert stop.json()["run_id"] == first["run_id"]
            await _await_ended(1)
            assert await _status(first["run_id"]) == "stopped"
            assert await _status(second["run_id"]) == "running"
        finally:
            spawns.release_all()
            await _await_background_run()
    assert await _status(first["run_id"]) == "stopped"
    assert await _status(second["run_id"]) == "completed"


@pytest.mark.asyncio
async def test_a_stop_naming_a_run_that_is_not_running_is_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    response = await app.post(
        "/api/v1/projects/proj-test/agent/writer/stop",
        params={"run_id": "run-000000000000"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "run-000000000000" in response.json()["detail"]


@pytest.mark.asyncio
async def test_both_running_runs_are_listed_and_both_conversations_show_running(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-live-indicators."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _tasks(TASK_A, TASK_B)
    await _set_project(profiles_run_in_parallel=True)
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            first, second = await _two_running(app, auth_headers, spawns)

            agents = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
            assert agents.status_code == 200
            writer = next(a for a in agents.json() if a["name"] == "writer")
            assert writer["status"] == "running"
            assert [
                (r["run_id"], r["conversation_id"], r["task_id"]) for r in writer["running_runs"]
            ] == [
                (first["run_id"], first["conversation_id"], TASK_A),
                (second["run_id"], second["conversation_id"], TASK_B),
            ]
            assert writer["running_conversation_id"] == second["conversation_id"]

            conversations = await app.get(
                "/api/v1/projects/proj-test/agent/writer/conversations", headers=auth_headers
            )
            assert conversations.status_code == 200
            attention = {c["id"]: c["attention"] for c in conversations.json()}
            assert attention[first["conversation_id"]] == "running"
            assert attention[second["conversation_id"]] == "running"
        finally:
            spawns.release_all()
            await _await_background_run()

    agents = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    writer = next(a for a in agents.json() if a["name"] == "writer")
    assert writer["running_runs"] == []
