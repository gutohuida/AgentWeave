"""The sweep check: run the Hub tests that scan the repository or the UI source, and only those.

    py -3.11 scripts/checks/sweep_check.py [--report PATH] [pytest arguments...]
    py -3.11 scripts/checks/sweep_check.py [--report PATH] --rerun ID [ID ...]

Spec `agentweave-s-checks-fit-a-busy-machine`, FR-7. The files are the ones
`scripts/checks/sweep_tests.txt` names (FR-5), the currency test among them (FR-6), so a missing
entry fails this check as well. It finishes in well under two minutes, so a failure in a
repo-wide guardrail test is reported soon after a task completes instead of when the full suite
ends. It is not the full suite and takes no turn on `hub_suite.py`'s lock.

With no arguments it runs `-q -p no:cacheprovider --timeout=600 -n <workers> --dist loadgroup`,
where workers is 8 or the logical CPU count if smaller (measured 2026-11-04 on 20 logical CPUs,
idle, pytest's own time: 1 worker 544 s, 4 workers 123 s, 8 workers 71-74 s, 12 workers 78 s,
20 workers 87 s).
Arguments given replace those. Its exit code is pytest's.

`--report PATH` writes the JUnit XML report the Hub reads the failing tests from, and `--rerun`
runs only the given `classname::name` ids, serially (spec
`checks-report-which-tests-failed-in-any-language`, FR-9; `junit_rerun.py`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import junit_rerun  # noqa: E402 -- beside this script, which is run by path

REPO_ROOT = Path(__file__).resolve().parents[2]
SWEEP_SET = REPO_ROOT / "scripts" / "checks" / "sweep_tests.txt"
WORKERS = min(8, os.cpu_count() or 2)
DEFAULT_ARGS = [
    "-q",
    "-p",
    "no:cacheprovider",
    "--timeout=600",
    "-n",
    str(WORKERS),
    "--dist",
    "loadgroup",
]


def sweep_files(sweep_set: Path = SWEEP_SET) -> list[str]:
    """The repo-relative test files the sweep set names, blank lines and `#` comments skipped."""
    lines = sweep_set.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def pytest_args(argv: list[str]) -> list[str]:
    """What pytest is run with for *argv*; `junit_rerun.UsageError` when *argv* is wrong."""
    report, rerun_ids, args = junit_rerun.parse_options(argv)
    if rerun_ids is not None:
        return junit_rerun.rerun_args(rerun_ids, report, REPO_ROOT)
    report_args = junit_rerun.report_args(report) if report else []
    return [*sweep_files(), *(args or DEFAULT_ARGS), *report_args]


def _run_pytest(args: list[str]) -> int:
    import pytest

    return int(pytest.main(args))


def main(argv: list[str], run_pytest: Optional[Callable[[list[str]], int]] = None) -> int:
    os.chdir(REPO_ROOT)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        args = pytest_args(argv)
    except junit_rerun.UsageError as exc:
        print(f"sweep: {exc}", flush=True)
        return 4  # pytest's usage error
    return (run_pytest or _run_pytest)(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
