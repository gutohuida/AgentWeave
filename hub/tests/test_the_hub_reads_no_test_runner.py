"""The Hub judges a check by its settings, exit code, time limit and report, and knows no test runner
(`checks-report-which-tests-failed-in-any-language`, FR-7, criterion no-parser-left).

Until that change the Hub read pytest's console summary for the failing tests and rewrote a check's
command into a serial pytest run of them: a hard-coded list of pytest options, xdist's worker and
distribution options, a refusal of shell characters. A JavaScript or Go project got a weaker gate,
and every new pytest ending needed a rule. This scans every module under `hub/hub` and fails, naming
the file and line, if any of that comes back.

Not banned: pytest named in prose, or a check environment's `PYTEST_XDIST_AUTO_NUM_WORKERS`, which
sizes `-n auto` to the machine and judges nothing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

HUB_PACKAGE = Path(__file__).resolve().parents[1] / "hub"

#: The retired names: the parsers, the option lists, the command rewrite.
RETIRED_NAMES = re.compile(
    r"\b(?:narrowed_command|failed_test_ids|summary_counts|def named_failures|def test_file|"
    r"_node_key|MAX_RERUN_TESTS|_SUMMARY_LINE_RE|_XDIST_GROUP_RE|_SAFE_NODE_ID_RE|_COUNT_RE|"
    r"_FINAL_LINE_RE|_NAMED_FAILURE_RE|_FAILURES_HEADER_RE|_VALUE_OPTIONS|_SELECTION_OPTIONS|"
    r"_PYTEST_RE|_WORKER_OPTIONS|_DISTRIBUTION_OPTIONS|_SHORT_WORKERS_RE)\b"
)
#: What any parser of pytest's console or rewrite of its command has to write, whatever its names.
RUNNER_KNOWLEDGE = [
    # The short summary's line prefix and section headers, in a regular expression.
    re.compile(r"\(\?:FAILED\|ERROR\)|\(FAILED\|ERROR\)|\^?FAILED \(|FAILURES\|ERRORS"),
    re.compile(r"short test summary"),
    # pytest's final count line: `3 failed, 10 passed ... in 1.2s`.
    re.compile(r"passed\|failed|failed\|passed"),
    # xdist's worker and distribution options, and pytest's own selection options, as strings. A
    # bare "-n" is not one: `nice -n` gives a check's processes way (`_spawn_arguments`).
    re.compile(r"""["'](?:--numprocesses|--dist|--maxprocesses|--tx)["']"""),
    re.compile(r"""["'](?:--lf|--last-failed|--ff|--failed-first|--sw|--stepwise)["']"""),
    re.compile(r"""["']-n 0["']|["']-n["'],\s*["']0["']"""),
    # A regular expression that finds pytest in a command, to rewrite it.
    re.compile(r"py\\?\.test\|pytest"),
]


def findings(text: str, name: str) -> List[str]:
    """Each line of *text* (module *name*) that holds a retired name or runner knowledge."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if RETIRED_NAMES.search(line) or any(p.search(line) for p in RUNNER_KNOWLEDGE):
            found.append(f"{name}:{number}: {line.strip()}")
    return found


def test_no_module_of_the_hub_parses_a_runners_output_or_rewrites_a_command():
    modules = sorted(HUB_PACKAGE.rglob("*.py"))
    assert len(modules) > 100, f"the scan reached the Hub package: {HUB_PACKAGE}"
    found: List[str] = []
    for module in modules:
        name = module.relative_to(HUB_PACKAGE.parent).as_posix()
        found += findings(module.read_text(encoding="utf-8"), name)
    assert not found, (
        "the Hub judges a check only by its settings, exit code, time limit and report (FR-7); "
        "a runner's failing tests come from the check's JUnit report and a re-run goes through the "
        "check's own re-run command:\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    "line",
    [
        # Lines of the code this change removed (`hub/hub/project_checks.py` before it).
        '_SUMMARY_LINE_RE = re.compile(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$", re.MULTILINE)',
        '_FAILURES_HEADER_RE = re.compile(r"^=+ (?:FAILURES|ERRORS) =+\\s*$", re.MULTILINE)',
        '_COUNT_RE = re.compile(r"\\b(\\d+) (passed|failed|errors?|skipped)\\b")',
        '_WORKER_OPTIONS = frozenset({"-n", "--numprocesses"})',
        '    {"--lf", "--last-failed", "--ff", "--failed-first", "--sw", "--stepwise"}',
        '_PYTEST_RE = re.compile(r"(?:^|(?<=\\s))(?:\\S*[\\\\/])?(?:py\\.test|pytest)(?:\\.exe)?")',
        "        kept[:0] = ['-n', '0']",
        "def narrowed_command(command: str, node_ids: Sequence[str]) -> Optional[str]:",
        "def named_failures(output: str) -> List[str]:",
        # The same knowledge under a new name.
        'RERUN_SERIAL = ["-n", "0"]',
        "FAILED_LINE = re.compile(r'^FAILED (\\S+)')",
        "BANNER = 'short test summary info'",
    ],
)
def test_the_scan_finds_what_was_removed(line):
    assert findings(line, "sample.py"), line


@pytest.mark.parametrize(
    "line",
    [
        'result["named_failures"] = report.failing',
        "return bool(result.get('timed_out')) and not result.get('named_failures')",
        'XDIST_AUTO_WORKERS_VARIABLE = "PYTEST_XDIST_AUTO_NUM_WORKERS"',
        "# `-n auto` sizes pytest-xdist to every CPU",
        "command: The command you ran (`npm test`, `pytest -k x`).",
        "_TEXT_TOOL_VALUE_OPTIONS = {",
    ],
)
def test_the_scan_leaves_what_judges_nothing(line):
    assert not findings(line, "sample.py"), line
