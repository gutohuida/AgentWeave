"""The PR's CI is the full check (`the-pr-s-ci-is-the-full-check`), task `act-on-ci`.

FR-2 (no-local-landing-checks, ac-no-local): with the setting on a PR build's approved task is
pushed without the project's landing-phase checks running here; with it off they still run before
the push. FR-6 (ci-passed, ac-passed): a pass on the head reads on the build and every pushed task,
naming the commit. FR-7 (ci-failed, ac-failed): a failure main does not share returns a ready PR to
draft and sends back the task whose push made the head, naming the check and its link, the same
with the single-commit setting. FR-8 (ready-on-green, ac-ready): with every task pushed the PR stays
a draft while CI is pending and is readied when it passes.

The same harness as the `read-ci` tests: real git against a local bare remote, a fake GitHub CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from hub import pull_requests
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskCheckRun

from .test_a_build_has_a_driver_a_level_and_its_people import (
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_build_lands_as_one_pull_request_push import (
    _approve,
    _build_row,
    _latest,
    _passing_check,
    _pr_build,
    _remote,
    _status,
    _work,
    git,
)
from .test_the_pr_s_ci_is_the_full_check_read import (
    CHECK,
    LINK,
    CIGitHub,
    _never,
    _push,
    _run,
    _settle,
    _stop_watches,
)


async def _ci_build(app, auth_headers, run_headers, bind_project_workspace, tmp_path, mp, **extra):
    """`read-ci`'s CI build, with a landing-phase check configured and any other *extra* setting."""
    check, ledger = _passing_check(tmp_path)
    repo, _, _, build_id = await _pr_build(
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
        checks=[check],
        **extra,
    )
    github = CIGitHub()
    mp.setattr(pull_requests, "_run_gh", github)
    mp.setattr(pull_requests, "github_repo", lambda root: "example/example")
    return repo, github, build_id, await _tasks_by_key(), ledger


async def _check_runs(task_id):
    async with async_session_factory() as db:
        rows = await db.execute(select(TaskCheckRun).where(TaskCheckRun.task_id == task_id))
        return list(rows.scalars())


async def _read(repo, build_id, sha):
    """What GitHub says of *sha* now, applied as the watch would apply it."""
    read = pull_requests.read_ci(Path(repo), "main", sha, [CHECK])
    state = await pull_requests._apply_ci(build_id, read)
    await _settle(watches=False)
    return state


# --- ac-no-local (FR-2) --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("ci_on", [True, False])
async def test_with_the_setting_on_no_landing_check_runs_before_the_push(
    ci_on,
    app,
    auth_headers,
    author_headers,  # noqa: F811
    bind_project_workspace,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    check, ledger = _passing_check(tmp_path)
    repo, bare, _, build_id = await _pr_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        pr_ci_full_check=ci_on,
        pr_ci_check_names=[CHECK] if ci_on else [],
        checks=[check],
    )
    monkeypatch.setattr(pull_requests, "_run_gh", CIGitHub())
    monkeypatch.setattr(pull_requests, "github_repo", lambda root: "example/example")
    t1 = (await _tasks_by_key())["t1"]
    try:
        work = await _work(repo, t1, "alpha.py", "a = 1\n")
        await _approve(t1)

        pushed = _remote(bare, f"refs/heads/{pull_requests.build_branch_name(build_id)}")
        assert pushed is not None, (await _build_row(build_id)).pr_error
        assert (await _latest(t1.id)).state == pull_requests.PUSHED
        assert git(repo, "merge-base", "--is-ancestor", work, pushed).returncode == 0
        ran = ledger.read_text(encoding="utf-8").split() if ledger.exists() else []
        runs = await _check_runs(t1.id)
        if ci_on:
            assert ran == [] and runs == [], "no landing-phase check run with CI as the full check"
        else:
            # Slice 1 unchanged: the landing checks ran on the pushed tree before the push.
            assert ran[-1] == git(repo, "rev-parse", f"{pushed}^{{tree}}").stdout.strip()
            assert any(run.merged_sha for run in runs)
    finally:
        await _stop_watches()


# --- ac-passed (FR-6) ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_on_the_head_reads_as_checked_by_ci_on_the_build_and_its_pushed_tasks(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks, _ = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        first = await _push(repo, tasks["t1"], "a", 0)
        github.runs[first] = [_run(CHECK, "success")]
        assert await _read(repo, build_id, first) == pull_requests.CHECK_PASSED
        assert (await _latest(tasks["t1"].id)).ci["head_sha"] == first
        assert github.prs[1]["isDraft"] is True, "t2 is not pushed yet"

        head = await _push(repo, tasks["t2"], "b", 1)
        github.runs[head] = [_run(CHECK, "success")]
        assert await _read(repo, build_id, head) == pull_requests.CHECK_PASSED

        build = await _build_row(build_id)
        assert build.pr_ci["state"] == pull_requests.CHECK_PASSED
        assert build.pr_ci["head_sha"] == head
        for key in ("t1", "t2"):
            ci = (await _latest(tasks[key].id)).ci
            assert ci["state"] == pull_requests.CHECK_PASSED and ci["head_sha"] == head, key
        assert await _status(tasks["t1"].id) == await _status(tasks["t2"].id) == "approved"
    finally:
        await _stop_watches()


# --- ac-failed (FR-7) ----------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("single", [False, True])
async def test_a_failure_on_a_ready_pr_drafts_it_and_sends_back_the_task_whose_push_made_the_head(
    single,
    app,
    auth_headers,
    author_headers,  # noqa: F811
    bind_project_workspace,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks, _ = await _ci_build(
        app,
        auth_headers,
        author_headers,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        pr_single_commit=single,
    )
    try:
        await _push(repo, tasks["t1"], "a", 0)
        head = await _push(repo, tasks["t2"], "b", 1)  # task B's push makes the head
        github.runs["main"] = [_run(CHECK, "success", url="https://github.com/main-run")]
        github.runs[head] = [_run(CHECK, "success")]
        assert await _read(repo, build_id, head) == pull_requests.CHECK_PASSED
        assert github.prs[1]["isDraft"] is False, "every task pushed and CI passed: ready"

        # A re-run of the counted check on that same head fails; main is green.
        github.runs[head] = [_run(CHECK, "success"), _run(CHECK, "failure", run_id=2)]
        assert await _read(repo, build_id, head) == pull_requests.CHECK_FAILED

        assert github.prs[1]["isDraft"] is True
        assert await _status(tasks["t1"].id) == "approved"
        assert await _status(tasks["t2"].id) == "revision_needed"
        async with async_session_factory() as db:
            notes = (await db.get(Task, tasks["t2"].id)).notes
        assert f"`{CHECK}` failed: {LINK}" in notes
        assert (await _build_row(build_id)).pr_ci["checks"][0]["main_result"] == "passed"
    finally:
        await _stop_watches()


# --- ac-ready (FR-8) -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_every_task_pushed_the_pr_is_a_draft_while_pending_and_ready_once_passed(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pull_requests, "_sleep", _never)
    repo, github, build_id, tasks, _ = await _ci_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    try:
        await _push(repo, tasks["t1"], "a", 0)
        head = await _push(repo, tasks["t2"], "b", 1)
        github.runs[head] = [_run(CHECK)]
        assert await _read(repo, build_id, head) == pull_requests.CHECK_PENDING
        # Slice 1 alone would ready it now, with every task pushed: CI decides.
        assert github.prs[1]["isDraft"] is True
        assert ["pr", "ready", "1"] not in github.calls

        github.runs[head] = [_run(CHECK, "success")]
        assert await _read(repo, build_id, head) == pull_requests.CHECK_PASSED
        assert github.prs[1]["isDraft"] is False
        assert (await _build_row(build_id)).pr_state == pull_requests.READY
    finally:
        await _stop_watches()
