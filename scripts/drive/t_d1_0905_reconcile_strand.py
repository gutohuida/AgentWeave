"""D-1 2026-09-05: three crashes strand the agent parked on the crashed run's task checkout.

`run_reconciliation.reconcile_interrupted_runs` ends runs, exactly as `_execute_run` does, but
releases only the interrupted run's **own** agent (`agents_to_schedule.add((run.project_id,
run.agent))` at `run_reconciliation.py:88`, `_schedule_now` at `:158`). Every other ending in the
product calls `redrain_queued_agents(project_id)` -- every agent with anything queued -- and F286
has just finished making that unconditional at both of `_execute_run`'s.

One crash hides this: the interrupted run's entry goes back to the queue, its agent is rescheduled,
and *that* turn's ordinary completion re-drains the project and releases whoever was parked. The
mask comes off at `inbound_queue.DELIVERY_ATTEMPT_LIMIT` (3): the third crash withdraws the entry,
so the agent has nothing to schedule, so no run ends, so nothing ever re-drains -- while the task
checkout the parked agent is waiting for is free.

`setup` parks B behind A. Then run `d1_0905_restart_hub.sh` while A is running, `step` to restart
A, and repeat three times; `watch` reports the end state.

Env: AW_HUB AW_KEY AW_PROJECT AW_A AW_B AW_DB AW_TASK
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\Users\huida\Documents\projects\AgentWeave\scripts\drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import P, api  # noqa: E402

DB = os.environ["AW_DB"]
A = os.environ["AW_A"]
B = os.environ["AW_B"]
STAGE = sys.argv[1] if len(sys.argv) > 1 else "setup"

LONG = ("Write a 4000 word essay about the history of the bicycle, in full prose. "
        "Use no tools and read no files.")
SHORT = "Reply with only the two characters OK. Use no tools."


def sql(q, a=()):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(q, a).fetchall()]
    finally:
        c.close()


def report(label, task):
    print(f"[{time.strftime('%H:%M:%S')}] {label}")
    for r in sql("SELECT id,agent,status,task_id,ended_at FROM runs WHERE task_id=? "
                 "ORDER BY started_at", (task,)):
        print(f"    run  {r['agent']} {r['id'][:16]} {r['status']:<12} end={r['ended_at']}")
    for agent in (A, B):
        for e in sql("SELECT id,state,delivery_attempts,abandoned_reason,waiting_reason FROM "
                     "inbound_queue_entries WHERE agent=? ORDER BY sequence DESC LIMIT 1", (agent,)):
            print(f"    entry {agent} {e['id'][:16]} {e['state']:<10} att={e['delivery_attempts']} "
                  f"abandoned={str(e['abandoned_reason'])[:60]!r}")
        code, st = api("GET", f"/projects/{P}/queue/{agent}/status")
        print(f"    GET /queue/{agent}/status [{code}] {st}")


if STAGE == "setup":
    code, task = api("POST", f"/projects/{P}/tasks",
                     {"title": f"d1 strand {time.strftime('%H%M%S')}"})
    T = task["id"]
    code, r1 = api("POST", f"/projects/{P}/agent/trigger",
                   {"agent": A, "message": LONG, "task_id": T})
    print(f"trigger {A} -> [{code}] run={r1.get('run_id')}")
    for _ in range(60):
        time.sleep(1)
        if sql("SELECT id FROM runs WHERE agent=? AND status='running'", (A,)):
            break
    code, r2 = api("POST", f"/projects/{P}/agent/trigger",
                   {"agent": B, "message": SHORT, "task_id": T})
    print(f"trigger {B} on the same task -> [{code}] status={r2.get('status')} "
          f"reason={str(r2.get('waiting_reason'))[:90]!r}")
    print(f"AW_TASK={T}")
    report("parked", T)
elif STAGE == "await-running":
    T = os.environ["AW_TASK"]
    for _ in range(90):
        time.sleep(1)
        rows = sql("SELECT id FROM runs WHERE agent=? AND status='running' AND task_id=?", (A, T))
        if rows:
            print(f"[{time.strftime('%H:%M:%S')}] A is running again: {rows[0]['id']}")
            sys.exit(0)
    print(f"[{time.strftime('%H:%M:%S')}] A is NOT running")
    report("A did not restart", T)
else:
    T = os.environ["AW_TASK"]
    report("first look", T)
    t0 = time.time()
    known = {r["id"] for r in sql("SELECT id FROM runs WHERE agent=?", (B,))}
    while time.time() - t0 < 240:
        time.sleep(5)
        new = [r for r in sql("SELECT id FROM runs WHERE agent=?", (B,)) if r["id"] not in known]
        if new:
            print(f"[{time.strftime('%H:%M:%S')}] B started {new[0]['id']} "
                  f"(+{time.time()-t0:.0f}s)")
            break
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 240s and B has NO new run")
    report("final", T)
