"""A roadmap's slices say where they stand, what they cost and what is offered
(`a-roadmap-that-is-recognisably-a-roadmap`, RTRR-2: FR-1..FR-6, FR-11).

The states are a pure function of a slice document and its figures (`slice_progress._state`), tested
for all five; the rest runs through the Hub's own routes: the roadmap's read carries `slices` and
`progress`, Overview's `next-slice-offers` and the roadmap read are the one offer rule, a decline
answers both, a second take queues nothing.
"""

# ruff: noqa: F811

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from hub import manager, slice_progress
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Build,
    EventLog,
    Run,
    SpecDocument,
    Task,
    TurnUsage,
)

from .test_next_slice_offer import (  # noqa: F401 -- fixtures
    DECLINE,
    DONE,
    OFFERS,
    TAKE,
    _agents,
    _built_slice,
    land,
)
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    BASE,
    _approved_roadmap_doc,
    _move,
    _proposed_slice,
    _queued,
    _settle,
    planner,
    scheduled,
)


def _facts(**kw):
    base = {"tasks_total": 0, "tasks_on_main": 0, "started_off_main": False, "build_running": False}
    return {**base, **kw}


def _doc(phase):
    return SimpleNamespace(phase=phase)


def test_the_five_states_in_order():
    states = [
        slice_progress._state(None, None),
        slice_progress._state(_doc("exploring"), _facts()),
        slice_progress._state(_doc("approved"), _facts(tasks_total=2)),
        slice_progress._state(
            _doc("approved"), _facts(tasks_total=2, tasks_on_main=1, started_off_main=True)
        ),
        slice_progress._state(_doc("approved"), _facts(tasks_total=2, tasks_on_main=2)),
    ]
    assert states == ["Not drafted", "Drafting", "Approved", "Building", "Built"]


def test_a_running_build_is_building_and_a_proposal_is_drafting():
    assert slice_progress._state(_doc("proposed"), _facts()) == "Drafting"
    assert (
        slice_progress._state(_doc("approved"), _facts(tasks_total=1, build_running=True))
        == "Building"
    )


async def _read(app, auth_headers, roadmap_path):
    response = await app.get(f"{BASE}/spec", params={"path": roadmap_path}, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {s["key"]: s for s in body["slices"]}, body["progress"]


@pytest.mark.asyncio
async def test_a_slice_whose_work_has_not_landed_is_building_not_built(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slices, _ = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["state"] == "Not drafted" and slices["s1"]["offers_drafting"]
    assert slices["s2"]["waits_for"] == ["s1"] and not slices["s2"]["offers_drafting"]

    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)
    slices, _ = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["state"] == "Drafting" and slices["s1"]["document"] == slice_path


@pytest.mark.asyncio
async def test_approved_then_building_then_built(
    app, auth_headers, planner, scheduled
):  # noqa: F811
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    slices, progress = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["state"] == "Approved"
    assert (slices["s1"]["tasks_on_main"], slices["s1"]["tasks_total"]) == (0, 1)

    await _move(app, auth_headers, task_id, "in_progress", "completed", "under_review", "approved")
    slices, progress = await _read(app, auth_headers, roadmap_path)
    # Approved is not on main: the landing has not happened.
    assert slices["s1"]["state"] == "Building"
    assert slices["s1"]["tasks_on_main"] == 0 and progress["built"] == 0

    await land(task_id)
    slices, progress = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["state"] == "Built"
    assert (slices["s1"]["tasks_on_main"], slices["s1"]["tasks_total"]) == (1, 1)
    assert slices["s1"]["built_at"]
    assert (progress["built"], progress["total"]) == (1, 2)


async def _turn(project_id, task_id, micros):
    async with async_session_factory() as session:
        run = Run(
            id=f"run-{task_id[-6:]}-{micros}",
            project_id=project_id,
            agent="planner",
            status="completed",
            initiator="autonomous",
            task_id=task_id,
        )
        session.add(run)
        await session.flush()
        session.add(
            TurnUsage(
                id=f"tu-{run.id}",
                run_id=run.id,
                project_id=project_id,
                agent="planner",
                status="measured",
                total_tokens=1000,
                api_equivalent_usd_micros=micros,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_cost_is_summed_and_unpriced_turns_are_counted_not_added(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == slice_path))
        ).scalar_one()
        task = await session.get(Task, task_id)
        for name in ("a", "b"):
            session.add(
                Build(
                    id=f"build-{name}",
                    project_id="proj-test",
                    document_id=document.id,
                    state="finished",
                    driver="flow",
                    level="reviewed",
                    landing="main",
                )
            )
        task.build_id = "build-a"
        await session.commit()
    await _turn("proj-test", task_id, 11_960_000)
    await _turn("proj-test", task_id, 24_420_000)
    await _turn("proj-test", task_id, None)

    slices, progress = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["cost_usd"] == 36.38
    assert slices["s1"]["unpriced_turns"] == 1
    assert progress["cost_usd"] == 36.38 and progress["unpriced_turns"] == 1


@pytest.mark.asyncio
async def test_a_built_slice_links_its_retrospective_or_says_none(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, "in_progress", "completed", "under_review", "approved")
    await land(task_id)
    slices, _ = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["state"] == "Built" and slices["s1"]["retrospective"] is None

    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == slice_path))
        ).scalar_one()
        session.add(
            EventLog(
                id="ev-retro",
                project_id="proj-test",
                event_type=manager.FIRED_EVENT,
                data={
                    "job": manager.BUILD_RETROSPECTIVE,
                    "subject": {"document": document.id},
                    "outcome": "written",
                    "vault_source": "src-1",
                },
            )
        )
        await session.commit()
    slices, _ = await _read(app, auth_headers, roadmap_path)
    assert slices["s1"]["retrospective"]["document"] == slice_path
    assert slices["s1"]["retrospective"]["vault_source"] == "src-1"


@pytest.mark.asyncio
async def test_overview_and_the_roadmap_offer_the_same_slices_and_a_decline_answers_both(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)

    async def page():
        slices, _ = await _read(app, auth_headers, roadmap_path)
        return sorted(k for k, s in slices.items() if s["offers_drafting"])

    async def overview():
        offers = (await app.get(OFFERS, headers=auth_headers)).json()["offers"]
        return sorted(o["next_slice"]["key"] for o in offers if o["roadmap"] == roadmap_path)

    assert await page() == await overview() == ["s1"]
    declined = await app.post(
        DECLINE, json={"path": roadmap_path, "slice": "s1"}, headers=auth_headers
    )
    assert declined.status_code == 200, declined.text
    assert await page() == await overview() == []


@pytest.mark.asyncio
async def test_taking_an_offer_twice_queues_one_turn_that_carries_the_prior_outcomes(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    async with async_session_factory() as session:
        session.add(Agent(id="ag-architect", project_id="proj-test", name="architect"))
        await session.commit()
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await land(task_id)
    await _settle()

    body = {"path": roadmap_path, "slice": "s2", "agent": "architect"}
    taken = await app.post(TAKE, json=body, headers=auth_headers)
    again = await app.post(TAKE, json=body, headers=auth_headers)

    assert taken.status_code == 200, taken.text
    assert again.status_code == 409, again.text
    (entry,) = await _queued("architect")
    assert roadmap_path in entry.content and "`s2`" in entry.content
    assert f"`{slice_path}`" in entry.content and "`s1`" in entry.content
    assert "Retrospective: none has been written yet" in entry.content
