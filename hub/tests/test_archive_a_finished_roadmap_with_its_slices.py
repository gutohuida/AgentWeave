"""A finished roadmap is archived with all its slice documents, or not at all.

`a-roadmap-that-is-recognisably-a-roadmap` FR-10 (ac-done): the roadmap page's one confirmed archive
sends the roadmap and its unarchived slice documents to `POST /documents/archive-batch`. An approved
slice document the Hub has not folded into a capability used to be refused while the roadmap was
archived anyway, leaving the operator an archived roadmap and approved slices.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument

from .test_a_finished_change_is_folded_into_its_capability import _finish_tasks
from .test_a_roadmap_shows_which_of_its_slices_are_done import (
    ROADMAP,
    ROADMAP_PAYLOAD,
    _approve,
    _change,
    _write,
)

BASE = "/api/v1/projects/proj-test/project"
SLICES = ["spec/changes/done-s1/spec.json", "spec/changes/done-s2/spec.json"]
BATCH = f"{BASE}/documents/archive-batch"


async def _phases():
    async with async_session_factory() as session:
        rows = await session.execute(
            select(SpecDocument.path, SpecDocument.phase).where(
                SpecDocument.path.in_([ROADMAP, *SLICES])
            )
        )
        return dict(rows.all())


async def _done_roadmap(app, auth_headers):
    await _write(app, auth_headers, ROADMAP, "The roadmap", ROADMAP_PAYLOAD, kind="roadmap")
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    for n, path in enumerate(SLICES, 1):
        await _write(app, auth_headers, path, f"Slice {n}", _change(f"Slice {n}"))
        assert (await _approve(app, auth_headers, path)).status_code == 200
        await _finish_tasks(path)


@pytest.mark.asyncio
async def test_the_plain_batch_still_refuses_an_unfolded_slice(app, auth_headers):
    await _done_roadmap(app, auth_headers)
    response = await app.post(BATCH, json={"paths": SLICES}, headers=auth_headers)
    assert response.json()["archived"] == []
    assert {r["code"] for r in response.json()["refused"]} == {"archive_not_folded"}


@pytest.mark.asyncio
async def test_the_check_says_what_happens_to_each_and_changes_nothing(app, auth_headers):
    await _done_roadmap(app, auth_headers)
    before = await _phases()
    response = await app.post(
        BATCH,
        json={"paths": [ROADMAP, *SLICES], "check_only": True, "no_capability_change": True},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    plan = {e["path"]: e["will"] for e in response.json()["plan"]}
    assert plan == {
        ROADMAP: "archive",
        SLICES[0]: "archive_no_capability_change",
        SLICES[1]: "archive_no_capability_change",
    }
    assert response.json()["archived"] == []
    assert await _phases() == before


@pytest.mark.asyncio
async def test_a_done_roadmap_and_its_unfolded_slices_archive_together(app, auth_headers):
    await _done_roadmap(app, auth_headers)
    response = await app.post(
        BATCH,
        json={"paths": [ROADMAP, *SLICES], "all_or_none": True, "no_capability_change": True},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert sorted(response.json()["archived"]) == sorted([ROADMAP, *SLICES])
    assert response.json()["refused"] == []
    assert set((await _phases()).values()) == {"archived"}


@pytest.mark.asyncio
async def test_one_refused_document_archives_none(app, auth_headers):
    await _done_roadmap(app, auth_headers)
    # Without the statement the slices are refused, so the roadmap must stay too.
    response = await app.post(
        BATCH, json={"paths": [ROADMAP, *SLICES], "all_or_none": True}, headers=auth_headers
    )
    body = response.json()
    assert body["archived"] == []
    assert {r["path"] for r in body["refused"]} == set(SLICES)
    assert (await _phases())[ROADMAP] == "approved"
    assert set((await _phases()).values()) == {"approved"}
