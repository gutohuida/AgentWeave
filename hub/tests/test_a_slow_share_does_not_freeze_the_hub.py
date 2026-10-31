"""F806: a folder listing, project open, create or relocate of a path on an unreachable network
share costs only its own request -- the filesystem work runs off the event loop."""

from __future__ import annotations

import asyncio
import threading

import pytest

from hub import project_lifecycle
from hub.api.v1 import fs_browse

# Only a blocked loop ever waits this out, so it can be far above any delay a loaded machine adds.
_STALL = 60.0


class _Stall:
    """Blocks the wrapped call, as an unreachable share's resolve/scandir does, until /health has
    answered. Run on the loop, nothing can answer /health, so the call waits out `_STALL`."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.answered = threading.Event()
        self.health_answered_during_it = False

    def wrapping(self, real):
        def wrapper(*args, **kwargs):
            self.entered.set()
            self.health_answered_during_it = self.answered.wait(_STALL)
            return real(*args, **kwargs)

        return wrapper


async def _health_answers_during(app, stall: _Stall, slow_request) -> bool:
    task = asyncio.create_task(slow_request())
    while not stall.entered.is_set():
        await asyncio.sleep(0.01)
    response = await app.get("/health")
    assert response.status_code == 200
    stall.answered.set()
    await task
    return stall.health_answered_during_it


@pytest.mark.asyncio
async def test_a_slow_folder_listing_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    stall = _Stall()
    monkeypatch.setattr(fs_browse, "list_directory", stall.wrapping(fs_browse.list_directory))

    answered = await _health_answers_during(
        app,
        stall,
        lambda: app.get("/api/v1/fs/list", params={"path": str(tmp_path)}, headers=auth_headers),
    )

    assert answered


@pytest.mark.asyncio
async def test_a_slow_project_open_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    stall = _Stall()
    target = tmp_path / "proj"
    target.mkdir()
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        stall.wrapping(project_lifecycle.canonicalize_project_directory),
    )

    answered = await _health_answers_during(
        app,
        stall,
        lambda: app.post("/api/v1/projects/open", json={"path": str(target)}, headers=auth_headers),
    )

    assert answered


@pytest.mark.asyncio
async def test_a_slow_project_create_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    stall = _Stall()
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        stall.wrapping(project_lifecycle.canonicalize_project_directory),
    )

    answered = await _health_answers_during(
        app,
        stall,
        lambda: app.post(
            "/api/v1/projects/create",
            json={"path": str(tmp_path / "fresh")},
            headers=auth_headers,
        ),
    )

    assert answered


@pytest.mark.asyncio
async def test_a_slow_project_relocate_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    stall = _Stall()
    original = tmp_path / "original"
    original.mkdir()
    opened = await app.post(
        "/api/v1/projects/open", json={"path": str(original)}, headers=auth_headers
    )
    project_id = opened.json()["id"]
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        stall.wrapping(project_lifecycle.canonicalize_project_directory),
    )

    answered = await _health_answers_during(
        app,
        stall,
        lambda: app.post(
            f"/api/v1/projects/{project_id}/relocate",
            json={"path": str(original)},
            headers=auth_headers,
        ),
    )

    assert answered
