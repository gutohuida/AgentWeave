"""The sweep check: run the Hub tests that scan the repository or the UI source, and only those.

    py -3.11 scripts/checks/sweep_check.py [--report PATH] [pytest arguments...]
    py -3.11 scripts/checks/sweep_check.py [--report PATH] --rerun ID [ID ...]
    py -3.11 scripts/checks/sweep_check.py [--report PATH] --changed-files LIST [pytest args...]

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

`--changed-files LIST` (one repo-relative path per line: the file the project's `{changed_files}`
placeholder names) runs only the sweep tests those paths can affect (`affected_tests`, AW-164).
Every sweep test imports the Hub and most scan `hub/hub`, so a Hub source change runs all of them,
while a change to the UI source, the docs or the CLI runs the few that read it, or none. Shared
infrastructure, and any path this script does not know, runs the full sweep. With no test to run
it writes an empty report and passes.
"""

from __future__ import annotations

import ast
import os
import re
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


# --- the sweep tests a change affects (AW-164) ---------------------------------------------------

#: Paths every test depends on, so a change to one runs the full sweep: the packages' and pytest's
#: configuration, the database's migration config, any conftest, any fixture, and this check's own
#: scripts and list.
SHARED_FILES = {
    "pyproject.toml",
    "hub/pyproject.toml",
    "constraints-dev.txt",
    "hub/alembic.ini",
    "hub/tests/__init__.py",
}
SHARED_PREFIXES = ("scripts/checks/",)
SHARED = re.compile(r"(^|/)(conftest\.py$|fixtures/)")

#: Every sweep test imports the Hub package and almost all scan it, so a change anywhere in it
#: affects each one -- except its built UI bundle, which no sweep test reads.
HUB_PACKAGE = "hub/hub/"
HUB_BUNDLE = "hub/hub/static/"

#: What each sweep test reads beyond the Hub package, read from its source on 2026-11-17. A sweep
#: test missing here has an unknown mapping, so any change runs the full sweep.
SCOPES: dict[str, tuple[str, ...]] = {
    "hub/tests/test_a_refused_review_leaves_nothing_behind.py": (),
    "hub/tests/test_agent_facing_text.py": (),
    "hub/tests/test_an_event_is_announced_after_commit.py": (),
    "hub/tests/test_charters_api.py": (),
    "hub/tests/test_conversation_contract.py": (),
    "hub/tests/test_conversation_task_binding.py": (),
    "hub/tests/test_database_backups.py": ("src/", "scripts/"),
    "hub/tests/test_every_send_back_says_why.py": ("hub/ui/src/__tests__/",),
    "hub/tests/test_firing_decision_is_shared.py": (),
    "hub/tests/test_manager_jobs.py": ("hub/ui/src/__tests__/",),
    "hub/tests/test_no_console_flash.py": (),
    "hub/tests/test_no_runner_literals.py": (),
    "hub/tests/test_rebinding_an_agents_runner_starts_clean.py": (),
    "hub/tests/test_spec_journey_words.py": (),
    "hub/tests/test_spec_storage_seam.py": (),
    "hub/tests/test_surface_ceilings.py": ("hub/ui/src/", "scripts/drive/"),
    "hub/tests/test_task_attribution.py": (),
    "hub/tests/test_task_lifecycle_bands.py": (),
    "hub/tests/test_task_transitions.py": (),
    "hub/tests/test_task_workspace_scheme.py": ("src/",),
    "hub/tests/test_test_git_shares_one_timeout.py": ("hub/tests/",),
    "hub/tests/test_the_hub_reads_no_test_runner.py": (),
    "hub/tests/test_the_old_check_rules_stay_retired.py": (),
    "hub/tests/test_the_sweep_set_is_current.py": ("hub/tests/",),
    "hub/tests/test_ui_vocabulary.py": ("hub/ui/src/", "scripts/checks/ui_vocabulary"),
    "hub/tests/test_vault_archive.py": ("hub/ui/src/api/", "scripts/drive/"),
    "hub/tests/test_workspace_writes.py": ("hub/ui/src/components/agents/",),
    "hub/tests/test_write_paths_on_run_events.py": (),
}

#: Where a change is known to reach no sweep test beyond what `SCOPES` names; a path outside these
#: (and outside `KNOWN_FILES`) is unknown and runs the full sweep.
KNOWN_PREFIXES = (
    "hub/hub/",
    "hub/tests/",
    "hub/ui/",
    "tests/",
    "src/",
    "scripts/",
    "docs/",
    "spec/",
    "openspec/",
    "brand/",
    "testbed/",
    ".claude/",
)
KNOWN_FILES = {"README.md", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md", "mkdocs.yml"}


HUB_TESTS = "hub/tests/"


def _imported_test_modules(path: Path, tests_root: Path) -> Optional[set[str]]:
    """The `hub/tests` modules *path* imports, as repo-relative paths that exist, or `None` when
    it does not parse. Relative imports (`from .x import`, `from . import x`, from a subpackage
    too) and absolute ones (`hub.tests.x`) are read, wherever in the file they are."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, ValueError):
        return None
    package = list(path.relative_to(tests_root).parent.parts)
    names: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module.split(".") if node.module else []
            if node.level:
                if node.level - 1 > len(package):
                    continue
                module = package[: len(package) - (node.level - 1)] + module
            elif module[:2] == ["hub", "tests"]:
                module = module[2:]
            else:
                continue
            names.append(module)
            names.extend([*module, alias.name] for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[:2] == ["hub", "tests"]:
                    names.append(parts[2:])
    found: set[str] = set()
    for parts in names:
        if not parts:
            continue
        for candidate in (
            tests_root.joinpath(*parts[:-1], parts[-1] + ".py"),
            tests_root.joinpath(*parts, "__init__.py"),
        ):
            if candidate.is_file():
                found.add(candidate.relative_to(tests_root.parents[1]).as_posix())
    return found


def importers_of_tests(repo_root: Path = REPO_ROOT) -> Optional[dict[str, set[str]]]:
    """For each `hub/tests` module, the `hub/tests` files that import it, directly or through
    another; `None` when some file does not parse, so its imports are unknown."""
    tests_root = repo_root / "hub" / "tests"
    imports: dict[str, set[str]] = {}
    for path in tests_root.rglob("*.py"):
        if "fixtures" in path.relative_to(tests_root).parts:
            continue
        found = _imported_test_modules(path, tests_root)
        if found is None:
            return None
        imports[path.relative_to(repo_root).as_posix()] = found
    direct: dict[str, set[str]] = {}
    for importer, modules in imports.items():
        for module in modules:
            direct.setdefault(module, set()).add(importer)
    closure: dict[str, set[str]] = {}
    for module in direct:
        seen: set[str] = set()
        stack = [module]
        while stack:
            for importer in direct.get(stack.pop(), ()):
                if importer not in seen:
                    seen.add(importer)
                    stack.append(importer)
        closure[module] = seen
    return closure


def affected_tests(
    changed: list[str],
    sweep: list[str],
    importers: Optional[dict[str, set[str]]] = None,
) -> Optional[list[str]]:
    """The tests of *sweep* the *changed* paths can affect, in *sweep*'s order, or `None` for the
    full sweep: a shared path, a path outside the known tree, a sweep test with no scope, or a
    changed `hub/tests` module whose importers cannot be read.

    A changed `hub/tests` module also runs every sweep test that imports it, directly or through
    another module (*importers*, from `importers_of_tests` when not given): sweep tests reuse helpers
    and other tests' fixtures, so a change to one of those can break them."""
    if any(test not in SCOPES for test in sweep):
        return None
    selected: set[str] = set()
    for path in (p.strip().replace("\\", "/") for p in changed if p.strip()):
        if path in SHARED_FILES or path.startswith(SHARED_PREFIXES) or SHARED.search(path):
            return None
        if path not in KNOWN_FILES and not path.startswith(KNOWN_PREFIXES):
            return None
        if path.startswith(HUB_PACKAGE) and not path.startswith(HUB_BUNDLE):
            return list(sweep)
        selected.update(t for t in sweep if t == path or path.startswith(SCOPES[t]))
        if path.startswith(HUB_TESTS) and path.endswith(".py"):
            if importers is None:
                importers = importers_of_tests()
                if importers is None:
                    return None
            selected.update(t for t in sweep if t in importers.get(path, ()))
    return [test for test in sweep if test in selected]


def pytest_args(argv: list[str]) -> Optional[list[str]]:
    """What pytest is run with for *argv*, or `None` where the change affects no sweep test;
    `junit_rerun.UsageError` when *argv* is wrong."""
    changed_path, argv = junit_rerun.extract_changed_files(argv)
    report, rerun_ids, args = junit_rerun.parse_options(argv)
    if rerun_ids is not None:
        return junit_rerun.rerun_args(rerun_ids, report, REPO_ROOT)
    report_args = junit_rerun.report_args(report) if report else []
    tests = sweep_files()
    if changed_path is not None:
        try:
            listing = Path(changed_path).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise junit_rerun.UsageError(f"cannot read --changed-files {changed_path}: {exc}")
        affected = affected_tests(listing, tests)
        if affected is None:
            print("sweep: the change touches a shared or unknown path; running the full sweep")
        elif not affected:
            print("sweep: no sweep test relates to the change; running no tests")
            return None
        else:
            print(f"sweep: running {len(affected)} of {len(tests)} sweep test files")
            tests = affected
    return [*tests, *(args or DEFAULT_ARGS), *report_args]


def _run_pytest(args: list[str]) -> int:
    import pytest

    return int(pytest.main(args))


def main(argv: list[str], run_pytest: Optional[Callable[[list[str]], int]] = None) -> int:
    os.chdir(REPO_ROOT)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        args = pytest_args(argv)
        report = junit_rerun.parse_options(junit_rerun.extract_changed_files(argv)[1])[0]
    except junit_rerun.UsageError as exc:
        print(f"sweep: {exc}", flush=True)
        return 4  # pytest's usage error
    if args is None:
        if report:
            junit_rerun.write_empty_report(report)
        return 0
    code = (run_pytest or _run_pytest)(args)
    if report:
        junit_rerun.tidy_report(Path(report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
