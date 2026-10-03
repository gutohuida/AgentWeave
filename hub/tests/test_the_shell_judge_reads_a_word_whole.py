"""Rule 6 judges a word's pieces, not its tail (F362, design D2) -- `the-shell-judge-reads-a-word-whole`.

The fixture below is the change's shared one (tasks.md "1. Tests first"): every later task group in
this change reuses it rather than building its own links. Only task 1.1's rows are in `_TABLE` so far.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hub.mcp_server import _decide

_WINDOWS = sys.platform == "win32"
_HUB = "http://127.0.0.1:8016"


def _link(link: Path, target: Path) -> None:
    """A directory link made without privilege: a junction on Windows, a symlink elsewhere."""
    if _WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A workspace with links in and out of it, shared by every task group in this change."""
    ws = tmp_path / "work"
    outside = tmp_path / "outside"
    sub = ws / "sub"
    sub.mkdir(parents=True)
    outside.mkdir()
    (outside / "x").write_text("x")
    (sub / "a.py").write_text("a")
    (sub / "b.py").write_text("b")
    _link(ws / "up", outside)  # a link out
    _link(ws / "in", sub)  # an inside link, to a directory of the same depth
    _link(sub / "l", ws)  # (R6) a link whose target is shallower than the link (D12)
    (sub / "@s").mkdir()
    _link(sub / "@s" / "p", outside)  # (R8) the shape `npm link` makes under a scope
    (ws / "a'b").mkdir()
    _link(ws / "a'b" / "up", outside)
    (ws / "a@b").mkdir()
    _link(ws / "a@b" / "l", ws)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    # No run credential: _report_decision raises internally and must be swallowed, same as
    # test_permission_approver.py's fixture.
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


def _row(label, command, allow, *, tool="Bash"):
    return pytest.param(tool, command, allow, id=label)


_TABLE = [
    # 1.1: rows allowed after this change, refused today. Rule 6 no longer scans a word for an
    # absolute tail (`'/x.py'` out of `src/*.py`); it splits the word into its path-shaped pieces
    # and judges each one, so a glob, an `@`-glued name, a revision prefix or a `%`-format spec
    # reads as the relative path it is (design D2).
    _row("1.1a", "ls test/*.test.js", True),
    _row("1.1b", "grep -r foo src/*.py", True),
    _row("1.1c", "find . -path './src/*' -name x", True),
    _row("1.1d", "npm install @types/node", True),
    _row("1.1e", "ls node_modules/@babel/core", True),  # no link behind it
    _row("1.1f", "git show HEAD:src/a.py", True),
    _row("1.1g", "git log --format=%h/%s", True),
    _row("1.1h", "printf '%s/%s' a b", True),
    _row("1.1i", "python -c 'print(1/2)'", True),
    _row("1.1j", r"sed -E 's/(foo)/\1/' f", True),
    _row("1.1k", "mkdir -p src/{a,b}", True),
    _row("1.1l", "ls src/?.ts src/[ab].ts", True),
    _row("1.1m", "gcc -I./include/x a.c", True),
    # D4: the null device and standard streams, named whole, stand in the bash dialect.
    _row("1.1n", "ls 2>/dev/null", True),
    _row("1.1o", "echo x > /dev/stderr", True),
    _row("1.1p", r"Get-ChildItem src\*.py", True, tool="PowerShell"),
    # 1.2 (F403): a brace the outer shell itself expands is read as expanded (design D1). The
    # first two are refused only once D1 runs the brace through, because `..` is one of its real
    # alternatives (measured in Git Bash: `.{,.}` -> `. ..`, `{.,.}.` -> `.. ..`). The next three
    # were already refused by the old tail backstop and must stay refused once rule 6 is rewritten
    # without D1 -- each FAILS against rule 6's piece reading alone, because the unexpanded brace
    # characters are just more word text, read as an inside relative path (R1's prototype measured
    # all three allowed): `.{,.}/x` has no separator-adjacent `..`, `{.,.}./x` reads as the inside
    # piece `{.,.}./x`, `src/{a,..}/../y` reads as the inside piece `src/{a,..}/../y`.
    _row("1.2a", "cp notes.md .{,.}", False),
    _row("1.2b", "cp notes.md {.,.}.", False),
    _row("1.2c", "cp notes.md .{,.}/x", False),
    _row("1.2d", "cp notes.md {.,.}./x", False),
    _row("1.2e", "cp x src/{a,..}/../y", False),
    # 1.3 (R2): a brace the outer shell left literal (quoted, escaped, or any brace in the
    # PowerShell dialect) is still judged as an inner shell would expand it. Each of the first four
    # PASSES today (the old tail backstop quotes only `'/x'`) and FAILS against rule 6's piece
    # reading alone, because `.{,.}/x` and `{,..}/x` have no separator-adjacent `..` once the
    # braces are read as ordinary word characters.
    _row("1.3a", "bash -c 'cp n .{,.}/x'", False),
    _row("1.3b", "sh -c 'cp n {,..}/x'", False),
    _row("1.3c", 'bash -c "cp x src/{a,..}/../y"', False),
    _row("1.3d", "bash -c 'cp n .{,.}/x'", False, tool="PowerShell"),
    # `.{,.}` alone (no trailing `/x`), quoted into an inner shell, expands to `.` and `..` -- the
    # outer bash never sentinel-marks it (it is inside the single-quoted `-c` argument), so this is
    # refused only once R2's own reading judges the expansion, not D1's top-level one (task 1.2).
    _row("1.3e", "bash -c 'cp n .{,.}'", False),
    # Controls: a literal brace an inner shell never gets to, so R2's reading must not fire.
    _row("1.3f", "awk '{print $1, $2}' f", True),
    _row("1.3g", "jq '{a: .x, b: .y}' f", True),
    _row("1.3h", "sed 's/a{2}/b/' f", True),
    # A `${...}` parameter expansion stays uncheckable (rule 3, `_expands`) -- R2 must not mistake
    # the `{` right after `$` for a brace group and expand `X}/y` on its own.
    _row("1.3i", "echo hi > ${X}/y", False),
    # The accepted cost: a file literally named `.{,.}` is refused, because R2 cannot tell this
    # word apart from one handed to an inner shell.
    _row("1.3j", "cp notes.md '.{,.}'/x", False),
]


@pytest.mark.parametrize("tool, command, allow", _TABLE)
def test_the_decided_table(workspace, monkeypatch, tool, command, allow):
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is allow, decision["reason"]
