"""A change document can name its roadmap slice after the fact (F674 backfill, vis-D9): the operator
links an archived document to its slice as a metadata write that changes no requirement."""

import json
import re

from sqlalchemy import select

from hub import spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent

from .test_a_roadmap_shows_which_of_its_slices_are_done import (
    BASE,
    FIRST,
    LOOSE,
    ROADMAP,
    ROADMAP_PAYLOAD,
    _approve,
    _change,
    _write,
)
from .test_a_finished_change_is_folded_into_its_capability import _finish_tasks


async def _archived_loose(app, auth_headers):
    await _write(app, auth_headers, ROADMAP, "The roadmap", ROADMAP_PAYLOAD, kind="roadmap")
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    await _write(app, auth_headers, LOOSE, "Built the first slice", _change("Built the first"))
    assert (await _approve(app, auth_headers, LOOSE)).status_code == 200
    await _finish_tasks(path=LOOSE)
    archived = await app.post(
        f"{BASE}/documents/phase",
        params={"path": LOOSE, "to": "archived"},
        json={"no_capability_change": True, "reason": "built"},
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text


def _stored(tmp_path, path):
    return json.loads((tmp_path / path).read_text(encoding="utf-8"))


async def _link(app, auth_headers, path, slice_key, roadmap=ROADMAP):
    return await app.put(
        f"{BASE}/documents/{path}/roadmap",
        json={"document": roadmap, "slice": slice_key},
        headers=auth_headers,
    )


async def test_an_archived_document_gains_its_slice(app, auth_headers, tmp_path):
    await _archived_loose(app, auth_headers)
    before = _stored(tmp_path, LOOSE)

    linked = await _link(app, auth_headers, LOOSE, "first")

    assert linked.status_code == 200, linked.text
    after = _stored(tmp_path, LOOSE)
    assert after["roadmap"] == {"document": ROADMAP, "slice": "first"}
    for field in ("requirements", "aw_identity", "acceptance_criteria", "tasks", "hub"):
        assert after[field] == before[field], field
    assert after["hub"]["phase"] == "archived"

    page = (await app.get(f"{BASE}/spec", params={"path": ROADMAP}, headers=auth_headers)).json()
    first = re.search(r'<li id="slice-first".*?</li>', page["content"], flags=re.S).group(0)
    assert "archived" in first and LOOSE in first

    # The write is the Hub's own: the row's digest is the file's, so it is not an outside edit.
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == LOOSE))
        ).scalar_one()
    assert row.content_digest == spec_lifecycle.digest((tmp_path / LOOSE).read_text("utf-8"))

    # The same link again changes nothing and is not an error.
    again = await _link(app, auth_headers, LOOSE, "first")
    assert again.status_code == 200, again.text


async def test_a_link_that_cannot_be_right_is_refused(app, auth_headers, tmp_path):
    await _archived_loose(app, auth_headers)
    await _write(
        app,
        auth_headers,
        FIRST,
        "Already linked",
        _change("Already linked", {"document": ROADMAP, "slice": "second"}),
    )
    before = (tmp_path / LOOSE).read_text(encoding="utf-8")

    cases = [
        (LOOSE, "third", ROADMAP, "roadmap_slice_unknown"),
        (LOOSE, "first", FIRST, "roadmap_not_found"),
        (ROADMAP, "first", ROADMAP, "not_a_change_document"),
        (FIRST, "first", ROADMAP, "roadmap_link_differs"),
    ]
    for path, key, roadmap, code in cases:
        response = await _link(app, auth_headers, path, key, roadmap)
        assert response.status_code == 422, (code, response.text)
        assert response.json()["detail"]["code"] == code, response.text

    assert (tmp_path / LOOSE).read_text(encoding="utf-8") == before


async def test_the_link_is_recorded_as_the_operators(app, auth_headers, tmp_path):
    await _archived_loose(app, auth_headers)
    assert (await _link(app, auth_headers, LOOSE, "first")).status_code == 200
    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(SpecDocumentEvent)
                    .join(SpecDocument, SpecDocument.id == SpecDocumentEvent.document_id)
                    .where(SpecDocument.path == LOOSE, SpecDocumentEvent.kind == "roadmap_link")
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1
    assert events[0].actor_kind == "operator"
    assert events[0].detail == {"document": ROADMAP, "slice": "first"}
