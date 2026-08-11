"""Tests for /api/v1/projects/proj-test/charters — runner-agent-charter-separation phase 2.

Covers project-scoped charter CRUD and the one-time seed from the Hub-bundled
legacy role guides. Context resolution and UI binding are covered separately by
tasks 2.3 and 2.4.
"""

import json
from pathlib import Path

import pytest

CHARTER_DIR = Path(__file__).parent.parent / "hub" / "data" / "charters"


def _bundled_charters() -> dict[str, str]:
    charters = json.loads((CHARTER_DIR / "charters.json").read_text(encoding="utf-8"))["charters"]
    return {
        metadata["name"]: (CHARTER_DIR / f"{charter_key}.md").read_text(encoding="utf-8")
        for charter_key, metadata in charters.items()
    }


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def test_every_seeded_charter_lives_directly_in_the_bundled_directory():
    """Seeding is manifest-keyed, so the manifest key is the only thing that chooses a file.

    Both seeding paths (`db/engine.py:_seed_default_charters` and
    `project_lifecycle.py`) build their path as `charters_dir / f"{key}.md"` with no
    glob, so a key containing a separator or `..` is the only way seeding could reach
    text outside this directory. `2026-08-11-charter-set-reshape` parks removed charter
    content under `openspec/`, and this asserts that content is unreachable by
    construction rather than by where it happens to sit today — which is why this checks
    the invariant and not the parked path, since that path moves when the change is
    archived.
    """
    charters = json.loads((CHARTER_DIR / "charters.json").read_text(encoding="utf-8"))["charters"]
    assert charters, "an empty manifest would make every assertion here vacuous"

    for key in charters:
        assert "/" not in key and "\\" not in key, f"charter key {key!r} contains a path separator"
        assert ".." not in key, f"charter key {key!r} could escape the bundled directory"

        resolved = (CHARTER_DIR / f"{key}.md").resolve()
        assert resolved.parent == CHARTER_DIR.resolve(), f"{key!r} resolves outside {CHARTER_DIR}"
        assert resolved.is_file(), f"manifest key {key!r} has no file; it would seed an empty charter"


@pytest.mark.asyncio
async def test_bundled_role_guides_seed_initial_charters(app, auth_headers):
    response = await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)
    assert response.status_code == 200

    expected = _bundled_charters()
    actual = {charter["name"]: charter["content"] for charter in response.json()}
    assert actual == expected
    assert all(charter["id"].startswith("charter-") for charter in response.json())


@pytest.mark.asyncio
async def test_charter_seeding_does_not_repeat_on_restart(app, auth_headers):
    from hub.db.engine import init_db

    before = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()
    await init_db()
    await init_db()
    after = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()

    assert len(before) == len(_bundled_charters())
    assert [charter["id"] for charter in after] == [charter["id"] for charter in before]


@pytest.mark.asyncio
async def test_charter_seeding_does_not_repeat_after_operator_deletes_all(app, auth_headers):
    """ "At most once" is durable project state, not merely `count(charters) == 0`.

    An operator who intentionally removes every seed charter must not see them return
    after the next Hub restart.
    """
    from hub.db.engine import init_db

    seeded = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()
    for charter in seeded:
        deleted = await app.delete(
            f"/api/v1/projects/proj-test/charters/{charter['id']}", headers=auth_headers
        )
        assert deleted.status_code == 204

    await init_db()
    after = await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)
    assert after.status_code == 200
    assert after.json() == []


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_charter(app, auth_headers):
    created = await app.post(
        "/api/v1/projects/proj-test/charters",
        json={"name": "Release Guardian", "content": "# Release Guardian\n\nVerify releases."},
        headers=auth_headers,
    )
    assert created.status_code == 201
    data = created.json()
    assert data["id"].startswith("charter-")
    assert data["name"] == "Release Guardian"
    assert data["content"] == "# Release Guardian\n\nVerify releases."

    fetched = await app.get(
        f"/api/v1/projects/proj-test/charters/{data['id']}", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json() == data


@pytest.mark.asyncio
async def test_list_charters_includes_authored_record(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Custom", "content": "Custom behavior"},
            headers=auth_headers,
        )
    ).json()

    listed = await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)
    assert listed.status_code == 200
    assert created["id"] in {charter["id"] for charter in listed.json()}


@pytest.mark.asyncio
async def test_update_charter_content(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Editor", "content": "Original"},
            headers=auth_headers,
        )
    ).json()

    updated = await app.patch(
        f"/api/v1/projects/proj-test/charters/{created['id']}",
        json={"name": "Senior Editor", "content": "Updated behavior"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Senior Editor"
    assert updated.json()["content"] == "Updated behavior"


@pytest.mark.asyncio
async def test_delete_unbound_charter(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Temporary", "content": "Delete me"},
            headers=auth_headers,
        )
    ).json()

    deleted = await app.delete(
        f"/api/v1/projects/proj-test/charters/{created['id']}", headers=auth_headers
    )
    assert deleted.status_code == 204
    missing = await app.get(
        f"/api/v1/projects/proj-test/charters/{created['id']}", headers=auth_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_get_missing_charter_returns_404(app, auth_headers):
    response = await app.get(
        "/api/v1/projects/proj-test/charters/charter-missing", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_bound_charter_is_refused(app, auth_headers):
    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Bound", "content": "Bound behavior"},
            headers=auth_headers,
        )
    ).json()
    registered = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "chartered-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert registered.status_code in (200, 201)
    bound = await app.patch(
        "/api/v1/projects/proj-test/agents/chartered-agent",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200

    deleted = await app.delete(
        f"/api/v1/projects/proj-test/charters/{charter['id']}", headers=auth_headers
    )
    assert deleted.status_code == 409
