"""A run reviewing a task cannot record evidence for that task (F500).

Found by the first real slice drive: a flow's reviewer recorded its own evidence on the task it was
reviewing, which made the requirement's evidence no longer *all* rejected, lifted the block C1b put
on a rejected requirement, and let the same reviewer approve over the operator's rejection. A
reviewer judges the evidence the author recorded; evidence a reviewer records is evidence the
reviewer then approves.

The review binding is a delivered queue entry carrying `review_task_id`, which is where the product
records it (`run_task_binding.review_task_for_run`); the rows are written directly because the
predicate reads exactly those rows.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, Run

from .test_approval_refuses_unaccepted_evidence import record_evidence_for
from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    commit_on_branch,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f500-author", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-f500-author",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_f500author-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_f500author-secret"}


async def reviewing_run(task_id, *, review=True):
    """A second agent's live run, delivered an entry that asks it to review *task_id*."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f500-rev", project_id="proj-test", name="checker"))
        session.add(
            Run(
                id="run-f500-rev",
                project_id="proj-test",
                agent="checker",
                status="running",
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token("aw_run_f500rev-secret"),
            )
        )
        session.add(
            InboundQueueEntry(
                id="entry-f500-rev",
                project_id="proj-test",
                agent="checker",
                origin_type="job",
                content="Review the task.",
                hop_depth=0,
                state="delivered",
                delivered_in_run_id="run-f500-rev",
                review_task_id=task_id if review else None,
                task_id=None if review else task_id,
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_f500rev-secret"}


@pytest.mark.asyncio
async def test_a_reviewer_recording_evidence_on_the_task_it_reviews_is_refused(
    app, auth_headers, author, tmp_path
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, author)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await record_evidence_for(app, author, "FR-1", task_id=task)
    git(tmp_path, "checkout", "-q", "main")

    checker = await reviewing_run(task)
    for body in (
        {"identifier": "FR-1", "summary": "I ran it too"},
        {"identifier": "FR-1", "summary": "named", "task_id": task},
    ):
        refused = await app.post(AGENT_EVIDENCE, json=body, headers=checker)
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["code"] == "reviewer_records_evidence", detail
        assert task in detail["message"]
        assert "revision_needed" in detail["message"]


@pytest.mark.asyncio
async def test_a_run_working_the_task_still_records_evidence(app, auth_headers, author, tmp_path):
    """The scoping constraint: only a *review* binding refuses. The same agent working the task
    (a `task_id` entry, not a `review_task_id` one) records evidence as before."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, author)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)

    worker = await reviewing_run(task, review=False)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=worker
    )
    git(tmp_path, "checkout", "-q", "main")
    assert recorded.status_code == 201, recorded.text
