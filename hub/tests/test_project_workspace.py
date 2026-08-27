"""Canonical path and workspace-resolution contracts (phase 0.3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub.db.engine import async_session_factory
from hub.project_lifecycle import ProjectLifecycleService
from hub.project_workspace import (
    ProjectIdentityConflict,
    ProjectPathError,
    ProjectWorkspace,
    ProjectWorkspaceUnavailable,
    canonical_path_key,
    canonicalize_project_directory,
    resolve_project_workspace,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (r"C:\Work\Demo", r"c:/work/demo"),
        ("C:\\Work\\Demo\\", r"c:\work\demo"),
    ],
)
def test_windows_path_keys_fold_case_and_separators(left: str, right: str) -> None:
    assert canonical_path_key(left, platform="windows") == canonical_path_key(
        right, platform="windows"
    )


def test_posix_path_keys_preserve_case() -> None:
    assert canonical_path_key("/work/Demo", platform="posix") != canonical_path_key(
        "/work/demo", platform="posix"
    )


def test_equivalent_existing_aliases_canonicalize_to_one_path(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    direct = canonicalize_project_directory(project)
    alias = canonicalize_project_directory(project / ".")

    assert alias.path == direct.path
    assert alias.path_key == direct.path_key


def test_symlink_or_junction_alias_resolves_to_the_real_directory(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(project, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks/junctions unavailable: {exc}")

    assert canonicalize_project_directory(alias) == canonicalize_project_directory(project)


def test_missing_directory_has_a_typed_unavailable_error(tmp_path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(missing)
    assert caught.value.code == "project_workspace_missing"
    assert caught.value.directory_state == "missing"


def test_file_is_not_accepted_as_a_project_directory(tmp_path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(file_path)
    assert caught.value.directory_state == "not_directory"


def test_unreadable_directory_has_a_typed_unavailable_error(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "unreadable"
    directory.mkdir()
    monkeypatch.setattr("hub.project_workspace.os.access", lambda *args: False)
    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(directory)
    assert caught.value.directory_state == "unreadable"


def test_filesystem_root_is_rejected() -> None:
    root = Path(Path.cwd().anchor)
    with pytest.raises(ProjectPathError, match="filesystem root"):
        canonicalize_project_directory(root)


def test_hub_data_directory_and_its_descendants_are_rejected(tmp_path) -> None:
    hub_data = tmp_path / "hub-data"
    nested = hub_data / "nested"
    nested.mkdir(parents=True)

    with pytest.raises(ProjectPathError, match="Hub data"):
        canonicalize_project_directory(nested, hub_data_directory=hub_data)


def test_project_containing_the_hub_data_directory_is_rejected(tmp_path) -> None:
    project = tmp_path / "project"
    hub_data = project / ".hub-data"
    hub_data.mkdir(parents=True)

    with pytest.raises(ProjectPathError, match="Hub data"):
        canonicalize_project_directory(project, hub_data_directory=hub_data)


def test_nested_agentweave_worktree_is_rejected(tmp_path) -> None:
    nested = tmp_path / "repo" / ".agentweave" / "worktrees" / "writer"
    nested.mkdir(parents=True)
    with pytest.raises(ProjectPathError, match="worktree"):
        canonicalize_project_directory(nested)


def test_nested_agentweave_task_checkout_is_rejected(tmp_path) -> None:
    """Task 6.8. A task checkout is the same hazard as an agent worktree by a different path:
    registering one as a project would give a project a working directory that another project's
    git owns and removes at release. The refusal walked for `.agentweave/worktrees` only.
    """
    nested = tmp_path / "repo" / ".agentweave" / "tasks" / "task-ab12cd34ef56"
    nested.mkdir(parents=True)
    with pytest.raises(ProjectPathError, match="checkout"):
        canonicalize_project_directory(nested)


def test_a_directory_merely_named_tasks_is_still_registrable(tmp_path) -> None:
    """The pair is what refuses, not the word. `tasks/` is an ordinary directory name and a
    project that has one — outside `.agentweave/` — must stay registrable, or this guard breaks
    real repositories to defend against a shape they do not have.
    """
    ordinary = tmp_path / "repo" / "tasks" / "sub"
    ordinary.mkdir(parents=True)

    assert canonicalize_project_directory(ordinary).path == ordinary.resolve()


@pytest.mark.parametrize(
    "relative",
    [
        "../escape",
        "a/../../escape",
        "/absolute",
        "bad\x00name",
        # A leading `~` is contained *here* — Python does not expand it, so it resolves to a
        # literal directory under the root and every containment check passes. It stops being
        # contained wherever it is expanded, and the resolved path becomes a spawned process's
        # cwd. `hub/tests/test_agents.py` has asserted the refusal since before the containment
        # check existed, but it was reaching a different guard: writing agents were refused a
        # `work_dir` outright, so no tilde ever reached this function. Pinned here so the rule
        # holds on its own rather than as a side effect of an unrelated one.
        "~/projects/secret",
        "~root/projects/secret",
    ],
)
def test_relative_resolution_rejects_escape_absolute_and_control_input(
    tmp_path, relative: str
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    canonical = canonicalize_project_directory(root)
    workspace = ProjectWorkspace(
        project_id="proj-safe",
        root=canonical.path,
        path_key=canonical.path_key,
    )

    with pytest.raises(ProjectPathError):
        workspace.resolve_relative(relative)


def test_relative_resolution_rejects_a_symlink_escape(tmp_path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks/junctions unavailable: {exc}")

    canonical = canonicalize_project_directory(root)
    workspace = ProjectWorkspace("proj-safe", canonical.path, canonical.path_key)
    with pytest.raises(ProjectPathError, match="escapes"):
        workspace.resolve_relative(os.path.join("link", "child"))


def test_relative_resolution_accepts_a_contained_path(tmp_path) -> None:
    root = tmp_path / "project"
    child = root / "src"
    child.mkdir(parents=True)
    canonical = canonicalize_project_directory(root)
    workspace = ProjectWorkspace("proj-safe", canonical.path, canonical.path_key)

    assert workspace.resolve_relative("src") == child.resolve(strict=True)


@pytest.mark.asyncio
async def test_database_workspace_resolver_revalidates_marker_identity(app, tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(root)
        workspace = await resolve_project_workspace(session, project.id)
        assert workspace.root == root.resolve()

    marker = root / ".agentweave" / "project.json"
    marker.write_text('{"version": 1, "project_id": "proj-other"}\n', encoding="utf-8")
    async with async_session_factory() as session:
        with pytest.raises(ProjectIdentityConflict):
            await resolve_project_workspace(session, project.id)
