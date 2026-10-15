"""The Workspace judge reads paths, not patterns or provider drives (F601 + F661).

`spec/changes/the-workspace-judge-reads-paths-not-patterns`. Two failures of the PowerShell
reading, in opposite directions: provider drives written without a separator were allowed as
"inside your workspace" (F601), and a quoted regular expression on the right of `-notmatch` was
read as a UNC root or an expansion, refusing a read-only listing (F661). The wire is driven by
`scripts/drive/d1015_judge_wire.py`; these pin the grammar, including what the exemption must not
open.
"""

from __future__ import annotations

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    (ws / "sub").mkdir(parents=True)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


def ps(command):
    return _decide("PowerShell", {"command": command})


def shown(text):
    """How a refusal quotes a word: each backslash doubled (F656 is the legibility finding)."""
    return text.replace("\\", "\\\\")


# --- F601: provider drives ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, word",
    [
        (r"Remove-Item HKCU:Software\AwG7Probe", r"HKCU:Software\AwG7Probe"),
        ("New-ItemProperty -Path HKCU:Environment -Name X -Value y", "HKCU:Environment"),
        ("Remove-Item Env:PATH", "Env:PATH"),
        ("Remove-Item Function:prompt", "Function:prompt"),
        ("Set-Item Variable:ErrorActionPreference Stop", "Variable:ErrorActionPreference"),
        ("Remove-Item Alias:ls", "Alias:ls"),
        ("Get-ChildItem Cert:", "Cert:"),
        ("Set-Item WSMan:localhost\\MaxEnvelopeSizekb 1024", "WSMan:localhost\\MaxEnvelopeSizekb"),
        ("Remove-Item hklm:Software", "hklm:Software"),
        (r"Get-Content HKCU:\Software", r"HKCU:\Software"),
        ("Remove-Item -Path:Env:PATH", "-Path:Env:PATH"),
    ],
)
def test_a_provider_drive_is_outside_and_named(workspace, command, word):
    decision = ps(command)
    assert decision["allow"] is False
    assert f"'{shown(word)}' is outside your workspace" in decision["reason"]


def test_a_colon_word_that_is_no_provider_drive_is_not_refused_for_it(workspace):
    """`HEAD:README.md` is git's syntax, not a drive: 'any name with a colon' would refuse it."""
    assert ps("git show HEAD:README.md")["allow"] is True


def test_the_bash_reading_is_unchanged(workspace):
    """In bash `Env:PATH` is an ordinary file name; the rule is PowerShell's."""
    assert _decide("Bash", {"command": "cat Env:PATH"})["allow"] is True


# --- F661: patterns -----------------------------------------------------------------------------


def test_the_recorded_refusals_are_allowed(workspace):
    """Both commands verbatim from the work-PC drive (run-b175c9ffa621), read-only, inside."""
    first = (
        f"Get-ChildItem -LiteralPath '{workspace}' -Recurse -File | Where-Object {{ $_.FullName "
        r"-notmatch '\\.git(\\|$)' } | ForEach-Object { $_.FullName }"
    )
    second = (
        r"Get-ChildItem -Recurse -Force -File | Where-Object { $_.FullName -notmatch '\\.git\\' }"
        " | Resolve-Path -Relative"
    )
    assert ps(first)["allow"] is True, ps(first)
    assert ps(second)["allow"] is True, ps(second)


@pytest.mark.parametrize(
    "operator",
    [
        "-match",
        "-notmatch",
        "-like",
        "-notlike",
        "-replace",
        "-split",
        "-cmatch",
        "-iNotLike",
        "-csplit",
        "-ireplace",
    ],
)
def test_each_operator_s_pattern_is_not_a_path(workspace, operator):
    assert ps(f"$name {operator} 'C:\\Windows\\*'")["allow"] is True


@pytest.mark.parametrize(
    "command",
    [
        r"5 -match 'C:\Windows'",
        r"$ok = $name -match 'C:\Windows'",
        r"$ok = 'x' -like 'C:\Windows\*'",
        r"$ok=$name -notmatch 'C:\Windows'",
    ],
)
def test_an_expression_after_a_number_or_an_assignment_still_qualifies(workspace, command):
    assert ps(command)["allow"] is True, ps(command)


def test_a_double_quoted_pattern_without_expansion_qualifies(workspace):
    assert ps(r'$x -match "C:\Windows"')["allow"] is True


def test_a_script_block_closed_against_its_pattern_qualifies(workspace):
    assert ps(r"Get-ChildItem | Where-Object {$_.FullName -notmatch '\\.git\\'}")["allow"] is True


# --- What the exemption must not open -----------------------------------------------------------


@pytest.mark.parametrize(
    "command, path",
    [
        # Command mode: `-match` is an argument and the next word reaches the command.
        (r"Write-Output $x -match 'C:\Windows\System32'", "C:\\Windows\\System32"),
        (r"Remove-Item -Path 'C:\Windows\x'", "C:\\Windows\\x"),
        # A new statement or element after the pattern is judged.
        (r"$x -match 'a'; Remove-Item 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"$x -match 'a' | Remove-Item 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"$x -match 'a' -and (Remove-Item 'C:\Windows\x')", "C:\\Windows\\x"),
        # Not the operand: an assignment, and the left side of the comparison.
        (r"$p = 'C:\Windows\x'; Remove-Item $p", "C:\\Windows\\x"),
        (r"'C:\Windows\x' -match 'y'", "C:\\Windows\\x"),
        # A replacement pair is not one literal.
        (r"$x -replace 'a','C:\Windows\x'", "C:\\Windows\\x"),
        # The draft's R2 sweep: none is expression mode where the operand reaches a command.
        (r"7z.exe $x -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r".\tool.exe $x -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"&('Copy-Item') x -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"(Copy-Item $x -match 'C:\Windows\x')", "C:\\Windows\\x"),
        (r"@args -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"$x.Method('C:\Windows\x')", "C:\\Windows\\x"),
        (r"$x -split 'C:\Windows\x', 2", "C:\\Windows\\x"),
        # An assignment's right side is a pipeline: the command gets the operand as an argument.
        (r"$null = robocopy src -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"$r += robocopy src -match 'C:\Windows\x'", "C:\\Windows\\x"),
        (r"$null=robocopy src -match 'C:\Windows\x'", "C:\\Windows\\x"),
    ],
)
def test_a_path_outside_the_pattern_operand_is_still_judged(workspace, command, path):
    decision = ps(command)
    assert decision["allow"] is False, decision
    assert shown(path) in decision["reason"]


def test_a_double_quoted_operand_that_expands_does_not_qualify(workspace):
    decision = ps(r'$x -match "$env:WINDIR\System32"')
    assert decision["allow"] is False


def test_unicode_quotes_do_not_qualify(workspace):
    decision = ps("$x -match \u2018C:\\Windows\u2019")
    assert decision["allow"] is False


def test_an_unquoted_operand_does_not_qualify(workspace):
    assert ps(r"$x -match C:\Windows\x")["allow"] is False


def test_a_quoted_operator_is_not_an_operator(workspace):
    assert ps(r"$x '-match' 'C:\Windows\x'")["allow"] is False


def test_the_bash_reading_of_a_pattern_is_unchanged(workspace):
    """Row 1.7c1's shape: a bash pattern holding a traversal stays refused."""
    assert _decide("Bash", {"command": r"grep -rn '\.\./' src"})["allow"] is False
