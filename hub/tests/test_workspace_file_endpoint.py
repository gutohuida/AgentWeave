"""Tests for `hub.workspace_file` and `GET /api/v1/projects/proj-test/workspace/file` (task 4 of
openspec/changes/2026-08-18-one-shell-three-panels — the panel shell's file content endpoint).

Design D7 (design.md:123-150): a path is readable if and only if it is a member of what
`list_workspace_paths` already decided is visible — traversal, a symlink pointing outside the
workspace, and a `.gitignore`d path are all refused *because they are absent from that listing*,
not because a second, independently reasoned sanitizer caught them. Size is bounded at
`aw_max_body_size` (refused, naming size and bound, never truncated); binary detection is a NUL
byte in the first 8,000 bytes, git's own heuristic.

Uses real, disposable git repositories under `tmp_path`, mirroring `test_workspace_paths.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub.project_workspace import ProjectWorkspace
from hub.project_workspace import (
    # A module-level constant holding the unpatched original, same trick conftest.py's
    # `bind_project_workspace` fixture uses — captured before the autouse fake-resolver
    # fixture can monkeypatch the module attribute.
    resolve_project_workspace as _REAL_RESOLVE_PROJECT_WORKSPACE,  # noqa: N812
)
from hub.workspace_file import (
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
    read_workspace_file,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("hello\n", newline="\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


def _workspace(root: Path) -> ProjectWorkspace:
    return ProjectWorkspace(project_id="proj-test", root=root, path_key="test:proj-test")


# -- domain function: hub.workspace_file.read_workspace_file --------------------------------


def test_read_tracked_file_returns_content(repo):
    result = read_workspace_file(_workspace(repo), "README.md", max_size=1_048_576)
    assert result.content == "hello\n"
    assert result.binary is False
    assert result.size == 6


def test_read_untracked_not_ignored_file_returns_content(repo):
    (repo / "scratch.txt").write_text("not committed\n", newline="\n")
    result = read_workspace_file(_workspace(repo), "scratch.txt", max_size=1_048_576)
    assert result.content == "not committed\n"


def test_traversal_path_refused_because_absent_from_listing(repo):
    outside = repo.parent / "outside.txt"
    outside.write_text("secret\n")
    with pytest.raises(WorkspaceFileNotFoundError):
        read_workspace_file(_workspace(repo), "../outside.txt", max_size=1_048_576)


def test_gitignored_path_refused_because_absent_from_listing(repo):
    (repo / ".gitignore").write_text("secret.txt\n")
    (repo / "secret.txt").write_text("ignored\n")
    with pytest.raises(WorkspaceFileNotFoundError):
        read_workspace_file(_workspace(repo), "secret.txt", max_size=1_048_576)


def test_symlink_pointing_outside_the_workspace_is_refused(repo):
    outside_dir = repo.parent / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("do not leak\n")
    link = repo / "leak.txt"
    try:
        link.symlink_to(outside_dir / "secret.txt")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this machine: {exc}")

    # The symlink's own path IS listed (git lists what a path is, not what it resolves
    # to) — this asserts refusal comes from resolve_relative's containment check (the
    # SAME primitive spec_documents.py already uses), not from the membership check.
    from hub.workspace_paths import list_workspace_paths

    assert "leak.txt" in list_workspace_paths(repo)
    with pytest.raises(WorkspaceFileNotFoundError):
        read_workspace_file(_workspace(repo), "leak.txt", max_size=1_048_576)


def test_nonexistent_path_refused(repo):
    with pytest.raises(WorkspaceFileNotFoundError):
        read_workspace_file(_workspace(repo), "does-not-exist.txt", max_size=1_048_576)


def test_oversized_file_refused_naming_size_and_bound(repo):
    (repo / "big.txt").write_text("x" * 100)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "big")

    with pytest.raises(WorkspaceFileTooLargeError) as caught:
        read_workspace_file(_workspace(repo), "big.txt", max_size=50)

    assert caught.value.size == 100
    assert caught.value.bound == 50
    assert "100" in str(caught.value)
    assert "50" in str(caught.value)


def test_binary_file_detected_by_nul_byte(repo):
    (repo / "image.bin").write_bytes(b"\x89PNG\x00\x01\x02")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "binary")

    result = read_workspace_file(_workspace(repo), "image.bin", max_size=1_048_576)

    assert result.binary is True
    assert result.content is None


def test_extensionless_text_file_treated_as_text_not_binary(repo):
    (repo / "Makefile").write_text("all:\n\techo hi\n", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "makefile")

    result = read_workspace_file(_workspace(repo), "Makefile", max_size=1_048_576)

    assert result.binary is False
    assert result.content == "all:\n\techo hi\n"


# -- HTTP route: GET /api/v1/projects/proj-test/workspace/file ------------------------------


@pytest.mark.asyncio
async def test_endpoint_returns_file_content(app, auth_headers, repo, bind_project_workspace):
    await bind_project_workspace(repo)

    response = await app.get(
        "/api/v1/projects/proj-test/workspace/file",
        params={"path": "README.md"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "hello\n"
    assert body["binary"] is False
    assert body["size"] == 6


@pytest.mark.asyncio
async def test_endpoint_refuses_traversal_with_404(app, auth_headers, repo, bind_project_workspace):
    await bind_project_workspace(repo)
    (repo.parent / "outside.txt").write_text("secret\n")

    response = await app.get(
        "/api/v1/projects/proj-test/workspace/file",
        params={"path": "../outside.txt"},
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_endpoint_refuses_oversized_file_with_413_and_no_partial_body(
    app, auth_headers, repo, bind_project_workspace, monkeypatch
):
    import hub.config

    monkeypatch.setattr(hub.config.settings, "aw_max_body_size", 3)
    await bind_project_workspace(repo)

    response = await app.get(
        "/api/v1/projects/proj-test/workspace/file",
        params={"path": "README.md"},
        headers=auth_headers,
    )

    assert response.status_code == 413
    assert "content" not in response.json()
    assert "6" in response.text
    assert "3" in response.text


@pytest.mark.asyncio
async def test_endpoint_reports_binary_without_content(
    app, auth_headers, repo, bind_project_workspace
):
    (repo / "image.bin").write_bytes(b"\x89PNG\x00\x01\x02")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "binary")
    await bind_project_workspace(repo)

    response = await app.get(
        "/api/v1/projects/proj-test/workspace/file",
        params={"path": "image.bin"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["binary"] is True
    assert body["content"] is None


@pytest.mark.asyncio
async def test_endpoint_docker_mode_denies_paths_outside_the_mounted_root(
    app, auth_headers, tmp_path, monkeypatch
):
    """Docker-mode parity (task 4.5): the route resolves through
    `project_workspace.resolve_project_workspace` exactly like `/paths` does, so a project whose
    directory falls outside a configured `AW_WORKSPACE_ROOT` is refused with the same typed 409
    every other project-scoped route already gives — no bespoke path handling in this route.
    """
    import hub.config
    from hub.db.engine import async_session_factory
    from hub.project_lifecycle import ProjectLifecycleService

    root = tmp_path / "workspaces"
    project_dir = root / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "README.md").write_text("hello\n", newline="\n")

    async with async_session_factory() as session:
        await ProjectLifecycleService(session, workspace_root=root).open_existing(project_dir)

    import hub.project_workspace as project_workspace_module

    monkeypatch.setattr(
        project_workspace_module, "resolve_project_workspace", _REAL_RESOLVE_PROJECT_WORKSPACE
    )
    monkeypatch.setattr(hub.config.settings, "aw_workspace_root", str(tmp_path / "other-root"))

    response = await app.get(
        "/api/v1/projects/proj-test/workspace/file",
        params={"path": "README.md"},
        headers=auth_headers,
    )

    assert response.status_code == 409
