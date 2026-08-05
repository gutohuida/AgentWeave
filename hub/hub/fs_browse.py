"""Directory listing for the project-directory picker (`GET /api/v1/fs/list`).

Browsers do not give a web page an absolute filesystem path — `showDirectoryPicker()` returns
a handle and deliberately withholds it — so a client-side picker cannot produce what project
registration needs. This module lists directories from the Hub process itself instead.

Directories only, never file names or contents. Symlinks are not followed: a directory entry
that is a symlink is excluded rather than traversed, so a listing can never escape its own
subtree through one. Where a workspace root is configured (`AW_WORKSPACE_ROOT`, the same
containment `project_workspace.py` enforces for project registration), listings stay beneath
it; native local mode leaves it unset and imposes no restriction. An unreadable directory
returns an empty listing with a stated reason rather than raising — the operator keeps
browsing from where they were, per design.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .project_workspace import (
    ProjectPathError,
    _is_within,
    _reject_control_characters,
    configured_workspace_root,
)


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    path: str


@dataclass(frozen=True)
class DirectoryListing:
    path: str
    parent: Optional[str]
    entries: List[DirectoryEntry]
    reason: Optional[str] = None


class DirectoryBrowseError(RuntimeError):
    """Raised only for a request the Hub refuses outright (bad path, outside workspace
    root) — never for an unreadable directory, which returns a listing with a reason
    instead (see module docstring)."""


def list_directory(raw_path: str) -> DirectoryListing:
    try:
        _reject_control_characters(raw_path)
    except ProjectPathError as exc:
        raise DirectoryBrowseError(str(exc)) from exc
    supplied = Path(raw_path).expanduser()
    if not supplied.is_absolute():
        raise DirectoryBrowseError("path must be absolute")
    resolved = supplied.resolve(strict=False)

    root = configured_workspace_root()
    if root is not None and not _is_within(resolved, root):
        raise DirectoryBrowseError(
            f"{resolved} is outside the configured workspace root ({root})"
        )

    parent = str(resolved.parent) if resolved.parent != resolved else None

    try:
        with os.scandir(resolved) as scanned:
            # follow_symlinks=False: a symlinked directory is excluded rather than
            # traversed, so a listing can never escape its own subtree through one.
            dir_entries = sorted(
                (entry for entry in scanned if entry.is_dir(follow_symlinks=False)),
                key=lambda entry: entry.name.lower(),
            )
    except OSError as exc:
        return DirectoryListing(path=str(resolved), parent=parent, entries=[], reason=str(exc))

    entries = [
        DirectoryEntry(name=entry.name, path=str(resolved / entry.name)) for entry in dir_entries
    ]
    return DirectoryListing(path=str(resolved), parent=parent, entries=entries)
