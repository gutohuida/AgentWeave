"""F190 phase 0 — the observation gate for `a-turn-says-how-it-ended`.

Four sittings of review argued about this change and none watched it happen. This file watches
it. It does **not** implement anything and it does not assert a desired outcome: every check
prints what was measured, and the two checks that can falsify the change say so in their labels.

The UI predicates are re-implemented here, line for line, from the shipped source:

  * `isSuccessCompletionEntry`  — `hub/ui/src/lib/agentTimelineModel.ts:24-28`
  * `groupIntoTurns`           — `:45-62`
  * `runStatusByRunId`         — `:187-199`  (last-wins over the array **as the route returns it**)
  * `lastRunSettled`           — `hub/ui/src/components/agents/AgentTimeline.tsx:114-116`
  * `anotherRunIsUnderway`     — `:131-138`
  * `runVisiblyActive`         — `:139`

and they are fed from exactly the three HTTP routes the components read
(`useAgentChatHistory` -> `/agent/{name}/chat/{conv}`, `useAgentTimeline` ->
`/agents/{name}/timeline`, the roster -> `/agents`), polled fast. `useAgentChatHistory` has no
optimistic append (`agentChat.ts:296-312`), so an HTTP poll sees precisely what the component
sees, one refetch earlier at worst.

Run: AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=... [AGENT=driver] py -3.11 \
         scripts/drive/t_f190_phase0_observe.py
"""

import json
import os
import sys

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
    watch,
)

# ------------------------------------------------------------------------------ preconditions

row = roster_row()
if row is None:
    print(f"REFUSING TO RUN: {AGENT!r} is not on this project's roster.")
    sys.exit(1)
if not row.get("runner_id"):
    print(f"REFUSING TO RUN: {AGENT!r} has no runner bound; every turn would only queue.")
    sys.exit(1)
print(f"precondition ok: {AGENT} bound to {row['runner_id']} ({row.get('display_model')})")
if not wait_idle():
    print(f"REFUSING TO RUN: {AGENT} is still running an earlier turn.")
    sys.exit(1)

PROMPT = "Reply with only the two characters OK. Do not read or write files, use no tools."

# ============================================================================ 0.3 — one run
print()
print("=" * 78)
print("0.3  THE SINGLE-RUN WORKING INDICATOR — the observation that can falsify the change")
print("=" * 78)
print("Round 2: this case is unaffected. Round 3b: broken, because signal 1 has never fired.")
print("What decides it: does VISIBLE_INDICATOR go False when the answer text lands, or does it")
print("stay True until the roster poll flips `running` -> `idle`?")

code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {"agent": AGENT, "session_mode": "new", "message": PROMPT},
)
conv_a = out.get("conversation_id") if isinstance(out, dict) else None
print(f"  trigger -> {code}  conversation={conv_a}")
if not conv_a:
    print(f"  ABORT: {out}")
    sys.exit(1)

t_a = watch(conv_a, 150, "conversation A, exactly one run, allowed to complete")

# ============================================================================ 0.2/0.5 — stop
print()
print("=" * 78)
print("0.2  A STOPPED TURN — does the conversation present any terminal label?")
print("=" * 78)
wait_idle()
code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {
        "agent": AGENT,
        "session_mode": "new",
        "message": (
            "Count slowly from 1 to 400, one number per line, writing each on its own line. "
            "Use no tools and read no files."
        ),
    },
)
conv_b = out.get("conversation_id") if isinstance(out, dict) else None
print(f"  trigger -> {code}  conversation={conv_b}")
t_b = watch(conv_b, 150, "conversation B, one run, stopped mid-flight", stop_after=14)

wait_idle()
final_b = evaluate(chat_entries(conv_b), timeline_events(), False)
print("\n  after the stop, the conversation as the component would render it:")
print(f"    lastRunId       {final_b['lastRunId']}")
print(f"    statusByRun     {final_b['statusByRun']}")
print(f"    TERMINAL_LABEL  {final_b['terminalLabel']!r}   <- 0.2: None means no label at all")

# ============================================================================ 0.5 — reload
print()
print("=" * 78)
print("0.5  THE RELOAD — a fresh read of both routes, and the output stream's status rows")
print("=" * 78)
reload_b = evaluate(chat_entries(conv_b), timeline_events(), False)
print(f"    label after reload   {reload_b['terminalLabel']!r}")
stopped_run = reload_b["lastRunId"]
rows = output_rows()
status_rows = [r for r in rows if (r.get("kind") or r.get("output_kind")) == "status"]
print(f"    /agents/{AGENT}/output: {len(rows)} rows, {len(status_rows)} of kind='status'")
for r in status_rows[:10]:
    print(f"      run={r.get('run_id')}  payload={json.dumps(r.get('payload'))[:110]}")
print(
    f"    status rows for the STOPPED run {stopped_run}: "
    f"{len([r for r in status_rows if r.get('run_id') == stopped_run])}"
)
_, raw_chat_b = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{conv_b}")
ents_b = (raw_chat_b.get("entries") if isinstance(raw_chat_b, dict) else []) or []
print(
    f"    chat entries for B: {len(ents_b)}; "
    f"isSuccessCompletionEntry matches: {sum(1 for e in ents_b if is_success_completion_entry(e))}"
)
_, raw_chat_a = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{conv_a}")
ents_a = (raw_chat_a.get("entries") if isinstance(raw_chat_a, dict) else []) or []
print(
    f"    chat entries for A (the COMPLETED run): {len(ents_a)}; "
    f"isSuccessCompletionEntry matches: {sum(1 for e in ents_a if is_success_completion_entry(e))}"
)
for e in ents_a:
    if e.get("kind") == "agent_output" and e.get("output_kind") == "status":
        print(f"      A status entry payload: {json.dumps(e.get('payload'))[:200]}")

# ============================================================================ 0.4 — two runs
print()
print("=" * 78)
print("0.4  THE MULTI-RUN INDICATOR — two or more ended runs in the event window")
print("=" * 78)
print("Round 2 correction 1 predicts `anotherRunIsUnderway` is True whenever a second run's")
print("status is non-terminal, which — given `statusByRun` is all 'started' — is whenever two")
print("runs exist. That collapses the gate to `isRunning`, the pre-fix behaviour.")
wait_idle()
code, out = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {"agent": AGENT, "conversation_id": conv_a, "message": PROMPT},
)
print(f"  trigger (second run in conversation A) -> {code} {str(out)[:120]}")
t_c = watch(conv_a, 150, "conversation A, now two runs")

wait_idle()
final_a = evaluate(chat_entries(conv_a), timeline_events(), False)
print(f"\n    A now has {final_a['turns']} turns; statusByRun={final_a['statusByRun']}")
print(f"    anotherRunIsUnderway (idle agent) = {final_a['anotherRunIsUnderway']}")
print(
    "    -> with isRunning True this would force VISIBLE_INDICATOR True regardless of settled: "
    f"{final_a['anotherRunIsUnderway']}"
)

# ============================================================================ verdict
print()
print("=" * 78)
print("WHAT WAS SEEN")
print("=" * 78)


def released_cleanly(transitions):
    """Did the indicator go False on the same snapshot the answer text became visible?"""
    first_answer = next((s for s in transitions if s["answerText"]), None)
    first_off = next((s for s in transitions if not s["runVisiblyActive"] and s["t"] > 0), None)
    if first_answer is None:
        return None, None, None
    return first_answer["t"], (first_off or {}).get("t"), first_answer["runVisiblyActive"]


ans_t, off_t, on_at_answer = released_cleanly(t_a)
print(f"  0.3  answer text first visible at t={ans_t}s")
print(f"       indicator first False at    t={off_t}s")
print(f"       indicator still ON when the answer landed: {on_at_answer}")
print(f"       signal 1 (entry) ever True in run A: {any(s['signal1_entry'] for s in t_a)}")
print(f"       signal 2 (lifecycle) ever True in run A: {any(s['signal2_lifecycle'] for s in t_a)}")
print(f"  0.2  terminal label for the stopped run: {final_b['terminalLabel']!r}")
print(f"  0.4  anotherRunIsUnderway with two ended runs: {final_a['anotherRunIsUnderway']}")
print("\n(0.6 is a direct database read and lives in t_f190_phase0_reconcile.py.)")
