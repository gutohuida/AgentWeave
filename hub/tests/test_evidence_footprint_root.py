"""A footprint names the work, not whatever the operator's checkout is sitting on.

The defect these tests exist for was found by driving the product, not by the suite: approving a task
merged `master` into `master`, recorded `outcome: merged`, and reported the requirement
`verified / integrated` while every line of the product sat on `agentweave/builder`.

**Why 19 passing tests missed it.** They used branch-switching inside a single repository with no
worktree, and the autouse `_default_project_workspace` fixture resolves any project to `tmp_path`. In
that shape the work and the checkout share a directory, so reading either one gives the same answer.
AgentWeave never produces that shape — it gives every agent its own checkout on its own branch.

So every test here uses `bind_project_workspace` (which restores the real resolver) and a real
worktree, and commits **inside** it: straight after provisioning, the worktree's HEAD and the project
checkout's HEAD are identical, and any assertion comparing them would pass without meaning anything.
"""

import subprocess
from pathlib import Path

import pytest

from hub import requirement_evidence, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
OPERATOR_EVIDENCE = f"{BASE}/spec/evidence"
PATH = "spec/changes/footprint-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It records a check-in", "modal": "MUST"}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)


def init_repo(path: Path, branch: str = "master") -> Path:
    """A repository on *branch* with one commit.

    `master` by default, matching the project the live defect was found on — and deliberately the
    *second* name `MAIN_BRANCH_NAMES` tries, so a test cannot pass by accident of ordering.
    """
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", branch)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    return path


def commit_in(worktree: Path, filename: str, content: str) -> str:
    """Commit inside the agent's own checkout, so its HEAD diverges from the project's."""
    (worktree / filename).write_text(content, encoding="utf-8")
    git(worktree, "add", filename)
    git(worktree, "commit", "-q", "-m", f"agent work on {filename}")
    return git(worktree, "rev-parse", "HEAD").stdout.strip()


def head_of(repo: Path, ref: str = "HEAD") -> str:
    return git(repo, "rev-parse", ref).stdout.strip()


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-fp", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-fp",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_fp-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_fp-secret"}


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Footprint demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Footprint demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def only_footprint() -> EvidenceFootprint:
    async with async_session_factory() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(EvidenceFootprint))).scalars().all()
        assert len(rows) == 1, f"expected exactly one footprint, got {len(rows)}"
        return rows[0]


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_evidence_is_footprinted_from_the_agents_worktree(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The test that fails on the code which shipped the defect.

    It recorded the project checkout's `master` commit, with `reachable_from_main=True`, for work
    that existed only on the agent's branch.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    agent_commit = commit_in(worktree, "feature.py", "print('hi')\n")

    assert agent_commit != head_of(repo), "the worktree must have diverged or this proves nothing"

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran the tests"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.kind == "git"
    assert footprint.branch == "agentweave/builder"
    assert footprint.commit_sha == agent_commit
    assert footprint.commit_sha != head_of(repo)
    assert "feature.py" in (footprint.entries or {})
    assert footprint.reachable_from_main is False


@pytest.mark.asyncio
async def test_operator_evidence_is_footprinted_from_the_project_root(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The operator's own checkout is the right answer for the operator.

    Also guarded by git itself: it refuses to check out a branch already checked out in a linked
    worktree, so the project checkout can never *be* an agent's branch.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    commit_in(worktree, "feature.py", "x\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        OPERATOR_EVIDENCE,
        json={"identifier": "FR-1", "summary": "I looked at it myself"},
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.branch == "master"
    assert footprint.commit_sha == head_of(repo)
    assert footprint.reachable_from_main is True


@pytest.mark.asyncio
async def test_an_agent_without_a_worktree_falls_back_and_creates_nothing(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The load-bearing negative: it fails the "fix" that reaches for `ensure_worktree`.

    Provisioning a checkout as a side effect of recording evidence would change what was being
    measured, and would give every read path the power to write to the operator's repository.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "no worktree here"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.kind == "git"
    assert footprint.branch == "master"
    assert footprint.commit_sha == head_of(repo)
    assert not worktrees.worktree_path(repo, "builder").exists()


@pytest.mark.asyncio
async def test_an_unregistered_directory_is_not_the_agents_worktree(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The trap a plausible implementation falls into.

    A git command run with `cwd` inside a directory git does not track walks up to the enclosing
    repository and answers about *that* — so a `.exists()` check would read the project checkout's
    HEAD while appearing to have verified the agent's worktree.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    stray = worktrees.worktree_path(repo, "builder")
    stray.mkdir(parents=True)
    (stray / "leftover.txt").write_text("not a worktree\n", encoding="utf-8")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "stray directory"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.branch == "master"
    assert footprint.commit_sha == head_of(repo)


@pytest.mark.asyncio
async def test_a_project_without_a_repository_still_footprints_paths(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """A non-repository project is a supported shape and must not be made worse by any of this."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "README.md").write_text("no git here\n", encoding="utf-8")
    await bind_project_workspace(plain)

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "no repository"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.kind == "paths"
    assert footprint.commit_sha is None


# ---------------------------------------------------------------------------
# The accessor itself
# ---------------------------------------------------------------------------


def test_existing_worktree_answers_only_for_a_registered_checkout(tmp_path):
    repo = init_repo(tmp_path / "repo")
    assert worktrees.existing_worktree(repo, "builder") is None

    provisioned = worktrees.ensure_worktree(repo, "builder")
    assert worktrees.existing_worktree(repo, "builder") == provisioned


def test_existing_worktree_creates_nothing(tmp_path):
    repo = init_repo(tmp_path / "repo")
    assert worktrees.existing_worktree(repo, "builder") is None
    assert not worktrees.worktree_root(repo).exists()


def test_existing_worktree_rejects_an_unregistered_directory(tmp_path):
    repo = init_repo(tmp_path / "repo")
    stray = worktrees.worktree_path(repo, "builder")
    stray.mkdir(parents=True)
    assert worktrees.existing_worktree(repo, "builder") is None


def test_existing_worktree_rejects_an_invalid_name(tmp_path):
    repo = init_repo(tmp_path / "repo")
    assert worktrees.existing_worktree(repo, "../escape") is None
    assert worktrees.existing_worktree(repo, "user") is None


# ---------------------------------------------------------------------------
# Reachability is re-answered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reachability_is_re_answered_after_the_work_lands(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Without this, the footprint fix would replace a false positive with a permanent false one.

    `reachable_from_main` is written once, at capture — and evidence is always recorded before the
    work is integrated, so the answer at that moment is "not yet" for every agent footprint.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    agent_commit = commit_in(worktree, "feature.py", "x\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    assert (await only_footprint()).reachable_from_main is False

    git(repo, "merge", "-q", "--no-ff", "-m", "integrate", agent_commit)

    async with async_session_factory() as session:
        updated = await requirement_evidence.refresh_reachability(
            session, "proj-test", repo, main_branch="master"
        )
        await session.commit()
    assert updated == 1
    assert (await only_footprint()).reachable_from_main is True


@pytest.mark.asyncio
async def test_reachability_prefers_the_configured_branch(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """A project integrating into `develop` has a `master` the guess would find first."""
    repo = init_repo(tmp_path / "repo")
    git(repo, "branch", "develop")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    agent_commit = commit_in(worktree, "feature.py", "x\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    git(repo, "checkout", "-q", "develop")
    git(repo, "merge", "-q", "--no-ff", "-m", "integrate", agent_commit)
    git(repo, "checkout", "-q", "master")

    async with async_session_factory() as session:
        # The guess would look at `master`, which does not have it.
        assert await requirement_evidence.refresh_reachability(session, "proj-test", repo) == 0
        assert (
            await requirement_evidence.refresh_reachability(
                session, "proj-test", repo, main_branch="develop"
            )
            == 1
        )
        await session.commit()
    assert (await only_footprint()).reachable_from_main is True


# ---------------------------------------------------------------------------
# End to end, and drift
# ---------------------------------------------------------------------------


async def _accept(app, auth_headers, evidence_id):
    decided = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text


async def _set_main_branch(name):
    from hub.db.models import Project

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = name
        await session.commit()


@pytest.mark.asyncio
async def test_approving_work_from_a_worktree_puts_it_on_main(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The whole change, end to end, in the arrangement the product actually creates.

    This is the run that reported `merged` while merging nothing.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _set_main_branch("master")
    worktree = worktrees.ensure_worktree(repo, "builder")
    agent_commit = commit_in(worktree, "feature.py", "print('shipped')\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    await _accept(app, auth_headers, recorded.json()["id"])

    tasks = "/api/v1/projects/proj-test/tasks"
    created = await app.post(
        tasks, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    # Coverage tells the truth before the merge — the statement B3 built and this makes reachable.
    before = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert before.json()["requirements"][0]["integration"] == "not_integrated"

    for status in ("assigned", "in_progress", "completed", "under_review", "approved"):
        moved = await app.patch(f"{tasks}/{task_id}", json={"status": status}, headers=auth_headers)
        assert moved.status_code == 200, moved.text

    merged_shas = git(repo, "log", "--format=%H", "master").stdout.split()
    assert agent_commit in merged_shas
    assert "feature.py" in git(repo, "ls-tree", "-r", "--name-only", "master").stdout

    rows = (await app.get(f"{tasks}/{task_id}/integrations", headers=auth_headers)).json()
    assert rows["integrations"][0]["outcome"] == "merged"
    assert rows["integrations"][0]["source_branch"] == "agentweave/builder"

    # The operator's checkout is untouched: still on master, still clean.
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "master"
    assert not git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()

    # And coverage now says so — the assertion that fails without the reachability refresh.
    after = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert after.json()["requirements"][0]["integration"] == "integrated"


@pytest.mark.asyncio
async def test_movement_on_main_is_not_drift_for_work_on_a_branch(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Two legs, because the negative alone is satisfied by muting the feature entirely.

    Without the per-ref comparison, leg one raises a candidate for every accepted requirement at
    once — reporting "this is not on master", which coverage already says as `not_integrated`.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    commit_in(worktree, "feature.py", "original\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    await _accept(app, auth_headers, recorded.json()["id"])

    # Leg 1: the main line moves. That is integration's business, not drift's.
    (repo / "unrelated.md").write_text("operator's own work\n", encoding="utf-8")
    git(repo, "add", "unrelated.md")
    git(repo, "commit", "-q", "-m", "unrelated")
    quiet = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert quiet.status_code == 200, quiet.text
    assert quiet.json()["raised"] == []

    # Leg 2: the branch the footprint names moves. That is drift.
    commit_in(worktree, "feature.py", "changed after it was accepted\n")
    raised = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert raised.status_code == 200, raised.text
    assert len(raised.json()["raised"]) == 1


@pytest.mark.asyncio
async def test_a_footprint_whose_branch_is_gone_raises_nothing(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Being unable to tell is not evidence that anything moved."""
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    commit_in(worktree, "feature.py", "x\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    await _accept(app, auth_headers, recorded.json()["id"])

    worktrees.release_worktree(repo, "builder")
    git(repo, "branch", "-D", "agentweave/builder")

    detected = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert detected.status_code == 200, detected.text
    assert detected.json()["raised"] == []


# ---------------------------------------------------------------------------
# What the Hub puts in someone else's repository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registering_seeds_ignore_rules_for_the_hubs_own_files(
    bind_project_workspace, tmp_path
):
    """Agents commit what they find.

    Without this the first agent to run commits its own isolated checkout, and the operator inherits
    an `.agentweave/worktrees/` tree in their history having never chosen it. Observed twice.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)

    ignored = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".agentweave/worktrees/" in ignored
    assert ".agentweave/logs/" in ignored

    # And git agrees, which is the only claim that matters.
    worktrees.ensure_worktree(repo, "builder")
    status = git(repo, "status", "--porcelain").stdout
    assert "worktrees" not in status


@pytest.mark.asyncio
async def test_seeding_preserves_what_the_operator_already_ignored(
    bind_project_workspace, tmp_path
):
    """The ignore file is the operator's. Being registered is not a reason to reorder it."""
    repo = init_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("# mine\nbuild/\n*.log\n", encoding="utf-8")

    await bind_project_workspace(repo)

    ignored = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ignored.startswith("# mine\nbuild/\n*.log\n")
    assert ".agentweave/worktrees/" in ignored


@pytest.mark.asyncio
async def test_a_project_without_a_repository_gets_no_ignore_file(bind_project_workspace, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    await bind_project_workspace(plain)
    assert not (plain / ".gitignore").exists()


@pytest.mark.asyncio
async def test_evidence_reports_the_work_it_describes(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """What a reviewer needs in order to accept evidence responsibly.

    Accepting evidence is a judgement about whether it demonstrates the requirement, and that is
    unanswerable without knowing which work it was taken against. A reviewer who could see
    `branch: master` on a builder's evidence would have caught the 2026-08-13 defect by eye.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    agent_commit = commit_in(worktree, "feature.py", "x\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    listed = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    footprint = listed.json()["evidence"][0]["footprint"]
    assert footprint["branch"] == "agentweave/builder"
    assert footprint["commit_sha"] == agent_commit
    assert footprint["reachable_from_main"] is False


@pytest.mark.asyncio
async def test_merging_works_in_a_repository_with_no_configured_identity(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The Hub supplies its own committer identity, never relying on the project's configuration.

    Found on the first real run of the integration path, not by this suite: every test repository
    here sets `user.email` in setup, so none of them could see it. A project the operator has not
    configured an identity in is an ordinary project — git simply refuses to commit there — and the
    Hub already supplies its own for worktree snapshots. Without the same on the merge, the Hub
    could create an agent's commits and then fail to integrate them:

        Committer identity unknown … unable to auto-detect email address
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "master")
    # Deliberately no user.email / user.name. The agent's own commits still work because
    # `snapshot_worktree` supplies an identity; the merge has to do the same.
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-q", "-m", "base")

    await bind_project_workspace(repo)
    await _set_main_branch("master")
    worktree = worktrees.ensure_worktree(repo, "builder")

    (worktree / "feature.py").write_text("x\n", encoding="utf-8")
    git(worktree, "add", "feature.py")
    agent_commit = worktrees.snapshot_worktree(worktree, "builder")
    assert agent_commit, "the Hub must be able to commit in the worktree without configuration"

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "tests pass"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    await _accept(app, auth_headers, recorded.json()["id"])

    tasks = "/api/v1/projects/proj-test/tasks"
    created = await app.post(
        tasks, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    for status in ("assigned", "in_progress", "completed", "under_review", "approved"):
        moved = await app.patch(f"{tasks}/{task_id}", json={"status": status}, headers=auth_headers)
        assert moved.status_code == 200, moved.text

    rows = (await app.get(f"{tasks}/{task_id}/integrations", headers=auth_headers)).json()
    assert rows["integrations"][0]["outcome"] == "merged", rows["integrations"]
    assert "feature.py" in git(repo, "ls-tree", "-r", "--name-only", "master").stdout


@pytest.mark.asyncio
async def test_an_already_registered_project_is_seeded_too(bind_project_workspace, tmp_path):
    """Seeding only new projects leaves it doing nothing for every project that already exists.

    Those are precisely the ones with the problem: their agents have already been committing. Found
    live — the seeding shipped and then silently did nothing for the project it was written for.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    assert (repo / ".gitignore").is_file()

    # Simulate a project registered before this capability existed.
    (repo / ".gitignore").unlink()
    await bind_project_workspace(repo)
    assert ".agentweave/worktrees/" in (repo / ".gitignore").read_text(encoding="utf-8")
