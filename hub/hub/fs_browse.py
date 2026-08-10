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

import ctypes
import os
import string
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


def list_roots() -> List[DirectoryEntry]:
    """The available starting points for browsing (composer/chrome refinement §9.1) — every
    mounted drive letter on Windows via `GetLogicalDrives`'s bitmask (stdlib `ctypes`, no new
    dependency), or the single `/` root elsewhere.

    A configured workspace root (`AW_WORKSPACE_ROOT`, Docker mode) replaces the OS-level
    roots entirely rather than filtering them: an OS root is always an *ancestor* of a real
    workspace root, never a descendant, so filtering by containment would silently return no
    roots at all. The workspace root itself is the only real starting point browsing can
    offer in that mode — the OS root exists but `list_directory` would refuse it anyway."""
    if os.name == "nt":
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        except Exception:
            bitmask = 0
        roots = [
            DirectoryEntry(name=f"{letter}:\\", path=f"{letter}:\\")
            for index, letter in enumerate(string.ascii_uppercase)
            if bitmask & (1 << index)
        ]
    else:
        roots = [DirectoryEntry(name="/", path="/")]

    configured_root = configured_workspace_root()
    if configured_root is None:
        return roots
    return [DirectoryEntry(name=str(configured_root), path=str(configured_root))]


def list_directory(raw_path: str) -> DirectoryListing:
    try:
        _reject_control_characters(raw_path)
    except ProjectPathError as exc:
        raise DirectoryBrowseError(str(exc)) from exc
    supplied = Path(raw_path).expanduser()
    # Windows' pathlib.is_absolute() requires a drive letter, so a bare "/" (or "/foo") is
    # "anchored" (has a root) but not "absolute" by that definition — rejecting it here would
    # refuse a reasonable browsing starting point on this platform (live-verified: the
    # composer's own directory picker defaults new browsing to "/"). resolve() correctly fills
    # in the current drive for an anchored-but-driveless path; a genuinely relative path
    # (no leading separator at all, e.g. "relative/path") has no root and is still refused.
    if not supplied.root:
        raise DirectoryBrowseError("path must be absolute")
    resolved = supplied.resolve(strict=False)

    root = configured_workspace_root()
    if root is not None and not _is_within(resolved, root):
        raise DirectoryBrowseError(f"{resolved} is outside the configured workspace root ({root})")

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
