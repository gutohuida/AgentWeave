"""F61 — a flow conversation says whose turn it is and which kind.

Every flow conversation was named after the job, so one project held eleven conversations titled
"Ledger flow" across three agents and two roles, and a review could not be told from the work it
reviewed without opening the database. The operator's chosen fix: title a flow conversation by its
agent and role. These fire the real scheduler and read the conversation the firing made.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Conversation, InboundQueueEntry, Task
from hub.scheduler import JobScheduler, job_conversation_title

from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import AUTHOR, REVIEWER, _attribute_completion, _flow
from .test_review_turn import _author_commit, _reviewable_task, _roster

pytestmark = pytest.mark.asyncio


async def _conversation_title_for(agent):
    async with async_session_factory() as db:
        entry = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .first()
        )
        assert entry is not None, f"no firing reached {agent}"
        # By column: `Conversation`'s primary key is not `id`, so `db.get` would miss it.
        return (
            await db.execute(
                select(Conversation.title).where(Conversation.id == entry.conversation_id)
            )
        ).scalar_one()


async def _fire(job_id):
    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job_id)
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)


async def test_a_review_turn_is_titled_as_the_reviewers_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, _loop = await _flow(db, suffix="review-title", task_id="task-1")

    await _fire(job.id)

    assert await _conversation_title_for(REVIEWER) == "critic · review: Balance the ledger"


async def test_a_work_turn_is_titled_as_the_authors_work(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="work-title")
        db.add(
            Task(
                id="task-work",
                project_id="proj-test",
                title="Balance the ledger",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()

    await _fire(job.id)

    assert await _conversation_title_for(AUTHOR) == "builder · work: Balance the ledger"


async def test_a_plain_job_is_still_titled_by_its_name(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "plain-agent")
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-plain-title",
                project_id="proj-test",
                name="Morning summary",
                agent="plain-agent",
                message="summarise yesterday",
                cron="0 9 * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()

    await _fire("job-plain-title")

    assert await _conversation_title_for("plain-agent") == "Morning summary"


def _task(title):
    return Task(id="task-x", project_id="proj-test", title=title, status="pending")


async def test_the_task_title_is_what_truncation_cuts():
    """The title is capped at 120 characters by `title_from_message`, which cuts at a word
    boundary. The agent and the role come first so a long task title is what gets shortened."""
    from hub.conversations import title_from_message

    title = job_conversation_title("Ledger flow", "critic", _task("word " * 60), True)
    assert title_from_message(title).startswith("critic · review: word")


async def test_no_task_means_the_job_name():
    assert job_conversation_title("Ledger flow", "builder", None, False) == "Ledger flow"


async def test_each_selection_of_a_wide_firing_is_titled_for_its_own_agent(
    app, auth_headers, bind_runner
):
    """The second selection onward goes through `_fire_additional_selection`, which names its
    conversation separately; both sites have to say whose turn it is."""
    from .test_flow_width import OWNER, SECOND
    from .test_flow_width import _flow as _wide_flow
    from .test_flow_width import _task as _wide_task

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _wide_flow(db, suffix="titles")
        await _wide_task(db, loop, "a")
        await _wide_task(db, loop, "b")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    titles = {await _conversation_title_for(OWNER), await _conversation_title_for(SECOND)}
    assert titles == {
        f"{OWNER} · work: work a",
        f"{SECOND} · work: work b",
    } or titles == {
        f"{OWNER} · work: work b",
        f"{SECOND} · work: work a",
    }
