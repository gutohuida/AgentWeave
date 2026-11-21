"""A stall offers its remedies (`a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, D5).

FR-8: the stall read carries `remedies` derived from its cause, and `POST /tasks/{id}/checker`
names a different checker -- recorded on the build, finished work handed to them for review, and
the task's `review_unstaffed` stall ended. FR-9's half on the Hub: the reasons read as sentences.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from hub import stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Build, InboundQueueEntry, Stall, Task, TaskTransition

from .test_review_turn import _roster

P = "proj-test"
TASKS = f"/api/v1/projects/{P}/tasks"
STALLS = f"/api/v1/projects/{P}/stalls"
REASON = (
    "TPBCD-4's checker QA has no runner bound, so its check is held and given to nobody else. "
    "Bind a runner to QA, or name a different checker."
)


async def _stalled_build_task(status="completed"):
    async with async_session_factory() as db:
        db.add(
            Build(
                id="build-st",
                project_id=P,
                document_id="spdoc-st",
                driver="flow",
                level="reviewed",
                state="running",
                people={
                    "builder": "Developer",
                    "checker": "QA",
                    "tasks": {"stall-surfaces": {"builder": "Developer", "checker": "QA"}},
                },
            )
        )
        db.add(
            Task(
                id="task-st",
                project_id=P,
                title="Stalled",
                status=status,
                assignee="Developer",
                builder="Developer",
                build_id="build-st",
                spec_task_key="stall-surfaces",
            )
        )
        if status == "completed":
            db.add(
                TaskTransition(
                    id="tt-st",
                    task_id="task-st",
                    project_id=P,
                    from_status="in_progress",
                    to_status="completed",
                    actor_kind="run",
                    actor_agent="Developer",
                )
            )
        await db.commit()
        stall, _ = await stalls.record(
            db, P, cause="review_unstaffed", subject="task-st", text=REASON, task_id="task-st"
        )
    return stall.id


async def _unbind(name):
    async with async_session_factory() as db:
        agent = await db.scalar(select(Agent).where(Agent.project_id == P, Agent.name == name))
        agent.runner_id = None
        await db.commit()


async def _name(app, auth_headers, agent):
    with (
        patch(
            "hub.task_integration.review_target", AsyncMock(return_value=MagicMock(resolved=True))
        ),
        patch("hub.turn_scheduler.schedule_agent", AsyncMock()),
    ):
        return await app.post(
            f"{TASKS}/task-st/checker", json={"agent": agent}, headers=auth_headers
        )


async def _entries(agent):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_a_review_stall_reads_with_its_remedies(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA")
    await _stalled_build_task()

    response = await app.get(f"{STALLS}?open=true", headers=auth_headers)

    assert response.status_code == 200, response.text
    (stall,) = response.json()["stalls"]
    assert stall["remedies"] == ["name_checker", "review_yourself"]


@pytest.mark.asyncio
async def test_other_causes_and_ended_stalls_offer_no_remedy(app, auth_headers):
    async with async_session_factory() as db:
        dead, _ = await stalls.record(db, P, cause="dead_run", subject="run-x", text="A run died.")
        review, _ = await stalls.record(
            db, P, cause="review_unstaffed", subject="task-y", text=REASON, task_id="task-y"
        )
        assert stalls.view(dead)["remedies"] == []
        await stalls.end(db, review, "resolved", "done")
        assert stalls.view(review)["remedies"] == []


@pytest.mark.asyncio
async def test_naming_a_checker_with_a_runner_ends_the_stall_and_queues_its_review(
    app, auth_headers, bind_runner
):
    """stall-remedy-controls-work, on the route the card's control calls."""
    await _roster(app, auth_headers, bind_runner, "Developer", "QA", "QA2")
    await _unbind("QA")
    stall_id = await _stalled_build_task()

    response = await _name(app, auth_headers, "QA2")

    assert response.status_code == 200, response.text
    assert "QA2" in response.json()["next_turn"]
    (entry,) = await _entries("QA2")
    assert entry.review_task_id == "task-st"
    async with async_session_factory() as db:
        stall = await db.get(Stall, stall_id)
        build = await db.get(Build, "build-st")
    assert stall.ended_at is not None and stall.outcome == "resolved"
    assert "QA2" in stall.outcome_detail
    assert build.people["tasks"]["stall-surfaces"]["checker"] == "QA2"


@pytest.mark.asyncio
async def test_a_checker_with_no_runner_is_refused_and_nothing_changes(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA")
    await _unbind("QA")
    stall_id = await _stalled_build_task()

    response = await _name(app, auth_headers, "QA")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("QA has no runner bound")
    assert "task-" not in detail
    async with async_session_factory() as db:
        assert (await db.get(Stall, stall_id)).ended_at is None
        assert (await db.get(Build, "build-st")).people["tasks"]["stall-surfaces"]["checker"] == (
            "QA"
        )
    assert await _entries("QA") == []


@pytest.mark.asyncio
async def test_the_builder_is_refused_as_its_own_checker(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA")
    stall_id = await _stalled_build_task()

    response = await _name(app, auth_headers, "Developer")

    assert response.status_code == 422
    assert "builder" in response.json()["detail"]
    async with async_session_factory() as db:
        assert (await db.get(Stall, stall_id)).ended_at is None


@pytest.mark.asyncio
async def test_unfinished_work_records_the_checker_for_its_review(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA", "QA2")
    await _stalled_build_task(status="in_progress")

    response = await _name(app, auth_headers, "QA2")

    assert response.status_code == 200, response.text
    assert await _entries("QA2") == []
    async with async_session_factory() as db:
        assert (await db.get(Build, "build-st")).people["tasks"]["stall-surfaces"]["checker"] == (
            "QA2"
        )
        assert (await db.get(Task, "task-st")).status == "in_progress"
