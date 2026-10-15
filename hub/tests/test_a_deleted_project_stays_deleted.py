"""`a-deleted-project-stays-deleted` (F592, F609, decision fix-D1).

A delete that asks (`remove_private=true`) removes the project's private vault entries before any
record and never touches the project's directory; one that does not ask keeps them. A shared
location or a failed removal deletes nothing. Reopening a deleted project's folder registers a new
project under a new id, while a marker from another database is still adopted under its own id
(`test_project_lifecycle.test_orphaned_marker_is_adopted_under_its_own_id`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub import vault
from hub.db.engine import async_session_factory
from hub.db.models import DeletedProject
from hub.project_workspace import PROJECT_MARKER_PATH


async def _open(app, auth_headers, directory: Path) -> str:
    directory.mkdir(exist_ok=True)
    opened = await app.post(
        "/api/v1/projects/open", json={"path": str(directory)}, headers=auth_headers
    )
    assert opened.status_code == 200, opened.text
    return opened.json()["id"]


async def _source(app, auth_headers, project: str, name: str, visibility: str) -> str:
    created = await app.post(
        f"/api/v1/projects/{project}/vault/sources",
        json={"name": name, "type": "note", "content": f"{name} text", "visibility": visibility},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _choose(app, auth_headers, project: str, location: Path) -> None:
    put = await app.put(
        f"/api/v1/projects/{project}/vault/settings",
        json={"private_location": str(location)},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text


async def _exists(app, auth_headers, project: str) -> bool:
    got = await app.get(f"/api/v1/projects/{project}", headers=auth_headers)
    return got.status_code == 200


@pytest.mark.asyncio
async def test_an_asked_delete_removes_the_default_private_folder_and_no_project_file(
    app, auth_headers, tmp_path
) -> None:
    directory = tmp_path / "asked"
    project = await _open(app, auth_headers, directory)
    await _source(app, auth_headers, project, "secret", "private")
    await _source(app, auth_headers, project, "shared", "tracked")
    private = vault.default_private_location(project)
    assert any(private.rglob("*"))
    project_files = sorted(p for p in directory.rglob("*") if ".git" not in p.parts)

    deleted = await app.delete(
        f"/api/v1/projects/{project}?remove_private=true", headers=auth_headers
    )

    assert deleted.status_code == 204, deleted.text
    assert not private.exists()
    assert sorted(p for p in directory.rglob("*") if ".git" not in p.parts) == project_files


@pytest.mark.asyncio
async def test_a_delete_that_does_not_ask_keeps_the_private_entries(
    app, auth_headers, tmp_path
) -> None:
    project = await _open(app, auth_headers, tmp_path / "unasked")
    await _source(app, auth_headers, project, "secret", "private")
    private = vault.default_private_location(project)
    kept = sorted(private.rglob("*"))

    deleted = await app.delete(f"/api/v1/projects/{project}", headers=auth_headers)

    assert deleted.status_code == 204, deleted.text
    assert sorted(private.rglob("*")) == kept and kept


@pytest.mark.asyncio
async def test_a_chosen_location_loses_only_the_vaults_own_folders(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    project = await _open(app, auth_headers, tmp_path / "chosen")
    location = tmp_path_factory.mktemp("chosen-private")
    (location / "keep.txt").write_text("the operator's own", encoding="utf-8")
    await _choose(app, auth_headers, project, location)
    await _source(app, auth_headers, project, "secret", "private")
    assert (location / vault.SOURCES).is_dir()

    deleted = await app.delete(
        f"/api/v1/projects/{project}?remove_private=true", headers=auth_headers
    )

    assert deleted.status_code == 204, deleted.text
    assert sorted(p.name for p in location.iterdir()) == ["keep.txt"]


@pytest.mark.asyncio
async def test_a_location_shared_with_another_project_refuses_and_deletes_nothing(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    location = tmp_path_factory.mktemp("shared-private")
    first = await _open(app, auth_headers, tmp_path / "first")
    second = await _open(app, auth_headers, tmp_path / "second")
    await _choose(app, auth_headers, first, location)
    await _choose(app, auth_headers, second, location / "nested")
    await _source(app, auth_headers, first, "secret", "private")
    kept = sorted(location.rglob("*"))

    deleted = await app.delete(
        f"/api/v1/projects/{first}?remove_private=true", headers=auth_headers
    )

    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["detail"]["code"] == "private_location_shared"
    assert second in deleted.json()["detail"]["message"]
    assert await _exists(app, auth_headers, first)
    assert sorted(location.rglob("*")) == kept


@pytest.mark.asyncio
async def test_a_failed_removal_deletes_no_record(app, auth_headers, tmp_path, monkeypatch) -> None:
    project = await _open(app, auth_headers, tmp_path / "locked")
    await _source(app, auth_headers, project, "secret", "private")

    def locked(_path):
        raise PermissionError("in use")

    monkeypatch.setattr(vault, "_remove_tree", locked)
    deleted = await app.delete(
        f"/api/v1/projects/{project}?remove_private=true", headers=auth_headers
    )

    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["detail"]["code"] == "private_entries_not_removed"
    assert await _exists(app, auth_headers, project)


@pytest.mark.asyncio
async def test_reopening_a_deleted_projects_folder_registers_a_new_project(
    app, auth_headers, tmp_path
) -> None:
    directory = tmp_path / "reopened"
    project = await _open(app, auth_headers, directory)
    secret = await _source(app, auth_headers, project, "secret", "private")
    deleted = await app.delete(f"/api/v1/projects/{project}", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text

    reopened = await _open(app, auth_headers, directory)

    assert reopened != project
    marker = json.loads((directory / PROJECT_MARKER_PATH).read_text(encoding="utf-8"))
    assert marker["project_id"] == reopened
    # The private entry's stub is a tracked file of the project, which a delete never touches; its
    # text was the deleted project's and must not be served to the new one.
    read = await app.get(
        f"/api/v1/projects/{reopened}/vault/entries/{secret}", headers=auth_headers
    )
    assert read.status_code == 200, read.text
    assert read.json()["content"] is None and read.json()["available"] is False
    async with async_session_factory() as session:
        assert await session.get(DeletedProject, project) is not None
        assert await session.get(DeletedProject, reopened) is None
