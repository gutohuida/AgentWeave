"""The gate for `constraints-dev.txt`.

The file pins the versions CI resolves so a local install lands on the same ones. Its whole
value is that things *install through it*: a constraints file nobody passes with `-c` is
decoration, and the drift it exists to stop -- starlette 1.6.0 on CI against 0.52.1 here, and a
test reading `create_app().routes` seeing 7 paths one side and 161 the other -- returns
silently, with the file still sitting in the tree looking like protection.

So most of what is asserted here is not about the pins. It is about the four call sites: the
two CI jobs that build a test environment, the two `Makefile` install targets, and CLAUDE.md's
documented Development Setup. Drop `-c` from any of them and this file goes red.

Two invariants guard the other condition of the verdict (`spec-queue/DECISIONS.md`, `DAY-1`) --
that the constraints file is development-only and **not** a second source of truth for what the
Hub supports: the published ranges must still be loose, and every pin here must sit inside
them. A pin outside the published range would mean CI tests a version the package forbids.

The pinned *numbers* are deliberately not asserted against anything. They are read from a green
CI run and bumped by hand when upstream moves; a test asserting 1.6.0 would have to be edited
in the same commit as the file, which makes it a copy rather than a check.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS = REPO_ROOT / "constraints-dev.txt"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DRIFT = REPO_ROOT / ".github" / "workflows" / "upstream-drift.yml"
MAKEFILE = REPO_ROOT / "Makefile"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# A `pip install` that installs something from this checkout. `pip install build`,
# `pip install --upgrade pip` and `pip install twine` are tool installs, not test
# environments, and are none of this file's business.
EDITABLE_INSTALL = re.compile(r"pip install\b[^\n]*\s-e\s")


def _pins(text: str) -> dict[str, str]:
    """`name -> version` for every `name==version` line, comments and blanks skipped."""
    pins: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        assert sep, f"{line!r} is not a `name==version` pin"
        pins[name.strip().lower()] = version.strip()
    return pins


def _version(value: str) -> tuple[int, ...]:
    """Dotted integers only -- enough for the pins this file is allowed to carry."""
    return tuple(int(part) for part in value.split("."))


def _editable_installs(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if EDITABLE_INSTALL.search(line)]


class TestTheFileItself:
    def test_it_exists_and_every_line_is_a_pin_or_a_comment(self):
        pins = _pins(CONSTRAINTS.read_text(encoding="utf-8"))
        assert pins, "the constraints file pins nothing"

    def test_it_pins_the_two_packages_the_drift_was_measured_on(self):
        pins = _pins(CONSTRAINTS.read_text(encoding="utf-8"))
        assert "starlette" in pins
        assert "fastapi" in pins

    def test_it_says_it_is_development_only(self):
        # The verdict's first condition is a documentation condition: whoever reads this file
        # must not take it for a statement of what the Hub supports.
        header = CONSTRAINTS.read_text(encoding="utf-8").lower()
        assert "not a statement of what the hub supports" in header
        assert "not a second source of truth" in header

    def test_it_is_not_packaged(self):
        # A constraints file shipped in the sdist would look like a user-facing pin.
        manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        assert "constraints-dev.txt" not in manifest


class TestItDoesNotNarrowThePublishedRanges:
    """`hub/pyproject.toml` stays the single source of truth, and stays loose."""

    def test_the_published_ranges_are_still_the_loose_ones(self):
        hub_pyproject = (REPO_ROOT / "hub" / "pyproject.toml").read_text(encoding="utf-8")
        assert '"starlette<2.0"' in hub_pyproject
        assert '"fastapi>=0.110"' in hub_pyproject

    def test_every_pin_sits_inside_the_published_range(self):
        # Not a formatting check: a pin outside the declared range would have CI resolving a
        # version the package itself refuses, so the suite would be testing an install a user
        # can never get.
        pins = _pins(CONSTRAINTS.read_text(encoding="utf-8"))
        assert _version(pins["starlette"]) < _version("2.0")
        assert _version(pins["fastapi"]) >= _version("0.110")


class TestEverythingThatBuildsATestEnvironmentInstallsThroughIt:
    def test_every_editable_install_in_ci_passes_it(self):
        installs = _editable_installs(CI.read_text(encoding="utf-8"))
        # Three today: `pip install -e ./hub` and `-e ".[dev]"` in `test`, and `-e .` in
        # `hub-test`. If a fourth appears, it is caught here rather than resolving fresh.
        assert len(installs) >= 3
        for line in installs:
            assert re.search(r"-c\s+\S*constraints-dev\.txt", line), line

    def test_the_hub_job_reaches_the_repo_root_for_it(self):
        # `working-directory: hub` is that job's default, so a bare `constraints-dev.txt`
        # there is a path that does not exist and pip fails the whole job.
        text = CI.read_text(encoding="utf-8")
        assert "pip install -c ../constraints-dev.txt" in text
        assert (REPO_ROOT / "hub" / ".." / "constraints-dev.txt").resolve() == CONSTRAINTS

    def test_the_makefile_install_targets_pass_it(self):
        installs = _editable_installs(MAKEFILE.read_text(encoding="utf-8"))
        assert len(installs) >= 2
        for line in installs:
            assert "-c constraints-dev.txt" in line, line

    def test_the_documented_local_install_passes_it(self):
        # CLAUDE.md's Development Setup is the other half of the verdict's second condition:
        # if the documented command resolves fresh, local and CI drift apart again.
        text = CLAUDE_MD.read_text(encoding="utf-8")
        start = text.index("### Development Setup")
        block = text[start : text.index("```", text.index("```", start) + 3)]
        installs = _editable_installs(block)
        assert installs, "Development Setup documents no editable install"
        for line in installs:
            assert "-c constraints-dev.txt" in line, line


class TestTheDriftAlarmTheConstraintsSilenced:
    """F308: pinning CI's resolution bought agreement by spending the drift alarm.

    Every job above installs through the constraints file, so no test job resolves the loose
    range `pyproject.toml` still advertises. The 2026-09-09 starlette break surfaced *because*
    CI resolved fresh. `upstream-drift.yml` is what resolves fresh now -- weekly, and named
    something other than `CI` so the merge gate (`.claude/loops/day-window.md`) never waits on
    it. These assertions exist because the obvious "fix" to that workflow is to add `-c`, which
    would delete the alarm again and leave a green file behind looking like protection.
    """

    def test_it_exists_and_runs_on_a_schedule(self):
        assert DRIFT.exists(), f"{DRIFT.name} is the replacement F308 asked for; it is missing"
        text = DRIFT.read_text(encoding="utf-8")
        assert "schedule:" in text and "cron:" in text, "an alarm nobody triggers is not an alarm"

    def test_it_installs_without_the_constraints_file(self):
        installs = _editable_installs(DRIFT.read_text(encoding="utf-8"))
        assert installs, "it must install this checkout, or it measures nothing"
        for line in installs:
            assert "constraints-dev.txt" not in line, (
                f"{line.strip()!r} constrains the one job that exists to resolve fresh. "
                f"That is F308's alarm, not a missing `-c`."
            )

    def test_it_runs_the_suites_rather_than_only_importing(self):
        # An install/import check is what `hub-image.yml` already gives, and F308 measured that
        # as catching nothing in the class the starlette defect belongs to.
        text = DRIFT.read_text(encoding="utf-8")
        assert "pytest tests/ -q --timeout" in text and text.count("pytest tests/") >= 2

    def test_it_is_not_named_ci_so_the_merge_gate_ignores_it(self):
        # The gate requires a success for the workflow named `CI` at HEAD's sha. A second
        # workflow called `CI` would make a weekly upstream break block every merge.
        name = re.search(r"^name:\s*(.+)$", DRIFT.read_text(encoding="utf-8"), re.M)
        assert name and name.group(1).strip().lower() != "ci", name
