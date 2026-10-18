"""F676: under "Workspace only", a command whose arguments another command produces is not allowed
on its text.

Measured in research 2026-10-02 §1: `echo Li4vb3V0c2lkZS0xMDAy | base64 -d | xargs touch` was
allowed as "inside your workspace", and run in Git Bash from the workspace it created
`../outside-1002`. The judge reads the command's text, and a pipe-fed argument is the case where the
text, by construction, does not hold the path.
"""

from __future__ import annotations

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    ws.mkdir()
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


def _refused_as_unbound(decision):
    assert decision["allow"] is False, decision
    assert "what another command outputs" in decision["reason"]
    assert "ask_user" in decision["reason"]


@pytest.mark.parametrize(
    "command",
    [
        # The research's measured rows.
        "echo Li4vb3V0c2lkZS0xMDAy | base64 -d | xargs touch",
        "cat names.txt | xargs touch",
        # The same shape by other routes.
        "xargs -a names.txt rm",
        "xargs rm < names.txt",
        "cat names.txt | command xargs -0 rm -rf",
        "cat names.txt | bin/xargs.exe rm",
        "cat names.txt | parallel rm",
        "cat script.txt | bash",
        "cat script.txt | sh -s",
        "cat script.txt | python3",
        "cat script.txt | node -",
        'cat names.txt | while read f; do rm -rf "$f"; done',
        "touch $(echo Li4vb3V0c2lkZQ== | base64 --decode)",
        "touch `echo Li4vb3V0c2lkZQ== | base64 -d`",
        "echo Li4v | base64 -d | tee name.txt",
        "pwsh -EncodedCommand ZQBjAGgAbwA=",
    ],
)
def test_a_bash_command_fed_from_another_commands_output_is_refused(workspace, command):
    _refused_as_unbound(_decide("Bash", {"command": command}))


@pytest.mark.parametrize(
    "command",
    [
        "Get-Content names.txt | ForEach-Object { New-Item $_ }",
        "Get-Content names.txt | % { Remove-Item -Recurse $_ }",
        "Get-Content names.txt | Remove-Item",
        "Get-Content script.txt | Invoke-Expression",
        "iex (Get-Content script.txt -Raw)",
        "New-Item ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('Li4vYXcteA==')))",
        "& ([scriptblock]::Create((Get-Content s.txt -Raw)))",
        "powershell -enc ZQBjAGgAbwA=",
    ],
)
def test_a_powershell_command_fed_from_another_commands_output_is_refused(workspace, command):
    _refused_as_unbound(_decide("PowerShell", {"command": command}))


@pytest.mark.parametrize(
    "tool,command",
    [
        ("Bash", "ls | wc -l"),
        ("Bash", "git log --oneline | head -5"),
        ("Bash", "cat data.json | python -m json.tool"),
        ("Bash", "cat data.json | python3 -c 'import json,sys; print(json.load(sys.stdin))'"),
        ("Bash", "printf hi | bash -c 'cat'"),
        ("Bash", "echo aGk= | base64 -d"),
        ("Bash", "base64 -d blob.b64 > blob.bin"),
        ("Bash", "pytest -q 2>&1 | tail -20"),
        ("Bash", "npm run build &> build.log"),
        ("Bash", "grep -n 'a|b' file.txt"),
        ("Bash", "echo 'cat x | xargs rm'"),
        ("Bash", "make test && echo done || echo failed"),
        ("PowerShell", "Get-ChildItem *.tmp | Remove-Item"),
        ("PowerShell", "Get-Content data.txt | ForEach-Object { $_.Length }"),
        ("PowerShell", "Get-Content data.txt | Select-String 'x' | Measure-Object"),
        ("PowerShell", "& git status"),
        ("PowerShell", "Write-Output 'a | iex'"),
    ],
)
def test_ordinary_pipelines_are_still_allowed(workspace, tool, command):
    """A pipe whose last stage reads, counts or prints is ordinary work: only a stage that takes
    paths or code from its input is held back."""
    assert _decide(tool, {"command": command})["allow"] is True
