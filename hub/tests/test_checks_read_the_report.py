"""A check's failing tests come from its JUnit XML report, and its failing tests are re-run through
its own re-run command (`checks-report-which-tests-failed-in-any-language`, FR-1 to FR-6).

The seams: the settings route (FR-1), `parse_report` over reports recorded from pytest (xunit1 and
xunit2), Node's runner and Vitest (FR-2, FR-3), `run_one` running real commands that write (or do
not write) a report (FR-4, FR-5), `confirm_failure` and batch narrowing re-running through the
re-run command (FR-4, FR-6), and a landing batch's narrowing over real git (FR-6). Every command is
a small Python script, so what ran, and with which arguments, is logged, not inferred.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Project

from .test_a_failing_batch_is_narrowed import (
    _approve,
    _batches,
    _project,
    _status,
    _tasks,
)
from .test_task_integration import git, make_repo

PY = f'"{sys.executable}"'
FIXTURES = Path(__file__).parent / "fixtures" / "junit"
URL = "/api/v1/projects/proj-test/settings"


def _recorded(name: str, root: Path) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8").replace("{ROOT}", root.as_posix())


def _junit(cases: Dict[str, str]) -> str:
    """A JUnit XML report: `{"classname::name": "passed" | "failed" | "error" | "skipped"}`."""
    body = []
    for test, outcome in cases.items():
        classname, name = test.split("::", 1)
        element = {"failed": "failure", "error": "error", "skipped": "skipped"}.get(outcome)
        inner = f"<{element} message='x'/>" if element else ""
        body.append(f'<testcase classname="{classname}" name="{name}">{inner}</testcase>')
    return f'<?xml version="1.0"?><testsuites><testsuite>{"".join(body)}</testsuite></testsuites>'


#: A check's command: logs that it ran to `ran.log` beside the project, writes `report` (when
#: given) to report.xml, and exits with `code`.
WRITER = """import json, sys, pathlib
here = pathlib.Path.cwd()
spec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
with open(spec["log"], "a", encoding="utf-8") as out:
    out.write(json.dumps({"as": spec["as"], "args": sys.argv[2:]}) + "\\n")
if spec.get("once") and (here / "wrote-once").exists():
    spec["report"] = None
if spec.get("report") is not None:
    (here / "report.xml").write_text(spec["report"], encoding="utf-8")
    (here / "wrote-once").write_text("", encoding="utf-8")
sys.exit(spec["code"])
"""


def _command(cwd: Path, log: Path, as_: str, code: int, report: Any = None, once=False) -> str:
    """A command running `WRITER` as *as_* (logged), writing *report* and exiting *code*."""
    (cwd / "writer.py").write_text(WRITER, encoding="utf-8")
    spec = cwd.parent / f"{cwd.name}-{as_}.json"
    spec.write_text(
        json.dumps({"log": str(log), "as": as_, "code": code, "report": report, "once": once}),
        encoding="utf-8",
    )
    return f'{PY} writer.py "{spec}"'


def _calls(log: Path) -> List[Dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _check(command: str, **fields: Any) -> Dict[str, Any]:
    return {"name": "tests", "command": command, "timeout_seconds": 60, **fields}


@pytest.fixture
def where(tmp_path_factory):
    cwd = tmp_path_factory.mktemp("project")
    return cwd, cwd.parent / f"{cwd.name}-ran.log"


# --- FR-1: the settings ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rerun_command_without_the_placeholder_is_refused_naming_it(app, auth_headers):
    """placeholder-required."""
    refused = await app.put(
        URL,
        json={"checks": [{"name": "t", "command": "npm test", "rerun_command": "npm test --"}]},
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text
    assert "{tests}" in refused.text
    assert (await app.get(URL, headers=auth_headers)).json()["checks"] is None

    plain = await app.put(
        URL, json={"checks": [{"name": "t", "command": "npm test"}]}, headers=auth_headers
    )
    assert plain.status_code == 200, plain.text
    read = (await app.get(URL, headers=auth_headers)).json()["checks"][0]
    assert read["report_path"] is None and read["rerun_command"] is None

    both = {
        "name": "t",
        "command": "node --test --test-reporter=junit --test-reporter-destination=out/r.xml",
        "report_path": "out\\r.xml",
        "rerun_command": "node rerun.js {tests}",
    }
    saved = await app.put(URL, json={"checks": [both]}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    read = (await app.get(URL, headers=auth_headers)).json()["checks"][0]
    assert (read["report_path"], read["rerun_command"]) == ("out/r.xml", "node rerun.js {tests}")
    async with async_session_factory() as session:
        configured = project_checks.configured_checks(await session.get(Project, "proj-test"))
    assert configured[0]["report_path"] == "out/r.xml"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/tmp/r.xml", "../r.xml", "C:/r.xml", "a/../../r.xml"])
async def test_a_report_path_outside_the_checks_directory_is_refused(app, auth_headers, path):
    refused = await app.put(
        URL,
        json={"checks": [{"name": "t", "command": "x", "report_path": path}]},
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text
    assert "report_path" in refused.text


def test_a_check_without_a_report_keeps_its_digest():
    """A pass recorded before this change is still reused: the digest gains the new settings only
    where they are set."""
    plain = _check("pytest")
    assert project_checks.check_digest({**plain, "report_path": None, "rerun_command": None}) == (
        project_checks.check_digest(plain)
    )
    assert project_checks.check_digest({**plain, "report_path": "r.xml"}) != (
        project_checks.check_digest(plain)
    )


# --- FR-2, FR-3: ids from recorded reports --------------------------------------------------------

RECORDED = [
    ("pytest_xunit1.xml", "pytest_xunit1_rerun.xml", "pkg.test_same.TestA::test_same"),
    ("pytest_xunit2.xml", "pytest_xunit2_rerun.xml", "pkg.test_same.TestA::test_same"),
    ("node_full.xml", "node_rerun.xml", "test::adds two numbers"),
    ("vitest_full.xml", "vitest_rerun.xml", "math.test.js::math > adds"),
]


@pytest.mark.parametrize("full, rerun, test", RECORDED)
def test_a_rerun_reports_the_failing_test_under_the_full_runs_id(tmp_path, full, rerun, test):
    """rerun-ids-match: the id is the report's classname and name, the same in both runs."""
    first = project_checks.parse_report(_recorded(full, tmp_path), tmp_path)
    again = project_checks.parse_report(_recorded(rerun, tmp_path), tmp_path)
    assert first is not None and again is not None
    assert test in first.failing
    assert again.failing == [test]


@pytest.mark.parametrize("name", ["pytest_xunit1.xml", "pytest_xunit2.xml"])
def test_same_named_methods_in_two_classes_of_one_file_get_different_ids(tmp_path, name):
    report = project_checks.parse_report(_recorded(name, tmp_path), tmp_path)
    assert report is not None
    assert report.outcomes["pkg.test_same.TestA::test_same"] is True
    assert report.outcomes["pkg.test_same.TestB::test_same"] is False
    assert report.failing == [
        "pkg.test_same.TestA::test_same",
        "pkg.test_same::test_module_level",
        "pkg.test_same::test_param[2]",
    ]


def test_the_file_a_testcase_names_is_kept_beside_its_id_relative_to_the_check(tmp_path):
    pytest_report = project_checks.parse_report(_recorded("pytest_xunit1.xml", tmp_path), tmp_path)
    node_report = project_checks.parse_report(_recorded("node_full.xml", tmp_path), tmp_path)
    assert pytest_report.files["pkg.test_same.TestA::test_same"] == "pkg/test_same.py"
    assert node_report.files["test::adds two numbers"] == "calc.test.js"
    assert "::" not in node_report.files["test::adds two numbers"]  # never part of the id


def test_a_skipped_testcase_is_neither_passed_nor_failed(tmp_path):
    """A re-run that skipped a test is no proof it passes."""
    report = project_checks.parse_report(_recorded("vitest_rerun.xml", tmp_path), tmp_path)
    assert report.outcomes["math.test.js::math > subtracts"] is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not xml at all",
        "<html><body/></html>",
        '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>',
    ],
)
def test_what_is_not_a_junit_report_reads_as_none(tmp_path, text):
    assert project_checks.parse_report(text, tmp_path) is None


# --- FR-4, FR-5: the run ----------------------------------------------------------------------------

TWO = {"t.T::fails": "failed", "t.T::passes": "passed"}


def test_a_failing_check_names_exactly_its_reports_failing_tests(where):
    cwd, log = where
    report = _junit({**TWO, "t.U::errors": "error", "t.U::skips": "skipped"})
    check = _check(_command(cwd, log, "full", 1, report), report_path="report.xml")
    result = project_checks.run_one(check, cwd)
    assert project_checks.failed(result)
    assert result["failed_tests"] == ["t.T::fails", "t.U::errors"]
    assert result["report"] == "read" and "whole_check" not in result


@pytest.mark.parametrize(
    "report_path, report, reason",
    [
        (None, _junit(TWO), "no report configured"),
        ("report.xml", None, "report missing"),
        ("report.xml", "this is not xml <", "report unreadable"),
        ("report.xml", "", "report unreadable"),
    ],
)
def test_a_failure_without_a_readable_report_is_the_whole_checks_and_says_why(
    where, report_path, report, reason
):
    """missing-report-said."""
    cwd, log = where
    check = _check(_command(cwd, log, "full", 1, report), report_path=report_path)
    result = project_checks.run_one(check, cwd)
    assert project_checks.failed(result)
    assert not result.get("failed_tests")
    assert result["whole_check"] == reason


def test_the_report_is_removed_before_the_check_runs(where):
    """Only a report the run itself wrote is read (FR-4)."""
    cwd, log = where
    (cwd / "report.xml").write_text(_junit(TWO), encoding="utf-8")
    check = _check(_command(cwd, log, "full", 1, None), report_path="report.xml")
    result = project_checks.run_one(check, cwd)
    assert not (cwd / "report.xml").exists()
    assert result["whole_check"] == "report missing" and not result.get("failed_tests")


def test_the_exit_code_decides_and_the_report_only_names(where):
    """exit-3-whole-check."""
    cwd, log = where
    exit_3 = _check(
        _command(cwd, log, "full", 3, _junit({"t.T::passes": "passed"})), report_path="report.xml"
    )
    result = project_checks.run_one(exit_3, cwd)
    assert project_checks.failed(result) and result["exit_code"] == 3
    assert not result.get("failed_tests")
    assert result["whole_check"] == "report names no failing test"

    exit_0 = _check(_command(cwd, log, "zero", 0, _junit(TWO)), report_path="report.xml")
    result = project_checks.run_one(exit_0, cwd)
    assert not project_checks.failed(result)
    assert not result.get("failed_tests") and "whole_check" not in result


def test_a_build_caught_entry_for_a_whole_check_failure_says_why():
    from hub import build_caught

    entries = build_caught._entries(
        {"name": "tests", "exit_code": 1, "timed_out": False, "whole_check": "report missing"}
    )
    assert entries == [
        {
            "test": None,
            "kind": "check failed",
            "origin": build_caught.INTRODUCED,
            "whole_check": "report missing",
            "check": "tests",
            "changed_by_build": False,
        }
    ]


# --- FR-6: re-running through the re-run command ------------------------------------------------

#: A re-run command: logs the ids it was given, as separate arguments, and writes a report naming
#: each as failing (exit 1) or, with `pass` first, as passing (exit 0).
RERUN = """import json, sys, pathlib
log, outcome, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
with open(log, "a", encoding="utf-8") as out:
    out.write(json.dumps({"as": "rerun", "args": ids}) + "\\n")
cases = "".join(
    '<testcase classname="%s" name="%s">%s</testcase>'
    % (*i.split("::", 1), "" if outcome == "pass" else "<failure/>")
    for i in ids
)
pathlib.Path("report.xml").write_text("<testsuites>%s</testsuites>" % cases, encoding="utf-8")
sys.exit(0 if outcome == "pass" else 1)
"""
SPACED = "test::adds two numbers"


def _rerun(cwd: Path, log: Path, outcome: str) -> str:
    (cwd / "rerun.py").write_text(RERUN, encoding="utf-8")
    return f'{PY} rerun.py "{log}" {outcome} {{tests}}'


@pytest.mark.parametrize("outcome, confirmed", [("fail", True), ("pass", False)])
def test_a_failure_is_confirmed_by_the_rerun_command_with_only_its_ids(where, outcome, confirmed):
    """The confirmation runs the re-run command with each failing id one argument, and reads the
    re-run's own report: reproduced, the failure stands; passed, it is a flake of those tests."""
    cwd, log = where
    report = _junit({SPACED: "failed", "test::adds zero": "passed"})
    check = _check(
        _command(cwd, log, "full", 1, report),
        report_path="report.xml",
        rerun_command=_rerun(cwd, log, outcome),
    )
    result = project_checks.run_one(check, cwd)
    assert result["failed_tests"] == [SPACED]
    project_checks.confirm_failure(check, cwd, result, None, changed=[])
    assert [c["args"] for c in _calls(log) if c["as"] == "rerun"] == [[SPACED]]
    assert len([c for c in _calls(log) if c["as"] == "full"]) == 1
    if confirmed:
        assert result["confirmed"]["how"] == "tests" and result["confirmed"]["tests"] == [SPACED]
        assert result["compared_tests"] == [SPACED]
    else:
        assert result["flaky"]["how"] == "tests" and result["flaky_tests"] == [SPACED]
        assert not project_checks.failed(result)


def test_a_rerun_that_writes_no_report_reads_report_missing_not_the_full_runs(where):
    """stale-report-not-read: the full run's report names the failure; the re-run (and the whole
    re-run after it) writes none in the same directory."""
    cwd, log = where
    check = _check(
        _command(cwd, log, "full", 1, _junit(TWO), once=True),
        report_path="report.xml",
        rerun_command=f'{PY} writer.py "{cwd.parent / (cwd.name + "-nothing.json")}" {{tests}}',
    )
    (cwd.parent / f"{cwd.name}-nothing.json").write_text(
        json.dumps({"log": str(log), "as": "rerun", "code": 1, "report": None}), encoding="utf-8"
    )
    result = project_checks.run_one(check, cwd)
    assert result["failed_tests"] == ["t.T::fails"]
    project_checks.confirm_failure(check, cwd, result, None, changed=[])
    assert [c["args"] for c in _calls(log) if c["as"] == "rerun"] == [["t.T::fails"]]
    assert result["confirmed"]["how"] == "check"
    assert result["confirmed"]["report"] == "report missing"
    assert "compared_tests" not in result


def test_a_rerun_command_too_long_with_its_ids_re_runs_the_whole_check(where):
    """long-rerun-whole."""
    cwd, log = where
    many = {f"suite.Case::{'x' * 150}_{n}": "failed" for n in range(60)}
    check = _check(
        _command(cwd, log, "full", 1, _junit(many)),
        report_path="report.xml",
        rerun_command=_rerun(cwd, log, "fail"),
    )
    result = project_checks.run_one(check, cwd)
    assert len(result["failed_tests"]) == 60
    assert project_checks.rerun_command(check, result["failed_tests"]) is None
    project_checks.confirm_failure(check, cwd, result, None, changed=[])
    assert [c["as"] for c in _calls(log)] == ["full", "full"]
    assert result["confirmed"]["how"] == "check"


def test_a_check_with_a_report_and_no_rerun_command_re_runs_as_a_whole(where):
    cwd, log = where
    check = _check(_command(cwd, log, "full", 1, _junit(TWO)), report_path="report.xml")
    result = project_checks.run_one(check, cwd)
    assert project_checks.rerun_check(check, result["failed_tests"]) is None
    project_checks.confirm_failure(check, cwd, result, None, changed=[])
    assert [c["as"] for c in _calls(log)] == ["full", "full"]
    assert result["confirmed"]["how"] == "check"


def test_a_failing_test_in_a_file_the_task_changed_is_touched_by_its_reported_file(where):
    cwd, log = where
    report = (
        '<testsuites><testcase classname="test" name="adds" file="spec/calc.test.js">'
        "<failure/></testcase></testsuites>"
    )
    check = _check(
        _command(cwd, log, "full", 1, report),
        report_path="report.xml",
        rerun_command=_rerun(cwd, log, "pass"),
    )
    result = project_checks.run_one(check, cwd)
    assert result["test_files"] == {"test::adds": "spec/calc.test.js"}
    project_checks.confirm_failure(check, cwd, result, None, changed=["spec/calc.test.js"])
    # A flake in a file the task changes is the task's (FR-4 of a-red-main-...): it stands.
    assert result["touched_tests"] == ["test::adds"]
    assert result["compared_tests"] == ["test::adds"] and "flaky" not in result


def test_a_reported_failure_with_no_file_is_touched_when_the_task_changed_files(where):
    """pytest's default xunit2 report names no file: the id's file is unknown, so a failure that
    passes its re-run stands rather than being cleared as flaky on a file guessed from its
    classname (an override is never automatic on a guess)."""
    cwd, log = where
    report = (
        '<testsuites><testcase classname="pkg.test_same.TestA" name="test_same">'
        "<failure/></testcase></testsuites>"
    )
    check = _check(
        _command(cwd, log, "full", 1, report),
        report_path="report.xml",
        rerun_command=_rerun(cwd, log, "pass"),
    )
    result = project_checks.run_one(check, cwd)
    assert result["failed_tests"] == ["pkg.test_same.TestA::test_same"]
    assert result["test_files"] == {}
    project_checks.confirm_failure(check, cwd, result, None, changed=["pkg/test_same.py"])
    assert result["touched_tests"] == ["pkg.test_same.TestA::test_same"]
    assert result["compared_tests"] == ["pkg.test_same.TestA::test_same"]
    assert "flaky" not in result and project_checks.failed(result)


def test_touched_tests_on_a_recorded_xunit2_report_counts_every_failure(tmp_path):
    report = project_checks.parse_report(_recorded("pytest_xunit2.xml", tmp_path), tmp_path)
    assert report is not None and report.files == {}
    touched = project_checks.touched_tests(report.failing, ["pkg/test_same.py"], report.files)
    assert touched == report.failing and len(touched) == 3
    # An id is never read as a path (FR-7): with no file recorded, every failure is touched.
    assert project_checks.touched_tests(["a/t.py::x", "b/t.py::y"], ["a/t.py"]) == [
        "a/t.py::x",
        "b/t.py::y",
    ]


@pytest.mark.asyncio
def test_an_id_the_shell_cannot_carry_re_runs_the_whole_check():
    check = _check("x", report_path="r.xml", rerun_command="run {tests}")
    assert project_checks.rerun_command(check, ["a::b\nc"]) is None
    assert project_checks.rerun_command(check, ["a::b", "c::d"]) is not None


# --- FR-6: narrowing a landing batch ----------------------------------------------------------------

#: The project's re-run wrapper for pytest: `classname::name` to a node id, then pytest, logged.
PYTEST_RERUN = """import json, subprocess, sys
log, ids = sys.argv[1], sys.argv[2:]
with open(log, "a", encoding="utf-8") as out:
    out.write(json.dumps({"as": "rerun", "args": ids}) + "\\n")
nodes = [i.split("::", 1)[0].replace(".", "/") + ".py::" + i.split("::", 1)[1] for i in ids]
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-p", "no:randomly", "--junitxml=report.xml", *nodes]))
"""
SUITE = (
    "import os\n\n\n"
    "def test_ok():\n    assert True\n\n\n"
    "def test_no_marker():\n    assert not os.path.exists('broken.txt'), 'broken'\n"
)
NO_MARKER = "test_suite::test_no_marker"


@pytest.fixture
def _a_long_gather_window(monkeypatch):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


@pytest.mark.asyncio
async def test_a_batch_is_narrowed_through_the_rerun_command(
    app, auth_headers, tmp_path, tmp_path_factory, _a_long_gather_window
):
    """narrowing-uses-command: the same culprit as the pytest rewrite finds
    (`test_a_failing_batch_is_narrowed`), each probe the re-run command with only the failing id."""
    log = tmp_path_factory.mktemp("log") / "ran.log"
    make_repo(tmp_path)
    for name, content in {
        "test_suite.py": SUITE,
        "rerun.py": PYTEST_RERUN,
        ".gitignore": "report.xml\n",
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
        git(tmp_path, "add", name)
    git(tmp_path, "commit", "-q", "-m", "the suite")
    await _project()
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = [
            {
                "name": "pytest",
                "command": f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly "
                "--junitxml=report.xml",
                "timeout_seconds": 120,
                "report_path": "report.xml",
                "rerun_command": f'{PY} rerun.py "{log}" {{tests}}',
            }
        ]
        await session.commit()
    ids, _ = await _tasks(
        tmp_path,
        [({"one.py": "x = 1\n"}, None), ({"broken.txt": "this breaks the suite\n"}, None)],
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == ["approved", "revision_needed"]
    narrowing = (await _batches())[0].narrowing
    assert narrowing, "the failing batch was narrowed"
    assert all(step["tests"] == [NO_MARKER] for step in narrowing), narrowing
    assert all("rerun.py" in step["command"] for step in narrowing), narrowing
    assert all(
        f'"{NO_MARKER}"' in step["command"] or NO_MARKER in step["command"] for step in narrowing
    )
    calls = [c["args"] for c in _calls(log)]
    assert calls and all(args == [NO_MARKER] for args in calls), calls
