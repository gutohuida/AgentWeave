"""F695: a prerequisite whose approved work conflicts with a dependent task's checkout is the
dependent task's author's to merge, in its own turn.

Before this, `worktrees._catch_up_prerequisites` refused the turn on such a conflict, and the refusal
told somebody to run `git merge --no-ff` in the checkout -- but the author, the one party whose work
it is to reconcile, never got a turn to do it in; only the operator, in a terminal, could. Now the
merge is abandoned (the checkout left clean), the turn starts, and its prompt carries the merge
instruction naming the prerequisite task, its commit and the conflicting paths. Approving the
dependent task is refused, naming the commit, until its branch contains that work.

Driven through the trigger route and the task transition route against a real repository under
`tmp_path` (the suite's default project workspace), with only the runner process faked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import TaskDependency

from .test_agent_trigger import _await_background_run, _fake_pty
from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
from .test_task_integration import TASKS, approve, drive_to, git, make_repo, set_main_branch

_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree


async def _builder(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"builder": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner("builder", cli="claude")


def _commit_in(checkout, name, body):
    (checkout / name).write_text(body, encoding="utf-8")
    git(checkout, "add", name)
    git(checkout, "commit", "-q", "-m", f"work on {name}")
    return git(checkout, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.asyncio
async def test_the_author_gets_its_turn_with_the_merge_and_approval_waits_for_it(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    make_repo(tmp_path)
    await set_main_branch("main")
    await _builder(app, auth_headers, bind_runner)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    loop = await make_loop(app, auth_headers, name="F695 loop")
    prerequisite = await loop_task(app, auth_headers, loop, title="A")
    dependent = await loop_task(app, auth_headers, loop, title="B")

    # B started first (its checkout cut from main, its own work committed on it) ...
    started = await drive_to(app, auth_headers, dependent, "assigned", "in_progress")
    assert started.status_code == 200, started.text
    worktrees.seed_repo_excludes(tmp_path)
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, dependent, "main")
    _commit_in(checkout, "f.txt", "B rewrote line one\n")
    # ... then the dependency was declared, and A's conflicting work was approved and landed.
    async with async_session_factory() as session:
        session.add(
            TaskDependency(
                id="dep-f695",
                project_id="proj-test",
                task_id=dependent,
                depends_on_task_id=prerequisite,
            )
        )
        await session.commit()
    a_commit = commit_on_task_branch(tmp_path, prerequisite, "f.txt", "A rewrote it too\n")
    git(tmp_path, "checkout", "-q", "main")
    landed = await approve(app, auth_headers, prerequisite)
    assert landed.status_code == 200, landed.text

    # B's next turn starts, in its checkout, and is told to merge A's work itself.
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "builder", "message": "carry on with B", "task_id": dependent},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()

    assert fake_spawn.call_args is not None, response.text
    assert fake_spawn.call_args.kwargs.get("cwd") in (str(checkout), checkout)
    argv = fake_spawn.call_args.args[0]
    prompt = next(part for part in argv if "carry on with B" in part)
    assert f"git merge --no-ff {a_commit}" in prompt
    assert prerequisite in prompt
    assert "f.txt" in prompt
    # Handed over clean: no half-finished merge, B's own work untouched.
    assert not worktrees._is_mid_merge(checkout)
    assert (checkout / "f.txt").read_text(encoding="utf-8") == "B rewrote line one\n"

    # Approving B before the merge is refused, naming A's commit.
    reviewed = await drive_to(app, auth_headers, dependent, "completed", "under_review")
    assert reviewed.status_code == 200, reviewed.text
    refused = await app.patch(
        f"{TASKS}/{dependent}", json={"status": "approved"}, headers=auth_headers
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied"
    assert [entry["commit_sha"] for entry in detail["unmerged_prerequisites"]] == [a_commit]
    assert a_commit[:12] in detail["message"] and prerequisite in detail["message"]

    # The author does what the prompt said; approval then goes through.
    git(checkout, "merge", "--no-ff", a_commit)
    (checkout / "f.txt").write_text("B and A, reconciled\n", encoding="utf-8")
    git(checkout, "add", "f.txt")
    git(checkout, "commit", "-q", "--no-edit")
    assert not worktrees._is_mid_merge(checkout)
    approved = await app.patch(
        f"{TASKS}/{dependent}", json={"status": "approved"}, headers=auth_headers
    )
    assert approved.status_code == 200, approved.text
