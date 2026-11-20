"""Which threads are the operator's (profiles-threads-and-builds-everywhere, FR-1, FR-2, D1).

The sidebar lists the operator's threads and nothing else, read from
`GET /conversations?operator_threads=true`. A thread is the operator's when the operator wrote in
it, or it was cut over at a checkpoint from one that is — never because of `Conversation.origin`,
which defaults to "operator" and is what a task's own start records.

Every conversation here is made by the Hub's own path for it: a flow firing a work turn and a
review turn, a task outside a flow starting on assignment, a stall waking the mender, a scheduled
job firing, an agent's peer message, the operator's composer, and a checkpoint cutover. Turns are
held at `schedule_accepted`, so the queue entries those paths write stay as written.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import assigned_task_start, stalls
from hub.checkpoint_cutover import cut_over
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Conversation, InboundQueueEntry, Run, Task
from hub.inbound_queue import deliver_entries_with_run
from hub.scheduler import JobScheduler
from hub.turn_scheduler import ScheduleResult

from .test_a_stalled_project_wakes_the_mender import mender_on
from .test_agent_trigger import _init_repo
from .test_checkpoint_cutover import _ready_checkpoint
from .test_conversation_reply import _active_run, _send
from .test_flow_fires_a_review_turn import AUTHOR, REVIEWER, _attribute_completion, _flow
from .test_review_turn import _author_commit, _reviewable_task, _roster

pytestmark = pytest.mark.asyncio

CONVERSATIONS = "/api/v1/projects/proj-test/conversations"
TRIGGER = "/api/v1/projects/proj-test/agent/trigger"
OPERATOR_PROFILE = "Architect"
JOB_AGENT = "plain-agent"
TASK_AGENT = "assignee"


@pytest.fixture
def turns_held():
    """No turn starts: every path's queue entry stays exactly as that path wrote it."""
    held = ScheduleResult(waiting_reason="held for this test", terminal_failure=False)
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock(return_value=held)):
        yield


async def _fire(job_id):
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            job = await db.get(AIJob, job_id)
            await JobScheduler()._fire_job_internal(job, trigger="scheduled", session=db)


async def _conversation_of_entry(agent=None, **where):
    async with async_session_factory() as db:
        query = select(InboundQueueEntry.conversation_id)
        if agent:
            query = query.where(InboundQueueEntry.agent == agent)
        for column, value in where.items():
            query = query.where(getattr(InboundQueueEntry, column) == value)
        conversation_id = (await db.execute(query)).scalars().first()
    assert conversation_id, f"no entry reached {agent} with {where}"
    return conversation_id


async def _threads(app, auth_headers, **params):
    response = await app.get(
        CONVERSATIONS, params={"operator_threads": "true", **params}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _operator_writes(app, auth_headers, agent, message, conversation_id=None):
    body = {"agent": agent, "message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = await app.post(TRIGGER, json=body, headers=auth_headers)
    assert response.status_code in (200, 202), response.text
    return response.json()["conversation_id"]


async def _the_hubs_own_conversations(app, auth_headers, bind_runner, repo):
    """One of each conversation the operator neither started nor wrote in, by the Hub's paths."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, JOB_AGENT, TASK_AGENT)
    made = {}

    # A flow's review turn on finished work, and a flow's work turn on a task of its queue.
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        review_job, _ = await _flow(db, suffix="review", task_id="task-1")
        work_job, work_loop = await _flow(db, suffix="work")
        db.add(
            Task(
                id="task-work",
                project_id="proj-test",
                title="Balance the ledger",
                status="pending",
                loop_id=work_loop.id,
            )
        )
        await db.commit()
    await _fire(review_job.id)
    made["review"] = await _conversation_of_entry(review_task_id="task-1")
    await _fire(work_job.id)
    made["flow work"] = await _conversation_of_entry(AUTHOR, task_id="task-work")

    # A task outside any flow, started on assignment: its conversation keeps the column's default
    # origin and its briefing is an `origin_type="operator"` entry naming the task.
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-assigned",
                project_id="proj-test",
                title="Tidy the importer",
                status="assigned",
                assignee=TASK_AGENT,
            )
        )
        await db.commit()
    assert await assigned_task_start.start("task-assigned")
    made["task start"] = await _conversation_of_entry(TASK_AGENT, task_id="task-assigned")

    # A stall waking the mender.
    await mender_on()
    async with async_session_factory() as db:
        stall, _ = await stalls.record(
            db, "proj-test", cause="integration_skipped", subject="task-1", text="merge skipped"
        )
        assert await stalls.wake(db, stall)
        made["mender"] = stall.conversation_id

    # A scheduled job firing.
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-plain",
                project_id="proj-test",
                name="Morning summary",
                agent=JOB_AGENT,
                message="summarise yesterday",
                cron="0 9 * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()
    await _fire("job-plain")
    made["job firing"] = await _conversation_of_entry(JOB_AGENT, origin_type="job")

    # An agent's peer message.
    headers = await _active_run("run-peer", AUTHOR)
    sent = await _send(app, headers, REVIEWER, "Can you look at the ledger?")
    assert sent.status_code in (200, 201), sent.text
    made["peer message"] = await _conversation_of_entry(REVIEWER, origin_type="agent")

    async with async_session_factory() as db:
        origins = {
            kind: (await get_conversation_by_id(db, conversation_id)).origin
            for kind, conversation_id in made.items()
        }
    # The trap the decision exists for: origin says "operator" where the operator wrote nothing.
    assert origins["task start"] == "operator"
    assert len(set(made.values())) == len(made), made
    return made


@pytest.mark.usefixtures("turns_held")
async def test_leaves_out_until_written(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """leaves-out-until-written: nothing the operator did not write in is listed; once they write
    in the job firing, it is, and the others still are not."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    made = await _the_hubs_own_conversations(app, auth_headers, bind_runner, repo)

    assert (await _threads(app, auth_headers))["conversations"] == []

    written = await _operator_writes(
        app, auth_headers, JOB_AGENT, "What did you find?", conversation_id=made["job firing"]
    )
    assert written == made["job firing"]

    listed = (await _threads(app, auth_headers))["conversations"]
    assert [row["id"] for row in listed] == [made["job firing"]]
    assert listed[0]["operator_thread"] is True
    assert listed[0]["agent"] == JOB_AGENT

    # Without the parameter the route lists everything, as before, and says which is which.
    everything = (await app.get(CONVERSATIONS, headers=auth_headers)).json()["conversations"]
    flags = {row["id"]: row["operator_thread"] for row in everything}
    assert set(made.values()) <= set(flags)
    assert {cid for cid, flag in flags.items() if flag} == {made["job firing"]}


@pytest.mark.usefixtures("turns_held")
async def test_threads_cut_over_kept(app, auth_headers, bind_runner):
    """threads-cut-over-kept: a successor with no operator message is listed through its
    predecessor; the archived predecessor is the operator's too, under Show archived."""
    await _roster(app, auth_headers, bind_runner, OPERATOR_PROFILE)
    predecessor_id = await _operator_writes(app, auth_headers, OPERATOR_PROFILE, "Plan the sidebar")

    async with async_session_factory() as db:
        # The turn that took the operator's message, as the scheduler delivers it.
        entry_id = (
            await db.execute(
                select(InboundQueueEntry.id).where(
                    InboundQueueEntry.conversation_id == predecessor_id
                )
            )
        ).scalar_one()
        run = Run(
            id="run-took-it",
            project_id="proj-test",
            agent=OPERATOR_PROFILE,
            status="running",
            turn_depth=0,
            conversation_id=predecessor_id,
        )
        await deliver_entries_with_run(
            db, project_id="proj-test", agent=OPERATOR_PROFILE, entry_ids=[entry_id], run=run
        )
        run.status = "completed"
        await db.commit()
        predecessor = await get_conversation_by_id(db, predecessor_id)
        checkpoint = await _ready_checkpoint(db, predecessor)
        successor, _ = await cut_over(db, predecessor, checkpoint)
        successor_id = successor.id
        written = (
            await db.execute(
                select(InboundQueueEntry.origin_type).where(
                    InboundQueueEntry.conversation_id == successor_id
                )
            )
        ).scalars()
        assert list(written) == ["checkpoint"]

    listed = await _threads(app, auth_headers)
    assert [row["id"] for row in listed["conversations"]] == [successor_id]
    assert listed["conversations"][0]["operator_thread"] is True
    assert listed["archived_count"] == 1

    archived = await _threads(app, auth_headers, lifecycle="archived")
    assert [row["id"] for row in archived["conversations"]] == [predecessor_id]


@pytest.mark.usefixtures("turns_held")
async def test_a_successor_of_a_thread_the_operator_never_wrote_in_is_not_theirs(
    app, auth_headers, bind_runner
):
    """The chain is followed forward only: a job firing cut over stays out, as its predecessor
    does."""
    await _roster(app, auth_headers, bind_runner, JOB_AGENT)
    async with async_session_factory() as db:
        firing = Conversation(
            id="conv-firing",
            project_id="proj-test",
            agent=JOB_AGENT,
            lifecycle="open",
            origin="job",
            lineage_id="conv-firing",
        )
        db.add(firing)
        await db.commit()
        checkpoint = await _ready_checkpoint(db, firing)
        await cut_over(db, firing, checkpoint)

    assert (await _threads(app, auth_headers))["conversations"] == []
    assert (await _threads(app, auth_headers, lifecycle="all"))["conversations"] == []


@pytest.mark.usefixtures("turns_held")
async def test_threads_are_ordered_by_their_last_activity(app, auth_headers, bind_runner):
    """Newest message or run first, and `last_activity_at` says when that was. A run in the older
    thread moves it above the newer one; renaming a thread (which moves `updated_at`) does not."""
    await _roster(app, auth_headers, bind_runner, OPERATOR_PROFILE, JOB_AGENT)
    first = await _operator_writes(app, auth_headers, OPERATOR_PROFILE, "First thread")
    second = await _operator_writes(app, auth_headers, JOB_AGENT, "Second thread")

    listed = (await _threads(app, auth_headers))["conversations"]
    assert [row["id"] for row in listed] == [second, first]
    assert all(row["last_activity_at"] for row in listed)

    await _active_run("run-in-first", OPERATOR_PROFILE, conversation_id=first)
    renamed = await app.patch(
        f"/api/v1/projects/proj-test/agent/{JOB_AGENT}/conversations/{second}",
        json={"title": "Renamed"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text

    listed = (await _threads(app, auth_headers))["conversations"]
    assert [row["id"] for row in listed] == [first, second]
    assert listed[0]["last_activity_at"] > listed[1]["last_activity_at"]
