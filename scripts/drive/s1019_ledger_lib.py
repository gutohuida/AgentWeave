"""Helpers for the 2026-10-19 ledger sweep (Logs, events & SSE x Checkpoints x Agents).

Thin wrappers over the e2e-loop harness; the Hub is whichever `AW_E2E_STATE` names (hub-up 8180).
Real turns only (Haiku); no seeded runs in this sweep.
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-ledger1019.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / "s1019_ledger_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
P = S.get("P", "")
B = f"/projects/{P}"
DIR = pathlib.Path(S.get("DIR", r"C:\Users\huida\Documents\aw-ledger-1019"))
LIVE = ("running", "queued", "starting", "pending")


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None, **kw):
    if path.startswith("~"):
        path = f"/projects/{S.get('P', P)}" + path[1:]
    return e2e.request(method, path, body, **kw)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:3000]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def git(*args, cwd=None):
    r = subprocess.run(["git", "-C", str(cwd or DIR), *args], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def run_status(run_id):
    rows = ro("select status from runs where id=?", (run_id,))
    return rows[0]["status"] if rows else None


def wait_run(run_id, secs=900):
    end = time.time() + secs
    while time.time() < end:
        st = run_status(run_id)
        if st and st not in LIVE:
            return st
        time.sleep(5)
    return "still-running"


def texts(run_id, limit=4000):
    rows = ro("select content from agent_outputs where run_id=? order by sequence", (run_id,))
    return "\n".join((r["content"] or "") for r in rows)[-limit:]
