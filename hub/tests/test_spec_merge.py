"""Folding a finished change into a capability document — the corpus absorbing what shipped.

An explicit authored merge, not automatic requirement migration: the operator supplies the payload
a capability document ends up with and cites which finished changes it draws from. Every refusal
happens before anything is written (design D5), the same discipline `rename_document` follows.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocumentEvent, SpecDocumentMerge
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
CAP_PATH = "spec/capabilities/demo/spec.html"
CHANGE_PATH = "spec/changes/demo/spec.html"
CHANGE2_PATH = "spec/changes/demo-two/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_merge-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-merge",
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
        "title": "Demo",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
    }
    payload.update(overrides)
    return payload


def _capability_payload(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability",
        "title": "Demo capability",
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
    }
    payload.update(overrides)
    return payload


async def _approve(app, auth_headers, run_headers, path):
    await app.post(f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers)
    await app.post(AGENT, json={"path": path, "document": _document()}, headers=run_headers)
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": path}, headers=auth_headers)
    await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "approved"},
        json={"reason": ""},
        headers=auth_headers,
    )


async def _capability(app, auth_headers, path=CAP_PATH):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_a_merge_from_an_approved_change_writes_a_row_and_an_event(
    app, auth_headers, run_headers, tmp_path
):
    await _capability(app, auth_headers)
    await _approve(app, auth_headers, run_headers, CHANGE_PATH)

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={
            "payload": _capability_payload(),
            "from_changes": [CHANGE_PATH],
            "note": "folded in the timing requirement",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["merged"] == 1

    async with async_session_factory() as session:
        rows = (await session.execute(select(SpecDocumentMerge))).scalars().all()
        assert len(rows) == 1
        assert rows[0].actor_kind == "operator"
        assert rows[0].note == "folded in the timing requirement"

        events = (
            (
                await session.execute(
                    select(SpecDocumentEvent).where(SpecDocumentEvent.kind == "merged")
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].detail["change_document_id"] == rows[0].change_document_id


@pytest.mark.asyncio
async def test_a_merge_naming_an_unfinished_source_is_refused(
    app, auth_headers, run_headers, tmp_path
):
    await _capability(app, auth_headers)
    await app.post(
        f"{BASE}/documents", json={"path": CHANGE_PATH, "title": "Demo"}, headers=auth_headers
    )
    await app.post(AGENT, json={"path": CHANGE_PATH, "document": _document()}, headers=run_headers)
    # Still exploring — proposed never happened.

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={"payload": _capability_payload(), "from_changes": [CHANGE_PATH]},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "source_not_finished"


@pytest.mark.asyncio
async def test_a_merge_naming_a_capability_document_as_source_is_refused(
    app, auth_headers, tmp_path
):
    """D5 step 4 already refuses any source whose phase is not (approved, archived) — a
    capability document's phase is always `current`, so this is the same refusal, not a
    separate one."""
    await _capability(app, auth_headers, path=CAP_PATH)
    await _capability(app, auth_headers, path="spec/capabilities/other/spec.html")

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={
            "payload": _capability_payload(),
            "from_changes": ["spec/capabilities/other/spec.html"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "source_not_finished"


@pytest.mark.asyncio
async def test_a_merge_against_a_non_capability_document_is_refused(
    app, auth_headers, run_headers, tmp_path
):
    await _approve(app, auth_headers, run_headers, CHANGE_PATH)
    await _approve(app, auth_headers, run_headers, CHANGE2_PATH)

    response = await app.post(
        f"{BASE}/documents/{CHANGE_PATH}/merge",
        json={"payload": _document(), "from_changes": [CHANGE2_PATH]},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_a_capability"


@pytest.mark.asyncio
async def test_two_merges_from_different_changes_accumulate_two_rows(
    app, auth_headers, run_headers, tmp_path
):
    await _capability(app, auth_headers)
    await _approve(app, auth_headers, run_headers, CHANGE_PATH)
    await _approve(app, auth_headers, run_headers, CHANGE2_PATH)

    await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={"payload": _capability_payload(), "from_changes": [CHANGE_PATH]},
        headers=auth_headers,
    )
    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={
            "payload": _capability_payload(title="Demo capability, revised"),
            "from_changes": [CHANGE2_PATH],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    async with async_session_factory() as session:
        rows = (await session.execute(select(SpecDocumentMerge))).scalars().all()
        assert len(rows) == 2
        assert len({row.change_document_id for row in rows}) == 2


@pytest.mark.asyncio
async def test_a_malformed_merge_payload_is_refused_the_same_as_any_other_submission(
    app, auth_headers, run_headers, tmp_path
):
    await _capability(app, auth_headers)
    await _approve(app, auth_headers, run_headers, CHANGE_PATH)

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={
            "payload": {"schema_version": SCHEMA_VERSION, "kind": "capability"},
            "from_changes": [CHANGE_PATH],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "payload_invalid"


@pytest.mark.asyncio
async def test_a_merge_naming_a_missing_source_404s_with_the_path(app, auth_headers, tmp_path):
    await _capability(app, auth_headers)

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={"payload": _capability_payload(), "from_changes": ["spec/changes/nope/spec.html"]},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert "spec/changes/nope/spec.html" in response.json()["detail"]


@pytest.mark.asyncio
async def test_an_agent_has_no_route_to_merge(app, auth_headers, run_headers, tmp_path):
    await _capability(app, auth_headers)
    await _approve(app, auth_headers, run_headers, CHANGE_PATH)

    response = await app.post(
        f"{BASE}/documents/{CAP_PATH}/merge",
        json={"payload": _capability_payload(), "from_changes": [CHANGE_PATH]},
        headers=run_headers,
    )

    assert response.status_code in (401, 403)
