"""AW-157: every `git` a Hub test runs itself is bounded by `_git_timeout.GIT_TIMEOUT`, not a literal.

Thirty helpers each passed `timeout=30`, and on the machine the landing checks run on a plain
`git config` ran past it: 17 tests failed in one batch on that alone, and passed re-run serially.
A literal here is how that comes back one helper at a time, so this walks `hub/tests` for any
`subprocess` call whose argv starts with `"git"` and is given a numeric timeout.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _literal_git_timeouts(source: str) -> list[int]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        argv = node.args[0] if node.args else None
        if argv is None:
            argv = next((k.value for k in node.keywords if k.arg == "args"), None)
        if not (
            isinstance(argv, (ast.List, ast.Tuple))
            and argv.elts
            and isinstance(argv.elts[0], ast.Constant)
            and argv.elts[0].value == "git"
        ):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "timeout"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, (int, float))
            ):
                found.append(node.lineno)
    return found


def test_the_scan_sees_a_literal_timeout_and_passes_the_shared_one():
    """The control: a scan that matched nothing would pass on any tree."""
    assert _literal_git_timeouts(
        'subprocess.run(["git", *args], cwd=repo,\n    timeout=30)\n'
        'subprocess.run(["git", "add", "-A"], timeout=GIT_TIMEOUT)\n'
        'subprocess.run(["npm", "ci"], timeout=30)\n'
    ) == [1]


def test_no_test_gives_its_own_git_a_literal_timeout():
    offenders = {
        str(path.relative_to(TESTS)): lines
        for path in sorted(TESTS.rglob("*.py"))
        if (lines := _literal_git_timeouts(path.read_text(encoding="utf-8-sig")))
    }
    assert not offenders, (
        "use `from ._git_timeout import GIT_TIMEOUT` (AW-157) instead of a literal timeout on "
        f"these git calls: {offenders}"
    )
