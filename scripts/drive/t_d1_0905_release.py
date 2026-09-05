"""D-1 2026-09-05: does a run reaching terminal status actually release the input queued behind it?

Independent of the night window's F286 harness: no injected exception, no A/B, no control. It
drives the ordinary seam an operator meets -- a turn running, more input arriving behind it -- and
measures how long the release takes on THIS branch's code.

Modes (argv[1]):
    complete   run 1 is left to finish on its own; two entries queue behind it
    stop       run 1 is interrupted with POST /agent/{name}/stop while an entry waits behind it

Env: AW_HUB AW_KEY AW_PROJECT AW_AGENT AW_DB
Prints only what it measured.
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\Users\huida\Documents\projects\AgentWeave\scripts\drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import P, api  # noqa: E402

DB = os.environ["AW_DB"]
AGENT = os.environ["AW_AGENT"]
MODE = sys.argv[1] if len(sys.argv) > 1 else "complete"
WATCH = float(os.environ.get("WATCH_SECONDS", "180"))

LONG = ("Write a 1500 word essay about the history of the bicycle, in full prose, "
        "one paragraph at a time. Use no tools and read no files.")
SECOND = "SECOND: reply with only the two characters OK."
THIRD = "THIRD: reply with only the four characters DONE."


def sql(q, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def entries():
    return sql("SELECT id, state, sequence, conversation_id, delivered_in_run_id, delivered_at, "
               "delivery_attempts, waiting_reason, arrived_at, substr(content,1,18) AS content "
               "FROM inbound_queue_entries WHERE agent = ? ORDER BY sequence", (AGENT,))


def runs():
    return sql("SELECT id, status, error, conversation_id, started_at, ended_at, exit_code "
               "FROM runs WHERE agent = ? ORDER BY started_at", (AGENT,))


def stamp():
    return time.strftime("%H:%M:%S")


def snap(label):
    print(f"[{stamp()}] {label}")
    for r in runs():
        print(f"    run  {r['id'][:16]} {r['status']:<10} exit={r['exit_code']} "
              f"start={r['started_at']} end={r['ended_at']} conv={str(r['conversation_id'])[:14]}")
    for e in entries():
        print(f"    entry {e['id'][:16]} {e['state']:<9} seq={e['sequence']} "
              f"att={e['delivery_attempts']} in_run={str(e['delivered_in_run_id'])[:16]} "
              f"delivered={e['delivered_at']} reason={e['waiting_reason']!r} {e['content']!r}")
    code, st = api("GET", f"/projects/{P}/queue/{AGENT}/status")
    print(f"    GET /queue/{AGENT}/status [{code}] {st}")


print(f"=== D-1 release drive, mode={MODE}, agent={AGENT} ===")
t0 = time.time()
code, r1 = api("POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "message": LONG})
print(f"[{stamp()}] trigger #1 -> [{code}] {str(r1)[:220]}")
if code != 200:
    sys.exit(1)

# Wait for the run to actually be running before queueing behind it.
for _ in range(60):
    time.sleep(1)
    rs = runs()
    if rs and rs[-1]["status"] == "running":
        break
snap("run 1 is running")

code, r2 = api("POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "message": SECOND})
print(f"[{stamp()}] trigger #2 -> [{code}] status={str(r2.get('status') if isinstance(r2, dict) else r2)}")
if MODE == "complete":
    code, r3 = api("POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "message": THIRD})
    print(f"[{stamp()}] trigger #3 -> [{code}] status={str(r3.get('status') if isinstance(r3, dict) else r3)}")
snap("input queued behind run 1")

if MODE == "stop":
    time.sleep(5)
    code, s = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
    print(f"[{stamp()}] POST /agent/{AGENT}/stop -> [{code}] {s}")

first_id = runs()[0]["id"]
ended_wall = None
released_wall = None
deadline = time.time() + WATCH
while time.time() < deadline:
    time.sleep(2)
    rs = runs()
    first = next((r for r in rs if r["id"] == first_id), None)
    if ended_wall is None and first and first["status"] != "running":
        ended_wall = time.time()
        print(f"[{stamp()}] run 1 reached {first['status']!r} "
              f"(+{ended_wall - t0:.1f}s from trigger #1)")
    if ended_wall is not None and len(rs) > 1:
        released_wall = time.time()
        print(f"[{stamp()}] a successor run exists: {rs[1]['id'][:16]} {rs[1]['status']}")
        break
    if ended_wall is not None and time.time() - ended_wall > 45:
        print(f"[{stamp()}] 45s after run 1 ended and no successor run")
        break

snap("after the release window")
if ended_wall and released_wall:
    print(f"MEASURED release latency: {released_wall - ended_wall:.2f}s "
          f"(polled every 2s, so this is an upper bound)")
elif ended_wall:
    print("MEASURED: run 1 ended and NO successor run appeared inside the window")
else:
    print("MEASURED: run 1 never reached a terminal status inside the window")

# Let the successor finish so the fixture is left idle, and show where the entries landed.
time.sleep(45)
snap("45s later")
