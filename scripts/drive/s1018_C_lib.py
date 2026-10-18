"""Sweep C (2026-10-18) helpers: thin wrappers over the e2e-loop harness, on Hub :8033 only."""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-sweepC.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = "proj-d056068c19fb"
B = f"/projects/{P}"
DIR = pathlib.Path(r"C:\Users\huida\Documents\aw-sweepC-1018")
assert e2e.hub().endswith(":8033"), e2e.hub()


def api(method, path, body=None):
    if path.startswith("~"):
        path = B + path[1:]
    return e2e.request(method, path, body)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:2500]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def git(*args, cwd=None):
    r = subprocess.run(["git", "-C", str(cwd or DIR), *args], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


LIVE = ("running", "queued", "starting", "pending")


def settle(agents=None, secs=600):
    end = time.time() + secs
    while time.time() < end:
        q = "select count(*) n from runs where project_id=? and status in ('running','queued','starting','pending')"
        args = [P]
        if agents:
            q += " and agent in (%s)" % ",".join("?" * len(agents))
            args += list(agents)
        if ro(q, args)[0]["n"] == 0:
            return True
        time.sleep(4)
    return False


def trigger(agent, message, task=None, conversation=None, perm="workspace", fresh=False):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if task:
        body["task_id"] = task
    if conversation:
        body["conversation_id"] = conversation
    elif not fresh:
        c = e2e.latest_conversation(P, agent)
        if c:
            body["conversation_id"] = c
    return api("POST", f"{B}/agent/trigger", body)


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        r = ro("select status from runs where id=?", (run_id,))
        if r and r[0]["status"] not in LIVE:
            return r[0]["status"]
        time.sleep(4)
    return "still-running"


def texts(run_id):
    return [r["content"] for r in ro(
        "select kind, content from agent_outputs where run_id=? order by timestamp, sequence, id",
        (run_id,)) if r["kind"] == "text"]


def outputs(run_id, limit=300):
    for r in ro("select kind, content from agent_outputs where run_id=? order by timestamp, sequence, id",
                (run_id,)):
        print(f"   [{r['kind']}] {(r['content'] or '').strip()[:limit]}")


def transitions(task_id):
    return ro("select from_status, to_status, actor_kind, actor_agent, origin, job_id, override_reason, created_at from task_transitions "
              "where task_id=? order by sequence", (task_id,))


def task(task_id):
    return api("GET", f"{B}/tasks/{task_id}")[1]
