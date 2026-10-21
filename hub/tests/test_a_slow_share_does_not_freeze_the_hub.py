"""F806: a folder listing, project open, create or relocate of a path on an unreachable network
share costs only its own request -- the filesystem work runs off the event loop."""

from __future__ import annotations

import asyncio
import time

import pytest

from hub import project_lifecycle
from hub.api.v1 import fs_browse

_STALL = 1.5


def _stalling(real):
    def wrapper(*args, **kwargs):
        time.sleep(_STALL)  # a blocking call, as an unreachable share's resolve/scandir is
        return real(*args, **kwargs)

    return wrapper


async def _health_latency_during(app, slow_request) -> float:
    # Timed from before the slow request starts: a blocked loop cannot even wake this sleep, so
    # the stall shows up as elapsed time here rather than vanishing before a late start stamp.
    started = time.monotonic()
    task = asyncio.create_task(slow_request())
    await asyncio.sleep(0.2)
    response = await app.get("/health")
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    await task
    return elapsed


@pytest.mark.asyncio
async def test_a_slow_folder_listing_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(fs_browse, "list_directory", _stalling(fs_browse.list_directory))

    elapsed = await _health_latency_during(
        app,
        lambda: app.get("/api/v1/fs/list", params={"path": str(tmp_path)}, headers=auth_headers),
    )

    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_a_slow_project_open_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    target = tmp_path / "proj"
    target.mkdir()
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        _stalling(project_lifecycle.canonicalize_project_directory),
    )

    elapsed = await _health_latency_during(
        app,
        lambda: app.post("/api/v1/projects/open", json={"path": str(target)}, headers=auth_headers),
    )

    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_a_slow_project_create_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        _stalling(project_lifecycle.canonicalize_project_directory),
    )

    elapsed = await _health_latency_during(
        app,
        lambda: app.post(
            "/api/v1/projects/create",
            json={"path": str(tmp_path / "fresh")},
            headers=auth_headers,
        ),
    )

    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_a_slow_project_relocate_does_not_block_other_requests(
    app, auth_headers, tmp_path, monkeypatch
):
    original = tmp_path / "original"
    original.mkdir()
    opened = await app.post(
        "/api/v1/projects/open", json={"path": str(original)}, headers=auth_headers
    )
    project_id = opened.json()["id"]
    monkeypatch.setattr(
        project_lifecycle,
        "canonicalize_project_directory",
        _stalling(project_lifecycle.canonicalize_project_directory),
    )

    elapsed = await _health_latency_during(
        app,
        lambda: app.post(
            f"/api/v1/projects/{project_id}/relocate",
            json={"path": str(original)},
            headers=auth_headers,
        ),
    )

    assert elapsed < 1.0
