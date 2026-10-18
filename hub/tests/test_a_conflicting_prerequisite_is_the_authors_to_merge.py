"""F695: a prerequisite whose approved work conflicts with a dependent task's checkout is the
dependent task's author's to merge, in its own turn.

Before this, `worktrees._catch_up_prerequisites` refused the turn on such a conflict, and the refusal
told somebody to run `git merge --no-ff` in the checkout -- but the author, the one party whose work
it is to reconcile, never got a turn to do it in; only the operator, in a terminal, could. Now the
merge is abandoned (the checkout left clean), the turn starts, and its prompt carries the merge
instruction naming the prerequisite task, its commit and the conflicting paths. Approving the
dependent task is refused, naming the commit, until its branch contains that work.

The follow-up (F695's own defect): an author who leaves that merge unfinished must not have the
end-of-turn auto-snapshot commit it with its conflicts in, and its next turn is told the merge is
unfinished and which paths are still conflicted. A merge resolved but not committed is committed by
the snapshot, as any other dirty state is.

Driven through the trigger route and the task transition route against a real repository under
`tmp_path` (the suite's default project workspace), with only the runner process faked -- its
"agent" runs git in the checkout it was spawned in, which is what a real agent would do.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import TaskDependency

from .test_agent_trigger import _await_background_run, _fake_pty
from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
from .test_task_integration import TASKS, approve, drive_to, git, make_repo, set_main_branch

_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree
_RESULT = '{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n'


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


async def _b_behind_a_conflicting(app, auth_headers, bind_runner, tmp_path, monkeypatch):
    """B started first and committed f.txt; then B was made to depend on A, and A's conflicting
    f.txt was approved and landed. Returns `(checkout, a_commit, a_id, b_id)`."""
    make_repo(tmp_path)
    await set_main_branch("main")
    await _builder(app, auth_headers, bind_runner)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    loop = await make_loop(app, auth_headers, name="F695 loop")
    prerequisite = await loop_task(app, auth_headers, loop, title="A")
    dependent = await loop_task(app, auth_headers, loop, title="B")

    started = await drive_to(app, auth_headers, dependent, "assigned", "in_progress")
    assert started.status_code == 200, started.text
    worktrees.seed_repo_excludes(tmp_path)
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, dependent, "main")
    _commit_in(checkout, "f.txt", "B rewrote line one\n")
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
    return checkout, a_commit, prerequisite, dependent


async def _turn(app, auth_headers, task_id, message, agent_does=None):
    """One turn on *task_id*; *agent_does(cwd)* runs as the spawned agent. Returns
    `(response, prompt or None)`."""
    inner = _fake_pty([_RESULT])
    calls = []

    def spawn(cmd, *args, **kwargs):
        calls.append((cmd, kwargs))
        if agent_does is not None:
            agent_does(kwargs.get("cwd"))
        return inner(cmd, *args, **kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "builder", "message": message, "task_id": task_id},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()
    if not calls:
        return response, None
    return response, next(part for part in calls[-1][0] if message in part)


def _unmerged(checkout):
    return git(checkout, "diff", "--name-only", "--diff-filter=U").stdout.split()


@pytest.mark.asyncio
async def test_the_author_gets_its_turn_with_the_merge_and_approval_waits_for_it(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    checkout, a_commit, prerequisite, dependent = await _b_behind_a_conflicting(
        app, auth_headers, bind_runner, tmp_path, monkeypatch
    )

    # B's next turn starts, in its checkout, and is told to merge A's work itself.
    seen = {}
    response, prompt = await _turn(
        app,
        auth_headers,
        dependent,
        "carry on with B",
        agent_does=lambda cwd: seen.setdefault("cwd", cwd),
    )

    assert prompt is not None, response.text
    assert str(seen["cwd"]) == str(checkout)
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


@pytest.mark.parametrize("staged", [False, True], ids=["left-unmerged", "markers-staged"])
@pytest.mark.asyncio
async def test_an_unfinished_merge_is_not_snapshotted_and_the_next_turn_is_told(
    app, auth_headers, bind_runner, tmp_path, monkeypatch, staged
):
    """The agent starts the merge and stops with the conflicts unresolved -- either still unmerged
    in the index, or `git add`ed with the conflict markers in them. The snapshot leaves it all as it
    is; the next turn starts (not refused over the mid-merge checkout) and is told."""
    checkout, a_commit, prerequisite, dependent = await _b_behind_a_conflicting(
        app, auth_headers, bind_runner, tmp_path, monkeypatch
    )
    tip = git(checkout, "rev-parse", "HEAD").stdout.strip()

    def starts_the_merge_and_stops(cwd):
        git(cwd, "merge", "--no-ff", a_commit)
        if staged:
            git(cwd, "add", "f.txt")

    _, first = await _turn(app, auth_headers, dependent, "merge A", starts_the_merge_and_stops)
    assert first is not None

    assert git(checkout, "rev-parse", "HEAD").stdout.strip() == tip, "the snapshot committed it"
    assert worktrees._is_mid_merge(checkout)
    assert "<<<<<<<" in (checkout / "f.txt").read_text(encoding="utf-8")
    assert _unmerged(checkout) == ([] if staged else ["f.txt"])

    response, second = await _turn(app, auth_headers, dependent, "finish it")
    assert second is not None, response.text
    assert "unfinished" in second
    assert a_commit in second and prerequisite in second and "f.txt" in second


@pytest.mark.asyncio
async def test_a_resolved_but_uncommitted_merge_is_committed_by_the_snapshot(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    checkout, a_commit, _, dependent = await _b_behind_a_conflicting(
        app, auth_headers, bind_runner, tmp_path, monkeypatch
    )

    def resolves_without_committing(cwd):
        git(cwd, "merge", "--no-ff", a_commit)
        (Path(cwd) / "f.txt").write_text("B and A, reconciled\n", encoding="utf-8")
        # Resolved in git's own sense: the path is marked resolved, the merge left uncommitted.
        git(cwd, "add", "f.txt")

    await _turn(app, auth_headers, dependent, "merge A", resolves_without_committing)

    assert not worktrees._is_mid_merge(checkout)
    assert git(checkout, "merge-base", "--is-ancestor", a_commit, "HEAD").returncode == 0
    assert git(checkout, "status", "--porcelain").stdout.strip() == ""
