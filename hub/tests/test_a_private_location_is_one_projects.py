"""F683 and F717: the private location a project chooses through `PUT /vault/settings`.

F683: two projects could share one private location (another's chosen one or its default folder),
and each then read the other's private entries, since private files carry no project id.
F717: a location on a drive that is not there was accepted, then every private add was a bare 500.
"""

from __future__ import annotations

import os
import string
from pathlib import Path

import pytest

from hub import vault

BASE = "/api/v1/projects/proj-test"


async def _other_project(pid: str, name: str, private_location=None) -> None:
    from hub.db.engine import async_session_factory
    from hub.db.models import Project, VaultSettings

    async with async_session_factory() as session:
        session.add(Project(id=pid, name=name))
        if private_location is not None:
            session.add(
                VaultSettings(
                    project_id=pid,
                    default_visibility="tracked",
                    private_location=str(private_location),
                )
            )
        await session.commit()


async def _put(app, auth_headers, location):
    return await app.put(
        f"{BASE}/vault/settings",
        json={"private_location": None if location is None else str(location)},
        headers=auth_headers,
    )


async def _chosen(app, auth_headers):
    got = await app.get(f"{BASE}/vault/settings", headers=auth_headers)
    assert got.status_code == 200, got.text
    return got.json()["private_location"]


@pytest.mark.asyncio
async def test_a_location_another_project_uses_is_refused(
    app, auth_headers, tmp_path_factory
) -> None:
    theirs = tmp_path_factory.mktemp("shared") / "their vault"
    await _other_project("proj-f683-chose", "Chose", private_location=theirs)
    await _other_project("proj-f683-default", "Defaulted")

    for location, named in (
        (theirs, "proj-f683-chose"),  # the same folder
        (theirs / "inner", "proj-f683-chose"),  # inside it
        (theirs.parent, "proj-f683-chose"),  # holding it
        (vault.default_private_location("proj-f683-default"), "proj-f683-default"),
        (vault.vaults_root(), "proj-f683-"),  # holds every default folder
    ):
        refused = await _put(app, auth_headers, location)
        assert refused.status_code == 400, (location, refused.text)
        assert named in refused.text
        assert await _chosen(app, auth_headers) is None

    own = tmp_path_factory.mktemp("own") / "vault"
    assert (await _put(app, auth_headers, own)).status_code == 200


@pytest.mark.asyncio
async def test_returning_to_the_default_is_refused_when_another_project_holds_it(
    app, auth_headers, tmp_path_factory
) -> None:
    own = tmp_path_factory.mktemp("own") / "vault"
    assert (await _put(app, auth_headers, own)).status_code == 200
    # Chosen before the check existed: another project points at this one's default folder.
    await _other_project(
        "proj-f683-squatter",
        "Squatter",
        private_location=vault.default_private_location("proj-test"),
    )
    refused = await _put(app, auth_headers, None)
    assert refused.status_code == 400, refused.text
    assert "proj-f683-squatter" in refused.text
    assert Path(await _chosen(app, auth_headers)) == own


def _missing_drive() -> str:
    for letter in reversed(string.ascii_uppercase):
        if not os.path.exists(f"{letter}:\\"):
            return f"{letter}:\\"
    pytest.skip("every drive letter is in use")


windows_only = pytest.mark.skipif(os.name != "nt", reason="drive letters are Windows'")


@windows_only
@pytest.mark.asyncio
async def test_a_location_on_a_drive_that_is_not_there_is_refused(app, auth_headers) -> None:
    refused = await _put(app, auth_headers, Path(_missing_drive(), "nowhere", "vault"))
    assert refused.status_code == 400, refused.text
    assert "not reachable" in refused.text
    assert await _chosen(app, auth_headers) is None


@windows_only
@pytest.mark.asyncio
async def test_a_private_add_after_the_drive_went_away_says_why(app, auth_headers) -> None:
    from hub.db.engine import async_session_factory
    from hub.db.models import VaultSettings

    gone = Path(_missing_drive(), "nowhere", "vault")
    async with async_session_factory() as session:
        session.add(
            VaultSettings(
                project_id="proj-test", default_visibility="tracked", private_location=str(gone)
            )
        )
        await session.commit()
    added = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "Contacts", "type": "note", "content": "x\n", "visibility": "private"},
        headers=auth_headers,
    )
    assert added.status_code == 409, added.text
    assert "not reachable" in added.text
