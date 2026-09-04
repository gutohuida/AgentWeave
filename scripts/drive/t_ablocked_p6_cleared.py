"""Leg 6.4 -- the point of holding the message is that performing the remedy delivers it.

Holding input forever is not a fix, it is a slower way to lose it. So: queue a message while the
agent's workspace is obstructed, confirm it is held, then do exactly what the refusal told the
operator to do -- remove that directory, and let the next turn prune -- and confirm the message
the Hub promised to keep is actually delivered (F96).

    AW_HUB=... AW_PROJECT=... AW_AGENT=... AW_ROOT=... AW_DB=... \
        py -3.11 scripts/drive/t_ablocked_p6_cleared.py
"""

import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

DB = os.environ["AW_DB"]
AGENT = os.environ["AW_AGENT"]
ROOT = pathlib.Path(os.environ["AW_ROOT"])
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
        "SELECT state, delivery_attempts, waiting_reason FROM inbound_queue_entries WHERE id = ?",
        (entry_id,),
    )[0]


check("the obstruction is still in place", BLOCK.is_dir(), str(BLOCK))

print()
print("=== a message the operator sends while the workspace is obstructed ===")
code, out = api("POST", f"/projects/{P}/agent/trigger", {
    "agent": AGENT,
    "message": "In one short sentence: what does calc.py do? Change no files.",
    "session_mode": "new",
})
CONV_C, ENTRY_C = out.get("conversation_id"), out.get("queue_entry_id")
print(f"  entry={ENTRY_C} conversation={CONV_C}")
state, attempts, waiting = read(ENTRY_C)
check("it is held, not counted", (state, attempts) == ("queued", 0), f"{state!r} {attempts}")
check("and it says what to remove", bool(waiting) and str(BLOCK) in waiting)

print()
print("=== the operator performs the remedy the refusal named ===")
shutil.rmtree(BLOCK)
print(f"  rm -r {BLOCK}")
pruned = subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True, text=True)
print(f"  git worktree prune -> rc={pruned.returncode} {pruned.stdout.strip()}{pruned.stderr.strip()}")
check("the obstruction is gone", not BLOCK.exists())

print()
print("=== one Continue, and the held message is delivered ===")
code, body = api("POST", f"/projects/{P}/conversations/{CONV_C}/continue")
show("POST /continue", code, body, limit=400)
check("the turn started", isinstance(body, dict) and body.get("started") is True,
      f"started={body.get('started') if isinstance(body, dict) else body!r}")

run = None
for _ in range(60):
    rows = q(
        "SELECT id, status, task_id, workspace_dir, error FROM runs "
        "WHERE project_id = ? AND agent = ? AND conversation_id = ? ORDER BY started_at DESC LIMIT 1",
        (P, AGENT, CONV_C),
    )
    if rows:
        run = rows[0]
        if run[1] != "running":
            break
    time.sleep(5)
print(f"  run: {run}")
check("a run happened for the held message", run is not None)
if run:
    check("the turn completed", run[1] == "completed", f"status={run[1]!r} error={run[4]!r}")
    check("it ran in the agent's own workspace -- the very path that was obstructed",
          str(run[3]) == str(BLOCK), f"workspace_dir={run[3]!r}")
check("the workspace was provisioned as a real git worktree", BLOCK.is_dir())
registered = subprocess.run(["git", "worktree", "list"], cwd=ROOT, capture_output=True, text=True)
print("  git worktree list:")
for line in registered.stdout.splitlines():
    print(f"    {line}")
check("git registered it on the agent's branch",
      f"agentweave/{AGENT}" in registered.stdout)

state, attempts, waiting = read(ENTRY_C)
check("THE MESSAGE THE HUB PROMISED TO HOLD WAS DELIVERED", state == "delivered",
      f"state={state!r} attempts={attempts}")

code, status = api("GET", f"/projects/{P}/queue/{AGENT}/status")
print(f"  queue status now: {status}")

print()
print(f"6.4: {sum(ok)}/{len(ok)}")
