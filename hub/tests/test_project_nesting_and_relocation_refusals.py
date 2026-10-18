"""F685 / F726: project-folder refusals name the other project and a way forward.

F685: opening a folder that *contains* a registered project was accepted (only the reverse was
checked, F646), and every later project under it was then refused as nested. F726: relocating
onto a folder whose marker names another project said only "relocation target does not carry the
project marker" -- it carries one, just not this project's, and the refusal named neither.
"""

from __future__ import annotations

import pytest

from hub.project_workspace import PROJECT_MARKER_PATH


async def _open(app, auth_headers, path):
    return await app.post("/api/v1/projects/open", json={"path": str(path)}, headers=auth_headers)


@pytest.mark.asyncio
async def test_a_folder_containing_a_project_is_refused_naming_it(app, auth_headers, tmp_path):
    inner = tmp_path / "parent" / "inner"
    inner.mkdir(parents=True)
    inner_opened = await _open(app, auth_headers, inner)
    assert inner_opened.status_code == 200, inner_opened.text
    inner_id = inner_opened.json()["id"]

    resp = await _open(app, auth_headers, tmp_path / "parent")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "project_nested"
    assert inner_id in detail["message"] and "contains" in detail["message"]
    assert not (tmp_path / "parent" / PROJECT_MARKER_PATH).exists()

    # The sibling folder the sweep then tried still opens: nothing was registered around it.
    sibling = tmp_path / "parent" / "sibling"
    sibling.mkdir()
    assert (await _open(app, auth_headers, sibling)).status_code == 200


@pytest.mark.asyncio
async def test_a_folder_whose_name_only_extends_a_project_is_not_containing(
    app, auth_headers, tmp_path
):
    (tmp_path / "proj-extra" / "x").mkdir(parents=True)
    (tmp_path / "proj").mkdir()
    assert (await _open(app, auth_headers, tmp_path / "proj-extra" / "x")).status_code == 200
    assert (await _open(app, auth_headers, tmp_path / "proj")).status_code == 200


@pytest.mark.asyncio
async def test_relocating_onto_another_projects_folder_names_that_project(
    app, auth_headers, tmp_path
):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    a_id = (await _open(app, auth_headers, a)).json()["id"]
    b_id = (await _open(app, auth_headers, b)).json()["id"]

    resp = await app.post(
        f"/api/v1/projects/{a_id}/relocate", json={"path": str(b)}, headers=auth_headers
    )

    assert resp.status_code == 409, resp.text
    message = resp.json()["detail"]["message"]
    assert "does not carry the project marker" not in message
    assert b_id in message, "the refusal must name the project the folder belongs to"
    assert a_id in message and "Relocate to the folder" in message


@pytest.mark.asyncio
async def test_relocating_onto_an_unmarked_folder_says_it_has_no_marker(
    app, auth_headers, tmp_path
):
    a = tmp_path / "a"
    plain = tmp_path / "plain"
    a.mkdir()
    plain.mkdir()
    a_id = (await _open(app, auth_headers, a)).json()["id"]

    resp = await app.post(
        f"/api/v1/projects/{a_id}/relocate", json={"path": str(plain)}, headers=auth_headers
    )

    assert resp.status_code == 409, resp.text
    message = resp.json()["detail"]["message"]
    assert "has no .agentweave/project.json" in message and a_id in message
