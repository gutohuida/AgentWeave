"""D-1 2026-09-05: does a run ending release an agent parked on the *task checkout* it held?

Design D8 admits one writing turn per task checkout. Agent A runs on task T; agent B is triggered
on the same task and is refused transiently, so its entry stays `queued`. Nothing but
`redrain_queued_agents` can start it, and F286's whole subject is whether that call happens on
every terminal ending rather than only on some. The night window's own log records this half as
*tested, not driven*.

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
MODE = sys.argv[1] if len(sys.argv) > 1 else "complete"

LONG = ("Write a 1200 word essay about the history of the bicycle, in full prose. "
        "Use no tools and read no files.")
SHORT = "Reply with only the two characters OK. Use no tools."


def sql(q, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def runs(agent):
    return sql("SELECT id, status, started_at, ended_at, task_id FROM runs WHERE agent = ? "
               "ORDER BY started_at", (agent,))


def entries(agent):
    return sql("SELECT id, state, delivered_in_run_id, delivery_attempts, waiting_reason "
               "FROM inbound_queue_entries WHERE agent = ? ORDER BY sequence", (agent,))


def stamp():
    return time.strftime("%H:%M:%S")


def snap(label):
    print(f"[{stamp()}] {label}")
    for agent in (A, B):
        for r in runs(agent):
            print(f"    run  {agent} {r['id'][:16]} {r['status']:<10} task={r['task_id']} "
                  f"start={r['started_at']} end={r['ended_at']}")
        for e in entries(agent):
            print(f"    entry {agent} {e['id'][:16]} {e['state']:<9} att={e['delivery_attempts']} "
                  f"in_run={str(e['delivered_in_run_id'])[:16]} reason={e['waiting_reason']!r}")
        code, st = api("GET", f"/projects/{P}/queue/{agent}/status")
        print(f"    GET /queue/{agent}/status [{code}] {st}")


code, task = api("POST", f"/projects/{P}/tasks",
                 {"title": f"d1 checkout hold {stamp()}", "description": "D-1 drive"})
print(f"POST /tasks [{code}] {str(task)[:200]}")
T = task["id"]

code, r1 = api("POST", f"/projects/{P}/agent/trigger",
               {"agent": A, "message": LONG, "task_id": T})
print(f"[{stamp()}] trigger {A} on {T} -> [{code}] {str(r1)[:160]}")
for _ in range(60):
    time.sleep(1)
    rs = runs(A)
    if rs and rs[-1]["status"] == "running":
        break

code, r2 = api("POST", f"/projects/{P}/agent/trigger",
               {"agent": B, "message": SHORT, "task_id": T})
print(f"[{stamp()}] trigger {B} on the SAME task -> [{code}] {str(r2)[:300]}")
snap("B parked behind A's checkout")

if MODE == "stop":
    time.sleep(3)
    code, s = api("POST", f"/projects/{P}/agent/{A}/stop")
    print(f"[{stamp()}] POST /agent/{A}/stop -> [{code}] {str(s)[:160]}")

a_first = runs(A)[-1]["id"]
ended = released = None
deadline = time.time() + 240
while time.time() < deadline:
    time.sleep(2)
    a = next((r for r in runs(A) if r["id"] == a_first), None)
    if ended is None and a and a["status"] != "running":
        ended = time.time()
        print(f"[{stamp()}] A's run reached {a['status']!r}")
    if ended is not None and runs(B):
        released = time.time()
        print(f"[{stamp()}] B has a run: {runs(B)[-1]['id'][:16]} {runs(B)[-1]['status']}")
        break
    if ended is not None and time.time() - ended > 60:
        print(f"[{stamp()}] 60s after A ended and B still has no run")
        break

snap("after the release window")
if ended and released:
    print(f"MEASURED checkout release latency: {released - ended:.2f}s (2s poll, upper bound)")
elif ended:
    print("MEASURED: A ended and B was NOT released inside 60s")
else:
    print("MEASURED: A never reached a terminal status")
time.sleep(30)
snap("30s later")
