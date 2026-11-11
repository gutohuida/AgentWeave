"""F1168: evidence acceptance cannot borrow a task to land unrelated work."""

import pytest
from sqlalchemy import select

from hub import landing_queue, task_integration
from hub.db.engine import async_session_factory
from hub.db.models import RequirementEvidence, Run, Task, TaskLanding

from .test_task_integration import (
    AGENT_EVIDENCE,
    BASE,
    builder,  # noqa: F401
    commit_on_branch,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


async def setup(app, auth_headers, run_headers, root):
    base = make_repo(root)
    await make_document(app, auth_headers, run_headers)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    async with async_session_factory() as session:
        (await session.get(Task, task)).status = "approved"
        await session.commit()
    return task, base


@pytest.mark.asyncio
async def test_message_signoff_has_no_git_footprint(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await setup(app, auth_headers, builder, tmp_path)
    commit_on_branch(tmp_path, "agentweave/builder", "README.md", "unreviewed\n")
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "operator agreed",
            "kind": "operator_signoff",
            "locator": "Operator message to Architect",
        },
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text
    footprint = recorded.json()["footprint"]
    assert footprint is None or not footprint.get("commit_sha")


@pytest.mark.asyncio
@pytest.mark.parametrize("recorder", [None, "own", "sibling"])
async def test_waiting_selection_belongs_only_to_recording_task(
    app, auth_headers, builder, tmp_path, recorder  # noqa: F811
):
    task, base = await setup(app, auth_headers, builder, tmp_path)
    sibling = await linked_task(app, auth_headers, title="Sibling")
    async with async_session_factory() as session:
        (await session.get(Task, sibling)).status = "approved"
        await session.commit()
    response = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "tests passed",
            "task_id": {None: None, "own": task, "sibling": sibling}[recorder],
        },
        headers=builder,
    )
    assert response.status_code == 201, response.text
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, response.json()["id"])
        waiting = await task_integration.tasks_awaiting_this_commit(session, evidence)
        assert [row.id for row in waiting] == ([] if recorder is None else [evidence.task_id])
        targets = await task_integration.integration_targets(session, await session.get(Task, task))
        # Still awaiting: explicitly accept here to exercise the target filter too.
        evidence.review_state = "accepted"
        await session.flush()
        targets = await task_integration.integration_targets(session, await session.get(Task, task))
        assert bool(targets) is (recorder == "own")


@pytest.mark.asyncio
async def test_failed_evidence_landing_does_not_reopen_landed_task(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, base = await setup(app, auth_headers, builder, tmp_path)
    # Its own branch is wholly on main; an old frozen landing names foreign work.
    git(tmp_path, "branch", f"agentweave/task/{task}", base)
    foreign = commit_on_branch(tmp_path, "agentweave/builder", "README.md", "foreign\n")
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        session.add(
            TaskLanding(
                id="land-old",
                project_id="proj-test",
                task_id=task,
                kind="evidence",
                order_key=1,
                targets=[{"commit_sha": foreign}],
            )
        )
        await session.commit()
    await landing_queue._send_back(
        "land-old", "batch-old", "conflict", "merge-needed", "foreign conflict"
    )
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "approved"
        assert (await session.get(TaskLanding, "land-old")).state == "not_landed"


@pytest.mark.asyncio
async def test_accepting_taskless_legacy_footprint_creates_no_landing(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, base = await setup(app, auth_headers, builder, tmp_path)
    commit_on_branch(tmp_path, "agentweave/builder", "README.md", "foreign\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "signoff"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    git(tmp_path, "checkout", "-q", "main")
    commit_on_branch(tmp_path, "main", "README.md", "main changed\n", create=False)
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    async with async_session_factory() as session:
        assert not (await session.execute(select(TaskLanding))).scalars().all()
        assert (await session.get(Task, task)).status == "approved"


@pytest.mark.asyncio
async def test_explicit_message_locator_is_never_a_merge_target(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, _ = await setup(app, auth_headers, builder, tmp_path)
    response = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "message",
            "task_id": task,
            "locator": "Operator message to Architect",
        },
        headers=builder,
    )
    assert response.status_code == 201, response.text
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, response.json()["id"])
        evidence.review_state = "accepted"
        await session.flush()
        assert await task_integration.tasks_awaiting_this_commit(session, evidence) == []
        assert (
            await task_integration.integration_targets(session, await session.get(Task, task)) == []
        )


@pytest.mark.asyncio
async def test_task_bound_evidence_cannot_merge_a_foreign_branch(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, base = await setup(app, auth_headers, builder, tmp_path)
    commit_on_branch(tmp_path, f"agentweave/task/{task}", "own.py", "own\n")
    git(tmp_path, "checkout", "-q", "main")
    commit_on_branch(tmp_path, "agentweave/builder", "foreign.py", "foreign\n")
    async with async_session_factory() as session:
        (await session.get(Run, "run-int")).workspace_dir = str(tmp_path)
        await session.commit()
    response = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "wrong checkout", "task_id": task},
        headers=builder,
    )
    assert response.status_code == 201, response.text
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, response.json()["id"])
        evidence.review_state = "accepted"
        await session.flush()
        assert (
            await task_integration.merge_targets(session, await session.get(Task, task), tmp_path)
            == []
        )
