"""F172: relocating onto a path another project still claims is refused legibly, not with a 500.

The operator's route to it is ordinary folder work. Project A is moved away, so its row still
claims a path nothing occupies. Project B's folder is then moved into A's old place, and B's marker
travels with it. Relocating B to say where it now lives hit `projects.path_key`'s UNIQUE constraint
at commit and answered `500 Internal Server Error` with no body. Every other refusal on the route is
typed and names a way forward. This one now does too.
"""

from __future__ import annotations

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project


async def _open(app, auth_headers, path) -> str:
    opened = await app.post("/api/v1/projects/open", json={"path": str(path)}, headers=auth_headers)
    assert opened.status_code == 200, opened.text
    return opened.json()["id"]


@pytest.mark.asyncio
async def test_relocating_onto_a_path_another_project_claims_names_the_claimant(
    app, auth_headers, tmp_path
):
    place = tmp_path / "place"
    other = tmp_path / "other"
    place.mkdir()
    other.mkdir()
    a_id = await _open(app, auth_headers, place)
    b_id = await _open(app, auth_headers, other)

    place.rename(tmp_path / "a-moved-away")  # A's row still claims `place`
    other.rename(place)  # B's folder, marker and all, now sits where A was

    resp = await app.post(
        f"/api/v1/projects/{b_id}/relocate", json={"path": str(place)}, headers=auth_headers
    )

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "project_path_claimed"
    assert a_id in detail["message"], "the refusal must name the project holding the path"
    async with async_session_factory() as session:
        b = await session.get(Project, b_id)
        assert b.working_directory == str(other.resolve()), "a refused relocation moved nothing"
