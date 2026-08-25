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
async def test_the_specs_tree_carries_the_document_id_the_panel_shell_keys_tabs_by(
    app, auth_headers, run_headers, tmp_path
):
    """The panel shell (`2026-08-18-one-shell-three-panels`, design D4) keys a `spec:` tab by
    document id so it survives a rename — `/project/specs` has to carry that id for every document
    the Hub actually tracks, the same way it already carries `phase`. A document discovery found on
    disk with no `spec_documents` row (never created through the Hub) reports `document_id: null`;
    the UI's own fallback to path-keying for that case is exercised in `hub/ui`, not here."""
    await _approved_document(app, auth_headers, run_headers)

    listed = await app.get(f"{BASE}/specs", headers=auth_headers)
    entry = next(s for s in listed.json()["specs"] if s["path"] == PATH)
    assert entry["document_id"]
    assert isinstance(entry["document_id"], str)


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
async def test_archiving_a_proposed_document_that_produced_work_is_refused(
    app, auth_headers, run_headers, tmp_path
):
    """Still refused, by a different rule (F37).

    `exploring -> archived` and `proposed -> archived` became legal so that a document created by
    mistake can be retired — but this one carries requirements and tasks, so archiving it here
    would retire work that exists. The refusal moved from the phase map to a guard that asks what
    the document produced, which is the distinction that actually matters.
    """
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
    assert response.json()["detail"]["code"] == "archive_would_orphan_work"


@pytest.mark.asyncio
async def test_an_empty_exploring_document_can_be_retired(app, auth_headers, tmp_path):
    """**This assertion is inverted deliberately** — it used to pin F37 in place.

    Confirmed live 2026-08-25: an agent was given a conversation with a document attached, ignored
    it, created a second one, and wrote the specification there. The first was an empty orphan and
    every exit was closed — `archived` needs `approved`, `approved` needs `proposed`, `proposed`
    needs requirements it does not have, and `DELETE` is 405. It was not inert either: it left a
    standing spec manifest drift warning nobody could clear.

    A document that has produced nothing is a mistake, not abandoned work, and retiring it is the
    operator's to do.
    """
    await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Archive demo"}, headers=auth_headers
    )

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "created by mistake"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "archived"


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


@pytest.mark.asyncio
async def test_first_approved_at_is_set_once_and_survives_a_reopen(app, tmp_path):
    """`task-dependencies` design D6: unlike `explore_closed_at`, which resets to `None` on every
    reopen, `first_approved_at` is set the first time a document is approved and never touched
    again — not on reopening, and not on a second approval."""
    operator = spec_lifecycle.Actor(kind="operator", name="operator")
    async with async_session_factory() as session:
        document = await spec_lifecycle.create_document(
            session,
            "proj-test",
            "spec/changes/first-approved-demo/spec.html",
            actor=operator,
            title="First approved demo",
        )
        assert document.first_approved_at is None

        await spec_lifecycle.close_exploration(session, document, actor=operator)
        await spec_lifecycle.transition(
            session, document, to_phase=spec_lifecycle.PROPOSED, actor=operator
        )
        await spec_lifecycle.transition(
            session, document, to_phase=spec_lifecycle.APPROVED, actor=operator
        )
        first_stamp = document.first_approved_at
        assert first_stamp is not None

        # Reopen. `explore_closed_at` resets; `first_approved_at` must not.
        await spec_lifecycle.transition(
            session, document, to_phase=spec_lifecycle.EXPLORING, actor=operator
        )
        assert document.explore_closed_at is None
        assert document.first_approved_at == first_stamp

        # Approve a second time. Still the original timestamp, not a later one.
        await spec_lifecycle.close_exploration(session, document, actor=operator)
        await spec_lifecycle.transition(
            session, document, to_phase=spec_lifecycle.PROPOSED, actor=operator
        )
        await spec_lifecycle.transition(
            session, document, to_phase=spec_lifecycle.APPROVED, actor=operator
        )
        assert document.first_approved_at == first_stamp
