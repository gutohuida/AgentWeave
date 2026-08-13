"""A document earns its name, and what moves when it does.

The interesting assertions here are the ones about what does *not* change. A
rename is the first operation that mutates the handle every other part of the
system uses to find a document, so the risk is not that the file fails to move
— it is that something silently keeps pointing at where it used to be, or that
the move takes identity with it.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, SpecDocument, SpecDocumentEvent
from hub.spec_payload import SCHEMA_VERSION, extract_payload

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
RENAME = "/api/v1/agent-actions/spec/documents/rename"

PLACEHOLDER = "spec/changes/amber-griffin/spec.html"
NAMED = "spec/changes/houseplant-watering-tracker/spec.html"
SUBJECT = "Houseplant watering tracker"


@pytest.fixture
async def run_headers():
    token = "aw_run_spec-rename-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-spec-rename",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Houseplant watering tracker",
        "scope": {"in_scope": ["watering"], "non_goals": ["photos"]},
        "requirements": [
            {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
        ],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
    }
    payload.update(overrides)
    return payload


async def _create(app, auth_headers, path=PLACEHOLDER):
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _rename(app, run_headers, subject=SUBJECT, path=PLACEHOLDER):
    return await app.post(RENAME, json={"path": path, "subject": subject}, headers=run_headers)


async def _row(path):
    async with async_session_factory() as session:
        result = await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        return result.scalars().first()


# ---------------------------------------------------------------------------
# The move itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_subject_becomes_the_documents_path(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)

    response = await _rename(app, run_headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"path": NAMED, "previous_path": PLACEHOLDER}
    assert await _row(NAMED) is not None
    assert await _row(PLACEHOLDER) is None


@pytest.mark.asyncio
async def test_the_file_moves_and_the_old_directory_does_not_linger(
    app, auth_headers, run_headers, tmp_path
):
    """A husk directory would put a name the document no longer has back into
    discovery, which walks the tree rather than reading the records."""
    await _create(app, auth_headers)

    await _rename(app, run_headers)

    assert (tmp_path / NAMED).is_file()
    assert not (tmp_path / PLACEHOLDER).exists()
    assert not (tmp_path / "spec/changes/amber-griffin").exists()


@pytest.mark.asyncio
async def test_the_renamed_document_is_the_one_that_is_listed(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _rename(app, run_headers)

    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    paths = [document["path"] for document in listed.json()["documents"]]
    assert paths == [NAMED]

    fetched = await app.get(f"{BASE}/spec", params={"path": NAMED}, headers=auth_headers)
    assert fetched.status_code == 200


# ---------------------------------------------------------------------------
# What a rename must not take with it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_content_and_identifiers_survive_the_move(
    app, auth_headers, run_headers, tmp_path
):
    created = await _create(app, auth_headers)
    submitted = await app.post(
        SUBMIT, json={"path": PLACEHOLDER, "document": _document()}, headers=run_headers
    )
    assert submitted.status_code == 200, submitted.text
    identifiers_before = submitted.json()["identifiers"]
    content_before = (tmp_path / PLACEHOLDER).read_text(encoding="utf-8")

    await _rename(app, run_headers)

    row = await _row(NAMED)
    assert row.id == created["id"], "identity is the row's id and never was the path"
    assert (tmp_path / NAMED).read_text(encoding="utf-8") == content_before

    payload = extract_payload(content_before)
    assert payload["aw_identity"]["requirements"] == identifiers_before


@pytest.mark.asyncio
async def test_the_history_is_kept_and_the_rename_is_recorded(
    app, auth_headers, run_headers, tmp_path
):
    created = await _create(app, auth_headers)
    await _rename(app, run_headers)

    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocumentEvent).where(SpecDocumentEvent.document_id == created["id"])
        )
        events = list(result.scalars().all())

    kinds = [event.kind for event in events]
    assert "created" in kinds, "the earlier history is not rewritten"
    renamed = [event for event in events if event.kind == "renamed"]
    assert len(renamed) == 1
    assert renamed[0].detail["from"] == PLACEHOLDER
    assert renamed[0].detail["to"] == NAMED
    assert renamed[0].actor_kind == "agent"


@pytest.mark.asyncio
async def test_a_document_can_still_be_written_at_its_new_path(
    app, auth_headers, run_headers, tmp_path
):
    """The turn that renames is usually the turn that then writes."""
    await _create(app, auth_headers)
    renamed = await _rename(app, run_headers)

    submitted = await app.post(
        SUBMIT,
        json={"path": renamed.json()["path"], "document": _document()},
        headers=run_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["path"] == NAMED


# ---------------------------------------------------------------------------
# Queued turns
# ---------------------------------------------------------------------------


async def _queue_entry(entry_id, path, *, delivered):
    async with async_session_factory() as session:
        session.add(
            InboundQueueEntry(
                id=entry_id,
                project_id="proj-test",
                agent="claude-1",
                origin_type="operator",
                content="carry on",
                hop_depth=0,
                spec_document=path,
                delivered_at=datetime(2026, 8, 13, tzinfo=timezone.utc) if delivered else None,
            )
        )
        await session.commit()


async def _entry_path(entry_id):
    async with async_session_factory() as session:
        result = await session.execute(
            select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)
        )
        return result.scalars().first().spec_document


@pytest.mark.asyncio
async def test_a_queued_turn_follows_the_document(app, auth_headers, run_headers, tmp_path):
    """A queue entry carries a path snapshot, and a busy agent's turn starts
    from a later scheduler call than the one that queued it."""
    await _create(app, auth_headers)
    await _queue_entry("qe-pending", PLACEHOLDER, delivered=False)

    await _rename(app, run_headers)

    assert await _entry_path("qe-pending") == NAMED


@pytest.mark.asyncio
async def test_a_delivered_turn_keeps_the_path_it_ran_with(
    app, auth_headers, run_headers, tmp_path
):
    """That entry is history: it records what was open when its turn ran."""
    await _create(app, auth_headers)
    await _queue_entry("qe-delivered", PLACEHOLDER, delivered=True)

    await _rename(app, run_headers)

    assert await _entry_path("qe-delivered") == PLACEHOLDER


# ---------------------------------------------------------------------------
# Refusals — none of which may move anything
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_approved_document_is_not_renamed(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)
    await app.post(SUBMIT, json={"path": PLACEHOLDER, "document": _document()}, headers=run_headers)
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PLACEHOLDER}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": PLACEHOLDER}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PLACEHOLDER, "to": "approved"},
        json={"reason": "looks right"},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text

    response = await _rename(app, run_headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_approved"
    assert (tmp_path / PLACEHOLDER).is_file()
    assert await _row(PLACEHOLDER) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["???", "   ", "!!!"])
async def test_a_subject_that_is_not_a_name_is_refused(
    app, auth_headers, run_headers, tmp_path, subject
):
    """No placeholder is minted to stand in for a failed rename — saying so is
    better than quietly producing a second meaningless name."""
    await _create(app, auth_headers)

    response = await _rename(app, run_headers, subject=subject)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "subject_unusable"
    assert await _row(PLACEHOLDER) is not None


@pytest.mark.asyncio
async def test_a_name_another_document_holds_is_refused(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)
    await _create(app, auth_headers, path=NAMED)

    response = await _rename(app, run_headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_exists"
    assert await _row(PLACEHOLDER) is not None
    assert (tmp_path / PLACEHOLDER).is_file()


@pytest.mark.asyncio
async def test_a_file_somebody_put_there_by_hand_is_refused(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    occupied = tmp_path / NAMED
    occupied.parent.mkdir(parents=True, exist_ok=True)
    occupied.write_text("<html>mine</html>", encoding="utf-8")

    response = await _rename(app, run_headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "path_occupied"
    assert occupied.read_text(encoding="utf-8") == "<html>mine</html>"


@pytest.mark.asyncio
async def test_renaming_a_document_that_does_not_exist_says_so(app, run_headers):
    response = await _rename(app, run_headers, path="spec/changes/nothing-here/spec.html")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_renaming_to_the_name_it_already_has_is_not_an_error(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers, path=NAMED)

    response = await _rename(app, run_headers, path=NAMED)

    assert response.status_code == 200
    assert response.json() == {"path": NAMED, "previous_path": NAMED}
    assert (tmp_path / NAMED).is_file()


@pytest.mark.asyncio
async def test_the_agent_cannot_express_a_destination(app, auth_headers, run_headers, tmp_path):
    """The tool takes a subject. A path in the body is not a hostile value that
    gets sanitised — it is a field that does not exist."""
    await _create(app, auth_headers)

    response = await app.post(
        RENAME,
        json={"path": PLACEHOLDER, "subject": SUBJECT, "to": "spec/../../evil.html"},
        headers=run_headers,
    )

    assert response.status_code == 422
    assert await _row(PLACEHOLDER) is not None


@pytest.mark.asyncio
async def test_a_traversal_in_the_subject_becomes_an_ordinary_name(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)

    response = await _rename(app, run_headers, subject="../../etc/passwd")

    assert response.status_code == 200
    path = response.json()["path"]
    assert path == "spec/changes/etc-passwd/spec.html"
    assert (tmp_path / path).is_file()
