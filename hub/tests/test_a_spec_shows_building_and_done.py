"""A spec shows Building while its work is open, and Done when it is finished (F1089).

The shown phase is computed once, in `spec_lifecycle.display_phases`, and carried by every read the
views use: the document list, the spec index and the agent's `read_spec_document`. It is not a
lifecycle phase: `phase` stays what it was, and nothing is stored.
"""

import pytest
from sqlalchemy import update

from hub.db.engine import async_session_factory
from hub.db.models import Build, SpecDocument, Task

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/changes/shown-phase/spec.json"
_n = iter(range(1, 1000))


async def _approved(app, auth_headers) -> str:
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Shown"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    async with async_session_factory() as session:
        await session.execute(
            update(SpecDocument).where(SpecDocument.id == document_id).values(phase="approved")
        )
        await session.commit()
    return document_id


async def _build(document_id: str, state: str) -> None:
    n = next(_n)
    async with async_session_factory() as session:
        session.add(
            Build(
                id=f"build-shown-{n}",
                project_id="proj-test",
                document_id=document_id,
                state=state,
                driver="hand",
                level="fast",
                builders=[],
                reviewers=[],
                landing="main",
            )
        )
        await session.commit()


async def _task(document_id: str, status: str, key: str | None = None) -> str:
    n = next(_n)
    async with async_session_factory() as session:
        session.add(
            Task(
                id=f"task-shown-{n}",
                project_id="proj-test",
                title="t",
                status=status,
                spec_document_id=document_id,
                spec_task_key=key,
            )
        )
        await session.commit()
    return f"task-shown-{n}"


async def _set_task(task_id: str, status: str) -> None:
    async with async_session_factory() as session:
        await session.execute(update(Task).where(Task.id == task_id).values(status=status))
        await session.commit()


async def _end_build(document_id: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(Build).where(Build.document_id == document_id).values(state="finished")
        )
        await session.commit()


async def _listed(app, auth_headers) -> dict:
    response = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert response.status_code == 200, response.text
    (row,) = [d for d in response.json()["documents"] if d["path"] == PATH]
    return row


async def _indexed(app, auth_headers) -> dict:
    response = await app.get("/api/v1/projects/proj-test/project/specs", headers=auth_headers)
    assert response.status_code == 200, response.text
    return next(s for s in response.json()["specs"] if s["path"] == PATH)


@pytest.mark.asyncio
async def test_never_built_reads_approved(app, auth_headers):
    document_id = await _approved(app, auth_headers)
    await _task(document_id, "pending")  # open work alone, with no build, is not a build

    row = await _listed(app, auth_headers)
    assert row["phase"] == "approved"
    assert row["display_phase"] == "approved"


@pytest.mark.asyncio
async def test_a_running_build_reads_building(app, auth_headers):
    document_id = await _approved(app, auth_headers)
    await _build(document_id, "running")

    assert (await _listed(app, auth_headers))["display_phase"] == "building"


@pytest.mark.asyncio
async def test_building_until_every_task_is_decided_then_done(app, auth_headers):
    document_id = await _approved(app, auth_headers)
    await _build(document_id, "running")
    planned = await _task(document_id, "approved", key="planned")
    side_finding = await _task(document_id, "in_progress")  # a task outside the build's plan
    await _end_build(document_id)

    # The build has ended, but a task bound to the document is open.
    assert (await _listed(app, auth_headers))["display_phase"] == "building"
    assert (await _indexed(app, auth_headers))["display_phase"] == "building"

    await _set_task(side_finding, "rejected")
    done = await _listed(app, auth_headers)
    assert done["display_phase"] == "done"
    assert done["phase"] == "approved"  # the lifecycle phase is untouched
    assert (await _indexed(app, auth_headers))["display_phase"] == "done"

    # A task sent back re-opens the document.
    await _set_task(planned, "revision_needed")
    assert (await _listed(app, auth_headers))["display_phase"] == "building"


@pytest.mark.asyncio
async def test_other_phases_read_as_today(app, auth_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Shown"}, headers=auth_headers
    )
    document_id = created.json()["id"]
    await _build(document_id, "finished")
    assert (await _listed(app, auth_headers))["display_phase"] == "exploring"

    async with async_session_factory() as session:
        await session.execute(
            update(SpecDocument).where(SpecDocument.id == document_id).values(phase="archived")
        )
        await session.commit()
    assert (await _listed(app, auth_headers))["display_phase"] == "archived"
