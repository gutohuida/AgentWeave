"""Shared helpers for the 2026-10-23 Runs drive (scratch Hub :8118, profile rn1023).

    AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/s1023_rn_lib.py GET /health
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault(
    "AW_E2E_STATE",
    "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e-state-rn1023.json",
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-71764bd56b63")
B = f"/projects/{P}"
DIR = pathlib.Path("C:/Users/huida/Documents/aw-rn1023")
HAIKU = "claude-haiku-4-5-20251001"


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def procs():
    """Every process as {pid: {ppid, name, cmd}} via CIM (Windows)."""
    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,"
            "CommandLine | ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    rows = json.loads(out)
    return {
        r["ProcessId"]: {"ppid": r["ParentProcessId"], "name": r["Name"], "cmd": r["CommandLine"] or ""}
        for r in rows
    }


def descendants(table, root):
    found, frontier = [], [root]
    while frontier:
        cur = frontier.pop()
        for pid, row in table.items():
            if row["ppid"] == cur and pid not in found:
                found.append(pid)
                frontier.append(pid)
    return found


def wait_run(run_id, minutes=10):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        rows = q("select status from runs where id=?", run_id)
        if rows and rows[0]["status"] not in ("running", "queued", "starting", "pending"):
            return rows[0]["status"]
        time.sleep(4)
    return "still-running"


def trigger(agent, message, perm="workspace", conversation=None, fresh=False, **extra):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    body.update(extra)
    if conversation:
        body["conversation_id"] = conversation
    elif not fresh:
        conv = e2e.latest_conversation(P, agent)
        if conv:
            body["conversation_id"] = conv
    return req("POST", f"{B}/agent/trigger", body)


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
