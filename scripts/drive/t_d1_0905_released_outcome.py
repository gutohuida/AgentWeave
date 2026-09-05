"""D-1 2026-09-05: does the released turn -- and the turn that released it -- keep its outcome?

The seam F274 names, reached by the release mechanism itself. A run ending starts the next one,
which writes more events, which is what evicts the older run from the timeline's fifty. So the act
of releasing input is itself an eviction driver: the more reliably the queue drains, the faster a
turn's own outcome disappears from the conversation that shows it.

Env: AW_HUB AW_KEY AW_PROJECT AW_AGENT AW_DB
"""
import os

import sqlite3
import sys

sys.path.insert(0, r"C:\Users\huida\Documents\projects\AgentWeave\scripts\drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import P, api  # noqa: E402

DB = os.environ["AW_DB"]
AGENT = os.environ["AW_AGENT"]


def sql(q, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


rows = sql("SELECT id, status, conversation_id, started_at FROM runs WHERE agent = ? "
           "ORDER BY started_at", (AGENT,))
print(f"runs on disk for {AGENT}: {len(rows)}")
for r in rows:
    print(f"    {r['id']} {r['status']:<10} conv={r['conversation_id']}")

code, tl = api("GET", f"/projects/{P}/agents/{AGENT}/timeline")
events = tl.get("events", [])
runs = tl.get("runs", {})
print(f"\nGET /agents/{AGENT}/timeline [{code}]  events={len(events)} (cap 50)  runs_in_map={len(runs)}")
missing = [r["id"] for r in rows if r["id"] not in runs]
print(f"runs on disk NOT in the map: {len(missing)}")
for m in missing:
    print(f"    {m}")

# What each conversation's chat renders, and whether the map can label those turns.
convs = sorted({r["conversation_id"] for r in rows if r["conversation_id"]})
for c in convs:
    code, hist = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{c}")
    ids = []
    for e in hist.get("entries", []) if isinstance(hist, dict) else []:
        rid = e.get("run_id")
        if isinstance(rid, str) and rid and rid not in ids:
            ids.append(rid)
    labelled = [i for i in ids if i in runs]
    print(f"\nconv {c}: chat names {len(ids)} run id(s); "
          f"{len(labelled)} of them are in the timeline map")
    for i in ids:
        mark = "LABELLED  " if i in runs else "NO OUTCOME"
        st = runs.get(i, {}).get("status") if i in runs else None
        print(f"    {mark} {i} status={st}")
