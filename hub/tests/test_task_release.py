"""A finished task gives its checkout back, and never gives its branch back (design D5).

Per-task isolation buys one directory per *unfinished* task. Without a release, it buys one per task
that has ever been worked, forever — and this product's own repository would carry hundreds. So what
bounds the disk is the checkout, and these tests are mostly about the asymmetry: the directory goes,
the branch and every commit on it stay.

The branch surviving is not tidiness. Three separate things depend on it, and each has a test here:
a reopened task resumes from its own prior work (`test_a_reopened_task_...`), a review after release
still has a commit to check out (`test_review_still_...`), and an operator reading the history after
the fact still has a history to read.

**Nothing here may fail a transition.** Same rule as integration, for the same reason: approval is a
judgement that the work was good, and a git failure is not grounds to reverse a judgement.
`test_a_release_that_raises_...` is the one that fails if that is ever quietly reversed.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EventLog, Project, RequirementEvidence, Run, Task
from hub.spec_payload import SCHEMA_VERSION

# Captured at import, before `conftest._no_real_worktree_provision` stubs the git-touching
# functions away for the suite at large. These tests want the real ones against `tmp_path`.
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree
_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/release-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
AGENT_BRANCH = "agentweave/builder"


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )


def make_repo(root, main="main"):
    """A repository with one commit on *main*, and nothing else."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "checkout", "-q", "-b", main)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "base")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commits_on(root, branch):
    return git(root, "log", "--format=%H", branch).stdout.split()


def branch_exists(root, branch):
    return git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def work_in(checkout, filename, content, message):
    """Commit *content* inside a task checkout, and return the new sha."""
    (checkout / filename).write_text(content, encoding="utf-8")
    git(checkout, "add", filename)
    git(checkout, "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-q", "-m", message)
    return git(checkout, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture(autouse=True)
def real_task_git(monkeypatch):
    """Restore the git-touching worktree functions this file is about.

    The suite stubs them out by default so no test can mutate the real checkout it is running in;
    every test here works against `tmp_path`, which the `_default_project_workspace` fixture has
    already made the project's root.
    """
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rel", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rel",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rel-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rel-secret"}


async def set_main_branch(name):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = name
        await session.commit()


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Release demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Release demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def accept_evidence(app, auth_headers, run_headers):
    """Record evidence as the agent and accept it as the operator.

    The footprint is taken from the workspace's HEAD at this moment, so the caller arranges for the
    work being claimed to be checked out first.
    """
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=run_headers
    )
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    return recorded.json()["id"]


async def make_task(app, auth_headers, requirement_ids=None):
    payload = {"title": "Build it"}
    if requirement_ids:
        payload["requirement_ids"] = requirement_ids
    created = await app.post(TASKS, json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def drive_to(app, auth_headers, task_id, *statuses):
    response = None
    for next_status in statuses:
        response = await app.patch(
            f"{TASKS}/{task_id}", json={"status": next_status}, headers=auth_headers
        )
        if response.status_code != 200:
            return response
    return response


async def approve(app, auth_headers, task_id):
    return await drive_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )


async def events_of_type(event_type):
    async with async_session_factory() as session:
        rows = await session.execute(select(EventLog).where(EventLog.event_type == event_type))
        return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# 5.1 / 5.3 — the directory goes, the branch stays
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_a_task_removes_its_checkout_and_keeps_the_branch(
    app, auth_headers, tmp_path
):
    """5.1. The whole of D5 in one test, on the ordinary path."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    sha = work_in(checkout, "feature.py", "print('hi')\n", "the task's work")
    branch = worktrees.task_branch_name(task)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert not checkout.exists(), "the checkout should have been released"
    assert branch_exists(tmp_path, branch), "the branch is the record of the work — never deleted"
    assert sha in commits_on(tmp_path, branch)


@pytest.mark.asyncio
async def test_a_rejected_task_is_released_too_and_keeps_its_branch(app, auth_headers, tmp_path):
    """5.3. `rejected` is a terminal status as much as `approved` is: nobody will work the task
    again without reopening it, so the checkout is dead weight. The branch stays for the same
    reason it stays on approval — it is what `rejected -> pending` resumes from, and rejected work
    is exactly the work an operator is most likely to want to read afterwards."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    sha = work_in(checkout, "wrong.py", "oops\n", "the work that was turned down")
    branch = worktrees.task_branch_name(task)

    rejected = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review", "rejected"
    )
    assert rejected.status_code == 200, rejected.text

    assert not checkout.exists()
    assert branch_exists(tmp_path, branch)
    assert sha in commits_on(tmp_path, branch)
    # And it stayed out of the product, which is the point of rejecting it.
    assert sha not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_an_uncommitted_change_is_snapshotted_onto_the_branch_before_release(
    app, auth_headers, tmp_path
):
    """The release inherits `release_worktree`'s discipline: a turn that ended mid-edit must not
    lose the edit just because the operator approved the task. It goes onto the branch, which
    survives."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    committed = work_in(checkout, "feature.py", "print('hi')\n", "the task's work")
    (checkout / "half-done.py").write_text("unfinished\n", encoding="utf-8")
    branch = worktrees.task_branch_name(task)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert not checkout.exists()
    history = commits_on(tmp_path, branch)
    assert history[0] != committed, "the uncommitted edit should have been snapshotted on top"
    assert committed in history
    assert "half-done.py" in git(tmp_path, "show", "--name-only", history[0]).stdout


# ---------------------------------------------------------------------------
# 5.2 — after integration, never before
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_happens_after_integration(app, auth_headers, builder, tmp_path, monkeypatch):
    """5.2. Ordering, asserted rather than argued.

    The spy records what `main` carried *at the moment release was called*. If release ran first,
    the evidence commit would not be there yet. This is what makes the test discriminate the order
    at all: `integration_targets` reads the accepted footprint either way, so the merged sha alone
    would look identical under both orderings — which is precisely why the ordering needs its own
    observation rather than a comment.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await make_task(app, auth_headers, requirement_ids=["FR-1"])
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    work = work_in(checkout, "feature.py", "print('hi')\n", "the task's work")

    # The evidence names the task's own commit. The footprint is taken from the project checkout's
    # HEAD, so put it there — phase 7 is what makes a task-bound run footprint itself.
    git(tmp_path, "merge", "-q", "--ff-only", work)
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "reset", "-q", "--hard", "HEAD~1")

    seen = {}
    real_release = worktrees.release_task_worktree

    def spy(repo_root, task_id):
        seen["main_at_release"] = commits_on(repo_root, "main")
        return real_release(repo_root, task_id)

    monkeypatch.setattr(worktrees, "release_task_worktree", spy)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    latest = approved.json()["latest_integration"]
    assert latest["outcome"] == "merged", latest
    assert (
        latest["commit_sha"] == work
    ), "the evidence commit is what merges, not a release snapshot"

    assert "main_at_release" in seen, "release was never called"
    assert work in seen["main_at_release"], "release ran before the merge it must follow"
    assert not checkout.exists()


# ---------------------------------------------------------------------------
# 5.4 — reopening, which is the whole reason the branch is kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reopened_task_is_re_provisioned_with_its_prior_work(app, auth_headers, tmp_path):
    """5.4. `approved -> revision_needed -> in_progress` is a legal, operator-only route, so
    "terminal" means "nobody is working it", not "nothing more can happen". The next writing turn
    re-provisions the checkout, and `ensure_task_worktree`'s branch-reuse path restores the work —
    because release never touched the branch. Deleting the branch would turn a revision request into
    starting over from the integration base."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    work_in(checkout, "feature.py", "first attempt\n", "the task's work")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert not checkout.exists()

    reopened = await drive_to(app, auth_headers, task, "revision_needed", "in_progress")
    assert reopened.status_code == 200, reopened.text

    # Exactly what the next writing turn does.
    again = worktrees.ensure_task_worktree(tmp_path, task, "main")
    assert again == checkout
    assert (again / "feature.py").read_text(encoding="utf-8") == "first attempt\n"


# ---------------------------------------------------------------------------
# 5.5 — review after release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_still_resolves_and_checks_out_after_release(
    app, auth_headers, builder, tmp_path
):
    """5.5. Open question 1 of the design, closed by measurement rather than by argument.

    `commit_for_task_review` is a database query over accepted evidence footprints — it never reads
    a working directory — and `ensure_review_checkout` needs the *commit*, which is reachable from
    the branch release kept. So a reviewer can still see the work after the author's checkout is
    gone, which a rejected task then being re-reviewed depends on.
    """
    from hub import requirement_evidence

    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await make_task(app, auth_headers, requirement_ids=["FR-1"])
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    work = work_in(checkout, "feature.py", "print('hi')\n", "the task's work")

    git(tmp_path, "merge", "-q", "--ff-only", work)
    evidence_id = await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "reset", "-q", "--hard", "HEAD~1")
    # `commit_for_task_review` asks which evidence belongs to the *task*, which a real run gets
    # from its task binding. This run has none, so the link is made directly.
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, evidence_id)
        evidence.task_id = task
        await session.commit()

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert not checkout.exists(), "the release under test must actually have happened"

    async with async_session_factory() as session:
        target = await requirement_evidence.commit_for_task_review(session, task)
    assert target.commit_sha == work, target

    review = worktrees.ensure_review_checkout(tmp_path, "critic", target.commit_sha)
    assert (review / "feature.py").read_text(encoding="utf-8") == "print('hi')\n"


# ---------------------------------------------------------------------------
# 5.7 — a release failure is a recorded fact, never a reversed judgement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_release_that_raises_is_recorded_and_the_transition_stands(
    app, auth_headers, tmp_path, monkeypatch
):
    """5.7. The rule integration already lives by. A checkout that could not be removed is a
    directory left on disk — annoying, and visible in the event log so it can be dealt with. A
    transition rolled back because of it would be the product overruling a human judgement about
    the quality of work, on the strength of a `git` exit code."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")
    work_in(checkout, "feature.py", "print('hi')\n", "the task's work")

    def boom(repo_root, task_id):
        raise worktrees.GitCommandError(
            ["worktree", "remove", "--force", str(repo_root)], 128, "permission denied"
        )

    monkeypatch.setattr(worktrees, "release_task_worktree", boom)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "approved"

    failures = await events_of_type("task_worktree_release_failed")
    assert len(failures) == 1, failures
    assert task in str(failures[0].data)
    assert "permission denied" in str(failures[0].data)


@pytest.mark.asyncio
async def test_a_grandfathered_task_has_no_checkout_to_release(app, auth_headers, tmp_path):
    """A task stamped `agent` by migration 0095 worked in the shared per-agent checkout, which
    belongs to the agent and outlives every task on it. Releasing it here would take a workspace
    away from an agent that is still using it, so the release is scoped by scheme rather than by
    what happens to exist on disk."""
    make_repo(tmp_path)
    await set_main_branch("main")

    task = await make_task(app, auth_headers)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        row.workspace_scheme = "agent"
        await session.commit()

    # Provisioned anyway, so the assertion is about the *scheme* deciding, not about absence.
    checkout = worktrees.ensure_task_worktree(tmp_path, task, "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert checkout.exists(), "a grandfathered task's turns did not run here; nothing to reclaim"
    assert await events_of_type("task_worktree_released") == []
