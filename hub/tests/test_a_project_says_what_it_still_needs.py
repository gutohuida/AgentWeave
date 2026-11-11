"""What a project still needs, as the Hub lists it (`a-project-says-what-it-still-needs`).

Task `setup-state`: each project the Hub lists carries its set-up items (FR-1), worked out from
its state now (FR-5); only the repository item can be dismissed, and a dismissal survives a Hub
restart (FR-3); and the events that change an item tell the app to re-read (FR-6).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from hub import project_workspace, sse
from hub.db.engine import async_session_factory, engine, init_db
from hub.db.models import SetupDismissal
from hub.main import create_app
from hub.project_setup import SETUP_CHANGED
from hub.runner_adapters import base as adapter_base

#: Taken at import, before conftest's autouse `_default_project_workspace` roots every project at
#: `tmp_path`: these tests are about the folder each project was really opened in.
_REAL_RESOLVE = project_workspace.resolve_project_workspace


@pytest.fixture(autouse=True)
def _projects_resolve_to_their_own_folders(monkeypatch) -> None:
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _REAL_RESOLVE)


@pytest.fixture
def broadcasts(monkeypatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    real = sse.sse_manager.broadcast

    async def _record(project_id, event_type, data=None, *args, **kwargs):
        seen.append((project_id, event_type))
        return await real(project_id, event_type, data, *args, **kwargs)

    monkeypatch.setattr(sse.sse_manager, "broadcast", _record)
    return seen


def _folder(tmp_path: Path, name: str = "scratch", *, git: bool = False) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "notes.txt").write_text("hi\n", encoding="utf-8")
    if git:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


async def _open(app, auth_headers, root: Path) -> str:
    opened = await app.post("/api/v1/projects/open", json={"path": str(root)}, headers=auth_headers)
    assert opened.status_code == 200, opened.text
    return opened.json()["id"]


async def _setup(app, auth_headers, project_id: str) -> dict:
    listed = await app.get("/api/v1/projects", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (project,) = [p for p in listed.json() if p["id"] == project_id]
    return project["setup"]


def _ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


@pytest.mark.asyncio
async def test_a_fresh_folder_lists_the_repository_and_agent_items_and_nothing_else(
    app, auth_headers, tmp_path
) -> None:
    """ac-fresh-folder (FR-1): no git and no agents."""
    project_id = await _open(app, auth_headers, _folder(tmp_path))

    setup = await _setup(app, auth_headers, project_id)

    assert _ids(setup["items"]) == ["repository", "agent"]
    assert [i["dismissable"] for i in setup["items"]] == [True, False]
    assert setup["dismissed"] == []


@pytest.mark.asyncio
async def test_a_project_with_a_repository_and_a_runnable_agent_lists_nothing(
    app, auth_headers, tmp_path, add_agent, monkeypatch
) -> None:
    """FR-1 (and FR-7's shape): every item met, nothing listed."""
    monkeypatch.setattr(adapter_base.shutil, "which", lambda name, *a, **k: f"/bin/{name}")
    project_id = await _open(app, auth_headers, _folder(tmp_path, git=True))
    await add_agent("Builder", project_id=project_id)
    runner = await app.post(
        f"/api/v1/projects/{project_id}/runners",
        json={"name": "claude-runner", "cli": "claude"},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text
    bound = await app.patch(
        f"/api/v1/projects/{project_id}/agents/Builder",
        json={"runner_id": runner.json()["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200, bound.text

    assert await _setup(app, auth_headers, project_id) == {"items": [], "dismissed": []}


@pytest.mark.asyncio
async def test_an_agent_whose_coding_agent_is_not_installed_has_a_can_run_item(
    app, auth_headers, add_agent, bind_runner, monkeypatch, broadcasts
) -> None:
    """ac-cannot-run (FR-1): one item per agent that cannot run, naming it and why."""
    monkeypatch.setattr(adapter_base.shutil, "which", lambda name, *a, **k: None)
    await add_agent("Alpha")
    await add_agent("Beta")
    await bind_runner("Alpha", cli="claude")

    setup = await _setup(app, auth_headers, "proj-test")

    can_run = [i for i in setup["items"] if i["key"] == "can-run"]
    assert can_run == [
        {
            "id": "can-run-Alpha",
            "key": "can-run",
            "dismissable": False,
            "agent": "Alpha",
            "provider": "claude",
            "reason": "not_installed",
            "detail": "Runner CLI 'claude' was not found in PATH.",
        },
        {
            "id": "can-run-Beta",
            "key": "can-run",
            "dismissable": False,
            "agent": "Beta",
            "provider": None,
            "reason": "no_model",
            "detail": "No model is chosen for this agent.",
        },
    ]
    # Binding a model is one of the changes the app re-reads on (FR-6).
    assert ("proj-test", SETUP_CHANGED) in broadcasts


@pytest.mark.asyncio
async def test_an_archived_agent_neither_counts_as_an_agent_nor_needs_to_run(
    app, auth_headers, add_agent, tmp_path
) -> None:
    project_id = await _open(app, auth_headers, _folder(tmp_path, git=True))
    await add_agent("Gone", project_id=project_id, lifecycle="archived")

    assert _ids((await _setup(app, auth_headers, project_id))["items"]) == ["agent"]


@pytest.mark.asyncio
async def test_a_missing_folder_lists_the_folder_item(app, auth_headers, tmp_path) -> None:
    root = _folder(tmp_path, git=True)
    project_id = await _open(app, auth_headers, root)
    root.rename(tmp_path / "moved")

    items = (await _setup(app, auth_headers, project_id))["items"]

    assert _ids(items) == ["folder", "agent"]
    assert items[0]["dismissable"] is False


@pytest.mark.asyncio
async def test_the_agent_item_cannot_be_dismissed(app, auth_headers, tmp_path, broadcasts) -> None:
    """ac-dismiss (FR-3): the folder, agent and can-run items are refused, and nothing is kept."""
    project_id = await _open(app, auth_headers, _folder(tmp_path))

    for item in ("agent", "folder", "can-run-Alpha", "anything"):
        refused = await app.put(
            f"/api/v1/projects/{project_id}/setup/dismissed/{item}", headers=auth_headers
        )
        assert refused.status_code == 400, refused.text
        assert refused.json()["detail"]["code"] == "setup_item_not_dismissable"

    async with async_session_factory() as session:
        assert (await session.execute(select(SetupDismissal))).scalars().all() == []
    assert _ids((await _setup(app, auth_headers, project_id))["items"]) == ["repository", "agent"]
    assert (project_id, SETUP_CHANGED) not in broadcasts


@pytest.mark.asyncio
async def test_a_dismissed_repository_item_stays_dismissed_across_a_restart_until_shown_again(
    app, auth_headers, tmp_path, broadcasts
) -> None:
    """ac-dismiss (FR-3): the Hub half; the screens are setup_list_check.py's."""
    project_id = await _open(app, auth_headers, _folder(tmp_path))

    dismissed = await app.put(
        f"/api/v1/projects/{project_id}/setup/dismissed/repository", headers=auth_headers
    )
    assert dismissed.status_code == 200, dismissed.text
    assert _ids(dismissed.json()["setup"]["items"]) == ["agent"]
    assert _ids(dismissed.json()["setup"]["dismissed"]) == ["repository"]
    assert (project_id, SETUP_CHANGED) in broadcasts

    # A restart: every connection closed, a new application on the same database file.
    await engine.dispose()
    restarted_app = create_app()
    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=restarted_app), base_url="http://test"
    ) as restarted:
        setup = await _setup(restarted, auth_headers, project_id)
        assert _ids(setup["items"]) == ["agent"]
        assert _ids(setup["dismissed"]) == ["repository"]

        shown = await restarted.delete(
            f"/api/v1/projects/{project_id}/setup/dismissed/repository", headers=auth_headers
        )
        assert shown.status_code == 200, shown.text
        assert _ids(shown.json()["setup"]["items"]) == ["repository", "agent"]
        assert shown.json()["setup"]["dismissed"] == []


@pytest.mark.asyncio
async def test_making_the_repository_clears_its_item_and_tells_the_app(
    app, auth_headers, tmp_path, broadcasts
) -> None:
    """FR-6: resolving an item tells the app to re-read, and the next read has it gone."""
    project_id = await _open(app, auth_headers, _folder(tmp_path))
    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )
    assert preview.status_code == 200, preview.text

    made = await app.post(
        f"/api/v1/projects/{project_id}/repository",
        json={"files": preview.json()["files"]},
        headers=auth_headers,
    )

    assert made.status_code == 200, made.text
    assert (project_id, SETUP_CHANGED) in broadcasts
    assert _ids((await _setup(app, auth_headers, project_id))["items"]) == ["agent"]


@pytest.mark.asyncio
async def test_archiving_the_last_agent_raises_the_agent_item_and_tells_the_app(
    app, auth_headers, add_agent, broadcasts, monkeypatch
) -> None:
    """FR-6: an agent archived is one of the changes the app re-reads on."""
    monkeypatch.setattr(adapter_base.shutil, "which", lambda name, *a, **k: f"/bin/{name}")
    await add_agent("Solo")
    assert "agent" not in _ids((await _setup(app, auth_headers, "proj-test"))["items"])

    archived = await app.post(
        "/api/v1/projects/proj-test/agents/Solo/archive", headers=auth_headers
    )

    assert archived.status_code == 200, archived.text
    assert ("proj-test", SETUP_CHANGED) in broadcasts
    assert "agent" in _ids((await _setup(app, auth_headers, "proj-test"))["items"])
