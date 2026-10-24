"""A stalled project wakes the mender, who unblocks it (`a-stalled-project-wakes-a-doctor-that-unblocks-it`).

The night of 2026-10-22 on the operator's Hub, as unit seams: approved work whose merge is skipped
on a checkout holding someone else's uncommitted change is one stall, counted on every retry; it
wakes the mender once; and the mender lands a conflict's resolution with no review. The repository
helpers come from `test_task_integration.py`, which owns this area's fixtures.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import manager, stalls
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Conversation,
    InboundQueueEntry,
    Loop,
    ManagerJob,
    Run,
    Runner,
    Stall,
    Task,
    TaskTransition,
)

from .test_task_integration import (
    AGENT_BRANCH,
    TASKS,
    accept_evidence,
    approve,
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

RETRY = TASKS + "/{}/integrations/retry"
MENDER_LAND = "/api/v1/agent-actions/mender/tasks/{}/branch"
MENDER_STALLS = "/api/v1/agent-actions/mender/stalls"
STALLS = "/api/v1/projects/proj-test/stalls"
MANAGER = "/api/v1/projects/proj-test/manager/jobs/mender"


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-mend-b", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-mend-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_mend-builder"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_mend-builder"}


async def mender_on():
    """The Manager entry on, with a runner; the agent is made when a stall wakes it."""
    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-mend", project_id="proj-test", name="Haiku", cli="claude", model="haiku"
            )
        )
        session.add(
            ManagerJob(
                project_id="proj-test", job=manager.MENDER, enabled=True, runner_id="runner-mend"
            )
        )
        await session.commit()


async def mender_run():
    """A running turn of the Hub's own mender agent."""
    async with async_session_factory() as session:
        agent = (
            await session.execute(select(Agent).where(Agent.name == stalls.MENDER))
        ).scalar_one_or_none()
        if agent is None:
            session.add(
                Agent(
                    id="ag-mender",
                    project_id="proj-test",
                    name=stalls.MENDER,
                    config={"hub_role": stalls.HUB_ROLE},
                )
            )
        session.add(
            Run(
                id="run-mender",
                project_id="proj-test",
                agent=stalls.MENDER,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_mender"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_mender"}


async def all_stalls():
    async with async_session_factory() as session:
        return (await session.execute(select(Stall).order_by(Stall.first_seen_at))).scalars().all()


async def approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path):
    """The night's first half: approved work, and the operator's own edit in the checkout."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "README.md", "the task's line\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "notes.txt").write_text("tracked\n", encoding="utf-8")
    git(tmp_path, "add", "notes.txt")
    git(tmp_path, "commit", "-q", "-m", "notes")
    (tmp_path / "notes.txt").write_text("tracked\nthe operator's half-written thought\n")
    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    await stalls.drain()
    assert (await integrations(app, auth_headers, task))[0]["outcome"] == "skipped"
    return task, work


@pytest.mark.asyncio
async def test_a_skipped_merge_is_one_stall_however_often_it_is_retried(
    app, auth_headers, builder, tmp_path
):
    task, _ = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)

    for _ in range(2):
        assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
        await stalls.drain()

    rows = await all_stalls()
    assert [(row.cause, row.task_id, row.seen_count) for row in rows] == [
        ("integration_skipped", task, 3)
    ]
    assert "uncommitted" in rows[0].reason
    listed = (await app.get(STALLS, headers=auth_headers)).json()["stalls"]
    assert [s["key"] for s in listed] == [f"integration_skipped:{task}"]


@pytest.mark.asyncio
async def test_the_work_merging_ends_its_stall(app, auth_headers, builder, tmp_path):
    task, work = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    git(tmp_path, "commit", "-q", "-am", "the operator commits their notes")

    assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
    await stalls.drain()

    assert work in commits_on(tmp_path, "main")
    [row] = await all_stalls()
    assert (row.outcome, row.ended_at is not None) == ("resolved", True)


@pytest.mark.asyncio
async def test_a_stall_wakes_the_mender_once(app, auth_headers, builder, tmp_path):
    await mender_on()
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()) as scheduled:
        task, _ = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
        assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
        await stalls.drain()

    assert scheduled.await_count == 1
    async with async_session_factory() as session:
        mender = (
            await session.execute(select(Agent).where(Agent.name == stalls.MENDER))
        ).scalar_one()
        assert stalls.is_mender(mender) and mender.runner_id == "runner-mend"
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == stalls.MENDER)
                )
            )
            .scalars()
            .all()
        )
        [stall] = (await session.execute(select(Stall))).scalars().all()
        conversation = (
            await session.execute(
                select(Conversation).where(Conversation.id == stall.conversation_id)
            )
        ).scalar_one()
    assert [entry.origin_type for entry in entries] == ["mender"]
    brief = entries[0].content
    assert stall.id in brief and "uncommitted" in brief and "notes.txt" in brief
    assert "ask the operator first" in brief.lower()
    assert (conversation.origin, conversation.agent) == ("mender", stalls.MENDER)


@pytest.mark.asyncio
async def test_with_the_mender_off_a_stall_is_only_recorded(app, auth_headers, builder, tmp_path):
    await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    [row] = await all_stalls()
    assert row.conversation_id is None
    async with async_session_factory() as session:
        assert (
            await session.execute(select(Agent).where(Agent.name == stalls.MENDER))
        ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_project_agent_named_mender_is_never_taken_over(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-m2", project_id="proj-test", name="Haiku", cli="claude", model="haiku"
            )
        )
        session.add(Agent(id="ag-own-mender", project_id="proj-test", name="mender"))
        await session.commit()

    refused = await app.patch(
        MANAGER, json={"enabled": True, "runner_id": "runner-m2"}, headers=auth_headers
    )

    assert refused.status_code == 409, refused.text
    assert "already has its own agent named 'mender'" in refused.json()["detail"]
    jobs = (await app.get("/api/v1/projects/proj-test/manager/jobs", headers=auth_headers)).json()
    assert next(j for j in jobs["jobs"] if j["key"] == "mender")["enabled"] is False


@pytest.mark.asyncio
async def test_turning_the_mender_on_makes_its_agent(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-m3", project_id="proj-test", name="Haiku", cli="claude", model="haiku"
            )
        )
        await session.commit()

    turned = await app.patch(
        MANAGER, json={"enabled": True, "runner_id": "runner-m3"}, headers=auth_headers
    )

    assert turned.status_code == 200, turned.text
    async with async_session_factory() as session:
        agent = (
            await session.execute(select(Agent).where(Agent.name == stalls.MENDER))
        ).scalar_one()
    assert stalls.is_mender(agent) and agent.runner_id == "runner-m3"


@pytest.mark.asyncio
async def test_only_the_mender_may_use_its_actions(app, builder):
    refused = await app.get(MENDER_STALLS, headers=builder)
    assert refused.status_code == 403, refused.text


@pytest.mark.asyncio
async def test_the_mender_lands_a_conflicts_resolution_with_no_review(
    app, auth_headers, builder, tmp_path
):
    task, work = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    # The operator commits their notes, and main moves under the work meanwhile.
    git(tmp_path, "commit", "-q", "-am", "the operator commits their notes")
    (tmp_path / "README.md").write_text("main's own line\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-am", "someone else's change")
    assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
    await stalls.drain()
    newest = (await integrations(app, auth_headers, task))[-1]
    assert newest["outcome"] == "failed", newest["reason"]
    mender = await mender_run()

    # A commit that drops the task's work is refused.
    refused = await app.post(
        MENDER_LAND.format(task), json={"commit": commits_on(tmp_path, "main")[0]}, headers=mender
    )
    assert refused.status_code == 409, refused.text
    assert work[:12] in refused.json()["detail"]

    # The resolution: the work, with main merged in and the conflict resolved.
    git(tmp_path, "checkout", "-q", "-b", "mend/x", work)
    git(tmp_path, "merge", "-q", "main")
    (tmp_path / "README.md").write_text("the task's line\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-am", "mend: keep the task's line")
    resolution = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    git(tmp_path, "checkout", "-q", "main")
    transitions_before = await _transitions(task)

    landed = await app.post(MENDER_LAND.format(task), json={"commit": resolution}, headers=mender)
    await stalls.drain()

    assert landed.status_code == 200, landed.text
    assert [r["outcome"] for r in landed.json()["results"]] == ["merged"]
    assert resolution in commits_on(tmp_path, "main") and work in commits_on(tmp_path, "main")
    assert (tmp_path / "README.md").read_text() == "the task's line\n"
    newest = (await integrations(app, auth_headers, task))[-1]
    assert (newest["outcome"], newest["actor"]) == ("merged", "mender")
    assert await _transitions(task) == transitions_before, "no review was asked for"
    assert {(row.cause, row.outcome) for row in await all_stalls()} == {
        ("integration_skipped", "fixed"),
        ("integration_failed", "fixed"),
    }


async def _transitions(task_id):
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(TaskTransition.to_status).where(TaskTransition.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_the_mender_ends_its_stall(app, auth_headers, builder, tmp_path):
    await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    [row] = await all_stalls()
    mender = await mender_run()

    ended = await app.post(
        f"{MENDER_STALLS}/{row.id}/end",
        json={"outcome": "gave_up", "summary": "The checkout holds the operator's notes."},
        headers=mender,
    )

    assert ended.status_code == 200, ended.text
    assert (ended.json()["outcome"], ended.json()["outcome_detail"]) == (
        "gave_up",
        "The checkout holds the operator's notes.",
    )


def test_a_refused_delivery_is_told_from_an_unstaffed_review():
    refused = (
        "Developer holds task-d4 ('x'), and delivering its turn to them was refused: Could not "
        "prepare the checkout. No firing will retry it. Fix it, then withdraw that input."
    )
    assert stalls.classify_unstaffed(refused) == "delivery_refused"
    assert stalls.classify_unstaffed("no agent may review task-x") == "review_unstaffed"


@pytest.mark.asyncio
async def test_a_loop_with_open_work_and_no_progress_is_a_stall(app):
    now = datetime.now(timezone.utc)
    long_ago = now - timedelta(minutes=stalls.NO_PROGRESS_MINUTES + 5)
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-np",
                project_id="proj-test",
                name="Pull the thread",
                agent="builder",
                message="next",
                cron="*/5 * * * *",
                enabled=True,
                created_at=long_ago,
            )
        )
        session.add(
            Loop(id="loop-np", project_id="proj-test", job_id="job-np", created_at=long_ago)
        )
        session.add(
            Task(
                id="task-np",
                project_id="proj-test",
                title="still open",
                status="pending",
                loop_id="loop-np",
                created_at=long_ago,
                updated=long_ago,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 1
    await stalls.drain()
    [row] = await all_stalls()
    assert (row.cause, row.loop_id) == ("no_progress", "loop-np")
    assert "Pull the thread" in row.reason

    # Progress since ends it.
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-np",
                project_id="proj-test",
                agent="builder",
                status="completed",
                turn_depth=0,
                started_at=now,
            )
        )
        await session.commit()
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0
    [row] = await all_stalls()
    assert row.outcome == "resolved"


@pytest.mark.asyncio
async def test_a_new_cause_on_a_task_being_mended_joins_that_thread(
    app, auth_headers, builder, tmp_path
):
    """Found by the acceptance drive: the conflict seen while the mender mended the dirty-checkout
    skip queued a second brief, which would have started a turn after both stalls had ended."""
    await mender_on()
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()) as scheduled:
        task, _ = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
        git(tmp_path, "commit", "-q", "-am", "the operator commits their notes")
        (tmp_path / "README.md").write_text("main's own line\n", encoding="utf-8")
        git(tmp_path, "commit", "-q", "-am", "someone else's change")
        assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
        await stalls.drain()

    assert scheduled.await_count == 1
    rows = await all_stalls()
    assert [row.cause for row in rows] == ["integration_skipped", "integration_failed"]
    assert rows[0].conversation_id is not None
    assert rows[1].conversation_id == rows[0].conversation_id
    async with async_session_factory() as session:
        queued = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == stalls.MENDER)
                )
            )
            .scalars()
            .all()
        )
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_ending_a_stall_withdraws_a_brief_the_mender_never_read(
    app, auth_headers, builder, tmp_path
):
    await mender_on()
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()):
        await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    [row] = await all_stalls()

    ended = await app.post(f"{STALLS}/{row.id}/end", json={}, headers=auth_headers)

    assert ended.status_code == 200, ended.text
    async with async_session_factory() as session:
        [entry] = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == stalls.MENDER)
                )
            )
            .scalars()
            .all()
        )
    assert entry.state == "withdrawn"
    assert "ended resolved" in entry.abandoned_reason


# F1043: silence is not death. Every run over 10 minutes was reported dead because the sweep read
# a heartbeat column nothing writes; on :8000 all 9 runs it named had completed normally.


async def _running_run(run_id, started):
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                started_at=started,
            )
        )
        await session.commit()


@pytest.fixture
def executing():
    """Runs this Hub process is executing, as `run_liveness` holds them during a turn."""
    from hub import run_liveness

    added: list = []

    def add(run_id):
        run_liveness.active_app_server_runs.add(run_id)
        added.append(run_id)

    yield add
    for run_id in added:
        run_liveness.active_app_server_runs.discard(run_id)


@pytest.mark.asyncio
async def test_a_long_silent_run_this_hub_is_executing_is_not_dead(app, executing):
    now = datetime.now(timezone.utc)
    await _running_run("run-long", now - timedelta(minutes=30))
    executing("run-long")
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0
    await stalls.drain()
    assert await all_stalls() == []


@pytest.mark.asyncio
async def test_a_running_run_this_hub_is_not_executing_is_dead(app):
    now = datetime.now(timezone.utc)
    await _running_run("run-gone", now - timedelta(minutes=10))
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 1
    await stalls.drain()
    [row] = await all_stalls()
    assert (row.cause, row.key) == ("dead_run", "dead_run:run-gone")
    assert "not executing" in row.reason


@pytest.mark.asyncio
async def test_a_run_still_starting_is_not_judged(app):
    now = datetime.now(timezone.utc)
    await _running_run("run-new", now - timedelta(minutes=1))
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0


@pytest.mark.asyncio
async def test_a_dead_run_stall_ends_once_its_run_is_live_or_over(app, executing):
    now = datetime.now(timezone.utc)
    await _running_run("run-a", now - timedelta(minutes=10))
    await _running_run("run-b", now - timedelta(minutes=10))
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 2
    await stalls.drain()

    executing("run-a")
    async with async_session_factory() as session:
        run_b = await session.get(Run, "run-b")
        run_b.status = "completed"
        await session.commit()
    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0
    assert {row.key: row.outcome for row in await all_stalls()} == {
        "dead_run:run-a": "resolved",
        "dead_run:run-b": "resolved",
    }
