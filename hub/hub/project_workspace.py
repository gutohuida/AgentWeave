"""Canonical directory identity and safe project-local path resolution."""

from __future__ import annotations

import json
import ntpath
import os
import posixpath
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Project

PROJECT_MARKER_VERSION = 1
PROJECT_MARKER_PATH = Path(".agentweave") / "project.json"


class ProjectWorkspaceError(RuntimeError):
    """Base typed error exposed by project workspace operations."""

    def __init__(self, message: str, *, code: str, directory_state: str) -> None:
        self.code = code
        self.directory_state = directory_state
        super().__init__(message)


class ProjectPathError(ProjectWorkspaceError):
    def __init__(self, message: str, *, code: str = "invalid_project_path") -> None:
        super().__init__(message, code=code, directory_state="unbound")


class ProjectWorkspaceUnavailable(ProjectWorkspaceError):  # noqa: N818 - stable public API
    pass


class ProjectIdentityConflict(ProjectWorkspaceError):  # noqa: N818 - stable public API
    def __init__(self, message: str, *, code: str = "project_identity_conflict") -> None:
        super().__init__(message, code=code, directory_state="identity_conflict")


@dataclass(frozen=True)
class CanonicalProjectPath:
    path: Path
    path_key: str


@dataclass(frozen=True)
class ProjectWorkspace:
    project_id: str
    root: Path
    path_key: str

    @property
    def worktree_root(self) -> Path:
        return self.root / ".agentweave" / "worktrees"

    def resolve_relative(self, relative: str | Path) -> Path:
        raw = str(relative)
        _reject_control_characters(raw)
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ProjectPathError("project-relative path must be contained and traversal-free")
        # A leading `~` is contained here and not necessarily contained later. Python does not
        # expand it, so `~/projects/secret` resolves under the root and passes the check below —
        # but the resolved path is handed to a spawned process as its cwd and appears in command
        # arguments, and anything that expands it reaches the operator's home directory instead.
        # Refused rather than normalised: the caller meant something, and quietly reinterpreting
        # a path as a literal directory named `~` is its own surprise.
        #
        # Only the first component: expansion applies there, and `backup~` is a real directory
        # name that nothing would expand.
        if candidate.parts and candidate.parts[0].startswith("~"):
            raise ProjectPathError("project-relative path must not begin with '~'")
        resolved = (self.root / candidate).resolve(strict=False)
        if not _is_within(resolved, self.root):
            raise ProjectPathError("resolved path escapes the project workspace")
        return resolved


def canonical_path_key(path: str | Path, *, platform: Optional[str] = None) -> str:
    """Return a host-semantic comparison key for an already canonical absolute path."""
    raw = str(path)
    target = platform or ("windows" if os.name == "nt" else "posix")
    if target == "windows":
        normalized = ntpath.normcase(ntpath.normpath(raw.replace("/", "\\")))
        return f"windows:{normalized}"
    if target == "posix":
        return f"posix:{posixpath.normpath(raw)}"
    raise ValueError(f"unsupported path platform: {target}")


def configured_workspace_root() -> Optional[Path]:
    """Return the explicitly configured container workspace root, or None.

    Native local mode leaves ``AW_WORKSPACE_ROOT`` unset and imposes no
    containment restriction; the Hub never guesses host/container mappings.
    """
    from .config import settings

    raw = settings.aw_workspace_root.strip()
    if not raw:
        return None
    _reject_control_characters(raw)
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ProjectPathError("configured workspace root must be an absolute path")
    return root.resolve(strict=False)


def _require_workspace_containment(candidate: Path, root: Path) -> None:
    if not _is_within(candidate, root):
        raise ProjectWorkspaceUnavailable(
            f"project directory is not visible beneath the configured workspace root: "
            f"{root}; mount the host directory into the container at that root "
            f"(AW_WORKSPACE_ROOT) before registering it",
            code="project_workspace_not_mounted",
            directory_state="not_mounted",
        )


def canonicalize_project_directory(
    raw_path: str | Path,
    *,
    hub_data_directory: Optional[str | Path] = None,
    workspace_root: Optional[str | Path] = None,
) -> CanonicalProjectPath:
    raw = str(raw_path)
    _reject_control_characters(raw)
    supplied = Path(raw).expanduser()
    if not supplied.is_absolute():
        raise ProjectPathError("project directory must be an absolute path")

    root: Optional[Path] = None
    if workspace_root is not None:
        root = Path(workspace_root).expanduser().resolve(strict=False)
        _require_workspace_containment(supplied.resolve(strict=False), root)

    try:
        canonical = supplied.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectWorkspaceUnavailable(
            f"project directory does not exist: {supplied}",
            code="project_workspace_missing",
            directory_state="missing",
        ) from exc
    except (PermissionError, OSError) as exc:
        raise ProjectWorkspaceUnavailable(
            f"project directory is unreadable: {supplied}",
            code="project_workspace_unreadable",
            directory_state="unreadable",
        ) from exc

    if not canonical.is_dir():
        raise ProjectWorkspaceUnavailable(
            f"project path is not a directory: {canonical}",
            code="project_workspace_not_directory",
            directory_state="not_directory",
        )
    if root is not None:
        _require_workspace_containment(canonical, root)
    if canonical == Path(canonical.anchor):
        raise ProjectPathError("filesystem root cannot be registered as a project")
    if not os.access(canonical, os.R_OK | os.X_OK):
        raise ProjectWorkspaceUnavailable(
            f"project directory is unreadable: {canonical}",
            code="project_workspace_unreadable",
            directory_state="unreadable",
        )

    folded_parts = [part.casefold() for part in canonical.parts]
    for index in range(len(folded_parts) - 1):
        if folded_parts[index : index + 2] == [".agentweave", "worktrees"]:
            raise ProjectPathError("nested AgentWeave worktree cannot be registered")

    if hub_data_directory is not None:
        hub_data = Path(hub_data_directory).expanduser().resolve(strict=False)
        if _is_within(canonical, hub_data) or _is_within(hub_data, canonical):
            raise ProjectPathError("Hub data directory cannot be registered as project content")

    return CanonicalProjectPath(canonical, canonical_path_key(canonical))


async def resolve_project_workspace(
    session: AsyncSession,
    project_id: str,
    *,
    hub_data_directory: Optional[str | Path] = None,
    workspace_root: Optional[str | Path] = None,
) -> ProjectWorkspace:
    if workspace_root is None:
        workspace_root = configured_workspace_root()
    project = await session.get(Project, project_id)
    if project is None:
        raise ProjectPathError("unknown project", code="project_not_found")
    if not project.working_directory or not project.path_key:
        project.directory_state = "unbound"
        raise ProjectWorkspaceUnavailable(
            "project has no bound working directory",
            code="project_workspace_unbound",
            directory_state="unbound",
        )

    try:
        canonical = canonicalize_project_directory(
            project.working_directory,
            hub_data_directory=hub_data_directory,
            workspace_root=workspace_root,
        )
    except ProjectWorkspaceUnavailable as exc:
        project.directory_state = exc.directory_state
        raise
    if canonical.path_key != project.path_key:
        project.directory_state = "identity_conflict"
        raise ProjectIdentityConflict("project directory resolves to a different canonical path")

    _validate_marker(canonical.path, project.id)
    project.directory_state = "available"
    project.last_seen_at = datetime.now(timezone.utc)
    return ProjectWorkspace(project.id, canonical.path, canonical.path_key)


def raise_workspace_http_error(exc: ProjectWorkspaceError) -> NoReturn:
    """Convert a typed workspace error into the shared HTTP 409/422 response."""
    if isinstance(exc, (ProjectIdentityConflict, ProjectWorkspaceUnavailable)):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
            "directory_state": exc.directory_state,
        },
    ) from exc


def _validate_marker(root: Path, project_id: str) -> None:
    marker_path = root / PROJECT_MARKER_PATH
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectIdentityConflict(
            f"project marker is missing or invalid: {marker_path}", code="project_marker_invalid"
        ) from exc
    if payload != {"version": PROJECT_MARKER_VERSION, "project_id": project_id}:
        raise ProjectIdentityConflict("project marker identifies a different project")


def _reject_control_characters(value: str) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProjectPathError("project path contains control characters")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
