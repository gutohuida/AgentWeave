"""A check that cannot run says so and is never silently excused
(`a-check-that-cannot-run-says-so-and-is-never-silently-excused`, task t1-outcome).

From 2026-11-15 to 2026-11-16, at least 12 landing batches on the operator's Hub recorded `hub-ui`
as `'eslint' is not recognized as an internal or external command`, exit 1, excused by a
whole-check known-failing entry: UI work landed with no lint, type check or UI test. These are the
acceptance drive: each test fails on the code before this change (the result was an ordinary
failure, a whole-check entry excused it, a refused spawn ended the run `error`) and passes only once
'could not run' is its own outcome -- never excused, never blamed, never a pass.

Real check subprocesses (scripts written outside the checkout) and real git, as
`test_checks_run_before_review` and `test_a_failing_batch_is_narrowed` do; the landing tests stub
only `run_one` where they say so.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub import known_failing, landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import (
    KnownFailingTest,
    LandingBatch,
    MainCheckRun,
    Project,
    Task,
    TaskCheckRun,
    TaskLanding,
    TaskTransition,
)

from .test_a_failing_batch_is_narrowed import (
    _approve,
    _batches,
    _merged,
    _project,
    _repo,
    _status,
    _tasks,
)
from .test_project_checks_run import _task_with_work, listed_whole_check
from .test_task_integration import commits_on, make_repo, set_main_branch

PY = f'"{sys.executable}"'
#: What cmd prints when `npm run lint` starts an eslint that is not installed (2026-11-15).
CMD_NOT_RECOGNIZED = (
    "'eslint' is not recognized as an internal or external command,\n"
    "operable program or batch file."
)


def _scripts(tmp_path: Path) -> Path:
    """Beside the repository: never in a checked tree."""
    scripts = tmp_path.parent / f"{tmp_path.name}-scripts"
    scripts.mkdir(exist_ok=True)
    return scripts


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = _scripts(tmp_path) / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return f'{PY} "{path}"'


def _lint(tmp_path: Path, installed: Path, name: str = "hub-ui") -> Dict[str, Any]:
    """`npm run lint` in a checkout without `node_modules`: npm echoes the script, cmd cannot find
    eslint, and npm exits 1 -- until *installed* exists, when it lints and passes."""
    command = _script(
        tmp_path,
        f"lint-{name}",
        "import os, sys\n"
        "print('> eslint . --ext ts,tsx')\n"
        f"if not os.path.exists({str(installed)!r}):\n"
        f"    print({CMD_NOT_RECOGNIZED!r})\n"
        "    sys.exit(1)\n"
        "print('lint ok')\n",
    )
    return {"name": name, "command": command, "timeout_seconds": 60}


def _passing(tmp_path: Path, name: str = "hub-tests") -> Dict[str, Any]:
    return {
        "name": name,
        "command": _script(tmp_path, f"pass-{name}", "print('ok')\n"),
        "timeout_seconds": 60,
    }


async def _configure(checks: List[Dict[str, Any]]) -> None:
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).checks = checks
        await session.commit()


async def _runs(task_id: str) -> List[TaskCheckRun]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskCheckRun)
                    .where(TaskCheckRun.task_id == task_id)
                    .order_by(TaskCheckRun.started_at)
                )
            ).scalars()
        )


async def _moved_to(task_id: str, status: str) -> List[TaskTransition]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id == task_id, TaskTransition.to_status == status
                    )
                )
            ).scalars()
        )


# ---------------------------------------------------------------------------------------------
# FR-1, FR-2, FR-3: the outcome, from the check's own run
# ---------------------------------------------------------------------------------------------


def test_ac_eslint_missing_is_could_not_run_naming_eslint(tmp_path):
    result = project_checks.run_one(_lint(tmp_path, tmp_path / "never"), tmp_path)

    assert result["exit_code"] == 1, "npm's exit, not the shell's: only the output tells"
    assert result["outcome"] == project_checks.COULD_NOT_RUN
    assert result["missing_program"] == "eslint"
    assert project_checks.could_not_run(result) and not project_checks.counts_against(result)
    assert project_checks.failed(result), "never a pass"


def test_ac_shell_codes_a_program_that_does_not_exist_could_not_run(tmp_path):
    check = {"name": "lint", "command": "aw-no-such-program-xyz --check", "timeout_seconds": 60}

    result = project_checks.run_one(check, tmp_path)

    # cmd run through `/c` exits 1 here, not 9009 (measured 2026-11-17); its sentence names it.
    assert result["exit_code"] != 0, result
    assert result["outcome"] == project_checks.COULD_NOT_RUN
    assert result["missing_program"] == "aw-no-such-program-xyz"


@pytest.mark.parametrize("code", [9009, 127])
def test_the_shells_own_not_found_code_alone_is_could_not_run(code, monkeypatch):
    """FR-1: the shell's own code counts where its sentence was lost (a check that swallows it);
    each platform's own code only -- 127 is an ordinary exit on Windows, and 9009 on POSIX."""
    from hub import pty_runner

    monkeypatch.setattr(pty_runner, "IS_WINDOWS", code == 9009)
    check = {"name": "lint", "command": "eslint . --ext ts", "timeout_seconds": 60}
    result = {"name": "lint", "exit_code": code, "timed_out": False, "output_tail": ""}
    project_checks.classify_could_not_run(check, result)
    assert (
        result["outcome"] == project_checks.COULD_NOT_RUN and result["missing_program"] == "eslint"
    )

    other = {"name": "lint", "exit_code": 9009 + 127 - code, "timed_out": False, "output_tail": ""}
    project_checks.classify_could_not_run(check, other)
    assert "outcome" not in other


def test_ac_plain_not_found_is_a_failure(tmp_path):
    check = {
        "name": "lint",
        "command": _script(tmp_path, "nf", "import sys\nprint('file not found')\nsys.exit(1)\n"),
        "timeout_seconds": 60,
    }

    result = project_checks.run_one(check, tmp_path)

    assert result["exit_code"] == 1
    assert "outcome" not in result and project_checks.counts_against(result)


@pytest.mark.parametrize(
    "output, program",
    [
        (CMD_NOT_RECOGNIZED, "eslint"),
        ("bash: eslint: command not found", "eslint"),
        ("/bin/bash: line 1: vitest: command not found", "vitest"),
        ("sh: 1: eslint: not found", "eslint"),
        ("/bin/sh: tsc: not found", "tsc"),
        ("file not found", None),
        ("FileNotFoundError: report.xml not found", None),
        ("error: module 'x' not found", None),
    ],
)
def test_the_shells_not_found_sentences_name_the_program(output, program):
    assert project_checks.missing_program(output) == program


def test_ac_tests_and_not_found_a_named_failing_test_is_a_failure(tmp_path):
    report = (
        '<?xml version="1.0"?><testsuite tests="1" failures="1">'
        '<testcase classname="tests.x" name="t" file="tests/x.py">'
        '<failure message="assert 1 == 2">assert 1 == 2</failure></testcase></testsuite>'
    )
    check = {
        "name": "hub-tests",
        "command": _script(
            tmp_path,
            "named",
            "import sys\n"
            f"open('report.xml', 'w').write({report!r})\n"
            "print('bash: eslint: command not found')\n"
            "sys.exit(1)\n",
        ),
        "timeout_seconds": 60,
        "report_path": "report.xml",
    }

    result = project_checks.run_one(check, tmp_path)

    assert result.get("outcome") != project_checks.COULD_NOT_RUN
    assert result["failed_tests"] == ["tests.x::t"]
    assert project_checks.counts_against(result)


# ---------------------------------------------------------------------------------------------
# FR-4: a refused spawn ends that one check
# ---------------------------------------------------------------------------------------------


async def test_ac_spawn_refused_ends_only_that_check_and_the_route_names_it(
    app, auth_headers, tmp_path, monkeypatch
):
    task_id, _ = await _task_with_work(tmp_path)
    refused = _passing(tmp_path, "refused")
    await _configure([refused, _passing(tmp_path, "hub-tests")])
    real = subprocess.Popen

    def popen(*args, **kwargs):
        command = kwargs.get("args", args[0] if args else "")
        if "pass-refused" in str(command):
            raise OSError(1455, "The paging file is too small for this operation to complete")
        return real(*args, **kwargs)

    monkeypatch.setattr(project_checks.subprocess, "Popen", popen)

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state not in ("error", "passed"), (run.state, run.error)
    first, second = run.results
    assert first["outcome"] == project_checks.COULD_NOT_RUN
    assert "paging file is too small" in first["spawn_error"]
    assert second["name"] == "hub-tests" and second["exit_code"] == 0
    assert (await _status(task_id)) == "completed", "nobody's failure: not sent back"


async def test_ac_names_eslint_on_the_tasks_checks_route(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _configure([_lint(tmp_path, tmp_path / "never")])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    read = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}/checks", headers=auth_headers)
    assert read.status_code == 200, read.text
    [result] = read.json()["runs"][0]["results"]
    assert result["outcome"] == "could_not_run" and result["missing_program"] == "eslint"
    assert read.json()["runs"][0]["state"] != "passed"


# ---------------------------------------------------------------------------------------------
# FR-5: never excused, never listed
# ---------------------------------------------------------------------------------------------


def test_a_whole_check_entry_does_not_excuse_a_check_that_could_not_run():
    result = {
        "name": "hub-ui",
        "exit_code": 1,
        "timed_out": False,
        "outcome": project_checks.COULD_NOT_RUN,
        "missing_program": "eslint",
    }
    whole = {"check": "hub-ui", "test": "", "kind": "fails on main"}

    known_failing.judge_result(result, [whole])

    assert result["preexisting"] is False and not result.get("listed")
    assert not project_checks.preexisting(result)


async def test_ac_not_added_from_main(app, tmp_path):
    tip = make_repo(tmp_path)
    await set_main_branch("main")
    await _configure([_lint(tmp_path, tmp_path / "never")])

    run_id = await known_failing.run_on_main("proj-test", tip)

    async with async_session_factory() as session:
        run = await session.get(MainCheckRun, run_id)
        listed = (await session.execute(select(KnownFailingTest))).scalars().all()
    assert run.state == "failed" and run.results[0]["outcome"] == project_checks.COULD_NOT_RUN
    assert listed == [], "a check that never ran is not a failure on main"


# ---------------------------------------------------------------------------------------------
# FR-6, FR-11: a landing batch holding one does not land, blames nobody, and retries
# ---------------------------------------------------------------------------------------------


async def _two_approved(app, auth_headers, tmp_path, tmp_path_factory, checks):
    _repo(tmp_path, tmp_path_factory.mktemp("ledger") / "runs.txt")
    await _project()
    await _configure(checks)
    ids, tips = await _tasks(tmp_path, [({"one.py": "x = 1\n"}, None), ({"two.py": "y\n"}, None)])
    for task_id in ids:
        await _approve(app, auth_headers, task_id)
    return ids, tips


@pytest.fixture
def forbid_blame(monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("a check that could not run was narrowed or blamed on a task")

    monkeypatch.setattr(landing_queue, "_narrow", boom)
    monkeypatch.setattr(landing_queue, "_send_back", boom)


async def test_ac_no_send_back_and_ac_batch_retries(
    app, auth_headers, tmp_path, tmp_path_factory, forbid_blame, monkeypatch
):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    installed = _scripts(tmp_path) / "node_modules-installed"
    ids, tips = await _two_approved(
        app,
        auth_headers,
        tmp_path,
        tmp_path_factory,
        [_lint(tmp_path, installed), _passing(tmp_path)],
    )
    await listed_whole_check("hub-ui")  # ac-whole-entry-does-not-excuse, in a landing batch

    try:
        await landing_queue.drain()

        [first] = await _batches()
        assert first.state == "failed" and first.state != "landed"
        assert (
            first.error.startswith(landing_queue.COULD_NOT_RUN_PREFIX) and "eslint" in first.error
        )
        lint, suite = first.results
        assert (
            lint["outcome"] == project_checks.COULD_NOT_RUN and lint["missing_program"] == "eslint"
        )
        assert not lint.get("preexisting"), "the whole-check entry for hub-ui did not excuse it"
        assert suite["exit_code"] == 0, "the other check still ran"
        assert first.narrowing == []
        async with async_session_factory() as session:
            run = await session.get(TaskCheckRun, first.check_run_id)
            states = [
                (await landing_queue.latest_landing(session, task_id)).state for task_id in ids
            ]
        assert run.state != "passed"
        assert states == ["queued", "queued"]
        assert [await _status(task_id) for task_id in ids] == ["approved", "approved"]
        assert [await _moved_to(task_id, "revision_needed") for task_id in ids] == [[], []]
        assert all(tip not in commits_on(tmp_path, "main") for tip in tips)

        # The dependencies arrive; the queue's next batch takes the same two tasks and lands them.
        installed.write_text("yes", encoding="utf-8")
        await landing_queue.drain()

        second = (await _batches())[-1]
        assert second.id != first.id and second.state == "landed"
        assert second.task_ids == ids
        for task_id, tip in zip(ids, tips, strict=True):
            assert [row.commit_sha for row in await _merged(task_id)] == [tip]
            assert len(await _moved_to(task_id, "approved")) == 1, "approved once, not again"
        assert all(tip in commits_on(tmp_path, "main") for tip in tips)
    finally:
        landing_queue.cancel_timers()


async def test_a_narrowing_probe_that_could_not_run_blames_nobody(app, tmp_path, monkeypatch):
    """FR-6: a probe whose command could not start proves nothing about a prefix. The batch's own
    failure is narrowed; the probe cannot start; nobody is sent back and the batch is queued
    again."""
    from .test_a_landing_timeout_is_unjudged import _batch, _rows

    async def boom(*args, **kwargs):
        raise AssertionError("a task was sent back on a probe that could not run")

    monkeypatch.setattr(landing_queue, "_send_back", boom)
    landings = await _rows(2)
    base = make_repo(tmp_path)
    await set_main_branch("main")
    await _batch("lbat-cnr0000001", base, landings)
    check = {"name": "ruff", "command": "ruff check .", "timeout_seconds": 60}
    failing = {
        "name": "ruff",
        "exit_code": 1,
        "timed_out": False,
        "duration_seconds": 0.1,
        "output_tail": "E1 bad",
    }
    cannot = dict(failing, outcome=project_checks.COULD_NOT_RUN, missing_program="ruff")
    calls: List[str] = []

    def run_one(*args, **kwargs):
        calls.append("run")
        return dict(failing if len(calls) <= 2 else cannot)  # the batch, its confirmation

    monkeypatch.setattr(project_checks, "run_one", run_one)
    outcome = await landing_queue.run_batch_checks(
        tmp_path, "proj-test", "lbat-cnr0000001", base, base, [check], landings
    )
    decided = await landing_queue._decide(
        tmp_path,
        "main",
        "proj-test",
        "lbat-cnr0000001",
        base,
        [landing.task_id for landing in landings],
        [base, base],
        landings,
        [check],
        outcome,
        landing_queue.Chain(),
    )

    assert decided is False
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, "lbat-cnr0000001")
        states = [(await session.get(TaskLanding, row.id)).state for row in landings]
        tasks = [(await session.get(Task, row.task_id)).status for row in landings]
    assert batch.error.startswith(landing_queue.COULD_NOT_RUN_PREFIX), batch.error
    assert states == ["queued", "queued"] and tasks == ["approved", "approved"]


# ---------------------------------------------------------------------------------------------
# FR-12, FR-10: before review the task waits, and the next run runs the check again
# ---------------------------------------------------------------------------------------------


async def test_ac_prereview_waits_and_ac_runs_again(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    installed = _scripts(tmp_path) / "node_modules-installed"
    await _configure([_lint(tmp_path, installed), _passing(tmp_path)])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    await project_checks.drain()

    [first] = await _runs(task_id)
    assert first.state == "failed" and not project_checks.own_failure(first.results)
    assert [r.get("outcome") for r in first.results] == [project_checks.COULD_NOT_RUN, None]
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        wait = await project_checks.review_wait(session, task)
    assert wait is not None and wait.state == project_checks.COULD_NOT_RUN
    assert not wait.needs_a_run and not wait.returns_the_work
    assert "hub-ui (eslint)" in wait.reason
    assert await _status(task_id) == "completed"
    assert await _moved_to(task_id, "revision_needed") == []
    assert await _moved_to(task_id, "under_review") == []

    # Nothing is carried forward: a run asked for again on the same work and tip is that one, but
    # the operator's re-run runs the command, and with eslint installed it passes on its own output.
    installed.write_text("yes", encoding="utf-8")
    rerun = await app.post(
        f"/api/v1/projects/proj-test/tasks/{task_id}/checks/run", headers=auth_headers
    )
    assert rerun.status_code == 202, rerun.text
    await project_checks.drain()

    second = (await _runs(task_id))[-1]
    assert second.id != first.id and second.state == "passed", second.results
    lint = second.results[0]
    assert lint.get("outcome") is None and "lint ok" in lint["output_tail"]
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        assert await project_checks.review_wait(session, task) is None, "it goes on to review"
    assert await _moved_to(task_id, "revision_needed") == []


async def test_a_fast_check_that_could_not_run_does_not_refuse_the_completion(tmp_path):
    """FR-6 at completion: `failing` (what refuses a completion) never holds a check that could not
    run, nor does the report a send-back carries."""
    results = [
        {"name": "lint", "exit_code": 1, "timed_out": False, "outcome": "could_not_run"},
        {"name": "hub-tests", "exit_code": 0, "timed_out": False},
    ]
    assert not project_checks.own_failure(results)
    assert "lint" not in project_checks.failure_report(results, run_id="chk-x", merged_sha="")
