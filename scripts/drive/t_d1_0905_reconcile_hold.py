"""D-1 2026-09-05: a run ends by Hub restart -- is the agent parked behind its checkout released?

Same seam as F286, at the third site that ends a run: `run_reconciliation.reconcile_interrupted_runs`.
Both of `_execute_run`'s endings now call `redrain_queued_agents(project_id)` -- every agent with
something queued. Reconciliation instead collects `(project_id, run.agent)` for the runs it
interrupted and calls `schedule_agent` for those agents only (`run_reconciliation.py:88,158-162`),
so an agent parked on the *interrupted run's* task checkout is not among them.

Stage 1 (`park`) parks B behind A and prints what to kill. Stage 2 (`watch`) runs after the Hub has
been restarted and reports what reconciliation did.

Env: AW_HUB AW_KEY AW_PROJECT AW_A AW_B AW_DB
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
STAGE = sys.argv[1] if len(sys.argv) > 1 else "park"

LONG = ("Write a 3000 word essay about the history of the bicycle, in full prose. "
        "Use no tools and read no files.")
SHORT = "Reply with only the two characters OK. Use no tools."


def sql(q, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def snap(label):
    print(f"[{time.strftime('%H:%M:%S')}] {label}")
    for agent in (A, B):
        for r in sql("SELECT id, status, task_id, pid, started_at, ended_at FROM runs "
                     "WHERE agent = ? ORDER BY started_at", (agent,))[-3:]:
            print(f"    run  {agent} {r['id'][:16]} {r['status']:<12} task={r['task_id']} "
                  f"pid={r['pid']} end={r['ended_at']}")
        for e in sql("SELECT id, state, delivery_attempts, waiting_reason FROM "
                     "inbound_queue_entries WHERE agent = ? ORDER BY sequence", (agent,))[-3:]:
            print(f"    entry {agent} {e['id'][:16]} {e['state']:<10} "
                  f"att={e['delivery_attempts']} reason={str(e['waiting_reason'])[:80]!r}")
        code, st = api("GET", f"/projects/{P}/queue/{agent}/status")
        print(f"    GET /queue/{agent}/status [{code}] {st}")


if STAGE == "park":
    code, task = api("POST", f"/projects/{P}/tasks",
                     {"title": f"d1 reconcile hold {time.strftime('%H%M%S')}"})
    T = task["id"]
    print(f"task {T}")
    code, r1 = api("POST", f"/projects/{P}/agent/trigger",
                   {"agent": A, "message": LONG, "task_id": T})
    print(f"trigger {A} -> [{code}] {str(r1)[:140]}")
    for _ in range(60):
        time.sleep(1)
        rs = sql("SELECT status FROM runs WHERE agent = ? ORDER BY started_at", (A,))
        if rs and rs[-1]["status"] == "running":
            break
    code, r2 = api("POST", f"/projects/{P}/agent/trigger",
                   {"agent": B, "message": SHORT, "task_id": T})
    print(f"trigger {B} on the same task -> [{code}] {str(r2)[:260]}")
    snap("parked")
    live = sql("SELECT id, pid FROM runs WHERE agent = ? AND status = 'running'", (A,))
    print(f"\nA's live run pid(s): {[r['pid'] for r in live]}")
    print("Now kill the Hub process tree and restart it, then run this with 'watch'.")
else:
    # The set of B's runs is taken *before* the wait and compared by id. A time window is not
    # good enough here and the first version of this harness proved it: `started_at >
    # datetime('now','-10 minutes')` matched B's runs from earlier in the same drive and reported
    # a release that had not happened.
    known = {r["id"] for r in sql("SELECT id FROM runs WHERE agent = ?", (B,))}
    snap("first look after restart")
    print(f"B's runs before the wait: {len(known)}")
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(5)
        new_runs = [r for r in sql("SELECT id, status, started_at FROM runs WHERE agent = ?", (B,))
                    if r["id"] not in known]
        if new_runs:
            print(f"[{time.strftime('%H:%M:%S')}] B started a NEW run {new_runs[0]['id']} "
                  f"(+{time.time() - t0:.0f}s after the restart)")
            break
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 300s after the restart and B has NO new run")
    snap("final")
