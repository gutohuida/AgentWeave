"""`spec/index.json` and each document's hub block follow the rows after every document write.

F1158: the index was regenerated only by a reindex or by creating a capability, so it listed 11 of
62 approved change documents between them. F1157: migration `0149` moved four documents from
`proposed` to `exploring` in their rows and never in their files, and nothing re-rendered them.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from hub import spec_documents, spec_index_file
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent

BASE = "/api/v1/projects/proj-test/project"
HOME = "spec/home.json"
AREA = "spec/area.json"
STALE = "spec/changes/stale/spec.json"


@pytest.fixture
def refreshing():
    """The Hub as it is once serving: the lifespan enables refreshes, and the suite runs none."""
    spec_index_file.enable()
    yield
    spec_index_file.disable()


async def _create(app, auth_headers, path: str, title: str, kind: str = "change-spec") -> None:
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title, "kind": kind}, headers=auth_headers
    )
    assert created.status_code == 201, created.text


def _index(tmp_path) -> dict:
    return json.loads((tmp_path / "spec" / "index.json").read_text(encoding="utf-8"))


def _indexed(tmp_path) -> dict:
    return {entry["path"]: entry for entry in _index(tmp_path)["documents"]}


async def _corpus(app, auth_headers, tmp_path) -> None:
    """A home, an area under it, and a change document, indexed with that arrangement."""
    await _create(app, auth_headers, HOME, "Home", "capability")
    await _create(app, auth_headers, AREA, "Area", "system-map")
    await _create(app, auth_headers, STALE, "Stale")
    rebuilt = await app.post(f"{BASE}/spec/reindex", json={"home": HOME}, headers=auth_headers)
    assert rebuilt.status_code == 200, rebuilt.text
    await spec_index_file.settle()
    raw = _index(tmp_path)
    for entry in raw["documents"]:
        if entry["path"] == STALE:
            entry["parent"] = AREA  # the operator's arrangement, which has no column
    (tmp_path / "spec" / "index.json").write_text(json.dumps(raw, indent=2) + "\n", "utf-8")


@pytest.mark.asyncio
async def test_a_document_the_hub_writes_is_in_the_index(app, auth_headers, tmp_path, refreshing):
    await _corpus(app, auth_headers, tmp_path)

    await _create(app, auth_headers, "spec/changes/later/spec.json", "Later")
    await spec_index_file.settle()

    indexed = _indexed(tmp_path)
    assert "spec/changes/later/spec.json" in indexed, sorted(indexed)
    assert indexed["spec/changes/later/spec.json"]["status"] == "exploring"
    # Regenerated from the rows, keeping what only the file records.
    assert _index(tmp_path)["home"] == HOME
    assert indexed[STALE]["parent"] == AREA


@pytest.mark.asyncio
async def test_a_documents_file_and_index_entry_take_the_phase_from_its_row(
    app, auth_headers, tmp_path, refreshing
):
    await _corpus(app, auth_headers, tmp_path)
    # What migration 0149 left: the row moved to `exploring`, the file and its entry did not.
    target = tmp_path / STALE
    text = target.read_text(encoding="utf-8")
    block = spec_documents.parse_hub(text)
    block["phase"] = "proposed"
    target.write_text(spec_documents.serialize(spec_documents.parse_stored(text), block), "utf-8")
    raw = _index(tmp_path)
    for entry in raw["documents"]:
        if entry["path"] == STALE:
            entry["status"] = "proposed"
    (tmp_path / "spec" / "index.json").write_text(json.dumps(raw, indent=2) + "\n", "utf-8")

    # Any later document write puts both right.
    await _create(app, auth_headers, "spec/changes/later/spec.json", "Later")
    await spec_index_file.settle()

    rewritten = target.read_text(encoding="utf-8")
    assert spec_documents.parse_hub(rewritten)["phase"] == "exploring"
    assert spec_documents.parse_stored(rewritten) == spec_documents.parse_stored(text)
    assert _indexed(tmp_path)[STALE]["status"] == "exploring"
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == STALE))
        ).scalar_one()
        events = (
            (
                await session.execute(
                    select(SpecDocumentEvent).where(
                        SpecDocumentEvent.document_id == row.id,
                        SpecDocumentEvent.kind == "rerendered",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert row.content_digest == spec_documents_digest(rewritten)
    assert [event.actor for event in events] == ["index"]


@pytest.mark.asyncio
async def test_nothing_is_refreshed_before_the_hub_is_serving(app, auth_headers, tmp_path):
    """A restart must not rewrite a project's files on its own: until the lifespan enables it, a
    write schedules nothing."""
    await _corpus(app, auth_headers, tmp_path)

    await _create(app, auth_headers, "spec/changes/later/spec.json", "Later")
    await spec_index_file.settle()

    assert "spec/changes/later/spec.json" not in _indexed(tmp_path)


@pytest.mark.asyncio
async def test_a_project_with_no_index_is_given_none(app, auth_headers, tmp_path, refreshing):
    """Choosing a corpus's home is the operator's, so no index is started for them."""
    await _create(app, auth_headers, HOME, "Home", "capability")
    await _create(app, auth_headers, STALE, "Stale")
    await spec_index_file.settle()

    assert not (tmp_path / "spec" / "index.json").exists()


def spec_documents_digest(text: str) -> str:
    from hub import spec_lifecycle

    return spec_lifecycle.digest(text)
