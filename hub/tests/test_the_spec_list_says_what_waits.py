"""The spec list route names each document's roadmap and slice, and what it waits on (SHR-2).

FR-9 / FR-12 of `the-spec-header-redesigned`: the list cannot group a slice under its roadmap, or
say what waits on the operator, unless the route returns both for every document it lists.
"""

import pytest
from sqlalchemy import update

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, SpecDocument, SpecDocumentEvent
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
ROADMAP = "spec/changes/the-roadmap/spec.json"


@pytest.fixture
async def run_headers():
    token = "aw_run_spec-waits-run-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-spec-waits",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _change(title, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": title,
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
        "delivery": {"mode": "none"},
    }
    payload.update(overrides)
    return payload


async def _make(app, auth_headers, run_headers, path, document, phase=None):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "T"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text
    if phase:
        async with async_session_factory() as session:
            await session.execute(
                update(SpecDocument)
                .where(SpecDocument.id == created.json()["id"])
                .values(phase=phase)
            )
            await session.commit()
    return created.json()["id"]


@pytest.mark.asyncio
async def test_the_list_route_says_each_documents_roadmap_and_what_waits(
    app, auth_headers, run_headers, tmp_path
):
    named = {"document": ROADMAP, "slice": "second"}
    await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/named/spec.json",
        _change("Named", roadmap=named),
    )
    await _make(app, auth_headers, run_headers, "spec/changes/clean/spec.json", _change("Clean"))
    await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/gap/spec.json",
        _change("Gap", roadmap={"document": "spec/changes/nowhere/spec.json", "slice": "x"}),
    )
    amended_id = await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/amended/spec.json",
        _change("Amended"),
        phase="approved",
    )
    await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/unbuilt/spec.json",
        _change("Unbuilt"),
        phase="approved",
    )
    done_id = await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/finished/spec.json",
        _change("Finished"),
        phase="approved",
    )
    async with async_session_factory() as session:
        session.add(
            Build(
                id="build-waits-1",
                project_id="proj-test",
                document_id=done_id,
                state="ended",
                driver="hand",
                level="fast",
                builders=[],
                reviewers=[],
                landing="main",
            )
        )
        session.add(
            SpecDocumentEvent(
                id="spev-waits-1",
                document_id=amended_id,
                project_id="proj-test",
                kind="amendment",
                actor_kind="agent",
                actor="qa",
                origin="submission",
                detail={"id": "am-1"},
            )
        )
        await session.commit()

    response = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert response.status_code == 200, response.text
    by_path = {d["path"]: d for d in response.json()["documents"]}

    assert by_path["spec/changes/named/spec.json"]["roadmap"] == {**named, "order": None}
    assert by_path["spec/changes/clean/spec.json"]["roadmap"] is None
    assert "ready_to_approve" in by_path["spec/changes/clean/spec.json"]["waiting"]
    assert by_path["spec/changes/gap/spec.json"]["waiting"] == []
    assert by_path["spec/changes/amended/spec.json"]["waiting"] == [
        "amendments_to_review",
        "ready_to_build",
    ]
    assert by_path["spec/changes/unbuilt/spec.json"]["waiting"] == ["ready_to_build"]
    assert by_path["spec/changes/finished/spec.json"]["waiting"] == ["ready_to_fold"]
