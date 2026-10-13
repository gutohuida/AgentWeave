"""F556 -- an operator-created loop names the mail waiting for its agent when its queue empties.

    AW_HUB=http://127.0.0.1:8010 AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt) \
        py -3.11 t_f556_operator_loop_outstanding_mail.py

The trial Hub must run this checkout from source (hub/, not the console script). No agent turn is
taken: the loop's agent has a blocked checkout, so the operator's message to it stays queued, which
is what "outstanding" means. Everything here is operator-side HTTP, the way an operator creates a loop (so
it has no creating run -- the case the old creator-directed check could never report on).

Legs:
  1. an operator loop, one task rejected so the queue is drained, an operator message queued for
     the loop's agent, then `POST /jobs/{id}/run`: the `loop_queue_exhausted` event names the mail;
  2. a second operator loop whose agent has no inbound mail: `pending_request` is null.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
if ":8000" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

TAG = time.strftime("%H%M%S")
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-f556")
NAME = os.path.basename(DIR.rstrip("\\/"))
PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail and not cond else ""))


def git(*args):
    return subprocess.run(["git", *args], cwd=DIR, capture_output=True, text=True)


os.makedirs(DIR, exist_ok=True)
if git("rev-parse", "--git-dir").returncode != 0:
    git("init")
if git("rev-parse", "HEAD").returncode != 0:
    with open(os.path.join(DIR, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("f556 fixture\n")
    git("add", "README.md")
    git("-c", "user.email=drive@local", "-c", "user.name=drive", "commit", "-m", "fixture")

_, body = api("GET", "/projects")
rows = body if isinstance(body, list) else (body or {}).get("projects") or []
PROJECT = next((p["id"] for p in rows if p.get("name") == NAME), None)
if PROJECT is None:
    code, body = api("POST", "/projects/open", {"path": DIR, "name": NAME})
    if code >= 300:
        sys.exit(f"could not open project: {code} {body}")
    PROJECT = body["id"]
A = f"/projects/{PROJECT}"
print("project", PROJECT)

HAIKU = "claude-haiku-4-5-20251001"
_, body = api("GET", f"{A}/runners")
runners = body if isinstance(body, list) else (body or {}).get("runners") or []
RUNNER = next((r["id"] for r in runners if r.get("name") == "Haiku (cheap)"), None)
if RUNNER is None:
    code, body = api("POST", f"{A}/runners", {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU})
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    RUNNER = body["id"]


def operator_loop(agent, label):
    code, _ = api("POST", f"{A}/agents", {"name": agent, "runner_id": RUNNER})
    print(f"agent {agent}: {code}")
    code, job = api(
        "POST",
        f"{A}/jobs",
        {
            "name": f"f556 {label} {TAG}",
            "agent": agent,
            "message": "work the queue",
            "cron": "0 3 1 1 *",
            "enabled": True,
            "purpose": f"f556 {label}",
            "stop_when_queue_empties": True,
        },
    )
    if code >= 300:
        sys.exit(f"could not create loop job: {code} {job}")
    loop_id = job.get("loop_id") or (job.get("loop") or {}).get("id")
    code, task = api("POST", f"{A}/tasks", {"title": f"f556 seed {label} {TAG}", "loop_id": loop_id})
    ok(f"{label}: the operator can seed the queue", code in (200, 201), f"{code} {str(task)[:200]}")
    code, body = api("PATCH", f"{A}/tasks/{task['id']}", {"status": "rejected"})
    ok(f"{label}: the queue is drained", code < 300, f"{code} {str(body)[:200]}")
    return job["id"], loop_id


def exhausted_event(loop_id):
    code, logs = api("GET", f"{A}/logs?event_type=loop_queue_exhausted&limit=500")
    rows = logs if isinstance(logs, list) else (logs or {}).get("logs") or (logs or {}).get("events") or []
    mine = [e for e in rows if (e.get("data") or e.get("payload") or {}).get("loop_id") == loop_id]
    return mine[0] if mine else None, code


# ---- leg 1: mail waiting for the loop's agent
AGENT1 = f"f556-a-{TAG}"
# A runnered, idle agent starts a turn the moment mail arrives (measured on the first run: the loop
# firing was refused "already running a turn"), so the mail would never be outstanding. Block the
# agent's own checkout -- a plain non-empty directory where git expects to add its worktree -- so the
# Hub accepts the mail and holds it queued (`a-blocked-agent-workspace-holds-its-input`).
blocker = os.path.join(DIR, ".agentweave", "worktrees", AGENT1)
os.makedirs(blocker, exist_ok=True)
with open(os.path.join(blocker, "blocker.txt"), "w", encoding="utf-8") as fh:
    fh.write("not a worktree")
job1, loop1 = operator_loop(AGENT1, "with-mail")
code, msg = api(
    "POST",
    f"{A}/messages",
    {"to": AGENT1, "subject": f"please answer {TAG}", "content": "an ask the loop never dealt with"},
)
ok("leg 1: the operator's message is accepted", code in (200, 201), f"{code} {str(msg)[:300]}")
code, fired = api("POST", f"{A}/jobs/{job1}/run", None, timeout=120)
print("run now:", code, str(fired)[:200])
ev, code = exhausted_event(loop1)
ok("leg 1: loop_queue_exhausted was recorded", ev is not None, f"logs {code}")
pending = ((ev or {}).get("data") or (ev or {}).get("payload") or {}).get("pending_request")
print("pending_request:", pending)
ok("leg 1: it names the mail addressed to the loop's agent",
   bool(pending) and pending.get("kind") == "message" and pending.get("to") == AGENT1
   and pending.get("reason") == f"please answer {TAG}", str(pending))

# ---- leg 2: nothing waiting
AGENT2 = f"f556-b-{TAG}"
job2, loop2 = operator_loop(AGENT2, "no-mail")
api("POST", f"{A}/jobs/{job2}/run", None, timeout=120)
ev2, _ = exhausted_event(loop2)
ok("leg 2: loop_queue_exhausted was recorded", ev2 is not None)
pending2 = ((ev2 or {}).get("data") or (ev2 or {}).get("payload") or {}).get("pending_request")
ok("leg 2: nothing outstanding when no mail is waiting", ev2 is not None and pending2 is None, str(pending2))

for j in (job1, job2):
    api("PATCH", f"{A}/jobs/{j}", {"enabled": False})
print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
