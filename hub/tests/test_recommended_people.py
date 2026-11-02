# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""A follow-up filed against a spec joins its build, reopening it if it had finished
(`every-task-comes-with-a-recommended-builder-and-checker`, FR-7 to FR-11 and FR-15).

Every filing goes through the agent's task route. Named by acceptance criterion: `-k ac_running`,
`-k ac_reopen`, `-k ac_warning`, `-k ac_flow`, `-k ac_stopped`, `-k ac_simultaneous`.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import update

from hub import landing_queue
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Build, Loop, Run, SpecDocument, Task, TaskLanding
from hub.scheduler import JobScheduler, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    PATH,
    P,
    _approved,
    _build,
    _document,
    _read,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_review_turn import _roster

AGENT_TASKS = "/api/v1/agent-actions/tasks"
JOBS = f"/api/v1/projects/{P}/jobs"
WARNINGS = f"{BASE}/reopening-warnings"
PEOPLE = {"builder": "DeveloperOpus", "checker": "QA", "builders": ["DeveloperOpus"]}
SCHEDULING = patch(
    "hub.turn_scheduler.schedule_agent",
    AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
)


async def _built(app, auth_headers, author_headers, bind_runner, **settings):
    await _roster(app, auth_headers, bind_runner, "DeveloperOpus", "Developer", "QA")
    await _approved(app, auth_headers, author_headers, _document())
    chosen = {"driver": "flow", "level": "reviewed", "budget_cap_usd": 50, **PEOPLE, **settings}
    with SCHEDULING:
        built = await _build(app, auth_headers, **chosen)
    assert built.status_code == 200, built.text


async def _finish(ago: timedelta = timedelta(hours=1)) -> None:
    """Every task closes, so the build finishes and its flow ends; then its end is aged."""
    for task in (await _tasks_by_key()).values():
        async with async_session_factory() as db:
            row = await db.get(Task, task.id)
            for status in ("in_progress", "completed", "under_review", "approved"):
                await apply_transition(db, row, status, operator())
            await db.commit()
    await landing_queue.drain(P)
    async with async_session_factory() as db:
        await db.execute(update(TaskLanding).values(state="landed"))
        await db.execute(update(Build).values(stopped_at=datetime.now(timezone.utc) - ago))
        await db.commit()
    (build,) = await _rows(Build)
    assert build.state == "finished"
    # Its flow outlived its last approval for that landing; the next firing ends it, if drained.
    for loop in await _rows(Loop):
        await _fire(loop.job_id)


async def _file(app, author_headers, title="A follow-up", **fields):
    filed = await app.post(
        AGENT_TASKS,
        json={"title": title, "spec_document": PATH, "requirement_ids": ["FR-1"], **fields},
        headers=author_headers,
    )
    assert filed.status_code == 201, filed.text
    return filed.json()


async def _shown(app, auth_headers) -> str:
    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    return next(d for d in listed.json()["documents"] if d["path"] == PATH)["display_phase"]


async def _only_build() -> Build:
    (build,) = await _rows(Build)
    return build


async def _warnings(app, auth_headers):
    read = await app.get(WARNINGS, headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()["warnings"]


async def _fire(job_id: str) -> None:
    with SCHEDULING:
        async with async_session_factory() as db:
            job = await db.get(AIJob, job_id)
            await JobScheduler()._do_fire_job(job, "scheduled", db)


@pytest.mark.asyncio
async def test_ac_running_a_task_takes_the_builds_people_unless_it_names_its_own(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)

    nobody = await _file(app, author_headers, title="Names nobody")
    named = await _file(app, author_headers, title="Names one", builder="Developer")
    assigned = await _file(app, author_headers, title="Assigned", assignee="Developer")

    assert (nobody["builder"], nobody["assignee"]) == ("DeveloperOpus", "DeveloperOpus")
    assert (named["builder"], named["assignee"]) == ("Developer", "Developer")
    assert (assigned["builder"], assigned["assignee"]) == ("Developer", "Developer")
    build = await _only_build()
    for task in (nobody, named, assigned):
        assert task["build_id"] == build.id
        read = await app.get(f"/api/v1/projects/{P}/tasks/{task['id']}", headers=auth_headers)
        assert read.json()["checker"] == "QA"
    assert await _warnings(app, auth_headers) == []


@pytest.mark.asyncio
async def test_ac_running_a_task_may_name_its_own_checker_but_only_an_open_agent(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    named = await _file(app, author_headers, checker="Developer")
    read = await app.get(f"/api/v1/projects/{P}/tasks/{named['id']}", headers=auth_headers)
    assert read.json()["checker"] == "Developer"

    refused = await app.post(
        AGENT_TASKS,
        json={
            "title": "Nobody",
            "spec_document": PATH,
            "requirement_ids": ["FR-1"],
            "builder": "Ghost",
        },
        headers=author_headers,
    )
    assert refused.status_code == 422
    assert "Ghost" in refused.text


@pytest.mark.asyncio
async def test_ac_running_a_task_named_against_the_spec_by_path_alone_joins_too(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    filed = await app.post(
        AGENT_TASKS, json={"title": "By path", "spec_document": PATH}, headers=author_headers
    )
    assert filed.status_code == 201, filed.text
    assert filed.json()["build_id"] == (await _only_build()).id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ago,words",
    [(timedelta(hours=1), "1 hour"), (timedelta(days=30), "30 days")],
    ids=["an-hour-ago", "30-days-ago"],
)
async def test_ac_reopen_a_finished_build_reopens_as_it_was(
    app, auth_headers, author_headers, bind_runner, ago, words
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(ago)
    before = await _only_build()
    assert await _shown(app, auth_headers) == "done"

    filed = await _file(app, author_headers)

    after = await _only_build()
    assert after.id == before.id
    assert after.state == "running"
    assert after.stopped_at is None
    assert (after.level, after.landing, after.budget_cap_usd_micros) == (
        "reviewed",
        before.landing,
        50_000_000,
    )
    assert filed["build_id"] == before.id
    assert (filed["builder"], filed["assignee"]) == ("DeveloperOpus", "DeveloperOpus")
    assert "reopened" in filed["build_note"]
    read = await _read(app, auth_headers)
    shown = next(b for b in read["builds"] if b["id"] == before.id)
    assert shown["state"] == "running"
    assert shown["reopenings"][0]["finished_ago"] == words
    assert await _shown(app, auth_headers) == "building"

    # It reads building until the task has landed, and done again once it has.
    async with async_session_factory() as db:
        row = await db.get(Task, filed["id"])
        for status in ("in_progress", "completed", "under_review", "approved"):
            await apply_transition(db, row, status, operator())
        await db.commit()
    await landing_queue.drain(P)
    async with async_session_factory() as db:
        await db.execute(update(TaskLanding).values(state="landed"))
        await db.commit()
    assert (await _only_build()).state == "finished"
    assert await _shown(app, auth_headers) == "done"


@pytest.mark.asyncio
async def test_ac_warning_route_payload_names_the_spec_task_filer_and_age(
    app, auth_headers, author_headers, bind_runner
):
    """The shape `reopeningWarnings.test.tsx` is fed."""
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(timedelta(days=30))
    filed = await _file(app, author_headers, title="Add FOLLOWUP.md")

    (warning,) = await _warnings(app, auth_headers)

    assert set(warning) == {
        "build_id",
        "document_id",
        "path",
        "title",
        "reopened_at",
        "finished_at",
        "finished_ago",
        "tasks",
    }
    assert warning["path"] == PATH
    assert warning["title"] == "A build of its own"
    assert warning["finished_ago"] == "30 days"
    assert warning["tasks"] == [
        {
            "id": filed["id"],
            "display_id": filed["readable_id"],
            "title": "Add FOLLOWUP.md",
            "filer": "author",
        }
    ]


@pytest.mark.asyncio
async def test_ac_warning_stopping_from_it_stops_the_build_and_its_flow(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(timedelta(days=30))
    filed = await _file(app, author_headers)
    (warning,) = await _warnings(app, auth_headers)
    (loop,) = await _rows(Loop, Loop.archived_at.is_(None))

    with patch("hub.scheduler.get_scheduler", return_value=None):
        stopped = await app.post(f"{BASE}/builds/{warning['build_id']}/stop", headers=auth_headers)
    assert stopped.status_code == 200, stopped.text

    assert (await _only_build()).state == "stopped"
    assert await _warnings(app, auth_headers) == []
    job = (await _rows(AIJob, AIJob.id == loop.job_id))[0]
    assert job.enabled is False
    await _fire(job.id)
    assert await _rows(Run, Run.task_id == filed["id"]) == []


@pytest.mark.asyncio
async def test_ac_warning_clears_when_the_build_ends_and_when_dismissed(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(timedelta(days=30))
    filed = await _file(app, author_headers)
    assert len(await _warnings(app, auth_headers)) == 1

    # Left alone, it clears when the build ends.
    async with async_session_factory() as db:
        row = await db.get(Task, filed["id"])
        for status in ("in_progress", "completed", "under_review", "approved"):
            await apply_transition(db, row, status, operator())
        await db.commit()
    assert (await _only_build()).state == "finished"
    assert await _warnings(app, auth_headers) == []

    # Reopened again: a new warning, which dismissing clears while the build runs on.
    await _file(app, author_headers, title="Another")
    (warning,) = await _warnings(app, auth_headers)
    dismissed = await app.post(
        f"{BASE}/builds/{warning['build_id']}/reopening-warning/dismiss", headers=auth_headers
    )
    assert dismissed.status_code == 200, dismissed.text
    assert await _warnings(app, auth_headers) == []
    assert (await _only_build()).state == "running"
    again = await app.post(
        f"{BASE}/builds/{warning['build_id']}/reopening-warning/dismiss", headers=auth_headers
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_ac_flow_a_finished_flow_build_gets_a_new_flow_that_starts_the_task(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish()
    (ended,) = await _rows(Loop)
    assert ended.ending_state == "completed"

    filed = await _file(app, author_headers)

    (fresh,) = await _rows(Loop, Loop.archived_at.is_(None))
    assert fresh.id != ended.id
    assert filed["loop_id"] == fresh.id
    assert (await _only_build()).loop_id == fresh.id
    job = (await _rows(AIJob, AIJob.id == fresh.job_id))[0]
    assert job.enabled is True
    # Decided on its first firing, with no other call.
    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, fresh.id), default_agent=job.agent)
    assert [(s.task.id, s.agent) for s in decision.selections] == [(filed["id"], "DeveloperOpus")]
    await _fire(job.id)
    async with async_session_factory() as db:
        assert (await db.get(Task, filed["id"])).status != "pending"


@pytest.mark.asyncio
async def test_ac_flow_a_finished_hand_build_waits_under_its_builder(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner, driver="hand")
    await _finish()

    filed = await _file(app, author_headers)

    assert (await _only_build()).state == "running"
    assert (filed["assignee"], filed["status"], filed["loop_id"]) == (
        "DeveloperOpus",
        "pending",
        None,
    )
    assert await _rows(Loop) == []
    assert await _rows(Run, Run.task_id == filed["id"]) == []
    assert len(await _warnings(app, auth_headers)) == 1


@pytest.mark.asyncio
async def test_ac_flow_a_flow_still_working_its_queue_is_not_replaced(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    (loop,) = await _rows(Loop)
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-the-hubs-fix",
                project_id=P,
                title="Fix",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()
    await _finish()

    filed = await _file(app, author_headers)

    (kept,) = await _rows(Loop)
    assert kept.id == loop.id and kept.archived_at is None and filed["loop_id"] == loop.id


@pytest.mark.asyncio
async def test_ac_flow_a_flow_named_by_a_stale_delivery_still_starts(
    app, auth_headers, author_headers, bind_runner
):
    """A delivery's stop time long past stops no reopened flow: it stops on an empty queue."""
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(timedelta(days=30))
    from hub.project_workspace import resolve_project_workspace
    from hub.spec_documents import parse_hub, parse_stored, read_document, serialize, write_document

    async with async_session_factory() as db:
        workspace = await resolve_project_workspace(db, P)
    content = read_document(workspace, PATH)
    stored = parse_stored(content)
    stored["delivery"] = {**stored["delivery"], "stop_at": "2020-01-01T00:00:00+00:00"}
    write_document(workspace, PATH, serialize(stored, parse_hub(content)))

    filed = await _file(app, author_headers)

    (fresh,) = await _rows(Loop, Loop.archived_at.is_(None))
    assert filed["loop_id"] == fresh.id
    assert (fresh.stop_at, fresh.stop_when_queue_empties) == (None, True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["the operator", "the cap"],
)
async def test_ac_stopped_a_stopped_build_stays_stopped_and_the_next_build_takes_it_in(
    app, auth_headers, author_headers, bind_runner, reason
):
    await _built(app, auth_headers, author_headers, bind_runner)
    build = await _only_build()
    if reason == "the operator":
        with patch("hub.scheduler.get_scheduler", return_value=None):
            stopped = await app.post(f"{BASE}/builds/{build.id}/stop", headers=auth_headers)
        assert stopped.status_code == 200, stopped.text
    else:
        from hub import builds

        async with async_session_factory() as db:
            await builds.stop(
                db, await db.get(Build, build.id), "the build has spent $1 of its cap"
            )
            await db.commit()
    loops_before = len(await _rows(Loop))

    filed = await _file(app, author_headers, builder="Developer")

    after = await _only_build()
    assert after.state == "stopped"
    assert (filed["build_id"], filed["loop_id"]) == (None, None)
    assert "stopped" in filed["build_note"]
    assert "next Build" in filed["build_note"]
    assert await _warnings(app, auth_headers) == []
    assert len(await _rows(Loop)) == loops_before

    with SCHEDULING:
        again = await _build(app, auth_headers, driver="flow", level="reviewed", **PEOPLE)
    assert again.status_code == 200, again.text
    async with async_session_factory() as db:
        taken = await db.get(Task, filed["id"])
    running = [row for row in await _rows(Build) if row.state == "running"]
    assert len(running) == 1
    assert taken.build_id == running[0].id
    assert taken.builder == "Developer" and taken.assignee == "Developer"
    assert taken.loop_id == running[0].loop_id
    assert await _warnings(app, auth_headers) == []


@pytest.mark.asyncio
async def test_ac_stopped_a_task_taken_in_with_no_name_takes_the_new_builds_default(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    build = await _only_build()
    with patch("hub.scheduler.get_scheduler", return_value=None):
        await app.post(f"{BASE}/builds/{build.id}/stop", headers=auth_headers)
    filed = await _file(app, author_headers)

    with SCHEDULING:
        again = await _build(
            app, auth_headers, driver="flow", level="reviewed", builder="Developer", checker="QA"
        )
    assert again.status_code == 200, again.text
    read = await app.get(f"/api/v1/projects/{P}/tasks/{filed['id']}", headers=auth_headers)
    assert (read.json()["builder"], read.json()["assignee"], read.json()["checker"]) == (
        "Developer",
        "Developer",
        "QA",
    )


@pytest.mark.asyncio
async def test_ac_stopped_an_archived_spec_starts_nothing_and_says_why(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish()
    async with async_session_factory() as db:
        await db.execute(update(SpecDocument).values(phase="archived"))
        await db.commit()
    loops_before = len(await _rows(Loop, Loop.archived_at.is_(None)))

    filed = await _file(app, author_headers)

    assert (await _only_build()).state == "finished"
    assert (filed["build_id"], filed["loop_id"]) == (None, None)
    assert "archived" in filed["build_note"]
    assert "next Build" not in filed["build_note"]
    assert await _warnings(app, auth_headers) == []
    assert len(await _rows(Loop, Loop.archived_at.is_(None))) == loops_before


@pytest.mark.asyncio
async def test_ac_simultaneous_one_build_one_flow_one_warning_and_create_flow_refused(
    app, auth_headers, author_headers, bind_runner
):
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish(timedelta(days=30))

    one, two = await asyncio.gather(
        _file(app, author_headers, title="One"),
        _file(app, author_headers, title="Two"),
    )

    build = await _only_build()
    assert build.state == "running"
    assert one["build_id"] == two["build_id"] == build.id
    (live,) = await _rows(Loop, Loop.archived_at.is_(None))
    assert one["loop_id"] == two["loop_id"] == live.id
    assert build.loop_id == live.id
    (warning,) = await _warnings(app, auth_headers)
    assert {task["title"] for task in warning["tasks"]} == {"One", "Two"}
    assert len(build.reopenings) == 1

    refused = await app.post(
        JOBS,
        json={
            "name": "Second driver",
            "agent": "DeveloperOpus",
            "message": "go",
            "cron": "*/5 * * * *",
            "stop_when_queue_empties": True,
            "spec_document_id": build.document_id,
        },
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert build.id in refused.text


@pytest.mark.asyncio
async def test_a_task_put_in_a_named_queue_does_not_reopen_the_build(
    app, auth_headers, author_headers, bind_runner
):
    """Its queue is its driver, and a Hub fix task carries no document at all."""
    await _built(app, auth_headers, author_headers, bind_runner)
    await _finish()
    async with async_session_factory() as db:
        job = AIJob(
            id="job-other",
            project_id=P,
            name="Other",
            agent="author",
            message="go",
            cron="*/5 * * * *",
        )
        db.add(job)
        db.add(Loop(id="loop-other", project_id=P, job_id=job.id, purpose="other"))
        await db.commit()

    filed = await _file(app, author_headers, loop_id="loop-other")

    assert (await _only_build()).state == "finished"
    assert filed["build_id"] is None
