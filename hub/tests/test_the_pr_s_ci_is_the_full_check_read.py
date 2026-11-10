"""The PR's CI is the full check (`the-pr-s-ci-is-the-full-check`), task `read-ci`.

FR-3 (counted-checks, ac-counted): only the counted checks decide CI's result. FR-4 (head-only,
ac-head): a result on a commit a later push replaced decides nothing and shows superseded. FR-5
(ask-while-pending, ac-pending): while the head's counted checks are pending the Hub asks at the
project's interval, stops once they concluded, and at the cutoff shows CI has not finished. FR-11
(fails-on-main-too, ac-main-too, ac-main-none): a failing check is compared with main's latest
commit; failing there too sends nothing back, no result there sends the latest task pushed back
saying so.

Real git against a local bare repository standing in for GitHub's remote, as slice 1's push tests
do; the GitHub CLI is a fake (`pull_requests._run_gh`) that also answers the `gh api` reads of a
branch, its rules and one commit's check runs and status. The clock of the interval asks is the
test's (`pull_requests._now`, `pull_requests._sleep`).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hub import landing_queue, pull_requests
from hub.db.engine import async_session_factory
from hub.db.models import Build, Task

from .test_a_build_has_a_driver_a_level_and_its_people import (
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_build_lands_as_one_pull_request_push import (
    FakeGitHub,
    _approve,
    _build_row,
    _latest,
    _pr_build,
    _status,
    _work,
)

CHECK = "ci-check"
LINK = "https://github.com/example/example/actions/runs/7/job/1"


def _run(name, conclusion=None, *, run_id=1, url=LINK):
    """A check run as GitHub's check-runs read answers it; no *conclusion* is still running."""
    return {
        "id": run_id,
        "name": name,
        "status": "completed" if conclusion else "in_progress",
        "conclusion": conclusion,
        "html_url": url,
    }


class CIGitHub(FakeGitHub):
    """Slice 1's fake PR side, plus `gh api` reads: required checks on main (`required`), and each
    commit's check runs (`runs[ref]`, a list or a callable answering one) and statuses."""

    def __init__(self) -> None:
        super().__init__()
        self.required: list = []
        self.runs: dict = {}
        self.statuses: dict = {}

    def __call__(self, root: Path, args: list) -> subprocess.CompletedProcess:
        if args[:1] != ["api"]:
            return super().__call__(root, args)
        self.calls.append(list(args))
        path = args[1]
        if path.endswith("/rules/branches/main"):
            return self._json([])
        if path.endswith("/branches/main"):
            checks = {"contexts": list(self.required), "checks": []}
            return self._json({"protection": {"enabled": True, "required_status_checks": checks}})
        ref, kind = path.split("/commits/", 1)[1].split("?", 1)[0].split("/", 1)
        if kind == "check-runs":
            runs = self.runs.get(ref, [])
            return self._json({"check_runs": runs() if callable(runs) else list(runs)})
        return self._json({"statuses": list(self.statuses.get(ref, []))})

    @staticmethod
    def _json(answer) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess([], 0, json.dumps(answer), "")

    def run_reads(self, ref):
        return [c for c in self.calls if c[:1] == ["api"] and f"/commits/{ref}/check-runs" in c[1]]


class Clock:
    """The interval asks' clock: `_sleep` moves it on at once."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


async def _never(seconds: float) -> None:
    await asyncio.Event().wait()


async def _ci_build(app, auth_headers, run_headers, bind_project_workspace, tmp_path, mp):
    """A started PR build of two tasks in a project with the CI setting on, counting `ci-check`
    by the project's list, against a GitHub answering through `CIGitHub`."""
    repo, bare, _, build_id = await _pr_build(
        app,
        auth_headers,
        run_headers,
        bind_project_workspace,
        tmp_path,
        mp,
        pr_ci_full_check=True,
        pr_ci_check_names=[CHECK],
        pr_ci_interval_minutes=2,
        pr_ci_cutoff_minutes=30,
    )
    github = CIGitHub()
    mp.setattr(pull_requests, "_run_gh", github)
    mp.setattr(pull_requests, "github_repo", lambda root: "example/example")
    tasks = await _tasks_by_key()
    return repo, github, build_id, tasks


async def _settle(*, watches=True):
    """Wait for the CI watches (unless they wait forever, `_never`) and the queue's jobs."""
    for _ in range(5):
        if watches:
            await pull_requests.settle_ci()
        jobs = [job for jobs in landing_queue._jobs.values() for job in jobs if not job.done()]
        if not jobs:
            return
        await asyncio.gather(*jobs, return_exceptions=True)


async def _stop_watches():
    for job in list(pull_requests._watching.values()):
        job.cancel()
    await asyncio.gather(*pull_requests._watching.values(), return_exceptions=True)


async def _push(repo, task, name, n):
    await _work(repo, task, f"{name}.txt", f"{name}\n", n=n)
    await _approve(task)
    landing = await _latest(task.id)
    assert landing.state == pull_requests.PUSHED, landing.reason
    return landing.landed_sha


# --- ac-counted (FR-3) ---------------------------------------------------------------------------


def _reading(monkeypatch, required, runs):
    github = CIGitHub()
    github.required, github.runs = required, {"abc": runs}
    monkeypatch.setattr(pull_requests, "_run_gh", github)
    monkeypatch.setattr(pull_requests, "github_repo", lambda root: "example/example")
    return github


def test_a_failing_check_that_does_not_count_leaves_the_result_passed(monkeypatch):
    _reading(monkeypatch, [CHECK], [_run(CHECK, "success"), _run("lint", "failure", run_id=2)])
    read = pull_requests.read_ci(Path("."), "main", "abc", [])
    assert read["state"] == pull_requests.CHECK_PASSED
    assert read["checks"] == [{"name": CHECK, "state": "passed", "url": LINK}]


def test_with_no_required_checks_the_listed_names_decide(monkeypatch):
    runs = [_run(CHECK, "success"), _run("lint", "failure", run_id=2)]
    _reading(monkeypatch, [], runs)
    assert pull_requests.read_ci(Path("."), "main", "abc", [CHECK])["state"] == "passed"
    read = pull_requests.read_ci(Path("."), "main", "abc", ["lint"])
    assert read["state"] == pull_requests.CHECK_FAILED
    assert [c["name"] for c in read["checks"]] == ["lint"]


def test_a_rerun_check_is_read_at_its_latest_run_and_a_status_counts_too(monkeypatch):
    github = _reading(
        monkeypatch, [CHECK, "legacy"], [_run(CHECK, "failure"), _run(CHECK, "success", run_id=9)]
    )
    github.statuses = {"abc": [{"context": "legacy", "state": "pending", "target_url": "u"}]}
    assert pull_requests.read_ci(Path("."), "main", "abc", [])["state"] == "pending"
    github.statuses = {"abc": [{"context": "legacy", "state": "success", "target_url": "u"}]}
    assert pull_requests.read_ci(Path("."), "main", "abc", [])["state"] == "passed"


def test_every_page_of_check_runs_is_read(monkeypatch):
    """F1146: one `per_page=100` read left a counted check past the first 100 runs pending until
    the cutoff. Every page is read, each an allowed GET, until the `total_count` is reached."""
    runs = [_run(f"job-{n}", "success", run_id=n + 10) for n in range(150)] + [
        _run(CHECK, "failure", run_id=5)
    ]
    calls = []

    def answer(root, args):
        pull_requests.check_gh_call(args)
        calls.append(args[1])
        path = args[1]
        if "/branches/" in path:
            return CIGitHub._json([] if "/rules/" in path else {"protection": {}})
        page = int(path.split("&page=")[1]) if "&page=" in path else 1
        if "/check-runs" in path:
            rows = runs[(page - 1) * 100 : page * 100]
            return CIGitHub._json({"total_count": len(runs), "check_runs": rows})
        return CIGitHub._json({"total_count": 0, "statuses": []})

    monkeypatch.setattr(pull_requests, "_run_gh", answer)
    monkeypatch.setattr(pull_requests, "github_repo", lambda root: "example/example")

    read = pull_requests.read_ci(Path("."), "main", "abc", [CHECK])

    assert [c["name"] for c in read["checks"]] == [CHECK]
    assert read["checks"][0]["state"] == pull_requests.CHECK_FAILED
    head_reads = [c for c in calls if "/commits/abc/check-runs" in c]
    assert head_reads == [
        "repos/example/example/commits/abc/check-runs?per_page=100",
        "repos/example/example/commits/abc/check-runs?per_page=100&page=2",
    ]


def test_with_neither_the_read_names_both_and_decides_nothing(monkeypatch):
    """The refusals of turning the setting on and starting a PR build are the `settings` task's
    tests (test_the_pr_s_ci_is_the_full_check_settings.py); a read with nothing counted, which a
    change on GitHub after the start can still produce, decides nothing and says why."""
    _reading(monkeypatch, [], [_run(CHECK, "failure")])
    read = pull_requests.read_ci(Path("."), "main", "abc", [])
    assert read["state"] is None
    assert "GitHub marks no status check required" in read["error"]
    assert pull_requests.CI_CHECK_NAMES in read["error"]


def test_the_commit_reads_are_allowed_and_nothing_else_is():
    pull_requests.check_gh_call(["api", "repos/o/r/commits/abc123/check-runs?per_page=100"])
    pull_requests.check_gh_call(["api", "repos/o/r/commits/main/status?per_page=100"])
    pull_requests.check_gh_call(["api", "repos/o/r/commits/abc/check-runs?per_page=100&page=2"])
    for refused in (
        ["api", "repos/o/r/commits/abc/check-runs"],
        ["api", "repos/o/r/commits/abc/check-runs?per_page=100", "-X", "POST"],
        ["api", "repos/o/r/check-runs/1/rerequest?per_page=100"],
        ["api", "repos/o/r/commits/abc/comments?per_page=100"],
        ["api", "repos/o/r/commits/abc/check-runs?per_page=100&page=0"],
        ["api", "repos/o/r/commits/abc/check-runs?per_page=100&page=2&filter=all"],
    ):
        with pytest.raises(pull_requests.RefusedGitHubCallError):
            pull_requests.check_gh_call(refused)


# --- ac-head (FR-4) ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failure_on_a_superseded_commit_sends_nothing_back(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        sha_a = await _push(repo, tasks["t1"], "a", 0)
        github.runs[sha_a] = [_run(CHECK)]  # A's run is still pending when B is pushed
        sha_b = await _push(repo, tasks["t2"], "b", 1)
        assert (await _latest(tasks["t1"].id)).ci["state"] == pull_requests.CI_SUPERSEDED

        github.runs[sha_a] = [_run(CHECK, "failure")]  # the failure reported on A's commit
        root = Path(repo)
        read_a = pull_requests.read_ci(root, "main", sha_a, [CHECK])
        assert read_a["state"] == pull_requests.CHECK_FAILED
        assert await pull_requests._apply_ci(build_id, read_a) == pull_requests.CI_SUPERSEDED
        await _settle(watches=False)

        assert await _status(tasks["t1"].id) == "approved"
        assert await _status(tasks["t2"].id) == "approved"
        assert (await _latest(tasks["t1"].id)).ci["state"] == pull_requests.CI_SUPERSEDED
        build = await _build_row(build_id)
        assert build.pr_ci["head_sha"] == sha_b
        assert build.pr_ci["state"] == pull_requests.CHECK_PENDING
    finally:
        await _stop_watches()


# --- ac-main-too, ac-main-none (FR-11) -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_check_failing_on_main_too_sends_nothing_back_and_the_pr_stays_a_draft(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        await _push(repo, tasks["t1"], "a", 0)
        head = await _push(repo, tasks["t2"], "b", 1)
        github.runs[head] = [_run(CHECK, "failure")]
        github.runs["main"] = [_run(CHECK, "failure", url="https://github.com/main-run")]

        assert await pull_requests.check_ci(build_id) == pull_requests.CI_FAILING_ON_MAIN
        await _settle(watches=False)

        assert await _status(tasks["t1"].id) == "approved"
        assert await _status(tasks["t2"].id) == "approved"
        build = await _build_row(build_id)
        assert build.pr_ci["state"] == pull_requests.CI_FAILING_ON_MAIN
        assert build.pr_ci["checks"] == [
            {"name": CHECK, "state": "failed", "url": LINK, "main_result": "failed"}
        ]
        # Every task is pushed, and slice 1 alone would have readied it: CI decides here.
        assert github.prs[1]["isDraft"] is True
        assert ["pr", "ready", "1"] not in github.calls
    finally:
        await _stop_watches()


@pytest.mark.asyncio
@pytest.mark.parametrize("on_main", ["pending", "absent"])
async def test_a_check_with_no_result_on_main_sends_the_latest_task_pushed_back(
    on_main,
    app,
    auth_headers,
    author_headers,  # noqa: F811
    bind_project_workspace,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        await _push(repo, tasks["t1"], "a", 0)
        head = await _push(repo, tasks["t2"], "b", 1)
        github.runs[head] = [_run(CHECK, "failure")]
        github.runs["main"] = [_run(CHECK)] if on_main == "pending" else [_run("other", "failure")]

        assert await pull_requests.check_ci(build_id) == pull_requests.CHECK_FAILED
        await _settle(watches=False)

        assert await _status(tasks["t1"].id) == "approved"
        assert await _status(tasks["t2"].id) == "revision_needed"
        async with async_session_factory() as db:
            notes = (await db.get(Task, tasks["t2"].id)).notes
        assert f"`{CHECK}` failed: {LINK}" in notes
        assert "main had no result for it" in notes
        landing = await _latest(tasks["t2"].id)
        assert landing.state == landing_queue.SENT_BACK
        build = await _build_row(build_id)
        assert build.pr_ci["checks"][0]["main_result"] == pull_requests.ON_MAIN_NONE
        assert github.prs[1]["isDraft"] is True
    finally:
        await _stop_watches()


@pytest.mark.asyncio
async def test_a_rerun_that_fails_after_a_pass_on_the_same_head_is_seen(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    """F1146: once CI had passed on a head nothing read it again, so a check re-run on the same
    head that then failed was never seen. A passed head is read again on each ask while its PR is
    open; the failure then sends back the latest task pushed, and is not read again after."""
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        await _push(repo, tasks["t1"], "a", 0)
        head = await _push(repo, tasks["t2"], "b", 1)
        github.runs[head] = [_run(CHECK, "success", run_id=1)]
        assert await pull_requests.check_ci(build_id) == pull_requests.CHECK_PASSED
        await _settle(watches=False)

        github.runs[head] = [_run(CHECK, "success", run_id=1), _run(CHECK, "failure", run_id=2)]
        github.runs["main"] = [_run(CHECK, "success")]
        assert await pull_requests.check_ci(build_id) == pull_requests.CHECK_FAILED
        await _settle(watches=False)

        assert await _status(tasks["t2"].id) == "revision_needed"
        assert await _status(tasks["t1"].id) == "approved"
        reads = len(github.run_reads(head))
        assert await pull_requests.check_ci(build_id) == pull_requests.CHECK_FAILED
        assert len(github.run_reads(head)) == reads
    finally:
        await _stop_watches()


# --- ac-pending (FR-5) ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pending_check_is_asked_for_each_interval_until_it_concludes_then_never(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    clock = Clock()
    monkeypatch.setattr(pull_requests, "_now", clock)
    monkeypatch.setattr(pull_requests, "_sleep", clock.sleep)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    concluded_at = clock.now + timedelta(minutes=5)
    github.runs["*"] = lambda: [_run(CHECK, "success" if clock.now >= concluded_at else None)]
    original = github.__class__.__call__

    def answer(self, root, args):
        if args[:1] == ["api"] and "/check-runs" in args[1] and "/commits/main/" not in args[1]:
            self.calls.append(list(args))
            return self._json({"check_runs": self.runs["*"]()})
        return original(self, root, args)

    monkeypatch.setattr(CIGitHub, "__call__", answer)
    head = await _push(repo, tasks["t1"], "a", 0)
    await _settle()

    build = await _build_row(build_id)
    assert build.pr_ci["state"] == pull_requests.CHECK_PASSED
    assert build.pr_ci["head_sha"] == head
    shown = datetime.fromisoformat(build.pr_ci["last_asked_at"])
    assert concluded_at <= shown <= concluded_at + timedelta(minutes=2)  # within one interval
    asks = len(github.run_reads(head))
    assert asks == 3  # at 2, 4 and 6 minutes after the push
    assert (await _latest(tasks["t1"].id)).ci["state"] == pull_requests.CHECK_PASSED

    # Nobody acts: the watch has ended, so however long passes, nothing more is asked.
    assert not [job for job in pull_requests._watching.values() if not job.done()]
    clock.now += timedelta(hours=3)
    await asyncio.sleep(0)
    assert len(github.run_reads(head)) == asks


@pytest.mark.asyncio
async def test_a_check_that_never_concludes_is_asked_for_until_the_cutoff_then_not_finished(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    clock = Clock()
    monkeypatch.setattr(pull_requests, "_now", clock)
    monkeypatch.setattr(pull_requests, "_sleep", clock.sleep)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    pushed_at = clock.now
    await _work(repo, tasks["t1"], "a.txt", "a\n")
    original = github.__class__.__call__

    def answer(self, root, args):
        if args[:1] == ["api"] and "/check-runs" in args[1]:
            self.calls.append(list(args))
            self.asked_at = getattr(self, "asked_at", []) + [clock.now]
            return self._json({"check_runs": [_run(CHECK)]})
        return original(self, root, args)

    monkeypatch.setattr(CIGitHub, "__call__", answer)
    await _approve(tasks["t1"])
    await _settle()

    build = await _build_row(build_id)
    assert build.pr_ci["state"] == pull_requests.CI_NOT_FINISHED
    assert (await _latest(tasks["t1"].id)).ci["state"] == pull_requests.CI_NOT_FINISHED
    assert len(github.asked_at) == 15  # every 2 minutes up to the 30-minute cutoff
    assert max(github.asked_at) == pushed_at + timedelta(minutes=30)
    assert not [job for job in pull_requests._watching.values() if not job.done()]

    # After the cutoff only slice 1's actions ask: an action reads CI again, still not finished.
    await pull_requests.ask("proj-test", build_id)
    assert len(github.asked_at) == 16
    assert (await _build_row(build_id)).pr_ci["state"] == pull_requests.CI_NOT_FINISHED


@pytest.mark.asyncio
async def test_the_build_and_task_reads_carry_ci(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        head = await _push(repo, tasks["t1"], "a", 0)
        checks = (
            await app.get(
                f"/api/v1/projects/proj-test/tasks/{tasks['t1'].id}/checks", headers=auth_headers
            )
        ).json()
        assert checks["landing"]["ci"]["state"] == "pending"
        assert checks["landing"]["ci"]["head_sha"] == head
        async with async_session_factory() as db:
            view = pull_requests_view(await db.get(Build, build_id))
        assert view["ci"]["state"] == "pending" and view["ci"]["head_sha"] == head
    finally:
        await _stop_watches()


def pull_requests_view(build):
    from hub.builds import pull_request_view

    return pull_request_view(build)


# --- migration 0170 ------------------------------------------------------------------------------


def test_0170_adds_nullable_ci_columns_and_round_trips(tmp_path):
    from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    from .test_migration_0151_the_hub_may_override_checks import _columns

    db_file = tmp_path / "pr-ci-read.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0170')")
        conn.commit()
    _downgrade_to(db_url, "0169")
    with sqlite3.connect(db_file) as conn:
        assert not {"pr_ci", "pr_ci_pushed_at"} & _columns(conn, "builds")
        assert "ci" not in _columns(conn, "task_landings")

    _upgrade_to(db_url, "0170")

    with sqlite3.connect(db_file) as conn:
        assert {"pr_ci", "pr_ci_pushed_at"} <= _columns(conn, "builds")
        assert "ci" in _columns(conn, "task_landings")
