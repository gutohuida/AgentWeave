"""A build that lands as one GitHub pull request (`a-build-lands-as-one-pull-request`).

This module is the Hub's only client of a code host, and it talks to GitHub through the user's own
GitHub CLI login (`gh`), never a token of its own.

What is here so far is the readiness check (FR-2): PR landing is refused, when it is turned on and
when a build landing as a pull request starts, unless the project directory has a GitHub remote, the
GitHub CLI is installed and it is logged in. It is found at the start, not at the first approved
task after hours of work.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import traces

#: The project setting that has to be on for a build to land as a pull request (FR-1), as the
#: settings route names it.
SETTING = "pr_landing"

#: How long one GitHub CLI or git call of the readiness check may take.
CHECK_TIMEOUT_SECONDS = 20

NO_GITHUB_REMOTE = "no_github_remote"
NO_GITHUB_CLI = "no_github_cli"
GITHUB_CLI_NOT_LOGGED_IN = "github_cli_not_logged_in"

# `https://github.com/o/r(.git)`, `git@github.com:o/r.git`, `ssh://git@github.com/o/r.git`.
_GITHUB_URL = re.compile(r"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|[^@/]+@)github\.com[:/]")


@dataclass(frozen=True)
class Problem:
    """Why PR landing cannot be used in a project: one of the three things it needs is missing."""

    code: str
    message: str


def is_github_url(url: str) -> bool:
    return bool(_GITHUB_URL.match((url or "").strip()))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return traces.run(
        ["git", *args],
        ok_codes=(0, 1, 2, 128),
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=CHECK_TIMEOUT_SECONDS,
    )


def github_remote(root: Path) -> Optional[str]:
    """The name of the project directory's GitHub remote, `origin` first when it is one; None when
    no remote points at GitHub (or the directory is not a repository)."""
    try:
        listed = _git(root, "remote")
    except (OSError, subprocess.SubprocessError):
        return None
    if listed.returncode != 0:
        return None
    names: List[str] = [line.strip() for line in (listed.stdout or "").splitlines() if line.strip()]
    names.sort(key=lambda name: name != "origin")
    for name in names:
        try:
            url = _git(root, "remote", "get-url", name)
        except (OSError, subprocess.SubprocessError):
            continue
        if url.returncode == 0 and is_github_url(url.stdout or ""):
            return name
    return None


def gh_executable() -> Optional[str]:
    """The GitHub CLI on the Hub's PATH, or None."""
    return shutil.which("gh")


def gh_logged_in(gh: str) -> bool:
    """Whether the GitHub CLI holds a login for github.com (`gh auth status` exits 0)."""
    try:
        answered = traces.run(
            [gh, "auth", "status", "--hostname", "github.com"],
            ok_codes=(0, 1),
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return answered.returncode == 0


def readiness_problem(root: Path) -> Optional[Problem]:
    """What stops a build landing as a pull request from this project directory, or None when it
    can: a GitHub remote, the GitHub CLI installed, and logged in, checked in that order (FR-2).
    Runs git and the CLI, so it is called off the event loop (`blocking.run`)."""
    if github_remote(root) is None:
        return Problem(
            NO_GITHUB_REMOTE,
            f"the project directory {root} has no GitHub remote: PR landing pushes the build "
            "branch to GitHub, so a remote pointing at github.com has to exist first",
        )
    gh = gh_executable()
    if gh is None:
        return Problem(
            NO_GITHUB_CLI,
            "the GitHub CLI (gh) is not installed, or not on the Hub's PATH: PR landing opens "
            "and updates the pull request through it",
        )
    if not gh_logged_in(gh):
        return Problem(
            GITHUB_CLI_NOT_LOGGED_IN,
            "the GitHub CLI is not logged in to github.com: run `gh auth login`, since PR landing "
            "uses your own login",
        )
    return None
