"""FR-10 and FR-11 of `every-task-can-always-be-moved-on`: landing says what it waits for.

The 2026-10-26 sequence, replayed in a git fixture: a task linked to FR-1 of its document, the
document then gains FR-2, and evidence for FR-2 is recorded on that task from its checkout at a later
commit and accepted. Landing used to be refused as 'commits on neither master nor inside any commit
the accepted evidence names', because only evidence for *linked* requirements counted.
"""

import json

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    ALPHA,
    BASE,
    PATH,
    SUBMIT,
    TASKS,
    approve,
    commit_on_branch,
    commits_on,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-int", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-int",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_int-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_int-secret"}


BETA = {"key": "beta", "statement": "It lists what is overdue", "modal": "MUST"}


async def add_requirement(app, run_headers):
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Integration demo",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def record(app, run_headers, identifier, task_id):
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": identifier, "summary": "ran it", "task_id": task_id},
        headers=run_headers,
    )
    assert recorded.status_code == 201, recorded.text
    return recorded.json()["id"]


async def decide(app, auth_headers, evidence_id, decision="accepted"):
    decided = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": decision, "reason": "checked"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text


async def linked_identifiers(app, auth_headers, task_id):
    shown = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    return sorted(item["identifier"] for item in shown.json()["requirement_links"])


@pytest.mark.asyncio
async def test_evidence_for_a_requirement_the_document_gained_merges_with_the_task(
    app, auth_headers, builder, tmp_path
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    assert await linked_identifiers(app, auth_headers, task) == ["FR-1"]

    first = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    await decide(app, auth_headers, await record(app, builder, "FR-1", task))

    await add_requirement(app, builder)
    later = commit_on_branch(tmp_path, AGENT_BRANCH, "two.py", "2\n", create=False)
    await decide(app, auth_headers, await record(app, builder, "FR-2", task))
    git(tmp_path, "checkout", "-q", "main")

    landed = await approve(app, auth_headers, task)
    assert landed.status_code == 200, landed.text
    assert first in commits_on(tmp_path, "main")
    assert later in commits_on(tmp_path, "main")
    assert await linked_identifiers(app, auth_headers, task) == ["FR-1", "FR-2"]


@pytest.mark.asyncio
async def test_accepted_evidence_for_an_unlinked_requirement_is_refused_with_the_link_as_remedy(
    app, auth_headers, builder, tmp_path
):
    """Evidence recorded before link-on-record: the refusal names the missing link, not new evidence."""
    from sqlalchemy import delete

    from hub.db.models import SpecRequirement, TaskRequirementLink

    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    branch = worktrees.task_branch_name(task)
    commit_on_branch(tmp_path, branch, "one.py", "1\n")
    await decide(app, auth_headers, await record(app, builder, "FR-1", task))
    await add_requirement(app, builder)
    later = commit_on_branch(tmp_path, branch, "two.py", "2\n", create=False)
    await decide(app, auth_headers, await record(app, builder, "FR-2", task))
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        beta = (
            await session.execute(
                select(SpecRequirement).where(SpecRequirement.identifier == "FR-2")
            )
        ).scalar_one()
        await session.execute(
            delete(TaskRequirementLink).where(
                TaskRequirementLink.task_id == task, TaskRequirementLink.requirement_id == beta.id
            )
        )
        await session.commit()

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert [(e["identifier"], e["commit_sha"]) for e in body["unlinked"]] == [("FR-2", later)]
    assert "Link the requirement to the task" in body["message"]
    assert "Ask the task's author to record it" not in body["message"]
    assert later not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_refusal_for_evidence_awaiting_a_decision_names_it_and_accepting_it_lands(
    app, auth_headers, builder, tmp_path
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    evidence_id = await record(app, builder, "FR-1", None)
    git(tmp_path, "checkout", "-q", "main")

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    waiting = refused.json()["detail"]["unaccepted"]
    assert [(e["evidence_id"], e["identifier"], e["commit_sha"]) for e in waiting] == [
        (evidence_id, "FR-1", work)
    ]

    await decide(app, auth_headers, evidence_id)
    landed = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert landed.status_code == 200, landed.text
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_decided_check_run_announces_itself_naming_the_task(app, auth_headers):
    """FR-12: the operator's app is told when a task's checks finish, so it can notify."""
    from datetime import datetime, timezone

    from hub import project_checks
    from hub.db.models import Task, TaskCheckRun
    from hub.sse import sse_manager

    async with async_session_factory() as session:
        session.add(
            Task(id="task-chk", project_id="proj-test", title="Landing page", status="completed")
        )
        session.add(
            TaskCheckRun(
                id="chk-1",
                project_id="proj-test",
                task_id="task-chk",
                main_sha="a" * 40,
                target_shas=[],
                state="running",
                results=[],
                started_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    queue = sse_manager.subscribe("proj-test")
    try:
        await project_checks._finish("chk-1", state="passed", results=[])
        event = queue.get_nowait()
    finally:
        sse_manager.unsubscribe("proj-test", queue)
    assert event.event == "task_checks_finished"
    assert json.loads(event.data) == {
        "task_id": "task-chk",
        "task_title": "Landing page",
        "state": "passed",
    }
