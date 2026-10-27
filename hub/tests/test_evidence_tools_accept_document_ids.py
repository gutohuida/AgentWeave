"""`list_evidence` and `record_evidence` take a document's `spdoc-…` id as `read_spec_document` does."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions"
PATH = "spec/changes/evidence-by-id/spec.json"


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-eid", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-eid",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_eid-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_eid-secret"}


@pytest.mark.asyncio
async def test_evidence_tools_resolve_a_document_id_like_its_path(app, auth_headers, author):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Evidence by id"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Evidence by id",
        "requirements": [{"key": "alpha", "statement": "It lists things", "modal": "MUST"}],
        "acceptance_criteria": [
            {
                "key": "c1",
                "requirement": "alpha",
                "given": "g",
                "when": "w",
                "then": "t",
                "checked_by": "agent",
                "how_to_check": "pytest",
            }
        ],
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "delivery": {"mode": "none"},
    }
    saved = await app.post(
        f"{AGENT}/spec/documents", json={"path": PATH, "document": document}, headers=author
    )
    assert saved.status_code == 200, saved.text
    async with async_session_factory() as session:
        doc_id = (
            await session.execute(select(SpecDocument.id).where(SpecDocument.path == PATH))
        ).scalar_one()

    first = await app.post(
        f"{AGENT}/spec/evidence",
        json={"identifier": "FR-1", "document": doc_id, "summary": "by id"},
        headers=author,
    )
    assert first.status_code == 201, first.text

    by_id = await app.get(f"{AGENT}/spec/evidence", params={"document": doc_id}, headers=author)
    by_path = await app.get(f"{AGENT}/spec/evidence", params={"document": PATH}, headers=author)
    with_fr = await app.get(
        f"{AGENT}/spec/evidence", params={"document": doc_id, "identifier": "FR-1"}, headers=author
    )
    assert by_id.status_code == by_path.status_code == with_fr.status_code == 200
    assert len(by_id.json()["evidence"]) == 1
    assert by_id.json() == by_path.json() == with_fr.json()
