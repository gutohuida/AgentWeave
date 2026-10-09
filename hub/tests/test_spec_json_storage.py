"""A spec document is stored as its payload: `spec.json`, rendered on open.

`a-spec-document-is-stored-as-its-payload` FR-1/2/3/5/6/10, the criteria `stored-shape`,
`deterministic-write`, `html-create-refused`, `legacy-diagnostic`, `journey-in-file` and
`agent-reads`. The conversion route (FR-7..9) is the next task. The acceptance drive is
`scripts/drive/d1010_spec_json.py`.
"""

from __future__ import annotations

import json

import pytest

from hub.project_workspace import ProjectWorkspace
from hub.spec_documents import parse_hub, parse_stored, serialize, write_payload
from hub.spec_payload import PayloadError, validate_payload

from .test_spec_documents_api import (
    AGENT,
    BASE,
    PATH,
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)


def _stored(tmp_path, path=PATH):
    return json.loads((tmp_path / path).read_text(encoding="utf-8"))


# stored-shape (FR-1)
@pytest.mark.asyncio
async def test_a_submitted_document_is_stored_as_its_payload_and_the_hub_block(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    response = await _submit(app, run_headers, _document(house_note="kept verbatim"))
    assert response.status_code == 200, response.text

    stored = _stored(tmp_path)
    assert stored["house_note"] == "kept verbatim"
    assert stored["title"] == "Demo"
    assert stored["hub"] == {
        "phase": "exploring",
        "rigor": "sketch",
        "step": "intake",
        "size": None,
    }
    assert not (tmp_path / "spec/changes/demo/spec.html").exists()
    assert sorted(p.name for p in (tmp_path / "spec/changes/demo").iterdir()) == ["spec.json"]


# deterministic-write (FR-3)
def test_the_same_payload_is_written_to_the_same_bytes(tmp_path):
    workspace = ProjectWorkspace(project_id="p", root=tmp_path, path_key="test:p")
    hub = {"phase": "exploring", "rigor": "sketch", "step": "intake", "size": None}
    first = write_payload(workspace, PATH, _document(), hub)
    before = (tmp_path / PATH).read_bytes()
    # Key order of the submission does not reach the file.
    reordered = dict(reversed(list(_document().items())))
    second = write_payload(workspace, PATH, reordered, dict(reversed(list(hub.items()))))

    assert first == second
    assert (tmp_path / PATH).read_bytes() == before
    assert before.endswith(b"}\n") and b"\r\n" not in before


def test_rewording_one_requirement_changes_only_its_line():
    hub = {"phase": "exploring", "rigor": "sketch", "step": "intake", "size": None}
    before = serialize(_document(), hub).splitlines()
    reworded = _document()
    reworded["requirements"][0]["statement"] = "It responds within 100ms"
    after = serialize(reworded, hub).splitlines()

    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert len(before) == len(after)
    assert changed == [
        (
            '      "statement": "It responds within 200ms"',
            '      "statement": "It responds within 100ms"',
        )
    ]


def test_the_hub_block_is_not_part_of_the_payload():
    text = serialize(
        _document(), {"phase": "approved", "rigor": "gate", "step": None, "size": None}
    )
    assert "hub" not in parse_stored(text)
    assert parse_hub(text)["phase"] == "approved"
    assert parse_stored("<html>not a stored file</html>") is None
    assert parse_hub("[1, 2]") == {}


def test_a_payload_may_not_carry_the_hub_block():
    with pytest.raises(PayloadError) as excinfo:
        validate_payload(_document(hub={"phase": "approved"}))
    assert excinfo.value.field == "hub"


# rendered-on-open (FR-2)
@pytest.mark.asyncio
async def test_get_spec_renders_the_page_from_the_stored_payload(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())

    fetched = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    page = fetched.json()["content"]
    assert page.lstrip().startswith("<!DOCTYPE html>") or page.lstrip().startswith("<html")
    assert "It responds within 200ms" in page
    assert 'name="aw-spec-status" content="exploring"' in page
    # The file itself is not the page.
    assert not (tmp_path / PATH).read_text(encoding="utf-8").lstrip().startswith("<")


@pytest.mark.asyncio
async def test_get_spec_on_an_unreadable_file_says_so(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    (tmp_path / PATH).write_text("{not json", encoding="utf-8")

    fetched = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert fetched.status_code == 422
    assert fetched.json()["detail"]["code"] == "payload_unreadable"


# html-create-refused (FR-5)
@pytest.mark.asyncio
async def test_creating_a_document_at_an_html_path_names_the_json_path(app, auth_headers):
    response = await app.post(
        f"{BASE}/documents",
        json={"path": "spec/changes/x/spec.html", "title": "X"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "spec/changes/x/spec.json" in response.text


@pytest.mark.asyncio
async def test_the_index_is_not_a_document_path(app, auth_headers):
    response = await app.post(
        f"{BASE}/documents", json={"path": "spec/index.json", "title": "X"}, headers=auth_headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_minted_path_is_a_json_path(app, auth_headers, tmp_path):
    response = await app.post(f"{BASE}/documents", json={"title": "X"}, headers=auth_headers)
    assert response.status_code == 201, response.text
    assert response.json()["path"].endswith("/spec.json")


# legacy-diagnostic (FR-6)
@pytest.mark.asyncio
async def test_a_legacy_html_document_is_reported_not_listed(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    legacy = tmp_path / "spec/changes/old/spec.html"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("<html><head><title>Old</title></head></html>", encoding="utf-8")

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [s["path"] for s in body["specs"]] == [PATH]
    (diagnostic,) = [d for d in body["diagnostics"] if d["code"] == "legacy_html_document"]
    assert diagnostic["path"] == "spec/changes/old/spec.html"
    assert diagnostic["expected"] == "spec/changes/old/spec.json"
    assert "POST /project/spec/convert?to=json" in diagnostic["actual"]


# journey-in-file (FR-10)
@pytest.mark.asyncio
async def test_an_operator_journey_move_rewrites_the_hub_block(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    moved = await app.post(
        f"{BASE}/documents/journey",
        params={"path": PATH},
        json={"step": "requirements", "size": "large"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text

    assert _stored(tmp_path)["hub"]["step"] == "requirements"
    assert _stored(tmp_path)["hub"]["size"] == "large"
    # The digest followed the rewrite, so the move is not reported as an edit behind the Hub.
    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    (view,) = [d for d in listed.json()["documents"] if d["path"] == PATH]
    assert view["diverged"] is False


@pytest.mark.asyncio
async def test_an_agent_journey_move_rewrites_the_hub_block(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    sized = await app.post(
        f"{AGENT}/size",
        json={"path": PATH, "size": "fix", "reason": "one line"},
        headers=run_headers,
    )
    assert sized.status_code == 200, sized.text
    advanced = await app.post(f"{AGENT}/advance", json={"path": PATH}, headers=run_headers)
    assert advanced.status_code == 200, advanced.text

    assert _stored(tmp_path)["hub"]["size"] == "fix"
    assert _stored(tmp_path)["hub"]["step"] == "tasks"


@pytest.mark.asyncio
async def test_a_phase_move_rewrites_the_hub_block(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    proposed = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    assert proposed.status_code == 200, proposed.text
    assert _stored(tmp_path)["hub"]["phase"] == "proposed"


# agent-reads (FR-4)
@pytest.mark.asyncio
async def test_an_agent_reads_and_submits_a_json_document(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    assert (await _submit(app, run_headers, _document())).status_code == 200

    read = await app.get(AGENT, params={"path": PATH}, headers=run_headers)
    assert read.status_code == 200, read.text
    statements = [r["statement"] for r in read.json()["requirements"]]
    assert statements == ["It responds within 200ms"]

    again = _document()
    again["requirements"][0]["statement"] = "It responds within 50ms"
    assert (await _submit(app, run_headers, again)).status_code == 200
    assert _stored(tmp_path)["requirements"][0]["statement"] == "It responds within 50ms"
