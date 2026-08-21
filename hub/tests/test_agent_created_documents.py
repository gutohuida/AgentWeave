"""An agent that needs a document creates one and keeps working.

`POST /agent-actions/spec/documents/create` reuses the same placeholder-minting
and write path `POST /project/documents` uses, aimed at a name nothing occupies
— so the load-bearing property is that nothing pre-existing ever gets touched
(task 5.7). The rest is the shape every neighbouring agent-actions route
already has: identity from the run's credential, never the body.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocument, SpecDocumentEvent

BASE = "/api/v1/projects/proj-test/project"
CREATE = "/api/v1/agent-actions/spec/documents/create"

PLACEHOLDER = "spec/changes/amber-griffin/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_spec-create-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-spec-create",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _row(path):
    async with async_session_factory() as session:
        result = await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        return result.scalars().first()


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_creates_a_document_with_no_body(app, run_headers, tmp_path):
    response = await app.post(CREATE, json={}, headers=run_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["path"].startswith("spec/changes/")
    assert body["phase"] == "exploring"
    assert (tmp_path / body["path"]).is_file()


@pytest.mark.asyncio
async def test_the_created_document_is_a_change_spec_attributed_to_the_run(
    app, run_headers, tmp_path
):
    response = await app.post(
        CREATE, json={"title": "A finding worth writing up"}, headers=run_headers
    )
    assert response.status_code == 201, response.text
    path = response.json()["path"]

    row = await _row(path)
    assert row is not None
    assert row.kind == "change-spec"
    assert row.phase == "exploring"
    assert row.title == "A finding worth writing up"

    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocumentEvent).where(SpecDocumentEvent.document_id == row.id)
        )
        events = list(result.scalars().all())
    created = [event for event in events if event.kind == "created"]
    assert len(created) == 1
    assert created[0].actor_kind == "agent"
    assert created[0].actor == "claude-1"
    assert created[0].run_id == "run-spec-create"


@pytest.mark.asyncio
async def test_each_call_mints_a_distinct_placeholder(app, run_headers):
    first = await app.post(CREATE, json={}, headers=run_headers)
    second = await app.post(CREATE, json={}, headers=run_headers)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["path"] != second.json()["path"]


@pytest.mark.asyncio
async def test_a_missing_title_produces_the_untitled_placeholder_title(app, run_headers):
    response = await app.post(CREATE, json={}, headers=run_headers)
    path = response.json()["path"]

    row = await _row(path)
    assert row.title == "Untitled exploration"


@pytest.mark.asyncio
async def test_the_created_document_reaches_the_write_layer_not_the_propose_branch(
    app, run_headers, tmp_path
):
    """Task 1.5: a fresh document is `sketch` rigor, so the placeholder write must
    land on disk immediately rather than being queued as a proposal."""
    response = await app.post(CREATE, json={}, headers=run_headers)
    path = response.json()["path"]

    on_disk = (tmp_path / path).read_text(encoding="utf-8")
    assert "aw_identity" in on_disk or "<html" in on_disk

    row = await _row(path)
    assert row.rigor in (None, "sketch")


@pytest.mark.asyncio
async def test_the_document_appears_in_the_operators_list(app, auth_headers, run_headers):
    response = await app.post(CREATE, json={}, headers=run_headers)
    path = response.json()["path"]

    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    paths = [document["path"] for document in listed.json()["documents"]]
    assert path in paths


# ---------------------------------------------------------------------------
# What the body cannot express (task 2.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_body_carrying_identity_or_placement_fields_has_them_ignored(
    app, run_headers, tmp_path
):
    """The route never reads `path`, `kind`, `actor`, `agent` or `run_id` from the
    body — sending them is not a validation error, it is simply not listened to
    (design D2/D3: unexpressible rather than merely refused)."""
    response = await app.post(
        CREATE,
        json={
            "title": "Legit title",
            "path": "spec/capabilities/agent-charter/spec.html",
            "kind": "capability",
            "actor": "operator",
            "agent": "someone-else",
            "run_id": "not-this-run",
        },
        headers=run_headers,
    )

    assert response.status_code == 201, response.text
    path = response.json()["path"]
    assert path != "spec/capabilities/agent-charter/spec.html"
    assert path.startswith("spec/changes/")

    row = await _row(path)
    assert row.kind == "change-spec"

    async with async_session_factory() as session:
        result = await session.execute(
            select(SpecDocumentEvent).where(SpecDocumentEvent.document_id == row.id)
        )
        created = [event for event in result.scalars().all() if event.kind == "created"]
    assert created[0].actor == "claude-1"
    assert created[0].run_id == "run-spec-create"


# ---------------------------------------------------------------------------
# Refusals (task 2.1, 2.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naming_exhaustion_is_a_409(app, run_headers, monkeypatch):
    from hub import spec_naming

    def _exhausted(is_taken):
        raise spec_naming.NamingExhaustedError("every placeholder is taken")

    monkeypatch.setattr(spec_naming, "mint_placeholder_path", _exhausted)

    response = await app.post(CREATE, json={}, headers=run_headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "naming_exhausted"


@pytest.mark.asyncio
async def test_an_unresolvable_workspace_is_a_409(app, run_headers, monkeypatch):
    from hub import project_workspace

    async def _broken(session, project_id):
        raise project_workspace.ProjectWorkspaceError(
            "no such directory", code="directory_missing", directory_state="missing"
        )

    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _broken)

    response = await app.post(CREATE, json={}, headers=run_headers)

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# The corpus is intact (task 5.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creating_documents_repeatedly_never_touches_a_pre_existing_file(
    app, auth_headers, run_headers, tmp_path
):
    existing_path = "spec/changes/houseplant-watering-tracker/spec.html"
    created = await app.post(
        f"{BASE}/documents",
        json={"path": existing_path, "title": "Pre-existing"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    before = (tmp_path / existing_path).read_text(encoding="utf-8")

    for _ in range(5):
        response = await app.post(CREATE, json={}, headers=run_headers)
        assert response.status_code == 201, response.text

    after = (tmp_path / existing_path).read_text(encoding="utf-8")
    assert after == before


@pytest.mark.asyncio
async def test_project_documents_route_is_unchanged_by_this_route_existing(
    app, auth_headers, tmp_path
):
    """Task 5.8: the operator route still works exactly as before."""
    response = await app.post(
        f"{BASE}/documents", json={"title": "Operator-started"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "change-spec"
    assert body["phase"] == "exploring"


# ---------------------------------------------------------------------------
# The full flow, and what it still cannot do (task 5.4, 5.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_full_three_call_flow_creates_renames_and_submits(app, run_headers, tmp_path):
    """Task 5.4: create, rename, submit — no operator step in between."""
    created = await app.post(CREATE, json={}, headers=run_headers)
    assert created.status_code == 201, created.text
    placeholder = created.json()["path"]

    renamed = await app.post(
        "/api/v1/agent-actions/spec/documents/rename",
        json={"path": placeholder, "subject": "How the retry queue backs off"},
        headers=run_headers,
    )
    assert renamed.status_code == 200, renamed.text
    path = renamed.json()["path"]
    assert path != placeholder
    assert not (tmp_path / placeholder).exists()
    assert (tmp_path / path).is_file()

    submitted = await app.post(
        "/api/v1/agent-actions/spec/documents",
        json={
            "path": path,
            "document": {
                "schema_version": 1,
                "kind": "change-spec",
                "title": "How the retry queue backs off",
            },
        },
        headers=run_headers,
    )
    assert submitted.status_code == 200, submitted.text

    row = await _row(path)
    assert row is not None
    assert row.phase == "exploring"


@pytest.mark.asyncio
async def test_the_creating_agent_cannot_propose_or_approve_its_own_document(
    app, run_headers, auth_headers
):
    """Task 5.6: the phase starts and stays `exploring` under the agent's own
    surface — `/agent-actions` has no propose/approve/transition/archive route
    at all, and the operator route that does refuses a run credential outright."""
    created = await app.post(CREATE, json={}, headers=run_headers)
    path = created.json()["path"]
    assert created.json()["phase"] == "exploring"

    propose_as_agent = await app.post(
        f"{BASE}/documents/propose", params={"path": path}, headers=run_headers
    )
    assert propose_as_agent.status_code == 401

    row = await _row(path)
    assert row.phase == "exploring"


@pytest.mark.asyncio
async def test_no_schema_states_the_retired_operator_only_rule():
    """Task 4.4: the rule this change retires must not survive as a third
    statement in a place `grep`-ing turn-context and tool descriptions misses —
    the OpenAPI schema Pydantic derives from a model's own docstring."""
    from hub.api.v1.agent_actions import SpecDocumentSubmission

    schema = SpecDocumentSubmission.model_json_schema()
    description = schema.get("description", "")
    assert "operator" not in description.lower() or "create_spec_document" in description


@pytest.mark.asyncio
async def test_creation_does_not_depend_on_the_agent_job_allowance(app, run_headers, tmp_path):
    """Task 5.5, design D5: `allow_agent_jobs` gates *jobs*, and must not gate this.

    Every other test here already runs against `proj-test`, which never sets the flag — so the
    flow was known to work while it was false, but only incidentally, and an incidental pass says
    nothing about intent. Asserted against both values explicitly, with the false case written
    first: a future reader changing the job allowance should see this fail if they reach for the
    same flag to gate document creation.
    """
    from hub.db.models import Project

    async def set_allowance(value: bool) -> None:
        async with async_session_factory() as session:
            project = await session.get(Project, "proj-test")
            project.allow_agent_jobs = value
            await session.commit()

    await set_allowance(False)
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project.allow_agent_jobs is False

    while_disallowed = await app.post(CREATE, json={}, headers=run_headers)
    assert while_disallowed.status_code == 201, while_disallowed.text
    first_path = while_disallowed.json()["path"]
    assert await _row(first_path) is not None

    await set_allowance(True)
    allowed = await app.post(CREATE, json={}, headers=run_headers)
    assert allowed.status_code == 201, allowed.text
    # Distinct documents either way — the flag changes nothing about this route at all.
    assert allowed.json()["path"] != first_path
