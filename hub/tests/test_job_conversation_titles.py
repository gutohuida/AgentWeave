"""A thread a flow or a build starts names its agent, role and turn (FR-12, `flow-title-form`)."""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Task
from hub.scheduler import earlier_turns_on_task, job_conversation_title


def _task(title="Balance the ledger"):
    return Task(id="task-x", project_id="proj-test", title=title, status="pending")


def test_the_title_carries_agent_role_and_turn() -> None:
    assert (
        job_conversation_title("Ledger flow", "Developer", _task(), False, 2)
        == "Developer · work turn 2: Balance the ledger"
    )
    assert (
        job_conversation_title("Ledger flow", "QA", _task(), True, 1)
        == "QA · review turn 1: Balance the ledger"
    )


def test_no_task_keeps_the_job_name() -> None:
    assert job_conversation_title("Ledger flow", "Developer", None, False, 3) == "Ledger flow"


@pytest.mark.asyncio
async def test_a_rebuild_after_a_send_back_is_work_turn_two(app) -> None:
    """The count is per role: the first build and a review before it do not mix."""
    async with async_session_factory() as db:
        db.add(Task(id="task-x", project_id="proj-test", title="T", status="pending"))
        for i, (work, review) in enumerate([("task-x", None), (None, "task-x")]):
            db.add(
                InboundQueueEntry(
                    id=f"q-{i}",
                    project_id="proj-test",
                    agent="Developer",
                    origin_type="job",
                    content="c",
                    hop_depth=0,
                    conversation_id=f"conv-{i}",
                    task_id=work,
                    review_task_id=review,
                )
            )
        await db.commit()
    async with async_session_factory() as db:
        assert await earlier_turns_on_task(db, "task-x", False) == 1
        assert await earlier_turns_on_task(db, "task-x", True) == 1
        assert await earlier_turns_on_task(db, "task-none", False) == 0
        assert (await db.execute(select(InboundQueueEntry))).scalars().all()
