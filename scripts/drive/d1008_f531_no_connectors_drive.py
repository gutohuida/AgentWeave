"""Acceptance drive for F531 (Tier 2): a Hub Claude run gets the Hub's MCP server and no other, on `:8010`.

A fresh project with one Haiku agent. One turn, which calls no tool: it reports the names of every tool it was given
whose name starts with `mcp__claude_ai` (Claude lists deferred tools by name in the model's context, so a turn can
name a connector without loading it). Meanwhile the drive reads the spawned `claude` process's command line from the
OS, by a marker word in the turn's message.

- the spawned argv carries `--strict-mcp-config`;
- the turn names no `mcp__claude_ai` tool.

On today's code both fail: the argv has no such flag, and the operator's account connectors (Claude Docs, Drive,
Calendar, Gmail) reach the run. Spends one Haiku turn.

Usage: py -3.11 scripts/drive/d1008_f531_no_connectors_drive.py
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010/api/v1"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
REPO = pathlib.Path(__file__).resolve().parents[2]
HAIKU = "claude-haiku-4-5-20251001"
MARKER = "zebrafinch" + time.strftime("%H%M%S")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path, data, {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def ro(sql, args=()):
    connection = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()


def claude_command_lines():
    """Every running `claude` process's command line (Windows)."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='claude.exe'\" | "
         "ForEach-Object { $_.CommandLine } | ConvertTo-Json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    text = out.stdout.strip()
    if not text:
        return []
    value = json.loads(text)
    return [value] if isinstance(value, str) else [v for v in value if v]


def main():
    root = REPO / "testbed/drive1008-f531" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"], ["-c", "user.email=d@example.invalid", "-c", "user.name=d",
                                                 "commit", "-q", "--allow-empty", "-m", "seed"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    print("project", pid)
    _, runner = api("POST", f"{P}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    code, body = api("POST", f"{P}/agents", {"name": "lister", "runner_id": runner["id"]})
    assert code in (200, 201), (code, body)

    message = (
        f"[{MARKER}] Do not call any tool. Look at the names of every tool you have been given, including deferred "
        "ones listed by name only. Reply with exactly one line: the full names of every tool whose name starts "
        "with `mcp__claude_ai`, comma-separated, or the single word NONE if there is no such tool."
    )
    code, trig = api("POST", f"{P}/agent/trigger", {
        "agent": "lister", "session_mode": "new", "message": message,
        "overrides": {"permission_mode": "bypassPermissions"},
    })
    assert code == 200, (code, trig)
    run_id = trig["run_id"]
    print("run", run_id)

    argv = None
    deadline = time.time() + 240
    while time.time() < deadline:
        if argv is None:
            argv = next((c for c in claude_command_lines() if MARKER in c), None)
        (status,) = ro("select status from runs where id=?", (run_id,))[0]
        if status not in ("running", "queued", "pending", "starting"):
            break
        time.sleep(0.5)
    print("status", status)

    check("the spawned claude process was seen", argv is not None)
    check("its argv carries --strict-mcp-config", argv is not None and "--strict-mcp-config" in argv,
          (argv or "")[:160])
    texts = [c for (c,) in ro("select content from agent_outputs where run_id=? and kind='text' order by sequence",
                              (run_id,))]
    answer = texts[-1].strip() if texts else ""
    check("the turn names no mcp__claude_ai tool", answer != "" and "claude_ai" not in answer, answer[:300])

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
