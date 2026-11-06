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
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
        await session.commit()
        await lq._announce(session, [landing_id])
    await refresh(build_id, opening=True)
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
