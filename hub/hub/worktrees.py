"""Per-agent workspace isolation via git worktrees (task 5, design.md Decision 7).

*Why worktrees, not locks* (Decision 7): in a shared working directory there is no
merge — two agents editing one folder produce a **lost update**, not a conflict. A
worktree does not remove that risk, it converts a silent loss into a visible,
resolvable conflict. Each writing agent gets its own worktree on its own branch
(``agentweave/<agent>``), sharing the primary checkout's object database. An agent
declared ``read_only`` in its config (new key, task 5.2) never gets one and shares the
primary checkout directly instead.

Every git call here is plumbing or a narrowly-scoped porcelain command run against an
explicit ``cwd`` — never the Hub process's own working directory implicitly, and never
anything that touches the *primary* checkout's index or HEAD (matching the convention
`src/agentweave/transport/git.py` already established for the same reason: a linked
worktree is a live, independent working copy, and the primary checkout must stay
whatever the operator/CI left it as).

This module is deliberately independent of any DB/session layer — it only needs a repo
root, an agent name, and (for the read-only decision) that agent's already-resolved
config dict, the same shape `launchability.get_agent_config` already returns.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BRANCH_PREFIX = "agentweave/"

# Directories worth symlinking into a fresh worktree rather than reinstalling
# (task 5.2) — kept small and explicit. Extend only for directories that are both
# expensive to regenerate and safe to share read-only across concurrent worktrees.
SHARED_DEPENDENCY_DIRS = ("node_modules", ".venv", "venv")

_GIT_TIMEOUT_SECONDS = 30
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


class GitCommandError(RuntimeError):
    """A git subprocess exited non-zero when the caller required success."""

    def __init__(self, args: List[str], returncode: int, stderr: str) -> None:
        self.git_args = args
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}")


class IsolationUnavailableError(RuntimeError):
    """A writing agent cannot be given the isolated checkout the spec requires."""


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if check and result.returncode != 0:
        raise GitCommandError(list(args), result.returncode, result.stderr)
    return result


def is_git_repo(path: Path) -> bool:
    """Best-effort check: is *path* a usable git working tree?

    Read-only agents do not need this check. A writing agent fails closed when it is
    false because sharing the primary directory would violate workspace isolation.
    """
    if shutil.which("git") is None or not path.exists():
        return False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def validate_agent_name(agent: str) -> None:
    """Reject names that cannot safely become both a path component and git ref suffix."""
    if not _AGENT_NAME_RE.fullmatch(agent) or agent.lower() == "user":
        raise ValueError(
            "invalid or reserved agent name; expected 1-32 letters, digits, underscores, "
            "or hyphens (except 'user')"
        )


def worktree_root(repo_root: Path) -> Path:
    return repo_root / ".agentweave" / "worktrees"


def worktree_path(repo_root: Path, agent: str) -> Path:
    validate_agent_name(agent)
    return worktree_root(repo_root) / agent


def branch_name(agent: str) -> str:
    validate_agent_name(agent)
    return f"{BRANCH_PREFIX}{agent}"


def is_writing_agent(config: Dict[str, Any]) -> bool:
    """Isolation is the default; sharing the primary checkout is the opt-in
    (Decision 7's own mitigation: "isolate only agents that *write*").
    """
    return not bool(config.get("read_only"))


def _symlink_shared_dependencies(repo_root: Path, worktree: Path) -> None:
    for name in SHARED_DEPENDENCY_DIRS:
        source = repo_root / name
        if not source.is_dir() or source.is_symlink():
            continue
        target = worktree / name
        if target.exists() or target.is_symlink():
            continue
        try:
            target.symlink_to(source, target_is_directory=True)
        except OSError:
            # Windows without Developer Mode / admin rights can't create symlinks —
            # degrade to "no shared deps" rather than fail worktree provisioning;
            # the agent's own first turn can still install locally if it needs to.
            logger.info(
                "Could not symlink %s into %s's worktree (no privilege?) — "
                "the agent will need to install its own copy if it needs it.",
                name,
                worktree,
            )
            continue


def _registered_worktree_branch(repo_root: Path, path: Path) -> Optional[str]:
    """Return the branch registered at *path*, without following path aliases."""
    result = _run_git(repo_root, "worktree", "list", "--porcelain")
    expected_path = path.absolute()
    record: Dict[str, str] = {}

    for raw_line in [*result.stdout.splitlines(), ""]:
        line = raw_line.strip()
        if line:
            key, _, value = line.partition(" ")
            record[key] = value
            continue
        registered_path = record.get("worktree")
        if registered_path and Path(registered_path).absolute() == expected_path:
            return record.get("branch")
        record = {}
    return None


def ensure_worktree(repo_root: Path, agent: str) -> Path:
    """Provision *agent*'s isolated checkout, creating it if absent. Idempotent.

    A branch that already exists (e.g. this agent was released via
    `release_worktree` and is now being reprovisioned) is reused rather than
    recreated from HEAD, so a previously-removed agent resumes its own history
    instead of silently starting over.
    """
    path = worktree_path(repo_root, agent)
    if path.exists():
        expected_ref = f"refs/heads/{branch_name(agent)}"
        if path.is_symlink() or _registered_worktree_branch(repo_root, path) != expected_ref:
            raise IsolationUnavailableError(
                f"refusing existing path {path}: it is not the registered git worktree "
                f"for {expected_ref}"
            )
        return path

    # A worktree directory can be gone (manually deleted, or removed by something
    # other than `release_worktree`) while git's own `.git/worktrees/<name>` metadata
    # still references it — prune first so `worktree add` doesn't refuse to proceed.
    _run_git(repo_root, "worktree", "prune", check=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    branch = branch_name(agent)

    branch_exists = (
        _run_git(repo_root, "rev-parse", "--verify", "--quiet", branch, check=False).returncode == 0
    )
    if branch_exists:
        # A released branch with no work beyond the primary checkout can safely catch
        # up before it is reused. Preserve it unchanged when it still carries unique
        # commits: those are the removed agent's explicitly retained work.
        is_ancestor = _run_git(
            repo_root, "merge-base", "--is-ancestor", branch, "HEAD", check=False
        )
        if is_ancestor.returncode == 0:
            _run_git(repo_root, "branch", "--force", branch, "HEAD")
        _run_git(repo_root, "worktree", "add", str(path), branch)
    else:
        _run_git(repo_root, "worktree", "add", "-b", branch, str(path), "HEAD")

    _symlink_shared_dependencies(repo_root, path)
    return path


def resolve_agent_workspace(repo_root: Path, agent: str, config: Dict[str, Any]) -> Path:
    """Return the directory a spawned *agent* process should use as its cwd.

    Writing agents get an isolated worktree, provisioned here if needed. Read-only
    agents share *repo_root*. Writing agents fail closed when isolation cannot be
    prepared: spawning one in the primary checkout would reintroduce silent lost updates.
    """
    if not is_writing_agent(config):
        return repo_root
    if not is_git_repo(repo_root):
        raise IsolationUnavailableError(
            f"cannot prepare an isolated worktree for {agent!r}: "
            f"{repo_root} is not a usable git repository"
        )
    return ensure_worktree(repo_root, agent)


def _has_uncommitted_changes(worktree: Path) -> bool:
    result = _run_git(worktree, "status", "--porcelain")
    return bool(result.stdout.strip())


def snapshot_worktree(worktree: Path, agent: str) -> Optional[str]:
    """Commit any dirty working-tree state in *worktree* onto the agent's own branch.

    Best-effort, internal safety net — not a user-facing commit meant to pass a
    project's own review gates, hence `--no-verify`: a project's commit-msg/pre-commit
    hook blocking this would silently strand the agent's own work uncommitted, which is
    exactly what this function exists to prevent. Returns the new commit SHA, or `None`
    if there was nothing to commit.
    """
    if not _has_uncommitted_changes(worktree):
        return None
    _run_git(worktree, "add", "-A")
    staged = _run_git(worktree, "diff", "--cached", "--name-only")
    if not staged.stdout.strip():
        return None
    _run_git(
        worktree,
        "-c",
        "user.name=AgentWeave",
        "-c",
        "user.email=agentweave@localhost",
        "commit",
        "--no-verify",
        "-m",
        f"Auto-snapshot: {agent}'s turn",
    )
    sha = _run_git(worktree, "rev-parse", "HEAD")
    return sha.stdout.strip()


def _commits_not_on_head(repo_root: Path, branch: str) -> List[str]:
    result = _run_git(repo_root, "rev-list", f"HEAD..{branch}", check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


@dataclass
class ReleaseResult:
    released: bool
    branch: str
    had_uncommitted_changes: bool = False
    snapshot_commit: Optional[str] = None
    unmerged_commits: List[str] = field(default_factory=list)

    @property
    def has_unmerged_work(self) -> bool:
        return bool(self.unmerged_commits)


def release_worktree(repo_root: Path, agent: str) -> ReleaseResult:
    """Release *agent*'s worktree (task 5.4): remove the checkout directory, but
    never the branch, and never silently — any uncommitted change is snapshotted
    onto the branch first, and any commit the branch carries beyond the primary
    checkout's HEAD is reported back, not discarded.
    """
    path = worktree_path(repo_root, agent)
    branch = branch_name(agent)

    if not path.exists():
        return ReleaseResult(released=False, branch=branch)

    had_uncommitted = _has_uncommitted_changes(path)
    snapshot_commit = snapshot_worktree(path, agent) if had_uncommitted else None

    _run_git(repo_root, "worktree", "remove", "--force", str(path))

    unmerged = _commits_not_on_head(repo_root, branch)
    return ReleaseResult(
        released=True,
        branch=branch,
        had_uncommitted_changes=had_uncommitted,
        snapshot_commit=snapshot_commit,
        unmerged_commits=unmerged,
    )


def list_agent_branches(repo_root: Path) -> List[str]:
    """Return agents with a currently registered checkout, excluding retained branches."""
    result = _run_git(repo_root, "worktree", "list", "--porcelain")
    names: List[str] = []
    record: Dict[str, str] = {}

    def append_record() -> None:
        ref = record.get("branch", "")
        prefix = f"refs/heads/{BRANCH_PREFIX}"
        if not ref.startswith(prefix):
            return
        agent = ref[len(prefix) :]
        if not _AGENT_NAME_RE.fullmatch(agent):
            return
        actual = Path(record.get("worktree", "")).resolve()
        if actual == worktree_path(repo_root, agent).resolve():
            names.append(agent)

    for raw_line in [*result.stdout.splitlines(), ""]:
        line = raw_line.strip()
        if not line:
            append_record()
            record = {}
            continue
        key, _, value = line.partition(" ")
        record[key] = value
    return names


@dataclass
class ConflictReport:
    agents: Tuple[str, str]
    paths: List[str]


def _merge_tree_conflicts(repo_root: Path, branch_a: str, branch_b: str) -> List[str]:
    """Test-merge two branches with `git merge-tree` — plumbing that touches
    neither the working tree nor the index of any checkout — and return the
    conflicted paths, or an empty list if the merge would be clean.
    """
    result = _run_git(
        repo_root, "merge-tree", "--write-tree", "--name-only", branch_a, branch_b, check=False
    )
    if result.returncode == 0:
        return []
    paths: List[str] = []
    # First stdout line is the (partial, conflicted) tree OID; conflicted paths
    # follow, one per line, until the blank line preceding git's human-readable
    # "Auto-merging"/"CONFLICT" messages.
    for line in result.stdout.splitlines()[1:]:
        if not line.strip():
            break
        paths.append(line.strip())
    return paths


def detect_conflicts(repo_root: Path) -> List[ConflictReport]:
    """Pairwise-check every currently-provisioned writing agent's branch against
    every other's, surfacing which agents diverge and on which files
    (hub-native-runtime's "Divergent changes surface as a conflict" scenario).
    """
    agents = sorted(list_agent_branches(repo_root))
    reports: List[ConflictReport] = []
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a, b = agents[i], agents[j]
            paths = _merge_tree_conflicts(repo_root, branch_name(a), branch_name(b))
            if paths:
                reports.append(ConflictReport(agents=(a, b), paths=paths))
    return reports
