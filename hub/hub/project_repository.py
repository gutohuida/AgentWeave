"""A folder AgentWeave makes into a git repository, and the AGENTS.md it starts with.

Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`. A project created in a folder
that did not exist becomes a repository whose first commit holds AGENTS.md alone (FR-1): a
repository with no commit cannot give writing agents their own worktrees, so `git init` alone is
not enough.

**AGENTS.md only where nothing instructs the folder's agents yet (FR-3).** A folder that already
holds an instruction file, or is already an AgentWeave project, belongs to someone who chose how
its agents are told things; a second file from us would contradict or duplicate theirs.
`should_create_agents_md` is that rule on its own, so every path that makes a repository applies
the same one.

**`.agentweave/` is ignored whole in a repository we create (FR-2).** `repo_hygiene` ignores only
the Hub's own sub-folders, because in someone else's repository `.agentweave/` may hold things they
track. A repository AgentWeave creates has no such history, so the whole folder is ignored, through
`.git/info/exclude` like the rest (never a committed `.gitignore`: the first commit holds AGENTS.md
and nothing else). The line sits outside `repo_hygiene`'s marked block, which that module rewrites
on every open.

**An existing folder is made a repository only on the operator's word (FR-5, FR-6).** Its first
commit would hold whatever is already there, so `preview_first_commit` names every file it would
hold first, by the same ignore rules the repository will have, and writes nothing into the folder:
git reads the folder through a scratch repository kept outside it.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from .repo_hygiene import EXCLUDE_BEGIN, EXCLUDE_END, EXCLUDE_PATTERNS, seed_repo_excludes
from .subprocess_windows import no_console_kwargs

logger = logging.getLogger(__name__)

AGENTS_MD = "AGENTS.md"

#: The branch a repository AgentWeave creates starts on.
MAIN_BRANCH = "main"

#: Any of these in a folder means its agents are already instructed (FR-3). The marker means it is
#: already an AgentWeave project, whose instructions are the Hub's.
EXISTING_INSTRUCTIONS = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    ".agentweave/project.json",
)

PROJECT_INSTRUCTIONS_HEADING = "## Project instructions"

#: FR-4: a short AgentWeave section, then an empty place for the project's own instructions.
AGENTS_MD_TEMPLATE = f"""# Working on this project with AgentWeave

This project is worked on through AgentWeave. Agents take their tasks from the AgentWeave Hub, each
in its own git worktree and branch; approved work is merged into the main branch.

- Specifications live in `spec/`: changes being built in `spec/changes/`, current behaviour in
  `spec/capabilities/`. Read the specification a task names before building against it.
- `.agentweave/` holds the Hub's own working files. Git ignores it; do not commit or edit it.

{PROJECT_INSTRUCTIONS_HEADING}

<!-- This project's own instructions for its agents go below. -->
"""

_EXCLUDE_WHOLE_FOLDER = (
    "# AgentWeave created this repository: its working folder is ignored whole.\n.agentweave/\n"
)

#: Used only where git has no identity configured, so a first commit never fails for want of one.
_FALLBACK_IDENTITY = ("-c", "user.name=AgentWeave", "-c", "user.email=agentweave@localhost")

_GIT_TIMEOUT_SECONDS = 30


class RepositoryInitError(Exception):
    """Git refused to make the folder a repository; the message quotes what it said."""


class GitUnavailableError(RepositoryInitError):
    """There is no git to run (the Hub's Docker image ships none); nothing was written."""


#: The instruction files alone, without the marker.
_INSTRUCTION_FILES = tuple(
    name for name in EXISTING_INSTRUCTIONS if not name.startswith(".agentweave/")
)


def should_create_agents_md(root: Path, *, marker_counts: bool = True) -> bool:
    """FR-3: whether *root* holds none of the files that already instruct its agents.

    `marker_counts=False` is for a folder whose marker this Hub wrote when it registered it: that
    marker says only that the operator opened the folder here, not that it was an AgentWeave
    project before (operator, 2026-11-10, NPSAG-2). A marker the folder carried in still counts.
    """
    names = EXISTING_INSTRUCTIONS if marker_counts else _INSTRUCTION_FILES
    return not any((root / name).exists() for name in names)


def preview_first_commit(root: Path) -> list[str]:
    """Every file a first commit of *root* would hold, sorted, writing nothing into *root*.

    The repository's own ignore rules (the whole `.agentweave/` folder, `repo_hygiene`'s block, the
    folder's own `.gitignore` files and the user's global excludes) decide, exactly as `git add`
    would under `initialise_repository`: git lists the folder through a scratch repository made
    outside it. AGENTS.md, when the rule would create it, is not on disk yet and is not listed.
    """
    if (root / ".git").exists():
        raise RepositoryInitError(f"{root} is already a git repository")
    scratch = Path(tempfile.mkdtemp(prefix="agentweave-preview-"))
    try:
        git_dir = scratch / "git"
        _run(scratch, "init", "--quiet", "--bare", str(git_dir))
        info = git_dir / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text(_exclude_text(), encoding="utf-8", newline="\n")
        listed = _git(
            root,
            f"--git-dir={git_dir}",
            f"--work-tree={root}",
            "-c",
            "core.bare=false",
            "ls-files",
            # Relative to the folder whatever git makes of the process's directory.
            "--full-name",
            "--others",
            "--exclude-standard",
            "-z",
        )
        if listed.returncode != 0:
            said = (listed.stderr or listed.stdout or "").strip()
            raise RepositoryInitError(f"could not list the files in {root}: {said}")
        return sorted(name for name in listed.stdout.split("\0") if name)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def initialise_repository(
    root: Path, *, files: Sequence[str] = (), agents_md: Optional[bool] = None
) -> Optional[str]:
    """Make *root* a git repository on `MAIN_BRANCH` and make its first commit.

    The commit holds AGENTS.md when the rule above creates it (or *agents_md* says so, for a
    caller that has applied the rule itself), plus *files* (paths relative to *root*, for a caller
    that has shown the operator what it will commit). Nothing else is staged. Returns the branch
    the commit is on, or None when there was nothing to commit.

    Refuses a folder that is already a repository: making a first commit there is not this.
    """
    if (root / ".git").exists():
        raise RepositoryInitError(f"{root} is already a git repository")

    _run(root, "init", "--quiet")
    _run(root, "symbolic-ref", "HEAD", f"refs/heads/{MAIN_BRANCH}")
    _ignore_whole_hub_folder(root)
    seed_repo_excludes(root)

    staged = list(files)
    if agents_md is None:
        agents_md = should_create_agents_md(root)
    if agents_md:
        (root / AGENTS_MD).write_text(AGENTS_MD_TEMPLATE, encoding="utf-8", newline="\n")
        staged.insert(0, AGENTS_MD)
    if not staged:
        return None

    # Through stdin, not the command line: an existing folder's list can outgrow Windows' limit.
    _run(root, "add", "--pathspec-from-file=-", "--pathspec-file-nul", input="\0".join(staged))
    _run(
        root,
        *_identity_options(root),
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "Start the project with AgentWeave",
    )
    return MAIN_BRANCH


def _ignore_whole_hub_folder(root: Path) -> None:
    target = root / ".git" / "info" / "exclude"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    target.write_text(f"{existing}{separator}{_EXCLUDE_WHOLE_FOLDER}", encoding="utf-8")


def _exclude_text() -> str:
    """What `_ignore_whole_hub_folder` and `seed_repo_excludes` together leave in a new repository."""
    block = "\n".join([EXCLUDE_BEGIN, *EXCLUDE_PATTERNS, EXCLUDE_END])
    return f"{_EXCLUDE_WHOLE_FOLDER}{block}\n"


def _identity_options(root: Path) -> tuple[str, ...]:
    for key in ("user.name", "user.email"):
        if _git(root, "config", "--get", key).returncode != 0:
            return _FALLBACK_IDENTITY
    return ()


def _run(root: Path, *args: str, input: Optional[str] = None) -> None:
    result = _git(root, *args, input=input)
    if result.returncode != 0:
        said = (result.stderr or result.stdout or "").strip()
        raise RepositoryInitError(f"git {' '.join(args)} failed in {root}: {said}")


def _git(root: Path, *args: str, input: Optional[str] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            input=input,
            capture_output=True,
            # Git speaks UTF-8 paths (`-z` leaves them unquoted); the locale's codec would not
            # round-trip a non-ASCII name from the preview back into `git add`.
            encoding="utf-8",
            errors="surrogateescape",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
            **no_console_kwargs(),
        )
    except FileNotFoundError as exc:
        raise GitUnavailableError(f"git is not installed where the Hub runs: {exc}") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryInitError(f"could not run git in {root}: {exc}") from exc
