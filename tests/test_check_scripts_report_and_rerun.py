"""This repository's checks write a report and re-run named tests serially.

Spec `checks-report-which-tests-failed-in-any-language`, FR-9: `scripts/checks/hub_suite.py` and
`sweep_check.py` take `--report PATH` (a JUnit XML report, xunit1, ids rooted at the current
directory) and `--rerun ID...`, which turns each `classname::name` id back into a pytest node id
(`scripts/checks/junit_rerun.py`) and runs them with `-n 0`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS = REPO_ROOT / "scripts" / "checks"


def _load(name: str):
    """Import a script of `scripts/checks/` by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location(name, CHECKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


junit_rerun = _load("junit_rerun")
hub_suite = _load("hub_suite")
sweep_check = _load("sweep_check")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "hub" / "tests").mkdir(parents=True)
    (tmp_path / "hub" / "tests" / "test_x.py").write_text("", encoding="utf-8")
    return tmp_path


# --- the id translation ------------------------------------------------------------------------


def test_a_module_level_test(tree: Path) -> None:
    assert junit_rerun.node_id("hub.tests.test_x::test_a", tree) == "hub/tests/test_x.py::test_a"


def test_a_test_in_a_class(tree: Path) -> None:
    assert (
        junit_rerun.node_id("hub.tests.test_x.TestY::test_a", tree)
        == "hub/tests/test_x.py::TestY::test_a"
    )


def test_a_parametrized_test_in_nested_classes(tree: Path) -> None:
    assert (
        junit_rerun.node_id("hub.tests.test_x.TestY.TestZ::test_a[1-a.b::c]", tree)
        == "hub/tests/test_x.py::TestY::TestZ::test_a[1-a.b::c]"
    )


def test_the_longest_prefix_that_is_a_file_is_the_module(tree: Path) -> None:
    # `hub/tests.py` exists too: the longer prefix `hub/tests/test_x.py` is the module.
    (tree / "hub" / "tests.py").write_text("", encoding="utf-8")
    assert (
        junit_rerun.node_id("hub.tests.test_x.TestY::test_a", tree)
        == "hub/tests/test_x.py::TestY::test_a"
    )


@pytest.mark.parametrize(
    "test_id", ["hub.tests.test_missing::test_a", "no-separator", "::test_a", "hub.tests.test_x::"]
)
def test_an_id_naming_no_test_file_is_refused(tree: Path, test_id: str) -> None:
    assert junit_rerun.node_id(test_id, tree) is None
    with pytest.raises(junit_rerun.UsageError, match="no test file"):
        junit_rerun.node_ids(["hub.tests.test_x::test_a", test_id], tree)


# --- the options -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], (None, None, [])),
        (["hub/tests", "-x"], (None, None, ["hub/tests", "-x"])),
        (["--report", "r.xml"], ("r.xml", None, [])),
        (["--report=r.xml", "-x"], ("r.xml", None, ["-x"])),
        (["--report", "r.xml", "--rerun", "a::b", "c.D::e"], ("r.xml", ["a::b", "c.D::e"], [])),
        (["--rerun", "a::b"], (None, ["a::b"], [])),
    ],
)
def test_options(argv: list, expected: tuple) -> None:
    assert junit_rerun.parse_options(argv) == expected


@pytest.mark.parametrize(
    "argv", [["--report"], ["--report="], ["--rerun"], ["-x", "--rerun", "a::b"]]
)
def test_wrong_options_are_refused(argv: list) -> None:
    with pytest.raises(junit_rerun.UsageError):
        junit_rerun.parse_options(argv)


def test_a_rerun_is_serial_and_writes_the_report(tree: Path) -> None:
    args = junit_rerun.rerun_args(["hub.tests.test_x.TestY::test_a"], "r.xml", tree)
    assert args[args.index("-n") + 1] == "0"
    assert "--junitxml=r.xml" in args and "junit_family=xunit1" in args and "--rootdir=." in args
    assert args[-1] == "hub/tests/test_x.py::TestY::test_a"


def test_tidy_report_removes_only_the_testcases_own_file_group(tmp_path: Path) -> None:
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="hub.tests.test_x.TestY" name="test_a@hub/tests/test_x.py"'
        r' file="hub\tests\test_x.py" />'
        '<testcase classname="hub.tests.test_x" name="test_b[a@b]" file="hub/tests/test_x.py" />'
        '<testcase classname="hub.tests.test_x" name="test_c@other" file="hub/tests/test_x.py" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    junit_rerun.tidy_report(report)
    names = [case.get("name") for case in ElementTree.parse(report).getroot().iter("testcase")]
    assert names == ["test_a", "test_b[a@b]", "test_c@other"]


def test_tidy_report_leaves_a_missing_or_unreadable_report(tmp_path: Path) -> None:
    junit_rerun.tidy_report(tmp_path / "missing.xml")
    (tmp_path / "bad.xml").write_text("not xml", encoding="utf-8")
    junit_rerun.tidy_report(tmp_path / "bad.xml")
    assert (tmp_path / "bad.xml").read_text(encoding="utf-8") == "not xml"


# --- hub_suite.py ------------------------------------------------------------------------------


class _NoLock:
    def acquire(self) -> float:
        raise AssertionError("a re-run does not wait for the full suite's lock")


def test_hub_suite_rerun_runs_the_ids_serially_without_the_lock(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tree)
    seen: list = []
    code = hub_suite.main(
        ["--report", "r.xml", "--rerun", "hub.tests.test_x.TestY::test_a"],
        run_pytest=lambda args: seen.append(args) or 1,
        lock=_NoLock(),
    )
    assert code == 1
    assert seen == [junit_rerun.rerun_args(["hub.tests.test_x.TestY::test_a"], "r.xml", tree)]


def test_hub_suite_refuses_an_unknown_id(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tree)
    code = hub_suite.main(["--rerun", "hub.tests.gone::test_a"], run_pytest=lambda a: 0)
    assert code == 4


def test_hub_suite_report_keeps_the_default_run(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AW_HUB_SUITE_LOCK_DIR", str(tmp_path))
    seen: list = []
    hub_suite.main(
        ["--report", "r.xml"],
        run_pytest=lambda args: seen.append(args) or 0,
        read_idle=lambda: 1.0,
        logical_cpus=4,
    )
    assert seen == [["-n", "4", *hub_suite.DEFAULT_ARGS, *junit_rerun.report_args("r.xml")]]


# --- sweep_check.py ----------------------------------------------------------------------------


def test_sweep_report_keeps_the_sweep_set() -> None:
    args = sweep_check.pytest_args(["--report", "r.xml"])
    assert args == [
        *sweep_check.sweep_files(),
        *sweep_check.DEFAULT_ARGS,
        *junit_rerun.report_args("r.xml"),
    ]


def test_sweep_rerun_runs_only_the_ids_serially() -> None:
    test_id = "tests.test_check_scripts_report_and_rerun::test_options[argv0-expected0]"
    args = sweep_check.pytest_args(["--report", "r.xml", "--rerun", test_id])
    assert args[args.index("-n") + 1] == "0"
    assert args[-1] == "tests/test_check_scripts_report_and_rerun.py::test_options[argv0-expected0]"
    assert not set(sweep_check.sweep_files()) & set(args)


# --- for real: a report's ids re-run as themselves ----------------------------------------------


FAILING = """import pytest


def test_module_level():
    assert False


class TestOuter:
    def test_in_class(self):
        assert 1 == 2

    def test_passes(self):
        pass

    @pytest.mark.parametrize("x", [1, "a b"])
    def test_param(self, x):
        assert x == 3
"""


#: As `hub/tests/conftest.py` does: every test grouped by its file for `--dist loadgroup`, which
#: makes xdist append `@<file>` to each node id.
GROUPED = """import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker(pytest.mark.xdist_group(name=item.nodeid.split("::")[0]))
"""


def _failing_ids(report: Path) -> dict:
    """Each failing testcase's `classname::name` to its file, as the Hub reads them."""
    root = ElementTree.parse(report).getroot()
    return {
        f"{case.get('classname')}::{case.get('name')}": case.get("file").replace("\\", "/")
        for case in root.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    }


def test_a_reports_failing_ids_rerun_alone_and_name_themselves_again(tree: Path) -> None:
    """In parallel under loadgroup, as the hub-tests check runs, then re-run serially: the id is
    the same in both reports, with no xdist group in it."""
    (tree / "hub" / "tests" / "test_x.py").write_text(FAILING, encoding="utf-8")
    (tree / "hub" / "tests" / "conftest.py").write_text(GROUPED, encoding="utf-8")
    env = {**os.environ, "AW_HUB_SUITE_LOCK_DIR": str(tree)}
    script = str(CHECKS / "hub_suite.py")
    report = tree / "out" / "report.xml"
    full = subprocess.run(
        [
            sys.executable,
            script,
            "--report",
            "out/report.xml",
            "hub/tests",
            "-n",
            "2",
            "--dist",
            "loadgroup",
        ],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
    )
    assert full.returncode == 1, full.stdout[-2000:]
    failing = _failing_ids(report)
    assert failing == {
        "hub.tests.test_x::test_module_level": "hub/tests/test_x.py",
        "hub.tests.test_x.TestOuter::test_in_class": "hub/tests/test_x.py",
        "hub.tests.test_x.TestOuter::test_param[1]": "hub/tests/test_x.py",
        "hub.tests.test_x.TestOuter::test_param[a b]": "hub/tests/test_x.py",
    }
    report.unlink()
    rerun = subprocess.run(
        [
            sys.executable,
            script,
            "--report",
            "out/report.xml",
            "--rerun",
            "hub.tests.test_x.TestOuter::test_in_class",
        ],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
    )
    assert rerun.returncode == 1, rerun.stdout[-2000:]
    assert len(list(ElementTree.parse(report).getroot().iter("testcase"))) == 1
    assert _failing_ids(report) == {
        "hub.tests.test_x.TestOuter::test_in_class": "hub/tests/test_x.py"
    }
    assert "without the suite lock" in rerun.stdout
