"""What an adopted document can do afterwards.

Adoption is only worth anything if the row it mints is an ordinary row. The
34 capability documents that motivated this change are readable today and inert:
`GET /specs` finds them on disk, and every other capability — phase, requirements,
coverage, evidence, task materialisation — is keyed on a row they do not have.

So these tests do not check adoption. They check that the things adoption was
blocking now work, through the same surfaces an operator uses, with no knowledge
that the document arrived by a different door.
"""

from __future__ import annotations

import json

import pytest

from hub.spec_payload import PAYLOAD_ELEMENT_ID, PAYLOAD_MIME

BASE = "/api/v1/projects/proj-test/project"


def _document(
    *,
    title: str = "A",
    kind: str = "capability",
    status: str | None = "current",
    requirements: list | None = None,
) -> str:
    declared = requirements or []
    payload = json.dumps(
        {
            "schema_version": 1,
            "kind": kind,
            "title": title,
            "requirements": declared,
            "aw_identity": {
                "requirements": {
                    requirement["key"]: f"FR-{index}"
                    for index, requirement in enumerate(declared, start=1)
                }
            },
        },
        indent=2,
    )
    head = f"<title>{title}</title>\n" f'<meta name="aw-spec-kind" content="{kind}">\n'
    if status is not None:
        head += f'<meta name="aw-spec-status" content="{status}">\n'
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        f"{head}</head>\n<body>\n<h1>{title}</h1>\n"
        f'<script type="{PAYLOAD_MIME}" id="{PAYLOAD_ELEMENT_ID}">\n{payload}\n</script>\n'
        "</body>\n</html>\n"
    )


def _write(tmp_path, relative: str, content: str) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))


def _requirement(key: str, statement: str) -> dict:
    return {"key": key, "statement": statement, "modal": "SHALL"}


async def _adopt(app, path: str, headers):
    return await app.post(f"{BASE}/documents/adopt", json={"path": path}, headers=headers)


@pytest.mark.asyncio
async def test_an_adopted_documents_requirements_resolve_by_identifier(app, tmp_path, auth_headers):
    path = "spec/capabilities/one/spec.html"
    _write(
        tmp_path,
        path,
        _document(
            title="One",
            requirements=[
                _requirement("adopts-a-file", "The Hub SHALL adopt a document from its file."),
                _requirement("never-writes", "Adoption SHALL NOT write to the file."),
            ],
        ),
    )
    adopted = await _adopt(app, path, auth_headers)
    assert adopted.status_code == 201, adopted.text

    response = await app.get(f"{BASE}/spec/requirements/FR-1", headers=auth_headers)
    assert response.status_code == 200, response.text
    requirement = response.json()["requirement"]
    # Resolves by its public identifier, carries the key the document declared,
    # and points at the row adoption minted.
    assert requirement["key"] == "adopts-a-file"
    assert requirement["document_id"] == adopted.json()["id"]
    assert requirement["state"] == "active"

    second = await app.get(f"{BASE}/spec/requirements/FR-2", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["requirement"]["key"] == "never-writes"


@pytest.mark.asyncio
async def test_an_adopted_change_spec_accepts_a_phase_transition(app, tmp_path, auth_headers):
    """`close-exploration` against a row that was never explored on this machine.

    The document arrived carrying a lifecycle; the question is whether the row can
    carry it forward."""
    path = "spec/changes/thing/spec.html"
    _write(tmp_path, path, _document(title="Thing", kind="change-spec", status="exploring"))
    assert (await _adopt(app, path, auth_headers)).status_code == 201

    response = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["explore_closed"] is True


@pytest.mark.asyncio
async def test_get_specs_reports_a_document_id_and_phase_after_adoption(
    app, tmp_path, auth_headers
):
    """Before adoption the tree lists the file with a null id — the UI keys that
    tab by path, the only identity such a document has ever had."""
    path = "spec/capabilities/one/spec.html"
    _write(tmp_path, path, _document(title="One"))

    before = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    entry = next(spec for spec in before["specs"] if spec["path"] == path)
    assert entry["document_id"] is None
    assert entry["phase"] is None

    assert (await _adopt(app, path, auth_headers)).status_code == 201

    after = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    entry = next(spec for spec in after["specs"] if spec["path"] == path)
    assert entry["document_id"] is not None
    assert entry["phase"] == "current"


@pytest.mark.asyncio
async def test_reindex_files_a_previously_unindexable_document_after_adoption(
    app, tmp_path, auth_headers
):
    """The concrete defect: `build_index` files *"only documents that are both on
    disk and known to the Hub"*, so a file with no row can never enter
    `spec/index.json` — which is why `project-instructions` and `quiet-hours` are
    permanently `unfiled` in this repository's own corpus."""
    path = "spec/capabilities/quiet-hours/spec.html"
    _write(tmp_path, path, _document(title="Quiet hours"))

    before = (await app.post(f"{BASE}/spec/reindex", headers=auth_headers)).json()
    unindexable = {
        diagnostic["path"]
        for diagnostic in before["index"]["diagnostics"]
        if diagnostic["code"] == "unindexable_document"
    }
    assert path in unindexable

    assert (await _adopt(app, path, auth_headers)).status_code == 201

    after = (await app.post(f"{BASE}/spec/reindex", headers=auth_headers)).json()
    codes = {diagnostic["code"] for diagnostic in after["index"]["diagnostics"]}
    assert "unindexable_document" not in codes

    index = json.loads((tmp_path / "spec" / "index.json").read_text(encoding="utf-8"))
    entry = next(document for document in index["documents"] if document["path"] == path)
    # Its real title and kind, not a name derived from the path.
    assert entry["title"] == "Quiet hours"
    assert entry["kind"] == "capability"


@pytest.mark.asyncio
async def test_a_corpus_reconstitutes_from_its_files_alone(app, tmp_path, auth_headers):
    """The clone case, end to end: files present, no rows, one call, then the
    corpus is filed with every title and phase its own documents recorded."""
    _write(tmp_path, "spec/agentweave.html", _document(title="Home", kind="system-map"))
    _write(tmp_path, "spec/capabilities/one/spec.html", _document(title="One"))
    _write(tmp_path, "spec/capabilities/two/spec.html", _document(title="Two"))

    assert (await app.post(f"{BASE}/spec/adopt", headers=auth_headers)).status_code == 200
    reindex = await app.post(
        f"{BASE}/spec/reindex", json={"home": "spec/agentweave.html"}, headers=auth_headers
    )
    assert reindex.status_code == 200, reindex.text

    index = json.loads((tmp_path / "spec" / "index.json").read_text(encoding="utf-8"))
    assert index["home"] == "spec/agentweave.html"
    assert {document["title"] for document in index["documents"]} == {"Home", "One", "Two"}

    specs = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()["specs"]
    assert all(spec["document_id"] is not None for spec in specs)
    assert all(spec["state"] == "filed" for spec in specs)
