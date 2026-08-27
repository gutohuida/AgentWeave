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

import contextlib
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

#: Task branches are nested one segment deeper than agent branches. See `task_branch_name`.
TASK_BRANCH_PREFIX = BRANCH_PREFIX + "task/"

_GIT_TIMEOUT_SECONDS = 30
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_TASK_ID_RE = re.compile(r"^task-[0-9a-f]{1,64}$")


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


def validate_task_id(task_id: str) -> None:
    """Reject ids that cannot safely become both a path component and a git ref suffix.

    Its own validator rather than a reuse of `validate_agent_name` (design D6): the two accept
    different shapes for different reasons, and a task id is `task-` followed by hex because
    that is what `short_id()` produces (`spec_tasks.py`, `api/v1/tasks.py`) — an id the product
    did not mint is not a task id this module will provision a checkout for.

    Lowercase only, deliberately. Two ids differing solely in case are two distinct git refs but
    a single directory on Windows and macOS, so accepting both would let one task's checkout be
    handed to another.
    """
    if not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError(
            "invalid task id; expected 'task-' followed by 1-64 lowercase hexadecimal digits"
        )


def task_root(repo_root: Path) -> Path:
    return repo_root / ".agentweave" / "tasks"


def task_worktree_path(repo_root: Path, task_id: str) -> Path:
    """Where *task_id*'s work happens (design D1). Pure — provisions nothing."""
    validate_task_id(task_id)
    return task_root(repo_root) / task_id


def task_branch_name(task_id: str) -> str:
    """The branch *task_id*'s work lives on. Pure.

    The `task/` segment is not cosmetic (design D6). `_AGENT_NAME_RE` accepts `task-ab12cd34ef56`
    as an agent name, so `agentweave/<task-id>` would be indistinguishable from that agent's own
    branch; `/` is not in the agent name character class, which makes the two namespaces disjoint
    by construction rather than by luck.
    """
    validate_task_id(task_id)
    return f"{TASK_BRANCH_PREFIX}{task_id}"


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


def _is_mid_merge(worktree: Path) -> bool:
    """True when a merge was started in *worktree* and never finished or aborted."""
    result = _run_git(worktree, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False)
    return result.returncode == 0


def _merge_prerequisites(worktree: Path, task_id: str, prerequisites: Tuple[str, ...]) -> None:
    """Bring each prerequisite commit not already reachable from *worktree*'s HEAD into it.

    Raises `IsolationUnavailableError` on the first one that cannot be brought in. The two ways
    that happens are told apart deliberately (design D1, corrected in R3): a commit that
    *conflicts* asks the operator to reconcile two pieces of work, and a commit that is *missing*
    from the repository asks them to restore a deleted ref. A single message covering both would
    send them looking for the wrong thing.
    """
    for sha in prerequisites:
        present = _run_git(
            worktree, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", check=False
        )
        if present.returncode != 0:
            raise IsolationUnavailableError(
                f"the work {task_id} depends on cannot be brought in: commit {sha[:12]} is "
                "missing from this repository. It was recorded as a prerequisite's accepted "
                "evidence, so the branch that carried it has probably been deleted."
            )

        # D1 says only commits "not already reachable" are merged, and there is deliberately no
        # reachability check here: `git merge --no-ff <ancestor>` is *measured* to be a no-op —
        # "Already up to date.", exit 0, no commit — so an explicit `merge-base --is-ancestor`
        # guard is a branch no test can fail, which this codebase treats as a defect source. The
        # ordinary case (the prerequisite was integrated into the base before this task started)
        # is therefore handled, and `test_a_prerequisite_already_reachable_from_the_base_is_not_
        # merged_twice` pins it by commit count rather than by inspecting our own control flow.
        #
        # `--no-ff` matches `task_integration`'s merge and is load-bearing: without it a task
        # branch cut from the base would *fast-forward* onto a prerequisite's tip, so two tasks
        # would share a branch tip and the merge that brought the work in would leave no record.
        merged = _run_git(
            worktree,
            "-c",
            f"user.name={COMMIT_IDENTITY[0]}",
            "-c",
            f"user.email={COMMIT_IDENTITY[1]}",
            "merge",
            "--no-ff",
            "-m",
            f"Bring in prerequisite work {sha[:12]}",
            sha,
            check=False,
        )
        if merged.returncode != 0:
            detail = (merged.stdout or merged.stderr).strip()[:2000]
            raise IsolationUnavailableError(
                f"the work {task_id} depends on conflicts with its base: merging prerequisite "
                f"commit {sha[:12]} failed. {detail}"
            )


def _unwind_task_worktree(repo_root: Path, path: Path, branch: str) -> None:
    """Undo a half-provisioned task checkout, in the order git forces (design D1).

    A branch that is checked out in a worktree cannot be deleted, so the removal has to come
    first; and `worktree prune` last, matching `ensure_worktree`'s own defence against metadata
    outliving a directory.

    Every step is `check=False` on purpose: a cleanup step that fails must not replace the
    refusal the operator needs to read with a second, less useful one.

    Deliberately **not** `release_task_worktree`, which snapshots the dirty tree onto the branch
    before removing the checkout — here that would commit a conflicted merge as though it were
    the agent's work, and then keep the branch carrying it.

    `branch -D` is safe unconditionally only because this function is reached solely from the
    creation path, seconds after `worktree add -b` made the branch: it carries nothing that was
    not already reachable from the base.
    """
    if path.is_dir():
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _run_git(path, "merge", "--abort", check=False)
    _run_git(repo_root, "worktree", "remove", "--force", str(path), check=False)
    _run_git(repo_root, "branch", "-D", branch, check=False)
    _run_git(repo_root, "worktree", "prune", check=False)


def ensure_task_worktree(
    repo_root: Path,
    task_id: str,
    base: str,
    prerequisites: Sequence[str] = (),
) -> Path:
    """Provision *task_id*'s isolated checkout at *base*, creating it if absent. Idempotent.

    The per-task counterpart of `ensure_worktree` (design D1). `base` and `prerequisites` are
    parameters rather than anything this module looks up: it is independent of the DB/session
    layer by design (see the module docstring), so the Hub layer resolves the project's
    integration base and `task_integration.integration_targets` and passes plain values in.

    Prerequisites are merged **only when the branch is created**. On any later call the branch
    already carries the task's own work, and the all-or-nothing unwind below would destroy it —
    the unwind is safe precisely because the branch is seconds old and carries nothing unique.

    Provisioning is all-or-nothing: a prerequisite that cannot be brought in leaves no checkout
    and no branch behind, and refuses the turn.
    """
    path = task_worktree_path(repo_root, task_id)
    branch = task_branch_name(task_id)
    expected_ref = f"refs/heads/{branch}"

    if path.exists():
        if path.is_symlink() or _registered_worktree_branch(repo_root, path) != expected_ref:
            raise IsolationUnavailableError(
                f"refusing existing path {path}: it is not the registered git worktree "
                f"for {expected_ref}"
            )
        if _is_mid_merge(path):
            # The one state a process killed between `worktree add` and the unwind can leave.
            # `ensure_worktree`'s idempotent path returns any correctly-registered directory
            # unexamined; handing this one over asks the agent to work out what happened to it
            # from a tree full of conflict markers.
            raise IsolationUnavailableError(
                f"refusing the checkout for {task_id} at {path}: it was left in an unfinished "
                "merge. Resolve or abort that merge before this task runs again."
            )
        return path

    _run_git(repo_root, "worktree", "prune", check=False)
    path.parent.mkdir(parents=True, exist_ok=True)

    branch_exists = (
        _run_git(repo_root, "rev-parse", "--verify", "--quiet", branch, check=False).returncode == 0
    )
    if branch_exists:
        # The task was released (design D5) and is being worked again. Its own history is on
        # the branch, so it resumes from there rather than restarting at the base — and its
        # prerequisites were merged when the branch was created.
        _run_git(repo_root, "worktree", "add", str(path), branch)
        _symlink_shared_dependencies(repo_root, path)
        return path

    _run_git(repo_root, "worktree", "add", "-b", branch, str(path), base)
    try:
        _merge_prerequisites(path, task_id, tuple(prerequisites))
    except IsolationUnavailableError:
        _unwind_task_worktree(repo_root, path, branch)
        raise

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


def takes_task_workspace(repo_root: Path, config: Dict[str, Any], task_id: Optional[str]) -> bool:
    """Whether this turn's workspace is *the task's own checkout* rather than a shared one.

    Split out of `resolve_turn_workspace` for design D8. The one-turn-per-task refusal applies to
    exactly the turns that get a task checkout and to no others, and stating that twice is how the
    refusal and the resolution drift apart — an over-broad copy would forbid a read-only agent or a
    grandfathered task, each of which is safe today and is named in D8 as an exemption. So the
    refusal asks this function, `resolve_turn_workspace` obeys it, and a change to either moves
    both.
    """
    return task_id is not None and is_writing_agent(config) and is_git_repo(repo_root)


def resolve_turn_workspace(
    repo_root: Path,
    agent: str,
    config: Dict[str, Any],
    *,
    task_id: Optional[str] = None,
    base: Optional[str] = None,
    prerequisites: Sequence[str] = (),
) -> Path:
    """Return the directory a spawned process should use as its cwd, for *this turn* (design D3).

    The workspace is keyed by what the turn is **about**, not by who is running it: a turn bound to
    a task executes in that task's own checkout, and a turn bound to nothing executes in the
    agent's, exactly as every turn did before per-task isolation. The per-agent workspace is not
    legacy — it is the workspace for work that is not a task, which is a permanent category
    (`db/models.py`: "unbound is legitimate" of `Run.task_id`).

    **`resolve_agent_workspace` is still the only implementation of the unbound answer.** This
    function delegates to it rather than restating it, which is what keeps "read-only agents share
    the project checkout" and "a project that is not a repository has no isolation to offer" from
    acquiring a second, divergent copy. The two guards below are read as *which scheme applies*,
    and both send the turn to that single implementation:

    - a read-only agent shares the project checkout whether or not it is bound to a task
      (`is_writing_agent` keeps precedence, task 4.7): a task checkout it may not write to would be
      an empty gesture, and reviewing agents legitimately read the project directory;
    - a project directory that is not a git repository still runs the turn in place rather than
      refusing it (task 4.8) — there is no isolation on offer for a task any more than for an
      agent, and refusing would be a total outage on a shape this product supports.

    `base` and `prerequisites` are **plain values**, resolved by the Hub layer and passed in: this
    module is independent of the DB/session layer by design (see the module docstring). A task id
    with no base is a programming error rather than a fallback, and says so — silently substituting
    `HEAD` would cut the branch from wherever the operator's checkout happened to be sitting, which
    is precisely the option D1 rejected.
    """
    if not takes_task_workspace(repo_root, config, task_id):
        return resolve_agent_workspace(repo_root, agent, config)
    if base is None:
        raise ValueError(f"a task workspace for {task_id} needs a base to be cut from")
    # `resolve_agent_workspace` seeds these on the path above, and states why it does it there
    # rather than only at registration. The task path is the same funnel and needs the same
    # seeding, before there is anything to ignore.
    seed_repo_excludes(repo_root)
    return ensure_task_worktree(repo_root, task_id, base, prerequisites)


def turn_branch_name(
    repo_root: Path, agent: str, config: Dict[str, Any], *, task_id: Optional[str] = None
) -> str:
    """The branch `resolve_turn_workspace` would put this turn on. Pure — provisions nothing.

    Exists so the *text* an agent is handed about its own workspace is derived from the same
    dispatch that chose the workspace, rather than from a second copy of the rule (task 6.5).
    The second copy is not hypothetical: `api/v1/agents.py` hardcoded `branch_name(agent)` and
    told every task-bound turn it was on a branch it was not on, from phase 4B until this.

    Asks `takes_task_workspace` for exactly the reason that function's own docstring gives, so a
    read-only agent, a non-repository project and a grandfathered task are answered here the same
    way they are answered there. Returns the agent branch for all of them, which is the branch
    those turns are on.
    """
    if not takes_task_workspace(repo_root, config, task_id):
        return branch_name(agent)
    assert task_id is not None  # narrowed by `takes_task_workspace`
    return task_branch_name(task_id)


def task_id_of(worktree: Path) -> Optional[str]:
    """The task whose checkout *worktree* is, or `None` for any other directory. Pure.

    Derived from the directory rather than passed in, so a statement about a checkout cannot
    disagree with the checkout it is about — `snapshot_worktree` names the task in its commit
    message on the strength of this, and the commit lands in this very directory.
    """
    parent = worktree.parent
    if parent.name != "tasks" or parent.parent.name != ".agentweave":
        return None
    return worktree.name if _TASK_ID_RE.fullmatch(worktree.name) else None


def _has_uncommitted_changes(worktree: Path) -> bool:
    result = _run_git(worktree, "status", "--porcelain")
    return bool(result.stdout.strip())


def snapshot_worktree(
    worktree: Path, agent: str, *, message: Optional[str] = None
) -> Optional[str]:
    """Commit any dirty working-tree state in *worktree* onto the agent's own branch.

    Best-effort, internal safety net — not a user-facing commit meant to pass a
    project's own review gates, hence `--no-verify`: a project's commit-msg/pre-commit
    hook blocking this would silently strand the agent's own work uncommitted, which is
    exactly what this function exists to prevent. Returns the new commit SHA, or `None`
    if there was nothing to commit.

    *message* overrides the default subject for callers whose checkout does not belong to an
    agent's turn — `release_task_worktree`, whose branch belongs to a task. Keyword-only so the
    existing positional call sites cannot acquire one by accident.

    The default subject names the task when the checkout is a task's (task 6.7). A task branch
    accumulates a snapshot per turn and, before this, every one of them read `Auto-snapshot:
    builder's turn` — identical subjects on the only per-commit statement of what a turn was, on
    the branch where several agents' turns can land in sequence. Read off the directory via
    `task_id_of` rather than threaded from the trigger, so the two call sites there cannot pass
    one task's id while committing in another's checkout.
    """
    if not _has_uncommitted_changes(worktree):
        return None
    _run_git(worktree, "add", "-A")
    staged = _run_git(worktree, "diff", "--cached", "--name-only")
    if not staged.stdout.strip():
        return None
    if message is None:
        task_id = task_id_of(worktree)
        message = (
            f"Auto-snapshot: {agent}'s turn on {task_id}"
            if task_id
            else f"Auto-snapshot: {agent}'s turn"
        )
    _run_git(
        worktree,
        "-c",
        f"user.name={COMMIT_IDENTITY[0]}",
        "-c",
        f"user.email={COMMIT_IDENTITY[1]}",
        "commit",
        "--no-verify",
        "-m",
        message,
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


def release_task_worktree(repo_root: Path, task_id: str) -> ReleaseResult:
    """Release *task_id*'s checkout (design D5): remove the directory, keep the branch.

    The per-task counterpart of `release_worktree`, and it keeps the same guarantees for the same
    reasons — any uncommitted change is snapshotted onto the task branch first, and every commit
    the branch carries beyond the primary checkout's HEAD is reported rather than discarded. What
    bounds the disk is the *checkout*; the branch is the record of what the task did, and deleting
    it would destroy the history an operator reads after the fact.

    Returns a `ReleaseResult` like `release_worktree`, with `review_checkout_released` always
    false: review checkouts are keyed by the reviewing agent, not by a task, so there is never
    one to release here.
    """
    path = task_worktree_path(repo_root, task_id)
    branch = task_branch_name(task_id)

    if not path.exists():
        return ReleaseResult(released=False, branch=branch)

    had_uncommitted = _has_uncommitted_changes(path)
    snapshot_commit = (
        snapshot_worktree(path, task_id, message=f"Auto-snapshot: {task_id}")
        if had_uncommitted
        else None
    )

    _run_git(repo_root, "worktree", "remove", "--force", str(path))

    return ReleaseResult(
        released=True,
        branch=branch,
        had_uncommitted_changes=had_uncommitted,
        snapshot_commit=snapshot_commit,
        unmerged_commits=_commits_not_on_head(repo_root, branch),
    )


@dataclass(frozen=True)
class WorkspaceBranch:
    """One currently registered Hub-owned checkout, and what it belongs to.

    `kind` is `"agent"` or `"task"`; `name` is the agent's name or the task's id. Keyed by
    *workspace* rather than by agent because a branch is no longer one per agent (design D6) —
    see `list_workspace_branches`.
    """

    kind: str
    name: str
    branch: str
    path: Path


def list_workspace_branches(repo_root: Path) -> List[WorkspaceBranch]:
    """Every Hub-owned checkout git currently has registered, agent and task alike.

    Two filters used to drop task checkouts here, not one, and relaxing either alone would have
    left them invisible (task 6.1): the `_AGENT_NAME_RE` match on what follows
    `refs/heads/agentweave/`, which `task/<id>` fails on the `/`, and the comparison of the
    registered path against `worktree_path(repo_root, agent)`, which a path under
    `.agentweave/tasks/` fails too. Both are still applied — per namespace, against the path that
    namespace's own pure function predicts, so a checkout registered somewhere unexpected is still
    excluded rather than reported under a name it does not occupy.

    Excludes retained branches (a branch with no checkout) and review checkouts (detached, so no
    branch record at all), exactly as before.
    """
    result = _run_git(repo_root, "worktree", "list", "--porcelain")
    found: List[WorkspaceBranch] = []
    record: Dict[str, str] = {}

    def append_record() -> None:
        ref = record.get("branch", "")
        prefix = f"refs/heads/{BRANCH_PREFIX}"
        if not ref.startswith(prefix):
            return
        actual = Path(record.get("worktree", "")).resolve()
        suffix = ref[len(prefix) :]
        if suffix.startswith("task/"):
            task_id = suffix[len("task/") :]
            if not _TASK_ID_RE.fullmatch(task_id):
                return
            if actual == task_worktree_path(repo_root, task_id).resolve():
                found.append(
                    WorkspaceBranch(
                        kind="task", name=task_id, branch=ref[len("refs/heads/") :], path=actual
                    )
                )
            return
        if not _AGENT_NAME_RE.fullmatch(suffix):
            return
        if actual == worktree_path(repo_root, suffix).resolve():
            found.append(
                WorkspaceBranch(
                    kind="agent", name=suffix, branch=ref[len("refs/heads/") :], path=actual
                )
            )

    for raw_line in [*result.stdout.splitlines(), ""]:
        line = raw_line.strip()
        if not line:
            append_record()
            record = {}
            continue
        key, _, value = line.partition(" ")
        record[key] = value
    return sorted(found, key=lambda w: (w.kind, w.name))


def list_agent_branches(repo_root: Path) -> List[str]:
    """Return agents with a currently registered checkout, excluding retained branches.

    The agent-kind half of `list_workspace_branches`, kept as the answer to a question that is
    still asked — "which *agents* are provisioned" — rather than as a compatibility shim.
    """
    return [w.name for w in list_workspace_branches(repo_root) if w.kind == "agent"]


@dataclass
class ConflictReport:
    """Two diverging workspaces and the paths they disagree on.

    `workspaces`, not `agents`: two of the branches that can now conflict belong to tasks rather
    than to agents, and one task's branch can conflict with another's while both are held by the
    same agent. A pair of agent names cannot express that — it would have named the same agent
    twice, or dropped the report for want of a second name.
    """

    workspaces: Tuple[WorkspaceBranch, WorkspaceBranch]
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
    """Pairwise-check every currently-provisioned Hub-owned branch against every
    other's, surfacing which workspaces diverge and on which files
    (hub-native-runtime's "Divergent changes surface as a conflict" scenario).

    Task branches are included (task 6.2). They are where the work actually is once a project is
    on per-task isolation, so a check that walked agent branches only would have gone quiet on a
    project doing everything through tasks — reporting no conflicts because it was looking at the
    empty half of the namespace.
    """
    workspaces = list_workspace_branches(repo_root)
    reports: List[ConflictReport] = []
    for i in range(len(workspaces)):
        for j in range(i + 1, len(workspaces)):
            a, b = workspaces[i], workspaces[j]
            paths = _merge_tree_conflicts(repo_root, a.branch, b.branch)
            if paths:
                reports.append(ConflictReport(workspaces=(a, b), paths=paths))
    return reports
