"""A build lands as one pull request (`a-build-lands-as-one-pull-request`), task `push`.

Approved tasks of a build landing as a pull request are pushed to the build branch instead of
merged into main. Real git throughout, against a local bare repository standing in for GitHub's
remote; only the GitHub CLI is answered by a fake (`pull_requests._run_gh`), which records every
call the Hub made through `pull_requests.gh`.

FR-3 checked-before-push (chk-ac1), FR-4 draft-at-first (draft-ac1), FR-5 ready-and-back
(ready-ac1), FR-6 description (desc-ac1), FR-7 squash-setting (sq-ac1, sq-ac2), FR-8 main-moved
(main-ac1), FR-12 never-merges (nm-ac1). Named by criterion: `-k draft`, `-k check_fails`,
`-k single`, `-k main_moved`, `-k never`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import landing_queue, pull_requests, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import (
    Build,
    EvidenceFootprint,
    Project,
    RequirementEvidence,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_a_build_has_a_driver_a_level_and_its_people import (
    PATH,
    _approved,
    _build,
    _document,
    _move,
    _read,
    _roster_rows,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_build_lands_as_one_pull_request import GITHUB_URL, _only_git_on_path
from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

PY = f'"{sys.executable}"'


class FakeGitHub:
    """GitHub's side of `gh pr ...`: one PR per `create`, its draft state, title and body."""

    def __init__(self) -> None:
        self.calls: list = []
        self.prs: dict = {}

    def __call__(self, root: Path, args: list) -> subprocess.CompletedProcess:
        self.calls.append(list(args))

        def value(flag):
            return args[args.index(flag) + 1] if flag in args else None

        def body():
            path = value("--body-file")
            return Path(path).read_text(encoding="utf-8") if path else None

        if args[:2] == ["pr", "create"]:
            number = len(self.prs) + 1
            self.prs[number] = {
                "isDraft": "--draft" in args,
                "baseRefName": value("--base"),
                "headRefName": value("--head"),
                "title": value("--title"),
                "body": body(),
            }
            url = f"https://github.com/example/example/pull/{number}"
            return subprocess.CompletedProcess(args, 0, url + "\n", "")
        pr = self.prs[int(args[2])]
        if args[:2] == ["pr", "edit"]:
            pr["title"], pr["body"] = value("--title"), body()
        elif args[:2] == ["pr", "ready"]:
            pr["isDraft"] = "--undo" in args
        return subprocess.CompletedProcess(args, 0, "", "")


async def _set(**fields):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        for name, value in fields.items():
            setattr(project, name, value)
        await session.commit()


async def _pr_build(
    app,
    auth_headers,
    run_headers,
    bind_project_workspace,
    tmp_path,
    monkeypatch,
    **project,
):
    """A started PR build of two tasks (t1 serves FR-1, t2 FR-2) on a repository whose GitHub
    remote is a local bare repository holding main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", GITHUB_URL)
    await set_main_branch("main")
    await bind_project_workspace(repo)
    path = os.environ["PATH"]
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=0)
    await _set(pr_landing=True, **project)
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, run_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="reviewed", landing="pull_request")
    assert built.status_code == 200, built.text
    # From here GitHub is the bare repository, and its CLI the fake (a fetch from a local
    # repository crashes git on a PATH of git's directory alone).
    monkeypatch.setenv("PATH", path)
    git(repo, "remote", "set-url", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    monkeypatch.setattr(pull_requests, "github_remote", lambda root: "origin")
    fake = FakeGitHub()
    monkeypatch.setattr(pull_requests, "_run_gh", fake)
    (build,) = await _rows(Build)
    return repo, bare, fake, build.id


async def _evidence(task_id, commit, n=0):
    async with async_session_factory() as db:
        (link,) = (
            (
                await db.execute(
                    select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        requirement = await db.get(SpecRequirement, link.requirement_id)
        db.add(
            RequirementEvidence(
                id=f"ev-pr-{task_id}-{n}",
                project_id="proj-test",
                requirement_id=requirement.id,
                task_id=task_id,
                digest=requirement.digest,
                kind="artifact_diff",
                actor_kind="agent",
                actor="dev",
                summary="built",
                review_state="awaiting",
            )
        )
        db.add(
            EvidenceFootprint(
                id=f"fp-pr-{task_id}-{n}",
                project_id="proj-test",
                evidence_id=f"ev-pr-{task_id}-{n}",
                kind="git",
                commit_sha=commit,
                branch=worktrees.task_branch_name(task_id),
            )
        )
        await db.commit()


async def _work(repo, task, filename, content, *, n=0, create=True):
    """The builder's commit on the task branch and its evidence, from main."""
    git(repo, "checkout", "-q", "main")
    tip = commit_on_branch(
        repo, worktrees.task_branch_name(task.id), filename, content, create=create
    )
    git(repo, "checkout", "-q", "main")
    await _evidence(task.id, tip, n)
    return tip


async def _approve(task, *, again=False):
    run = f"run-{task.spec_task_key}-{'again' if again else 'first'}"
    if not again:
        await _move(task.id, "in_progress", "dev", run_id=f"{run}-dev")
    await _move(task.id, "completed", "dev", run_id=f"{run}-dev")
    await _move(task.id, "under_review", "qa", run_id=f"{run}-qa")
    await _move(task.id, "approved", "qa", run_id=f"{run}-qa")
    await landing_queue.drain("proj-test")


async def _send_back(task):
    async with async_session_factory() as db:
        row = await db.get(Task, task.id)
        await apply_transition(
            db, row, "revision_needed", operator(), reason_class="defect", reason="drive"
        )
        await db.commit()
    await landing_queue.drain("proj-test")


async def _status(task_id):
    async with async_session_factory() as db:
        return (await db.get(Task, task_id)).status


async def _latest(task_id):
    async with async_session_factory() as db:
        return await landing_queue.latest_landing(db, task_id)


async def _build_row(build_id):
    async with async_session_factory() as db:
        return await db.get(Build, build_id)


def _remote(bare, ref):
    found = git(bare, "rev-parse", "--verify", "--quiet", ref)
    return found.stdout.strip() if found.returncode == 0 else None


def _passing_check(tmp_path):
    """A check that records the tree it ran on, and passes."""
    ledger = tmp_path / "ran.txt"
    script = tmp_path / "check.py"
    script.write_text(
        "import subprocess\n"
        "tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], capture_output=True,"
        " text=True).stdout.strip()\n"
        f"open(r'{ledger}', 'a', encoding='utf-8').write(tree + '\\n')\n",
        encoding="utf-8",
    )
    command = f'{PY} "{script}"'
    return {"name": "count", "command": command, "timeout_seconds": 120, "phase": "landing"}, ledger


# --- draft-ac1, ready-ac1, desc-ac1, nm-ac1, chk (pass) -----------------------------------------


@pytest.mark.asyncio
async def test_draft_pr_at_the_first_task_then_ready_draft_ready(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    check, ledger = _passing_check(tmp_path)
    repo, bare, fake, build_id = await _pr_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        checks=[check],
    )
    tasks = await _tasks_by_key()
    t1, t2 = tasks["t1"], tasks["t2"]
    main_before = git(repo, "rev-parse", "main").stdout.strip()
    branch = pull_requests.build_branch_name(build_id)

    one = await _work(repo, t1, "alpha.py", "a = 1\n")
    await _approve(t1)

    # draft-ac1: pushed after its checks passed, a draft PR against main from the build branch.
    pushed = _remote(bare, f"refs/heads/{branch}")
    assert pushed is not None, (await _build_row(build_id)).pr_error
    assert git(repo, "merge-base", "--is-ancestor", one, pushed).returncode == 0
    ran = ledger.read_text(encoding="utf-8").split()
    assert ran and ran[-1] == git(repo, "rev-parse", f"{pushed}^{{tree}}").stdout.strip()
    assert (await _latest(t1.id)).state == pull_requests.PUSHED
    assert list(fake.prs) == [1]
    pr = fake.prs[1]
    assert pr["isDraft"] and pr["baseRefName"] == "main" and pr["headRefName"] == branch
    build = await _build_row(build_id)
    assert (build.pr_number, build.pr_state, build.pr_pushed_sha) == (1, "draft", pushed)
    assert build.pr_url.endswith("/pull/1") and build.pr_last_asked_at is not None
    # Never merged into main by the Hub.
    assert git(repo, "rev-parse", "main").stdout.strip() == main_before
    assert _remote(bare, "refs/heads/main") == main_before

    two = await _work(repo, t2, "beta.py", "b = 2\n")
    await _approve(t2)

    after = _remote(bare, f"refs/heads/{branch}")
    assert git(bare, "merge-base", "--is-ancestor", pushed, after).returncode == 0
    assert git(repo, "merge-base", "--is-ancestor", two, after).returncode == 0
    assert list(fake.prs) == [1], "the build keeps one PR"
    # ready-ac1: ready once both are pushed ...
    assert fake.prs[1]["isDraft"] is False
    assert (await _build_row(build_id)).pr_state == "ready"

    # desc-ac1: the spec's title; the spec path, every requirement, the accepted evidence, each
    # task with its state.
    (read,) = (await _read(app, auth_headers))["builds"][:1]
    assert read["pull_request"]["state"] == "ready"
    body = fake.prs[1]["body"]
    assert fake.prs[1]["title"] == "A build of its own"
    assert PATH in body
    for identifier, statement in (("FR-1", "It does alpha"), ("FR-2", "It does beta")):
        assert f"**{identifier}** {statement}" in body
    accepted = [
        row.id
        for row in await _rows(RequirementEvidence, RequirementEvidence.review_state == "accepted")
    ]
    assert sorted(accepted) == sorted([f"ev-pr-{t1.id}-0", f"ev-pr-{t2.id}-0"])
    assert all(f"`{evidence}`" in body for evidence in accepted)
    for key in ("t1", "t2"):
        (line,) = [ln for ln in body.splitlines() if ln.startswith(f"- `{key}`")]
        assert line.endswith("approved, pushed"), line

    # ... back to draft when the second is sent back ...
    await _send_back(t2)
    assert fake.prs[1]["isDraft"] is True
    assert (await _build_row(build_id)).pr_state == "draft"
    assert any(
        ln.startswith("- `t2`") and ln.endswith("revision_needed")
        for ln in fake.prs[1]["body"].splitlines()
    )

    # ... and ready again once it is approved and pushed again.
    again = await _work(repo, t2, "beta.py", "b = 3\n", n=1, create=False)
    await _move(t2.id, "in_progress", "dev", run_id="run-t2-again-dev")
    await _approve(t2, again=True)
    assert fake.prs[1]["isDraft"] is False
    final = _remote(bare, f"refs/heads/{branch}")
    assert git(repo, "merge-base", "--is-ancestor", again, final).returncode == 0

    # nm-ac1: every call the Hub made is one the module allows.
    assert fake.calls
    for call in fake.calls:
        pull_requests.check_gh_call(call)
        assert tuple(call[:2]) in {("pr", "create"), ("pr", "edit"), ("pr", "ready")}


# --- chk-ac1 -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_whose_check_fails_is_sent_back_and_nothing_is_pushed(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    failing = {
        "name": "fails",
        "command": f"{PY} -c \"import sys; print('FAILED tests/test_x.py::test_x'); sys.exit(1)\"",
        "timeout_seconds": 120,
        "phase": "landing",
    }
    repo, bare, fake, build_id = await _pr_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        checks=[failing],
    )
    t1 = (await _tasks_by_key())["t1"]
    await _work(repo, t1, "alpha.py", "a = 1\n")
    await _approve(t1)

    assert await _status(t1.id) == "revision_needed"
    assert (await _latest(t1.id)).state == landing_queue.SENT_BACK
    assert _remote(bare, f"refs/heads/{pull_requests.build_branch_name(build_id)}") is None
    assert fake.calls == [] and fake.prs == {}


# --- sq-ac2, sq-ac1 ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_commit_mode_holds_one_commit_above_main(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id = await _pr_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        pr_single_commit=True,
    )
    tasks = await _tasks_by_key()
    branch = f"refs/heads/{pull_requests.build_branch_name(build_id)}"
    await _work(repo, tasks["t1"], "alpha.py", "a = 1\n")
    await _approve(tasks["t1"])
    await _work(repo, tasks["t2"], "beta.py", "b = 2\n")
    await _approve(tasks["t2"])

    tip = _remote(bare, branch)
    above = git(bare, "rev-list", f"refs/heads/main..{tip}").stdout.split()
    assert above == [tip], f"{len(above)} commits above main"
    files = git(bare, "ls-tree", "--name-only", tip).stdout.split()
    assert {"alpha.py", "beta.py", "README.md"} <= set(files)
    assert git(bare, "rev-parse", f"{tip}^").stdout.strip() == _remote(bare, "refs/heads/main")
    assert fake.prs[1]["isDraft"] is False


@pytest.mark.asyncio
async def test_single_commit_push_is_refused_over_someone_elses_commit(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id = await _pr_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        pr_single_commit=True,
    )
    tasks = await _tasks_by_key()
    name = pull_requests.build_branch_name(build_id)
    await _work(repo, tasks["t1"], "alpha.py", "a = 1\n")
    await _approve(tasks["t1"])
    # Somebody else pushes to the build branch on GitHub.
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", name, str(bare), str(other))
    git(other, "config", "user.email", "o@example.com")
    git(other, "config", "user.name", "Other")
    (other / "theirs.py").write_text("t = 1\n", encoding="utf-8")
    git(other, "add", "theirs.py")
    git(other, "commit", "-q", "-m", "their work")
    git(other, "push", "-q", "origin", name)
    theirs = git(other, "rev-parse", "HEAD").stdout.strip()

    await _work(repo, tasks["t2"], "beta.py", "b = 2\n")
    await _approve(tasks["t2"])

    assert _remote(bare, f"refs/heads/{name}") == theirs, "their commit is still the branch"
    landing = await _latest(tasks["t2"].id)
    assert landing.state == landing_queue.NOT_LANDED
    assert "refused" in landing.reason
    shown = (await _read(app, auth_headers))["builds"][0]["pull_request"]["error"]
    assert shown and "refused the push" in shown


# --- main-ac1 ------------------------------------------------------------------------------------


def _push_to_main(tmp_path, bare, filename, content):
    other = tmp_path / f"main-{filename}"
    git(tmp_path, "clone", "-q", "-b", "main", str(bare), str(other))
    git(other, "config", "user.email", "o@example.com")
    git(other, "config", "user.name", "Other")
    (other / filename).write_text(content, encoding="utf-8")
    git(other, "add", filename)
    git(other, "commit", "-q", "-m", f"main gains {filename}")
    git(other, "push", "-q", "origin", "main")
    return git(other, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.asyncio
async def test_main_moved_with_a_conflict_sends_the_task_back_and_pushes_nothing(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id = await _pr_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    tasks = await _tasks_by_key()
    branch = f"refs/heads/{pull_requests.build_branch_name(build_id)}"
    await _work(repo, tasks["t1"], "alpha.py", "a = 1\n")
    await _approve(tasks["t1"])
    first = _remote(bare, branch)
    _push_to_main(tmp_path, bare, "beta.py", "b = 'main'\n")

    await _work(repo, tasks["t2"], "beta.py", "b = 'task'\n")
    await _approve(tasks["t2"])

    assert await _status(tasks["t2"].id) == "revision_needed"
    landing = await _latest(tasks["t2"].id)
    assert landing.state == landing_queue.SENT_BACK and "beta.py" in landing.reason
    async with async_session_factory() as db:
        from hub.db.models import TaskTransition

        (moved,) = (
            (
                await db.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id == tasks["t2"].id,
                        TaskTransition.to_status == "revision_needed",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert moved.reason_class == "merge-needed"
    assert _remote(bare, branch) == first, "the remote branch is unchanged"


@pytest.mark.asyncio
async def test_main_moved_without_a_conflict_is_merged_into_the_build_branch(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id = await _pr_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    tasks = await _tasks_by_key()
    branch = f"refs/heads/{pull_requests.build_branch_name(build_id)}"
    await _work(repo, tasks["t1"], "alpha.py", "a = 1\n")
    await _approve(tasks["t1"])
    first = _remote(bare, branch)
    moved = _push_to_main(tmp_path, bare, "gamma.py", "g = 1\n")

    two = await _work(repo, tasks["t2"], "beta.py", "b = 2\n")
    await _approve(tasks["t2"])

    tip = _remote(bare, branch)
    for contained in (first, moved, two):
        assert git(repo, "merge-base", "--is-ancestor", contained, tip).returncode == 0
    assert (await _latest(tasks["t2"].id)).state == pull_requests.PUSHED


# --- nm-ac1 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        ["pr", "merge", "1"],
        ["pr", "merge", "1", "--auto", "--squash"],
        ["pr", "review", "1", "--approve"],
        ["pr", "close", "1"],
        ["pr", "edit", "1", "--base", "develop"],
        ["pr", "edit", "1", "--base=develop"],
        ["pr", "edit", "1", "-B", "develop"],
        ["pr", "ready", "1", "--repo", "other/repo"],
        ["api", "repos/o/r/branches/main/protection", "-X", "PUT"],
        ["repo", "edit", "--default-branch", "x"],
        ["ruleset", "list"],
    ],
)
def test_the_module_never_issues_a_merge_approval_base_or_protection_change(call, monkeypatch):
    ran = []
    monkeypatch.setattr(pull_requests, "_run_gh", lambda root, args: ran.append(args))
    with pytest.raises(pull_requests.RefusedGitHubCallError):
        pull_requests.gh(Path("."), *call)
    assert ran == []


@pytest.mark.parametrize(
    "call",
    [
        ["pr", "create", "--draft", "--base", "main", "--head", "b", "--title", "t"],
        ["pr", "edit", "1", "--title", "t", "--body-file", "f"],
        ["pr", "ready", "1"],
        ["pr", "ready", "1", "--undo"],
        ["pr", "view", "1", "--json", "state"],
    ],
)
def test_the_module_issues_the_pr_calls_it_needs(call):
    pull_requests.check_gh_call(call)


def test_the_gh_wrapper_is_the_only_caller_of_the_cli_in_the_module():
    """Every `_run_gh` call in the module is inside `gh`, which checks it first."""
    source = Path(pull_requests.__file__).read_text(encoding="utf-8")
    assert source.count("_run_gh(") == 2  # its definition and `gh`'s one call
    assert "check_gh_call(args)\n    try:\n        return _run_gh(root, list(args))" in source
