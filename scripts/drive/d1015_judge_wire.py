"""Acceptance drive for F601 + F661: the Workspace judge, asked over the real tool-server wire.

Spawns `hub/hub/mcp_server.py` the way a Hub spawns it for a Claude run (stdio JSON-RPC, the
Workspace posture, `AW_WORKSPACE_DIR` naming a scratch workspace) and asks `approve_tool_call` about
PowerShell commands. Two failures, opposite directions:

- F601: provider drives written without a separator (`Env:PATH`, `HKCU:Software\\X`) were allowed
  as "inside your workspace". They name no file in the workspace and must be refused.
- F661: a quoted regex on the right of `-notmatch` was read as a path (`'\\\\.git\\\\'` as a UNC
  root, `'...(\\\\|$)'` as an expansion), refusing read-only listings. They must be allowed.

Plus controls that must keep their answer. Nothing is executed: the judge only answers.

  py -3.11 scripts/drive/d1015_judge_wire.py

Exit 1 when any row has the wrong answer.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

MCP_SERVER = pathlib.Path(__file__).resolve().parents[2] / "hub" / "hub" / "mcp_server.py"

#: (label, command, expected behavior)
ROWS = [
    # F601: provider drives, no separator -- were allowed as inside the workspace.
    ("F601 Remove-Item HKCU:Software", r"Remove-Item HKCU:Software\AwProbe", "deny"),
    ("F601 New-ItemProperty HKCU:Environment",
     "New-ItemProperty -Path HKCU:Environment -Name X -Value y", "deny"),
    ("F601 Remove-Item Env:PATH", "Remove-Item Env:PATH", "deny"),
    ("F601 Remove-Item Function:prompt", "Remove-Item Function:prompt", "deny"),
    ("F601 Set-Item Variable:x", "Set-Item Variable:ErrorActionPreference Stop", "deny"),
    ("F601 lowercase hklm:", "Remove-Item hklm:Software", "deny"),
    ("control: a New-PSDrive root is judged as a path",
     "New-PSDrive -Name Q -PSProvider Registry -Root HKCU:\\ ; Remove-Item Q:Software",
     "deny"),
    # F661: a quoted pattern of a comparison operator, read-only -- was refused.
    ("F661 -notmatch '\\\\.git\\\\'",
     r"Get-ChildItem -Recurse -Force -File | Where-Object { $_.FullName -notmatch '\\.git\\' } | Resolve-Path -Relative",
     "allow"),
    ("F661 -notmatch '\\\\.git(\\\\|$)'",
     r"Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '\\.git(\\|$)' } | ForEach-Object { $_.Name }",
     "allow"),
    # Controls: unchanged answers.
    ("control: HKCU:\\Software with a separator", r"Get-Content HKCU:\Software", "deny"),
    ("control: Temp:foo", "Copy-Item x Temp:foo", "deny"),
    ("control: a plain listing", "Get-ChildItem -Recurse -File", "allow"),
    ("control: an outside path is still outside",
     r"Get-ChildItem C:\Windows | Where-Object { $_.Name -match 'x' }", "deny"),
    ("control: command mode -match is an argument, judged",
     r"Write-Output x -match 'C:\Windows\System32'", "deny"),
    # An ASCII-quoted pattern naming an outside path is only a pattern; the same pattern in Unicode
    # quotes gets no exemption (wpc2-g) and is judged as today.
    ("F661 an ASCII-quoted pattern is not a path",
     r"Get-ChildItem | Where-Object { $_.FullName -match 'C:\Windows' }", "allow"),
    ("control: Unicode quotes do not qualify",
     "Get-ChildItem | Where-Object { $_.FullName -match \u2018C:\\Windows\u2019 }", "deny"),
]


def ask(command, workspace):
    env = dict(os.environ)
    env.update({"AW_WORKSPACE_DIR": workspace, "HUB_URL": "http://127.0.0.1:9", "AW_PERMISSION_POSTURE": ""})
    env.pop("AW_RUN_TOKEN", None)
    proc = subprocess.Popen(
        [sys.executable, str(MCP_SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1, env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def read():
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit("the tool server closed stdout before answering")
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "d1015", "version": "1"}}})
        read()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "approve_tool_call",
            "arguments": {"tool_name": "PowerShell", "input": {"command": command},
                          "tool_use_id": "toolu_d1015"}}})
        return json.loads(read()["result"]["content"][0]["text"])
    finally:
        proc.kill()


def main():
    failures = []
    with tempfile.TemporaryDirectory() as workspace:
        for label, command, expected in ROWS:
            answer = ask(command, workspace)
            got = answer["behavior"]
            ok = got == expected
            note = answer.get("message", "")[:110]
            print(f"[{'PASS' if ok else 'FAIL'}] {label}: {got} (want {expected}) {note}")
            if not ok:
                failures.append(label)
            if expected == "deny" and got == "deny" and "inside your workspace" in note:
                print("       but the refusal calls it inside the workspace")
    print("FAILED: " + "; ".join(failures) if failures else "ALL PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
