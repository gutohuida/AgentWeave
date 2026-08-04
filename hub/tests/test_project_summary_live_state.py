"""Regression coverage for live project-summary directory observation."""

import pytest


@pytest.mark.asyncio
async def test_project_reads_refresh_live_directory_state(app, auth_headers, tmp_path) -> None:
    directory = tmp_path / "moves-later"
    relocated = tmp_path / "moved"
    directory.mkdir()
    opened = await app.post(
        "/api/v1/projects/open",
        json={"path": str(directory)},
        headers=auth_headers,
    )
    assert opened.status_code == 200, opened.text
    project_id = opened.json()["id"]

    directory.rename(relocated)

    detail = await app.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["directory_state"] == "missing"

    collection = await app.get("/api/v1/projects", headers=auth_headers)
    assert collection.status_code == 200
    summary = next(item for item in collection.json() if item["id"] == project_id)
    assert summary["directory_state"] == "missing"
