"""`the-spec-page-redesigned` (`build-progress-on-the-document`): what a build has taken so far.

The page draws each build's runs, its wall time split by what it was doing and its cost by who spent
it. The figures come from `hub/build_figures.py` (one module, so roadmap slice G can swap it for the
shared tally) over what the build already records: the runs bound to its tasks, their turn usage,
the tasks' transitions and their check runs. The timeline here is written by hand so the expected
split is arithmetic, not a measurement.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, SpecDocument, Task, TaskCheckRun, TaskTransition, TurnUsage

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    PATH,
    P,
    _approved,
    _build,
    _document,
    _move,
    _roster_rows,
    _tasks_by_key,
    author_headers,  # noqa: F401, F811 -- a fixture, used by name
)

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


async def _usage(run_id: str, agent: str, task_id, micros: int) -> None:
    async with async_session_factory() as db:
        db.add(Run(id=run_id, project_id=P, agent=agent, task_id=task_id, status="completed"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{run_id}",
                run_id=run_id,
                project_id=P,
                agent=agent,
                status="measured",
                total_tokens=10,
                api_equivalent_usd_micros=micros,
                observed_at=T0,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_a_builds_figures_split_its_time_cost_and_runs(
    app, auth_headers, author_headers  # noqa: F811
):
    """t1 is built (100-300 s), then waits for review (300-700 s) with the checks running 500-600 s,
    while t2 is never handed out: 400 s waiting to be handed out (0-100 s and 700-1000 s), 200 s
    building, 100 s of checks, 300 s of review (t1 is decided at 700 s; t2 still waits). The builder's turn costs 3, the reviewer's 1.
    """
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(
        app, auth_headers, driver="hand", level="reviewed", builders=["dev"], reviewers=["qa"]
    )
    assert built.status_code == 200, built.text
    build_id = built.json()["build_outcome"]["build"]["id"]
    t1 = (await _tasks_by_key())["t1"]

    await _move(t1.id, "in_progress", "dev", run_id="run-dev-fig")
    await _move(t1.id, "completed", "dev", run_id="run-dev-fig")
    await _move(t1.id, "under_review", "qa", run_id="run-qa-fig")
    await _move(t1.id, "approved", "qa", run_id="run-qa-fig")
    async with async_session_factory() as db:
        build = await db.get(Build, build_id)
        build.created_at, build.stopped_at = _at(0), _at(1000)
        rows = (
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == t1.id)
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .all()
        )
        for row, seconds in zip(rows, (100, 300, 300, 700), strict=True):
            row.created_at = _at(seconds)
        db.add(
            TaskCheckRun(
                id="tcr-fig",
                project_id=P,
                task_id=t1.id,
                main_sha="a",
                target_shas=[],
                state="passed",
                results=[],
                error="",
                started_at=_at(500),
                ended_at=_at(600),
            )
        )
        await db.commit()
    await _usage("run-dev-fig-1", "dev", t1.id, 3_000_000)
    await _usage("run-qa-fig-1", "qa", t1.id, 1_000_000)
    await _usage("run-elsewhere", "dev", None, 9_000_000)  # not this build's: ignored

    read = await app.get(f"{BASE}/builds/{build_id}/figures", headers=auth_headers)

    assert read.status_code == 200, read.text
    assert read.json() == {
        "id": build_id,
        "runs": 2,
        "time": {"building": 200, "checks": 100, "review": 300, "waiting": 400},
        "cost": {"build": 3.0, "review": 1.0, "lead": 0.0},
    }


@pytest.mark.asyncio
async def test_another_projects_build_has_no_figures(app, auth_headers):
    read = await app.get(f"{BASE}/builds/build-nope/figures", headers=auth_headers)
    assert read.status_code == 404


@pytest.mark.asyncio
async def test_the_document_list_marks_a_running_build_and_its_progress(
    app, auth_headers, author_headers  # noqa: F811
):
    """The list the page filters ('has a build running') carries each running build's progress."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    assert (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"][0].get(
        "build"
    ) is None
    built = await _build(app, auth_headers, driver="hand", level="fast")
    build_id = built.json()["build_outcome"]["build"]["id"]
    t1 = (await _tasks_by_key())["t1"]
    await _move(t1.id, "in_progress", "dev", run_id="run-dev-list")
    await _move(t1.id, "completed", "dev", run_id="run-dev-list")
    await _move(t1.id, "approved", "dev", run_id="run-dev-list")

    (document,) = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]

    assert document["build"] == {"id": build_id, "done": 1, "total": 2}
    async with async_session_factory() as db:
        assert (
            (await db.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .one()
        )
        assert (await db.execute(select(Task).where(Task.build_id == build_id))).scalars().all()


@pytest.mark.asyncio
async def test_a_build_finishing_announces_the_document_so_the_page_stops_polling(
    app, auth_headers, author_headers, monkeypatch  # noqa: F811
):
    """The last task of a Fast build approved: the build reads finished and `spec_updated` goes out
    for the document, so an open page reads it again instead of polling a finished build."""
    from hub import sse as sse_module
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import operator

    await _roster_rows("dev")
    await _approved(app, auth_headers, author_headers, _document())
    assert (await _build(app, auth_headers, driver="hand", level="fast")).status_code == 200
    frames: list = []
    real = sse_module.sse_manager.publish

    def spy(project_id, event_type, payload):
        frames.append((event_type, payload))
        return real(project_id, event_type, payload)

    monkeypatch.setattr(sse_module.sse_manager, "publish", spy)
    for task in (await _tasks_by_key()).values():
        async with async_session_factory() as db:
            row = await db.get(Task, task.id)
            for status in ("in_progress", "completed", "approved"):
                await apply_transition(db, row, status, operator())
            await db.commit()

    read = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()
    assert read["builds"][0]["state"] == "finished"
    assert ("spec_updated", {"path": PATH}) in frames


@pytest.mark.asyncio
async def test_a_roadmap_read_names_the_change_document_of_each_slice(app, auth_headers):
    """`slice_documents` maps a slice key to the change document that names it."""
    from .test_a_roadmap_shows_which_of_its_slices_are_done import (
        FIRST,
        ROADMAP,
        _roadmap_with_first_claimed,
    )

    await _roadmap_with_first_claimed(app, auth_headers)

    page = (await app.get(f"{BASE}/spec", params={"path": ROADMAP}, headers=auth_headers)).json()

    assert page["slice_documents"] == {"first": FIRST}
