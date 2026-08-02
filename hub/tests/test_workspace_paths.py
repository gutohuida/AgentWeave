"""Tests for `hub.workspace_paths` and `GET /api/v1/workspace/paths` (task 0 of the
composer-intelligence change) — see
openspec/changes/composer-intelligence/specs/agent-composer/spec.md's "Workspace path listing
endpoint" requirement: excludes gitignored paths (including nested `.gitignore` files) and
returns an empty list, not an error, when the working directory isn't a git repository.

Uses real, disposable git repositories under `tmp_path`, mirroring `test_worktrees.py`'s
pattern — never the real AgentWeave checkout.
"""

import subprocess
from pathlib import Path

import pytest

from hub.workspace_paths import list_workspace_paths


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("hello\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


def test_list_workspace_paths_includes_tracked_files(repo):
    assert "README.md" in list_workspace_paths(repo)


def test_list_workspace_paths_includes_untracked_not_ignored_files(repo):
    (repo / "scratch.txt").write_text("not committed, not ignored\n")
    assert "scratch.txt" in list_workspace_paths(repo)


def test_list_workspace_paths_excludes_gitignored_paths(repo):
    (repo / ".gitignore").write_text("node_modules/\n")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "pkg.js").write_text("ignored\n")

    paths = list_workspace_paths(repo)

    assert not any(path.startswith("node_modules/") for path in paths)


def test_list_workspace_paths_excludes_nested_gitignore(repo):
    (repo / "sub").mkdir()
    (repo / "sub" / ".gitignore").write_text("build/\n")
    (repo / "sub" / "build").mkdir()
    (repo / "sub" / "build" / "out.js").write_text("ignored\n")
    (repo / "sub" / "keep.txt").write_text("kept\n")

    paths = list_workspace_paths(repo)

    assert "sub/keep.txt" in paths
    assert not any(path.startswith("sub/build/") for path in paths)


def test_list_workspace_paths_returns_empty_for_non_git_directory(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "file.txt").write_text("hello\n")

    assert list_workspace_paths(plain) == []


@pytest.mark.asyncio
async def test_workspace_paths_endpoint_lists_paths_for_hub_cwd(app, auth_headers, repo, monkeypatch):
    monkeypatch.chdir(repo)
    (repo / "extra.txt").write_text("hi\n")

    response = await app.get("/api/v1/workspace/paths", headers=auth_headers)

    assert response.status_code == 200
    assert {"README.md", "extra.txt"} <= set(response.json())


@pytest.mark.asyncio
async def test_workspace_paths_endpoint_returns_empty_for_non_git_cwd(
    app, auth_headers, tmp_path, monkeypatch
):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    monkeypatch.chdir(plain)

    response = await app.get("/api/v1/workspace/paths", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []
