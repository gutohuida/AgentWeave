"""F702: the corpus strip promised fixes that could not happen, and printed codes.

Every sentence here is one the Hub answers and the strip shows verbatim, so the tests are on the
route answers: what `/specs` says about an unfiled document the Hub does not track, what a rebuild
says when it will not write the index or cannot read a document, and that a rebuild naming a home
that is no tracked document is refused rather than run.
"""

from __future__ import annotations

import json

from ._spec_files import stored_text

BASE = "/api/v1/projects/proj-test/project"


def _payload(title: str, requirements: list | None = None) -> dict:
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "requirements": requirements or [],
    }


async def _create(app, headers, path: str, title: str) -> None:
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title}, headers=headers
    )
    assert response.status_code == 201, response.text


async def _reindex(app, headers, body=None):
    return await app.post(f"{BASE}/spec/reindex", json=body, headers=headers)


def _diagnostics(body: dict) -> dict:
    return {d["code"]: d for d in body["index"]["diagnostics"]}


async def test_an_untracked_unfiled_document_is_told_to_be_adopted_first(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers, "spec/home/spec.json", "Home")
    written = await _reindex(app, auth_headers)
    assert written.json()["index"]["written"], written.text
    await _create(app, auth_headers, "spec/later/spec.json", "Later")
    untracked = tmp_path / "spec/areas/noid/spec.json"
    untracked.parent.mkdir(parents=True)
    untracked.write_text(stored_text(_payload("No id")), encoding="utf-8")

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    by_path = {
        d["path"]: d for d in listed.json()["diagnostics"] if d["code"] == "unfiled_document"
    }
    assert "Rebuilding the index files it" in by_path["spec/later/spec.json"]["message"]
    message = by_path["spec/areas/noid/spec.json"]["message"]
    assert "Rebuilding the index files it" not in message
    assert "Adopt it first" in message

    rebuilt = await _reindex(app, auth_headers)
    unindexable = _diagnostics(rebuilt.json())["unindexable_document"]
    assert unindexable["message"] != "Unindexable document: spec/areas/noid/spec.json."
    assert "does not track it" in unindexable["message"]


async def test_a_rebuild_that_will_not_choose_a_home_says_so_in_words(app, auth_headers):
    await _create(app, auth_headers, "spec/a/spec.json", "A")
    await _create(app, auth_headers, "spec/b/spec.json", "B")

    response = await _reindex(app, auth_headers)

    assert response.status_code == 200, response.text
    found = _diagnostics(response.json())
    assert found["home_ambiguous"]["message"].startswith("The index was not written")
    assert "spec/a/spec.json, spec/b/spec.json" in found["home_ambiguous"]["message"]
    assert "the index." not in found["index_home_required"]["message"]


async def test_a_rebuild_naming_a_home_that_is_no_tracked_document_is_refused(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers, "spec/a/spec.json", "A")
    await _create(app, auth_headers, "spec/b/spec.json", "B")

    response = await _reindex(app, auth_headers, {"home": "spec/nowhere/spec.json"})

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "home_unknown"
    assert "spec/nowhere/spec.json" in response.json()["detail"]["message"]
    assert not (tmp_path / "spec/index.json").exists()

    chosen = await _reindex(app, auth_headers, {"home": "spec/a/spec.json"})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["index"]["written"]["home"] == "spec/a/spec.json"


async def test_a_document_whose_requirements_cannot_be_read_says_which_field(
    app, auth_headers, tmp_path
):
    path = "spec/hand/spec.json"
    await _create(app, auth_headers, path, "Hand written")
    target = tmp_path / path
    stored = json.loads(target.read_text(encoding="utf-8"))
    stored["requirements"] = [{"statement": "No key here.", "modal": "SHALL"}]
    target.write_text(json.dumps(stored), encoding="utf-8")

    response = await _reindex(app, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["documents"][path] is None
    unreadable = _diagnostics(body)["requirements_unreadable"]
    assert unreadable["path"] == path
    assert "requirements[0].key" in unreadable["message"]
    [skip] = [s for s in body["corpus"]["skipped"] if s["path"] == path]
    assert "requirements[0].key" in skip["message"]
