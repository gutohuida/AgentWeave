"""F286 phase 0 -- observe the defect before implementing it away.

Run (2026-09-04 night, the measurement recorded under F286 in FINDINGS.md):

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-96849871dd06 AW_AGENT=f286a230652         AW_DB=C:/Users/huida/AppData/Local/Temp/aw-f286/f286.db IDLE_MINUTES=4         py -3.11 scripts/drive/t_f286_phase0_observe.py

It reads the queue and run rows straight from SQLite because no operator route exposes
`delivered_in_run_id`; everything it *writes* goes through the HTTP surface an operator uses.
The exception it depends on is a temporary `AW_F286_INJECT` guarded raise added to
`hub/hub/api/v1/agent_trigger.py` immediately before the in-window status write (`:2235`),
reverted with `git checkout` after the drive -- see F286.

0.2  a turn runs, a second message queues behind it, an in-window bookkeeping call raises once
     (AW_F286_INJECT, predicated on the terminal status write at agent_trigger.py:2235 -- AFTER
     the terminal commit at :2175, BEFORE `redrain_queued_agents` at :2286).
0.3  nothing recovers it on its own; a settings save delivers it instantly.
0.4  the run's recorded outcome is the one it reached, not `failed`.

Prints only what it measured. Nothing here asserts a desired outcome.
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\Users\huida\Documents\projects\AgentWeave\scripts\drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import P, api  # noqa: E402

DB = os.environ.get("AW_DB", r"C:/Users/huida/AppData/Local/Temp/aw-f286/f286.db")
AGENT = os.environ["AW_AGENT"]
IDLE_MINUTES = float(os.environ.get("IDLE_MINUTES", "4"))

LONG = ("Write a 2000 word essay about the history of the bicycle, in full prose, "
        "one paragraph at a time. Use no tools and read no files.")
SECOND = "SECOND MESSAGE: reply with only the two characters OK."


def sql(q, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def entries():
    return sql("SELECT id, state, delivered_in_run_id, delivered_at, delivery_attempts, "
               "waiting_reason, arrived_at, content FROM inbound_queue_entries "
               "WHERE agent = ? ORDER BY sequence", (AGENT,))


def runs():
    return sql("SELECT id, status, error, started_at, ended_at, exit_code FROM runs "
               "WHERE agent = ? ORDER BY started_at", (AGENT,))


def stamp():
    return time.strftime("%H:%M:%S")


def dump(label):
    print(f"\n--- {label}   ({stamp()})")
    for r in runs():
        print(f"    run  {r['id']}  status={r['status']!r} error={str(r['error'])[:60]!r} "
              f"ended_at={r['ended_at']} exit={r['exit_code']}")
    for e in entries():
        print(f"    entry {e['id']}  state={e['state']!r} delivered_in_run_id={e['delivered_in_run_id']!r} "
              f"attempts={e['delivery_attempts']} waiting_reason={str(e['waiting_reason'])[:50]!r} "
              f"content={e['content'][:34]!r}")


print("=" * 78)
print(f"F286 PHASE 0    project={P}  agent={AGENT}  hub=8011  injection=ARMED")
print("=" * 78)

# ---------------------------------------------------------------- 0.2 the headline
code, out = api("POST", f"/projects/{P}/agent/trigger",
                {"agent": AGENT, "session_mode": "new", "message": LONG})
print(f"trigger #1 -> {code}  {json.dumps(out, default=str)[:220]}")
conv1, run1 = out.get("conversation_id"), out.get("run_id")
t0 = time.time()

# wait until the run is genuinely running before queueing behind it
for _ in range(40):
    rs = runs()
    if rs and rs[-1]["status"] == "running":
        print(f"  run {rs[-1]['id']} is running at t={round(time.time()-t0,1)}s")
        break
    time.sleep(0.5)
else:
    print("  ABORT: no running run appeared")
    sys.exit(1)

time.sleep(3)
code2, out2 = api("POST", f"/projects/{P}/agent/trigger",
                  {"agent": AGENT, "message": SECOND})
print(f"trigger #2 -> {code2}  {json.dumps(out2, default=str)[:260]}")
entry_id = out2.get("queue_entry_id") if isinstance(out2, dict) else None
print(f"  queued entry id = {entry_id}")
dump("immediately after the second message")

# wait for run #1 to leave `running`
print("\nwaiting for run #1 to reach a terminal status ...")
for _ in range(300):
    rs = [r for r in runs() if r["id"] == run1]
    if rs and rs[0]["status"] != "running":
        print(f"  run #1 terminal at t={round(time.time()-t0,1)}s: status={rs[0]['status']!r}")
        break
    time.sleep(1)
else:
    print("  run #1 never left `running` within 300s")

time.sleep(5)
dump("0.2 -- 5s after run #1 reached its terminal status")

# ---------------------------------------------------------------- 0.4 outcome not relabelled
r1 = [r for r in runs() if r["id"] == run1]
if r1:
    print(f"\n0.4  run #1 recorded outcome: status={r1[0]['status']!r}  error={r1[0]['error']!r}")

# ---------------------------------------------------------------- 0.3 nothing recovers it
print(f"\n0.3  leaving the Hub running and untouched for {IDLE_MINUTES} minutes ...")
deadline = time.time() + IDLE_MINUTES * 60
while time.time() < deadline:
    time.sleep(30)
    e = [x for x in entries() if x["id"] == entry_id]
    left = round(deadline - time.time())
    if e:
        print(f"    {stamp()}  +{round(IDLE_MINUTES*60 - left)}s  state={e[0]['state']!r} "
              f"delivered_in_run_id={e[0]['delivered_in_run_id']!r} attempts={e[0]['delivery_attempts']}")
dump(f"0.3 -- after {IDLE_MINUTES} idle minutes")
n_runs_before_save = len(runs())

print("\n0.3  now saving the project's settings (the coincidence) ...")
code, cur = api("GET", f"/projects/{P}/settings")
print(f"  GET settings -> {code}")
t_save = time.time()
code, saved = api("PUT", f"/projects/{P}/settings", cur if isinstance(cur, dict) else {})
print(f"  PUT settings -> {code}  ({stamp()})")
for _ in range(30):
    e = [x for x in entries() if x["id"] == entry_id]
    if e and e[0]["delivered_in_run_id"]:
        print(f"  DELIVERED {round(time.time()-t_save,2)}s after the settings save: "
              f"state={e[0]['state']!r} delivered_in_run_id={e[0]['delivered_in_run_id']!r}")
        break
    time.sleep(0.5)
else:
    print("  not delivered within 15s of the settings save")
dump("after the settings save")
print(f"\nruns before the save: {n_runs_before_save}   after: {len(runs())}")
print(f"\nRUN1={run1}  CONV1={conv1}  ENTRY={entry_id}")
