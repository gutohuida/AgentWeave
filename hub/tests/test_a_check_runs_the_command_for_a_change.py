"""A check can run only the tests for what a task changed
(`a-check-can-run-only-the-tests-for-what-a-task-changed`, FR-1 to FR-7).

A check may carry a command for a change, its `{changed_files}` replaced by the path of a file
listing the files the task changed. A task's pre-review run uses it when that list is known; every
other run -- landing, main, a confirmation -- runs the check's own command.

Real git repositories and real subprocesses, as in `test_project_checks_run.py`. Each command
appends what it ran (and the list file's contents) to a log outside the repository, so which
command ran is observed, not inferred.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub import landing_queue, project_checks
from hub.worktrees import task_branch_name

from .test_checks_read_the_report import PYTEST_RERUN
from .test_project_checks_gate import _approve
from .test_project_checks_run import PY, _project, _runs, _task_with_work
from .test_task_integration import git

#: `log.py <log> <mode> [<list file>]`: appends {mode, list} to the log, then exits 0.
LOG_SCRIPT = """import json, pathlib, sys
log, mode = sys.argv[1], sys.argv[2]
listing = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8") if len(sys.argv) > 3 else None
with open(log, "a", encoding="utf-8") as out:
    out.write(json.dumps({"mode": mode, "list": listing}) + "\\n")
"""


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


@pytest.fixture
def logged(tmp_path_factory):
    """`(check, log)`: a check whose command logs `full` and whose command for a change logs
    `changed` with the list file it was handed."""
    where = tmp_path_factory.mktemp("logged")
    script, log = where / "log.py", where / "ran.jsonl"
    script.write_text(LOG_SCRIPT, encoding="utf-8")
    check = {
        "name": "suite",
        "command": f'{PY} "{script}" "{log}" full',
        "change_command": f'{PY} "{script}" "{log}" changed {{changed_files}}',
        "timeout_seconds": 60,
    }
    return check, log


def _ran(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


# --- FR-1, FR-4: a known change runs the command for a change, and says so ---------------------


@pytest.mark.asyncio
async def test_a_known_change_runs_the_command_for_a_change_with_its_list(app, tmp_path, logged):
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    await _project([check])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    assert _ran(log) == [{"mode": "changed", "list": "feature.py\n"}]
    [run] = await _runs(task_id)
    assert run.state == "passed"
    [result] = run.results
    assert result["sized_to_change"] is True
    assert result["changed_file_count"] == 1
    # The list is beside the run's checkout, never in the tree the check reads.
    listing = project_checks.changed_files_list(tmp_path, task_id)
    assert listing.read_text(encoding="utf-8") == "feature.py\n"
    assert listing.parent == tmp_path / project_checks.CHECKS_DIR


@pytest.mark.asyncio
async def test_a_rename_lists_both_the_old_and_the_new_path(app, tmp_path, logged):
    """cc-ac2."""
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    git(tmp_path, "checkout", "-q", task_branch_name(task_id))
    git(tmp_path, "mv", "README.md", "READ-ME.md")
    git(tmp_path, "commit", "-q", "-m", "rename")
    git(tmp_path, "checkout", "-q", "main")
    await _project([check])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [entry] = _ran(log)
    assert entry["mode"] == "changed"
    assert sorted(entry["list"].splitlines()) == ["READ-ME.md", "README.md", "feature.py"]
    [run] = await _runs(task_id)
    assert run.results[0]["changed_file_count"] == 3


# --- FR-2: an unknown change runs the full command, and says why --------------------------------


@pytest.mark.asyncio
async def test_an_unknown_change_runs_the_full_command_and_says_so(
    app, tmp_path, logged, monkeypatch
):
    """fu-ac1: the merge base cannot be read, so which files changed is not known."""
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    await _project([check])
    monkeypatch.setattr(project_checks, "changed_paths", lambda *args: None)

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    assert _ran(log) == [{"mode": "full", "list": None}]
    [run] = await _runs(task_id)
    [result] = run.results
    assert result["sized_to_change"] is False
    assert result["full_because"] == project_checks.CHANGE_UNKNOWN


@pytest.mark.asyncio
async def test_a_check_without_a_command_for_a_change_records_no_size(app, tmp_path, logged):
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    await _project([{k: v for k, v in check.items() if k != "change_command"}])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    assert _ran(log) == [{"mode": "full", "list": None}]
    [run] = await _runs(task_id)
    assert "sized_to_change" not in run.results[0]


# --- FR-3: only before review ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_landing_batch_runs_the_full_command(app, auth_headers, tmp_path, logged):
    """pr-ac1's seam: the pre-review pass of the command for a change is not a pass of the full
    command, so the batch runs it rather than reusing the narrowed pass."""
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    await _project([check])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    assert [e["mode"] for e in _ran(log)] == ["changed"]

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    await project_checks.drain()

    assert [e["mode"] for e in _ran(log)] == ["changed", "full"]


@pytest.mark.asyncio
async def test_a_run_on_main_runs_the_full_command(app, tmp_path, logged):
    """pr-ac2, the run on main."""
    from hub import known_failing

    check, log = logged
    make_main = await _task_with_work(tmp_path)  # the repository and main branch
    assert make_main
    await _project([check])
    tip = git(tmp_path, "rev-parse", "main").stdout.strip()

    assert await known_failing.run_on_main("proj-test", tip) is not None
    assert _ran(log) == [{"mode": "full", "list": None}]


def test_a_narrowing_or_confirming_re_run_never_uses_the_command_for_a_change(tmp_path):
    """pr-ac2, the re-run: a check sized to the change is re-run through its re-run command, or as
    its own command, exactly as a check without a command for a change."""
    check = {
        "name": "suite",
        "command": "run-all",
        "change_command": "run-related {changed_files}",
        "rerun_command": "run-these {tests}",
    }
    [sized] = project_checks.for_change([check], ["a.py"])
    assert sized["command"] == "run-all"
    narrowed = project_checks.rerun_check(sized, ["t::a"])
    assert narrowed is not None and narrowed["command"].startswith("run-these ")
    # Without a re-run command the whole check runs again: its own command.
    assert project_checks.rerun_check({**sized, "rerun_command": None}, ["t::a"]) is None


# --- FR-6: a pass is reused only for the same list ---------------------------------------------


def test_the_digest_of_a_sized_run_names_its_list_and_the_full_digest_is_unchanged():
    plain = {"name": "suite", "command": "run-all", "timeout_seconds": 60, "paths": []}
    check = {**plain, "change_command": "run-related {changed_files}"}
    # The full command's passes stay reusable when a command for a change is added.
    assert project_checks.check_digest(check) == project_checks.check_digest(plain)
    [one] = project_checks.for_change([check], ["a.py"])
    [same] = project_checks.for_change([check], ["a.py", "a.py"])
    [other] = project_checks.for_change([check], ["b.py"])
    digests = {project_checks.check_digest(c) for c in (one, other, check)}
    assert len(digests) == 3
    assert project_checks.check_digest(one) == project_checks.check_digest(same)


@pytest.mark.asyncio
async def test_the_same_tree_with_another_list_runs_again(app, tmp_path, logged):
    """ru-ac1: a pass on tree T with list L is not reused for T with another list."""
    check, log = logged
    task_id, _ = await _task_with_work(tmp_path)
    git(tmp_path, "checkout", "-q", task_branch_name(task_id))
    (tmp_path / "other.py").write_text("y = 2\n", encoding="utf-8")
    git(tmp_path, "add", "other.py")
    git(tmp_path, "commit", "-q", "-m", "other")
    git(tmp_path, "checkout", "-q", "main")
    await _project([check])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    # main gains other.py exactly as the task has it, and the task brings main in: the merged tree
    # is the one already passed, while the task now changes only feature.py against main.
    (tmp_path / "other.py").write_text("y = 2\n", encoding="utf-8")
    git(tmp_path, "add", "other.py")
    git(tmp_path, "commit", "-q", "-m", "other lands on main")
    git(tmp_path, "checkout", "-q", task_branch_name(task_id))
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "bring in main", "main")
    git(tmp_path, "checkout", "-q", "main")
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    first, second = await _runs(task_id)
    assert first.results[0]["tree"] == second.results[0]["tree"]
    assert [e["list"] for e in _ran(log)] == ["feature.py\nother.py\n", "feature.py\n"]
    assert "reused_from" not in second.results[0]

    # The same tree with the same list is reused, and still says it was sized to the change.
    await project_checks.request_run("proj-test", task_id, force=False)
    await project_checks.drain()
    third = (await _runs(task_id))[-1]
    if third.id != second.id:
        assert third.results[0]["reused_from"]
        assert third.results[0]["sized_to_change"] is True
    assert len(_ran(log)) == 2


# --- FR-5: a failure of the command for a change is judged as any failure ----------------------

SUITE_A = "from a import double\n\n\ndef test_double():\n    assert double(2) == 4\n"
SUITE_B = "def test_b():\n    assert True\n"
#: `related.py <list file>`: pytest on the test files that name a changed module.
RELATED = r"""import pathlib, re, subprocess, sys
names = {pathlib.PurePosixPath(p).stem for p in pathlib.Path(sys.argv[1]).read_text().split()}
files = [str(f) for f in sorted(pathlib.Path(".").glob("test_*.py"))
         if any(re.search(r"\b" + n + r"\b", f.read_text()) for n in names)]
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-p", "no:randomly", "--junitxml=report.xml", *files]))
"""


@pytest.mark.asyncio
async def test_a_failure_is_named_by_the_report_and_confirmed_by_the_re_run_command(
    app, tmp_path, tmp_path_factory
):
    """js-ac1's seam: the failing test is read from the report and confirmed through the re-run
    command, which is never the command for a change."""
    log = tmp_path_factory.mktemp("log") / "rerun.jsonl"
    task_id, _ = await _task_with_work(tmp_path)
    for name, content in {
        "a.py": "def double(x):\n    return x * 2\n",
        "test_a.py": SUITE_A,
        "test_b.py": SUITE_B,
        "rerun.py": PYTEST_RERUN,
        "related.py": RELATED,
        ".gitignore": "report.xml\n",
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
        git(tmp_path, "add", name)
    git(tmp_path, "commit", "-q", "-m", "the suite")
    git(tmp_path, "checkout", "-q", task_branch_name(task_id))
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "bring in main", "main")
    (tmp_path / "a.py").write_text("def double(x):\n    return x + 3\n", encoding="utf-8")
    git(tmp_path, "add", "a.py")
    git(tmp_path, "commit", "-q", "-m", "break a")
    git(tmp_path, "checkout", "-q", "main")
    pytest_ = f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly --junitxml=report.xml"
    await _project(
        [
            {
                "name": "pytest",
                "command": pytest_,
                # The project's choice of related tests: the test files naming a changed module.
                "change_command": f"{PY} related.py {{changed_files}}",
                "timeout_seconds": 120,
                "report_path": "report.xml",
                "rerun_command": f'{PY} rerun.py "{log}" {{tests}}',
            }
        ]
    )

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state == "failed", (run.error, run.results)
    [result] = run.results
    assert result["sized_to_change"] is True
    assert result["failed_tests"] == ["test_a::test_double"]
    assert result["confirmed"]["how"] == "tests"
    # Only test_a.py ran: test_b's passing test would have said "passed".
    assert "1 failed" in result["output_tail"] and "passed" not in result["output_tail"]
    reruns = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["args"] for r in reruns] == [["test_a::test_double"]]


# --- FR-7: the setting -------------------------------------------------------------------------

URL = "/api/v1/projects/proj-test/settings"


@pytest.mark.asyncio
async def test_a_command_for_a_change_without_its_placeholder_is_refused(app, auth_headers):
    """st-ac1."""
    bad = {"name": "t", "command": "pytest", "change_command": "pytest related"}
    refused = await app.put(URL, json={"checks": [bad]}, headers=auth_headers)
    assert refused.status_code == 422, refused.text
    assert "{changed_files}" in refused.text

    good = {**bad, "change_command": "python related.py {changed_files}"}
    saved = await app.put(URL, json={"checks": [good]}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["checks"][0]["change_command"] == good["change_command"]
    read = await app.get(URL, headers=auth_headers)
    assert read.json()["checks"][0]["change_command"] == good["change_command"]
