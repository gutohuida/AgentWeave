"""D-1: does a turn keep its outcome once the timeline's 50-event window moves past it?

`AgentTimeline` reads a turn's terminal label and duration from `runs[turn.runId]`
(`AgentTimeline.tsx:237,280`). `runs` comes from the timeline route, which sorts events
newest-first and truncates to 50 (`hub/hub/api/v1/agents.py:800-801`) before building the map from
the ids the *surviving* events name. The turns themselves come from the chat route, which is
bounded separately. So the two are bounded by different things.

Costs no tokens: the agent it drives fails on an unknown CLI flag before a model is contacted.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 scripts/drive/d1_aturn_window.py <agent> <n>
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

AGENT = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 1
CONV = os.environ.get("CONV")


def snapshot(label):
    code, tl = api("GET", f"/projects/{P}/agents/{AGENT}/timeline")
    events = tl.get("events", [])
    runs = tl.get("runs", {})
    named = [e for e in events if (e.get("data") or {}).get("run_id")]
    ids = {(e["data"]["run_id"]) for e in named}
    code2, chat = api("GET", f"/projects/{P}/agent/{AGENT}/chat?limit=500")
    turn_runs = []
    for e in chat.get("entries", []):
        rid = e.get("run_id")
        if rid and rid not in turn_runs:
            turn_runs.append(rid)
    unlabelled = [r for r in turn_runs if r not in runs]
    print(f"--- {label}")
    print(f"    timeline: events={len(events)} (cap 50)  runs_in_map={len(runs)}  ids_named={len(ids)}")
    print(f"    chat:     distinct run ids across turns on screen = {len(turn_runs)}")
    print(f"    turns whose run is NOT in the map (no label, no duration) = {len(unlabelled)}")
    if unlabelled:
        print(f"      {unlabelled}")
    return {"events": len(events), "runs": len(runs), "turns": len(turn_runs), "orphans": unlabelled}


before = snapshot("before")
for i in range(N):
    body = {"agent": AGENT, "message": f"push {i}"}
    if CONV:
        body["conversation_id"] = CONV
    else:
        body["session_mode"] = "new"
    code, out = api("POST", f"/projects/{P}/agent/trigger", body)
    print(f"  trigger {i} -> [{code}] {str(out)[:120]}")
    time.sleep(16)
after = snapshot("after")
print(json.dumps({"before": {k: v for k, v in before.items() if k != 'orphans'},
                  "after": {k: v for k, v in after.items() if k != 'orphans'},
                  "orphans": after["orphans"]}, indent=1))
