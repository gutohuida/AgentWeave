"""Leg 6.3 -- the leg that can falsify the change.

6.2 on its own cannot tell "the head is held because nothing else could have run" from "the head
is held, full stop". So: with the same directory still obstructed, queue a *task-bound* message
for the same agent in another conversation. That entry would run in the task's own checkout,
which the obstruction never touched -- so the unbound head really is in the way, must still be
counted down, must still be given up on at the limit, and the task turn must then run.

The task is an ordinary one. A drive cannot produce a grandfathered task (nothing at runtime
writes `workspace_scheme`), which is why the unit test 3.7 exists and why this leg does not stand
in for it.

    AW_HUB=... AW_PROJECT=... AW_AGENT=... AW_ROOT=... AW_DB=... AW_CONV_A=... AW_ENTRY_A=... \
        py -3.11 scripts/drive/t_ablocked_p6_elsewhere.py
"""

import os
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

DB = os.environ["AW_DB"]
AGENT = os.environ["AW_AGENT"]
ROOT = pathlib.Path(os.environ["AW_ROOT"])
CONV_A = os.environ["AW_CONV_A"]
ENTRY_A = os.environ["AW_ENTRY_A"]
BLOCK = ROOT / ".agentweave" / "worktrees" / AGENT

ok = []


def check(label, condition, detail=""):
    ok.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{('  -- ' + detail) if detail else ''}")


def q(sql, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def read(entry_id):
    return q(
        "SELECT state, delivery_attempts, abandoned_reason FROM inbound_queue_entries WHERE id = ?",
        (entry_id,),
    )[0]


check("the obstruction is still in place", BLOCK.is_dir(), str(BLOCK))
state, attempts, _ = read(ENTRY_A)
check("6.2's message is where 6.2 left it", (state, attempts) == ("queued", 0),
      f"state={state!r} attempts={attempts}")

print()
print("=== an ordinary task, and a message bound to it in another conversation ===")
code, task = api("POST", f"/projects/{P}/tasks", {
    "title": "say what calc.py does",
    "description": "Reply with one sentence describing calc.py. Change no files.",
    "assignee": AGENT,
})
show("POST /tasks", code, task, limit=400)
TASK = task["id"]
scheme = q("SELECT workspace_scheme FROM tasks WHERE id = ?", (TASK,))[0][0]
check("the task takes its own checkout (ordinary, not grandfathered)", scheme == "task",
      f"workspace_scheme={scheme!r}")

code, out = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": AGENT,
    "message": "please do this task",
    "task_id": TASK,
    "session_mode": "new",
})
show("POST /agent/trigger (task-bound, new conversation)", code, out, limit=700)
CONV_B, ENTRY_B = out.get("conversation_id"), out.get("queue_entry_id")
check("it landed in a different conversation", CONV_B != CONV_A, f"{CONV_B} vs {CONV_A}")

state, attempts, _ = read(ENTRY_A)
print(f"  head after that schedule: state={state!r} attempts={attempts}")
check("THE HEAD IS NOW BEING COUNTED DOWN -- something else could have run",
      attempts == 1, f"attempts={attempts}")

print()
print("=== the operator keeps pressing Continue on the blocked conversation ===")
for click in range(1, 4):
    code, body = api("POST", f"/projects/{P}/conversations/{CONV_A}/continue")
    time.sleep(0.8)
    state, attempts, abandoned = read(ENTRY_A)
    print(f"  click {click}: HTTP {code} -> state={state!r} attempts={attempts}")
    if state == "withdrawn":
        print(f"      abandoned_reason: {abandoned}")
        break

state, attempts, abandoned = read(ENTRY_A)
check("the head was given up on at the limit", state == "withdrawn", f"state={state!r}")
check("it gave up after three attempts, not more", attempts == 3, f"attempts={attempts}")
check("the reason names the obstruction", bool(abandoned) and "own workspace" in (abandoned or ""))

print()
print("=== and now the task turn runs ===")
code, body = api("POST", f"/projects/{P}/conversations/{CONV_B}/continue")
show("POST /continue (task conversation)", code, body, limit=500)

run = None
for _ in range(60):
    rows = q(
        "SELECT id, status, task_id, workspace_dir FROM runs WHERE project_id = ? AND agent = ? "
        "ORDER BY started_at DESC LIMIT 1",
        (P, AGENT),
    )
    if rows:
        run = rows[0]
        if run[1] != "running":
            break
    time.sleep(5)

print(f"  run: {run}")
check("a run was created at all", run is not None)
if run:
    check("the run is bound to the task", run[2] == TASK, f"task_id={run[2]!r}")
    check("it executed in the TASK's checkout, not the obstructed one",
          bool(run[3]) and TASK in str(run[3]) and str(BLOCK) not in str(run[3]),
          f"workspace_dir={run[3]!r}")
    check("the turn completed", run[1] == "completed", f"status={run[1]!r}")

state, attempts, _ = read(ENTRY_B)
check("the task-bound entry was delivered", state == "delivered", f"state={state!r}")

print()
print(f"6.3: {sum(ok)}/{len(ok)}")
print(f"AW_TASK={TASK}")
print(f"AW_CONV_B={CONV_B}")
