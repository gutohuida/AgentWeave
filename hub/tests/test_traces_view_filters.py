"""`a-traces-view-with-filters-grouping-and-stats`: the traces list filters by agent and time range
(FR-3) and each run's row carries what the view shows (FR-4, FR-14)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub import traces, work_tally
from hub.db.engine import async_session_factory
from hub.db.models import Build, Conversation, Run, Stall, Task, TurnUsage

PROJECT = "proj-test"
NOW = datetime.now(timezone.utc)


async def _run(
    run_id,
    agent,
    *,
    days_ago=0,
    status="completed",
    task_id=None,
    conv=None,
    micros=None,
    model="haiku",
):
    started = NOW - timedelta(days=days_ago, minutes=5)
    async with async_session_factory() as db:
        run = Run(
            id=run_id,
            project_id=PROJECT,
            agent=agent,
            status="running",
            started_at=started,
            task_id=task_id,
            conversation_id=conv,
        )
        db.add(run)
        traces.start_run(db, run, prompt="go", runner="claude", model=model)
        await db.commit()
    if status == "running":
        return
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = status
        run.ended_at = started + timedelta(seconds=10)
        if micros is not None:
            db.add(
                TurnUsage(
                    id=f"tu-{run_id}",
                    run_id=run_id,
                    project_id=PROJECT,
                    agent=agent,
                    status="measured",
                    total_tokens=10,
                    model=model,
                    api_equivalent_usd_micros=micros,
                )
            )
        await traces.finish_run(db, run_id)
        await db.commit()


async def _listed(app, auth_headers, **params):
    res = await app.get(f"/api/v1/projects/{PROJECT}/traces", params=params, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["traces"]


@pytest.mark.asyncio
async def test_agent_task_and_range_filters_combine(app, auth_headers):
    async with async_session_factory() as db:
        db.add(Task(id="task-v1", project_id=PROJECT, title="One"))
        db.add(Task(id="task-v2", project_id=PROJECT, title="Two"))
        await db.commit()
    await _run("run-v-a1", "alpha", task_id="task-v1")
    await _run("run-v-a2", "alpha", task_id="task-v2")
    await _run("run-v-a3", "alpha", task_id="task-v1", days_ago=2)
    await _run("run-v-b1", "beta", task_id="task-v1")

    ids = lambda rows: {t["run_id"] for t in rows}  # noqa: E731
    assert ids(await _listed(app, auth_headers, agent="alpha")) == {
        "run-v-a1",
        "run-v-a2",
        "run-v-a3",
    }
    assert ids(await _listed(app, auth_headers, agent="beta")) == {"run-v-b1"}
    since = (NOW - timedelta(hours=1)).isoformat()
    assert ids(await _listed(app, auth_headers, since=since)) == {
        "run-v-a1",
        "run-v-a2",
        "run-v-b1",
    }
    until = (NOW - timedelta(days=1)).isoformat()
    assert ids(await _listed(app, auth_headers, until=until)) == {"run-v-a3"}
    assert ids(await _listed(app, auth_headers, agent="alpha", task_id="task-v1", since=since)) == {
        "run-v-a1"
    }
    bad = await app.get(
        f"/api/v1/projects/{PROJECT}/traces",
        params={"since": until, "until": (NOW - timedelta(days=3)).isoformat()},
        headers=auth_headers,
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_a_runs_row_carries_its_fields(app, auth_headers):
    async with async_session_factory() as db:
        db.add(Task(id="task-r1", readable_id="TV-9", project_id=PROJECT, title="Wire it"))
        db.add(Conversation(id="conv-r1", project_id=PROJECT, agent="gamma", title="Chatting"))
        await db.commit()
    await _run("run-r-ok", "gamma", task_id="task-r1", micros=12_500, model="claude-haiku")
    await _run("run-r-bad", "gamma", status="failed", conv="conv-r1", micros=2_000)
    await _run("run-r-gone", "gamma", task_id="task-gone", micros=None)
    await _run("run-r-live", "gamma", status="running")

    rows = {t["run_id"]: t for t in await _listed(app, auth_headers, agent="gamma")}
    ok = rows["run-r-ok"]
    assert (ok["task_ref"], ok["task_title"], ok["task_missing"]) == ("TV-9", "Wire it", False)
    assert ok["model"] == "claude-haiku"
    assert ok["cost_usd"] == 0.0125 and ok["cost_state"] == "measured"
    assert ok["is_error"] is False
    bad = rows["run-r-bad"]
    assert bad["is_error"] is True
    assert bad["conversation_title"] == "Chatting" and bad["task_missing"] is False
    gone = rows["run-r-gone"]
    assert gone["task_missing"] is True and gone["task_title"] is None
    assert gone["cost_usd"] is None and gone["cost_state"] == "unpriced"
    live = rows["run-r-live"]
    assert live["cost_state"] == "running" and live["cost_usd"] is None


@pytest.mark.asyncio
async def test_build_filter_lists_exactly_the_runs_of_that_builds_tasks(app, auth_headers):
    """FR-12: a build's run count opens the view filtered to the runs of that build's tasks."""
    async with async_session_factory() as db:
        db.add(Task(id="task-bf1", project_id=PROJECT, title="In build", build_id="build-bf1"))
        db.add(Task(id="task-bf2", project_id=PROJECT, title="Other build", build_id="build-bf2"))
        db.add(Task(id="task-bf3", project_id=PROJECT, title="No build"))
        for bid in ("build-bf1", "build-bf2"):
            db.add(
                Build(
                    id=bid,
                    project_id=PROJECT,
                    document_id=f"spdoc-{bid}",
                    driver="flow",
                    level="reviewed",
                    lead_conversation_id="conv-lead-bf1" if bid == "build-bf1" else None,
                )
            )
        db.add(
            Stall(
                id="stall-bf1",
                project_id=PROJECT,
                key="k-bf1",
                cause="dead_run",
                task_id="task-bf1",
                conversation_id="conv-stall-bf1",
            )
        )
        await db.commit()
    await _run("run-bf-1", "alpha", task_id="task-bf1")
    await _run("run-bf-2", "beta", task_id="task-bf1")
    await _run("run-bf-3", "alpha", task_id="task-bf2")
    await _run("run-bf-4", "alpha", task_id="task-bf3")
    await _run("run-bf-mend", "mender", conv="conv-stall-bf1")
    await _run("run-bf-lead", "lead", conv="conv-lead-bf1")

    got = {t["run_id"] for t in await _listed(app, auth_headers, build_id="build-bf1")}
    assert got == {"run-bf-1", "run-bf-2", "run-bf-mend", "run-bf-lead"}
    async with async_session_factory() as db:
        card = (await work_tally.tally(db, PROJECT, build_id="build-bf1"))["builds"]["build-bf1"]
    assert card["runs"]["total"] == len(got)
    got = {
        t["run_id"] for t in await _listed(app, auth_headers, build_id="build-bf1", agent="beta")
    }
    assert got == {"run-bf-2"}
    assert await _listed(app, auth_headers, build_id="build-none") == []

    res = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/totals",
        params={"build_id": "build-bf1"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["totals"]["count"] == 4


@pytest.mark.asyncio
async def test_a_runs_row_says_who_started_it(app, auth_headers):
    """TWC-2: the row's `initiator` is the root span's `aw.run.initiator`."""
    for run_id, initiator in (("run-i-user", "operator"), ("run-i-auto", "autonomous")):
        async with async_session_factory() as db:
            run = Run(
                id=run_id,
                project_id=PROJECT,
                agent="iota",
                status="running",
                started_at=NOW - timedelta(minutes=5),
                initiator=initiator,
            )
            db.add(run)
            traces.start_run(db, run, prompt="go", runner="claude", model="haiku")
            await db.commit()
    rows = {t["run_id"]: t for t in await _listed(app, auth_headers, agent="iota")}
    assert rows["run-i-user"]["initiator"] == "operator"
    assert rows["run-i-auto"]["initiator"] == "autonomous"
