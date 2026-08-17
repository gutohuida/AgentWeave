"""Archiving a document — the operator act that follows approval.

Mirrors `test_an_agent_cannot_approve_a_document` in `test_spec_documents_api.py`: an agent has no
route to archive at all (the phase route requires the project credential), so that refusal is
checked at the API boundary. The refusal *inside* `spec_lifecycle.transition()` itself has no HTTP
path that reaches it with an agent actor — there is no route to reach it through — so it is checked
directly here, the same way design D1 states the rule exists "here as well as at the API boundary."
"""

import pytest

from hub import spec_lifecycle
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/archive-demo/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_archive-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-archive",
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
        "title": "Archive demo",
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


async def _approved_document(app, auth_headers, run_headers, path=PATH):
    await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Archive demo"}, headers=auth_headers
    )
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


@pytest.mark.asyncio
async def test_an_approved_document_archives(app, auth_headers, run_headers, tmp_path):
    await _approved_document(app, auth_headers, run_headers)

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "shipped"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "archived"


@pytest.mark.asyncio
async def test_the_specs_tree_reports_phase_for_a_document_that_never_moved(
    app, auth_headers, run_headers, tmp_path
):
    """Archiving is a phase transition, not a move — `PATH` here is `spec/changes/archive-demo/
    spec.html`, nowhere near `spec/changes/archive/`. The tree the UI builds its navigation from
    has no other way to learn the document is archived, so `/project/specs` has to carry the phase
    alongside the path rather than leaving archived-detection to a directory convention this flow
    never follows."""
    await _approved_document(app, auth_headers, run_headers)

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    before = {s["path"]: s.get("phase") for s in listed.json()["specs"]}
    assert before[PATH] == "approved"

    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "shipped"},
        headers=auth_headers,
    )

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    after = {s["path"]: s.get("phase") for s in listed.json()["specs"]}
    assert after[PATH] == "archived"


@pytest.mark.asyncio
async def test_archiving_does_not_touch_tasks(app, auth_headers, run_headers, tmp_path):
    await _approved_document(app, auth_headers, run_headers)
    tasks_before = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    before = {task["id"]: task["status"] for task in tasks_before.json()}
    assert before, "approval should have materialised at least one task"

    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "shipped"},
        headers=auth_headers,
    )

    tasks_after = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    after = {task["id"]: task["status"] for task in tasks_after.json()}
    assert after == before


@pytest.mark.asyncio
async def test_archiving_a_proposed_document_is_refused(app, auth_headers, run_headers, tmp_path):
    await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Archive demo"}, headers=auth_headers
    )
    await app.post(AGENT, json={"path": PATH, "document": _document()}, headers=run_headers)
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": ""},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "illegal_transition"


@pytest.mark.asyncio
async def test_archiving_an_exploring_document_is_refused(app, auth_headers, tmp_path):
    await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Archive demo"}, headers=auth_headers
    )

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": ""},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "illegal_transition"


@pytest.mark.asyncio
async def test_an_archived_document_has_no_legal_outgoing_transition(
    app, auth_headers, run_headers, tmp_path
):
    await _approved_document(app, auth_headers, run_headers)
    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "shipped"},
        headers=auth_headers,
    )

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "exploring"},
        json={"reason": ""},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "illegal_transition"


@pytest.mark.asyncio
async def test_an_agent_has_no_route_to_archive(app, auth_headers, run_headers, tmp_path):
    """Mirrors `test_an_agent_cannot_approve_a_document`: the phase route requires the project
    credential, so a run token never reaches it at all."""
    await _approved_document(app, auth_headers, run_headers)

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": ""},
        headers=run_headers,
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_transition_itself_refuses_an_agent_actor_archiving(app, auth_headers, tmp_path):
    """`spec_lifecycle.transition()`'s own operator-only check for archiving, exercised directly —
    there is no HTTP path that reaches this specific line with an agent actor, since the route
    above already refuses the credential first. Design D1: the check exists "here as well as at
    the API boundary," so both are worth a test."""
    async with async_session_factory() as session:
        document = await spec_lifecycle.create_document(
            session,
            "proj-test",
            "spec/changes/archive-direct/spec.html",
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
            title="Direct",
        )
        document.phase = spec_lifecycle.APPROVED
        await session.flush()

        with pytest.raises(spec_lifecycle.PhaseError) as excinfo:
            await spec_lifecycle.transition(
                session,
                document,
                to_phase=spec_lifecycle.ARCHIVED,
                actor=spec_lifecycle.Actor(kind="agent", name="claude-1", run_id="run-x"),
            )
        assert excinfo.value.code == "archive_is_the_operators"
        assert document.phase == spec_lifecycle.APPROVED, "a refused transition must not mutate"
