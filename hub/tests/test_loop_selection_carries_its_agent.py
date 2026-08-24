"""`loop-becomes-a-flow` group 2 — the agent becomes a per-selection value.

Design D2: `AIJob.agent` stops being the mandate and becomes *the agent this job fires when nothing
says otherwise*. The column stays `NOT NULL`; nothing is dropped. Group 4 is what will eventually
put a different agent in a selection (a resolved reviewer); this group only makes the firing able
to carry one, with the job's own agent as the default.

Because the default *is* `AIJob.agent`, a loop with no document must behave exactly as it does
today — that is D2's own statement of the regression bar, and 2.1 is it. 2.2 is the other half:
when a selection does name a different agent, every identity the firing produces must follow it,
not the job. A run attributed to the job's agent while the work was done by another is a lie the
whole flow would be built on — and it is not one thing to fix but four, because agent identity
reaches the run, the conversation, the queue entry and the run credential separately.

The credential is covered by asserting `Run.agent`: `agent_auth` derives its `AgentActor` from the
run row (`agent_auth.py:80`), so there is no fifth place for identity to diverge.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Conversation, InboundQueueEntry, Loop, Run, Task
from hub.scheduler import JobScheduler, LoopSelection, _select_for_firing

pytestmark = pytest.mark.asyncio


async def _make_job(db, *, suffix, agent):
    job = AIJob(
        id=f"job-sel-{suffix}",
        project_id="proj-test",
        name=f"Selection {suffix}",
        agent=agent,
        message="hello from a scheduled job",
        cron="0 9 * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    return job


async def _make_loop(db, *, job_id, **fields):
    loop = Loop(id=f"loop-sel-{job_id}", project_id="proj-test", job_id=job_id, **fields)
    db.add(loop)
    await db.commit()
    return loop


async def _make_task(db, task_id, *, status, loop_id):
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=task_id,
        status=status,
        loop_id=loop_id,
    )
    db.add(task)
    await db.flush()
    return task


def _fake_pty():
    """A spawn mock whose `.pid` is a real int.

    A bare `MagicMock()` binds a `MagicMock` into `runs.pid` and SQLite raises
    `type 'MagicMock' is not supported` — recorded as a dead end in handoff 0079 after it cost a
    session time.
    """
    session = MagicMock()
    session.pid = 4242
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-sel-1"}\n',
        "",
    ]
    session.wait.return_value = 0
    return session


# ---------------------------------------------------------------------------
# 2.1 — the default, which is the regression bar
# ---------------------------------------------------------------------------


async def test_a_loop_with_no_document_selects_the_jobs_own_agent(app):
    """D2's default. A loop that declares no document has nothing to say about who works its
    queue, so every selection carries `AIJob.agent` — on this firing and on any other."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="default", agent="loop-owner")
        loop = await _make_loop(db, job_id=job.id, purpose="no document here")
        await _make_task(db, "task-sel-default", status="pending", loop_id=loop.id)
        await db.commit()
        assert loop.spec_document_id is None

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        selections = await _select_for_firing(db, fresh_loop, default_agent=fresh_job.agent)

    assert [(s.task.id, s.agent) for s in selections] == [("task-sel-default", "loop-owner")]


async def test_an_empty_queue_selects_nothing_and_still_carries_no_agent(app):
    """The empty case survives the shape change: no selections, not a selection with no task."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="empty", agent="loop-owner")
        await _make_loop(db, job_id=job.id, purpose="empty")

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert await _select_for_firing(db, fresh_loop, default_agent="loop-owner") == []


# ---------------------------------------------------------------------------
# 2.2 — a selection that names a different agent is followed by every identity
# ---------------------------------------------------------------------------


async def test_a_selection_naming_another_agent_is_who_actually_gets_fired(
    app, auth_headers, bind_runner
):
    """The whole point of group 2, asserted end to end through a real firing.

    The job's agent is `job-owner`; the selection names `other-agent`. Every identity the firing
    produces must say `other-agent` — the run (and therefore the run credential), the conversation
    the turn happens in, and the queue entry the briefing is delivered on. Any one of them still
    reading `job.agent` is a place the flow would later attribute a reviewer's work to the author.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    "job-owner": {"runner": "claude"},
                    "other-agent": {"runner": "claude"},
                }
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("job-owner", cli="claude")
    await bind_runner("other-agent", cli="claude")

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="other", agent="job-owner")
        loop = await _make_loop(db, job_id=job.id, purpose="staffed by someone else")
        await _make_task(db, "task-sel-other", status="pending", loop_id=loop.id)
        await db.commit()

    async def _selection_naming_other(session, loop_row, *, default_agent):
        task = (await session.execute(select(Task).where(Task.id == "task-sel-other"))).scalar_one()
        return [LoopSelection(task=task, agent="other-agent")]

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=_fake_pty())
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.scheduler._select_for_firing", _selection_naming_other):
                scheduler = JobScheduler()
                async with async_session_factory() as db:
                    fresh_job = await db.get(AIJob, job.id)
                    fired = await scheduler._fire_job_internal(
                        fresh_job, trigger="scheduled", session=db
                    )
                for task in list(agent_trigger._background_runs):
                    await task

    assert fired is True

    async with async_session_factory() as db:
        runs = (await db.execute(select(Run).where(Run.project_id == "proj-test"))).scalars().all()
        fired_runs = [r for r in runs if r.agent in ("job-owner", "other-agent")]
        assert [r.agent for r in fired_runs] == ["other-agent"], (
            "the run — and therefore the run credential, which agent_auth derives from it — must "
            "attribute to the selection's agent"
        )

        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.project_id == "proj-test")
                )
            )
            .scalars()
            .all()
        )
        assert [e.agent for e in entries] == ["other-agent"]

        conversations = (
            (await db.execute(select(Conversation).where(Conversation.project_id == "proj-test")))
            .scalars()
            .all()
        )
        assert [c.agent for c in conversations] == ["other-agent"]

        # And the task is assigned to whoever was actually fired for it, not to the job's agent.
        task = (await db.execute(select(Task).where(Task.id == "task-sel-other"))).scalar_one()
        assert task.assignee == "other-agent"
