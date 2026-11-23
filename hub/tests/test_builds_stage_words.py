"""`builds.project_rows` names what each build is doing now (`overview-at-a-glance-with-dashboard-
and-briefing-tabs`, FR-8, D8): the furthest-along unfinished task's stage, or that it waits for the
operator, or is stalled."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from hub import builds
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, SpecDocument, Stall, Task, TaskCheckRun, TaskLanding

from .conftest import TEST_PROJECT_ID

P = TEST_PROJECT_ID
NOW = datetime.now(timezone.utc)


async def _words(*rows: Any) -> Dict[str, str]:
    async with async_session_factory() as db:
        db.add(SpecDocument(id="spdoc-x", project_id=P, path="spec/changes/x/spec.json", title="X"))
        db.add(
            Build(
                id="build-x", project_id=P, document_id="spdoc-x", driver="flow", level="reviewed"
            )
        )
        await db.flush()
        for row in rows:
            db.add(row)
            await db.flush()
        await db.commit()
    async with async_session_factory() as db:
        return {r["id"]: r["stage_words"] for r in await builds.project_rows(db, P)}


def _task(n: int, status: str) -> Task:
    return Task(
        id=f"t-{n}",
        readable_id=f"X-{n}",
        project_id=P,
        title=f"Task {n}",
        status=status,
        build_id="build-x",
        created_at=NOW - timedelta(hours=10 - n),
    )


@pytest.mark.asyncio
async def test_a_task_in_its_landing_check_is_named(app):
    words = await _words(
        _task(1, "approved"),
        _task(2, "approved"),
        TaskLanding(id="tl-2", project_id=P, task_id="t-2", state="queued", order_key=1.0),
    )
    assert words["build-x"] == "Checking task X-2"


@pytest.mark.asyncio
async def test_a_task_whose_own_checks_run_is_checking(app):
    words = await _words(
        _task(1, "in_progress"),
        _task(2, "completed"),
        TaskCheckRun(
            id="tcr", project_id=P, task_id="t-2", main_sha="a", target_shas=[], state="running"
        ),
    )
    assert words["build-x"] == "Checking task X-2"


@pytest.mark.asyncio
async def test_the_furthest_along_task_wins(app):
    words = await _words(
        _task(1, "in_progress"),
        Run(id="run-1", project_id=P, agent="dev", task_id="t-1", status="running"),
        _task(2, "under_review"),
        _task(3, "approved"),
        TaskLanding(id="tl-3", project_id=P, task_id="t-3", state="landing", order_key=1.0),
    )
    assert words["build-x"] == "Landing task X-3"


@pytest.mark.asyncio
async def test_building_beats_waiting_to_start(app):
    words = await _words(
        _task(1, "assigned"),
        _task(2, "in_progress"),
        Run(id="run-2", project_id=P, agent="dev", task_id="t-2", status="running"),
    )
    assert words["build-x"] == "Building task X-2"


@pytest.mark.asyncio
async def test_a_stalled_build_says_so(app):
    words = await _words(
        _task(1, "in_progress"),
        Stall(id="st-1", project_id=P, key="k", cause="stuck_task", reason="nobody", task_id="t-1"),
    )
    assert words["build-x"] == "Stalled"


@pytest.mark.asyncio
async def test_an_ended_build_says_how_it_ended(app):
    async with async_session_factory() as db:
        db.add(SpecDocument(id="spdoc-y", project_id=P, path="spec/changes/y/spec.json", title="Y"))
        db.add(
            Build(
                id="build-f",
                project_id=P,
                document_id="spdoc-y",
                driver="flow",
                level="fast",
                state="finished",
            )
        )
        db.add(
            Build(
                id="build-s",
                project_id=P,
                document_id="spdoc-y",
                driver="flow",
                level="fast",
                state="stopped",
            )
        )
        await db.commit()
    async with async_session_factory() as db:
        words = {r["id"]: r["stage_words"] for r in await builds.project_rows(db, P)}
    assert words == {"build-f": "Finished", "build-s": "Stopped"}
