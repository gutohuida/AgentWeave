"""`requirement_ids` is accepted on write and was reported nowhere.

Loop 7 read a task's `requirement_ids` while diagnosing why an approval would not merge, got
`None`, and concluded the links were missing — they were not. The links existed, and were exposed
under a different name. A field a caller can write and never read back cannot be used to confirm
what was recorded, and reads as absent data rather than as an absent field.

The identifiers reported must be the ones accepted (`FR-1`), not the system's row identity, or what
is read back cannot be submitted again — which would be worse than the field staying absent.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/requirement-ids/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It settles the account", "modal": "MUST"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rid", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rid",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rid-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rid-secret"}


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Identifiers"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Identifiers",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


@pytest.mark.asyncio
async def test_the_task_response_returns_the_identifiers_it_accepts(app, auth_headers, builder):
    await make_document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1", "FR-2"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    assert sorted(created.json()["requirement_ids"]) == ["FR-1", "FR-2"]


@pytest.mark.asyncio
async def test_requirement_ids_round_trip_through_create_and_get(app, auth_headers, builder):
    """What is read back must be submittable again, which is the whole point of the field."""
    await make_document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    task_id = created.json()["id"]

    fetched = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    read_back = fetched.json()["requirement_ids"]
    assert read_back == ["FR-1"]

    resubmitted = await app.post(
        TASKS, json={"title": "Build it again", "requirement_ids": read_back}, headers=auth_headers
    )
    assert resubmitted.status_code == 201, resubmitted.text
    assert resubmitted.json()["requirement_ids"] == ["FR-1"]


@pytest.mark.asyncio
async def test_requirement_ids_are_identifiers_not_row_ids(app, auth_headers, builder):
    """`spreq-…` would not round-trip, and would be worse than the field being absent."""
    await make_document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    body = created.json()
    assert body["requirement_ids"] == ["FR-1"]
    assert not any(value.startswith("spreq-") for value in body["requirement_ids"])
    # The row identity is still available, on the link — the two are not being conflated.
    assert body["requirement_links"][0]["requirement_id"].startswith("spreq-")


@pytest.mark.asyncio
async def test_a_task_serving_nothing_reports_an_empty_list(app, auth_headers, builder):
    """Absent links are an empty list, not a null — the shape does not change with the data."""
    await make_document(app, auth_headers, builder)
    created = await app.post(TASKS, json={"title": "Unlinked"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    assert created.json()["requirement_ids"] == []


@pytest.mark.asyncio
async def test_the_list_route_carries_them_too(app, auth_headers, builder):
    """All four response paths run through `_attach_requirements`; the board reads this one."""
    await make_document(app, auth_headers, builder)
    await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["requirement_ids"] == ["FR-1"]


@pytest.mark.asyncio
async def test_the_agent_plane_task_response_carries_requirement_ids(app, auth_headers, builder):
    """The plane an agent diagnoses a stuck merge from is the one that most needed this."""
    await make_document(app, auth_headers, builder)
    created = await app.post(
        "/api/v1/agent-actions/tasks",
        json={"title": "Build it", "requirement_ids": ["FR-1", "FR-2"]},
        headers=builder,
    )
    assert created.status_code == 201, created.text
    assert sorted(created.json()["requirement_ids"]) == ["FR-1", "FR-2"]
