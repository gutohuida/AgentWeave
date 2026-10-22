"""F835: work the main line just received re-tries what was refused for want of it.

A dependent task's turn refused because its prerequisite's merge could not be brought in stays
`queued`; `redrain_queued_agents` ran only at a run's end, project open and settings changes, so
the prerequisite landing later (Try again, Land, approve) never delivered the waiting work and the
screen kept saying the merge was frozen. A successful integration now re-drains the project's queue
once its transaction commits; a skipped or failed one does not.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, TaskDependency

# Imported here, at collection, deliberately: conftest stubs `worktrees.ensure_task_worktree` and
# `resolve_agent_workspace` for every test, so a module first imported inside a test would capture
# the stubs and the "real" provisioning below would silently be the stub.
from .test_a_conflicting_prerequisite_is_the_authors_to_merge import (
    _REAL_ENSURE_TASK_WORKTREE,
    _RESULT,
    _builder,
    _turn,
)
from .test_agent_trigger import _await_background_run, _fake_pty
from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
from .test_task_integration import (  # noqa: F401  (builder is a fixture)
    AGENT_BRANCH,
    TASKS,
    accept_evidence,
    approve,
    builder,
    commit_on_branch,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace


@pytest.mark.asyncio
async def test_an_approval_that_merges_redrains_the_queue(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers)

    with patch("hub.turn_scheduler.redrain_queued_agents", new=AsyncMock()) as redrain:
        approved = await approve(app, auth_headers, task)
        assert approved.status_code == 200, approved.text
        assert approved.json()["latest_integration"]["outcome"] == "merged"
        # The re-drain is scheduled after the commit on the loop; let it run.
        await asyncio.sleep(0)
    redrain.assert_awaited_once_with("proj-test")


@pytest.mark.asyncio
async def test_a_retry_that_merges_redrains_the_queue(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """The repro's path: the merge failed (no main branch yet), the operator fixes it and presses
    Try again."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers)

    with patch("hub.turn_scheduler.redrain_queued_agents", new=AsyncMock()) as redrain:
        approved = await approve(app, auth_headers, task)
        assert approved.status_code == 200, approved.text
        assert approved.json()["latest_integration"]["outcome"] == "skipped"
        await asyncio.sleep(0)
        redrain.assert_not_awaited()

        await set_main_branch("main")
        retried = await app.post(f"{TASKS}/{task}/integrations/retry", headers=auth_headers)
        assert retried.status_code == 200, retried.text
        await asyncio.sleep(0)
    redrain.assert_awaited_once_with("proj-test")


@pytest.mark.asyncio
async def test_a_dependent_refused_for_a_frozen_merge_is_delivered_when_the_prerequisite_lands(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    """The finding's own repro, with nothing mocked but the runner process: a hook freezes merges,
    the prerequisite's approval records a retryable failure, the dependent's turn is refused for
    the same hook and queued; the hook goes, the operator presses Try again on the prerequisite,
    and the dependent's turn is delivered with no other call."""
    make_repo(tmp_path)
    await set_main_branch("main")
    await _builder(app, auth_headers, bind_runner)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    loop = await make_loop(app, auth_headers, name="F835 loop")
    prerequisite = await loop_task(app, auth_headers, loop, title="A")
    dependent = await loop_task(app, auth_headers, loop, title="B")
    async with async_session_factory() as session:
        session.add(
            TaskDependency(
                id="dep-f835",
                project_id="proj-test",
                task_id=dependent,
                depends_on_task_id=prerequisite,
            )
        )
        await session.commit()
    # Dispatched (which stamps its per-task scheme) but with no checkout yet: the turn cuts it, so
    # the refusal is the creation path's (`_merge_prerequisites`).
    started = await drive_to(app, auth_headers, dependent, "assigned")
    assert started.status_code == 200, started.text
    worktrees.seed_repo_excludes(tmp_path)
    a_commit = commit_on_task_branch(tmp_path, prerequisite, "a.txt", "from A\n")
    git(tmp_path, "checkout", "-q", "main")

    hook = tmp_path / ".git" / "hooks" / "pre-merge-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\necho 'policy: merges are frozen (hook)'\nexit 1\n", newline="\n")
    hook.chmod(0o755)

    landed = await approve(app, auth_headers, prerequisite)
    assert landed.status_code == 200, landed.text
    assert landed.json()["latest_integration"]["outcome"] == "failed"

    response, prompt = await _turn(app, auth_headers, dependent, "carry on with B")
    assert prompt is None, "the turn must be refused while the merge is frozen"
    assert response.json()["status"] == "queued", response.text
    assert "could not be merged into its base" in response.json()["waiting_reason"]

    hook.unlink()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:
        spawn.side_effect = _fake_pty([_RESULT])
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            retried = await app.post(
                f"{TASKS}/{prerequisite}/integrations/retry", headers=auth_headers
            )
            assert retried.status_code == 200, retried.text
            # Delivery runs in the background, after the route returned; git is slow on Windows.
            for _ in range(100):
                if spawn.called:
                    break
                await asyncio.sleep(0.1)
        assert spawn.called, "the dependent's turn was never delivered"
        await _await_background_run()

    assert a_commit in git(tmp_path, "log", "main", "--format=%H").stdout.split()
    async with async_session_factory() as session:
        queued = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.state == "queued",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert queued == []
