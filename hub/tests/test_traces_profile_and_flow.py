"""`profiles-threads-and-builds-everywhere` D5: GET /traces lists a profile's runs (the names folded
into it too) and a flow's runs, and each run's row says what kind of run it was (FR-6, FR-13)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub import traces
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Conversation,
    InboundQueueEntry,
    JobRun,
    Loop,
    Run,
    Task,
)

PROJECT = "proj-test"
NOW = datetime.now(timezone.utc)


async def _run(run_id, agent, *, minutes_ago, task_id=None, conv=None, status="completed"):
    started = NOW - timedelta(minutes=minutes_ago)
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
        traces.start_run(db, run, prompt="go", runner="claude", model="haiku")
        await db.commit()
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = status
        run.ended_at = started + timedelta(seconds=10)
        await traces.finish_run(db, run_id)
        await db.commit()


def _conversation(conv_id, agent, origin):
    return Conversation(id=conv_id, project_id=PROJECT, agent=agent, title=conv_id, origin=origin)


async def _listed(app, auth_headers, **params):
    res = await app.get(f"/api/v1/projects/{PROJECT}/traces", params=params, headers=auth_headers)
    assert res.status_code == 200, res.text
    return res.json()["traces"]


@pytest.mark.asyncio
async def test_profile_runs_listed(app, auth_headers):
    """profile-runs-listed: a thread, a task build, a review, a mender, a job and a message run of
    the profile, and a run of a name folded into it, all listed newest first with their kind, task,
    start time and outcome; another profile's run is not."""
    async with async_session_factory() as db:
        db.add(Agent(id="ag-pr-a", project_id=PROJECT, name="alpha"))
        db.add(
            Agent(
                id="ag-pr-old",
                project_id=PROJECT,
                name="old-alpha",
                folded_into="alpha",
                lifecycle="archived",
            )
        )
        db.add(Agent(id="ag-pr-b", project_id=PROJECT, name="beta"))
        db.add(Task(id="task-pr1", readable_id="PR-1", project_id=PROJECT, title="Build it"))
        db.add(Task(id="task-pr2", readable_id="PR-2", project_id=PROJECT, title="Check it"))
        db.add(_conversation("conv-pr-thread", "alpha", "operator"))
        db.add(_conversation("conv-pr-flow", "alpha", "job"))
        db.add(_conversation("conv-pr-review", "alpha", "job"))
        db.add(_conversation("conv-pr-mender", "alpha", "mender"))
        db.add(_conversation("conv-pr-job", "alpha", "job"))
        db.add(_conversation("conv-pr-peer", "alpha", "peer"))
        db.add(_conversation("conv-pr-old", "old-alpha", "operator"))
        db.add(_conversation("conv-pr-beta", "beta", "operator"))
        await db.commit()
    await _run("run-pr-old", "old-alpha", minutes_ago=70, conv="conv-pr-old")
    await _run("run-pr-thread", "alpha", minutes_ago=60, conv="conv-pr-thread")
    await _run("run-pr-task", "alpha", minutes_ago=50, task_id="task-pr1", conv="conv-pr-flow")
    await _run("run-pr-review", "alpha", minutes_ago=40, task_id="task-pr2", conv="conv-pr-review")
    await _run("run-pr-mender", "alpha", minutes_ago=30, conv="conv-pr-mender", status="failed")
    await _run("run-pr-job", "alpha", minutes_ago=20, conv="conv-pr-job")
    await _run("run-pr-msg", "alpha", minutes_ago=10, conv="conv-pr-peer")
    await _run("run-pr-beta", "beta", minutes_ago=5, conv="conv-pr-beta")
    async with async_session_factory() as db:
        db.add(
            InboundQueueEntry(
                id="iq-pr-review",
                project_id=PROJECT,
                agent="alpha",
                origin_type="job",
                content="review it",
                hop_depth=0,
                state="delivered",
                review_task_id="task-pr2",
                delivered_in_run_id="run-pr-review",
            )
        )
        await db.commit()

    rows = await _listed(app, auth_headers, profile="alpha")
    assert [(r["run_id"], r["run_kind"]) for r in rows] == [
        ("run-pr-msg", "message"),
        ("run-pr-job", "job"),
        ("run-pr-mender", "mender"),
        ("run-pr-review", "review"),
        ("run-pr-task", "task"),
        ("run-pr-thread", "thread"),
        ("run-pr-old", "thread"),
    ]
    by_id = {r["run_id"]: r for r in rows}
    assert by_id["run-pr-old"]["agent"] == "old-alpha"
    assert (by_id["run-pr-task"]["task_ref"], by_id["run-pr-task"]["task_title"]) == (
        "PR-1",
        "Build it",
    )
    assert by_id["run-pr-review"]["task_ref"] == "PR-2"
    assert by_id["run-pr-mender"]["run_status"] == "failed"
    assert by_id["run-pr-thread"]["run_status"] == "completed"
    for row in rows:
        assert row["start_time"] and row["conversation_id"]
    starts = [r["start_time"] for r in rows]
    assert starts == sorted(starts, reverse=True)

    assert {r["run_id"] for r in await _listed(app, auth_headers, profile="beta")} == {
        "run-pr-beta"
    }
    # `agent` still means the one name, folded names left out.
    assert {r["run_id"] for r in await _listed(app, auth_headers, agent="old-alpha")} == {
        "run-pr-old"
    }


async def _flow(loop_id, job_id, *, archived):
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id=job_id,
                project_id=PROJECT,
                name=f"Flow {loop_id}",
                agent="alpha",
                message="next",
                cron="*/5 * * * *",
                enabled=not archived,
            )
        )
        db.add(
            Loop(
                id=loop_id,
                project_id=PROJECT,
                job_id=job_id,
                stopped_at=NOW if archived else None,
                stop_reason="operator stopped it" if archived else None,
                archived_at=NOW if archived else None,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_flow_runs_listed(app, auth_headers):
    """flow-runs-listed: a flow in no build started two task runs on two profiles, then was
    stopped and archived; both are listed newest first with profile, task, start time and outcome.
    A run of another flow's task is not."""
    await _flow("loop-fr", "job-fr", archived=True)
    await _flow("loop-fr-other", "job-fr-other", archived=False)
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-fr1", readable_id="FR-T1", project_id=PROJECT, title="A", loop_id="loop-fr"
            )
        )
        db.add(
            Task(
                id="task-fr2", readable_id="FR-T2", project_id=PROJECT, title="B", loop_id="loop-fr"
            )
        )
        db.add(Task(id="task-fr3", project_id=PROJECT, title="Elsewhere", loop_id="loop-fr-other"))
        db.add(_conversation("conv-fr1", "alpha", "job"))
        db.add(_conversation("conv-fr2", "beta", "job"))
        await db.commit()
    await _run("run-fr-a", "alpha", minutes_ago=30, task_id="task-fr1", conv="conv-fr1")
    await _run(
        "run-fr-b", "beta", minutes_ago=20, task_id="task-fr2", conv="conv-fr2", status="failed"
    )
    await _run("run-fr-other", "alpha", minutes_ago=10, task_id="task-fr3")

    rows = await _listed(app, auth_headers, loop_id="loop-fr")
    assert [(r["run_id"], r["agent"], r["task_ref"], r["run_status"]) for r in rows] == [
        ("run-fr-b", "beta", "FR-T2", "failed"),
        ("run-fr-a", "alpha", "FR-T1", "completed"),
    ]
    assert all(r["run_kind"] == "task" and r["conversation_id"] for r in rows)
    assert await _listed(app, auth_headers, loop_id="loop-none") == []


@pytest.mark.asyncio
async def test_a_flows_unbound_firing_is_among_its_runs(app, auth_headers):
    """D5: a run in a conversation the flow's firing opened is the flow's, task or not."""
    await _flow("loop-fu", "job-fu", archived=True)
    async with async_session_factory() as db:
        db.add(_conversation("conv-fu", "alpha", "job"))
        db.add(
            JobRun(
                id="jr-fu",
                job_id="job-fu",
                project_id=PROJECT,
                status="completed",
                conversation_id="conv-fu",
            )
        )
        await db.commit()
    await _run("run-fu", "alpha", minutes_ago=5, conv="conv-fu")
    await _run("run-fu-not", "alpha", minutes_ago=4)

    rows = await _listed(app, auth_headers, loop_id="loop-fu")
    assert [(r["run_id"], r["run_kind"]) for r in rows] == [("run-fu", "job")]


def test_run_kind_precedence():
    assert traces.run_kind("job", True, True) == "review"
    assert traces.run_kind("mender", True, False) == "mender"
    # A briefing on assignment writes an operator-origin conversation bound to a task.
    assert traces.run_kind("operator", True, False) == "task"
    assert traces.run_kind("spec", False, False) == "thread"
    assert traces.run_kind("handoff", False, False) == "message"
    assert traces.run_kind(None, False, False) == "message"
