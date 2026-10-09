"""Converting a project's spec documents between `.html` and `spec.json`, both directions.

`a-spec-document-is-stored-as-its-payload` FR-7/8/9, task `convert`: the files, the rows'
paths, undelivered queue entries, payload references (`roadmap.document`, a task's
`from.document`) and `spec/index.json`; a second call changes nothing; refused while a run is
active. The acceptance drive is `scripts/drive/d1010_spec_json.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, SpecDocument
from hub.spec_documents import parse_legacy
from hub.spec_payload import SCHEMA_VERSION

from .test_spec_documents_api import BASE, _document

ROADMAP = "spec/changes/plan/spec.json"
CHANGE = "spec/changes/route/spec.json"
OTHER = "spec/changes/other/spec.json"


def _html(path):
    return path[: -len(".json")] + ".html"


def _roadmap():
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "roadmap",
        "title": "The plan",
        "scope": {"in_scope": ["a route"], "non_goals": ["the rest"]},
        "slices": [{"key": "route", "title": "The route", "intent": "Answer", "done": "answers"}],
    }


async def _put(app, auth_headers, path, document):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": document["title"], "kind": document["kind"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    saved = await app.put(
        f"{BASE}/documents/{path}/content", json={"document": document}, headers=auth_headers
    )
    assert saved.status_code == 200, saved.text


async def _corpus(app, auth_headers):
    """A roadmap, a change on its slice importing a task from a third document, and an index."""
    await _put(app, auth_headers, ROADMAP, _roadmap())
    await _put(app, auth_headers, OTHER, _document(title="Other"))
    await _put(
        app,
        auth_headers,
        CHANGE,
        _document(
            title="Route",
            roadmap={"document": ROADMAP, "slice": "route"},
            tasks=[
                {"key": "t1", "description": "Build it", "requirements": ["alpha"]},
                {"key": "t0", "from": {"document": OTHER, "key": "t1"}},
            ],
        ),
    )
    reindexed = await app.post(f"{BASE}/spec/reindex", json={"home": ROADMAP}, headers=auth_headers)
    assert reindexed.status_code == 200, reindexed.text
    assert reindexed.json()["index"]["written"] is not None


async def _convert(app, auth_headers, to):
    return await app.post(f"{BASE}/spec/convert", params={"to": to}, headers=auth_headers)


def _tree(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted((root / "spec").rglob("*"))
        if p.is_file()
    }


async def _rows():
    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocument.id, SpecDocument.path).where(SpecDocument.project_id == "proj-test")
        )
        return dict(result.all())


async def _page(app, auth_headers, path):
    fetched = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    return fetched.json()["content"]


@pytest.mark.asyncio
async def test_converting_to_html_writes_the_page_and_rewrites_every_path(
    app, auth_headers, tmp_path
):
    await _corpus(app, auth_headers)
    ids = await _rows()
    page = await _page(app, auth_headers, CHANGE)

    response = await _convert(app, auth_headers, "html")
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(item["to"] for item in body["converted"]) == sorted(
        _html(p) for p in (ROADMAP, CHANGE, OTHER)
    )

    files = _tree(tmp_path)
    assert sorted(files) == sorted([_html(ROADMAP), _html(CHANGE), _html(OTHER), "spec/index.json"])
    # Same ids, the rows now at the .html paths.
    assert await _rows() == {doc_id: _html(path) for doc_id, path in ids.items()}
    # The page the app showed, with the paths it names moved to .html: corpus navigation, the slice
    # line and the embedded payload's references.
    written = files[_html(CHANGE)].decode("utf-8")
    assert written == page.replace("/spec.json", "/spec.html")
    assert _html(ROADMAP) in written and ROADMAP not in written
    embedded = parse_legacy(written)
    assert embedded["roadmap"]["document"] == _html(ROADMAP)
    assert embedded["tasks"][1]["from"]["document"] == _html(OTHER)
    index = json.loads(files["spec/index.json"])
    assert index["home"] == _html(ROADMAP)
    assert {doc["path"] for doc in index["documents"]} == {
        _html(p) for p in (ROADMAP, CHANGE, OTHER)
    }


@pytest.mark.asyncio
async def test_converting_back_restores_the_stored_files_byte_for_byte(app, auth_headers, tmp_path):
    await _corpus(app, auth_headers)
    before = _tree(tmp_path)
    ids = await _rows()

    assert (await _convert(app, auth_headers, "html")).status_code == 200
    back = await _convert(app, auth_headers, "json")

    assert back.status_code == 200, back.text
    assert _tree(tmp_path) == before
    assert await _rows() == ids
    stored = json.loads(before[CHANGE])
    assert stored["roadmap"]["document"] == ROADMAP
    assert stored["tasks"][1]["from"]["document"] == OTHER
    # The documents read as documents again, not as legacy diagnostics.
    listed = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert sorted(s["path"] for s in listed["specs"]) == sorted([ROADMAP, CHANGE, OTHER])
    assert not [d for d in listed["diagnostics"] if d["code"] == "legacy_html_document"]
    assert (await _page(app, auth_headers, CHANGE)).count("It responds within 200ms") >= 1


@pytest.mark.asyncio
async def test_a_second_conversion_changes_nothing(app, auth_headers, tmp_path):
    await _corpus(app, auth_headers)
    first = await _convert(app, auth_headers, "json")
    assert first.status_code == 200, first.text
    assert first.json()["converted"] == []
    frozen, paths = _tree(tmp_path), await _rows()

    second = await _convert(app, auth_headers, "json")

    assert second.status_code == 200
    assert second.json()["converted"] == []
    assert _tree(tmp_path) == frozen
    assert await _rows() == paths


@pytest.mark.asyncio
async def test_undelivered_queue_entries_follow_the_document_and_delivered_ones_keep_history(
    app, auth_headers
):
    await _corpus(app, auth_headers)
    async with async_session_factory() as session:
        for entry_id, delivered in (("qe-open", None), ("qe-done", datetime.now(timezone.utc))):
            session.add(
                InboundQueueEntry(
                    id=entry_id,
                    project_id="proj-test",
                    agent="claude-1",
                    origin_type="operator",
                    content="carry on",
                    hop_depth=0,
                    spec_document=CHANGE,
                    delivered_at=delivered,
                )
            )
        await session.commit()

    response = await _convert(app, auth_headers, "html")

    assert response.status_code == 200, response.text
    async with async_session_factory() as session:
        result = await session.execute(
            select(InboundQueueEntry.id, InboundQueueEntry.spec_document)
        )
        assert dict(result.all()) == {"qe-open": _html(CHANGE), "qe-done": CHANGE}


@pytest.mark.asyncio
async def test_the_conversion_is_refused_while_a_run_is_active_and_changes_nothing(
    app, auth_headers, tmp_path
):
    await _corpus(app, auth_headers)
    before, ids = _tree(tmp_path), await _rows()
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-busy",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await _convert(app, auth_headers, "html")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "conversion_run_active"
    assert detail["runs"] == ["run-busy"]
    assert "run-busy" in detail["message"]
    assert _tree(tmp_path) == before
    assert await _rows() == ids


@pytest.mark.asyncio
async def test_a_conversion_names_its_direction(app, auth_headers):
    response = await _convert(app, auth_headers, "markdown")
    assert response.status_code == 422
