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
    # 1.4 (D3): a glob component that begins with `.`, holds `*`/`?`/`[`, and that
    # `fnmatch.fnmatchcase("..", component)` proves some real bash can still expand to `..`
    # (`globskipdots` is off in bash before 5.2; Git Bash 5.2.37 has it on) is rewritten to `..`
    # before `_judge_path` resolves it. Measured in real Git Bash 5.2.37 with `shopt -u
    # globskipdots` (off, matching the older bash the rule guards against): `.*` -> `. ..`,
    # `..*` -> `..`, `.[.]` -> `..`. `..?` needs a third character and never matches `..` in any
    # bash (measured: stays literal), so `sub/..?/y` is left alone.
    _row("1.4a", "ls .*/x", False),
    _row("1.4h", "ls ..*/x", False),
    _row("1.4i", "cp x .[.]/y", False),
    # These two already resolve outside without any rewrite -- the leading component is already
    # the literal `..`, which has no glob character to trigger D3 -- so they are controls: D3 must
    # not change whether they refuse, only (below) whether the reason still quotes the whole piece.
    _row("1.4j", "ls ../*", False),
    _row("1.4k", "rm -rf ../*.py", False),
    _row("1.4l", r"Get-ChildItem ..\*", False, tool="PowerShell"),
    # Allowed: a dot-glob not at a component that could reach `..`, and a glob needing a third
    # character after the dot.
    _row("1.4m", "ls sub/.*/x", True),
    _row("1.4n", "cp x sub/..?/y", True),
    # 1.5 (D5): a schemeless network address (`user@host:`, `host:port/…`) is refused with the
    # network reason, read on the whole word after rule 2 and before rule 3, in both dialects --
    # so a separator-less address (`git@github.com:repo`) is seen at all, not only a word rule 6
    # would otherwise reach. These eleven already pass today (regression guards: the trailing-colon
    # fix below touches `_words`, which every rule uses).
    _row("1.5a", "git clone git@github.com:o/r.git", False),
    _row("1.5b", "curl -s 127.0.0.1:9/x", False),
    _row("1.5c", "git clone git@github.com:repo", False),
    _row("1.5d", "scp n user@example.com:file", False),
    _row("1.5e", "scp n root@10.0.0.5:f", False),
    # Not addresses: the host before the colon is dotless (a package-manager or digest form), or
    # there is no port-shaped tail after it.
    _row("1.5f", "docker pull alpine@sha256:abc", True),
    _row("1.5g", "npm i x@npm:y", True),
    _row("1.5h", "pnpm add x@workspace:y", True),
    _row("1.5i", "scp a host:x/y", True),
    _row("1.5j", "scp n user@myserver:file", True),
    _row("1.5k", "docker run -p 8080:80 img", True),
    # Refused anyway, as the outside piece rule 6 already finds -- not as a network address.
    _row("1.5l", "docker run -v data:/app img", False),
    _row("1.5m", "npm i x@file:../lib", False),
    # (R5) `_words` trims a word's trailing `:`, so this reached the judge as `user@example.com`,
    # which `_SCP_ADDRESS_RE` (needing a trailing `:`) never matched. FAILS today (allowed,
    # measured).
    _row("1.5n", "scp n user@example.com:", False),
    # 1.7: negative controls that must stay refused. Re-derived independently against `_decide`
    # (iteration 9 did not trust iteration 7's note as given -- see the night log); the task's own
    # four bullets split into three that already refuse correctly today and a fourth that does not
    # (below, left out of this table). These eleven are regression guards: each names the design
    # step that is the actual reason it refuses, so a future change that removes that step is
    # caught here rather than by a different row's accident.
    # D2 step 1: a glued short option's letters are dropped; the value `/tmp/x` is then absolute
    # (rule 5).
    _row("1.7a", "curl -o/tmp/x $HUB_URL/api", False),
    # D2 step 3: `@` is a break where "a path is glued to a curl `name@file`" (design's own
    # example); the piece `/etc/passwd` is absolute.
    _row("1.7e", "curl -F file=@/etc/passwd x", False),
    # D2 step 1: a glued short option (`-xvf`); the value `/tmp/a.tar` is absolute.
    _row("1.7f", "tar -xvf/tmp/a.tar", False),
    # D2 step 3: `(` is a break ("opens a subshell or a call"); the piece `b/../../x` resolves
    # outside.
    _row("1.7g", "ls a(b/../../x", False),
    # D2 step 3: a leading `@` break; the piece `../y` resolves outside.
    _row("1.7h", "cp x @../y", False),
    # D2 step 3: `<` survives lexing only when quoted and matters to an inner shell; the piece
    # `/etc/passwd` is absolute.
    _row("1.7i", "sh -c 'cat</etc/passwd'", False),
    # D2 step 3: `>` survives lexing only when quoted and matters to an inner shell (design's own
    # example); the piece `../x` resolves outside.
    _row("1.7j", 'sh -c "echo hi>../x"', False),
    # D2 step 3: `(` is a break for "a call" (design's own example, `open('../x','w')`); the piece
    # `/etc/x` is absolute.
    _row("1.7k", "python -c \"open('/etc/x','w')\"", False),
    # D2 step 3: `(` is a break for "a call"; the piece `../x` resolves outside.
    _row("1.7l", "node -e \"require('fs').writeFileSync('../x','')\"", False),
    # D2 step 3: `:` is a break where "a path is glued to a host" (design's own example,
    # `host:/x`); the piece `/x` is absolute.
    _row("1.7m", "scp a host:/x", False),
    # Rule 5: an ordinary absolute path. `/dev/tcp/...` is not one of D4's named devices (the null
    # device and standard streams), so D4's exemption must not reach it.
    _row("1.7n", "cat /dev/tcp/1.2.3.4/80", False),
    # Rule 5: D4's device exemption is bash-only ("may be named, in bash only"); on the PowerShell
    # dialect `/dev/null` is an ordinary absolute path, outside.
    _row("1.7o", "echo hi > /dev/null", False, tool="PowerShell"),
]


@pytest.mark.parametrize("tool, command, allow", _TABLE)
def test_the_decided_table(workspace, monkeypatch, tool, command, allow):
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is allow, decision["reason"]


# 1.4: the refused rows above already pass an allow-only check today for three of the six (the
# leading component is already a literal `..`), but the first three pass only once D3 rewrites the
# glob component -- and even the three that already refused must still quote the *whole* piece as
# written, not a fragment, so this checks the reason text itself rather than trusting `allow` alone.
_DOTDOT_GLOB_REASON_TABLE = [
    ("1.4a", "Bash", "ls .*/x", ".*/x"),
    ("1.4h", "Bash", "ls ..*/x", "..*/x"),
    ("1.4i", "Bash", "cp x .[.]/y", ".[.]/y"),
    ("1.4j", "Bash", "ls ../*", "../*"),
    ("1.4k", "Bash", "rm -rf ../*.py", "../*.py"),
    ("1.4l", "PowerShell", r"Get-ChildItem ..\*", r"..\*"),
]


@pytest.mark.parametrize(
    "tool, command, shown",
    [
        pytest.param(tool, command, shown, id=label)
        for label, tool, command, shown in _DOTDOT_GLOB_REASON_TABLE
    ],
)
def test_the_glob_dotdot_rows_quote_the_whole_piece(workspace, monkeypatch, tool, command, shown):
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is False
    assert decision["reason"] == f"{shown!r} is outside your workspace"


# 1.5 (R5, R7): an allow-only check would not catch a wrong quote -- the refusal for the
# trailing-colon row must quote the word with its colon restored (`'user@example.com:'`), the text
# D5 actually matched, not the colon-trimmed word `_words` otherwise yields.
def test_the_trailing_colon_address_quotes_the_colon_restored(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide("Bash", {"command": "scp n user@example.com:"})
    assert decision["allow"] is False
    assert "'user@example.com:'" in decision["reason"]
