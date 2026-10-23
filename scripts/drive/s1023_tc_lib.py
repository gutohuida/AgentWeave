"""Shared helpers for the 2026-10-23 Traces drive (scratch Hub :8120, profile tc1023).

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_tc_lib.py GET /health
"""

import importlib.util
import json
import os
import pathlib
import sys
import time

os.environ.setdefault(
    "AW_E2E_STATE", "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e-state-tc1023.json"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
_E2E = ROOT / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

STATE_FILE = ROOT / "testbed" / "scratch" / "s1023_tc_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"P": "proj-75b3f47608fc"}
P = S["P"]
B = f"/projects/{P}"
DIR = pathlib.Path.home() / "Documents" / "aw-tc1023"
HAIKU = "claude-haiku-4-5-20251001"
LIVE = ("running", "queued", "starting", "pending")

# Fake secrets: an Anthropic-shaped key whole, one split across two tool outputs, a GitHub token.
KEY = "sk-ant-api03-" + "TRACEfake0123456789abcdefghijKLMNOPqrstuv"  # 13 + 40
HALF1 = "sk-ant-api03-" + "SPLITfake0123456789a"  # 13 + 20
HALF2 = "bcdefghijKLMNOPqrstu"  # the other 20
GH = "ghp_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"  # 4 + 36


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def req(method, path, body=None, **kw):
    if path.startswith("~"):
        path = B + path[1:]
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    print(f"{method} {path} -> {status}\n{text[:limit]}", flush=True)
    return status, res


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:4000]}", flush=True)


def q(sql, *args):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def trigger(agent, message, conversation=None, task=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if conversation:
        body["conversation_id"] = conversation
    if task:
        body["task_id"] = task
    st, res = req("POST", "~/agent/trigger", body)
    say(f"trigger {agent} -> {st}", {k: res.get(k) for k in ("run_id", "status", "conversation_id", "detail")})
    return res.get("run_id")


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = q("select status from runs where id=?", run_id)
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(3)
    return "still-running"


def wait_tool_call(run_id, needle="Called", secs=180):
    end = time.time() + secs
    while time.time() < end:
        rows = q("select count(*) n from agent_outputs where run_id=? and content like ?", run_id, f"%{needle}%")
        if rows[0]["n"]:
            return True
        time.sleep(3)
    return False


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
