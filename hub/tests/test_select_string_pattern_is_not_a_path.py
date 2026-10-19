"""F781: `Select-String`'s pattern is not a path.

The Architect's read-only `Select-String -Path openspec\\...\\tasks.md -Pattern '- \\[ \\]'` was
refused as "'\\' is outside your workspace" and ended its Copilot turn. F661 exempted the pattern
of an expression-mode `-match`; a cmdlet's `-Pattern` value, or its first positional argument
when `-Pattern` is not named, is the same thing in command mode. Copilot's shell calls are read
in both dialects ("Shell"), so both must agree. Only a quoted literal is exempt, and only where
the parameter is unambiguously `-Pattern`; every path the command names is judged as before.
"""

from __future__ import annotations

import os

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    (ws / "sub").mkdir(parents=True)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


OUT = r"C:\Windows\x" if os.sep == "\\" else "/etc/x"
KEYS = ("PowerShell", "Bash", "Shell")


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize(
    "command",
    [
        # The command the Architect ran, verbatim but for the change name.
        r"Select-String -Path openspec\changes\a\tasks.md -Pattern '- \[ \]'",
        r"Select-String -Path sub\tasks.md -Pattern '- \[x\]' | Select-Object -First 3",
        r"Select-String '- \[ \]' sub\tasks.md",
        r"Get-Content sub\a.md | sls '\\.git\\'",
        r"Select-String -CaseSensitive -Path sub\a.md -Patt '^\s*- \[ \]'",
    ],
)
def test_a_select_string_pattern_is_not_judged_as_a_path(workspace, key, command):
    assert _decide(key, {"command": command})["allow"] is True


def test_a_double_quoted_pattern_is_exempt_in_the_powershell_reading(workspace):
    # Bash's lexer does not count a double-quoted word holding a backslash escape as one plain
    # literal, so the bash (and the both-dialect "Shell") reading still judges it.
    command = r'Select-String -SimpleMatch "\\server" sub\a.md'
    assert _decide("PowerShell", {"command": command})["allow"] is True


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize(
    "command",
    [
        f"Select-String -Path '{OUT}' -Pattern 'a'",
        f"Select-String 'a' '{OUT}'",
        f"Select-String -Pattern 'a' '{OUT}'",
        f"Select-String -LiteralPath '{OUT}' 'a'",
        # An ambiguous prefix (`-Pa`: Path or Pattern) is not taken to be the pattern.
        f"Select-String -Pa '{OUT}' 'a'",
        # A parameter this reading does not know may take the next argument: nothing after it is
        # taken to be the pattern.
        f"Select-String -Bogus '{OUT}' sub\\a.md",
        f"Select-String -Pattern 'a' sub\\a.md; Get-Content '{OUT}'",
        f"Write-Output -Pattern '{OUT}'",
    ],
)
def test_every_path_select_string_names_is_still_judged(workspace, key, command):
    assert _decide(key, {"command": command})["allow"] is False


def test_an_unquoted_first_argument_is_judged_as_before(workspace):
    # Only a quoted literal is exempt. (Bash reads `C:\Windows\x` unquoted as `C:Windowsx`.)
    assert _decide("PowerShell", {"command": f"Select-String {OUT} sub\\a.md"})["allow"] is False
