"""F806: a folder listing, project open, create or relocate of a path on an unreachable network
share costs only its own request -- the filesystem work runs off the event loop."""

from __future__ import annotations

import asyncio
import threading

import pytest

import hub.main as hub_main
from hub import project_lifecycle
from hub.api.v1 import fs_browse

from ._loop_lag import STALL_LIMIT, LagProbe, slow_git

# Only a blocked loop ever waits this out, so it can be far above any delay a loaded machine adds.
_STALL = 60.0


class _Stall:
    """Blocks the wrapped call, as an unreachable share's resolve/scandir does, until /health has
    answered. Run on the loop, nothing can answer /health, so the call waits out `_STALL`. It also records whether it ran on the loop's
    thread, which does not depend on how busy the machine is."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.answered = threading.Event()
        self.health_answered_during_it = False
        self.loop_thread = threading.current_thread()
        self.on_loop: "list[bool]" = []

    def wrapping(self, real):
        def wrapper(*args, **kwargs):
            self.on_loop.append(threading.current_thread() is self.loop_thread)
            self.entered.set()
            self.health_answered_during_it = self.answered.wait(_STALL)
            return real(*args, **kwargs)

        return wrapper


async def _health_answers_during(app, stall: _Stall, slow_request) -> bool:
    """Whether /health answered while the slow call was held, with the call made off the loop and
    the loop never held past the probe's limit meanwhile: a share's call made on the loop holds it
    for as long as the share does, and a 250 ms hold anywhere in the request still counts."""
    async with LagProbe() as probe:
        task = asyncio.create_task(slow_request())
        while not stall.entered.is_set():
            await asyncio.sleep(0.01)
        response = await app.get("/health")
        assert response.status_code == 200
        stall.answered.set()
        await task
    assert stall.on_loop and not any(stall.on_loop), "the slow call ran on the loop"
    assert probe.worst < STALL_LIMIT, f"the loop stalled {probe.worst * 1000:.0f} ms: {probe.why}"
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


@pytest.mark.asyncio
async def test_health_works_out_its_ui_staleness_warning_off_the_loop(app):
    """F1128: an expired staleness cache made `/health` run git two or three times, and stat every
    UI source file, on the loop's thread, so every poll of it once per TTL froze the Hub."""
    hub_main._reset_ui_staleness_cache()
    try:
        with slow_git(threading.current_thread()) as git:
            response = await app.get("/health")
    finally:
        hub_main._reset_ui_staleness_cache()

    assert response.status_code == 200
    assert git.calls, "the staleness check asked git nothing: this test exercised nothing"
    assert not git.on_loop, [call.argv for call in git.on_loop]
