"""A build that lands as one GitHub pull request (`a-build-lands-as-one-pull-request`).

This module is the Hub's only client of a code host, and it talks to GitHub through the user's own
GitHub CLI login (`gh`), never a token of its own.

**Readiness** (FR-2): PR landing is refused, when it is turned on and when a build landing as a pull
request starts, unless the project directory has a GitHub remote, the GitHub CLI is installed and it
is logged in. It is found at the start, not at the first approved task after hours of work.

**Pushing** (task `push`): the landing queue hands a PR build's approved task here (`land`) instead
of merging it into main. GitHub's main is fetched and merged into the build branch when it moved
(FR-8: a conflict sends the task back as a merge conflict); the task's work is merged on with
plumbing (`landing_queue.build_chain`); the project's landing-phase checks run on that tree as a
batch of one, judged against the known-failing list (FR-3); only a pass is pushed. The push always
carries a lease on the commit the Hub last pushed, so a branch someone else pushed to is never
replaced (FR-7). With the single-commit setting the pushed commit is one commit on GitHub's main
holding the whole build's tree. The first push opens a draft PR against the project's main branch
(FR-4); every push and every draft or ready change rewrites its title and description (FR-6); it is
readied once every task of the build is pushed and returned to draft when one is sent back (FR-5).

**What it may ask of GitHub** (FR-12): `git push` of the build branch, and through the CLI only the
commands in `GH_ALLOWED` -- `gh` is called through `gh` alone, which refuses anything else, so the
Hub cannot merge a PR, approve it, change its base or touch branch protection.

**The PR's CI is the full check** (`the-pr-s-ci-is-the-full-check`, task `settings`): the checks
that count for a PR are those GitHub marks required on its base branch, else the project's list of
check names (FR-3, `counted_checks`). The required ones are read with two plain `gh api` GETs, the
branch and the rules that apply to it, and `gh` allows no other `gh api` call (`required_checks`)
but two GETs of one commit's check runs and status (`commit_checks`).

Task `read-ci`: with the setting on, each push records CI pending on the commit it pushed
(`ci_pushed`); only the PR's head decides (FR-4), and a result on a commit a later push replaced
is marked superseded. While the head's counted checks are pending the Hub asks at the project's
interval up to its cutoff (`watch_ci`, FR-5), besides slice 1's actions (`ask`). A failing counted
check is compared with the same check on main's latest commit (`read_ci`, FR-11): when every
failing one fails there too nothing is sent back, else the latest task pushed is.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import traces

logger = logging.getLogger(__name__)

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


# --- the GitHub CLI calls the Hub may make (FR-12) -----------------------------------------------

#: The only `gh` subcommands the Hub issues: open, edit, ready (or return to draft) and read its PR.
#: Merging, reviewing, closing, `gh api` and anything touching branch protection are not here, and
#: `gh` refuses them before anything runs.
GH_ALLOWED = frozenset({("pr", "create"), ("pr", "edit"), ("pr", "ready"), ("pr", "view")})

#: The only `gh api` calls the Hub makes: a GET, with no other argument, of a branch or of the rules
#: that apply to it, to learn its required status checks (`required_checks`). Anything naming
#: branch protection itself is refused, even as a read.
_API_READ = re.compile(r"^repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:rules/)?branches/[^\s?#]+$")
#: ... and a GET of the check runs or the combined status of one commit (a SHA, or a branch for its
#: latest commit), to read CI's result there (`commit_checks`).
_COMMIT_READ = re.compile(
    r"^repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/commits/[^\s?#]+/(?:check-runs|status)\?per_page=100$"
)

#: How long one push, fetch or GitHub CLI call of a landing may take.
NETWORK_TIMEOUT_SECONDS = 180

#: The build branch, on the project directory and on GitHub.
BRANCH_PREFIX = "agentweave/build/"

#: A pull request build's landing that was pushed to the build branch: the work is on the PR, and
#: lands on main only when the PR is merged on GitHub.
PUSHED = "pushed"

DRAFT = "draft"
READY = "ready"


class RefusedGitHubCallError(ValueError):
    """A `gh` call outside `GH_ALLOWED`, or one that would change the PR's base (FR-12)."""


def check_gh_call(args: Sequence[str]) -> None:
    """Refuse any `gh` call the Hub must never make (FR-12). Raises `RefusedGitHubCallError`."""
    words = tuple(args[:2])
    if words[:1] == ("api",) and len(args) == 2:
        path = str(args[1])
        readable = _API_READ.match(path) or _COMMIT_READ.match(path)
        if readable and "protection" not in path.lower().split("/"):
            return
        raise RefusedGitHubCallError(f"the Hub never runs `gh api {path}`")
    if words not in GH_ALLOWED:
        raise RefusedGitHubCallError(f"the Hub never runs `gh {' '.join(args[:2])}`")
    rest = list(args[2:])
    if words == ("pr", "edit") and any(
        arg in ("--base", "-B") or arg.startswith("--base=") for arg in rest
    ):
        raise RefusedGitHubCallError("the Hub never changes a pull request's base branch")
    if words == ("pr", "ready") and any(arg.startswith("-") and arg != "--undo" for arg in rest):
        raise RefusedGitHubCallError("`gh pr ready` takes only `--undo` from the Hub")


def _run_gh(root: Path, args: List[str]) -> subprocess.CompletedProcess:
    """Run the GitHub CLI (a seam: tests answer for GitHub here)."""
    exe = gh_executable()
    if exe is None:
        raise OSError("the GitHub CLI (gh) is not installed, or not on the Hub's PATH")
    return traces.run(
        [exe, *args],
        ok_codes=(0, 1),
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=NETWORK_TIMEOUT_SECONDS,
        env={**os.environ, "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1"},
    )


def gh(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Every GitHub CLI call the Hub makes goes through here, and only an allowed one runs."""
    check_gh_call(args)
    try:
        return _run_gh(root, list(args))
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, 1, "", f"{type(exc).__name__}: {exc}")


def _gh_error(result: subprocess.CompletedProcess) -> str:
    said = ((result.stderr or "") + (result.stdout or "")).strip()[:2000]
    return said or f"gh exited {result.returncode}"


# --- the checks that count (`the-pr-s-ci-is-the-full-check`, FR-3) -------------------------------

#: The project setting 'the PR's CI is the full check', as the settings route names it.
CI_SETTING = "pr_ci_full_check"
#: The project's own list of the check names that count when GitHub marks none required.
CI_CHECK_NAMES = "pr_ci_check_names"

#: Refused: the setting, or a PR build with it on, where nothing would be waited for (FR-3).
NOTHING_TO_WAIT_FOR = "nothing_to_wait_for"

#: A counted check's state, and CI's as a whole on a commit (`judge`).
CHECK_PENDING = "pending"
CHECK_PASSED = "passed"
CHECK_FAILED = "failed"

# `gh pr checks --json bucket` (and `judge`'s input): which buckets are a pass, and which a failure.
# A skipped check is GitHub's own pass for a required check; a cancelled one did not pass.
_PASSING_BUCKETS = frozenset({"pass", "skipping"})
_FAILING_BUCKETS = frozenset({"fail", "cancel"})

_REPO_IN_URL = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class RequiredChecks:
    """The status checks GitHub marks required on a branch, and why they could not be read, if
    they could not (`error`; `names` is then whatever the readable half answered)."""

    names: List[str]
    error: Optional[str] = None


def github_repo(root: Path) -> Optional[str]:
    """`owner/repo` of the project directory's GitHub remote, or None."""
    name = github_remote(root)
    if name is None:
        return None
    try:
        url = _git(root, "remote", "get-url", name)
    except (OSError, subprocess.SubprocessError):
        return None
    found = _REPO_IN_URL.search((url.stdout or "").strip())
    return f"{found.group(1)}/{found.group(2)}" if found else None


def _json_of(result: subprocess.CompletedProcess) -> Any:
    return json.loads(result.stdout or "null")


def required_checks(root: Path, branch: str) -> RequiredChecks:
    """The status checks GitHub marks required on *branch*: branch protection's, as the branch
    reads them, and those of every ruleset that applies to it. Two `gh api` GETs; runs the CLI, so
    it is called off the event loop."""
    repo = github_repo(root)
    if repo is None:
        return RequiredChecks([], "the project directory has no GitHub remote")
    quoted = quote(branch, safe="/")
    names: List[str] = []
    errors: List[str] = []

    branch_read = gh(root, "api", f"repos/{repo}/branches/{quoted}")
    if branch_read.returncode == 0:
        try:
            guarded = (_json_of(branch_read) or {}).get("protection") or {}
            status = guarded.get("required_status_checks") or {} if guarded.get("enabled") else {}
            names.extend(str(c) for c in status.get("contexts") or [])
            names.extend(
                str(c.get("context")) for c in status.get("checks") or [] if c.get("context")
            )
        except (ValueError, AttributeError) as exc:
            errors.append(f"the branch {branch} could not be read: {exc}")
    else:
        errors.append(f"the branch {branch} could not be read: {_gh_error(branch_read)}")

    rules_read = gh(root, "api", f"repos/{repo}/rules/branches/{quoted}")
    if rules_read.returncode == 0:
        try:
            for rule in _json_of(rules_read) or []:
                if rule.get("type") != "required_status_checks":
                    continue
                for c in (rule.get("parameters") or {}).get("required_status_checks") or []:
                    if c.get("context"):
                        names.append(str(c["context"]))
        except (ValueError, AttributeError) as exc:
            errors.append(f"the rules of {branch} could not be read: {exc}")
    else:
        errors.append(f"the rules of {branch} could not be read: {_gh_error(rules_read)}")

    return RequiredChecks(list(dict.fromkeys(names)), "; ".join(errors) or None)


def counted_checks(required: RequiredChecks, listed: Sequence[str]) -> List[str]:
    """The checks that count for a PR (FR-3): the required ones, else the project's list -- which is
    also what counts when the required ones could not be read at all."""
    if required.names:
        return list(required.names)
    return [name for name in dict.fromkeys(listed) if name]


def nothing_to_wait_for(
    required: RequiredChecks, listed: Sequence[str], branch: str
) -> Optional[str]:
    """Why nothing would be waited for -- GitHub marks no check required on *branch* and the
    project lists none -- naming both; None when some check counts (FR-3)."""
    if counted_checks(required, listed):
        return None
    github = (
        f"the Hub could not read which checks GitHub requires on {branch} ({required.error})"
        if required.error and not required.names
        else f"GitHub marks no status check required on {branch}"
    )
    return (
        f"{github}, and the project lists no check names ({CI_CHECK_NAMES}), so there would be no "
        "CI result to wait for: mark a check required on GitHub, or list the names of the checks "
        "that count"
    )


def wait_problem(root: Path, branch: Optional[str], listed: Sequence[str]) -> Optional[str]:
    """Why a project with the CI setting on would have nothing to wait for (`nothing_to_wait_for`),
    or None. A non-empty list is enough without asking GitHub; otherwise GitHub's required checks on
    *branch* are read, so this runs the CLI and is called off the event loop."""
    if counted_checks(RequiredChecks([]), listed):
        return None
    if not branch:
        return nothing_to_wait_for(
            RequiredChecks([], "the project has no main branch set"), listed, "main"
        )
    return nothing_to_wait_for(required_checks(root, branch), listed, branch)


def judge(counted: Sequence[str], results: Sequence[Dict[str, Any]]) -> str:
    """CI's state on a commit from the counted checks alone (FR-3): failed when any counted check
    failed, passed when every one passed, pending otherwise (one still running, or not reported).
    *results* are GitHub's checks on the commit, each `{name, bucket}`; a check not counted decides
    nothing, whatever its result."""
    buckets: Dict[str, str] = {}
    for result in results:
        buckets.setdefault(str(result.get("name")), str(result.get("bucket") or "pending").lower())
    states = [buckets.get(name, "pending") for name in counted]
    if any(state in _FAILING_BUCKETS for state in states):
        return CHECK_FAILED
    if states and all(state in _PASSING_BUCKETS for state in states):
        return CHECK_PASSED
    return CHECK_PENDING


# --- CI's result on a commit (FR-4, FR-11) -------------------------------------------------------

#: CI's state on the build beyond `judge`'s three: every failing counted check also fails on main's
#: latest commit (FR-11), a later push replaced the commit it was read on (FR-4), and the cutoff
#: passed with a counted check still unconcluded (FR-5).
CI_FAILING_ON_MAIN = "failing_on_main"
CI_SUPERSEDED = "superseded"
CI_NOT_FINISHED = "not_finished"

#: A failing counted check's result on main's latest commit (FR-11): failed there too, passed
#: there, or no concluded result (pending, never run there, or unreadable).
ON_MAIN_FAILED = "failed"
ON_MAIN_PASSED = "passed"
ON_MAIN_NONE = "none"

# A check run's conclusion, and a commit status's state, as `judge`'s buckets.
_RUN_BUCKETS = {
    "success": "pass",
    "neutral": "pass",
    "skipped": "skipping",
    "failure": "fail",
    "timed_out": "fail",
    "action_required": "fail",
    "startup_failure": "fail",
    "cancelled": "cancel",
}
_STATUS_BUCKETS = {"success": "pass", "failure": "fail", "error": "fail"}


def _bucket_state(bucket: str) -> str:
    if bucket in _FAILING_BUCKETS:
        return CHECK_FAILED
    if bucket in _PASSING_BUCKETS:
        return CHECK_PASSED
    return CHECK_PENDING


@dataclass
class CommitChecks:
    """GitHub's checks on one commit, each `{name, bucket, url}`; *error* where either read failed,
    and then *results* decide nothing."""

    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


def commit_checks(root: Path, repo: str, ref: str) -> CommitChecks:
    """The check runs and commit statuses on *ref* (a SHA, or a branch for its latest commit): two
    `gh api` GETs. A check run more than once is read at its latest run. Blocking."""
    quoted = quote(ref, safe="")
    out = CommitChecks()
    latest: Dict[str, Dict[str, Any]] = {}
    runs = gh(root, "api", f"repos/{repo}/commits/{quoted}/check-runs?per_page=100")
    if runs.returncode == 0:
        try:
            for run in (_json_of(runs) or {}).get("check_runs") or []:
                name = str(run.get("name") or "")
                if not name:
                    continue
                if name in latest and int(latest[name].get("id") or 0) > int(run.get("id") or 0):
                    continue
                latest[name] = run
        except (ValueError, AttributeError, TypeError) as exc:
            out.error = f"the check runs on {ref} could not be read: {exc}"
    else:
        out.error = f"the check runs on {ref} could not be read: {_gh_error(runs)}"
    for name, run in latest.items():
        done = str(run.get("status") or "").lower() == "completed"
        bucket = _RUN_BUCKETS.get(str(run.get("conclusion") or "").lower(), "pending")
        out.results.append(
            {"name": name, "bucket": bucket if done else "pending", "url": run.get("html_url")}
        )
    status = gh(root, "api", f"repos/{repo}/commits/{quoted}/status?per_page=100")
    if status.returncode == 0:
        try:
            for each in (_json_of(status) or {}).get("statuses") or []:
                name = str(each.get("context") or "")
                if name and name not in latest:
                    bucket = _STATUS_BUCKETS.get(str(each.get("state") or "").lower(), "pending")
                    out.results.append(
                        {"name": name, "bucket": bucket, "url": each.get("target_url")}
                    )
        except (ValueError, AttributeError, TypeError) as exc:
            out.error = out.error or f"the commit status of {ref} could not be read: {exc}"
    else:
        out.error = (
            out.error or f"the commit status of {ref} could not be read: {_gh_error(status)}"
        )
    return out


def _on_main(bucket: str, error: Optional[str]) -> str:
    if error:
        return ON_MAIN_NONE
    if bucket in _FAILING_BUCKETS:
        return ON_MAIN_FAILED
    if bucket in _PASSING_BUCKETS:
        return ON_MAIN_PASSED
    return ON_MAIN_NONE


def read_ci(root: Path, main_branch: str, sha: str, listed: Sequence[str]) -> Dict[str, Any]:
    """CI's result on the PR's head *sha* from the counted checks alone (FR-3), each failing one
    compared with the same check on GitHub's latest commit of *main_branch* (FR-11). Answers
    `{state, head_sha, checks: [{name, state, url, main_result?}], main_error, error}`; `state` is None
    where GitHub could not be read, which decides nothing. Blocking."""
    out: Dict[str, Any] = {"state": None, "head_sha": sha, "checks": [], "error": None}
    repo = github_repo(root)
    if repo is None:
        out["error"] = "the project directory has no GitHub remote"
        return out
    required = required_checks(root, main_branch)
    counted = counted_checks(required, listed)
    if not counted:
        out["error"] = nothing_to_wait_for(required, listed, main_branch)
        return out
    head = commit_checks(root, repo, sha)
    if head.error:
        out["error"] = head.error
        return out
    by_name: Dict[str, Dict[str, Any]] = {}
    for result in head.results:
        by_name.setdefault(result["name"], result)
    for name in counted:
        result = by_name.get(name) or {}
        state = _bucket_state(str(result.get("bucket") or "pending"))
        out["checks"].append({"name": name, "state": state, "url": result.get("url")})
    state = judge(counted, head.results)
    failing = [check for check in out["checks"] if check["state"] == CHECK_FAILED]
    if failing:
        main = commit_checks(root, repo, main_branch)
        on_main: Dict[str, Dict[str, Any]] = {}
        for result in main.results:
            on_main.setdefault(result["name"], result)
        for check in failing:
            bucket = str((on_main.get(check["name"]) or {}).get("bucket") or "")
            check["main_result"] = _on_main(bucket, main.error)
        out["main_error"] = main.error
        if all(check["main_result"] == ON_MAIN_FAILED for check in failing):
            state = CI_FAILING_ON_MAIN
    out["state"] = state
    return out


def ci_report(display_id: str, read: Dict[str, Any], main_branch: str) -> str:
    """The send-back of the latest task pushed when CI failed on the head (FR-7, FR-11): each
    failing counted check that does not also fail on main, its link, and what main said of it."""
    sha = str(read.get("head_sha") or "")[:12]
    lines = [
        f"CI failed on the build's pull request at {sha}, the commit task {display_id}'s push "
        "made:",
        "",
    ]
    for check in read.get("checks") or []:
        if check.get("state") != CHECK_FAILED or check.get("main_result") == ON_MAIN_FAILED:
            continue
        if check.get("main_result") == ON_MAIN_PASSED:
            said = f"it passed on the latest commit of {main_branch}"
        elif read.get("main_error"):
            said = f"main had no result for it: {read['main_error']}"
        else:
            said = f"main had no result for it on the latest commit of {main_branch}"
        lines.append(f"- `{check['name']}` failed: {check.get('url') or 'no link'} ({said})")
    also = [c["name"] for c in read.get("checks") or [] if c.get("main_result") == ON_MAIN_FAILED]
    if also:
        lines += ["", f"Failing on {main_branch} too, so not this task's: {', '.join(also)}."]
    lines += [
        "",
        "Fix it on the task's branch and complete the task again; its next push runs CI again.",
    ]
    return "\n".join(lines)


# --- git -----------------------------------------------------------------------------------------


def build_branch_name(build_id: str) -> str:
    return f"{BRANCH_PREFIX}{build_id}"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    from .project_checks import _git as git

    return git(root, *args)


def _net(root: Path, *args: str) -> subprocess.CompletedProcess:
    """A git call that reaches the remote: never prompts for a credential, bounded in time."""
    try:
        return traces.run(
            ["git", *args],
            ok_codes=(0, 1, 128),
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=NETWORK_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, 1, "", f"{type(exc).__name__}: {exc}")


def _sha(root: Path, ref: str) -> Optional[str]:
    result = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    sha = (result.stdout or "").strip()
    return sha if result.returncode == 0 and sha else None


def _contains(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        ancestor == descendant
        or _git(root, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0
    )


def _merge_tree(root: Path, ours: str, theirs: str) -> Tuple[Optional[str], List[str]]:
    """`(tree, [])` of *theirs* merged onto *ours* with plumbing, or `(None, conflicting paths)`."""
    merged = _git(root, "merge-tree", "--write-tree", "--name-only", ours, theirs)
    lines = (merged.stdout or "").splitlines()
    if merged.returncode == 0 and lines:
        return lines[0].strip(), []
    paths: List[str] = []
    for line in lines[1:]:
        if not line.strip():
            break
        paths.append(line.strip())
    return None, paths or ["(unknown path)"]


@dataclass
class Prepared:
    """What `prepare` built: the tree a PR build's task is checked on, and what would be pushed."""

    #: GitHub's main, as fetched.
    remote_main: Optional[str] = None
    #: The build branch, with GitHub's main merged in where it had moved (FR-8).
    base: Optional[str] = None
    #: *base* with the task's work merged on: what the checks run on.
    merged: Optional[str] = None
    #: Conflicting paths, and whether they conflict with GitHub's main rather than the task's work.
    conflict: List[str] = field(default_factory=list)
    with_main: bool = False
    error: str = ""


def prepare(
    root: Path, remote: str, main_branch: str, branch: str, task_id: str, shas: Sequence[str]
) -> Prepared:
    """Fetch GitHub's main, merge it into the build branch where it moved (FR-8), and merge the
    task's targets on with plumbing: no checkout and no branch moves. Blocking."""
    from .landing_queue import build_chain

    tracking = f"refs/remotes/{remote}/{main_branch}"
    fetched = _net(root, "fetch", "-q", remote, f"+refs/heads/{main_branch}:{tracking}")
    if fetched.returncode != 0:
        said = (fetched.stderr or fetched.stdout or "").strip()[:1500]
        said = said or f"git fetch exited {fetched.returncode}"
        return Prepared(error=f"could not fetch {main_branch} from {remote}: {said}")
    remote_main = _sha(root, tracking)
    if remote_main is None:
        return Prepared(error=f"{remote} has no branch {main_branch}")
    local = _sha(root, f"refs/heads/{branch}")
    base = local or remote_main
    if local is not None and not _contains(root, remote_main, local):
        tree, paths = _merge_tree(root, local, remote_main)
        if tree is None:
            return Prepared(remote_main=remote_main, conflict=paths, with_main=True)
        commit = _git(
            root,
            "commit-tree",
            tree,
            "-p",
            local,
            "-p",
            remote_main,
            "-m",
            f"Merge {remote}/{main_branch} into {branch}",
        )
        if commit.returncode != 0:
            return Prepared(error=f"git commit-tree failed: {(commit.stderr or '').strip()[:300]}")
        base = commit.stdout.strip()
    chain = build_chain(root, base, [(task_id, list(shas))])
    if chain.error:
        return Prepared(remote_main=remote_main, base=base, error=chain.error)
    if chain.conflicts:
        return Prepared(remote_main=remote_main, base=base, conflict=list(chain.conflicts[0][1]))
    merged = chain.prefixes[-1] if chain.prefixes else base
    return Prepared(remote_main=remote_main, base=base, merged=merged)


@dataclass
class Pushed:
    sha: Optional[str] = None
    error: str = ""
    #: The remote refused the lease: the branch on GitHub is not the one the Hub last pushed.
    refused: bool = False


def push(
    root: Path,
    remote: str,
    branch: str,
    merged: str,
    remote_main: str,
    expected: Optional[str],
    *,
    single_commit: bool,
    message: str,
) -> Pushed:
    """Push *merged* -- or, with the single commit (FR-7), one commit on GitHub's main holding its
    tree -- to the build branch, replacing only *expected*, the commit the Hub last pushed (none:
    the branch must not exist yet). The local build branch follows a push that went. Blocking."""
    commit = merged
    if single_commit:
        tree = (_git(root, "rev-parse", "--verify", f"{merged}^{{tree}}").stdout or "").strip()
        made = _git(root, "commit-tree", tree, "-p", remote_main, "-m", message) if tree else None
        if made is None or made.returncode != 0:
            why = (made.stderr or "").strip()[:300] if made is not None else "no tree"
            return Pushed(error=f"git commit-tree failed: {why}")
        commit = made.stdout.strip()
    ref = f"refs/heads/{branch}"
    pushed = _net(
        root,
        "push",
        "--porcelain",
        f"--force-with-lease={ref}:{expected or ''}",
        remote,
        f"{commit}:{ref}",
    )
    if pushed.returncode != 0:
        said = ((pushed.stderr or "") + (pushed.stdout or "")).strip()[:2000]
        refused = any(word in said for word in ("stale info", "rejected", "fetch first"))
        if refused:
            return Pushed(
                error=(
                    f"GitHub refused the push to {branch}: the branch there is not the one the "
                    f"Hub last pushed ({(expected or 'none')[:12]}), so somebody else pushed to "
                    f"it, and nothing was replaced.\n{said}"
                ),
                refused=True,
            )
        return Pushed(error=f"the push to {branch} failed: {said or 'git push failed'}")
    _git(root, "update-ref", ref, commit)
    return Pushed(sha=commit)


# --- the PR's title and description (FR-6) -------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _identifier_order(identifier: str) -> Tuple[int, str]:
    digits = identifier.rsplit("-", 1)[-1]
    return (int(digits) if digits.isdigit() else 0, identifier)


async def describe(session: AsyncSession, build: Any) -> Tuple[str, str]:
    """`(title, body)` of *build*'s PR: the spec's title; the spec path, each requirement the build
    serves by identifier and statement with its accepted evidence, and each task with its state."""
    from . import project_workspace, spec_reading
    from .db.models import (
        RequirementEvidence,
        SpecDocument,
        SpecRequirement,
        Task,
        TaskRequirementLink,
    )
    from .landing_queue import latest_landing

    document = await session.get(SpecDocument, build.document_id)
    title = (document.title if document is not None else "") or f"Build {build.id}"
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.build_id == build.id).order_by(Task.created_at, Task.id)
            )
        ).scalars()
    )
    requirements: List[Any] = []
    if tasks:
        requirements = list(
            (
                await session.execute(
                    select(SpecRequirement)
                    .join(
                        TaskRequirementLink,
                        TaskRequirementLink.requirement_id == SpecRequirement.id,
                    )
                    .where(TaskRequirementLink.task_id.in_([task.id for task in tasks]))
                    .distinct()
                )
            ).scalars()
        )
    requirements.sort(key=lambda requirement: _identifier_order(requirement.identifier))
    evidence: Dict[str, List[str]] = {}
    if requirements:
        for requirement_id, evidence_id in (
            await session.execute(
                select(RequirementEvidence.requirement_id, RequirementEvidence.id)
                .where(
                    RequirementEvidence.requirement_id.in_([r.id for r in requirements]),
                    RequirementEvidence.review_state == "accepted",
                )
                .order_by(RequirementEvidence.produced_at)
            )
        ).all():
            evidence.setdefault(requirement_id, []).append(evidence_id)
    wording: Dict[str, Dict[str, Any]] = {}
    try:
        workspace = await project_workspace.resolve_project_workspace(session, build.project_id)
        payloads = await spec_reading.payloads_for_documents(
            session, workspace, [build.document_id]
        )
        wording = spec_reading.statements_by_key(payloads.get(build.document_id))
    except Exception:  # noqa: BLE001 -- a description without the wording beats no push
        wording = {}

    path = document.path if document is not None else build.document_id
    lines = [f"Built by AgentWeave from the specification `{path}`.", "", "## Requirements", ""]
    for requirement in requirements:
        statement = (wording.get(requirement.key) or {}).get("statement") or requirement.key
        accepted = evidence.get(requirement.id) or []
        lines.append(f"- **{requirement.identifier}** {statement}")
        lines.append(
            "  - accepted evidence: " + (", ".join(f"`{e}`" for e in accepted) or "none yet")
        )
    if not requirements:
        lines.append("- none")
    lines += ["", "## Tasks", ""]
    for task in tasks:
        landing = await latest_landing(session, task.id)
        state = task.status
        if landing is not None and task.status == "approved":
            state = f"approved, {landing.state.replace('_', ' ')}"
        key = task.spec_task_key or task.display_id
        lines.append(f"- `{key}` {task.display_id} {task.title}: {state}")
    lines += [
        "",
        "Merging is yours: AgentWeave never merges, approves or retargets this pull request.",
    ]
    return title, "\n".join(lines) + "\n"


async def every_task_pushed(session: AsyncSession, build_id: str) -> bool:
    """Whether every task of the build is approved with its latest landing pushed (FR-5)."""
    from .db.models import Task
    from .landing_queue import latest_landing

    tasks = list((await session.execute(select(Task).where(Task.build_id == build_id))).scalars())
    if not tasks:
        return False
    for task in tasks:
        landing = await latest_landing(session, task.id)
        if task.status != "approved" or landing is None or landing.state != PUSHED:
            return False
    return True


def _number_of(url: str) -> Optional[int]:
    found = re.search(r"/pull/(\d+)", url or "")
    return int(found.group(1)) if found else None


def sync_pr(
    root: Path,
    branch: str,
    main_branch: str,
    number: Optional[int],
    state: Optional[str],
    title: str,
    body: str,
    ready: bool,
) -> Dict[str, Any]:
    """Open the PR as a draft where there is none (FR-4), else rewrite its title and description
    (FR-6); then ready it or return it to draft as *ready* says (FR-5). Blocking. Answers
    `{number, url, state, error}`, `error` GitHub's own words where a call failed."""
    out: Dict[str, Any] = {"number": number, "url": None, "state": state, "error": None}
    handle, body_file = tempfile.mkstemp(prefix="aw-pr-", suffix=".md")
    with os.fdopen(handle, "w", encoding="utf-8") as written:
        written.write(body)
    try:
        if number is None:
            made = gh(
                root,
                "pr",
                "create",
                "--draft",
                "--base",
                main_branch,
                "--head",
                branch,
                "--title",
                title,
                "--body-file",
                body_file,
            )
            url = next((w for w in (made.stdout or "").split() if "/pull/" in w), "")
            if made.returncode != 0 or _number_of(url) is None:
                out["error"] = f"could not open the pull request: {_gh_error(made)}"
                return out
            out.update(number=_number_of(url), url=url, state=DRAFT)
        else:
            edited = gh(root, "pr", "edit", str(number), "--title", title, "--body-file", body_file)
            if edited.returncode != 0:
                out["error"] = f"could not update the pull request: {_gh_error(edited)}"
        if ready and out["state"] != READY:
            done = gh(root, "pr", "ready", str(out["number"]))
            if done.returncode == 0:
                out["state"] = READY
            else:
                out["error"] = f"could not mark the pull request ready: {_gh_error(done)}"
        elif not ready and out["state"] == READY:
            done = gh(root, "pr", "ready", str(out["number"]), "--undo")
            if done.returncode == 0:
                out["state"] = DRAFT
            else:
                out["error"] = f"could not return the pull request to draft: {_gh_error(done)}"
        return out
    finally:
        with contextlib.suppress(OSError):
            os.unlink(body_file)


async def _record_pr(build_id: str, synced: Dict[str, Any]) -> None:
    from .db.engine import async_session_factory
    from .db.models import Build

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        if build is None:
            return
        if synced.get("number") is not None:
            build.pr_number = synced["number"]
        if synced.get("url"):
            build.pr_url = synced["url"]
        if synced.get("state"):
            build.pr_state = synced["state"]
        build.pr_last_asked_at = _now()
        build.pr_error = synced.get("error")
        await session.commit()


async def refresh(build_id: str, *, opening: bool = False) -> None:
    """Rewrite the build's PR from its tasks now: open it as a draft where *opening* and there is
    none, rewrite its title and description, and ready it or return it to draft (FR-4..FR-6).
    Nothing where the build has no open PR and is not opening one."""
    from . import blocking, project_workspace
    from .db.engine import async_session_factory
    from .db.models import Build, Project

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        if build is None:
            return
        if build.pr_number is None and not opening:
            return
        if build.pr_number is not None and build.pr_state not in (DRAFT, READY):
            return  # merged or closed: not the Hub's to change
        project = await session.get(Project, build.project_id)
        try:
            root = (
                await project_workspace.resolve_project_workspace(session, build.project_id)
            ).root
        except Exception:  # noqa: BLE001 -- nowhere to talk to GitHub from
            return
        title, body = await describe(session, build)
        ready = await every_task_pushed(session, build.id)
        if project is not None and project.pr_ci_full_check:
            ci = build.pr_ci or {}
            ready = ready and ci.get("state") == CHECK_PASSED
            ready = ready and ci.get("head_sha") == build.pr_pushed_sha
        number, state = build.pr_number, build.pr_state
        main_branch = (project.main_branch if project is not None else None) or "main"
        await session.commit()
    synced = await blocking.run(
        sync_pr, root, build_branch_name(build_id), main_branch, number, state, title, body, ready
    )
    await _record_pr(build_id, synced)


# --- a task of the build sent back returns the PR to draft (FR-5) --------------------------------

_SENT_BACK_KEY = "pull_request_sent_back"


def sent_back_after_commit(session: AsyncSession, task: Any) -> None:
    """Once the caller's transaction commits, return *task*'s build's PR to draft and rewrite its
    description: a task of the build left `approved`, so not every task is pushed (FR-5)."""
    if task.build_id:
        session.sync_session.info.setdefault(_SENT_BACK_KEY, set()).add(
            (task.project_id, task.build_id)
        )


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return
    builds = session.info.pop(_SENT_BACK_KEY, set())
    if not builds:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    from . import landing_queue

    for project_id, build_id in builds:
        landing_queue._start(
            project_id,
            _refresh_locked(project_id, build_id),
            f"return the pull request of {build_id} to draft",
        )


@event.listens_for(Session, "after_transaction_end")
def _after_transaction_end(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_SENT_BACK_KEY, None)


async def _refresh_locked(project_id: str, build_id: str) -> None:
    """`refresh` behind the project's landing queue, so it never races a push to the same PR."""
    from . import landing_queue

    async with landing_queue._lock(project_id):
        await refresh(build_id)


# --- landing one approved task on the PR ---------------------------------------------------------


def _conflict_report(display_id: str, paths: Sequence[str], with_main: bool, main: str) -> str:
    against = f"GitHub's {main}" if with_main else "the build branch"
    return (
        f"Task {display_id}'s work does not merge cleanly onto {against} before its push to the "
        f"build's pull request: {', '.join(list(paths)[:10])}. Merge {main} from GitHub into the "
        "task's branch, resolve the conflict, and complete the task again. Nothing was pushed."
    )


async def land(landing_id: str, checks: List[Dict[str, Any]]) -> bool:
    """Land one PR build's approved task on its pull request: prepared on the build branch with
    GitHub's main merged in (FR-8), checked as a batch of one (FR-3), pushed (FR-4, FR-7), and the
    PR opened, described, readied or drafted (FR-4..FR-6). `False` where the Hub could not produce
    a result and the landing waits in the queue for another try."""
    from . import blocking, landing_queue, project_checks, project_workspace
    from .db.engine import async_session_factory
    from .db.models import Build, LandingBatch, Project, Task, TaskLanding
    from .task_transitions import SEND_BACK_DEFECT, SEND_BACK_MERGE_NEEDED
    from .utils import short_id

    lq = landing_queue
    batch_id = f"lbat-{short_id()}"
    why = ""
    async with async_session_factory() as session:
        landing = await session.get(TaskLanding, landing_id)
        task = await session.get(Task, landing.task_id) if landing is not None else None
        build = await session.get(Build, task.build_id) if task and task.build_id else None
        project = await session.get(Project, landing.project_id) if landing is not None else None
        if landing is None or task is None or build is None or project is None:
            return True
        root: Optional[Path] = None
        try:
            root = (await project_workspace.resolve_project_workspace(session, project.id)).root
        except Exception as exc:  # noqa: BLE001 -- recorded on the landing
            why = f"the project directory is unavailable: {exc}"
        main_branch = project.main_branch
        single = bool(project.pr_single_commit)
        ci_on = bool(project.pr_ci_full_check)
        expected = build.pr_pushed_sha
        display, task_id = task.display_id, task.id
        build_id, project_id = build.id, project.id
        shas = lq.target_shas(landing)
        unchecked = landing.unchecked
        await session.commit()
    if root is None or not main_branch:
        await _not_pushed(landing_id, build_id, why or "the project has no main branch set")
        return True
    if not shas:
        await _not_pushed(
            landing_id, build_id, "nothing to push: approval named no commit of the task's work"
        )
        return True
    remote = await blocking.run(github_remote, root)
    if remote is None:
        await _not_pushed(landing_id, build_id, "the project directory has no GitHub remote")
        return True
    # Before each push GitHub is asked whether the PR is still open (FR-9): the branch of a PR
    # merged or closed there takes no more work.
    await ask(project_id, build_id)
    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        ended = build.pr_state if build is not None and build.pr_state in (MERGED, CLOSED) else None
        await session.commit()
    if ended is not None:
        await _not_pushed(
            landing_id,
            build_id,
            f"the build's pull request was {ended} on GitHub, so nothing more is pushed to it",
        )
        return True
    async with async_session_factory() as session:
        session.add(
            LandingBatch(
                id=batch_id,
                project_id=project_id,
                base_sha="",
                state="checking",
                task_ids=[task_id],
                prefixes=[],
                results=[],
                narrowing=[],
            )
        )
        await session.commit()
    if not await lq._claim([landing_id], lq.CHECKING, batch_id):
        await lq._end_batch(batch_id, "failed", error="the landing was no longer queued")
        return True
    if not await lq._drop_unapproved([landing]):
        await lq._end_batch(batch_id, "failed", error="the task is no longer approved")
        return True
    branch = build_branch_name(build_id)
    repo = root
    prepared = await blocking.run(lambda: prepare(repo, remote, main_branch, branch, task_id, shas))
    if prepared.error:
        await lq._requeue([landing_id])
        await lq._end_batch(batch_id, "failed", error=prepared.error)
        await _record_error(build_id, prepared.error)
        return False
    if prepared.conflict:
        against = f"GitHub's {main_branch}" if prepared.with_main else "the build branch"
        await lq._end_batch(batch_id, "failed", error="a merge conflict before the push")
        await lq._send_back(
            landing_id,
            batch_id,
            _conflict_report(display, prepared.conflict, prepared.with_main, main_branch),
            SEND_BACK_MERGE_NEEDED,
            f"Its work conflicts with {against} before its push to the build's pull request: "
            "merge it again.",
        )
        return True
    base, merged = prepared.base or "", prepared.merged or ""
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.base_sha, batch.merged_sha, batch.prefixes = base, merged, [merged]
        await session.commit()
    if checks and not unchecked:
        outcome = await lq.run_batch_checks(
            root, project_id, batch_id, base, merged, checks, [landing]
        )
        unjudged_again = outcome.unjudged and await lq._previous_batch_unjudged(
            batch_id, project_id, [task_id]
        )
        if outcome.state == "error" and not unjudged_again:
            # The Hub produced no verdict (or a first unjudged timeout): tried again later.
            await lq._requeue([landing_id])
            await lq._end_batch(batch_id, "failed", error=outcome.error)
            return False
        own = [
            result
            for result in outcome.results
            if project_checks.failed(result) and not project_checks.preexisting(result)
        ]
        if unjudged_again or own:
            if unjudged_again:
                timed = next(r for r in outcome.results if project_checks.unjudged_timeout(r))
                report = lq._timeout_report(batch_id, outcome, timed, display, [])
            else:
                report = lq._failure_report(batch_id, outcome, own[0], display, [])
            await lq._end_batch(batch_id, "failed", error="the checks failed: nothing was pushed")
            await lq._send_back(
                landing_id,
                batch_id,
                report,
                SEND_BACK_DEFECT,
                "The project's checks failed on the build branch with its work merged in.",
            )
            return True
    if not await lq._drop_unapproved([landing]):
        await lq._end_batch(batch_id, "failed", error="the task is no longer approved")
        return True
    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        title, _ = await describe(session, build)
        await session.commit()
    remote_main = prepared.remote_main or ""
    pushed = await blocking.run(
        lambda: push(
            repo,
            remote,
            branch,
            merged,
            remote_main,
            expected,
            single_commit=single,
            message=f"{title}\n\nBuilt by AgentWeave (build {build_id}).",
        )
    )
    if pushed.sha is None:
        await lq._end_batch(batch_id, "failed", error=pushed.error)
        await _not_pushed(landing_id, build_id, pushed.error)
        return True
    async with async_session_factory() as session:
        row = await session.get(TaskLanding, landing_id)
        row.state, row.landed_sha, row.ended_at = PUSHED, pushed.sha, _now()
        row.reason = f"pushed to {branch}"
        build = await session.get(Build, build_id)
        build.pr_pushed_sha, build.pr_error = pushed.sha, None
        batch = await session.get(LandingBatch, batch_id)
        batch.state, batch.ended_at = PUSHED, _now()
        await lq._close_batch_run(session, batch)
        if ci_on:
            await ci_pushed(session, build, row)
        await session.commit()
        await lq._announce(session, [landing_id])
    await refresh(build_id, opening=True)
    if ci_on:
        watch_ci(project_id, build_id)
    return True


async def _record_error(build_id: str, error: str) -> None:
    from .db.engine import async_session_factory
    from .db.models import Build

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        if build is not None:
            build.pr_error = error[:4000]
            await session.commit()


async def _not_pushed(landing_id: str, build_id: str, reason: str) -> None:
    """Nothing was pushed for the landing: it ends `not_landed` with *reason*, which the build
    shows (FR-7, FR-13); retrying the task's integration queues it again."""
    from . import landing_queue
    from .db.engine import async_session_factory
    from .db.models import Build, TaskLanding

    async with async_session_factory() as session:
        row = await session.get(TaskLanding, landing_id)
        if row is not None:
            row.state, row.reason, row.ended_at = landing_queue.NOT_LANDED, reason, _now()
        build = await session.get(Build, build_id)
        if build is not None:
            build.pr_error = reason[:4000]
        await session.commit()
        await landing_queue._announce(session, [landing_id])


# --- noticing a merged or closed PR (FR-9, FR-10) ------------------------------------------------

MERGED = "merged"
CLOSED = "closed"

#: The asks in flight, one per project: an action while one runs joins it rather than asking again.
_asking: Dict[Tuple[int, str], "asyncio.Task[Any]"] = {}


def notice(project_id: str, why: str) -> None:
    """Something is about to start in *project_id*, or the operator is looking (FR-9): ask GitHub
    about its builds' open PRs in the background. Never waits and never raises -- a slow GitHub
    must not delay a turn starting -- and joins an ask already in flight. Nothing else is
    scheduled: the one timer is `watch_ci`'s, while CI on a head is pending."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = (id(loop), project_id)
    running = _asking.get(key)
    if running is not None and not running.done():
        return
    try:
        job = loop.create_task(_ask_logged(project_id, why))
    except Exception:  # noqa: BLE001
        logger.warning("could not ask GitHub about %s's pull requests", project_id, exc_info=True)
        return
    _asking[key] = job

    def _done(finished: "asyncio.Task[Any]") -> None:
        if _asking.get(key) is finished:
            del _asking[key]

    job.add_done_callback(_done)


async def _ask_logged(project_id: str, why: str) -> None:
    try:
        await ask(project_id)
    except Exception:  # noqa: BLE001 -- the next action asks again
        logger.warning("asking GitHub about %s (%s) failed", project_id, why, exc_info=True)


async def settle_asks() -> None:
    """Wait for the asks in flight (tests)."""
    pending = [job for job in _asking.values() if not job.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def open_pr_builds(session: AsyncSession, project_id: Optional[str] = None) -> List[Any]:
    """The builds whose PR is open on GitHub as far as the Hub last knew (draft or ready)."""
    from .builds import LANDING_PULL_REQUEST
    from .db.models import Build

    query = select(Build).where(
        Build.landing == LANDING_PULL_REQUEST,
        Build.pr_number.is_not(None),
        Build.pr_state.in_((DRAFT, READY)),
    )
    if project_id is not None:
        query = query.where(Build.project_id == project_id)
    return list((await session.execute(query)).scalars())


def read_pr(root: Path, number: int) -> Dict[str, Any]:
    """GitHub's word on PR *number*: `{state, merge_commit, error}`, *state* one of `draft`,
    `ready`, `merged`, `closed`, or None with *error* where it could not be read. Blocking."""
    import json

    def failed(error: str) -> Dict[str, Any]:
        return {"state": None, "merge_commit": None, "error": error}

    answered = gh(root, "pr", "view", str(number), "--json", "state,isDraft,mergeCommit")
    if answered.returncode != 0:
        return failed(f"could not read the pull request: {_gh_error(answered)}")
    try:
        data = json.loads(answered.stdout or "{}")
    except ValueError:
        return failed(f"GitHub's answer was not JSON: {(answered.stdout or '')[:300]}")
    state = str(data.get("state") or "").upper()
    if state == "MERGED":
        merge_commit = (data.get("mergeCommit") or {}).get("oid") or None
        return {"state": MERGED, "merge_commit": merge_commit, "error": None}
    if state == "CLOSED":
        return {"state": CLOSED, "merge_commit": None, "error": None}
    if state == "OPEN":
        open_state = DRAFT if data.get("isDraft") else READY
        return {"state": open_state, "merge_commit": None, "error": None}
    return failed(f"GitHub answered the pull request's state as {state!r}")


async def ask(project_id: str, build_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ask GitHub now for the state of *project_id*'s open PRs (only *build_id*'s, where given),
    and act on each answer (FR-10); then, where one was found merged, bring the local main forward
    when that is safe (FR-11). Answers what each build was found to be."""
    from . import blocking, project_workspace
    from .db.engine import async_session_factory

    async with async_session_factory() as session:
        builds = [
            build
            for build in await open_pr_builds(session, project_id)
            if build_id is None or build.id == build_id
        ]
        if not builds:
            return []
        try:
            root = (await project_workspace.resolve_project_workspace(session, project_id)).root
        except Exception as exc:  # noqa: BLE001 -- nowhere to ask from; the build says why
            for build in builds:
                build.pr_error = f"the project directory is unavailable: {exc}"[:4000]
            await session.commit()
            return []
        asked = [(build.id, int(build.pr_number)) for build in builds]
        await session.commit()
    found: List[Dict[str, Any]] = []
    for each, number in asked:
        answer = await blocking.run(read_pr, root, number)
        await _apply(each, answer)
        found.append({"build_id": each, **answer})
        if answer["state"] in (DRAFT, READY):
            # CI on the head, where the setting is on and it has not concluded (FR-5).
            await check_ci(each)
    if any(answer["state"] == MERGED for answer in found):
        await bring_main_forward(project_id)
    return found


async def _apply(build_id: str, answer: Dict[str, Any]) -> None:
    """Record GitHub's answer on the build. A merged PR lands each task the build branch carried,
    naming the merge commit; a closed one records them not landed. The build branch is kept, here
    and on GitHub: nothing here deletes a branch (FR-10)."""
    from . import landing_queue, task_integration
    from .db.engine import async_session_factory
    from .db.models import Build, Project, Task
    from .task_transition_service import _redrain_after_commit

    ti = task_integration
    state = answer.get("state")
    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        if build is None:
            return
        build.pr_last_asked_at = _now()
        if state is None:
            build.pr_error = (answer.get("error") or "")[:4000] or None
            await session.commit()
            await _broadcast_build(build.project_id, build.id, build.state)
            return
        build.pr_error = None
        build.pr_state = state
        changed: List[str] = []
        if state in (MERGED, CLOSED):
            project = await session.get(Project, build.project_id)
            main_branch = (project.main_branch if project is not None else None) or ""
            merge_commit = answer.get("merge_commit")
            tasks = (await session.execute(select(Task).where(Task.build_id == build.id))).scalars()
            for task in list(tasks):
                landing = await landing_queue.latest_landing(session, task.id)
                if landing is None or landing.state != PUSHED:
                    continue
                if state == MERGED:
                    # One merged integration record per target, carrying GitHub's merge commit: how
                    # coverage reads the work as on main, and how the main watch knows the move
                    # that brings it here was this merge and not somebody else's.
                    for entry in landing.targets or []:
                        landing_queue._record(
                            session,
                            task,
                            ti.IntegrationResult(
                                outcome=ti.MERGED,
                                commit_sha=entry.get("commit_sha"),
                                source_branch=entry.get("branch"),
                                target_branch=main_branch,
                                merged_sha=merge_commit,
                            ),
                            landing,
                        )
                    landing.state, landing.landed_sha = landing_queue.LANDED, merge_commit
                    landing.reason = f"merged on GitHub in pull request #{build.pr_number}" + (
                        f" as {merge_commit[:12]}" if merge_commit else ""
                    )
                else:
                    landing.state = landing_queue.NOT_LANDED
                    landing.reason = (
                        f"pull request #{build.pr_number} was closed on GitHub without merging; "
                        f"the build branch {build_branch_name(build.id)} is kept"
                    )
                landing.ended_at = _now()
                changed.append(landing.id)
            if state == MERGED and changed:
                from . import main_watch

                if merge_commit:
                    main_watch.note_own_merge(merge_commit)
                _redrain_after_commit(session, build.project_id)
        project_id, build_state = build.project_id, build.state
        await session.commit()
        if changed:
            await landing_queue._announce(session, changed)
    await _broadcast_build(project_id, build_id, build_state)


async def _broadcast_build(project_id: str, build_id: str, state: str) -> None:
    from .sse import sse_manager

    try:
        await sse_manager.broadcast(project_id, "build_updated", {"id": build_id, "state": state})
    except Exception:  # noqa: BLE001
        logger.debug("build broadcast failed", exc_info=True)


async def notice_at_startup() -> int:
    """The Hub started (FR-9): ask, in the background, about every project with an open PR."""
    from .db.engine import async_session_factory

    async with async_session_factory() as session:
        builds = await open_pr_builds(session)
        projects = sorted({build.project_id for build in builds})
        pending = [
            (build.project_id, build.id)
            for build in builds
            if (build.pr_ci or {}).get("state") == CHECK_PENDING
        ]
    for project_id in projects:
        notice(project_id, "the Hub started")
    for project_id, build_id in pending:
        watch_ci(project_id, build_id)  # the interval asks a restart interrupted (FR-5)
    return len(projects)


# --- the local main after a merge (FR-11) --------------------------------------------------------


@dataclass
class MainState:
    """The project's local main against GitHub's, as last fetched."""

    branch: str = ""
    local: Optional[str] = None
    github: Optional[str] = None
    #: GitHub's main holds commits the local main does not.
    behind: bool = False
    #: Moved forward by this call.
    updated: bool = False
    #: Why it cannot be brought forward now, where it is behind; empty where it can.
    reason: str = ""

    def view(self) -> Dict[str, Any]:
        return {
            "branch": self.branch,
            "local": self.local,
            "github": self.github,
            "behind": self.behind,
            "updated": self.updated,
            "can_update": self.behind and not self.reason,
            "reason": self.reason or None,
        }


def _checked_out_at(root: Path, branch: str) -> Optional[Path]:
    """The worktree that has *branch* checked out, or None."""
    listed = _git(root, "worktree", "list", "--porcelain")
    path: Optional[str] = None
    for line in (listed.stdout or "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :].strip()
        elif line.strip() == f"branch refs/heads/{branch}" and path:
            return Path(path)
    return None


def main_state(
    root: Path,
    remote: str,
    main_branch: str,
    hub_written: Sequence[str] = (),
    *,
    fetch: bool = False,
    move: bool = False,
) -> MainState:
    """Where the local main stands against GitHub's: fetched first where *fetch*, and moved to it
    where *move* and that is safe -- a fast-forward, onto a main that is not checked out with
    uncommitted changes. Never touches a checkout holding changes. Blocking."""
    from .task_integration import has_uncommitted_changes

    out = MainState(branch=main_branch)
    local_ref, tracking = f"refs/heads/{main_branch}", f"refs/remotes/{remote}/{main_branch}"
    if fetch:
        fetched = _net(root, "fetch", "-q", remote, f"+{local_ref}:{tracking}")
        if fetched.returncode != 0:
            said = (fetched.stderr or fetched.stdout or "").strip()[:1500] or "git fetch failed"
            out.reason = f"could not fetch {main_branch} from {remote}: {said}"
    out.local, out.github = _sha(root, local_ref), _sha(root, tracking)
    if out.github is None or out.local == out.github:
        return out
    if out.local is not None and _contains(root, out.github, out.local):
        return out  # ahead of GitHub, not behind
    out.behind = True
    if out.reason:
        return out
    if out.local is None:
        out.reason = f"there is no local {main_branch} to bring forward"
        return out
    if not _contains(root, out.local, out.github):
        out.reason = (
            f"the local {main_branch} has commits GitHub's {main_branch} does not, so it cannot "
            f"be fast-forwarded: merge {remote}/{main_branch} into it yourself"
        )
        return out
    checkout = _checked_out_at(root, main_branch)
    if checkout is not None:
        same = checkout.resolve() == root.resolve()
        if has_uncommitted_changes(checkout, hub_written if same else ()):
            out.reason = (
                f"{main_branch} is checked out at {checkout} with uncommitted changes: commit or "
                "stash them, then Update. The Hub never touches a checkout holding your changes"
            )
            return out
    if not move:
        return out
    if checkout is None:
        moved = _git(root, "update-ref", local_ref, out.github, out.local)
    else:
        moved = _git(checkout, "merge", "--ff-only", "-q", out.github)
    if moved.returncode != 0:
        said = ((moved.stderr or "") + (moved.stdout or "")).strip()[:1500] or "it refused"
        out.reason = f"git could not fast-forward {main_branch}: {said}"
        return out
    out.local, out.behind, out.updated = out.github, False, True
    return out


async def _main_inputs(project_id: str) -> Optional[Tuple[Path, str, str, List[str]]]:
    """`(root, GitHub remote, main branch, Hub-written files)`, or None where there is no GitHub
    main to compare with here (PR landing off, no main branch, no directory, no GitHub remote)."""
    from . import blocking, landing_queue, project_workspace
    from .db.engine import async_session_factory
    from .db.models import Project

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if project is None or not project.pr_landing or not project.main_branch:
            return None
        main_branch = project.main_branch
        try:
            root = (await project_workspace.resolve_project_workspace(session, project_id)).root
        except Exception:  # noqa: BLE001
            return None
        written = sorted(await landing_queue._hub_written(session, project_id))
        await session.commit()
    remote = await blocking.run(github_remote, root)
    if remote is None:
        return None
    return root, remote, main_branch, written


async def bring_main_forward(project_id: str) -> Optional[MainState]:
    """Fetch GitHub's main and fast-forward the local main to it when that is safe (FR-11): after a
    PR is found merged, and the Update button. Where it is not safe the answer says why, and the
    project shows that main is behind GitHub. None where PR landing does not apply."""
    from . import blocking, landing_queue

    inputs = await _main_inputs(project_id)
    if inputs is None:
        return None
    root, remote, main_branch, written = inputs
    # Serialized with worktree creation and merges, which also move branches in this repository.
    state = await blocking.run_serialized(
        lambda: main_state(root, remote, main_branch, written, fetch=True, move=True)
    )
    if state.updated:
        await landing_queue._refresh_reachability(project_id, root)
    if state.updated or state.behind:
        await _broadcast_main(project_id, state)
    return state


async def main_behind(project_id: str) -> Optional[MainState]:
    """Whether the local main is behind GitHub's as last fetched, and whether Update could bring it
    forward now; neither fetches nor moves anything. None where PR landing does not apply."""
    from . import blocking

    inputs = await _main_inputs(project_id)
    if inputs is None:
        return None
    root, remote, main_branch, written = inputs
    return await blocking.run(lambda: main_state(root, remote, main_branch, written))


async def _broadcast_main(project_id: str, state: MainState) -> None:
    from .sse import sse_manager

    try:
        await sse_manager.broadcast(project_id, "main_behind_github", state.view())
    except Exception:  # noqa: BLE001
        logger.debug("main broadcast failed", exc_info=True)


# --- CI on the PR's head: recorded, asked for while pending, acted on (FR-4, FR-5, FR-11) --------

#: CI states that need no more asking: every counted check on the head concluded.
_CI_CONCLUDED = frozenset({CHECK_PASSED, CHECK_FAILED, CI_FAILING_ON_MAIN})

#: The CI watches running, one per build: each asks GitHub at the project's interval while the
#: head's counted checks are pending (`watch_ci`). A push while one runs is folded into it.
_watching: Dict[Tuple[int, str], "asyncio.Task[Any]"] = {}
_rewatch: set = set()


async def _sleep(seconds: float) -> None:
    """The wait between asks (a seam: tests run the clock themselves)."""
    await asyncio.sleep(seconds)


def _aware(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


async def _build_landings(session: AsyncSession, build_id: str) -> List[Any]:
    """Each task of the build's latest landing, where it has one."""
    from .db.models import Task
    from .landing_queue import latest_landing

    out = []
    for task in (await session.execute(select(Task).where(Task.build_id == build_id))).scalars():
        landing = await latest_landing(session, task.id)
        if landing is not None:
            out.append(landing)
    return out


async def ci_pushed(session: AsyncSession, build: Any, landing: Any) -> None:
    """*landing* was just pushed as the head of *build*'s PR in a project with the CI setting on:
    CI is pending on that commit, the cutoff counts from now, and an earlier head's result that
    had not concluded is superseded: it can no longer decide anything (FR-4, FR-5). The caller
    commits, then starts the watch (`watch_ci`)."""
    now = _now()
    pending = {
        "state": CHECK_PENDING,
        "head_sha": landing.landed_sha,
        "checks": [],
        "last_asked_at": None,
        "error": None,
    }
    for other in await _build_landings(session, build.id):
        if other.id == landing.id or not other.ci:
            continue
        if other.ci.get("state") not in _CI_CONCLUDED | {CI_SUPERSEDED}:
            other.ci = {**other.ci, "state": CI_SUPERSEDED}
    build.pr_ci, build.pr_ci_pushed_at = pending, now
    landing.ci = dict(pending)


async def check_ci(build_id: str) -> Optional[str]:
    """Read CI on the build's PR head now where it has not concluded there, and act on it
    (`_apply_ci`). Answers CI's state on the build afterwards; None for a build with nothing to
    read (not a PR build, the setting off, nothing pushed, the PR merged or closed)."""
    from . import blocking, project_workspace
    from .builds import LANDING_PULL_REQUEST
    from .db.engine import async_session_factory
    from .db.models import Build, Project

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        project = await session.get(Project, build.project_id) if build is not None else None
        if (
            build is None
            or project is None
            or build.landing != LANDING_PULL_REQUEST
            or not project.pr_ci_full_check
            or not build.pr_pushed_sha
            or build.pr_state in (MERGED, CLOSED)
        ):
            return None
        state = (build.pr_ci or {}).get("state")
        if state in _CI_CONCLUDED:
            return state
        try:
            root = (await project_workspace.resolve_project_workspace(session, project.id)).root
        except Exception:  # noqa: BLE001 -- nowhere to ask from; the next ask tries again
            return state
        sha = build.pr_pushed_sha
        main_branch = project.main_branch or "main"
        listed = list(project.pr_ci_check_names or [])
        await session.commit()
    read = await blocking.run(read_ci, root, main_branch, sha, listed)
    return await _apply_ci(build_id, read)


async def _apply_ci(build_id: str, read: Dict[str, Any]) -> Optional[str]:
    """Record *read* (`read_ci`) on the build and its pushed tasks, and act on it. A read of a
    commit a later push replaced only marks that push's result superseded (FR-4). A failure on the
    head that does not also fail on main sends back the latest task pushed, naming each failing
    check, its link and what main said (FR-7, FR-11); a pass, or a failure main shares, rewrites
    the PR, which stays a draft unless every task is pushed and CI passed."""
    from . import landing_queue
    from .db.engine import async_session_factory
    from .db.models import Build, Project, Task
    from .task_transitions import SEND_BACK_DEFECT

    send_back: Optional[Tuple[str, str, str]] = None
    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        project = await session.get(Project, build.project_id) if build is not None else None
        if build is None or project is None:
            return None
        now = _now().isoformat()
        sha = read.get("head_sha")
        landings = await _build_landings(session, build_id)
        own = [landing for landing in landings if landing.landed_sha == sha]
        previous = (build.pr_ci or {}).get("state")
        if sha != build.pr_pushed_sha:
            for landing in own:
                landing.ci = {**read, "state": CI_SUPERSEDED, "last_asked_at": now}
            await session.commit()
            return CI_SUPERSEDED
        build.pr_last_asked_at = _now()
        if read.get("state") is None:
            build.pr_ci = {**(build.pr_ci or {}), "last_asked_at": now, "error": read.get("error")}
            project_id = build.project_id
            await session.commit()
            await _broadcast_build(project_id, build_id, build.state)
            return previous
        state = read["state"]
        if state == CHECK_PENDING and previous == CI_NOT_FINISHED:
            state = CI_NOT_FINISHED  # past the cutoff: still not finished, asked on actions only
        view = {**read, "state": state, "last_asked_at": now, "error": None}
        build.pr_ci = view
        for landing in own:
            landing.ci = dict(view)
        if state == CHECK_PASSED:
            # Every task pushed in that head reads as checked by CI, naming the commit (FR-6).
            for landing in landings:
                if landing.state == PUSHED and (landing.ci or {}).get("state") != CHECK_PASSED:
                    landing.ci = dict(view)
        if state == CHECK_FAILED:
            head = next((landing for landing in own if landing.state == PUSHED), None)
            task = await session.get(Task, head.task_id) if head is not None else None
            if head is not None and task is not None:
                report = ci_report(task.display_id, read, project.main_branch or "main")
                send_back = (head.id, head.batch_id or "", report)
        project_id, build_state = build.project_id, build.state
        await session.commit()
    if send_back is not None:
        landing_id, batch_id, report = send_back
        await landing_queue._send_back(
            landing_id,
            batch_id,
            report,
            SEND_BACK_DEFECT,
            "CI failed on the build's pull request at the commit its push made.",
        )
    elif state != previous and state in _CI_CONCLUDED:
        landing_queue._start(
            project_id,
            _refresh_locked(project_id, build_id),
            f"rewrite the pull request of {build_id} after CI",
        )
    await _broadcast_build(project_id, build_id, build_state)
    return state


async def _ci_plan(build_id: str) -> Optional[Tuple[float, datetime, datetime]]:
    """`(interval seconds, cutoff time, push time)` while CI on the build's PR head is pending and
    the PR is open in a project with the setting on; None when there is nothing to ask for."""
    from .builds import LANDING_PULL_REQUEST
    from .db.engine import async_session_factory
    from .db.models import Build, Project

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        project = await session.get(Project, build.project_id) if build is not None else None
        pushed_at = _aware(build.pr_ci_pushed_at) if build is not None else None
        if (
            build is None
            or project is None
            or build.landing != LANDING_PULL_REQUEST
            or not project.pr_ci_full_check
            or build.pr_state in (MERGED, CLOSED)
            or (build.pr_ci or {}).get("state") != CHECK_PENDING
            or pushed_at is None
        ):
            return None
        interval = 60.0 * max(1, int(project.pr_ci_interval_minutes or 2))
        cutoff = timedelta(minutes=max(1, int(project.pr_ci_cutoff_minutes or 60)))
        return interval, pushed_at + cutoff, pushed_at


async def _not_finished(build_id: str, pushed_at: datetime) -> None:
    """The cutoff passed since the push at *pushed_at* with a counted check still unconcluded: the
    build shows CI has not finished, and only slice 1's actions ask again (FR-5)."""
    from .db.engine import async_session_factory
    from .db.models import Build

    async with async_session_factory() as session:
        build = await session.get(Build, build_id)
        if build is None or _aware(build.pr_ci_pushed_at) != pushed_at:
            return
        ci = build.pr_ci or {}
        if ci.get("state") != CHECK_PENDING:
            return
        build.pr_ci = {**ci, "state": CI_NOT_FINISHED}
        for landing in await _build_landings(session, build_id):
            if landing.landed_sha == ci.get("head_sha"):
                landing.ci = {**(landing.ci or {}), "state": CI_NOT_FINISHED}
        project_id, build_state = build.project_id, build.state
        await session.commit()
    await _broadcast_build(project_id, build_id, build_state)


def watch_ci(project_id: str, build_id: str) -> None:
    """Ask GitHub about the build's PR at the project's interval while CI on its head is pending
    (FR-5), in the background. Never waits and never raises; one watch per build, which a later
    push joins rather than starting a second."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = (id(loop), build_id)
    running = _watching.get(key)
    if running is not None and not running.done():
        _rewatch.add(key)
        return
    try:
        job = loop.create_task(_watch_logged(project_id, build_id, key))
    except Exception:  # noqa: BLE001
        logger.warning("could not watch CI of %s", build_id, exc_info=True)
        return
    _watching[key] = job

    def _done(finished: "asyncio.Task[Any]") -> None:
        if _watching.get(key) is finished:
            del _watching[key]

    job.add_done_callback(_done)


async def _watch_logged(project_id: str, build_id: str, key: Tuple[int, str]) -> None:
    try:
        await _watch(project_id, build_id, key)
    except Exception:  # noqa: BLE001 -- the next push or action asks again
        logger.warning("watching CI of %s failed", build_id, exc_info=True)


async def _watch(project_id: str, build_id: str, key: Tuple[int, str]) -> None:
    """Each interval, ask GitHub as slice 1's actions do (`ask`, which reads CI while it is
    pending); stop once CI on the head concluded, the PR is merged or closed, or the cutoff passed
    since the push (then the build shows CI has not finished)."""
    while True:
        plan = await _ci_plan(build_id)
        if plan is None:
            if key in _rewatch:  # a push while this was deciding to stop
                _rewatch.discard(key)
                continue
            return
        _rewatch.discard(key)
        interval, deadline, pushed_at = plan
        await _sleep(max(0.0, min(interval, (deadline - _now()).total_seconds())))
        if await _ci_plan(build_id) is None:
            continue
        found = await ask(project_id, build_id)
        if not any(answer["build_id"] == build_id for answer in found):
            await check_ci(build_id)  # no PR open to ask about: CI on the pushed head still counts
        if _now() >= deadline:
            await _not_finished(build_id, pushed_at)


async def settle_ci() -> None:
    """Wait for the CI watches running (tests)."""
    pending = [job for job in _watching.values() if not job.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
