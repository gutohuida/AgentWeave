"""Capability documents: created at `current`, written only by the operator through a merge.

Creation is operator-only already (`POST /project/documents` requires the project credential and
hardcodes `actor=_operator()`), so what this file actually has to prove is everything downstream
of that: the phase a capability document lands in, that `transition()` refuses to move it anywhere
(including back to `current` itself), that an ordinary agent submission against one is refused, and
that a document's `kind` cannot be changed by a later submission — capability-specific or not.
"""

import pytest

from hub import spec_lifecycle
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
CAP_PATH = "spec/capabilities/demo/spec.html"
CHANGE_PATH = "spec/changes/demo/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_capability-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-capability",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _payload(kind, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "title": "Demo",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_creating_a_capability_document_lands_it_at_current(app, auth_headers, tmp_path):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": CAP_PATH, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    assert created.json()["phase"] == "current"
    assert created.json()["kind"] == "capability"
    assert created.json()["explore_closed"] is False


@pytest.mark.asyncio
async def test_transition_refuses_any_to_phase_for_a_capability_document(
    app, auth_headers, tmp_path
):
    await app.post(
        f"{BASE}/documents",
        json={"path": CAP_PATH, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )

    for to_phase in ("exploring", "proposed", "approved", "archived", "current"):
        response = await app.post(
            f"{BASE}/documents/phase",
            params={"path": CAP_PATH, "to": to_phase},
            json={"reason": ""},
            headers=auth_headers,
        )
        assert response.status_code == 409, f"to={to_phase} should be refused"
        code = response.json()["detail"]["code"]
        expected = "unknown_phase" if to_phase == "current" else "illegal_transition"
        assert code == expected, f"to={to_phase} got {code}"


@pytest.mark.asyncio
async def test_an_agents_submission_against_a_capability_document_is_refused(
    app, auth_headers, run_headers, tmp_path
):
    await app.post(
        f"{BASE}/documents",
        json={"path": CAP_PATH, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )

    response = await app.post(
        AGENT,
        json={"path": CAP_PATH, "document": _payload("capability")},
        headers=run_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "capability_write_is_the_operators"


@pytest.mark.asyncio
async def test_save_document_accepts_an_operator_actor_against_a_capability_document(
    app, auth_headers, tmp_path
):
    from hub import project_workspace, spec_service

    created = await app.post(
        f"{BASE}/documents",
        json={"path": CAP_PATH, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    async with async_session_factory() as session:
        document = await spec_lifecycle.get_document(session, "proj-test", CAP_PATH)
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")
        result = await spec_service.save_document(
            session,
            workspace,
            document,
            _payload("capability"),
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        )
        await session.commit()
    assert result.phase == "current"


@pytest.mark.asyncio
async def test_a_payload_kind_mismatch_is_refused_for_a_capability_document(
    app, auth_headers, tmp_path
):
    from hub import project_workspace, spec_service

    await app.post(
        f"{BASE}/documents",
        json={"path": CAP_PATH, "title": "Demo capability", "kind": "capability"},
        headers=auth_headers,
    )

    async with async_session_factory() as session:
        document = await spec_lifecycle.get_document(session, "proj-test", CAP_PATH)
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")
        with pytest.raises(spec_service.SaveRefusedError) as excinfo:
            await spec_service.save_document(
                session,
                workspace,
                document,
                _payload("change-spec"),
                actor=spec_lifecycle.Actor(kind="operator", name="operator"),
            )
    assert excinfo.value.code == "kind_is_fixed"


@pytest.mark.asyncio
async def test_a_payload_kind_mismatch_is_refused_for_an_ordinary_document(
    app, auth_headers, run_headers, tmp_path
):
    """Design D3's fix is not capability-specific."""
    await app.post(
        f"{BASE}/documents", json={"path": CHANGE_PATH, "title": "Demo"}, headers=auth_headers
    )

    response = await app.post(
        AGENT,
        json={"path": CHANGE_PATH, "document": _payload("roadmap")},
        headers=run_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "kind_is_fixed"
