"""Tests for task 3.5/3.6: unavailable project directories preserve state and pause execution.

Covers the requirement from
openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md
lines 117-136:

- New operator input is refused while the workspace is unavailable.
- Existing queued entries remain durable.
- Autonomous/scheduled starts pause (with an attributed event), not fail.
- Repair (relocate/open) re-evaluates queued work without disabling jobs.
"""

import shutil
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, Project, Question, Run


async def _sync_agent(app, auth_headers, agent_name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent_name: {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _active_run(run_id: str, agent: str) -> tuple[dict[str, str], str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}, token


def _fake_pty(lines, pid=4242):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = 0
    return MagicMock(return_value=session)


@pytest.mark.asyncio
async def test_trigger_is_refused_when_workspace_unavailable(
    app, auth_headers, bind_project_workspace, tmp_path
):
    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")
    shutil.rmtree(directory)

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        headers=auth_headers,
        json={"agent": "claude", "message": "hello"},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "code" in detail
    assert "message" in detail
    assert detail["directory_state"] == "missing"

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "claude")
                )
            )
            .scalars()
            .all()
        )
        assert entries == []


@pytest.mark.asyncio
async def test_message_is_refused_when_workspace_unavailable(
    app, auth_headers, bind_project_workspace, tmp_path
):
    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")
    shutil.rmtree(directory)

    response = await app.post(
        "/api/v1/projects/proj-test/messages",
        headers=auth_headers,
        json={
            "sender": "operator",
            "recipient": "claude",
            "subject": "test",
            "content": "hello",
        },
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["directory_state"] == "missing"

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "claude")
                )
            )
            .scalars()
            .all()
        )
        assert entries == []


@pytest.mark.asyncio
async def test_answering_question_is_refused_when_workspace_unavailable(
    app, auth_headers, bind_project_workspace, tmp_path
):
    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")

    async with async_session_factory() as session:
        question = Question(
            id="q-test-1",
            project_id="proj-test",
            from_agent="claude",
            question="What is the answer?",
        )
        session.add(question)
        await session.commit()

    shutil.rmtree(directory)

    response = await app.patch(
        "/api/v1/projects/proj-test/questions/q-test-1",
        headers=auth_headers,
        json={"answer": "42"},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["directory_state"] == "missing"

    async with async_session_factory() as session:
        question = await session.get(Question, "q-test-1")
        assert question.answered is False


@pytest.mark.asyncio
async def test_agent_to_agent_message_is_not_refused_but_stays_queued_when_workspace_unavailable(
    app, auth_headers, bind_project_workspace, tmp_path
):
    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "recipient")
    shutil.rmtree(directory)

    headers, _ = await _active_run("run-sender", "sender")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "recipient", "content": "hello"},
    )

    # Agent-to-agent continuation must not be refused; it is paused durably.
    assert response.status_code == 201, response.text

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "recipient")
                )
            )
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].state == "queued"


@pytest.mark.asyncio
async def test_queued_entry_survives_and_pause_is_attributed_when_workspace_becomes_unavailable(
    app, auth_headers, bind_project_workspace, bind_runner, tmp_path
):
    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")
    await bind_runner("claude", cli="claude")

    # Block scheduling deterministically by pretending claude is already running.
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-blocking",
                project_id="proj-test",
                agent="claude",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        headers=auth_headers,
        json={"agent": "claude", "message": "hello"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"

    # Now make the workspace unavailable and remove the blocker.
    shutil.rmtree(directory)
    async with async_session_factory() as session:
        run = await session.get(Run, "run-blocking")
        run.status = "completed"
        await session.commit()

    import hub.turn_scheduler as turn_scheduler

    scheduled = await turn_scheduler.schedule_agent("proj-test", "claude")
    assert scheduled.response is None

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "claude")
                )
            )
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].state == "queued"

        event = (
            await session.execute(
                select(EventLog).where(
                    EventLog.project_id == "proj-test",
                    EventLog.event_type == "queue_agent_paused",
                    EventLog.agent == "claude",
                )
            )
        ).scalar_one()
        assert event.severity == "warn"
        assert event.data["agent"] == "claude"
        assert event.data["directory_state"] == "missing"


@pytest.mark.asyncio
async def test_job_fire_pauses_without_failing_when_workspace_unavailable(
    app, auth_headers, bind_project_workspace, bind_runner, tmp_path
):
    from hub.db.models import AIJob, JobRun
    from hub.scheduler import JobScheduler

    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "job-claude")
    await bind_runner("job-claude", cli="claude")

    async with async_session_factory() as db:
        job = AIJob(
            id="job-sched-pause",
            project_id="proj-test",
            name="Pause Test Job",
            agent="job-claude",
            message="hello from a scheduled job",
            cron="0 9 * * *",
            enabled=True,
        )
        db.add(job)
        await db.commit()

    shutil.rmtree(directory)

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    # The fire must succeed at queuing; the spawn is paused, not a job failure.
    assert success is True

    async with async_session_factory() as db:
        job = await db.get(AIJob, "job-sched-pause")
        assert job.enabled is True

        job_run = (
            await db.execute(select(JobRun).where(JobRun.job_id == "job-sched-pause"))
        ).scalar_one()
        assert job_run.status == "fired"

        entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.agent == "job-claude")
            )
        ).scalar_one()
        assert entry.state == "queued"

        event = (
            await db.execute(
                select(EventLog).where(
                    EventLog.project_id == "proj-test",
                    EventLog.event_type == "queue_agent_paused",
                    EventLog.agent == "job-claude",
                )
            )
        ).scalar_one()
        assert event.severity == "warn"


@pytest.mark.asyncio
async def test_relocate_repairs_and_redrains_queued_work(
    app, auth_headers, bind_project_workspace, bind_runner, tmp_path
):
    import hub.api.v1.agent_trigger as agent_trigger

    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")
    await bind_runner("claude", cli="claude")

    # Queue an operator entry and block it with a synthetic running run.
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-blocking",
                project_id="proj-test",
                agent="claude",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        headers=auth_headers,
        json={"agent": "claude", "message": "hello"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"

    # Move the directory (preserving the marker) to simulate repair.
    new_directory = tmp_path / "relocated"
    shutil.move(str(directory), str(new_directory))

    async with async_session_factory() as session:
        run = await session.get(Run, "run-blocking")
        run.status = "completed"
        await session.commit()

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-1"}\n']
    )

    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        response = await app.post(
            "/api/v1/projects/proj-test/relocate",
            headers=auth_headers,
            json={"path": str(new_directory)},
        )

    assert response.status_code == 200, response.text
    assert response.json()["directory_state"] == "available"

    for task in list(agent_trigger._background_runs):
        await task

    async with async_session_factory() as session:
        runs = (
            (
                await session.execute(
                    select(Run).where(
                        Run.project_id == "proj-test",
                        Run.agent == "claude",
                        Run.id != "run-blocking",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(runs) == 1
        assert runs[0].status == "completed"

        project = await session.get(Project, "proj-test")
        assert project.working_directory == str(new_directory)
