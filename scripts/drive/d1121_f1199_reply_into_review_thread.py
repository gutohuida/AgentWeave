"""Drive F1199: a builder's reply lands in the checker's task-bound review thread, and the turn it
starts runs in the builder's checkout, bound to the task.

Replicates the sequence observed on 2026-11-21 (Hub profile sweep1121, task FWCAW-1). Only the
first turn is started by hand; the rest is the Hub's own loop (review on completion, restart on
send-back), watched rather than driven:

  1. Developer builds the task, deliberately incomplete, and completes it   (operator trigger)
  2. The Hub hands it to QA for review; QA sends it back and messages Developer
  3. The Hub restarts Developer on the send-back; Developer fixes it and replies to QA with a
     plain message naming no task, without completing (as Developer did in the observed drive)
  4. -> observe where that reply is delivered, and the QA turn it starts: its checkout, its task
     binding, the thread's binding, and what it does to the task.

The messaging is asked for in the task description, which both builder and reviewer read: the
observed drive got it from the agents' own choices, which a short drive cannot wait for.

Pass/fail, as the acceptance drive of `a-two-profile-build-cannot-deadlock-and-a-stall-says-so`:
the reply's turn must not run in .agentweave/tasks/<task>, must not be bound to the task, and QA
must not complete the task. Before the fix each is expected to FAIL. Exit 0 pass, 1 fail,
2 inconclusive (the agents never produced the reply).

Needs AW_HUB, AW_KEY naming a drive Hub (never :8000 or :8010) and AW_DB its SQLite file. Two
Haiku agents.
"""

import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
DB = os.environ["AW_DB"]
root = pathlib.Path(r"C:\Users\huida\Documents\aw-f1199-repro") / TAG
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("F1199 reproduction\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "a@example.invalid"],
    ["git", "config", "user.name", "a"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "init"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)


def db():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


c, proj = api("POST", "/projects/open", {"path": str(root), "name": "f1199-" + TAG})
assert c in (200, 201), (c, proj)
PID = proj["id"]
S = "/projects/%s" % PID
c, rn = api("POST", S + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
assert c == 201, (c, rn)
for n in ("Developer", "QA"):
    c, b = api("POST", S + "/agents", {"name": n, "runner_id": rn["id"]})
    assert c in (200, 201), (n, c, b)

DESCRIPTION = (
    "Goal: hello.txt at the repository root holds exactly two lines: `hello`, then `world`.\n\n"
    "How this task is worked (follow it exactly):\n"
    "- Builder (Developer), first pass: write only the line `hello`, then mark the task "
    "completed. The second line is deliberately left for after review.\n"
    "- Reviewer (QA): review against the Goal. The first pass is missing `world`, so send it "
    "back (revision_needed, reason_class defect) AND call send_message to Developer saying "
    "what is missing and asking Developer to reply to you when it is fixed.\n"
    "- Builder, after a send-back: add the line `world`, then do NOT call update_task; instead "
    "reply to QA with send_message (do not pass task_id) saying it is fixed and ready for them."
)
c, task = api(
    "POST",
    S + "/tasks",
    {"title": "Add hello.txt", "description": DESCRIPTION, "assignee": "Developer"},
)
assert c in (200, 201), (c, task)
TID = task["id"]
print("project", PID, "task", TID, "repo", root)

c, b = api(
    "POST",
    S + "/agent/trigger",
    {
        "agent": "Developer",
        "message": "Work this task, following its description exactly.",
        "task_id": TID,
    },
)
assert c in (200, 201, 202), (c, b)

seen = set()
reply_run = None
deadline = time.time() + 540
while time.time() < deadline:
    with db() as c:
        for r in c.execute(
            "select r.*, cv.task_id as conv_task from runs r left join conversations cv "
            "on cv.id = r.conversation_id where r.project_id=? order by r.started_at",
            (PID,),
        ):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            e = c.execute(
                "select origin_type,origin_agent,message_id,task_id,review_task_id "
                "from inbound_queue_entries where delivered_in_run_id=?",
                (r["id"],),
            ).fetchall()
            ws = (r["workspace_dir"] or "").replace(str(root), "")
            print(
                f"RUN {r['id']} {r['agent']:9} conv={r['conversation_id']} "
                f"conv.task_id={r['conv_task']} run.task_id={r['task_id']} ws={ws} "
                f"entries={[tuple(x) for x in e]}",
                flush=True,
            )
            if r["agent"] == "QA" and any(x["origin_type"] == "agent" for x in e):
                reply_run = r["id"]
        status = c.execute("select status from tasks where id=?", (TID,)).fetchone()[0]
        live = c.execute(
            "select count(*) from runs where project_id=? and ended_at is null", (PID,)
        ).fetchone()[0]
    if live == 0 and (reply_run or status == "approved"):
        break
    time.sleep(3)

with db() as c:
    trans = [
        tuple(r)
        for r in c.execute(
            "select sequence,from_status,to_status,actor_agent,run_id,origin from task_transitions "
            "where task_id=? order by sequence",
            (TID,),
        )
    ]
    msgs = [
        tuple(r)
        for r in c.execute(
            "select sender,recipient,type,task_id,conversation_id,created_by_run_id from messages "
            "where project_id=? order by timestamp",
            (PID,),
        )
    ]
    rr = c.execute("select * from runs where id=?", (reply_run,)).fetchone() if reply_run else None
    status = c.execute("select status from tasks where id=?", (TID,)).fetchone()[0]
print("\nTRANSITIONS")
for t in trans:
    print(" ", t)
print("MESSAGES")
for m in msgs:
    print(" ", m)
print("final task status:", status)
if rr is None:
    print("INCONCLUSIVE: no QA turn was started by a message from Developer")
    sys.exit(2)
ws = rr["workspace_dir"] or ""
checks = {
    "reply turn NOT in the builder's checkout": f"tasks\\{TID}" not in ws
    and f"tasks/{TID}" not in ws,
    "reply turn NOT bound to the task": rr["task_id"] != TID,
    "task NOT completed by QA": not any(t[2] == "completed" and t[3] == "QA" for t in trans),
}
for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)
sys.exit(0 if all(checks.values()) else 1)
