"""F696's remainder (operator decision 2026-10-18): under "Workspace only", grep's pattern is text,
not a path, and a bare `$PWD` names the directory the command runs in.

d0a27d4 exempted sed/awk/cut/tr scripts; grep's pattern was left judged (accepted costs 1.5a2 /
1.7c1) and a bare `$PWD` refused (design D2, F401). Now `grep '\\.\\./' src` and `echo $PWD` pass,
while every file grep reads (`-f`, `--file`, each file operand) is still judged, and `$PWD` that
anything derives a path from (`$PWD/..`, `$(dirname $PWD)`, `(Split-Path $PWD)`, `x=$PWD`) or
that the command reassigns stays refused.
"""

from __future__ import annotations

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    ws.mkdir()
    (ws / "f").write_text("x")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:8016")
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


@pytest.mark.parametrize(
    "command",
    [
        "grep '$HOME' f",
        r"grep -rn '\.\./' src",
        "grep -e '../a' f",
        "grep --regexp=../a f",
        "grep -rnA3 '../a' f",
        "grep -m 3 '../a' f",
        "grep -i -e /etc/passwd -e '../x' f",
        "egrep '(\\.\\./)+' f",
        "git log --oneline | grep '/usr/'",
    ],
)
def test_a_grep_pattern_is_not_a_path(workspace, command):
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is True, decision


@pytest.mark.parametrize(
    "command",
    [
        # Every file grep reads is judged.
        "grep -f ../x f",
        "grep --file=../x f",
        "grep -rf ../x f",
        "grep foo ../x",
        "grep -e foo ../x",
        "grep -e foo -e bar ../x",
        "grep -m 3 foo ../x",
        "grep --exclude-from ../x pat f",
        "grep -- -x ../x",
        # A pattern the shell changes is not plain text.
        'grep "$HOME" f',
        "grep $HOME f",
        "grep $(cat p) ../x",
    ],
)
def test_a_file_grep_reads_is_still_judged(workspace, command):
    assert _decide("Bash", {"command": command})["allow"] is False


@pytest.mark.parametrize(
    "tool, command",
    [
        ("Bash", "echo $PWD"),
        ("Bash", "echo ${PWD}"),
        ("Bash", 'echo "$PWD"'),
        ("Bash", "ls $PWD"),
        ("Bash", "cd sub && ls $PWD"),
        ("PowerShell", "Copy-Item x $PWD"),
        ("PowerShell", "Get-ChildItem ${PWD}"),
        ("PowerShell", 'Write-Output "$PWD"'),
    ],
)
def test_a_bare_pwd_names_the_workspace(workspace, tool, command):
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is True, decision


@pytest.mark.parametrize(
    "tool, command",
    [
        ("Bash", "cp x $PWD/.."),
        ("Bash", "cp x $PWD.."),
        ("Bash", "cp x ${PWD}/.."),
        ("Bash", "cp x ${PWD%/*}"),
        ("Bash", "cp x $(dirname $PWD)"),
        ("Bash", "cp x `dirname $PWD`"),
        ("Bash", "x=$PWD; cp a $(dirname $x)"),
        ("Bash", "PWD=/ cp x $PWD"),
        ("Bash", "PWD=/; cp x $PWD"),
        ("Bash", "export PWD=/tmp; cp x $PWD"),
        ("Bash", 'eval P"WD"=/; cp x $PWD'),
        ("Bash", "read PWD; cp x $PWD"),
        ("Bash", "echo $OLDPWD"),
        ("Bash", "echo '$PWD'"),
        ("Bash", "bash -c 'cp n $PWD'"),
        ("PowerShell", "Copy-Item x $PWD.Path"),
        ("PowerShell", "Copy-Item x (Split-Path $PWD)"),
        ("PowerShell", "Copy-Item x $(Split-Path $PWD)"),
        ("PowerShell", "$PWD = 'C:\\'; Copy-Item x $PWD"),
        ("PowerShell", "Set-Variable PWD C:\\; Copy-Item x $PWD"),
        ("PowerShell", "1 | ForEach-Object { Split-Path $PWD }"),
    ],
)
def test_a_pwd_something_derives_from_is_still_refused(workspace, tool, command):
    assert _decide(tool, {"command": command})["allow"] is False
