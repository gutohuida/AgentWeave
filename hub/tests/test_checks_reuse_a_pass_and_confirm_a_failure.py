"""The approval gate re-runs only what it must (Tier 1, operator brief 2026-10-25).

Measured on the operator's Hub (flow loop-df5f74816122): sixteen gate runs, ~147 minutes, and four of
thirteen finished runs failed only on flaky tests the task never touched. Two causes, two fixes:

- A result counted only for the exact (main commit, task branch commit) pair, so a prerequisite merged
  into the task's branch, which leaves the merged tree as it was, ran the whole suite again. A pass is
  now reused for an identical merged *tree* and an identical check, and for nothing else.
- A flake that failed on the task's tree and passed on main was charged to the task. A failure is now
  run once more on the same tree (the failed tests alone, through the check's re-run command, where
  its report names them) before it counts,
  and a flake is recorded in the result, never swallowed.

Real git repositories and real subprocesses, as in `test_project_checks_run.py`. Each check counts
its own executions in a file outside the repository, so "nothing ran" is observed, not inferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Task
from hub.worktrees import task_branch_name

from .test_checks_read_the_report import PYTEST_RERUN
from .test_checks_refresh_when_main_moves import _move_main
from .test_project_checks_gate import _approve
from .test_project_checks_run import PY, _project, _runs, _task_with_work, listed_whole_check
from .test_task_integration import commits_on, git


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


def _counting(name: str, counter: Path, *, fail_first: int = 0) -> dict:
    """A check that appends a line to *counter* each time it runs, and fails its first *fail_first*
    executions (a flake). The counter is outside the repository, so it is not in the tree."""
    path = counter.as_posix()
    return {
        "name": name,
        "command": (
            f"{PY} -c \"import sys; f = open(r'{path}', 'a+'); f.seek(0); n = len(f.read()); "
            f"f.write('x'); f.close(); sys.exit(1 if n < {fail_first} else 0)\""
        ),
        "timeout_seconds": 60,
    }


def _executions(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8")) if counter.exists() else 0


def _bring_in_main(repo: Path, task_id: str) -> str:
    """What the Hub's "Bring in approved prerequisite work" does: main merged into the task branch,
    which moves the branch head and leaves main-plus-the-branch exactly as it was."""
    branch = task_branch_name(task_id)
    git(repo, "checkout", "-q", branch)
    git(repo, "merge", "-q", "--no-ff", "-m", "bring in approved prerequisite work", "main")
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "main")
    return head


# --- a pass is reused for an identical tree ----------------------------------------------------


async def test_a_prerequisite_merged_into_the_branch_is_approved_without_running_again(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """The acceptance drive: the branch head moves, the merged tree does not, and approval passes
    at once on the pass already recorded for that tree. Before, it refused (`running`) and re-ran.
    """
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, work = await _task_with_work(repo)
    _move_main(repo, "prerequisite.txt")  # a prerequisite lands on main
    await _project([_counting("suite", counter)])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    assert _executions(counter) == 1
    [first] = await _runs(task_id)
    assert first.state == "passed"

    head = _bring_in_main(repo, task_id)
    assert head != work

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    # Its batch's merged tree is the tree already passed: landed without running again.
    await landing_queue.drain()
    assert head in commits_on(repo, "main")
    await project_checks.drain()
    assert _executions(counter) == 1, "the identical tree was checked again"


async def test_a_run_on_an_identical_tree_is_recorded_from_the_pass_without_executing(
    app, tmp_path, tmp_path_factory
):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    _move_main(repo, "prerequisite.txt")
    await _project([_counting("suite", counter)])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    head = _bring_in_main(repo, task_id)

    second = await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    runs = await _runs(task_id)
    assert [r.state for r in runs] == ["passed", "passed"]
    assert runs[1].id == second and runs[1].target_shas == [head]
    assert runs[1].results[0]["reused_from"] == runs[0].id
    assert runs[1].results[0]["tree"] == runs[0].results[0]["tree"]
    assert _executions(counter) == 1


async def test_a_different_tree_is_checked_again(app, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    await _project([_counting("suite", counter)])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    _move_main(repo, "unrelated.txt")  # the merged tree now holds a file it did not
    # A pass of the same work counts on any tip (`approved-work-merges-in-batches`, FR-9), so the
    # work changes: main brought into the branch, whose tree no run has checked.
    _bring_in_main(repo, task_id)
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    runs = await _runs(task_id)
    assert [r.state for r in runs] == ["passed", "passed"]
    assert "reused_from" not in runs[1].results[0]
    assert runs[1].results[0]["tree"] != runs[0].results[0]["tree"]
    assert _executions(counter) == 2


async def test_a_changed_check_is_not_reused_on_the_same_tree(app, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    _move_main(repo, "prerequisite.txt")
    check = _counting("suite", counter)
    await _project([check])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    _bring_in_main(repo, task_id)

    await _project([{**check, "timeout_seconds": 61}])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    assert _executions(counter) == 2


async def test_a_forced_re_run_executes_on_an_identical_tree(app, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    await _project([_counting("suite", counter)])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    await project_checks.request_run("proj-test", task_id, force=True)
    await project_checks.drain()
    assert _executions(counter) == 2


async def test_a_failure_is_never_reused(app, auth_headers, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    _move_main(repo, "prerequisite.txt")
    await _project([_counting("suite", counter, fail_first=99)])
    # The whole check is on the known-failing list, so its failure is not the task's.
    await listed_whole_check("suite")
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    [run] = await _runs(task_id)
    assert run.state == "failed"
    ran = _executions(counter)
    _bring_in_main(repo, task_id)

    # The failure was on the work before main was brought in: it holds nothing now, and the
    # batch runs the check again on the same tree rather than reusing the failure.
    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    await project_checks.drain()
    assert _executions(counter) > ran, "a failure on the same tree is run again, not reused"


# --- a failure is confirmed before it is the task's --------------------------------------------


async def test_a_check_that_fails_once_and_passes_again_passes_and_records_the_flake(
    app, tmp_path, tmp_path_factory
):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    await _project([_counting("suite", counter, fail_first=1)])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state == "passed"
    [result] = run.results
    assert result["exit_code"] == 0 and not project_checks.failed(result)
    assert result["flaky"]["how"] == "check"
    assert result["flaky"]["first"]["exit_code"] == 1
    assert "flaky" in result["output_tail"]
    assert "on_main" not in result, "a flake needs no baseline on main"
    assert _executions(counter) == 2

    from hub.review_turn import _checks_sentence

    async with async_session_factory() as session:
        sentence = await _checks_sentence(session, await session.get(Task, task_id))
    assert sentence and "checks passed" in sentence
    assert "`suite` failed once and passed when run again" in sentence, sentence


async def test_a_reproduced_failure_still_refuses_and_says_it_was_confirmed(
    app, auth_headers, tmp_path
):
    repo = tmp_path
    task_id, work = await _task_with_work(repo)
    # Fails where the task's work is, passes on main: the task's own, reproducible failure.
    check = {
        "name": "tests",
        "command": f"{PY} -c \"import os, sys; sys.exit(3 if os.path.exists('feature.py') else 0)\"",
        "timeout_seconds": 60,
    }
    await _project([check])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state == "failed"
    [result] = run.results
    assert result["confirmed"]["how"] == "check" and result["confirmed"]["exit_code"] == 3
    assert not result["preexisting"] and result["listed"] == []
    refused = await _approve(app, auth_headers, task_id)
    assert refused.status_code == 409, refused.text
    assert work not in commits_on(repo, "main")


def _pytest_project(repo: Path, counter: Path) -> None:
    """A test file on main: one test that fails its first execution, one that always passes; each
    appends its name to *counter*. With the project's re-run wrapper (`PYTEST_RERUN`)."""
    path = counter.as_posix()
    (repo / "test_sample.py").write_text(
        "def _ran(name):\n"
        f"    with open(r'{path}', 'a+') as f:\n"
        "        f.seek(0)\n"
        "        seen = f.read().split()\n"
        "        f.write(name + ' ')\n"
        "    return seen.count(name)\n"
        "\n"
        "def test_flaky():\n"
        "    assert _ran('flaky') >= 1\n"
        "\n"
        "def test_ok():\n"
        "    _ran('ok')\n",
        encoding="utf-8",
    )
    (repo / "rerun.py").write_text(PYTEST_RERUN, encoding="utf-8")
    (repo / ".gitignore").write_text("report.xml\n", encoding="utf-8")
    git(repo, "add", "test_sample.py", "rerun.py", ".gitignore")
    git(repo, "commit", "-q", "-m", "tests")


def _pytest_check(log: Path) -> dict:
    """A pytest check writing a JUnit report, re-run through the wrapper logging to *log*. xunit1,
    so each testcase names its file: a failing test whose file is unknown counts as touched."""
    return {
        "name": "pytest",
        "command": f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly "
        "-o junit_family=xunit1 --junitxml=report.xml",
        "timeout_seconds": 120,
        "report_path": "report.xml",
        "rerun_command": f'{PY} rerun.py "{log}" {{tests}}',
    }


async def test_a_flaky_pytest_failure_re_runs_only_the_failed_test(app, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    _pytest_project(repo, counter)
    await _project([_pytest_check(tmp_path_factory.mktemp("log") / "ran.log")])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    [result] = run.results
    assert run.state == "passed", result
    assert result["flaky"]["how"] == "tests"
    assert result["flaky"]["tests"] == ["test_sample::test_flaky"]
    ran = counter.read_text(encoding="utf-8").split()
    assert ran.count("ok") == 1, "only the failed test ran again"
    assert ran.count("flaky") == 2


def test_a_rerun_that_ran_nothing_proves_nothing():
    nothing = {"exit_code": 5, "timed_out": False, "output_tail": "no tests ran in 0.01s\n"}
    usage = {"exit_code": 4, "timed_out": False, "output_tail": "ERROR: file not found: x\n"}
    for result in (nothing, usage):
        assert not project_checks.proves_the_tests_pass(result, ["t.py::a"])
        assert not project_checks.reproduces_a_test_failure(result)


# --- main moving does not re-check a task already going back -------------------------------------


async def test_a_task_whose_own_failure_stands_is_not_re_checked_when_main_moves(app, tmp_path):
    repo = tmp_path
    task_id, _ = await _task_with_work(repo)
    check = {
        "name": "tests",
        "command": f"{PY} -c \"import os, sys; sys.exit(3 if os.path.exists('feature.py') else 0)\"",
        "timeout_seconds": 60,
    }
    await _project([check])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = "under_review"
        await session.commit()
    _move_main(repo)

    await project_checks.refresh("proj-test")
    await project_checks.drain()

    assert [r.state for r in await _runs(task_id)] == ["failed"]


def test_a_long_failing_output_keeps_what_its_report_says_about_each_failure(tmp_path_factory):
    """The stored tail of a long suite holds only its end; what the report says about each failing
    test is kept too, whatever the runner (FR-7). Two gate runs on 2026-10-25 kept the failing id
    and nothing that said why."""
    outside = tmp_path_factory.mktemp("noisy")
    script = outside / "noisy.py"
    script.write_text(
        "import pathlib, sys\n"
        "print('E   AssertionError: the reason it failed')\n"
        "print('warning line\\n' * 800)\n"
        "pathlib.Path('report.xml').write_text(\n"
        '    \'<testsuites><testcase classname="t" name="a">\'\n'
        "    '<failure message=\"AssertionError: the reason it failed\">tb line</failure>'\n"
        '    \'</testcase><testcase classname="t" name="b"/></testsuites>\')\n'
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    result = project_checks.run_one(
        {
            "name": "suite",
            "command": f'{PY} "{script}"',
            "timeout_seconds": 60,
            "report_path": "report.xml",
        },
        outside,
    )
    assert "the reason it failed" not in result["output_tail"]
    assert result["failure_excerpt"] == "t::a\nAssertionError: the reason it failed\ntb line"
    assert result["failed_tests"] == ["t::a"]


# --- a check's `-n auto` is sized to its share of the machine -----------------------------------


def test_a_checks_auto_workers_are_its_share_of_the_cpus(monkeypatch):
    monkeypatch.delenv(project_checks.XDIST_AUTO_WORKERS_VARIABLE, raising=False)
    env, _ = project_checks.check_environment()
    assert env[project_checks.XDIST_AUTO_WORKERS_VARIABLE] == str(project_checks.auto_workers())
    assert project_checks.MAX_CONCURRENT_RUNS == 2
    assert project_checks.auto_workers(20) == 6, "two runs and the agents share 20 CPUs"
    assert project_checks.auto_workers(2) == 1


def test_an_operators_own_worker_count_is_kept(monkeypatch):
    monkeypatch.setenv(project_checks.XDIST_AUTO_WORKERS_VARIABLE, "3")
    env, _ = project_checks.check_environment()
    assert env[project_checks.XDIST_AUTO_WORKERS_VARIABLE] == "3"


def test_pytest_xdist_sizes_auto_by_the_variable(tmp_path_factory, monkeypatch):
    """The knob is xdist's own: a real `-n auto` run in the check environment uses it."""
    monkeypatch.setenv(project_checks.XDIST_AUTO_WORKERS_VARIABLE, "2")
    outside = tmp_path_factory.mktemp("xdist")
    (outside / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    result = project_checks.run_one(
        {
            "name": "auto",
            # Its own --basetemp: otherwise this run, as it exits, deletes whatever old pytest-N
            # directories other suites left in the shared temp folder, which can take past this
            # timeout with `1 passed` already printed (F1109).
            "command": (
                f"{PY} -m pytest -n auto -p no:cacheprovider "
                f'--basetemp "{outside / "basetemp"}" test_one.py'
            ),
            "timeout_seconds": 120,
        },
        outside,
    )
    assert result["exit_code"] == 0, result["output_tail"]
    assert "created: 2/2 workers" in result["output_tail"], result["output_tail"]


def test_a_check_ends_when_its_process_does_not_when_its_output_closes(tmp_path_factory):
    """A process that outlives the check and holds its output open does not make it time out.

    The xdist check above timed out on 2026-10-30 with `1 passed` already printed: the run
    waited for the end of its output, which something still holding the pipe kept open.

    The verdict is that the check ended while the holder was still alive, holding the pipe, not a
    duration: the holder outlives the check's timeout many times over, so a run waiting for its
    output to close times out instead, however fast or slow the machine is. (It was
    `duration_seconds < 20` against a 20 s timeout and a 60 s holder.)
    """
    from hub.pty_runner import pid_alive, terminate_process_tree

    outside = tmp_path_factory.mktemp("lingering")
    pid_file = outside / "holder.pid"
    script = outside / "leave_a_holder.py"
    script.write_text(
        "import subprocess, sys\n"
        "holder = subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(900)'], stdout=sys.stdout\n"
        ")\n"
        f"open({str(pid_file)!r}, 'w').write(str(holder.pid))\n"
        "print('1 passed')\n",
        encoding="utf-8",
    )
    holder_alive_at_the_end = None
    try:
        result = project_checks.run_one(
            {"name": "lingering", "command": f'{PY} "{script}"', "timeout_seconds": 120},
            outside,
        )
        holder_alive_at_the_end = pid_file.exists() and pid_alive(int(pid_file.read_text()))
    finally:
        if pid_file.exists():
            terminate_process_tree(int(pid_file.read_text()))
    assert not result["timed_out"], result["output_tail"]
    assert result["exit_code"] == 0, result["output_tail"]
    assert "1 passed" in result["output_tail"]
    assert holder_alive_at_the_end, "the check ended only once its output's holder had gone"
