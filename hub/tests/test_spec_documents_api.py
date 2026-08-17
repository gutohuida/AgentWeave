"""Authoring a document end to end, and the gate that makes approval real.

The load-bearing test here is `test_an_agent_cannot_approve_a_document`. The
skill it replaces enforced approval by instructing the agent to grep the
document's own status metadata and stop if it did not say `approved` — the agent
checking its own permission slip, in a file it could edit. What replaces it has
to be checked against the surface an agent actually has, not against the
intention.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocumentEvent
from hub.main import create_app
from hub.spec_payload import SCHEMA_VERSION, extract_payload

from ._routing import iter_api_routes

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/demo/spec.html"


@pytest.fixture
async def run_headers():
    """A live run credential — the only way an agent reaches `/agent-actions`.

    Identity comes from this token, never from a request body, which is what
    makes "the agent that submitted this" a fact rather than a claim.
    """
    token = "aw_run_spec-doc-run-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-spec-doc",
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


async def _create(app, auth_headers, path=PATH):
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _submit(app, run_headers, document, path=PATH):
    return await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creating_a_document_starts_it_in_exploring(app, auth_headers, tmp_path):
    created = await _create(app, auth_headers)

    assert created["phase"] == "exploring"
    assert created["explore_closed"] is False
    assert (tmp_path / PATH).is_file(), "the document should exist on disk immediately"


@pytest.mark.asyncio
async def test_an_empty_document_is_readable_before_anything_is_written_into_it(
    app, auth_headers, tmp_path
):
    """Explore starts from an empty document, so this is the first thing an
    operator ever sees."""
    await _create(app, auth_headers)

    fetched = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert fetched.status_code == 200
    assert "Demo" in fetched.json()["content"]


@pytest.mark.asyncio
async def test_creating_the_same_document_twice_is_refused(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    again = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Demo"}, headers=auth_headers
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_an_unsafe_document_path_is_refused(app, auth_headers, tmp_path):
    response = await app.post(
        f"{BASE}/documents", json={"path": "../escape.html"}, headers=auth_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_submission_renders_the_document(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)

    response = await _submit(app, run_headers, _document())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["identifiers"] == {"alpha": "FR-1"}
    assert body["blocking"] == []
    assert "It responds within 200ms" in (tmp_path / PATH).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_an_incomplete_submission_is_stored_and_reports_what_blocks_a_proposal(
    app, auth_headers, run_headers, tmp_path
):
    """Saving an incomplete document is not an error. A document under
    discussion is incomplete, and refusing it would make exploring impossible."""
    await _create(app, auth_headers)

    response = await _submit(app, run_headers, _document(tasks=[], acceptance_criteria=[]))

    assert response.status_code == 200
    codes = {item["code"] for item in response.json()["blocking"]}
    assert "requirement_without_task" in codes
    assert "requirement_without_criterion" in codes


@pytest.mark.asyncio
async def test_an_invalid_payload_is_refused_with_its_field_and_writes_nothing(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    before = (tmp_path / PATH).read_text(encoding="utf-8")

    response = await _submit(
        app,
        run_headers,
        _document(requirements=[{"key": "alpha", "statement": "x", "modal": "please"}]),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "requirements[0].modal"
    assert (tmp_path / PATH).read_text(encoding="utf-8") == before, "no partial write"


@pytest.mark.asyncio
async def test_submitting_to_a_document_that_does_not_exist_says_who_starts_one(
    app, auth_headers, run_headers, tmp_path
):
    response = await _submit(app, run_headers, _document(), path="spec/changes/absent/spec.html")
    assert response.status_code == 404
    assert "operator" in response.json()["detail"]


@pytest.mark.asyncio
async def test_identifiers_survive_a_rewording_and_a_reorder(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    first = await _submit(
        app,
        run_headers,
        _document(
            requirements=[
                {"key": "alpha", "statement": "First", "modal": "MUST"},
                {"key": "beta", "statement": "Second", "modal": "SHOULD"},
            ],
            acceptance_criteria=[],
            tasks=[],
        ),
    )
    assert first.json()["identifiers"] == {"alpha": "FR-1", "beta": "FR-2"}

    second = await _submit(
        app,
        run_headers,
        _document(
            requirements=[
                {"key": "inserted", "statement": "New one", "modal": "MUST"},
                {"key": "beta", "statement": "Second, reworded", "modal": "SHOULD"},
                {"key": "alpha", "statement": "First", "modal": "MUST"},
            ],
            acceptance_criteria=[],
            tasks=[],
        ),
    )

    assert second.json()["identifiers"] == {"alpha": "FR-1", "beta": "FR-2", "inserted": "FR-3"}


@pytest.mark.asyncio
async def test_unknown_payload_fields_survive_the_round_trip(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document(gate_policy={"rigor": "gate"}))

    stored = extract_payload((tmp_path / PATH).read_text(encoding="utf-8"))
    assert stored["gate_policy"] == {"rigor": "gate"}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_cannot_approve_a_document(app, auth_headers, run_headers, tmp_path):
    """Checked against the surface an agent actually has, not the intention.

    There is no phase route under `/agent-actions` at all, and the submission
    body forbids extra fields, so neither a phase argument nor a smuggled one
    reaches anything.
    """
    await _create(app, auth_headers)

    # A phase stated in the payload changes nothing.
    await _submit(app, run_headers, _document(phase="approved"))
    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert listed.json()["documents"][0]["phase"] == "exploring"

    # A phase smuggled beside the payload is refused outright.
    smuggled = await app.post(
        AGENT,
        json={"path": PATH, "document": _document(), "phase": "approved"},
        headers=run_headers,
    )
    assert smuggled.status_code == 422

    # And the operator's phase route does not accept a run credential.
    attempted = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": ""},
        headers=run_headers,
    )
    assert attempted.status_code in (401, 403)


@pytest.mark.asyncio
async def test_proposing_reports_every_blocking_check_instead_of_transitioning(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document(tasks=[], scope={"in_scope": [], "non_goals": []}))
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )

    response = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "exploring", "a blocked proposal must not transition"
    codes = {item["code"] for item in body["blocking"]}
    assert {"non_goals_empty", "requirement_without_task"} <= codes


@pytest.mark.asyncio
async def test_a_document_cannot_be_proposed_before_exploration_is_closed(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())

    response = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "explore_not_closed"


@pytest.mark.asyncio
async def test_the_full_operator_path_reaches_approved(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )

    proposed = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    assert proposed.json()["blocking"] == []
    assert proposed.json()["phase"] == "proposed"

    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "looks right"},
        headers=auth_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["phase"] == "approved"

    # The visible status in the file follows the phase rather than leading it.
    content = (tmp_path / PATH).read_text(encoding="utf-8")
    assert 'name="aw-spec-status" content="approved"' in content


@pytest.mark.asyncio
async def test_an_approved_document_refuses_further_submissions(
    app, auth_headers, run_headers, tmp_path
):
    """Silently rewriting what an operator approved would make the approval
    meaningless."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)
    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": ""},
        headers=auth_headers,
    )

    response = await _submit(app, run_headers, _document(title="Changed behind your back"))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_approved"


@pytest.mark.asyncio
async def test_reopening_an_approved_document_requires_closing_exploration_again(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)
    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": ""},
        headers=auth_headers,
    )

    reopened = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "exploring"},
        json={"reason": "more work needed"},
        headers=auth_headers,
    )
    assert reopened.json()["phase"] == "exploring"
    assert reopened.json()["explore_closed"] is False

    blocked = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_an_illegal_transition_is_refused(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": ""},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "illegal_transition"


# ---------------------------------------------------------------------------
# Naming a document nobody understands yet
#
# The path used to be derived in the browser from the operator's opening
# sentence — a permanent identifier minted from the guess that preceded the
# interview, at the one moment nobody knows what the document is about.
# ---------------------------------------------------------------------------


import re  # noqa: E402 - kept beside the tests that need it

PLACEHOLDER_RE = re.compile(r"^spec/changes/[a-z]+-[a-z]+(-[0-9a-f]+)?/spec\.html$")


@pytest.mark.asyncio
async def test_a_document_created_with_no_path_is_given_a_meaningless_one(
    app, auth_headers, tmp_path
):
    response = await app.post(f"{BASE}/documents", json={}, headers=auth_headers)

    assert response.status_code == 201, response.text
    path = response.json()["path"]
    assert PLACEHOLDER_RE.match(path), path
    assert (tmp_path / path).is_file()


@pytest.mark.asyncio
async def test_the_minted_name_says_nothing_about_the_subject(app, auth_headers, tmp_path):
    title = "Personal houseplant watering tracker"
    response = await app.post(f"{BASE}/documents", json={"title": title}, headers=auth_headers)

    path = response.json()["path"]
    for word in ["personal", "houseplant", "watering", "tracker"]:
        assert word not in path, f"the placeholder leaked {word!r} from the title"


@pytest.mark.asyncio
async def test_two_documents_created_the_same_way_do_not_collide(app, auth_headers, tmp_path):
    """The old client-side fallback was the literal `exploration`, so a second
    exploration started the same way was refused as `document_exists`."""
    first = await app.post(f"{BASE}/documents", json={"title": "Same"}, headers=auth_headers)
    second = await app.post(f"{BASE}/documents", json={"title": "Same"}, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 201, second.text
    assert first.json()["path"] != second.json()["path"]


@pytest.mark.asyncio
async def test_the_placeholder_never_becomes_the_title(app, auth_headers, tmp_path):
    """A reader looking at the title is looking for the subject. The old
    fallback took the last path segment and produced the literal "spec"."""
    response = await app.post(f"{BASE}/documents", json={}, headers=auth_headers)

    created = response.json()
    placeholder = created["path"].split("/")[2]
    content = (tmp_path / created["path"]).read_text(encoding="utf-8")

    assert created["title"] == "Untitled exploration"
    assert "<title>Untitled exploration</title>" in content
    for word in placeholder.split("-"):
        assert word not in created["title"].lower()


@pytest.mark.asyncio
async def test_an_explicit_path_is_still_honoured(app, auth_headers, tmp_path):
    created = await _create(app, auth_headers)
    assert created["path"] == PATH


# ---------------------------------------------------------------------------
# Events (D8) — append-only, nothing in this change reads them
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_events_are_append_only_with_no_route_to_change_or_delete_one(
    app, auth_headers, run_headers, tmp_path
):
    """`spec_lifecycle.record_event` says "there is no update and no delete —
    by construction, not by policy." Checked against the actual route table
    rather than the docstring's intention, the same way approval is checked
    in `test_an_agent_cannot_approve_a_document`: no route anywhere in the app
    names a spec document event, so nothing exists to send a PATCH or DELETE
    to. Then, behaviourally, a sequence of writes to one document only ever
    adds rows — an earlier event's fields never change underneath it.
    """
    application = create_app()
    # Walked through `iter_api_routes` rather than `application.routes` directly: newer Starlette
    # keeps included routers as wrappers, so the top-level list holds almost no real routes and a
    # direct scan would find nothing and pass vacuously — which is the worst outcome for a test
    # whose whole job is to prove an absence.
    event_routes = [
        (path, sorted(getattr(route, "methods", None) or []))
        for path, route in iter_api_routes(application)
        if "spec" in path.lower() and "event" in path.lower()
    ]
    assert event_routes == [], f"no route may touch a spec document event, found {event_routes}"

    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)

    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocumentEvent).order_by(SpecDocumentEvent.created_at)
        )
        before = list(result.scalars().all())

    assert len(before) >= 3, "create, submit and propose must each leave a row"
    snapshot = {event.id: (event.kind, event.actor, event.origin, event.detail) for event in before}

    await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "looks right"},
        headers=auth_headers,
    )

    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocumentEvent).order_by(SpecDocumentEvent.created_at)
        )
        after = list(result.scalars().all())

    assert len(after) == len(before) + 1, "approval adds one event and changes nothing else"
    for event in after[: len(before)]:
        assert (event.kind, event.actor, event.origin, event.detail) == snapshot[
            event.id
        ], "an earlier event must not change when a later one is recorded"
