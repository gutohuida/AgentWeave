"""The sweep set (`scripts/checks/sweep_tests.txt`) names every Hub test that scans the tree.

Spec `agentweave-s-checks-fit-a-busy-machine`, FR-6. The sweep set runs as its own fast check
because a test that walks the repository or reads the UI source is reached by no import, so a
UI-only change would otherwise pass the fast checks and fail only when the full suite runs at
landing. A list nobody maintains rots silently; this test fails, naming the file, when

- a Hub test file walks or globs a path anchored at its own location, or reads `hub/ui/src`,
  and is neither in the sweep set nor in `NOT_SWEEPS` below with the reason it was audited out;
- the sweep set names a file that does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SWEEP_SET = REPO_ROOT / "scripts" / "checks" / "sweep_tests.txt"

#: Test files the detector below matches that were read and found not to scan the tree.
NOT_SWEEPS = {
    "hub/tests/test_spec_adoption_corpus.py": "rglobs tmp_path; reads one module it imports",
    "hub/tests/test_timestamp_serialization.py": "reads models.py; names hub/ui/src in prose",
    "hub/tests/test_tool_server_pin.py": "globs tmp directories only",
    "hub/tests/test_ui_build_stamp.py": "builds and globs tmp repos; loads one script by path",
}

#: A walk or glob call. `ast.walk` walks a syntax tree, not a directory, so it is not one.
WALKS = re.compile(
    r"(?<!ast)\.(?:rglob|glob|iterdir)\(|\bos\.(?:walk|listdir|scandir)\(|\bglob\.i?glob\("
)
#: A path into the UI source, written as one string or joined.
UI_SOURCE = re.compile(r"""ui/src|["']ui["']\s*/\s*["']src["']""")


def listed(sweep_set: Path) -> list[str]:
    """The repo-relative paths a sweep set names, blank lines and `#` comments skipped."""
    lines = sweep_set.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def scans_the_tree(source: str) -> bool:
    """A test that locates the tree from `__file__` and walks it or reaches into the UI source."""
    return "__file__" in source and bool(WALKS.search(source) or UI_SOURCE.search(source))


def problems(root: Path, sweep_set: Path, not_sweeps: dict[str, str]) -> list[str]:
    """Every way the sweep set disagrees with the Hub tests under `root`, each naming its file."""
    names = listed(sweep_set)
    found = [
        f"{name} is in {sweep_set.name} but does not exist"
        for name in names
        if not (root / name).is_file()
    ]
    for path in sorted((root / "hub" / "tests").rglob("test_*.py")):
        name = path.relative_to(root).as_posix()
        if name in names or name in not_sweeps:
            continue
        if scans_the_tree(path.read_text(encoding="utf-8")):
            found.append(
                f"{name} scans the repository or the UI source but is not in {sweep_set.name}: "
                "add it there, or to NOT_SWEEPS in this test with the reason it does not scan"
            )
    return found


def test_the_sweep_set_names_every_scanning_test_and_only_files_that_exist() -> None:
    if not SWEEP_SET.is_file():  # pragma: no cover - not a source checkout
        pytest.skip(f"{SWEEP_SET} is absent; nothing to check")
    found = problems(REPO_ROOT, SWEEP_SET, NOT_SWEEPS)
    assert not found, "\n".join(found)


def test_every_audited_out_file_still_exists() -> None:
    gone = [name for name in NOT_SWEEPS if not (REPO_ROOT / name).is_file()]
    assert not gone, f"NOT_SWEEPS names files that no longer exist: {gone}"


def _tree(tmp_path: Path, sweep_lines: list[str]) -> tuple[Path, Path]:
    tests = tmp_path / "hub" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_plain.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")
    (tests / "test_listed.py").write_text(
        'from pathlib import Path\nHUB = Path(__file__).parents[1] / "hub"\n'
        'def test_x():\n    assert list(HUB.rglob("*.py")) is not None\n',
        encoding="utf-8",
    )
    sweep_set = tmp_path / "sweep_tests.txt"
    sweep_set.write_text("# a comment\n\n" + "\n".join(sweep_lines) + "\n", encoding="utf-8")
    return tmp_path, sweep_set


def test_a_current_tree_has_no_problems(tmp_path: Path) -> None:
    root, sweep_set = _tree(tmp_path, ["hub/tests/test_listed.py"])
    assert problems(root, sweep_set, {}) == []


def test_a_new_test_globbing_the_ui_source_and_not_listed_fails_naming_it(tmp_path: Path) -> None:
    root, sweep_set = _tree(tmp_path, ["hub/tests/test_listed.py"])
    (root / "hub" / "tests" / "test_new_ui_guard.py").write_text(
        "from pathlib import Path\n"
        'UI = Path(__file__).resolve().parents[1] / "ui" / "src"\n'
        "def test_no_literal():\n"
        '    for path in UI.rglob("*.tsx"):\n'
        '        assert "x" not in path.read_text()\n',
        encoding="utf-8",
    )
    found = problems(root, sweep_set, {})
    assert len(found) == 1
    assert "hub/tests/test_new_ui_guard.py" in found[0]


def test_a_sweep_set_naming_a_deleted_file_fails_naming_it(tmp_path: Path) -> None:
    root, sweep_set = _tree(tmp_path, ["hub/tests/test_listed.py", "hub/tests/test_deleted.py"])
    found = problems(root, sweep_set, {})
    assert len(found) == 1
    assert "hub/tests/test_deleted.py" in found[0]


def test_an_audited_out_file_is_not_reported(tmp_path: Path) -> None:
    root, sweep_set = _tree(tmp_path, [])
    assert problems(root, sweep_set, {"hub/tests/test_listed.py": "audited"}) == []
    assert len(problems(root, sweep_set, {})) == 1


def test_a_syntax_tree_walk_is_not_a_directory_walk() -> None:
    assert not scans_the_tree("import ast\nPath(__file__)\nfor n in ast.walk(tree): pass\n")
