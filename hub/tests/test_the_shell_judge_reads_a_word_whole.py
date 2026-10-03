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
    # 1.4f (task 2.0b, design D12), the literal (non-glob) rows only -- the glob rows (`sub/l*/..`)
    # need D8's `_glob_links`, not yet built. `ntpath.realpath` normalises a `..` lexically before
    # reading any link, so these escape today on Windows (msys itself resolves `..` physically,
    # measured) -- `_physical`'s second reading in `_where` is what refuses them. Already refused on
    # POSIX, where `os.path.realpath` is itself physical; this table runs there too, as a control.
    _row("1.4f1", "cp n sub/l/../y", False),
    _row("1.4f2", "echo hi > sub/l/../x1", False),
    _row("1.4f3", "ls sub/l/../x", False),
    # Controls allowed, both platforms (design D12): a `..` through a link that is not shallower
    # than where it sits lands back where the lexical reading already put it.
    _row("1.4f4", "ls in/../sub", True),
    _row("1.4f5", "ls sub/../sub/a.py", True),
    _row("1.4f6", "ls in/../sub/*.py", True),
    # 1.4e/2.1d (R6, D11), the part built this iteration: the bracket-kept word `_words` now also
    # yields, and D3's dot rule (`_rewrite_dotdot_globs`) now also reads a component that opens
    # with `[` rather than `.`. `cp n [.]./x` needs only these two (no directory listing): the
    # ordinary word is `.]./x` (no rewrite, inside today), and the bracket-kept word `[.]./x`'s
    # first component is rewritten to `..`. The link-detection half of 1.4e (`[u]p/x`, `./u[p]`,
    # where a bracket-kept word must be matched against a real directory entry that is a link) needs
    # `_glob_links` (task 2.1c, not built) and is not covered here; task 2.1d itself stays unticked.
    _row("1.4e1", "cp n [.]./x", False),
    # Controls: the bracket-kept word can only ever add a refusal, never replace the ordinary
    # word's reading or introduce a false one of its own.
    _row("1.4e2", "ls [../x]", False),  # unaffected: still refused as '../x', the ordinary word
    _row("1.4e3", "echo arr[0] x[1:]", True),
    _row("1.4e4", 'python -c \'["a","b"]\'', True),
    _row("1.4e5", "ls sub/[ab].py", True),
    # The separator-less forms stay allowed under this change alone (task 1.4e's own note); the
    # sibling change's 1.4f refuses them once its drive machinery lands.
    _row("1.4e6", "cp n [u]p", True),
    _row("1.4e7", "cp n u[p]", True),
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
    # (R6, D11) The bracket-kept word, not the ordinary one (`.]./x`, which is not rewritten): the
    # refusal quotes `[.]./x` as written, not the ordinary word's own reading of the same piece.
    ("1.4e1", "Bash", "cp n [.]./x", "[.]./x"),
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


# 2.0b / design D12 Costs: named so that a change of mind is visible. A native program resolves `..`
# lexically and would write inside the workspace -- `Set-Content` through PowerShell, and the Write
# tool's own `file_path` -- but `_decide` refuses both, because msys resolves the identical text
# physically and the judge cannot tell which program a word reaches. Windows-only: `_physical` only
# runs under `_DRIVE_LETTERS`, and `Set-Content` is a PowerShell cmdlet.
@pytest.mark.skipif(not _WINDOWS, reason="D12's physical reading only runs on a drive-letter host")
def test_a_dotdot_after_a_link_is_refused_though_a_native_program_writes_inside(
    workspace, monkeypatch
):
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide("PowerShell", {"command": r"Set-Content sub\l\..\p1 hi"})
    assert decision["allow"] is False
    assert "it resolves to" in decision["reason"]
    decision = _decide("Write", {"file_path": str(workspace / "sub" / "l" / ".." / "z")})
    assert decision["allow"] is False
    assert "it resolves to" in decision["reason"]


# design D12 "Bound": `_physical` makes at most one `realpath` per `..` that follows a name; a path
# needing a 65th is answered `_UNRESOLVED` rather than growing the cost without limit. Windows-only:
# the bound is part of the physical reading, which only runs under `_DRIVE_LETTERS`.
@pytest.mark.skipif(not _WINDOWS, reason="D12's physical reading only runs on a drive-letter host")
def test_the_physical_readings_64_step_bound(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)
    within_bound = _decide("Bash", {"command": "ls " + "sub/../" * 64 + "x"})
    assert within_bound["allow"] is True, within_bound["reason"]
    past_bound = _decide("Bash", {"command": "ls " + "sub/../" * 65 + "x"})
    assert past_bound["allow"] is False
    assert past_bound["reason"].endswith("could not be resolved")


def _brace_list(prefix, count):
    return "{" + ",".join(f"{prefix}{n}" for n in range(1, count + 1)) + "}"


# 1.6 (partial), task 2.0 / design "The bounds": `_Budget` is one object for the whole `_decide`
# call. Monkeypatching its total down to 15 (room for one 10-alternative argument, not two) proves
# two things neither existed before task 2.0, so both fail with an `AttributeError` on today's code
# (there was no `_BRACE_TOTAL_BUDGET` to patch) and, once the attribute exists, would fail on a
# `_Budget` that charged without memoizing:
#
# - "a Bash command read in both readings charges the budget once" (the memo): `_decide` reads
#   `command` under both the `c` and `utf8` readings even for a tool fixed to one dialect, and the
#   brace argument renders identical text in both. Without the expansion memo (keyed by the marked
#   argument text and dialect, not by `reading`), the second reading would spend the same 10
#   alternatives again, totalling 20 against a budget of 15, and this single-argument command would
#   be wrongly refused.
# - the total is spent across separate arguments, not reset between them: a second 10-alternative
#   argument in the same command has only the 5 the first left, and is refused.
def test_the_brace_budget_is_one_per_decide_not_per_reading_or_argument(workspace, monkeypatch):
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)
    monkeypatch.setattr(mcp_server, "_BRACE_TOTAL_BUDGET", 15)
    one_argument = _decide("Bash", {"command": f"touch {_brace_list('f', 10)}"})
    assert one_argument["allow"] is True, one_argument["reason"]
    two_arguments = _decide(
        "Bash", {"command": f"touch {_brace_list('f', 10)} {_brace_list('g', 10)}"}
    )
    assert two_arguments["allow"] is False
    assert two_arguments["reason"].endswith(mcp_server._TOO_MANY)


# 1.6 (partial), the brace/budget rows only -- task 2.1's `_expand_braces` is iterative (an explicit
# stack, no recursion) and task 2.0's `_Budget.expand_braces` caps every call at
# `min(_BRACE_ARGUMENT_BUDGET, _BRACE_TOTAL_BUDGET - spent)` before building any alternative
# (`_brace_absorb` checks `len(parent) * len(alternatives) > budget` before multiplying), so each row
# below is answered, and refused with `_TOO_MANY`, in well under a second rather than raising
# (a naive recursive expander would overflow the stack on the unbalanced rows, or build 2**40
# strings on the last one). Measured directly against `_decide` before writing this test (a
# throwaway script; every row below answered in under 5ms). The rest of task 1.6 -- the extglob and
# backslash-run rows (no raise, but not brace-specific), the link-cycle `**` row and the listing memo
# (both need `_glob_links`, task 2.1c, not built), the memo key's colon flag, and `approve_tool_call`
# catching a raise from `_decide` (D6, task 2.2b, not built) -- is not covered here and task 1.6
# itself stays unticked.
def test_the_totality_rows_for_brace_expansion_never_raise_or_hang(workspace, monkeypatch):
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)

    unbalanced_open = _decide("Bash", {"command": "cp n " + "{" * 5000 + "x"})
    assert unbalanced_open["allow"] is False
    assert unbalanced_open["reason"].endswith(mcp_server._TOO_MANY)

    unbalanced_open_quoted = _decide("Bash", {"command": "cp n '" + "{" * 5000 + "x'"})
    assert unbalanced_open_quoted["allow"] is False
    assert unbalanced_open_quoted["reason"].endswith(mcp_server._TOO_MANY)

    twenty_arguments = " ".join(_brace_list(f"a{i}", 100) for i in range(20))
    over_the_decide_bound = _decide("Bash", {"command": f"cmd {twenty_arguments}"})
    assert over_the_decide_bound["allow"] is False
    assert over_the_decide_bound["reason"].endswith(mcp_server._TOO_MANY)

    unbalanced_commas = _decide("Bash", {"command": "cp n " + "{a," * 2000 + "x"})
    assert unbalanced_commas["allow"] is False
    assert unbalanced_commas["reason"].endswith(mcp_server._TOO_MANY)

    three_hundred_alternatives = _decide("Bash", {"command": f"cp n {_brace_list('a', 300)}"})
    assert three_hundred_alternatives["allow"] is False
    assert three_hundred_alternatives["reason"].endswith(mcp_server._TOO_MANY)

    # (R5) `{a,b}` x 40 is 2**40 alternatives if ever built in full; `_brace_absorb` refuses once the
    # running product would pass the budget, long before that, so this must return quickly.
    forty_times = _decide("Bash", {"command": "echo " + "{a,b}" * 40})
    assert forty_times["allow"] is False
    assert forty_times["reason"].endswith(mcp_server._TOO_MANY)

    # Letter ranges expand in full (`_brace_sequence`): `{a..c}` is `a b c`, all inside.
    letter_range_inside = _decide("Bash", {"command": "ls {a..c}"})
    assert letter_range_inside["allow"] is True, letter_range_inside["reason"]


@pytest.mark.skipif(not _WINDOWS, reason="a drive-letter host reads a backslash as a separator")
def test_a_letter_range_through_a_separator_is_refused_on_windows(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)

    # `{Z..a}` runs the ASCII range `Z [ \ ] ^ _ \x60 a`, so one alternative is `\..`, a parent
    # traversal through what Windows reads as a path separator.
    refused = _decide("Bash", {"command": "cp x {Z..a}.."})
    assert refused["allow"] is False
    assert refused["reason"].endswith("outside your workspace")


# 2.1c (design D8), a first slice: rule 5 also matches an absolute glob word against the links it
# finds, not only its literal text (R5's "cp n <workspace, absolute, forward slashes>/u*/" row).
# Reachable only on this slice's own terms -- the glob is the piece's last component, and nothing
# in the piece is `..` -- the fuller walk (more than one glob component, a glob followed by
# further components, an extglob group, `..`) is left to a further slice; see this task's own note
# in tasks.md. PASSES today only by the tail (`'/'`), so this asserts the reason names where the
# match resolves, which FAILS today (measured with a throwaway script first; confirmed by stashing
# just `mcp_server.py` and rerunning, below).
def test_an_absolute_glob_word_is_also_matched_against_the_links_it_finds(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)
    forward = str(workspace).replace("\\", "/")

    refused = _decide("Bash", {"command": f"cp n {forward}/u*/"})
    assert refused["allow"] is False
    assert "it resolves to" in refused["reason"]

    # Controls, unaffected by this slice:
    # a match with no link behind it (the base is listed, but nothing there refuses).
    no_link = _decide("Bash", {"command": f"cp n {forward}/sub/*.py"})
    assert no_link["allow"] is True, no_link["reason"]
    # the glob matches nothing at all, so there is no entry to walk a tail through.
    not_last = _decide("Bash", {"command": f"cp n {forward}/nomatch*/x"})
    assert not_last["allow"] is True, not_last["reason"]
    # a relative glob reaches rule 6, which this slice does not touch.
    relative = _decide("Bash", {"command": "cp n u*/x"})
    assert relative["allow"] is True, relative["reason"]


# 2.1c (design D8 step 4), a further slice: a glob-holding component need not be the piece's last
# one -- the literal components after it are walked too, one at a time, with no new listing (they
# hold no glob character to match against). This is D8 step 4's walk, sized down to exclude `..`
# anywhere in the piece (still returns None for that, left to a further slice): a literal
# component after the glob is read by `os.lstat` (`_is_link_path`, since it has no `DirEntry`),
# and, if it is a link, judged and followed to its `realpath` the same way a matched glob entry
# is. Reachable only through the fixture's `sub/@s/p` shape (a plain directory matched by the
# glob, holding a link in its own literal tail) and `up`/`x` (a glob match that is itself a link,
# with a literal tail after it) -- before this slice, `_glob_links` returned None the moment the
# glob was not the piece's last component, so neither reached a link at all. PASSES today only by
# the tail (`'/p'`/`'/x'`); measured first with a throwaway script
# (`testbed/scratch/measure_glob_tail.py`, gitignored, not committed) against the real fixture
# shape, then confirmed by stashing just `mcp_server.py` and rerunning, below.
def test_an_absolute_glob_word_s_tail_is_also_walked_through_a_link(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)
    forward = str(workspace).replace("\\", "/")

    # The glob matches `sub/@s`, a plain (non-link) directory; the link is in the literal
    # component after it (`p`, to the fixture's outside target).
    through_tail_link = _decide("Bash", {"command": f"cp n {forward}/sub/@s*/p"})
    assert through_tail_link["allow"] is False
    assert "it resolves to" in through_tail_link["reason"]

    # The glob match itself is the link (`up`), with a literal tail (`x`) after it -- already
    # refused by the first slice's own judgement of the matched entry, but the walk must still
    # reach that judgement rather than bailing out for having a non-empty tail.
    through_glob_link = _decide("Bash", {"command": f"cp n {forward}/u*/x"})
    assert through_glob_link["allow"] is False
    assert "it resolves to" in through_glob_link["reason"]

    # Control: the same shape, but the tail component does not exist. `lstat` raises, read as
    # "not a link" (design "What each changed route returns": a name that does not exist still
    # moves the branch), so nothing is judged and the word stands allowed.
    missing_tail = _decide("Bash", {"command": f"cp n {forward}/sub/@s*/missing"})
    assert missing_tail["allow"] is True, missing_tail["reason"]


# D8 step 4, a further slice: a `..` in the tail moves the branch to its real parent and is judged
# there (R6), naming where it lands through `_resolves_elsewhere` even though the piece as written
# reads as inside (R7) -- this needs each branch to carry its listed path beside its real one, since
# they diverge the moment a link is followed. Reachable through the fixture's own `sub/l` -> `work`
# link (R6's worked example, shallower than the link): before this slice `_glob_links` bailed to
# `None` the moment any component was `..`, so the literal reading alone stood, and
# `realpath`'s lexical `..` handling resolved `sub/l*/..` to `sub` -- inside. PASSES today only by
# the literal reading; measured first with a throwaway script
# (`testbed/scratch/measure_glob_dotdot.py`, gitignored, not committed) against the real fixture
# shape, then confirmed by stashing just `mcp_server.py` and rerunning, below.
def test_an_absolute_glob_word_s_tail_dotdot_moves_the_branch_through_a_link(
    workspace, monkeypatch
):
    monkeypatch.setenv("HUB_URL", _HUB)
    forward = str(workspace).replace("\\", "/")

    # `sub/l` is a junction/symlink to `work` itself (R6's own worked example, shallower than the
    # link): the glob matches it, is followed inside, and the `..` after it climbs to `work`'s
    # parent, outside.
    through_link = _decide("Bash", {"command": f"cp n {forward}/sub/l*/.."})
    assert through_link["allow"] is False
    assert "it resolves to" in through_link["reason"]

    # Control: the glob matches a plain (non-link) directory (`@s`); the `..` after it lands back
    # at `sub`, inside, with no link ever followed, so nothing refuses.
    stays_inside = _decide("Bash", {"command": f"cp n {forward}/sub/@s*/.."})
    assert stays_inside["allow"] is True, stays_inside["reason"]

    # Control: the same link, but as a relative word -- reached through rule 6, which this change
    # has not yet wired to `_glob_links` (task 2.2). Stays allowed until that task is built.
    relative = _decide("Bash", {"command": "cp n sub/l*/.."})
    assert relative["allow"] is True, relative["reason"]


# D8 step 2's bracket relaxation, re-derived from the design text again (not iteration 19's own
# reading) and sized the same way: a bracket expression the piece's last component holds is kept
# exact for `fnmatch` when it is one `fnmatch` already reads as the shell does, and relaxed to `?`
# only where it cannot (it opens with `!`/`^`, or holds a `[`, `\` or backtick). Each row PASSES
# today only by the tail; measured first with a throwaway script against a real junction before
# trusting this test.
def test_an_absolute_glob_word_s_bracket_expression_is_relaxed_like_the_shell_reads_it(
    workspace, monkeypatch
):
    monkeypatch.setenv("HUB_URL", _HUB)
    forward = str(workspace).replace("\\", "/")

    # Exact bracket match: `[u]p` matches only `up`, the link.
    exact = _decide("Bash", {"command": f"cp n {forward}/[u]p/"})
    assert exact["allow"] is False
    assert "it resolves to" in exact["reason"]

    # Control: `[0-9]` is also matched exactly -- no one-character digit name exists, so nothing
    # matches and the word stands allowed (R8's own worked example).
    no_match = _decide("Bash", {"command": f"cp n {forward}/[0-9]/"})
    assert no_match["allow"] is True, no_match["reason"]

    # Bash negation: `fnmatch` reads `^` literally, so `[^a]` relaxes to `?` and matches `up`.
    negated = _decide("Bash", {"command": f"ls {forward}/[^a]p/"})
    assert negated["allow"] is False
    assert "it resolves to" in negated["reason"]

    # PowerShell reads `!` literally where bash negates with it; either way `fnmatch` cannot read
    # it, so `[!a]` also relaxes to `?` and matches `up`.
    bang = _decide("Bash", {"command": f"cp n {forward}/[!a]p/"})
    assert bang["allow"] is False
    assert "it resolves to" in bang["reason"]

    # A POSIX class `fnmatch` has no notion of: `[[:alpha:]]` relaxes to `?` and matches `up`.
    posix_class = _decide("Bash", {"command": f"cp n {forward}/[[:alpha:]]p/"})
    assert posix_class["allow"] is False
    assert "it resolves to" in posix_class["reason"]


# ("The bounds") `_glob_links` charges `budget.glob_entries_examined` as each directory entry is
# read from `os.scandir`, not after the whole listing is built, and refuses with `_TOO_MANY` once
# the running total passes `_GLOB_ENTRY_BUDGET` -- the bound task 2.0's `_Budget` names for this,
# which had no hook into `_glob_links` before this slice (an unbounded directory could be listed in
# full, and held in memory as a Python list, before anything was ever charged or checked). Uses a
# pattern that matches no entry in the fixture's workspace root (`nomatch*`, the same one the
# neighbouring "not the last component" control uses) so the refusal can only come from the budget,
# never from a link match racing it -- `os.scandir`'s listing order is unspecified. Measured
# directly against `_decide` first (testbed/scratch/measure_glob_budget.py, gitignored, not
# committed, run three times to rule out order-dependence): with the bound monkeypatched to 2
# against the fixture's 5 direct entries (`sub`, `up`, `in`, `a'b`, `a@b`), the call was wrongly
# **unbounded** before this slice and is now refused as too many, every time.
def test_the_glob_link_walk_s_entries_are_charged_against_the_decide_budget(workspace, monkeypatch):
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)
    forward = str(workspace).replace("\\", "/")

    within_bound = _decide("Bash", {"command": f"cp n {forward}/nomatch*/"})
    assert within_bound["allow"] is True, within_bound["reason"]

    monkeypatch.setattr(mcp_server, "_GLOB_ENTRY_BUDGET", 2)
    over_bound = _decide("Bash", {"command": f"cp n {forward}/nomatch*/"})
    assert over_bound["allow"] is False
    assert over_bound["reason"].endswith(mcp_server._TOO_MANY)


# 2.2, a first slice (design D2 step 2, D3's extglob units): an unquoted extglob group -- a
# trigger (`@ ? * + !`) directly followed by `(`, up to its matching `)` -- is kept as one unit
# through both the lexer and rule 6's piece reading, rather than fragmented at the `(`, `|` and `@`
# it contains. Two layers were both wrong before this slice: `_lex` already ends an argument at any
# bare `(`, `|` or `)` (`_ARGUMENT_ENDS`, mimicking a real subshell/pipe), which splits
# `@(..)/x` into three separate arguments ("@", "..", "/x") before rule 6 ever runs -- so rule 6's
# own `_PIECE_BREAKS_RE` split (which already left `)` alone, for regex back-references) was never
# reached by an intact group at all. Measured against real Git Bash 5.2.37 with `extglob` on and
# `globskipdots` off (`testbed/scratch/measure_extglob.sh`, gitignored, not committed):
# `@(..)/x`, `?(..)/x` and `@(.|..)/x` all expand to `../x` in a directory one level inside the
# workspace. Measured against `_decide` next (testbed/scratch/measure_extglob_decide.py, gitignored,
# not committed) before writing this test; confirmed by stashing just `mcp_server.py` and rerunning.
#
# Measured against old code too (git-stashing just `mcp_server.py`), row by row, rather than
# assumed: every dotdot-capable row above was already refused before this slice, but each for an
# accidental reason -- the lexer's fragmentation happens to isolate a bare `..` as its own argument
# (`@(..)/x`, `?(..)/x`, `@(.|..)/x`, `sub@(..)x/y`), which rule 4's `cut == ".."` then catches by
# coincidence, or (`@(.*)/y`) isolates a spurious absolute-looking `/y` fragment that is outside for
# an unrelated reason. Each reason before this slice names only the isolated fragment (`'..'`,
# `'/y'`); after it, the reason names the whole word, because the group survives intact into
# `_judge_pieces`/`_rewrite_dotdot_globs` rather than being torn apart by `_lex` or by
# `_PIECE_BREAKS_RE`. Two rows below are not just a reason change: `@(a|b)/x` and `sub/@(..)/x` were
# both wrongly **refused** before this slice (the same accidental fragmentation: an isolated `/x`
# read as absolute, and an isolated bare `..` read apart from the `sub` it is actually glued after,
# which cancels it out), and are correctly allowed after.
def test_an_unquoted_extglob_group_is_kept_as_one_unit_through_the_lexer_and_rule_6(
    workspace, monkeypatch
):
    monkeypatch.setenv("HUB_URL", _HUB)

    # The design's own worked example: run from the workspace root, so `..` is genuinely outside.
    bare_star_trigger = _decide("Bash", {"command": "cp n @(..)/x"})
    assert bare_star_trigger["allow"] is False
    assert bare_star_trigger["reason"].startswith("'@(..)/x'")

    question_trigger = _decide("Bash", {"command": "cp n ?(..)/x"})
    assert question_trigger["allow"] is False
    assert question_trigger["reason"].startswith("'?(..)/x'")

    # One of two alternatives begins with `.` -- the whole component is dotdot-capable.
    one_alternative = _decide("Bash", {"command": "cp n @(.|..)/x"})
    assert one_alternative["allow"] is False
    assert one_alternative["reason"].startswith("'@(.|..)/x'")

    # Refused before this slice too, but by accident (see the note above) -- the reason now
    # names the whole word rather than an isolated fragment.
    glob_alternative = _decide("Bash", {"command": "cp n @(.*)/y"})
    assert glob_alternative["allow"] is False
    assert glob_alternative["reason"].startswith("'@(.*)/y'")

    glued_prefix = _decide("Bash", {"command": "cp n sub@(..)x/y"})
    assert glued_prefix["allow"] is False
    assert glued_prefix["reason"].startswith("'sub@(..)x/y'")

    # Control: neither alternative is dotdot-capable, so the component is a literal (if odd) name,
    # lexically inside the workspace -- stays allowed.
    no_dot_alternative = _decide("Bash", {"command": "cp n @(a|b)/x"})
    assert no_dot_alternative["allow"] is True, no_dot_alternative["reason"]

    # Control: the same group one level inside the workspace resolves to the workspace root
    # itself (`sub`'s parent) -- genuinely inside, not merely allowed by accident.
    resolves_inside = _decide("Bash", {"command": "cp n sub/@(..)/x"})
    assert resolves_inside["allow"] is True, resolves_inside["reason"]

    # Control: an unbalanced trigger+`(` is not a group, and falls through to the ordinary
    # `_ARGUMENT_ENDS` splitting unaffected by this slice.
    unbalanced = _decide("Bash", {"command": "echo a@(b"})
    assert unbalanced["allow"] is True, unbalanced["reason"]


# 2.2's second slice -- task 1.4g (design D2 step 6, R8, the third review's HIGH): after the
# pieces, the undivided value is also judged as the path it spells. A break character (`@`, `'`,
# `(`, `:`) is also a name character to the shell, so a link or a physical `..` sitting right
# before one was never resolved by the piece split alone -- each piece on its own side of the
# break looks like an ordinary relative name. Measured against `_decide` directly first
# (`testbed/scratch/measure_whole_value.py`, gitignored, not committed), row by row, and again by
# `git stash`ing just `mcp_server.py`.
#
# Confirmed by stashing: `sub/@s/p/x` (a piece-level split leaves `sub`, `s`, `p`, `x`, none of
# which crosses the `@s/p` link the fixture sets up; the undivided value does), the same through
# `-Destination:` (PowerShell's colon-joined option, dropped first by `_whole_value`) and through a
# `'` (`"a'b/up/x"`), `sub/@s/p/*` (no `_glob_links` match needed here -- the link is literal, only
# the trailing component is a glob, so the *literal* undivided value already resolves through it,
# exactly as 1.4g's own text says: "the literal whole value is what refuses"), and `"a@b/l/../y"`
# (`a@b/l` is a link back to the workspace root itself, so the undivided value's own `..` lands one
# level above it -- D12's physical reading, already built, fires automatically inside
# `_judge_path`/`_where`, no new wiring needed here). The run-on rows (`"../work(a"`,
# `'../work@'`) are the ones the design calls out by name: the piece `../work` is the workspace's
# own root, allowed on its own, but the undivided value names a *different* sibling that sits
# outside -- a break the piece split cannot see because nothing glues the two sides together once
# split at `(`.
#
# Windows-only (on a drive-letter host the colons stay divided, never judged whole-with-colons,
# D9): `grep 'ORM\|:2580' f` and `sed -E 's/(:700)/(:697)/g' f`, both from this repository's own
# transcripts, are the task's named example of what judging whole-with-colons would wrongly refuse
# (`ntpath.realpath` reads `|:2580`/`(:700)` as a drive and drops the real prefix -- confirmed by
# temporarily removing the `_DRIVE_LETTERS` guard in `_judge_whole_value` and rerunning, in the
# same scratch script). POSIX-only: a directory literally named `t:d` (no name on Windows can hold
# a `:`) with a link `up` -> outside; `cp n t:d/up/x` is refused, naming where it resolves (the
# whole value with its colon kept, since POSIX judges it both ways per D2 step 6) -- not measurable
# on this machine, left to the `hub-test` CI job (`ubuntu-latest`).
def test_the_undivided_whole_value_is_judged_too_1_4g(workspace, monkeypatch):
    monkeypatch.setenv("HUB_URL", _HUB)

    glued_at_at = _decide("Bash", {"command": "cp n sub/@s/p/x"})
    assert glued_at_at["allow"] is False
    assert "resolves to" in glued_at_at["reason"]

    colon_joined_option = _decide("PowerShell", {"command": "Copy-Item n -Destination:sub/@s/p/x"})
    assert colon_joined_option["allow"] is False
    assert "resolves to" in colon_joined_option["reason"]

    glued_at_quote = _decide("Bash", {"command": 'cp n "a\'b/up/x"'})
    assert glued_at_quote["allow"] is False
    assert "resolves to" in glued_at_quote["reason"]

    glob_base_is_the_link = _decide("Bash", {"command": "cp n sub/@s/p/*"})
    assert glob_base_is_the_link["allow"] is False
    assert "resolves to" in glob_base_is_the_link["reason"]

    dotdot_past_a_link = _decide("Bash", {"command": 'cp n "a@b/l/../y"'})
    assert dotdot_past_a_link["allow"] is False
    assert "resolves to" in dotdot_past_a_link["reason"]

    run_on_paren = _decide("Bash", {"command": 'cp n "../work(a"'})
    assert run_on_paren["allow"] is False
    assert run_on_paren["reason"] == "'../work(a' is outside your workspace"

    run_on_at = _decide("Bash", {"command": "mkdir '../work@'"})
    assert run_on_at["allow"] is False
    assert run_on_at["reason"] == "'../work@' is outside your workspace"

    # Windows-only controls: the guard in `_judge_whole_value` keeps a drive-letter host from ever
    # reading the undivided value with its colons kept (D9) -- without it, both would be wrongly
    # refused (confirmed directly, see the comment above).
    if _WINDOWS:
        line_reference = _decide("Bash", {"command": "grep 'ORM\\|:2580' f"})
        assert line_reference["allow"] is True, line_reference["reason"]
        regex_with_colons = _decide("Bash", {"command": "sed -E 's/(:700)/(:697)/g' f"})
        assert regex_with_colons["allow"] is True, regex_with_colons["reason"]

    # POSIX-only: a directory `work/t:d` holding a link `up` -> outside, judged whole with its
    # colon kept (D2 step 6 runs both readings on POSIX). Not buildable on this Windows machine
    # (NTFS refuses a `:` in a file name outside the drive position); left to CI's `hub-test` job.
    if not _WINDOWS:
        colon_in_a_directory_name = workspace / "t:d"
        colon_in_a_directory_name.mkdir()
        _link(colon_in_a_directory_name / "up", workspace.parent / "outside")
        posix_colon_component = _decide("Bash", {"command": "cp n t:d/up/x"})
        assert posix_colon_component["allow"] is False
        assert "resolves to" in posix_colon_component["reason"]

    # Controls, allowed: a plain word reaching rule 6 that holds a `::` but no link or `..` behind
    # it must not be refused merely for being judged whole with its colons on POSIX.
    no_link_or_dotdot = _decide("Bash", {"command": "ls lib/Foo::Bar.pm"})
    assert no_link_or_dotdot["allow"] is True, no_link_or_dotdot["reason"]
    redirect_glued_to_a_glob = _decide("Bash", {"command": "sh -c 'ls 2>&1/x'"})
    assert redirect_glued_to_a_glob["allow"] is True, redirect_glued_to_a_glob["reason"]

    # Control: the same shape with no link behind it stays allowed -- the new step only adds a
    # refusal through a real link or a physical `..`, never a bare glued name.
    no_link_behind_it = _decide("Bash", {"command": "cp n sub/@s/q"})
    assert no_link_behind_it["allow"] is True, no_link_behind_it["reason"]
