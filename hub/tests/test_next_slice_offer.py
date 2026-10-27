"""The next slice is offered, not queued (`amendments-main-watch-and-the-next-slice`, task
`next-slice-offer`, D6).

Red first: on master a slice approved with `draft_next_slice` queued its drafting turn the moment
its last task closed (05:44 on 2026-10-27, while the operator slept), and nothing was offered. The
acceptance drive's `offer` is the first case; here `-k claimed`, `-k take`, `-k request`, and the
behaviours the old queueing tests pinned, carried over to the take: each task's outcome (F501),
the slice author's conversation or a new one (F1047), once per offer, never failing a transition.
"""

import pytest
from sqlalchemy import select

from hub import slice_drafting, spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, SpecDocument, Task

from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    BASE,
    CONVERSATION,
    _agent_create,
    _agent_submit,
    _approve,
    _approved_roadmap_doc,
    _move,
    _propose,
    _proposed_slice,
    _queued,
    _settle,
    _slice_doc,
    planner,
    scheduled,
)

OFFERS = f"{BASE}/next-slice-offers"
TAKE = f"{BASE}/documents/next-slice/take"
DECLINE = f"{BASE}/documents/next-slice/decline"
DONE = ("in_progress", "completed", "under_review", "approved")


async def _agents(*names):
    async with async_session_factory() as session:
        for name in names:
            session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name))
        await session.commit()


async def _built_slice(app, auth_headers, planner, key="s1"):  # noqa: F811
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path, key=key)
    approved = await _approve(app, auth_headers, slice_path)
    assert approved.status_code == 200, approved.text
    (task_id,) = approved.json()["tasks_created"]
    return roadmap_path, slice_path, task_id


async def _offers(app, auth_headers):
    response = await app.get(OFFERS, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["offers"]


@pytest.mark.asyncio
async def test_no_offer_when_the_next_slice_is_claimed(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    # Another document already names the next slice in its roadmap link.
    claiming = await _agent_create(app, planner, title="Slice two")
    saved = await _agent_submit(
        app,
        planner,
        claiming,
        _slice_doc(title="Slice two", roadmap={"document": roadmap_path, "slice": "s2"}),
    )
    assert saved.status_code == 200, saved.text

    await _move(app, auth_headers, task_id, *DONE)
    await _settle()

    assert await _offers(app, auth_headers) == []
    assert await _queued() == []


@pytest.mark.asyncio
async def test_take_queues_once_in_a_new_conversation_with_the_outcomes(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """F1047 and F501: the slice's conversation was archived, so the turn opens its own, named for
    the next slice; it says how each task ended; a second take queues nothing."""
    await _agents("planner", "architect")
    _, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, "rejected")
    await _settle()
    async with async_session_factory() as session:
        (
            await session.execute(select(Conversation).where(Conversation.id == CONVERSATION))
        ).scalar_one().lifecycle = "archived"
        await session.commit()
    (offer,) = await _offers(app, auth_headers)
    assert offer["agent"] == "planner", "the author is preselected"

    taken = await app.post(
        TAKE, params={"path": slice_path}, json={"agent": "architect"}, headers=auth_headers
    )
    again = await app.post(
        TAKE, params={"path": slice_path}, json={"agent": "architect"}, headers=auth_headers
    )

    assert taken.status_code == 200, taken.text
    assert again.status_code == 409, again.text
    (entry,) = await _queued("architect")
    assert await _queued("planner") == []
    assert entry.origin_type == "operator" and entry.spec_document == offer["roadmap"]
    assert f"`{task_id}`" in entry.content and ": rejected" in entry.content
    assert "no merge into the main branch is recorded" in entry.content
    assert "s2" in entry.content and "Slice two" in entry.content
    async with async_session_factory() as session:
        fresh = (
            await session.execute(
                select(Conversation).where(Conversation.id == entry.conversation_id)
            )
        ).scalar_one()
    assert (fresh.agent, fresh.lifecycle) == ("architect", "open")
    assert "Slice two" in (fresh.title or "")
    assert scheduled == [("proj-test", "architect")]
    assert await _offers(app, auth_headers) == []


@pytest.mark.asyncio
async def test_take_goes_to_the_author_in_its_open_conversation(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    await _agents("planner")
    _, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await _settle()

    taken = await app.post(TAKE, params={"path": slice_path}, headers=auth_headers)

    assert taken.status_code == 200, taken.text
    (entry,) = await _queued("planner")
    assert entry.conversation_id == CONVERSATION


@pytest.mark.asyncio
async def test_declining_hides_the_offer(app, auth_headers, planner, scheduled):  # noqa: F811
    _, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await _settle()

    declined = await app.post(DECLINE, params={"path": slice_path}, headers=auth_headers)

    assert declined.status_code == 200, declined.text
    assert await _offers(app, auth_headers) == []
    assert await _queued() == []


@pytest.mark.asyncio
async def test_the_last_slice_offers_nothing(app, auth_headers, planner, scheduled):  # noqa: F811
    _, _, task_id = await _built_slice(app, auth_headers, planner, key="s2")
    await _move(app, auth_headers, task_id, *DONE)
    await _settle()
    assert await _offers(app, auth_headers) == []


@pytest.mark.asyncio
async def test_an_open_task_holds_the_offer(app, auth_headers, planner, scheduled):  # noqa: F811
    await _built_slice(app, auth_headers, planner)
    assert await _offers(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_failing_offer_never_fails_the_task_transition(
    app, auth_headers, planner, scheduled, monkeypatch  # noqa: F811
):
    _, _, task_id = await _built_slice(app, auth_headers, planner)

    async def broken(*args, **kwargs):
        raise RuntimeError("the offer could not be read")

    monkeypatch.setattr(slice_drafting, "offer_for", broken)
    await _move(app, auth_headers, task_id, *DONE)
    async with async_session_factory() as session:
        assert (await session.get(Task, task_id)).status == "approved"


@pytest.mark.asyncio
async def test_approval_refuses_the_request_and_an_old_request_is_an_offer(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """`-k request`: approval with draft_next_slice is refused naming the offer; a request recorded
    before this change, never answered, on a built slice is listed as an offer (the one on :8000
    since 2026-10-25)."""
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    refused = await _approve(app, auth_headers, slice_path, draft_next_slice=True)
    assert refused.status_code == 400, refused.text
    assert "offer" in refused.json()["detail"]["message"]
    refused_too = await app.post(
        f"{BASE}/documents/approve-and-build",
        params={"path": slice_path},
        json={"draft_next_slice": True},
        headers=auth_headers,
    )
    assert refused_too.status_code == 400, refused_too.text

    approved = await _approve(app, auth_headers, slice_path)
    (task_id,) = approved.json()["tasks_created"]
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == slice_path))
        ).scalar_one()
        # As master's approval recorded it.
        await spec_lifecycle.record_event(
            session,
            document,
            kind=slice_drafting.REQUESTED,
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
            detail={
                "roadmap": roadmap_path,
                "roadmap_title": "The plan",
                "approved_slice": {"key": "s1", "title": "Slice one"},
                "next_slice": {"key": "s2", "title": "Slice two"},
                "agent": "planner",
                "conversation_id": CONVERSATION,
            },
        )
        task = await session.get(Task, task_id)
        task.status = "rejected"
        await session.commit()

    (offer,) = await _offers(app, auth_headers)
    assert offer["document"] == slice_path and offer["requested"] is True
    assert await _queued() == []


@pytest.mark.asyncio
async def test_an_operator_created_slice_offers_its_writer(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    """159 of 180 documents on :8000 were created by the operator and written by an agent: the
    writer is the author the take defaults to."""
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = "spec/changes/operator-slice/spec.json"
    created = await app.post(
        f"{BASE}/documents", json={"path": slice_path, "title": "Slice one"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await _agent_submit(
        app, planner, slice_path, _slice_doc(roadmap={"document": roadmap_path, "slice": "s1"})
    )
    assert saved.status_code == 200, saved.text
    assert (await _propose(app, auth_headers, slice_path))["blocking"] == []
    approved = await _approve(app, auth_headers, slice_path)
    (task_id,) = approved.json()["tasks_created"]
    await _move(app, auth_headers, task_id, "rejected")
    await _settle()

    (offer,) = await _offers(app, auth_headers)
    assert offer["agent"] == "planner"
