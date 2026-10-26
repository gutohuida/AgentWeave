"""Workspace path listing — git-backed, `.gitignore`-respecting file/directory enumeration.

Feeds the composer's `@path` trigger (and, filtered client-side to `.claude/skills/`, its
`$skill` trigger) — see
openspec/changes/composer-intelligence/design.md's Decision 1 for why this shells out to git
rather than hand-rolling a `.gitignore` parser.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from . import binaries
from .subprocess_windows import no_console_kwargs

_GIT_TIMEOUT_SECONDS = 10


def list_workspace_paths(repo_root: Path) -> List[str]:
    """Return every tracked-or-untracked-but-not-ignored path under *repo_root*, sorted.

    Returns an empty list, not an error, when *repo_root* is not a usable git working
    tree (no git binary on PATH, or `repo_root` isn't inside one) — a non-git project
    simply gets no `@path` matches rather than a broken composer.
    """
    if binaries.which("git") is None:
        return []
    try:
        result = subprocess.run(
            # quotepath off and UTF-8 out: git otherwise writes `café.md` as `"caf\303\251.md"` and
            # this machine's locale codepage would decode the rest of it (F777).
            [
                "git",
                "-c",
                "core.quotepath=off",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return sorted(line for line in result.stdout.splitlines() if line)
