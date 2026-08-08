"""Tests for `hub.worktrees` (task 5, design.md Decision 7) against real, disposable git
repositories under `tmp_path` — never the real AgentWeave checkout (see `conftest.py`'s
`_no_real_worktree_provision` autouse fixture, which keeps every other test in this suite
from touching real git state via this module).
"""

import subprocess
from pathlib import Path

import pytest

from hub import worktrees

# Named import (not `resolve_agent_workspace(...)`) deliberately: the whole-suite
# autouse `_no_real_worktree_provision` fixture in conftest.py monkeypatches the module
# *attribute* so every other test's module-namespace lookup gets a no-op stub — a name bound
# here at collection time is a separate reference to the real function, unaffected by that
# patch, exactly like `test_launchability.py`'s direct imports of `probe_mcp_registered` et al.
from hub.worktrees import resolve_agent_workspace


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("line1\nline2\nline3\n")
    (path / "README.md").write_text("hello\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


def test_is_git_repo_true_for_real_repo(repo):
    assert worktrees.is_git_repo(repo) is True


def test_is_git_repo_false_for_plain_directory(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert worktrees.is_git_repo(plain) is False


def test_is_writing_agent_defaults_true():
    assert worktrees.is_writing_agent({}) is True
    assert worktrees.is_writing_agent({"runner": "claude"}) is True


def test_is_writing_agent_false_when_read_only():
    assert worktrees.is_writing_agent({"read_only": True}) is False


def test_ensure_worktree_creates_branch_and_directory(repo):
    path = worktrees.ensure_worktree(repo, "alice")
    assert path == worktrees.worktree_path(repo, "alice")
    assert path.is_dir()
    assert (path / "f.txt").read_text() == "line1\nline2\nline3\n"

    branches = _git(repo, "branch", "--list", "agentweave/alice").stdout
    assert "agentweave/alice" in branches

    worktree_list = _git(repo, "worktree", "list").stdout
    assert str(path) in worktree_list or path.name in worktree_list


def test_ensure_worktree_is_idempotent(repo):
    first = worktrees.ensure_worktree(repo, "bob")
    second = worktrees.ensure_worktree(repo, "bob")
    assert first == second
    assert first.is_dir()


def test_ensure_worktree_rejects_unregistered_existing_directory(repo):
    path = worktrees.worktree_path(repo, "occupied")
    path.mkdir(parents=True)
    (path / "untrusted.txt").write_text("not a linked worktree\n")

    with pytest.raises(worktrees.IsolationUnavailableError, match="registered git worktree"):
        worktrees.ensure_worktree(repo, "occupied")


def test_resolve_agent_workspace_isolates_writing_agent(repo):
    path = resolve_agent_workspace(repo, "carol", {})
    assert path == worktrees.worktree_path(repo, "carol")
    assert path.is_dir()


def test_resolve_agent_workspace_shares_checkout_for_read_only_agent(repo):
    path = resolve_agent_workspace(repo, "reader", {"read_only": True})
    assert path == repo
    assert not worktrees.worktree_path(repo, "reader").exists()


def test_resolve_agent_workspace_refuses_writer_when_not_a_git_repo(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    with pytest.raises(worktrees.IsolationUnavailableError, match="git repository"):
        resolve_agent_workspace(plain, "dave", {})


def test_resolve_agent_workspace_does_not_fall_back_after_git_failure(repo, monkeypatch):
    def fail(*args, **kwargs):
        raise worktrees.GitCommandError(["worktree", "add"], 1, "boom")

    monkeypatch.setattr(worktrees, "ensure_worktree", fail)

    with pytest.raises(worktrees.GitCommandError, match="boom"):
        resolve_agent_workspace(repo, "dave", {})


def test_symlinks_shared_dependency_dirs_into_new_worktree(repo):
    node_modules = repo / "node_modules"
    node_modules.mkdir()
    (node_modules / "pkg.txt").write_text("installed\n")

    path = worktrees.ensure_worktree(repo, "erin")
    linked = path / "node_modules"
    # Symlink creation can silently fail without privilege on Windows — assert
    # only that when it *does* succeed, the content is actually shared, not that
    # it always succeeds (see `_symlink_shared_dependencies`'s own docstring note).
    if linked.exists():
        assert (linked / "pkg.txt").read_text() == "installed\n"


def test_snapshot_worktree_commits_dirty_changes(repo):
    path = worktrees.ensure_worktree(repo, "frank")
    (path / "f.txt").write_text("frank was here\n")

    sha = worktrees.snapshot_worktree(path, "frank")
    assert sha is not None

    log = _git(path, "log", "-1", "--format=%s").stdout
    assert "frank" in log
    status = _git(path, "status", "--porcelain").stdout
    assert status.strip() == ""


def test_snapshot_worktree_returns_none_when_clean(repo):
    path = worktrees.ensure_worktree(repo, "grace")
    assert worktrees.snapshot_worktree(path, "grace") is None


def test_snapshot_worktree_does_not_require_operator_git_identity(repo):
    path = worktrees.ensure_worktree(repo, "identityless")
    _git(path, "config", "--unset", "user.email")
    _git(path, "config", "--unset", "user.name")
    (path / "f.txt").write_text("safe snapshot\n")

    assert worktrees.snapshot_worktree(path, "identityless") is not None


def test_release_worktree_reports_no_worktree_when_never_provisioned(repo):
    result = worktrees.release_worktree(repo, "nobody")
    assert result.released is False
    assert result.has_unmerged_work is False


def test_release_worktree_removes_directory_but_keeps_branch(repo):
    path = worktrees.ensure_worktree(repo, "henry")
    result = worktrees.release_worktree(repo, "henry")

    assert result.released is True
    assert not path.exists()
    branches = _git(repo, "branch", "--list", "agentweave/henry").stdout
    assert "agentweave/henry" in branches
    assert "henry" not in worktrees.list_agent_branches(repo)


def test_release_worktree_snapshots_and_reports_uncommitted_changes(repo):
    path = worktrees.ensure_worktree(repo, "iris")
    (path / "f.txt").write_text("iris's uncommitted edit\n")

    result = worktrees.release_worktree(repo, "iris")

    assert result.had_uncommitted_changes is True
    assert result.snapshot_commit is not None
    assert result.has_unmerged_work is True
    assert result.unmerged_commits == [result.snapshot_commit]


def test_release_worktree_reports_clean_agent_as_no_unmerged_work(repo):
    worktrees.ensure_worktree(repo, "jack")
    result = worktrees.release_worktree(repo, "jack")

    assert result.released is True
    assert result.had_uncommitted_changes is False
    assert result.has_unmerged_work is False


def test_ensure_worktree_reuses_existing_branch_after_release(repo):
    path = worktrees.ensure_worktree(repo, "kim")
    (path / "f.txt").write_text("kim's work\n")
    sha_before = worktrees.snapshot_worktree(path, "kim")
    worktrees.release_worktree(repo, "kim")

    reprovisioned = worktrees.ensure_worktree(repo, "kim")
    assert (reprovisioned / "f.txt").read_text() == "kim's work\n"
    log = _git(reprovisioned, "log", "-1", "--format=%H").stdout.strip()
    assert log == sha_before


def test_ensure_worktree_fast_forwards_merged_released_branch(repo):
    worktrees.ensure_worktree(repo, "lucy")
    worktrees.release_worktree(repo, "lucy")
    (repo / "new.txt").write_text("new primary content\n")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-q", "-m", "advance primary")

    path = worktrees.ensure_worktree(repo, "lucy")

    assert (path / "new.txt").read_text() == "new primary content\n"


@pytest.mark.parametrize("agent", ["../escape", "nested/name", "", "x" * 33, "user", "USER"])
def test_agent_name_cannot_escape_worktree_namespace(repo, agent):
    with pytest.raises(ValueError, match="agent name"):
        worktrees.ensure_worktree(repo, agent)


def test_list_agent_branches_returns_only_provisioned_agents(repo):
    worktrees.ensure_worktree(repo, "liam")
    worktrees.ensure_worktree(repo, "mia")
    names = worktrees.list_agent_branches(repo)
    assert set(names) == {"liam", "mia"}


def test_list_agent_branches_empty_when_none_provisioned(repo):
    assert worktrees.list_agent_branches(repo) == []


def test_detect_conflicts_empty_when_no_overlap(repo):
    a = worktrees.ensure_worktree(repo, "noah")
    b = worktrees.ensure_worktree(repo, "olive")
    (a / "a-only.txt").write_text("noah's file\n")
    worktrees.snapshot_worktree(a, "noah")
    (b / "b-only.txt").write_text("olive's file\n")
    worktrees.snapshot_worktree(b, "olive")

    assert worktrees.detect_conflicts(repo) == []


def test_detect_conflicts_reports_diverging_agents_and_paths(repo):
    a = worktrees.ensure_worktree(repo, "penny")
    b = worktrees.ensure_worktree(repo, "quinn")
    (a / "f.txt").write_text("penny's version\n")
    worktrees.snapshot_worktree(a, "penny")
    (b / "f.txt").write_text("quinn's version\n")
    worktrees.snapshot_worktree(b, "quinn")

    reports = worktrees.detect_conflicts(repo)
    assert len(reports) == 1
    report = reports[0]
    assert set(report.agents) == {"penny", "quinn"}
    assert report.paths == ["f.txt"]


def test_detect_conflicts_ignores_agents_with_no_commits_yet(repo):
    worktrees.ensure_worktree(repo, "river")  # never edits anything
    worktrees.ensure_worktree(repo, "sage")
    assert worktrees.detect_conflicts(repo) == []


@pytest.mark.asyncio
async def test_worktree_endpoints_list_active_agents_and_their_conflicts(
    app, auth_headers, repo, bind_project_workspace
):
    await bind_project_workspace(repo)
    a = worktrees.ensure_worktree(repo, "taylor")
    b = worktrees.ensure_worktree(repo, "uma")
    (a / "f.txt").write_text("taylor\n")
    worktrees.snapshot_worktree(a, "taylor")
    (b / "f.txt").write_text("uma\n")
    worktrees.snapshot_worktree(b, "uma")

    listing = await app.get("/api/v1/projects/proj-test/worktrees", headers=auth_headers)
    conflicts = await app.get(
        "/api/v1/projects/proj-test/worktrees/conflicts", headers=auth_headers
    )

    assert listing.status_code == 200
    assert {item["agent"] for item in listing.json()} == {"taylor", "uma"}
    assert conflicts.status_code == 200
    assert conflicts.json() == [{"agents": ["taylor", "uma"], "paths": ["f.txt"]}]


@pytest.mark.asyncio
async def test_an_agents_workspace_reads_without_provisioning_one(
    app, auth_headers, repo, bind_project_workspace
):
    """Opening an agent's configuration must not create its worktree.

    The panel answers from `worktree_path`/`branch_name`, which are pure — so an agent that has
    never run says where it *will* work rather than rendering blank, and looking at the page does
    not leave a checkout behind. Task 3.7 of 2026-08-08-agent-configuration-page.
    """
    await bind_project_workspace(repo)

    resp = await app.get("/api/v1/projects/proj-test/worktrees/vera", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["isolated"] is True
    assert body["branch"] == "agentweave/vera"
    assert body["provisioned"] is False
    assert body["working_dir"] == str(repo / ".agentweave" / "worktrees" / "vera")
    assert not (repo / ".agentweave" / "worktrees" / "vera").exists()

    worktrees.ensure_worktree(repo, "vera")
    resp = await app.get("/api/v1/projects/proj-test/worktrees/vera", headers=auth_headers)
    assert resp.json()["provisioned"] is True


@pytest.mark.asyncio
async def test_a_read_only_agent_shares_the_project_checkout(
    app, auth_headers, repo, bind_project_workspace
):
    """No branch and nothing to provision — reporting "not provisioned" would imply something
    is missing, when sharing the checkout is the whole arrangement."""
    await bind_project_workspace(repo)
    reg = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "wren", "contact_mode": "poll", "config": {"read_only": True}},
        headers=auth_headers,
    )
    assert reg.status_code == 200

    resp = await app.get("/api/v1/projects/proj-test/worktrees/wren", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["isolated"] is False
    assert body["branch"] is None
    assert body["provisioned"] is True
    assert body["working_dir"] == str(repo)


@pytest.mark.asyncio
async def test_a_workspace_that_cannot_isolate_says_so_before_a_turn_refuses(
    app, auth_headers, tmp_path, bind_project_workspace
):
    """The same condition `resolve_agent_workspace` fails a spawn on, reported where the operator
    can read it first rather than afterwards as a run failure."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    await bind_project_workspace(plain)

    resp = await app.get("/api/v1/projects/proj-test/worktrees/xan", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["isolated"] is True
    assert body["provisioned"] is False
    assert "not a git repository" in body["unavailable_reason"]


@pytest.mark.asyncio
async def test_the_conflicts_route_is_not_read_as_an_agent_name(app, auth_headers, repo,
                                                                bind_project_workspace):
    """`/worktrees/conflicts` is a route, and `conflicts` is a legal agent name — declaration
    order is the only thing keeping the two apart, so it is worth a test."""
    await bind_project_workspace(repo)
    resp = await app.get("/api/v1/projects/proj-test/worktrees/conflicts", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_an_illegal_agent_name_is_refused(app, auth_headers, repo, bind_project_workspace):
    await bind_project_workspace(repo)
    resp = await app.get(
        "/api/v1/projects/proj-test/worktrees/not%20a%20name", headers=auth_headers
    )
    assert resp.status_code == 400
