"""Per-agent workspace isolation via git worktrees (task 5, design.md Decision 7).

*Why worktrees, not locks* (Decision 7): in a shared working directory there is no
merge — two agents editing one folder produce a **lost update**, not a conflict. A
worktree does not remove that risk, it converts a silent loss into a visible,
resolvable conflict. Each writing agent gets its own worktree on its own branch
(``agentweave/<agent>``), sharing the primary checkout's object database. An agent
declared ``read_only`` in its config (new key, task 5.2) never gets one and shares the
primary checkout directly instead.

That conversion needs a repository, so it is available rather than unconditional. A
project directory that is not a git repository has no isolation to offer and gets none:
its writing agents run in the project directory itself rather than being refused
(``resolve_agent_workspace``, and see ``2026-08-12-run-without-a-git-repository``). Two
of them can then lose each other's updates — accepted deliberately, because the only
mechanism for converting that into a conflict is the repository that is absent, and the
alternatives are refusing the operator's project or serialising it. The posture is
stated to the agent in its turn context and to the operator in its workspace report;
what is *not* done is creating a repository to satisfy an invariant nobody asked for.

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

from .repo_hygiene import seed_repo_excludes
from .subprocess_windows import no_console_kwargs

logger = logging.getLogger(__name__)

BRANCH_PREFIX = "agentweave/"

#: Who the Hub commits as when it creates a commit itself — a worktree snapshot, or the merge that
#: integrates approved work.
#:
#: Supplied explicitly on every such commit, never relied upon from configuration. A project the
#: operator has not configured an identity in is an ordinary project, and git refuses to commit
#: there at all; without this the Hub can create an agent's snapshot and then fail to merge it,
#: which is exactly what happened on the first real run of the integration path.
COMMIT_IDENTITY = ("AgentWeave", "agentweave@localhost")

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


class ReviewCommitUnavailableError(RuntimeError):
    """The commit a review turn was asked to check out is not in this repository.

    A stated refusal rather than a guess. A reviewer pointed at the wrong tree reports a verdict
    about code nobody wrote, which is worse than no review at all.
    """


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        **no_console_kwargs(),
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
            **no_console_kwargs(),
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


def review_root(repo_root: Path) -> Path:
    return repo_root / ".agentweave" / "reviews"


def review_path(repo_root: Path, agent: str) -> Path:
    """Where *agent* reviews someone else's work (design D3).

    Keyed by the **reviewing** agent, not by the commit, task or evidence, because that is what
    makes the set bounded: one directory per agent forever, re-pointed with `git checkout --detach`
    at each review. Only one run per agent can be live at a time, so one is provably enough. Keying
    by anything else grows without limit and reintroduces a cleanup problem.

    Pure, like `worktree_path`, and validated the same way — an agent name that cannot safely become
    a path component is refused here rather than at the git call.
    """
    validate_agent_name(agent)
    return review_root(repo_root) / agent


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


def _registered_worktree_record(repo_root: Path, path: Path) -> Optional[Dict[str, str]]:
    """Return git's own porcelain record for the worktree registered at *path*, if any.

    Whole record rather than just the branch, because a **review** checkout is detached and so has
    no `branch` line at all — `detached` appears instead, with no value. A helper that could only
    answer "which branch" therefore could not tell an unregistered path from a registered detached
    one, and both callers below need that distinction.

    Path comparison is `absolute()`, deliberately not `resolve()`: following symlinks here would let
    an aliased path answer for a directory git does not actually track there.
    """
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
            return record
        record = {}
    return None


def _registered_worktree_branch(repo_root: Path, path: Path) -> Optional[str]:
    """Return the branch registered at *path*, without following path aliases."""
    record = _registered_worktree_record(repo_root, path)
    return record.get("branch") if record is not None else None


def existing_worktree(repo_root: Path, agent: str) -> Optional[Path]:
    """*agent*'s checkout if git really tracks one there, and `None` otherwise.

    **Provisions nothing.** This answers a question on read paths — "where is this agent's work?" —
    and a read path that creates a checkout as a side effect of being asked is a read path that
    changes what it was measuring.

    **The directory existing is not the question, and testing it is a trap.** A git command run with
    `cwd` set to a directory git does not track walks *up* to the enclosing repository and answers
    about that instead. So an empty or abandoned `.agentweave/worktrees/<agent>` would yield the
    project checkout's own HEAD while looking like a checked and passing case — which is exactly the
    defect this function exists to prevent, reintroduced behind a plausible guard. The registered
    branch is what settles it.
    """
    try:
        path = worktree_path(repo_root, agent)
    except ValueError:
        return None
    if not path.is_dir() or path.is_symlink():
        return None
    try:
        registered = _registered_worktree_branch(repo_root, path)
    except (GitCommandError, OSError, subprocess.SubprocessError):
        return None
    return path if registered == f"refs/heads/{branch_name(agent)}" else None


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


def resolve_review_commit(repo_root: Path, sha: str) -> str:
    """Return the full SHA *sha* names, or refuse with a reason (tasks 1.5, 2.2).

    `^{commit}` rather than a bare verify: a tag or a tree would otherwise pass here and fail later
    inside `worktree add`, where the error names git's plumbing instead of the review.
    """
    if not sha or not sha.strip():
        raise ReviewCommitUnavailableError("no commit was given to review")
    candidate = sha.strip()
    result = _run_git(
        repo_root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}", check=False
    )
    resolved = result.stdout.strip()
    if result.returncode != 0 or not resolved:
        raise ReviewCommitUnavailableError(
            f"commit {candidate} is not present in this repository, so there is nothing to check "
            "out for review"
        )
    return resolved


def existing_review_checkout(repo_root: Path, agent: str) -> Optional[Path]:
    """*agent*'s review checkout if git really tracks a detached one there, else `None`.

    Provisions nothing, for the same reason `existing_worktree` provisions nothing, and tests the
    registration rather than the directory for the same reason too: a git command run with `cwd`
    set to an untracked directory answers about the *enclosing* repository, so an abandoned
    directory would look like a passing case.

    A record carrying a `branch` is rejected. That path is supposed to be detached (design D2); if
    something has put a branch there it is not ours to reuse silently.
    """
    try:
        path = review_path(repo_root, agent)
    except ValueError:
        return None
    if not path.is_dir() or path.is_symlink():
        return None
    try:
        record = _registered_worktree_record(repo_root, path)
    except (GitCommandError, OSError, subprocess.SubprocessError):
        return None
    if record is None or record.get("branch"):
        return None
    return path


def ensure_review_checkout(repo_root: Path, agent: str, sha: str) -> Path:
    """Provision *agent*'s review checkout, detached at *sha*. Idempotent (task 1.2).

    Created on the first review and **re-pointed** on every one after it, so the number of these
    directories is bounded by the roster rather than by the number of reviews (design D3).

    *Detached, with no branch* (design D2). A branch invites a commit, and a reviewer is not an
    author — if it wants a change made, the product already has `revision_needed` and the author
    makes it. Detached also means git itself states the role: `git status` in here says
    "HEAD detached at <sha>", so the environment tells the agent what it is doing rather than
    depending on the prompt to. An accidental commit is then orphaned and harmless.

    `checkout --force`, because a review checkout is disposable and the reviewer is not its author:
    a tracked file it modified must not be able to block the next review. Untracked files are left
    alone — `--force` does not remove them — so a scratch note costs nothing.
    """
    commit = resolve_review_commit(repo_root, sha)
    path = review_path(repo_root, agent)

    if path.exists():
        if existing_review_checkout(repo_root, agent) is None:
            raise IsolationUnavailableError(
                f"refusing existing path {path}: it is not a detached git worktree registered for "
                f"{agent}'s reviews"
            )
        _run_git(path, "checkout", "--force", "--detach", commit)
    else:
        # Same reason as `ensure_worktree`: git's own `.git/worktrees/<name>` metadata can outlive
        # a directory removed by something other than `release_review_checkout`, and `worktree add`
        # refuses to proceed while it does.
        _run_git(repo_root, "worktree", "prune", check=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        _run_git(repo_root, "worktree", "add", "--detach", str(path), commit)

    # Task 1.3, and design D6: without this the reviewer cannot run the suite, which is the entire
    # justification for giving it a checkout rather than a diff.
    _symlink_shared_dependencies(repo_root, path)
    return path


def release_review_checkout(repo_root: Path, agent: str) -> bool:
    """Remove *agent*'s review checkout. Returns whether there was one (task 1.4).

    Nothing is preserved and nothing needs to be. A working worktree is released carefully because
    it carries the agent's own unmerged work; a review checkout carries no work by construction —
    it is detached, and anything committed onto it was already orphaned.
    """
    try:
        path = review_path(repo_root, agent)
    except ValueError:
        return False
    if not path.exists():
        return False
    _run_git(repo_root, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    _run_git(repo_root, "worktree", "prune", check=False)
    return True


def resolve_agent_workspace(repo_root: Path, agent: str, config: Dict[str, Any]) -> Path:
    """Return the directory a spawned *agent* process should use as its cwd.

    Writing agents get an isolated worktree, provisioned here if needed. Read-only
    agents share *repo_root*.

    **Absence of a repository is a degradation; failing to provision one is an error**
    (design.md Decision 1). The two look alike and are not. Where *repo_root* is not a
    git repository there is no isolation on offer — no branch exists, no primary checkout
    is at risk, and running in place is the only thing the Hub could do, so it does that.
    Where the project *is* a repository and `ensure_worktree` fails, it still raises:
    falling back there would put a writing agent on the operator's primary checkout,
    mutating the working copy their editor and CI read, which is the silent lost update
    this module exists to prevent.

    Seeding the Hub's ignore rules here rather than only at registration is deliberate: a
    project registered before a pattern existed never passes through `open_existing` again,
    and this is the one funnel every triggered agent goes through. It runs before the
    worktree is provisioned so the rules are in place before there is anything to ignore.
    """
    seed_repo_excludes(repo_root)
    if not is_writing_agent(config):
        return repo_root
    if not is_git_repo(repo_root):
        # Nothing to isolate from. `is_git_repo` also answers False for a machine with no
        # `git` at all, which is correct here for the same reason: that machine has no
        # isolation to offer either, and refusing every turn on it was a total outage.
        return repo_root
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
        f"user.name={COMMIT_IDENTITY[0]}",
        "-c",
        f"user.email={COMMIT_IDENTITY[1]}",
        "commit",
        "--no-verify",
        "-m",
        f"Auto-snapshot: {agent}'s turn",
    )
    sha = _run_git(worktree, "rev-parse", "HEAD")
    return sha.stdout.strip()


def files_changed_in(worktree: Path, sha: str) -> List[str]:
    """Paths touched by *sha*, sorted. Empty when the commit cannot be read.

    `git show --name-only` rather than a `sha^..sha` diff, because the first commit on a fresh
    agent branch has no parent and a diff against `sha^` fails outright on it.

    Best-effort by design: a checkpoint that reports no changed files because a commit was
    garbage-collected is wrong, but a checkpoint that fails to exist because of it is worse.
    """
    result = _run_git(worktree, "show", "--pretty=format:", "--name-only", sha, check=False)
    if result.returncode != 0:
        return []
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


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
    #: Whether this agent also had a review checkout, and it was removed (task 1.4). Independent of
    #: `released`: an agent that only ever reviewed has one of these and no working worktree.
    review_checkout_released: bool = False

    @property
    def has_unmerged_work(self) -> bool:
        return bool(self.unmerged_commits)


def release_worktree(repo_root: Path, agent: str) -> ReleaseResult:
    """Release *agent*'s worktree (task 5.4): remove the checkout directory, but
    never the branch, and never silently — any uncommitted change is snapshotted
    onto the branch first, and any commit the branch carries beyond the primary
    checkout's HEAD is reported back, not discarded.

    The agent's *review* checkout goes too (task 1.4), and goes first, because it is released
    unconditionally: an agent that has only ever reviewed has one of those and no working worktree
    at all, so releasing it after the early return below would never happen for exactly the agent
    that needs it.
    """
    path = worktree_path(repo_root, agent)
    branch = branch_name(agent)

    review_released = release_review_checkout(repo_root, agent)

    if not path.exists():
        return ReleaseResult(
            released=False, branch=branch, review_checkout_released=review_released
        )

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
        review_checkout_released=review_released,
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
