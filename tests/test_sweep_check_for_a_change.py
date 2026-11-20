"""`sweep_check.py --changed-files`: only the sweep tests a change affects (AW-164).

The mapping from changed paths to sweep tests, its fallbacks to the full sweep (shared
infrastructure, unknown paths, a sweep test without a scope), and the run it makes: the selected
files with the report, or no run and an empty report.
"""

from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS = REPO_ROOT / "scripts" / "checks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, CHECKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sweep_check = _load("sweep_check")
SWEEP = sweep_check.sweep_files()


def _affected(*paths: str):
    return sweep_check.affected_tests(list(paths), SWEEP)


def test_every_sweep_test_has_a_scope():
    """A sweep test without a scope would make every change run the full sweep."""
    assert set(sweep_check.SCOPES) == set(SWEEP)


def test_a_hub_module_change_runs_every_sweep_test():
    assert _affected("hub/hub/landing_queue.py") == SWEEP


def test_a_ui_source_change_runs_only_the_tests_that_read_the_ui():
    assert _affected("hub/ui/src/components/agents/AgentCard.tsx") == [
        "hub/tests/test_surface_ceilings.py",
        "hub/tests/test_ui_vocabulary.py",
        "hub/tests/test_workspace_writes.py",
    ]
    assert _affected("hub/ui/src/api/vault.ts") == [
        "hub/tests/test_surface_ceilings.py",
        "hub/tests/test_ui_vocabulary.py",
        "hub/tests/test_vault_archive.py",
    ]


def test_a_changed_sweep_test_runs_itself_and_the_tests_that_walk_hub_tests():
    assert _affected("hub/tests/test_no_runner_literals.py") == [
        "hub/tests/test_no_runner_literals.py",
        "hub/tests/test_test_git_shares_one_timeout.py",
        "hub/tests/test_the_sweep_set_is_current.py",
    ]


def test_a_cli_change_runs_the_tests_that_scan_src():
    assert _affected("src/agentweave/cli.py") == [
        "hub/tests/test_database_backups.py",
        "hub/tests/test_task_workspace_scheme.py",
    ]


@pytest.mark.parametrize(
    "path", ["docs/index.md", "spec/changes/x/spec.json", "hub/hub/static/ui/index.js", "README.md"]
)
def test_a_change_no_sweep_test_reads_runs_none(path):
    assert _affected(path) == []


@pytest.mark.parametrize(
    "path",
    [
        "hub/tests/conftest.py",
        "tests/conftest.py",
        "hub/tests/fixtures/run.json",
        "hub/ui/src/__tests__/fixtures/managerJobs.route.json",
        "scripts/checks/sweep_tests.txt",
        "scripts/checks/sweep_check.py",
        "scripts/checks/junit_rerun.py",
        "hub/pyproject.toml",
        "pyproject.toml",
        "hub/alembic.ini",
    ],
)
def test_shared_infrastructure_runs_the_full_sweep(path):
    assert _affected("docs/index.md", path) is None


@pytest.mark.parametrize(
    "path", ["Makefile", "hub/Dockerfile", "something/new.py", ".github/x.yml"]
)
def test_an_unknown_path_runs_the_full_sweep(path):
    assert _affected("docs/index.md", path) is None


def test_a_sweep_test_without_a_scope_runs_the_full_sweep():
    assert sweep_check.affected_tests(["docs/a.md"], [*SWEEP, "hub/tests/test_new.py"]) is None


def test_windows_separators_and_blank_lines_are_read():
    assert _affected("", "hub\\ui\\src\\api\\vault.ts", "  ") == _affected(
        "hub/ui/src/api/vault.ts"
    )


@pytest.mark.parametrize(
    "helper, importer",
    [
        ("hub/tests/_background_runs.py", "hub/tests/test_conversation_contract.py"),
        (
            "hub/tests/_background_runs.py",
            "hub/tests/test_rebinding_an_agents_runner_starts_clean.py",
        ),
        ("hub/tests/_git_timeout.py", "hub/tests/test_a_refused_review_leaves_nothing_behind.py"),
        (
            "hub/tests/test_agent_trigger.py",
            "hub/tests/test_a_refused_review_leaves_nothing_behind.py",
        ),
        ("hub/tests/test_task_integration.py", "hub/tests/test_every_send_back_says_why.py"),
        ("hub/tests/test_title_generation.py", "hub/tests/test_manager_jobs.py"),
        ("hub/tests/_spec_versions.py", "hub/tests/test_vault_archive.py"),
        (
            "hub/tests/test_a_refused_review_leaves_nothing_behind.py",
            "hub/tests/test_an_event_is_announced_after_commit.py",
        ),
        # through another module: _git_timeout -> test_a_refused_review... -> test_an_event...
        ("hub/tests/_git_timeout.py", "hub/tests/test_an_event_is_announced_after_commit.py"),
    ],
)
def test_a_changed_hub_tests_module_runs_the_sweep_tests_that_import_it(helper, importer):
    """QA's send-back at ab73a94: a helper or test a sweep test imports must select that test."""
    assert importer in _affected(helper)


def _tree(root: Path, files: dict) -> Path:
    for name, text in files.items():
        path = root / "hub" / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_every_import_form_is_read_and_followed_through_other_modules(tmp_path):
    root = _tree(
        tmp_path,
        {
            "__init__.py": "",
            "_helper.py": "",
            "_other.py": "",
            "_absolute.py": "",
            "test_middle.py": "from ._helper import thing\n",
            "test_top.py": "def f():\n    from .test_middle import (\n        x,\n    )\n",
            "test_package_form.py": "from . import _other\n",
            "test_absolute.py": "import hub.tests._absolute\nfrom hub.tests import _other\n",
            "sub/__init__.py": "",
            "sub/test_deep.py": "from .._helper import thing\n",
            "test_alone.py": "import os\n",
        },
    )
    importers = sweep_check.importers_of_tests(root)
    assert importers["hub/tests/_helper.py"] == {
        "hub/tests/test_middle.py",
        "hub/tests/test_top.py",
        "hub/tests/sub/test_deep.py",
    }
    assert importers["hub/tests/_other.py"] == {
        "hub/tests/test_package_form.py",
        "hub/tests/test_absolute.py",
    }
    assert importers["hub/tests/_absolute.py"] == {"hub/tests/test_absolute.py"}
    assert "hub/tests/test_alone.py" not in importers


def test_a_hub_tests_file_that_does_not_parse_runs_the_full_sweep(tmp_path, monkeypatch):
    root = _tree(tmp_path, {"_helper.py": "", "test_broken.py": "def (:\n"})
    assert sweep_check.importers_of_tests(root) is None
    monkeypatch.setattr(sweep_check, "importers_of_tests", lambda: None)
    assert _affected("hub/tests/_helper.py") is None
    # a path outside hub/tests needs no import scan
    assert _affected("docs/index.md") == []


def test_the_hub_tests_package_init_runs_the_full_sweep():
    assert _affected("hub/tests/__init__.py") is None


def _main(tmp_path, monkeypatch, paths):
    listing = tmp_path / "changed.txt"
    listing.write_text("".join(f"{p}\n" for p in paths), encoding="utf-8")
    report = tmp_path / "out" / "sweep.xml"
    seen: list = []
    monkeypatch.chdir(tmp_path)
    code = sweep_check.main(
        ["--report", str(report), "--changed-files", str(listing)],
        run_pytest=lambda args: seen.append(args) or 0,
    )
    return code, seen, report


def test_one_hub_ui_module_runs_its_tests_and_writes_the_report(tmp_path, monkeypatch):
    code, seen, report = _main(tmp_path, monkeypatch, ["hub/ui/src/api/vault.ts"])
    assert code == 0 and len(seen) == 1
    assert [a for a in seen[0] if a.endswith(".py")] == [
        "hub/tests/test_surface_ceilings.py",
        "hub/tests/test_ui_vocabulary.py",
        "hub/tests/test_vault_archive.py",
    ]
    assert f"--junitxml={report}" in seen[0]


def test_shared_or_unknown_runs_the_whole_sweep_set(tmp_path, monkeypatch):
    for path in ("hub/tests/conftest.py", "unknown/file.txt"):
        _, seen, _ = _main(tmp_path, monkeypatch, [path])
        assert [a for a in seen[0] if a.endswith(".py")] == SWEEP


def test_no_related_test_runs_nothing_and_writes_an_empty_report(tmp_path, monkeypatch):
    code, seen, report = _main(tmp_path, monkeypatch, ["docs/index.md"])
    assert code == 0 and seen == []
    suite = ElementTree.parse(report).getroot().find("testsuite")
    assert suite is not None and suite.get("tests") == "0"


def test_an_unreadable_listing_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = sweep_check.main(
        ["--changed-files", str(tmp_path / "missing.txt")], run_pytest=lambda a: 0
    )
    assert code == 4


def test_the_settings_size_sweep_to_the_change():
    checks = {c["name"]: c for c in json.loads((CHECKS / "check_settings.json").read_text("utf-8"))}
    sweep = checks["sweep"]
    assert sweep["change_command"] == f"{sweep['command']} --changed-files {{changed_files}}"
