"""A document moves forward only through its checks (F207, F113).

The completeness checks used to run only inside `propose`; the phase route reached `proposed` and
`approved` without them, and approval is where a payload becomes tasks. They now run inside
`spec_lifecycle.transition()`, so no caller can move a document forward unchecked.
"""

import pytest
from sqlalchemy import select

from hub import project_workspace, spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, Task

from .test_spec_documents_api import (
    BASE,
    PATH,
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

OPERATOR = spec_lifecycle.Actor(kind="operator", name="operator")


async def _close(app, auth_headers):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    assert closed.status_code == 200, closed.text


async def _phase(app, auth_headers, to):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": to},
        json={"reason": ""},
        headers=auth_headers,
    )


async def _tasks_of_document():
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        return (
            (await session.execute(select(Task).where(Task.spec_document_id == document.id)))
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_1_1_the_phase_route_will_not_propose_an_empty_document(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    await _close(app, auth_headers)

    response = await _phase(app, auth_headers, "proposed")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "document_incomplete"
    assert detail["blocking"]
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert row.phase == "exploring"


@pytest.mark.asyncio
async def test_1_2_an_edit_after_proposing_is_checked_again_at_approval(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await _close(app, auth_headers)
    proposed = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    assert proposed.json()["blocking"] == []

    edited = await _submit(app, run_headers, _document(tasks=[]))
    assert edited.status_code == 200, edited.text

    response = await _phase(app, auth_headers, "approved")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "document_incomplete"
    assert "requirement_without_task" in {b["code"] for b in detail["blocking"]}
    assert await _tasks_of_document() == []


@pytest.mark.asyncio
async def test_1_3_propose_lists_every_blocker_and_no_longer_an_open_exploration(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document(tasks=[], scope={"in_scope": [], "non_goals": []}))

    response = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "exploring"
    codes = [b["code"] for b in body["blocking"]]
    # The operator's "exploration is complete" step is retired (step-journey FR-11).
    assert "explore_not_closed" not in codes
    assert {"non_goals_empty", "requirement_without_task"} <= set(codes)


@pytest.mark.asyncio
async def test_1_6_a_complete_document_still_goes_propose_then_approve(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await _close(app, auth_headers)
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)

    response = await _phase(app, auth_headers, "approved")

    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "approved"
    assert len(response.json()["tasks_created"]) == 1


@pytest.mark.asyncio
async def test_1_7_a_payload_corrupted_on_disk_is_a_422_not_a_500(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await _close(app, auth_headers)
    await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)

    target = tmp_path / PATH
    text = target.read_text(encoding="utf-8")
    assert '"schema_version"' in text
    target.write_text(text.replace('"schema_version"', '"schema_versionX"'), encoding="utf-8")

    response = await _phase(app, auth_headers, "approved")

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "payload_invalid"
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert row.phase == "proposed"


@pytest.mark.asyncio
async def test_1_9_transition_itself_runs_the_checks_for_any_caller(app, auth_headers, tmp_path):
    """Pins the check to the function that moves the phase, not to a route."""
    await _create(app, auth_headers)
    await _close(app, auth_headers)

    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")

        with pytest.raises(spec_lifecycle.PhaseError) as excinfo:
            await spec_lifecycle.transition(
                session,
                document,
                to_phase=spec_lifecycle.PROPOSED,
                actor=OPERATOR,
                workspace=workspace,
            )
        assert excinfo.value.code == "document_incomplete"
        assert excinfo.value.blocking
        assert document.phase == "exploring"

        # The same for approval, on a proposed document whose payload is the stub.
        document.phase = spec_lifecycle.PROPOSED
        with pytest.raises(spec_lifecycle.PhaseError) as excinfo:
            await spec_lifecycle.transition(
                session,
                document,
                to_phase=spec_lifecycle.APPROVED,
                actor=OPERATOR,
                workspace=workspace,
            )
        assert excinfo.value.code == "document_incomplete"
        assert document.phase == spec_lifecycle.PROPOSED
