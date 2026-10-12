"""F551 part 3: requirement identifiers sort as numbers, so `FR-2` comes before `FR-10`.

The three reads below ordered rows in SQL by the identifier text, so a document with ten
requirements listed `FR-1, FR-10, FR-2, ...` in the coverage report, in the `unserved` list beside
it, and in the requirements a task serves. The data was right and the order read as a defect.
"""

import pytest

from hub import requirement_links
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from tests.test_requirement_coverage import PATH, TASKS, _coverage, _document, _numbered

NATURAL = [f"FR-{n}" for n in range(1, 11)]


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-order-builder", project_id="proj-test", name="order-builder"))
        session.add(
            Run(
                id="run-order",
                project_id="proj-test",
                agent="order-builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_order-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_order-secret"}


@pytest.mark.asyncio
async def test_the_coverage_report_lists_ten_requirements_in_numeric_order(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder, requirements=_numbered(10))

    report = await _coverage(app, auth_headers)

    assert [row["identifier"] for row in report["requirements"]] == NATURAL
    # Nothing is linked, so the same ten are the unserved list the route builds beside it.
    assert [row["identifier"] for row in report["unserved"]] == NATURAL


@pytest.mark.asyncio
async def test_the_requirements_a_task_serves_come_back_in_numeric_order(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder, requirements=_numbered(10))
    created = await app.post(
        TASKS,
        json={"title": "Build them", "requirement_ids": ["FR-10", "FR-2", "FR-1"]},
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text

    async with async_session_factory() as session:
        rows = await requirement_links.for_task(session, created.json()["id"])

    assert [row.identifier for row in rows] == ["FR-1", "FR-2", "FR-10"]


@pytest.mark.asyncio
async def test_a_coverage_document_scope_keeps_the_numeric_order(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder, requirements=_numbered(12))

    report = await _coverage(app, auth_headers, document=PATH)

    assert [row["identifier"] for row in report["requirements"]][-3:] == ["FR-10", "FR-11", "FR-12"]
