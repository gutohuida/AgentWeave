"""The specification document tree, read from the project working directory.

These endpoints used to serve a push-fed cache, so their tests wrote through
`POST /specs/sync`. There is no such endpoint: a document is a file, and a test
that wants one writes it to the project's working directory. The autouse
`_default_project_workspace` fixture roots every project at the test's own
`tmp_path`, so each test gets an isolated tree — the "the test DB is shared"
caveats the previous version carried no longer apply.
"""

import json

import pytest

BASE = "/api/v1/projects/proj-test/project"


def _write(tmp_path, relative: str, content: str = "<html><body>doc</body></html>") -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _index(tmp_path, payload: dict) -> None:
    target = tmp_path / "spec" / "index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


def _document(path: str, *, title: str, kind: str, status: str, order: int, parent=None) -> dict:
    return {
        "path": path,
        "title": title,
        "kind": kind,
        "status": status,
        "parent": parent,
        "order": order,
    }


@pytest.mark.asyncio
async def test_a_document_on_disk_is_listed_and_readable(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html", "<html><body>v1</body></html>")

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert listed.status_code == 200
    specs = listed.json()["specs"]
    assert [s["path"] for s in specs] == ["spec/spec.html"]
    assert specs[0]["updated_at"]

    fetched = await app.get(f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["content"] == "<html><body>v1</body></html>"


@pytest.mark.asyncio
async def test_the_file_is_the_document_so_an_edit_is_immediately_visible(
    app, auth_headers, tmp_path
):
    """No cache to invalidate — the read goes to the file every time."""
    _write(tmp_path, "spec/spec.html", "<html>old</html>")
    first = await app.get(f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=auth_headers)
    assert first.json()["content"] == "<html>old</html>"

    _write(tmp_path, "spec/spec.html", "<html>new</html>")
    second = await app.get(f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=auth_headers)
    assert second.json()["content"] == "<html>new</html>"


@pytest.mark.asyncio
async def test_discovery_reaches_nested_documents(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html")
    _write(tmp_path, "spec/roadmaps/collaboration.html")
    _write(tmp_path, "spec/changes/archive/2026-01-01-old/spec.html")

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    paths = {s["path"] for s in listed.json()["specs"]}
    assert paths == {
        "spec/spec.html",
        "spec/roadmaps/collaboration.html",
        "spec/changes/archive/2026-01-01-old/spec.html",
    }


@pytest.mark.asyncio
async def test_an_unsafe_path_is_excluded_and_reported(app, auth_headers, tmp_path):
    """Excluded is not enough — a document silently missing from a list is
    indistinguishable from one that was never written."""
    _write(tmp_path, "spec/spec.html")
    _write(tmp_path, "spec/NotLowercase.html")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()

    assert [s["path"] for s in body["specs"]] == ["spec/spec.html"]
    codes = {d["code"]: d for d in body["diagnostics"]}
    assert "unsafe_document_path" in codes
    assert codes["unsafe_document_path"]["path"] == "spec/NotLowercase.html"


@pytest.mark.asyncio
async def test_a_hidden_directory_is_not_part_of_the_tree(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html")
    _write(tmp_path, "spec/.trash/old.html")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert [s["path"] for s in body["specs"]] == ["spec/spec.html"]


@pytest.mark.asyncio
async def test_unknown_document_returns_404(app, auth_headers, tmp_path):
    resp = await app.get(
        f"{BASE}/spec",
        params={"path": "spec/changes/never-written/spec.html"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["../etc", "spec/foo.txt", "foo/spec.html", "spec/../escape.html"])
async def test_an_unsafe_request_path_is_refused(app, auth_headers, tmp_path, bad):
    resp = await app.get(f"{BASE}/spec", params={"path": bad}, headers=auth_headers)
    assert resp.status_code == 400, f"expected 400 for path={bad!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_without_an_index_documents_are_listed_as_unindexed(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert body["specs"][0]["state"] == "unindexed"
    assert body["manifest"]["state"] == "absent"


@pytest.mark.asyncio
async def test_an_invalid_index_still_lists_the_documents(app, auth_headers, tmp_path):
    """The index's condition is reported alongside the tree, never in place of it."""
    _write(tmp_path, "spec/spec.html")
    (tmp_path / "spec" / "index.json").write_text("{not json", encoding="utf-8")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert [s["path"] for s in body["specs"]] == ["spec/spec.html"]
    assert body["manifest"]["state"] == "invalid"


@pytest.mark.asyncio
async def test_a_filed_document_carries_its_index_metadata(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html")
    _index(
        tmp_path,
        {
            "version": 1,
            "home": "spec/spec.html",
            "documents": [
                _document(
                    "spec/spec.html", title="Baseline", kind="baseline", status="living", order=1
                )
            ],
        },
    )

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    entry = body["specs"][0]
    assert entry["state"] == "filed"
    assert entry["title"] == "Baseline"
    assert entry["kind"] == "baseline"
    assert body["home"] == "spec/spec.html"
    assert body["manifest"]["state"] == "valid"


@pytest.mark.asyncio
async def test_an_index_entry_with_no_file_is_retained_and_reported(app, auth_headers, tmp_path):
    """It could be a deliberate deletion, a rename the index missed, or a document
    never written. The Hub cannot tell, so it reports rather than discards."""
    _write(tmp_path, "spec/spec.html")
    _index(
        tmp_path,
        {
            "version": 1,
            "home": "spec/spec.html",
            "documents": [
                _document(
                    "spec/spec.html", title="Baseline", kind="baseline", status="living", order=1
                ),
                _document(
                    "spec/changes/gone/spec.html",
                    title="Gone",
                    kind="change-spec",
                    status="draft",
                    order=2,
                ),
            ],
        },
    )

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert [m["path"] for m in body["missing"]] == ["spec/changes/gone/spec.html"]
    assert any(d["code"] == "missing_document" for d in body["diagnostics"])


@pytest.mark.asyncio
async def test_a_document_the_index_omits_is_reported_as_unfiled(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/spec.html")
    _write(tmp_path, "spec/changes/new/spec.html")
    _index(
        tmp_path,
        {
            "version": 1,
            "home": "spec/spec.html",
            "documents": [
                _document(
                    "spec/spec.html", title="Baseline", kind="baseline", status="living", order=1
                )
            ],
        },
    )

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    states = {s["path"]: s["state"] for s in body["specs"]}
    assert states["spec/changes/new/spec.html"] == "unfiled"
    assert any(d["code"] == "unfiled_document" for d in body["diagnostics"])


@pytest.mark.asyncio
async def test_an_ambiguous_home_is_reported_rather_than_chosen(app, auth_headers, tmp_path):
    """The previous implementation fell back to `spec/spec.html` and then to the
    first document alphabetically — a choice made on the operator's behalf and
    indistinguishable from one they made."""
    _write(tmp_path, "spec/one.html")
    _write(tmp_path, "spec/two.html")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert body["home"] is None
    assert any(d["code"] == "home_ambiguous" for d in body["diagnostics"])


@pytest.mark.asyncio
async def test_a_lone_document_is_the_only_candidate_for_home(app, auth_headers, tmp_path):
    _write(tmp_path, "spec/base.html")

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert body["home"] == "spec/base.html"


@pytest.mark.asyncio
async def test_an_index_naming_a_home_that_is_gone_does_not_silently_substitute(
    app, auth_headers, tmp_path
):
    _write(tmp_path, "spec/other.html")
    _index(
        tmp_path,
        {
            "version": 1,
            "home": "spec/base.html",
            "documents": [
                _document(
                    "spec/base.html", title="Base", kind="baseline", status="living", order=1
                ),
                _document(
                    "spec/other.html", title="Other", kind="baseline", status="living", order=2
                ),
            ],
        },
    )

    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert body["home"] is None
    assert any(d["code"] == "home_missing" for d in body["diagnostics"])


@pytest.mark.asyncio
async def test_listing_an_empty_project_is_not_an_error(app, auth_headers, tmp_path):
    body = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert body["specs"] == []
    assert body["home"] is None
    assert body["missing"] == []
