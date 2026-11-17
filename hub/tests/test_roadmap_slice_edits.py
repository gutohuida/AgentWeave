"""An approved roadmap's slices are reordered, removed and added after approval
(`a-roadmap-that-is-recognisably-a-roadmap`, RTRR-3: FR-7, FR-8, FR-9).

The operator moves and removes (their own acts, applied at once, recorded as document events); only
an agent adds, in a conversation the operator opened with it. Each refusal and each history row has
a test here.
"""

# ruff: noqa: F811

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent, SpecDocument, SpecDocumentEvent

from .test_next_slice_offer import _agents, _move, land  # noqa: F401 -- fixtures
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    AGENT_DOCS,
    BASE,
    _agent_create,
    _agent_submit,
    _approve,
    _propose,
    _proposed_slice,
    _queued,
    _roadmap,
    _run,
    planner,
    scheduled,
)

MOVE = f"{BASE}/documents/slices/move"
REMOVE = f"{BASE}/documents/slices/remove"
CONVERSATION = f"{BASE}/documents/slices/conversation"
AMEND = "/api/v1/agent-actions/spec/documents/amend"


def _five():
    def one(key, after=()):
        return {
            "key": key,
            "title": f"Slice {key}",
            "intent": f"{key} outcome",
            "done": f"{key} is built",
            "builds_after": list(after),
        }

    return [one("s1"), one("s2", ["s1"]), one("s3"), one("s4", ["s3"]), one("s5")]


async def _roadmap_of_five(app, auth_headers, planner):
    path = await _agent_create(app, planner, kind="roadmap", title="The plan")
    saved = await _agent_submit(app, planner, path, _roadmap(slices=_five()))
    assert saved.status_code == 200, saved.text
    assert (await _propose(app, auth_headers, path))["blocking"] == []
    approved = await _approve(app, auth_headers, path)
    assert approved.status_code == 200, approved.text
    return path


async def _slices(app, auth_headers, path):
    response = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _order(app, auth_headers, path):
    return [s["key"] for s in (await _slices(app, auth_headers, path))["slices"]]


async def _phase(path):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument.phase).where(SpecDocument.path == path))
        ).scalar_one()


async def _events(path, kind):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        rows = await session.execute(
            select(SpecDocumentEvent).where(
                SpecDocumentEvent.document_id == document.id, SpecDocumentEvent.kind == kind
            )
        )
        return list(rows.scalars().all())


@pytest.mark.asyncio
async def test_the_operator_moves_a_not_drafted_slice_at_once(app, auth_headers, planner):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(
        MOVE, json={"path": path, "slice": "s5", "position": 3}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = await _slices(app, auth_headers, path)
    assert [s["key"] for s in body["slices"]] == ["s1", "s2", "s5", "s3", "s4"]
    assert await _phase(path) == "approved", "no re-approval"
    (event,) = await _events(path, "slice_moved")
    assert (event.actor_kind, event.actor) == ("operator", "operator")
    assert event.detail == {"slice": "s5", "from": 5, "to": 3}


@pytest.mark.asyncio
async def test_moving_to_the_slices_own_place_records_nothing(app, auth_headers, planner):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(
        MOVE, json={"path": path, "slice": "s5", "position": 5}, headers=auth_headers
    )

    assert response.status_code == 200 and response.json()["moved"] is False
    assert await _events(path, "slice_moved") == []


@pytest.mark.asyncio
async def test_a_position_outside_the_roadmap_is_refused(app, auth_headers, planner):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(
        MOVE, json={"path": path, "slice": "s5", "position": 6}, headers=auth_headers
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "position_out_of_range"
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4", "s5"]


@pytest.mark.asyncio
async def test_a_slice_that_is_approved_or_built_cannot_be_moved(
    app, auth_headers, planner, scheduled
):
    path = await _roadmap_of_five(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, path, key="s1")

    # Drafting may move.
    response = await app.post(
        MOVE, json={"path": path, "slice": "s1", "position": 2}, headers=auth_headers
    )
    assert response.status_code == 200, response.text

    approved = await _approve(app, auth_headers, slice_path)
    assert approved.status_code == 200, approved.text
    (task_id,) = approved.json()["tasks_created"]
    approved_refusal = await app.post(
        MOVE, json={"path": path, "slice": "s1", "position": 1}, headers=auth_headers
    )
    assert approved_refusal.status_code == 409
    assert approved_refusal.json()["detail"]["code"] == "slice_not_movable"
    assert "Approved" in approved_refusal.json()["detail"]["message"]

    await _move(app, auth_headers, task_id, "in_progress", "completed", "under_review", "approved")
    await land(task_id)
    built_refusal = await app.post(
        MOVE, json={"path": path, "slice": "s1", "position": 1}, headers=auth_headers
    )
    assert built_refusal.status_code == 409
    assert "Built" in built_refusal.json()["detail"]["message"]
    assert len(await _events(path, "slice_moved")) == 1, "only the move that applied is recorded"


@pytest.mark.asyncio
async def test_moving_a_slice_ahead_of_one_it_builds_after_warns_and_applies(
    app, auth_headers, planner
):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(
        MOVE, json={"path": path, "slice": "s4", "position": 2}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    by_key = {s["key"]: s for s in (await _slices(app, auth_headers, path))["slices"]}
    assert (await _order(app, auth_headers, path))[1] == "s4"
    assert "s3" in by_key["s4"]["warning"]
    assert by_key["s3"]["warning"] is None and by_key["s5"]["warning"] is None


@pytest.mark.asyncio
async def test_the_operator_removes_a_not_drafted_slice_and_it_is_recorded(
    app, auth_headers, planner
):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(REMOVE, json={"path": path, "slice": "s5"}, headers=auth_headers)

    assert response.status_code == 200, response.text
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4"]
    (event,) = await _events(path, "slice_removed")
    assert event.actor == "operator"
    assert event.detail["slice"] == "s5"


@pytest.mark.asyncio
async def test_removing_a_slice_drops_it_from_others_builds_after_and_says_so(
    app, auth_headers, planner
):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(REMOVE, json={"path": path, "slice": "s3"}, headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json()["dropped_from_builds_after"] == ["s4"]
    by_key = {s["key"]: s for s in (await _slices(app, auth_headers, path))["slices"]}
    assert by_key["s4"]["builds_after"] == [] and by_key["s2"]["builds_after"] == ["s1"]
    (event,) = await _events(path, "slice_removed")
    assert event.detail["dropped_from_builds_after"] == ["s4"]


@pytest.mark.asyncio
async def test_a_slice_a_document_names_is_not_removed_and_the_refusal_names_it(
    app, auth_headers, planner
):
    path = await _roadmap_of_five(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, path, key="s3")

    response = await app.post(REMOVE, json={"path": path, "slice": "s3"}, headers=auth_headers)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "slice_named_by_document" and slice_path in detail["message"]
    assert "s3" in await _order(app, auth_headers, path)
    assert await _events(path, "slice_removed") == []


@pytest.mark.asyncio
async def test_a_slice_is_edited_only_on_an_approved_roadmap(app, auth_headers, planner):
    path = await _agent_create(app, planner, kind="roadmap", title="Still exploring")
    saved = await _agent_submit(app, planner, path, _roadmap(slices=_five()))
    assert saved.status_code == 200, saved.text

    for route, body in (
        (MOVE, {"slice": "s5", "position": 1}),
        (REMOVE, {"slice": "s5"}),
    ):
        response = await app.post(route, json={"path": path, **body}, headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "roadmap_not_approved"


@pytest.mark.asyncio
async def test_add_a_slice_opens_a_conversation_seeded_with_the_roadmap(
    app, auth_headers, planner, scheduled
):
    await _agents("planner")
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(CONVERSATION, json={"path": path}, headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent"] == "planner", "defaults to the roadmap's author"
    (entry,) = await _queued("planner")
    assert entry.conversation_id == body["conversation_id"]
    assert path in entry.content and "add_slice" in entry.content
    for key in ("s1", "s2", "s3", "s4", "s5"):
        assert key in entry.content, "seeded with the roadmap's slices"
    assert ("proj-test", "planner") in scheduled
    # Nothing was added by hand: the roadmap is as it was.
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4", "s5"]
    (event,) = await _events(path, "slice_conversation_started")
    assert event.detail["agent"] == "planner"


@pytest.mark.asyncio
async def test_the_conversation_is_refused_for_an_agent_that_is_not_open(
    app, auth_headers, planner, scheduled
):
    path = await _roadmap_of_five(app, auth_headers, planner)

    response = await app.post(
        CONVERSATION, json={"path": path, "agent": "ghost"}, headers=auth_headers
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "agent_not_open"
    assert await _queued("ghost") == []


@pytest.mark.asyncio
async def test_the_asked_agent_adds_a_slice_marked_and_unreviewed(
    app, auth_headers, planner, scheduled
):
    await _agents("planner", "scout")
    path = await _roadmap_of_five(app, auth_headers, planner)
    started = await app.post(
        CONVERSATION, json={"path": path, "agent": "scout"}, headers=auth_headers
    )
    assert started.status_code == 200, started.text
    scout = await _run(
        "run-scout", "aw_run_scout-secret", agent="scout", conversation_id="conv-scout"
    )

    response = await app.post(
        AMEND,
        json={
            "path": path,
            "op": "add_slice",
            "reason": "Operator wants a polish slice",
            "how_to_check": "It reads third on the roadmap",
            "change": {
                "title": "Polish pass",
                "intent": "It feels finished",
                "done": "The polish list is empty",
                "builds_after": ["s1"],
                "position": 3,
            },
        },
        headers=scout,
    )

    assert response.status_code == 201, response.text
    assert response.json()["op"] == "add_slice" and response.json()["reviewed"] is False
    body = await _slices(app, auth_headers, path)
    assert [s["key"] for s in body["slices"]] == ["s1", "s2", "polish-pass", "s3", "s4", "s5"]
    added = body["slices"][2]
    assert added["added_after_approval"] is True and added["added_by"] == "scout"
    assert added["builds_after"] == ["s1"] and added["state"] == "Not drafted"
    assert await _phase(path) == "approved"
    listed = await app.get(f"{BASE}/documents/{path}/amendments", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (amendment,) = listed.json()["amendments"]
    assert (amendment["op"], amendment["author"], amendment["reviewed"]) == (
        "add_slice",
        "scout",
        False,
    )
    assert amendment["run_id"] == "run-scout"
    (added_event,) = await _events(path, "slice_added")
    assert (added_event.actor, added_event.run_id) == ("scout", "run-scout")


@pytest.mark.asyncio
async def test_an_agent_the_operator_did_not_ask_cannot_add_a_slice(
    app, auth_headers, planner, scheduled
):
    path = await _roadmap_of_five(app, auth_headers, planner)
    async with async_session_factory() as session:
        session.add(Agent(id="ag-other", project_id="proj-test", name="other"))
        await session.commit()
    other = await _run("run-other", "aw_run_other-secret", agent="other", conversation_id="conv-o")

    response = await app.post(
        AMEND,
        json={
            "path": path,
            "op": "add_slice",
            "reason": "I think it is needed",
            "how_to_check": "n/a",
            "change": {"title": "Uninvited"},
        },
        headers=other,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "add_slice_not_asked"
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4", "s5"]


@pytest.mark.asyncio
async def test_an_added_slice_is_refused_when_it_names_a_missing_slice_or_position(
    app, auth_headers, planner, scheduled
):
    path = await _roadmap_of_five(app, auth_headers, planner)

    for change in (
        {"title": "Bad dependency", "builds_after": ["nope"]},
        {"title": "Bad position", "position": 9},
        {"title": "Duplicate", "key": "s1"},
        {"intent": "no title"},
    ):
        response = await app.post(
            AMEND,
            json={
                "path": path,
                "op": "add_slice",
                "reason": "r",
                "how_to_check": "c",
                "change": change,
            },
            headers=planner,
        )
        assert response.status_code == 422, (change, response.text)
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4", "s5"]


@pytest.mark.asyncio
async def test_no_route_adds_a_slice_from_a_form(app, auth_headers, planner):
    path = await _roadmap_of_five(app, auth_headers, planner)

    for route in ("slices", "slices/add", "slices/create"):
        response = await app.post(
            f"{BASE}/documents/{route}",
            json={"path": path, "title": "By hand", "slice": "by-hand"},
            headers=auth_headers,
        )
        assert response.status_code in (404, 405, 422), (route, response.status_code)
    assert await _order(app, auth_headers, path) == ["s1", "s2", "s3", "s4", "s5"]
    assert AGENT_DOCS  # the agent route is the only door
