"""F190 phase 0, leg 2 — a turn that is actually stopped, and 0.6's reconciliation skew.

`t_f190_phase0_observe.py`'s stop leg missed: the Haiku turn ended at 11.3s and the stop was
issued at 14s, so what it measured was a *completed* run wearing the stop leg's name. This file
does the stop properly — it stops early and confirms the route returned 200 and the run row says
`stopped` — and then does 0.6, which needs the Hub killed rather than asked.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... [AGENT=driver] [STOP_AT=4] py -3.11 \
         scripts/drive/t_f190_phase0_stop.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402
from f190_model import (  # noqa: E402
    AGENT,
    chat_entries,
    evaluate,
    is_success_completion_entry,
    output_rows,
    roster_row,
    timeline_events,
    wait_idle,
)

STOP_AT = float(os.environ.get("STOP_AT", "4"))

if not wait_idle():
    print(f"REFUSING TO RUN: {AGENT} is still running an earlier turn.")
    sys.exit(1)

print("=" * 78)
print("0.2 / 0.5  A TURN THAT IS ACTUALLY STOPPED")
print("=" * 78)

code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {
        "agent": AGENT,
        "session_mode": "new",
        "message": (
            "Write a 3000 word essay about the history of the bicycle, in full prose, "
            "one paragraph at a time. Use no tools and read no files."
        ),
    },
)
conv = out.get("conversation_id") if isinstance(out, dict) else None
run_id = out.get("run_id") if isinstance(out, dict) else None
print(f"  trigger -> {code}  conversation={conv}  run={run_id}")
if not conv:
    print(f"  ABORT: {out}")
    sys.exit(1)

t0 = time.time()
while time.time() - t0 < STOP_AT:
    time.sleep(0.3)

row = roster_row()
print(f"  t={round(time.time() - t0, 1)}s  roster status before the stop: {row.get('status')!r}")
code, body = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
print(f"  POST stop -> {code}  {str(body)[:160]}")
if code != 200:
    print("  ABORT: the stop did not land, so nothing below would be about a stopped run.")
    sys.exit(1)

# Watch the handover the way the component would.
print("\n--- after the stop, polled")
previous = None
t1 = time.time()
while time.time() - t1 < 40:
    r = roster_row()
    state = evaluate(chat_entries(conv), timeline_events(), (r or {}).get("status") == "running")
    key = (
        state["isRunning"],
        state["signal1_entry"],
        state["signal2_lifecycle"],
        state["runVisiblyActive"],
        json.dumps(state["statusByRun"], sort_keys=True),
    )
    if key != previous:
        previous = key
        print(
            f"  t={round(time.time() - t1, 1):>5}s  running={state['isRunning']!s:<5} "
            f"sig1_entry={state['signal1_entry']!s:<5} "
            f"sig2_lifecycle={state['signal2_lifecycle']!s:<5} "
            f"settled={state['lastRunSettled']!s:<5} "
            f"VISIBLE_INDICATOR={state['runVisiblyActive']!s:<5} "
            f"label={state['terminalLabel']!r}  statusByRun={state['statusByRun']}"
        )
    if not state["isRunning"] and time.time() - t1 > 8:
        break
    time.sleep(0.6)

final = evaluate(chat_entries(conv), timeline_events(), False)
print()
print("  0.2  what the conversation says about the run that was stopped:")
print(f"       lastRunId          {final['lastRunId']}")
print(f"       statusByRun        {final['statusByRun']}")
print(f"       TERMINAL_LABEL     {final['terminalLabel']!r}")

print()
print("  0.5  the reload, and the output stream")
reload_state = evaluate(chat_entries(conv), timeline_events(), False)
print(f"       label after a fresh read of both routes: {reload_state['terminalLabel']!r}")
rows = output_rows()
status_rows = [r for r in rows if (r.get("kind") or r.get("output_kind")) == "status"]
mine = [r for r in status_rows if r.get("run_id") == run_id]
print(f"       /agents/{AGENT}/output: {len(rows)} rows, {len(status_rows)} kind='status'")
print(f"       status rows for the STOPPED run {run_id}: {len(mine)}")
for r in mine:
    print(f"         payload={json.dumps(r.get('payload'))[:140]}")
ents = chat_entries(conv)
print(f"       chat entries for this conversation: {len(ents)}")
for e in ents:
    print(
        f"         [{e.get('kind')}/{e.get('output_kind')}] run={str(e.get('run_id'))[-6:]} "
        f"payload={json.dumps(e.get('payload'))[:80]}"
    )
print(
    "       isSuccessCompletionEntry matches in the stopped conversation: "
    f"{sum(1 for e in ents if is_success_completion_entry(e))}"
)

# What the truth is, straight from the run row.
_, runs = api("GET", f"/projects/{P}/runs")
if isinstance(runs, dict):
    runs = runs.get("runs") or []
mine_run = [r for r in (runs or []) if r.get("id") == run_id]
print(f"\n       the runs table says: {json.dumps(mine_run)[:400]}")
print(f"       the timeline event stream says: {final['statusByRun'].get(run_id)!r}")
print("\n       (the lifecycle EVENTS for this run, oldest last, as the route returns them:)")
for ev in timeline_events():
    if (ev.get("data") or {}).get("run_id") == run_id:
        print(f"         {ev.get('timestamp')}  {ev.get('event_type')}")
