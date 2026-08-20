"""Adopting a whole corpus, and proving adoption never writes.

The case this covers is a project whose database was created after its files —
a clone, a migration, a restored machine. The files are there and inert; nothing
about them is reachable because every capability except the read path is keyed on
a row that does not travel.

Two things are being held here at once:

**The sweep is per-document.** One hand-written file must not cost the other
thirty-three their rows, and a second run must adopt nothing rather than
duplicate everything.

**Nothing is written.** Asserted on the bytes of every file in the tree, before
and after, including a snapshot of the whole directory — because the failure this
change exists to prevent is a route that mints a row and then renders a starter
file over the document it was aimed at.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from hub import spec_adoption, spec_documents
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.spec_payload import PAYLOAD_ELEMENT_ID, PAYLOAD_MIME

BASE = "/api/v1/projects/proj-test/project"


def _document(
    *,
    title: str = "A",
    kind: str = "capability",
    status: str | None = "current",
    requirements: list | None = None,
    raw_payload: str | None = None,
) -> str:
    if raw_payload is None:
        declared = requirements or []
        raw_payload = json.dumps(
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
        f'<script type="{PAYLOAD_MIME}" id="{PAYLOAD_ELEMENT_ID}">\n{raw_payload}\n</script>\n'
        "</body>\n</html>\n"
    )


def _write(tmp_path, relative: str, content: str) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))


def _snapshot(tmp_path) -> dict:
    """Every file beneath the tree, by relative path, as bytes.

    A whole-tree snapshot rather than a per-file check: a route that wrote a new
    file, deleted one, or moved one would pass a check that only compared the
    documents it was handed.
    """
    return {
        item.relative_to(tmp_path).as_posix(): item.read_bytes()
        for item in sorted(tmp_path.rglob("*"))
        if item.is_file()
    }


def _corpus(tmp_path) -> None:
    """Three adoptable documents, one hand-written file, one damaged payload.

    Shaped like this repository's own corpus, which is the case the change was
    written for: capability documents at `current`, and a single `system-map` home
    at `exploring`. The home's phase is stated rather than defaulted because
    `current` and `capability` imply each other — a `system-map` claiming `current`
    is an inconsistency the real corpus does not have, and a fixture carrying one
    quietly tests D3a's fallback instead of the sweep.
    """
    _write(
        tmp_path,
        "spec/agentweave.html",
        _document(title="Home", kind="system-map", status="exploring"),
    )
    _write(tmp_path, "spec/capabilities/one/spec.html", _document(title="One"))
    _write(tmp_path, "spec/capabilities/two/spec.html", _document(title="Two"))
    _write(tmp_path, "spec/notes.html", "<html><body>written by a person</body></html>")
    _write(tmp_path, "spec/capabilities/broken/spec.html", _document(raw_payload="{ oops"))


async def _adopt_corpus(app, headers):
    return await app.post(f"{BASE}/spec/adopt", headers=headers)


class TestCorpusAdoption:
    @pytest.mark.asyncio
    async def test_every_untracked_document_with_a_payload_is_adopted(
        self, app, tmp_path, auth_headers
    ):
        _corpus(tmp_path)

        response = await _adopt_corpus(app, auth_headers)
        assert response.status_code == 200, response.text
        body = response.json()

        assert set(body["adopted"]) == {
            "spec/agentweave.html",
            "spec/capabilities/one/spec.html",
            "spec/capabilities/two/spec.html",
        }
        assert body["documents"]["spec/capabilities/one/spec.html"]["title"] == "One"
        assert body["documents"]["spec/agentweave.html"]["kind"] == "system-map"

    @pytest.mark.asyncio
    async def test_one_unadoptable_document_does_not_abort_the_sweep(
        self, app, tmp_path, auth_headers
    ):
        """Design D5. A corpus recovery that gives up at the first hand-written
        file is not a recovery."""
        _corpus(tmp_path)

        body = (await _adopt_corpus(app, auth_headers)).json()

        assert set(body["skipped"]) == {
            "spec/notes.html",
            "spec/capabilities/broken/spec.html",
        }
        assert body["documents"]["spec/notes.html"]["code"] == "payload_absent"
        assert body["documents"]["spec/capabilities/broken/spec.html"]["code"] == (
            "payload_unreadable"
        )
        assert len(body["adopted"]) == 3

    @pytest.mark.asyncio
    async def test_every_discovered_path_is_reported_either_way(self, app, tmp_path, auth_headers):
        """A document missing from the report looks identical to one that was
        never there."""
        _corpus(tmp_path)
        body = (await _adopt_corpus(app, auth_headers)).json()
        assert set(body["documents"]) == set(body["adopted"]) | set(body["skipped"])
        assert len(body["documents"]) == 5

    @pytest.mark.asyncio
    async def test_a_second_run_adopts_nothing_and_creates_no_duplicates(
        self, app, tmp_path, auth_headers
    ):
        _corpus(tmp_path)
        await _adopt_corpus(app, auth_headers)

        second = (await _adopt_corpus(app, auth_headers)).json()
        assert second["adopted"] == []
        for path in ("spec/agentweave.html", "spec/capabilities/one/spec.html"):
            assert second["documents"][path]["code"] == "document_exists"
            # Nothing moved underneath the row between the two runs.
            assert second["documents"][path]["differences"] == []

        async with async_session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(SpecDocument))
        assert total == 3

    @pytest.mark.asyncio
    async def test_an_empty_tree_is_not_an_error(self, app, tmp_path, auth_headers):
        response = await _adopt_corpus(app, auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["documents"] == {}

    @pytest.mark.asyncio
    async def test_discovery_truncation_is_surfaced_rather_than_presented_as_complete(
        self, app, tmp_path, auth_headers, monkeypatch
    ):
        """`discover()` caps at `MAX_DISCOVERED_DOCUMENTS` and says so. A sweep
        that swallowed the diagnostic would report a partial corpus as the corpus."""
        monkeypatch.setattr(spec_documents, "MAX_DISCOVERED_DOCUMENTS", 2)
        _corpus(tmp_path)

        body = (await _adopt_corpus(app, auth_headers)).json()
        codes = {diagnostic["code"] for diagnostic in body["diagnostics"]}
        assert "discovery_truncated" in codes
        assert len(body["documents"]) == 2

    @pytest.mark.asyncio
    async def test_corpus_adoption_refuses_a_credential_that_is_not_the_operators(
        self, app, tmp_path
    ):
        _corpus(tmp_path)
        for headers in ({}, {"Authorization": "Bearer aw_run_not_an_operator"}):
            response = await _adopt_corpus(app, headers)
            assert response.status_code == 401, response.text


class TestNothingIsWritten:
    """The single most important property in this change, asserted on bytes."""

    @pytest.mark.asyncio
    async def test_a_successful_adoption_leaves_the_file_byte_identical(
        self, app, tmp_path, auth_headers
    ):
        _write(tmp_path, "spec/a.html", _document(title="A"))
        before = _snapshot(tmp_path)

        response = await app.post(
            f"{BASE}/documents/adopt", json={"path": "spec/a.html"}, headers=auth_headers
        )
        assert response.status_code == 201, response.text
        assert _snapshot(tmp_path) == before

    @pytest.mark.parametrize(
        ("path", "content", "expected_code"),
        [
            ("spec/a.html", "<html><body>no payload</body></html>", "payload_absent"),
            ("spec/a.html", None, "payload_unreadable"),
            ("spec/a.html", None, "payload_identity_missing"),
        ],
    )
    @pytest.mark.asyncio
    async def test_each_refusal_leaves_the_file_byte_identical(
        self, app, tmp_path, auth_headers, path, content, expected_code
    ):
        if expected_code == "payload_unreadable":
            content = _document(raw_payload="{ not json")
        elif expected_code == "payload_identity_missing":
            content = _document(raw_payload=json.dumps({"schema_version": 1, "kind": "capability"}))
        _write(tmp_path, path, content)
        before = _snapshot(tmp_path)

        response = await app.post(
            f"{BASE}/documents/adopt", json={"path": path}, headers=auth_headers
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == expected_code
        assert _snapshot(tmp_path) == before

    @pytest.mark.asyncio
    async def test_a_refusal_for_an_already_tracked_path_leaves_the_file_byte_identical(
        self, app, tmp_path, auth_headers
    ):
        _write(tmp_path, "spec/a.html", _document(title="A"))
        await app.post(
            f"{BASE}/documents/adopt", json={"path": "spec/a.html"}, headers=auth_headers
        )
        before = _snapshot(tmp_path)

        response = await app.post(
            f"{BASE}/documents/adopt", json={"path": "spec/a.html"}, headers=auth_headers
        )
        assert response.status_code == 409
        assert _snapshot(tmp_path) == before

    @pytest.mark.asyncio
    async def test_a_missing_file_is_not_created_by_being_adopted(
        self, app, tmp_path, auth_headers
    ):
        """The failure mode in miniature: `POST /documents` would write one here."""
        before = _snapshot(tmp_path)
        response = await app.post(
            f"{BASE}/documents/adopt", json={"path": "spec/absent.html"}, headers=auth_headers
        )
        assert response.status_code == 422
        assert _snapshot(tmp_path) == before
        assert not (tmp_path / "spec" / "absent.html").exists()

    @pytest.mark.asyncio
    async def test_corpus_adoption_leaves_every_file_in_the_tree_byte_identical(
        self, app, tmp_path, auth_headers
    ):
        _corpus(tmp_path)
        before = _snapshot(tmp_path)

        response = await _adopt_corpus(app, auth_headers)
        assert response.status_code == 200, response.text
        after = _snapshot(tmp_path)

        assert after == before
        # Stated separately: equal dicts would also hold if both were empty.
        assert len(before) == 5

    @pytest.mark.asyncio
    async def test_the_adoption_module_imports_no_writer(self):
        """The guarantee, checked structurally rather than by review.

        Every function adoption composes is read-only on disk, and the one that
        mints the row takes no workspace and therefore cannot reach the
        filesystem. This asserts the module never acquired a way to.
        """
        source = __import__("pathlib").Path(spec_adoption.__file__).read_text(encoding="utf-8")
        for writer in (
            "write_document",
            "write_index",
            "move_document",
            "save_document",
            "write_text",
            "write_bytes",
            "open(",
        ):
            assert writer not in source, writer
