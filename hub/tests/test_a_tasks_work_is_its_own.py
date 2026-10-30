"""A task's checks and merges use its own work (`a-task-s-checks-and-merges-use-its-own-work-and-a-
live-run-is-never-reset`, FR-1..FR-4).

Read in the ledger of the flow spdoc-a7d41f10be14 on 2026-10-29: the F1083 task's completion check
targeted the acceptance-drive task's commit, because both served FR-7 and `merge_targets` joined
evidence by requirement; it reused that commit's pass, and two broken Hub tests went past the gate.
Its later completions ran no check at all, the stand-in commit having landed. And a task depending
only on the drive task was refused approval for lacking a third task's commit, because once that
task was approved its evidence counted as the drive task's work (F520's retired clause).

Real git repositories, real check subprocesses, and the real task, evidence and agent routes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import project_checks, task_integration, task_workspace, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task, TaskCheckRun, TaskTransition

from .test_checks_run_before_review import _configure, _lint, _slow
from .test_task_integration import (
    AGENT_EVIDENCE,
    BASE,
    TASKS,
    approve,
    builder,  # noqa: F401 - fixture
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

pytestmark = pytest.mark.asyncio

#: Captured at import, before `conftest` stubs it for every test (as `test_turn_workspace` does).
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree

AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
B_TOKEN = "aw_run_own-work-b"
B_HEADERS = {"Authorization": f"Bearer {B_TOKEN}"}
#: What the suite prints for the test B's commit breaks.
BROKEN_TEST = "tests/test_ledger.py::test_balance"


async def _record(app, run_headers, task_id, root=None, branch=None):
    """FR-1 evidence recorded for *task_id*, with *branch* checked out in the project root."""
    if branch is not None:
        git(root, "checkout", "-q", branch)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": f"{task_id}'s work", "task_id": task_id},
        headers=run_headers,
    )
    assert recorded.status_code == 201, recorded.text
    if branch is not None:
        git(root, "checkout", "-q", "main")
    return recorded.json()["id"]


async def _accept(app, auth_headers, evidence_id):
    decided = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text


async def _task_with_accepted_work(app, auth_headers, builder, root, title, filename):  # noqa: F811
    """A task serving FR-1 whose own branch holds one commit, demonstrated by accepted evidence it
    recorded. Returns `(task id, commit)`."""
    task_id = await linked_task(app, auth_headers, title=title)
    branch = worktrees.task_branch_name(task_id)
    commit = commit_on_branch(root, branch, filename, f"# {title}\n")
    git(root, "checkout", "-q", "main")
    await _accept(app, auth_headers, await _record(app, builder, task_id, root, branch))
    return task_id, commit


async def _set_status(task_id, status):
    """A status written directly: a task approved whose work has not landed, which the routes reach
    only through a landing that has not run yet."""
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = status
        await session.commit()


async def _runs(task_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskCheckRun)
                    .where(TaskCheckRun.task_id == task_id)
                    .order_by(TaskCheckRun.started_at)
                )
            ).scalars()
        )


async def _merge_targets(task_id, root):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        return [t.commit_sha for t in await task_integration.merge_targets(session, task, root)]


# ---------------------------------------------------------------------------------------------
# ac-shared-requirement-check, ac-recompletion-checked (FR-1, FR-2)
# ---------------------------------------------------------------------------------------------


async def _held_by_its_builder(task_id):
    """*task_id* in progress, held by the builder's running turn bound to it."""
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status, task.assignee = "in_progress", "builder"
        session.add(
            Run(
                id="run-own-work-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(B_TOKEN),
            )
        )
        await session.commit()


async def test_a_completion_is_checked_on_its_own_commit_not_a_siblings(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    # The drive task D: approved and landed, its accepted FR-1 evidence at its own commit d.
    drive, d = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "Drive", "d.py")
    assert (await approve(app, auth_headers, drive)).status_code == 200
    assert d in commits_on(tmp_path, "main")

    # The build task B serves FR-1 too; its commit breaks an existing test.
    build = await linked_task(app, auth_headers, title="Build")
    branch = worktrees.task_branch_name(build)
    b1 = commit_on_branch(tmp_path, branch, "broken.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    await _held_by_its_builder(build)
    # B's own FR-1 evidence, at b1, waiting for its review.
    await _record(app, B_HEADERS, build, tmp_path, branch)
    await _configure([_lint(tmp_path), _slow(tmp_path, fails_on="broken.py")])

    completed = await app.patch(
        AGENT_TASKS.format(build), json={"status": "completed"}, headers=B_HEADERS
    )
    assert completed.status_code == 200, completed.text
    await project_checks.drain()

    [run] = await _runs(build)
    assert b1 in run.target_shas and d not in run.target_shas, run.target_shas
    assert run.state == "failed"
    assert not any(r.get("reused_from") for r in run.results), "a pass was reused from D's run"
    assert any(BROKEN_TEST in (r.get("output_tail") or "") for r in run.results), run.results
    async with async_session_factory() as session:
        assert (await session.get(Task, build)).status == "revision_needed"

    # ac-recompletion-checked: sent back, with d on main, B completes again with a fix, its
    # evidence still naming b1: the check is on the commit completed, b2.
    git(tmp_path, "checkout", "-q", branch)
    git(tmp_path, "rm", "-q", "broken.py")
    git(tmp_path, "commit", "-q", "-m", "fix")
    b2 = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    git(tmp_path, "checkout", "-q", "main")
    resumed = await app.patch(
        AGENT_TASKS.format(build), json={"status": "in_progress"}, headers=B_HEADERS
    )
    assert resumed.status_code == 200, resumed.text

    again = await app.patch(
        AGENT_TASKS.format(build), json={"status": "completed"}, headers=B_HEADERS
    )
    assert again.status_code == 200, again.text
    await project_checks.drain()

    runs = await _runs(build)
    assert len(runs) == 2, [r.target_shas for r in runs]
    assert b2 in runs[-1].target_shas and runs[-1].state == "passed", runs[-1].results


async def test_a_completion_with_nothing_to_check_says_why_in_its_history(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """FR-2: a completion that records no check run says why on its history row."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    build = await linked_task(app, auth_headers, title="Build")
    commit_on_branch(tmp_path, worktrees.task_branch_name(build), "ok.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    await _held_by_its_builder(build)
    # No fast check configured: none can run at completion.
    await _configure([_slow(tmp_path)])

    completed = await app.patch(
        AGENT_TASKS.format(build), json={"status": "completed"}, headers=B_HEADERS
    )
    assert completed.status_code == 200, completed.text

    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == build, TaskTransition.to_status == "completed"
                )
            )
        ).scalar_one()
    assert row.note and "no check ran" in row.note.lower() and "fast" in row.note, row.note


# ---------------------------------------------------------------------------------------------
# ac-sibling-not-merged (FR-1)
# ---------------------------------------------------------------------------------------------


async def test_approving_a_task_merges_its_own_commit_not_an_approved_siblings(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    sibling, b = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "B", "b.py")
    await _set_status(sibling, "approved")  # approved; its own landing has not run
    task, a = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "A", "a.py")

    assert await _merge_targets(task, tmp_path) == [a]
    assert (await approve(app, auth_headers, task)).status_code == 200

    rows = await integrations(app, auth_headers, task)
    assert {row["commit_sha"] for row in rows} == {a}, rows
    assert a in commits_on(tmp_path, "main")
    assert b not in commits_on(tmp_path, "main"), "B's work landed through A's approval"


# ---------------------------------------------------------------------------------------------
# ac-no-third-party-merge (FR-3)
# ---------------------------------------------------------------------------------------------


async def _dependent(app, auth_headers, depends_on, title="C"):
    created = await app.post(
        TASKS,
        json={"title": title, "requirement_ids": ["FR-1"], "depends_on": [depends_on]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_a_dependent_is_never_asked_for_a_commit_of_a_task_it_does_not_depend_on(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    drive, d = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "D", "d.py")
    assert (await approve(app, auth_headers, drive)).status_code == 200
    dependent = await _dependent(app, auth_headers, drive)
    # C's branch is cut from main holding d, before B's work exists.
    c = commit_on_branch(tmp_path, worktrees.task_branch_name(dependent), "c.py", "# C\n")
    git(tmp_path, "checkout", "-q", "main")
    # B, which C does not depend on, serves FR-1 with D and is approved at b.
    sibling, b = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "B", "b.py")
    await _set_status(sibling, "approved")
    await _accept(
        app,
        auth_headers,
        await _record(app, builder, dependent, tmp_path, worktrees.task_branch_name(dependent)),
    )

    async with async_session_factory() as session:
        task = await session.get(Task, dependent)
        asked = await task_workspace.approved_prerequisite_commits(session, task, tmp_path)
    assert b not in {sha for _, sha in asked}, asked

    approved = await approve(app, auth_headers, dependent)
    assert approved.status_code == 200, approved.text
    assert c in commits_on(tmp_path, "main")
    log = git(tmp_path, "log", "--format=%H %s", worktrees.task_branch_name(dependent)).stdout
    assert b not in log and b[:12] not in log, log


# ---------------------------------------------------------------------------------------------
# ac-merge-label (FR-4)
# ---------------------------------------------------------------------------------------------


async def test_the_prerequisite_merge_names_the_commit_and_the_task_that_produced_it(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    # D is still being worked; its accepted evidence seeds a new dependent checkout (F159).
    drive, d = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "D", "d.py")
    await _set_status(drive, "in_progress")
    sibling, b = await _task_with_accepted_work(app, auth_headers, builder, tmp_path, "B", "b.py")
    await _set_status(sibling, "approved")
    dependent = await _dependent(app, auth_headers, drive)

    async with async_session_factory() as session:
        task = await session.get(Task, dependent)
        inputs = await task_workspace.resolve_turn_workspace_inputs(
            session, project_id="proj-test", repo_root=tmp_path, task=task
        )
    checkout = worktrees.ensure_task_worktree(
        tmp_path, dependent, inputs.base, inputs.prerequisites, inputs.approved
    )

    merges = git(checkout, "log", "--merges", "--format=%s", "HEAD").stdout.splitlines()
    assert len(merges) == 1, merges
    [message] = merges
    assert d[:12] in message and drive in message, message
    assert sibling not in message and b[:12] not in message, message
