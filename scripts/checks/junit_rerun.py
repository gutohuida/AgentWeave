"""The report and re-run options `hub_suite.py` and `sweep_check.py` share.

Spec `checks-report-which-tests-failed-in-any-language`, FR-9. The Hub reads which tests failed
from the JUnit XML report a check writes, and re-runs them through the check's re-run command with
each failing test's id, `classname::name`, as one argument. Both scripts take, before any pytest
argument:

    --report PATH        write the JUnit XML report to PATH (relative to the current directory)
    --rerun ID [ID ...]  run only these `classname::name` ids, serially (`-n 0`)

The report is pytest's xunit1 family, so each testcase also carries its file, and pytest's rootdir
is the current directory, so a classname is the test's path from here with dots
(`hub.tests.test_x.TestY`) and its file is that path (`hub/tests/test_x.py`), which is what the Hub
compares with the files a task changed. Left to itself pytest would take `hub/` as the rootdir of a
Hub test (`hub/pyproject.toml` configures pytest) and write `tests.test_x.TestY`.

An id is turned back into a pytest node id by `node_id`: the longest dotted prefix of the classname
that names a `.py` file under the rootdir is the module, the rest of the classname are classes, and
the name (with any `[parameters]`) is the test.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

#: The pytest options that write the report the Hub reads.
JUNIT_FAMILY = "junit_family=xunit1"
#: How a re-run runs: serially, as `a-red-main-does-not-hold-the-night` FR-2 requires (a timing
#: test passed one parallel re-run and failed the next under load).
RERUN_ARGS = ["-q", "-p", "no:cacheprovider", "--timeout=600", "-n", "0"]


class UsageError(ValueError):
    """The script's own options were given wrongly, or an id names no test file."""


def report_args(report: str) -> List[str]:
    """The pytest arguments that write the report to *report*, ids rooted at the current
    directory."""
    return [f"--junitxml={report}", "-o", JUNIT_FAMILY, "--rootdir=."]


def node_id(test_id: str, root: Path) -> Optional[str]:
    """The pytest node id of *test_id* (`classname::name`) under *root*, or `None` where no prefix
    of its classname is a `.py` file there."""
    classname, sep, name = test_id.partition("::")
    if not sep or not classname or not name:
        return None
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        module = "/".join(parts[:end]) + ".py"
        if (root / module).is_file():
            return "::".join([module, *parts[end:], name])
    return None


def node_ids(test_ids: Sequence[str], root: Path) -> List[str]:
    """The node ids of *test_ids*; `UsageError` naming every id that names no test file."""
    found = [(test, node_id(test, root)) for test in test_ids]
    unknown = [test for test, node in found if node is None]
    if unknown:
        raise UsageError(
            f"no test file under {root} for {', '.join(unknown)} "
            "(expected classname::name, the classname a dotted path to a .py file)"
        )
    return [str(node) for _, node in found]


def parse_options(argv: Sequence[str]) -> Tuple[Optional[str], Optional[List[str]], List[str]]:
    """(report path, re-run ids or `None`, the pytest arguments left) from *argv*.

    `--report` comes first if given; `--rerun` then takes every argument after it as an id."""
    args = list(argv)
    report: Optional[str] = None
    if args and (args[0] == "--report" or args[0].startswith("--report=")):
        if "=" in args[0]:
            report = args.pop(0).split("=", 1)[1]
        else:
            args.pop(0)
            if not args:
                raise UsageError("--report needs a path")
            report = args.pop(0)
        if not report:
            raise UsageError("--report needs a path")
    if args and args[0] == "--rerun":
        ids = args[1:]
        if not ids:
            raise UsageError("--rerun needs at least one classname::name id")
        return report, ids, []
    if "--rerun" in args:
        raise UsageError("--rerun comes before any pytest argument (after --report)")
    return report, None, args


def rerun_args(test_ids: Sequence[str], report: Optional[str], root: Path) -> List[str]:
    """The pytest arguments that run *test_ids* alone, serially, writing *report* if given."""
    return [*RERUN_ARGS, *(report_args(report) if report else []), *node_ids(test_ids, root)]
