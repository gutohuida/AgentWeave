"""F452: what `read_spec_document` returns can be submitted back without losing anything.

The read nests each requirement's acceptance criteria under it and adds the Hub's own `identifier`,
`state` and `anchor`; the submit took criteria only as a flat top-level list and kept unknown nested
fields as extras. So an agent that read its document and resubmitted it (sweep 2026-09-25, row 9)
silently deleted every criterion, and `propose` then blocked on `requirement_without_criterion` as if
none had ever been written. The Hub now lifts nested criteria into the flat list, drops its own read
fields and the retired requirements the read lists, and refuses a truncated read rather than saving
what it cut.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_documents import parse_stored
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
DOCS = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/roundtrip-demo/spec.json"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a watering", "modal": "SHOULD"}
CRITERIA = [
    {
        "key": "alpha-lists",
        "requirement": "alpha",
        "given": "g",
        "when": "w",
        "then": "both appear",
    },
    {"key": "beta-records", "requirement": "beta", "given": "g", "when": "w", "then": "done"},
]


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rt", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rt",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rt-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rt-secret"}


def _document(requirements, criteria=None):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Roundtrip demo",
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": requirements,
        "tasks": [{"key": "t", "description": "d", "requirements": ["alpha", "beta"]}],
        "delivery": {"mode": "none"},
    }
    if criteria is not None:
        document["acceptance_criteria"] = criteria
    return document


async def _make(app, auth_headers, builder, requirements=(ALPHA, BETA), criteria=CRITERIA):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Roundtrip demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        DOCS,
        json={"path": PATH, "document": _document(list(requirements), list(criteria))},
        headers=builder,
    )
    assert saved.status_code == 200, saved.text


async def _read(app, builder):
    read = await app.get(DOCS, params={"path": PATH, "include": "full"}, headers=builder)
    assert read.status_code == 200, read.text
    return read.json()


def _stored(workspace):
    return parse_stored((workspace / PATH).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_resubmitting_the_read_view_keeps_every_criterion(
    app, auth_headers, builder, tmp_path
):
    await _make(app, auth_headers, builder)
    view = await _read(app, builder)

    # Exactly what submit_spec_document sends when an agent passes the read's requirements back:
    # nested criteria, the Hub's identifier/state/anchor, no top-level acceptance_criteria.
    saved = await app.post(
        DOCS, json={"path": PATH, "document": _document(view["requirements"])}, headers=builder
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["blocking"] == []

    stored = _stored(tmp_path)
    assert sorted(c["key"] for c in stored["acceptance_criteria"]) == [
        "alpha-lists",
        "beta-records",
    ]
    for requirement in stored["requirements"]:
        for hub_field in ("identifier", "state", "anchor", "acceptance_criteria"):
            assert hub_field not in requirement, (requirement["key"], hub_field)
    again = await _read(app, builder)
    assert [r["identifier"] for r in again["requirements"]] == ["FR-1", "FR-2"]


@pytest.mark.asyncio
async def test_a_retired_requirement_in_the_read_is_not_resurrected(
    app, auth_headers, builder, tmp_path
):
    await _make(app, auth_headers, builder)
    # Retire beta: the next read lists it with state 'retired' and no statement.
    saved = await app.post(
        DOCS,
        json={
            "path": PATH,
            "document": _document([ALPHA], [CRITERIA[0]])
            | {"tasks": [{"key": "t", "description": "d", "requirements": ["alpha"]}]},
        },
        headers=builder,
    )
    assert saved.status_code == 200, saved.text
    view = await _read(app, builder)
    assert [r["state"] for r in view["requirements"]] == ["active", "retired"]

    document = _document(view["requirements"]) | {
        "tasks": [{"key": "t", "description": "d", "requirements": ["alpha"]}]
    }
    resaved = await app.post(DOCS, json={"path": PATH, "document": document}, headers=builder)
    assert resaved.status_code == 200, resaved.text
    stored = _stored(tmp_path)
    assert [r["key"] for r in stored["requirements"]] == ["alpha"]
    assert [c["key"] for c in stored["acceptance_criteria"]] == ["alpha-lists"]


@pytest.mark.asyncio
async def test_a_nested_criterion_that_contradicts_a_flat_one_is_refused(
    app, auth_headers, builder, tmp_path
):
    await _make(app, auth_headers, builder)
    view = await _read(app, builder)
    flat = [dict(CRITERIA[0], then="something else"), CRITERIA[1]]
    refused = await app.post(
        DOCS,
        json={"path": PATH, "document": _document(view["requirements"], flat)},
        headers=builder,
    )
    assert refused.status_code == 422, refused.text
    assert "alpha-lists" in refused.text
    # Nothing was written.
    assert _stored(tmp_path)["acceptance_criteria"][0]["then"] == "both appear"


@pytest.mark.asyncio
async def test_a_truncated_read_is_refused_rather_than_saved(app, auth_headers, builder, tmp_path):
    await _make(app, auth_headers, builder)
    view = await _read(app, builder)
    view["requirements"][0]["section_truncated"] = True
    view["requirements"][0]["acceptance_criteria"] = []
    refused = await app.post(
        DOCS, json={"path": PATH, "document": _document(view["requirements"])}, headers=builder
    )
    assert refused.status_code == 422, refused.text
    assert "truncated" in refused.text
    assert len(_stored(tmp_path)["acceptance_criteria"]) == 2
