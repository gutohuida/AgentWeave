"""Draft creates the slice's document (`every-spec-entry-point-leads-into-the-journey`, task
`draft-creates-document`, D1 and D2).

Red first: before this, taking a slice's offer created no document and queued the drafting turn
bound to the roadmap, which has no journey step, with a message telling the agent to call
`create_spec_document` and write the whole slice in one go. The take now creates the slice's change
document at intake, linked to the slice, makes it the drafting conversation's document and binds
the turn to it; a second take still creates nothing.
"""

import pytest
from sqlalchemy import select

from hub import project_workspace, slice_drafting, slice_progress, spec_lifecycle, spec_reading
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument

from .test_next_slice_offer import DONE, TAKE, _agents, _built_slice, land
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    _move,
    _queued,
    _settle,
    planner,
    scheduled,
)


async def _offered_s2(app, auth_headers, planner):  # noqa: F811
    """A roadmap whose slice s1 is built, so s2 is offered for drafting."""
    await _agents("planner")
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await land(task_id)
    await _settle()
    return roadmap_path, slice_path


async def _take(app, auth_headers, slice_path):
    return await app.post(TAKE, params={"path": slice_path}, headers=auth_headers)


async def _documents_naming(roadmap_path, key):
    async with async_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(SpecDocument).where(
                        SpecDocument.project_id == "proj-test",
                        SpecDocument.kind == "change-spec",
                    )
                )
            )
            .scalars()
            .all()
        )
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")
        payloads = await spec_reading.payloads_for_documents(
            session, workspace, [r.id for r in rows]
        )
    return [
        row
        for row in rows
        if (payloads.get(row.id) or {}).get("roadmap") == {"document": roadmap_path, "slice": key}
    ]


@pytest.mark.asyncio
async def test_take_creates_document_before_turn(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """take-creates-document-before-turn: no agent turn has run (the scheduler is stubbed), and
    the change document exists in exploring at intake, titled and linked to the slice."""
    roadmap_path, slice_path = await _offered_s2(app, auth_headers, planner)

    taken = await _take(app, auth_headers, slice_path)

    assert taken.status_code == 200, taken.text
    path = taken.json()["document"]
    assert path and path != roadmap_path
    (document,) = await _documents_naming(roadmap_path, "s2")
    assert document.path == path
    assert (document.kind, document.phase, document.step) == (
        "change-spec",
        spec_lifecycle.EXPLORING,
        "intake",
    )
    assert document.title == "Slice two"
    # The drafting conversation's document is the new one (D3).
    (entry,) = await _queued("planner")
    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, entry.conversation_id)
    assert conversation.spec_document_id == document.id


@pytest.mark.asyncio
async def test_draft_entry_bound_to_new_document(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """draft-entry-bound-to-new-document."""
    roadmap_path, slice_path = await _offered_s2(app, auth_headers, planner)

    taken = await _take(app, auth_headers, slice_path)

    assert taken.status_code == 200, taken.text
    (entry,) = await _queued("planner")
    assert entry.spec_document == taken.json()["document"] != roadmap_path
    assert "create_spec_document" not in entry.content
    assert "dozen requirements" not in entry.content
    assert taken.json()["document"] in entry.content
    assert "step by step" in entry.content


@pytest.mark.asyncio
async def test_take_marks_slice_drafting_at_once(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """take-marks-slice-drafting-at-once: read right after the take, before any turn."""
    roadmap_path, slice_path = await _offered_s2(app, auth_headers, planner)

    taken = await _take(app, auth_headers, slice_path)

    assert taken.status_code == 200, taken.text
    async with async_session_factory() as session:
        roadmap = await spec_lifecycle.get_document(session, "proj-test", roadmap_path)
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")
        view = await slice_progress.roadmap_view(session, workspace, roadmap)
    (s2,) = [row for row in view["slices"] if row["key"] == "s2"]
    assert s2["state"] == slice_progress.DRAFTING
    assert s2["document"] == taken.json()["document"]
    assert s2["offers_drafting"] is False


@pytest.mark.asyncio
async def test_second_take_refused(app, auth_headers, planner, scheduled):  # noqa: F811
    """second-take-refused (guard): 409 no_offer, and still one document names the slice."""
    roadmap_path, slice_path = await _offered_s2(app, auth_headers, planner)

    first = await _take(app, auth_headers, slice_path)
    again = await _take(app, auth_headers, slice_path)

    assert first.status_code == 200, first.text
    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "no_offer"
    assert len(await _documents_naming(roadmap_path, "s2")) == 1
    assert len(await _queued("planner")) == 1


@pytest.mark.asyncio
async def test_a_refused_take_creates_no_document(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """D1: the document is created inside the take, so a take refused for its agent leaves none."""
    roadmap_path, slice_path = await _offered_s2(app, auth_headers, planner)

    refused = await app.post(
        TAKE, params={"path": slice_path}, json={"agent": "nobody"}, headers=auth_headers
    )

    assert refused.status_code == 422, refused.text
    assert await _documents_naming(roadmap_path, "s2") == []


def test_draft_message_keeps_prior_outcomes():
    """draft-message-keeps-prior-outcomes (guard, F501): the roadmap, the slice's intent and done
    sentence, each prior task's merge outcome and rejected evidence, and where the retrospective
    is, alongside the new document's path."""

    class _Task:
        id = "task-1"
        display_id = "SL-1"
        title = "Build slice one"
        status = "approved"

    detail = {
        "roadmap": "spec/changes/the-plan/spec.json",
        "roadmap_title": "The plan",
        "next_slice": {
            "key": "s2",
            "title": "Slice two",
            "intent": "Second outcome",
            "done": "S2 is built",
        },
        "built_slices": [
            {
                "key": "s1",
                "title": "Slice one",
                "document": "spec/changes/slice-one/spec.json",
                "tasks_on_main": 1,
                "tasks_total": 1,
                "retrospective": {
                    "document": "spec/changes/slice-one/spec.json",
                    "at": "2026-11-19T10:00:00+00:00",
                },
            }
        ],
    }
    message = slice_drafting.next_slice_message(
        detail,
        tasks=[_Task()],
        outcomes={
            "task-1": ["merged into master", "FR-2 evidence rejected: the baseline lines differ"]
        },
        document="spec/changes/olive-salamander/spec.json",
    )

    assert "`spec/changes/the-plan/spec.json`" in message and "'The plan'" in message
    assert "- Intent: Second outcome" in message
    assert "- Done when: S2 is built" in message
    assert "`SL-1` Build slice one: approved" in message
    assert "  - merged into master" in message
    assert "  - FR-2 evidence rejected: the baseline lines differ" in message
    assert "Retrospective: written 2026-11-19T10:00:00+00:00" in message
    assert "read it on `spec/changes/slice-one/spec.json`" in message
    assert "`spec/changes/olive-salamander/spec.json`" in message
    assert "create_spec_document" not in message
