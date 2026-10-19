"""Helpers for the 2026-10-19 tasks sweep (Tasks x Flows & review x Worktrees & integration).

Thin wrappers over the e2e-loop harness; the Hub is whichever `AW_E2E_STATE` names (hub-up 8170).
Real turns only (Haiku); no seeded runs in this sweep.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-tasks1019.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / "s1019_tasks_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
P = S.get("P", "proj-9efd0274930b")
B = f"/projects/{P}"
D = f"{B}/project"
DIR = pathlib.Path(S.get("DIR", r"C:\Users\huida\Documents\aw-tasks-1019"))
LIVE = ("running", "queued", "starting", "pending")


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None):
    if path.startswith("~"):
        path = B + path[1:]
    return e2e.request(method, path, body)


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


def q(path):
    return urllib.parse.quote(path)


def runs(limit=8):
    return ro("select id, agent, status, task_id, conversation_id, substr(started_at,12,8) t, error from runs "
              "where project_id=? order by started_at desc limit ?", (P, limit))


def settle(secs=900):
    end = time.time() + secs
    while time.time() < end:
        n = ro("select count(*) n from runs where project_id=? and status in ('running','queued','starting','pending')",
               (P,))[0]["n"]
        if n == 0:
            return True
        time.sleep(5)
    return False


def texts(run_id):
    return [r["content"] for r in ro(
        "select kind, content from agent_outputs where run_id=? order by timestamp, sequence, id",
        (run_id,)) if r["kind"] == "text"]


def transitions(task_id):
    return ro("select id, from_status, to_status, actor_kind, actor_agent, origin, job_id, run_id, override_reason, "
              "created_at from task_transitions where task_id=? order by sequence", (task_id,))


def task(task_id):
    return api("GET", f"{B}/tasks/{task_id}")[1]


def spec_tasks():
    return [t for t in api("GET", f"{B}/tasks?limit=50")[1]["tasks"] if t.get("spec_document_id")]
