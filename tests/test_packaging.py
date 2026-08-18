"""Tests that the built distribution actually contains what the CLI loads at runtime.

Template coverage in the wheel currently rests on two independent mechanisms:
MANIFEST.in's `recursive-include src/agentweave/templates *`, plus setuptools'
`include_package_data` (on by default for pyproject.toml-configured projects).
The `[tool.setuptools.package-data]` list enumerates subdirectories explicitly
and is *not* exhaustive — any subdirectory absent from that list ships only
because of the two mechanisms above.

That is fragile: dropping MANIFEST.in or setting `include_package_data = false`
would silently ship an incomplete `templates/` directory, and every other test
would still pass because they import from the source tree. These tests build a
real wheel and compare its contents against the source tree so the gap surfaces
at test time rather than after publishing.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "src" / "agentweave" / "templates"

# Data extensions declared in package-data; .py files are package code, not data.
DATA_SUFFIXES = {".md", ".json"}


def _source_template_files() -> set:
    """Every template data file in the source tree, relative to the package root."""
    return {
        p.relative_to(TEMPLATES_DIR.parent).as_posix()
        for p in TEMPLATES_DIR.rglob("*")
        if p.is_file() and p.suffix in DATA_SUFFIXES and "__pycache__" not in p.parts
    }


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory):
    """Build a wheel from the repo and return the path to it."""
    if not (REPO_ROOT / "pyproject.toml").exists():
        pytest.skip("not running from a source checkout")

    outdir = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        pytest.skip(f"wheel build unavailable (pip install build):\n{result.stderr[-2000:]}")

    wheels = list(outdir.glob("*.whl"))
    assert wheels, "build succeeded but produced no wheel"
    return wheels[0]


def test_source_tree_has_template_data():
    """Guard the guard: if this is empty the wheel comparison proves nothing."""
    assert _source_template_files(), "no template data files found in source tree"


def test_wheel_ships_every_template_file(built_wheel):
    """Every template the CLI can load must be present in the wheel.

    Failures here are easy to miss in the wild: `_ensure_skill_support_files`
    swallows FileNotFoundError by design, so a template missing from the wheel
    degrades silently for pip-installed users rather than raising.
    """
    with zipfile.ZipFile(built_wheel) as zf:
        shipped = {n for n in zf.namelist() if n.startswith("agentweave/templates/")}

    expected = _source_template_files()
    missing = sorted(name for name in expected if f"agentweave/{name}" not in shipped)

    assert not missing, (
        "template files present in the source tree but missing from the wheel — "
        "check [tool.setuptools.package-data] in pyproject.toml:\n  " + "\n  ".join(missing)
    )


def test_wheel_excludes_pycache(built_wheel):
    """Broad include rules must not sweep compiled bytecode into the wheel."""
    with zipfile.ZipFile(built_wheel) as zf:
        junk = [n for n in zf.namelist() if "__pycache__" in n or n.endswith(".pyc")]

    assert not junk, f"wheel contains bytecode artifacts: {junk}"
