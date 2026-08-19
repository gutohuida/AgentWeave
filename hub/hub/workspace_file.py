"""Workspace file content reading for the panel shell's files tab.

See openspec/changes/2026-08-18-one-shell-three-panels/design.md's D7: a path is
readable if and only if it is a member of what `list_workspace_paths` already
decided is *visible* — not a second, independently reasoned traversal check.
Membership alone is not a content guarantee, though: `git ls-files` lists a
tracked or untracked-not-ignored symlink by its own path, not by where it
points, so a listed path can still be a symlink whose target lives outside the
workspace. The resolved filesystem path is therefore additionally required to
fall under the workspace root via `ProjectWorkspace.resolve_relative` — the
same established primitive `spec_documents.py` already uses for every other
project-relative read (it "refuses absolute paths, traversal, control
characters and symlink escapes" per that module's own docstring), not a new
bespoke check invented for this endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .project_workspace import ProjectPathError, ProjectWorkspace
from .workspace_paths import list_workspace_paths

_BINARY_SNIFF_BYTES = 8_000


class WorkspaceFileError(RuntimeError):
    """Base for workspace-file read failures."""


class WorkspaceFileNotFoundError(WorkspaceFileError):
    """*path* is not a member of this workspace's visible listing."""


class WorkspaceFileTooLargeError(WorkspaceFileError):
    def __init__(self, size: int, bound: int) -> None:
        super().__init__(f"file is {size} bytes, exceeding the {bound} byte limit")
        self.size = size
        self.bound = bound


@dataclass
class WorkspaceFileContent:
    path: str
    binary: bool
    size: int
    content: Optional[str]


def read_workspace_file(
    workspace: ProjectWorkspace, path: str, *, max_size: int
) -> WorkspaceFileContent:
    """Read *path* if and only if it is a member of this workspace's visible listing.

    Raises `WorkspaceFileNotFoundError` for anything absent from that listing — a
    traversal attempt, a symlink resolving outside the workspace, or a
    `.gitignore`d path are all indistinguishable from "not in the workspace" by
    design. Raises `WorkspaceFileTooLargeError` over *max_size*, checked before any
    content is read so an oversized file is never partially returned.
    """
    if path not in list_workspace_paths(workspace.root):
        raise WorkspaceFileNotFoundError(path)

    try:
        resolved = workspace.resolve_relative(path)
    except ProjectPathError as exc:
        raise WorkspaceFileNotFoundError(path) from exc

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise WorkspaceFileNotFoundError(path) from exc
    if size > max_size:
        raise WorkspaceFileTooLargeError(size, max_size)

    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise WorkspaceFileNotFoundError(path) from exc

    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        return WorkspaceFileContent(path=path, binary=True, size=size, content=None)
    return WorkspaceFileContent(
        path=path, binary=False, size=size, content=data.decode("utf-8", errors="replace")
    )
