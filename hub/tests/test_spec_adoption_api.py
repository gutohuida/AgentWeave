"""Adopting a document that already exists on disk.

A specification document is a file plus a row. The file travels between machines;
the row does not. These tests cover the route that mints the row from the file —
and, more importantly, cover the thing that route must never do.

**The assertions that matter here are on bytes.** A test that checks a row
appeared passes just as well against `POST /documents`, which mints a row and
then renders a starter file over the path, destroying the document it was aimed
at. That is the failure adoption exists to prevent, so every outcome — success,
each refusal, and the corpus-wide sweep — is asserted against the file's exact
content before and after.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from hub import spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent
from hub.spec_payload import PAYLOAD_ELEMENT_ID, PAYLOAD_MIME

BASE = "/api/v1/projects/proj-test/project"


def _document(
    *,
    title: str = "Agent charter",
    kind: str = "capability",
    status: str | None = "current",
    requirements: list | None = None,
    raw_payload: str | None = None,
) -> str:
    """A document as `spec_render` would have written it.

    Including `aw_identity`, which is the Hub's own map of requirement key to
    minted identifier. A payload without it indexes nothing — deliberately, since
    a requirement indexed under an invented handle is how a link comes to point at
    the wrong thing — so a fixture omitting it would prove requirement indexing
    works when it had simply been skipped.
    """
    if raw_payload is None:
        declared = requirements or []
        payload = {
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
        }
        raw_payload = json.dumps(payload, indent=2)
    head = f"<title>{title}</title>\n" f'<meta name="aw-spec-kind" content="{kind}">\n'
    if status is not None:
        head += f'<meta name="aw-spec-status" content="{status}">\n'
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        f"{head}</head>\n<body>\n<h1>{title}</h1>\n"
        f'<script type="{PAYLOAD_MIME}" id="{PAYLOAD_ELEMENT_ID}">\n{raw_payload}\n</script>\n'
        "</body>\n</html>\n"
    )


def _requirement(key: str = "r1", statement: str = "The Hub adopts a document.") -> dict:
    return {"key": key, "statement": statement, "modal": "SHALL"}


def _write(tmp_path, relative: str, content: str) -> bytes:
    """Write a document and return its bytes, for comparing against afterwards."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    return target.read_bytes()


def _bytes(tmp_path, relative: str) -> bytes:
    return (tmp_path / relative).read_bytes()


async def _adopt(app, path: str, headers):
    return await app.post(f"{BASE}/documents/adopt", json={"path": path}, headers=headers)


class TestAdoptingOneDocument:
    @pytest.mark.asyncio
    async def test_a_document_with_a_payload_is_adopted_from_its_own_identity(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/capabilities/agent-charter/spec.html"
        before = _write(tmp_path, path, _document(title="Agent charter", kind="capability"))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        body = response.json()

        assert body["path"] == path
        assert body["title"] == "Agent charter"
        assert body["kind"] == "capability"
        assert body["phase"] == "current"
        assert body["phase_source"] == "read"
        assert body["id"].startswith("spdoc-")

        # The whole point, asserted on bytes.
        assert _bytes(tmp_path, path) == before

        async with async_session_factory() as session:
            row = (
                await session.execute(select(SpecDocument).where(SpecDocument.path == path))
            ).scalar_one()
            assert row.title == "Agent charter"
            assert row.kind == "capability"
            assert row.phase == "current"

    @pytest.mark.asyncio
    async def test_the_content_digest_records_the_file_as_found(self, app, tmp_path, auth_headers):
        """Design D6. Without a baseline the first outside edit after adoption is
        undetectable, so drift detection would start from nothing."""
        path = "spec/a.html"
        content = _document(title="A")
        _write(tmp_path, path, content)

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["content_digest"] == spec_lifecycle.digest(content)

    @pytest.mark.asyncio
    async def test_a_change_spec_adopts_at_the_phase_its_file_records(
        self, app, tmp_path, auth_headers
    ):
        """`approved` is unreachable from a fresh row through `transition()` — it
        would need walking the document through `proposed` and approving it, which
        invents a history to record one that really happened elsewhere."""
        path = "spec/changes/thing/spec.html"
        _write(tmp_path, path, _document(title="Thing", kind="change-spec", status="approved"))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["phase"] == "approved"
        assert response.json()["phase_source"] == "read"

    @pytest.mark.asyncio
    async def test_a_defaulted_phase_is_reported_as_defaulted(self, app, tmp_path, auth_headers):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A", kind="capability", status=None))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["phase"] == "current"
        assert response.json()["phase_source"] == "defaulted"
        assert response.json()["unrecognised_phase"] is None

    @pytest.mark.asyncio
    async def test_an_unrecognised_phase_is_reported_with_its_value(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A", kind="capability", status="in-review"))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["phase"] == "current"
        assert response.json()["unrecognised_phase"] == "in-review"

    @pytest.mark.asyncio
    async def test_the_requirements_are_indexed_against_the_new_row(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/a.html"
        _write(
            tmp_path,
            path,
            _document(title="A", requirements=[_requirement("r1"), _requirement("r2", "Two.")]),
        )

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert len(response.json()["requirements"]["created"]) == 2

    @pytest.mark.asyncio
    async def test_a_document_with_no_requirements_reports_none_rather_than_failing(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A", requirements=[]))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["requirements"]["created"] == []

    @pytest.mark.asyncio
    async def test_adoption_is_recorded_in_the_document_history(self, app, tmp_path, auth_headers):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A"))
        response = await _adopt(app, path, auth_headers)
        document_id = response.json()["id"]

        async with async_session_factory() as session:
            events = (
                (
                    await session.execute(
                        select(SpecDocumentEvent).where(
                            SpecDocumentEvent.document_id == document_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        kinds = {event.kind for event in events}
        assert "adopted" in kinds
        adopted = next(event for event in events if event.kind == "adopted")
        assert adopted.actor_kind == "operator"
        assert adopted.detail["phase_source"] == "read"


class TestRefusals:
    @pytest.mark.asyncio
    async def test_a_missing_file_is_refused(self, app, tmp_path, auth_headers):
        response = await _adopt(app, "spec/not-here.html", auth_headers)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "file_missing"

    @pytest.mark.asyncio
    async def test_a_file_with_no_payload_is_refused_and_left_alone(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/hand-written.html"
        before = _write(tmp_path, path, "<html><body>written by a person</body></html>")

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "payload_absent"
        assert _bytes(tmp_path, path) == before

        async with async_session_factory() as session:
            rows = (
                (await session.execute(select(SpecDocument).where(SpecDocument.path == path)))
                .scalars()
                .all()
            )
        assert rows == []

    @pytest.mark.asyncio
    async def test_an_unreadable_payload_is_refused_distinctly(self, app, tmp_path, auth_headers):
        path = "spec/broken.html"
        before = _write(tmp_path, path, _document(raw_payload="{ half a payload"))

        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "payload_unreadable"
        assert _bytes(tmp_path, path) == before

    @pytest.mark.asyncio
    async def test_a_path_outside_the_spec_tree_is_refused(self, app, tmp_path, auth_headers):
        outside = tmp_path / "notes.html"
        outside.write_text(_document(title="Notes"), encoding="utf-8")

        for path in ("notes.html", "../notes.html", "/etc/passwd", "spec/../../escape.html"):
            response = await _adopt(app, path, auth_headers)
            assert response.status_code == 400, (path, response.text)
            assert response.json()["detail"]["code"] == "unsafe_document_path"

    @pytest.mark.asyncio
    async def test_a_body_naming_anything_but_a_path_is_refused(self, app, tmp_path, auth_headers):
        """Title, kind and phase come from the file. A caller able to state them
        could state them differently from what the file says."""
        _write(tmp_path, "spec/a.html", _document(title="A"))
        response = await app.post(
            f"{BASE}/documents/adopt",
            json={"path": "spec/a.html", "title": "Something else", "kind": "roadmap"},
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_adoption_refuses_a_credential_that_is_not_the_operators(self, app, tmp_path):
        """`get_project` resolves an operator credential (`aw_live_...`) and nothing
        else, so a run-scoped token cannot bring a document into existence."""
        _write(tmp_path, "spec/a.html", _document(title="A"))
        for headers in ({}, {"Authorization": "Bearer aw_run_not_an_operator"}):
            response = await _adopt(app, "spec/a.html", headers)
            assert response.status_code == 401, response.text


class TestDisagreementIsReportedNotResolved:
    @pytest.mark.asyncio
    async def test_an_already_tracked_path_is_refused(self, app, tmp_path, auth_headers):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A"))
        assert (await _adopt(app, path, auth_headers)).status_code == 201

        second = await _adopt(app, path, auth_headers)
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["code"] == "document_exists"

    @pytest.mark.asyncio
    async def test_agreement_is_reported_as_an_empty_difference_list(
        self, app, tmp_path, auth_headers
    ):
        """Present and empty, never omitted — an absent list and an empty one must
        not be ambiguous to a reader."""
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A"))
        await _adopt(app, path, auth_headers)

        second = await _adopt(app, path, auth_headers)
        assert second.json()["detail"]["differences"] == []

    @pytest.mark.asyncio
    async def test_each_differing_field_is_named_with_both_values(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A", kind="capability", status="current"))
        await _adopt(app, path, auth_headers)

        # The file moves underneath the row — the case drift detection exists for.
        _write(tmp_path, path, _document(title="A renamed", kind="roadmap", status="exploring"))
        second = await _adopt(app, path, auth_headers)

        assert second.status_code == 409, second.text
        differences = {d["field"]: d for d in second.json()["detail"]["differences"]}
        assert differences["title"] == {"field": "title", "file": "A renamed", "row": "A"}
        assert differences["kind"] == {"field": "kind", "file": "roadmap", "row": "capability"}
        assert differences["phase"] == {"field": "phase", "file": "exploring", "row": "current"}

    @pytest.mark.asyncio
    async def test_neither_the_row_nor_the_file_changes_when_disagreement_is_reported(
        self, app, tmp_path, auth_headers
    ):
        path = "spec/a.html"
        _write(tmp_path, path, _document(title="A", kind="capability", status="current"))
        await _adopt(app, path, auth_headers)

        changed = _document(title="A renamed", kind="roadmap", status="exploring")
        before = _write(tmp_path, path, changed)
        response = await _adopt(app, path, auth_headers)
        assert response.status_code == 409

        assert _bytes(tmp_path, path) == before
        async with async_session_factory() as session:
            rows = (
                (await session.execute(select(SpecDocument).where(SpecDocument.path == path)))
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert (rows[0].title, rows[0].kind, rows[0].phase) == ("A", "capability", "current")
