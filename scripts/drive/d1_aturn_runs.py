"""D-1, the day window's ordinary e2e slot for `a-turn-says-how-it-ended`.

Makes the runs an operator would make -- one stopped, one failed, one clean -- and prints the
conversation and run ids so the *browser* leg can read what the operator actually sees. The
phase-6/7 harnesses evaluated `aturn_model.py`, a Python transcription of the built component;
nothing has yet asked the served bundle.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 scripts/drive/d1_aturn_runs.py LEG
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

LEG = (sys.argv[1] if len(sys.argv) > 1 else "stop")
OK = os.environ.get("AW_AGENT_OK", "p6driver0903d1")
BAD = os.environ.get("AW_AGENT_FAIL", "p6fail0903d1")
LONG = (
    "Write a 3000 word essay about the history of the bicycle, in full prose, "
    "one paragraph at a time. Use no tools and read no files."
)


def trigger(agent, message):
    code, out = api(
        "POST", f"/projects/{P}/agent/trigger",
        {"agent": agent, "session_mode": "new", "message": message},
    )
    if not isinstance(out, dict) or not out.get("conversation_id"):
        print(f"  ABORT [{code}] {str(out)[:400]}")
        sys.exit(1)
    print(f"  trigger {agent} -> [{code}] conv={out['conversation_id']} run={out.get('run_id')}")
    return out["conversation_id"], out.get("run_id")


def timeline(agent):
    code, out = api("GET", f"/projects/{P}/agents/{agent}/timeline")
    return code, out


def dump_runs(agent, label):
    code, tl = timeline(agent)
    runs = tl.get("runs", {}) if isinstance(tl, dict) else {}
    evs = tl.get("events", []) if isinstance(tl, dict) else []
    named = {(e.get("data") or {}).get("run_id") for e in evs}
    named.discard(None)
    print(f"  --- {label}  GET timeline [{code}]  events={len(evs)}  runs={len(runs)}")
    for rid, f in runs.items():
        print(f"      {rid}  status={f['status']:<12} exit={f.get('exit_code')}  "
              f"started={f['started_at']}  ended={f.get('ended_at')}")
    missing = named - set(runs)
    if missing:
        print(f"      !! events name runs absent from the map: {sorted(missing)}")
    return tl


def wait_idle(agent, seconds=180):
    t0 = time.time()
    while time.time() - t0 < seconds:
        code, roster = api("GET", f"/projects/{P}/agents")
        rows = roster if isinstance(roster, list) else (roster or {}).get("agents", [])
        row = next((r for r in rows if r.get("name") == agent), None)
        if row and row.get("status") != "working":
            return row
        time.sleep(1.5)
    return None


if LEG == "stop":
    conv, run = trigger(OK, LONG)
    time.sleep(6)
    code, body = api("POST", f"/projects/{P}/agent/{OK}/stop")
    print(f"  POST stop -> [{code}] {str(body)[:200]}")
    wait_idle(OK)
    dump_runs(OK, "after the stop")
    print(json.dumps({"leg": "stop", "agent": OK, "conversation": conv, "run": run}))

elif LEG == "fail":
    conv, run = trigger(BAD, "Say hello.")
    wait_idle(BAD)
    dump_runs(BAD, "after the failure")
    print(json.dumps({"leg": "fail", "agent": BAD, "conversation": conv, "run": run}))

elif LEG == "clean":
    conv, run = trigger(OK, "Reply with exactly the word: pear. Use no tools.")
    wait_idle(OK)
    dump_runs(OK, "after the clean turn")
    print(json.dumps({"leg": "clean", "agent": OK, "conversation": conv, "run": run}))

elif LEG == "show":
    dump_runs(sys.argv[2], "timeline")
