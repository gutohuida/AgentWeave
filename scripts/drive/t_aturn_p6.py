"""a-turn-says-how-it-ended, phase 6 — the implementer drives the built change.

Tasks 6.1 (a stopped turn names its stop), 6.2 (it survives a reload, with the exit code),
and 6.3 (the same for a failed run and an interrupted one).

The evaluation is `aturn_model.py`, a transcription of the *built* component. Every check below
therefore asks what the operator's screen would say, not what the database contains.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... AGENT=p6driver0903 \
        LEG=stop|fail|interrupt-start|interrupt-read py -3.11 scripts/drive/t_aturn_p6.py

`interrupt` is two calls with a Hub kill in between: `interrupt-start` prints the conversation and
run ids, the caller kills the Hub *tree* and restarts it, then `interrupt-read CONV=... RUN=...`
reads what the operator would see. `run_reconciliation.reconcile_interrupted_runs` only marks a run
interrupted when its pid is gone, which is why the whole tree has to go.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aturn_model import AGENT, evaluate, output_rows, read_state, roster_row, wait_idle  # noqa: E402
from aw import P, api  # noqa: E402

LEG = os.environ.get("LEG", "stop")
STOP_AT = float(os.environ.get("STOP_AT", "5"))
LONG_PROMPT = (
    "Write a 3000 word essay about the history of the bicycle, in full prose, "
    "one paragraph at a time. Use no tools and read no files."
)

PASS, FAIL = [], []


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  — ' + detail) if detail else ''}")


def trigger(message):
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "session_mode": "new", "message": message},
    )
    conv = out.get("conversation_id") if isinstance(out, dict) else None
    run = out.get("run_id") if isinstance(out, dict) else None
    print(f"  trigger -> {code}  conversation={conv}  run={run}")
    if not conv:
        print(f"  ABORT: {out}")
        sys.exit(1)
    return conv, run


def show_state(label, state, run_id):
    print(f"\n  --- {label}")
    print(f"      lastRunId        {state['lastRunId']}")
    print(f"      runs             {json.dumps(state['runs'], default=str)[:400]}")
    print(f"      TERMINAL_LABEL   {state['terminalLabel']!r}")
    print(f"      durationSeconds  {state['durationSeconds']}")
    print(f"      exit_code        {state['exitCode']}")
    print(f"      settled={state['lastRunSettled']}  visibleIndicator={state['runVisiblyActive']}")
    if run_id and run_id not in state["runs"]:
        print(f"      !! run {run_id} is absent from the envelope")


def poll_until_settled(conv, seconds=90):
    previous, t0 = None, time.time()
    while time.time() - t0 < seconds:
        state = read_state(conv)
        key = (
            state["isRunning"],
            state["lastRunSettled"],
            state["runVisiblyActive"],
            json.dumps({k: v.get("status") for k, v in state["runs"].items()}, sort_keys=True),
        )
        if key != previous:
            previous = key
            print(
                f"      t={round(time.time() - t0, 1):>5}s  running={state['isRunning']!s:<5} "
                f"settled={state['lastRunSettled']!s:<5} "
                f"INDICATOR={state['runVisiblyActive']!s:<5} "
                f"label={state['terminalLabel']!r}  "
                f"statuses={ {k: v.get('status') for k, v in state['runs'].items()} }"
            )
        if state["lastRunSettled"] and not state["isRunning"]:
            return state
        time.sleep(0.8)
    return read_state(conv)


# ---------------------------------------------------------------------------------- legs


def leg_stop():
    print("=" * 78)
    print(f"6.1 / 6.2  A STOPPED TURN NAMES ITS STOP, AND SURVIVES A RELOAD   agent={AGENT}")
    print("=" * 78)
    if not wait_idle():
        print(f"REFUSING: {AGENT} is still running an earlier turn.")
        sys.exit(1)

    conv, run_id = trigger(LONG_PROMPT)
    t0 = time.time()
    while time.time() - t0 < STOP_AT:
        time.sleep(0.3)
    row = roster_row()
    print(f"  t={round(time.time() - t0, 1)}s  roster before the stop: {(row or {}).get('status')!r}")
    code, body = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
    print(f"  POST stop -> {code}  {str(body)[:160]}")
    if code != 200:
        print("  ABORT: the stop did not land.")
        sys.exit(1)

    print("\n  polled, the way the component re-reads after every SSE frame:")
    state = poll_until_settled(conv)
    show_state("6.1 — what the conversation says", state, run_id)

    check("6.1 the run the turn names is IN the envelope", run_id in state["runs"], str(run_id))
    check(
        "6.1 its status is 'stopped'",
        (state["runs"].get(run_id) or {}).get("status") == "stopped",
        repr((state["runs"].get(run_id) or {}).get("status")),
    )
    check(
        "6.1 the turn is labelled 'Turn stopped'",
        state["terminalLabel"] == "Turn stopped",
        repr(state["terminalLabel"]),
    )
    check("6.1 the live indicator is gone", not state["runVisiblyActive"])

    # 6.2 — a reload is a fresh read of all three routes with no accumulated client state.
    time.sleep(1.5)
    reloaded = read_state(conv)
    show_state("6.2 — after a reload (fresh reads, no client state)", reloaded, run_id)
    check(
        "6.2 the label is still there after a reload",
        reloaded["terminalLabel"] == "Turn stopped",
        repr(reloaded["terminalLabel"]),
    )
    check(
        "6.2 the exit code is still there after a reload",
        reloaded["exitCode"] is not None,
        f"exit_code={reloaded['exitCode']!r}",
    )
    check(
        "6.2 the turn still says what it cost",
        reloaded["durationSeconds"] is not None and reloaded["durationSeconds"] >= 0,
        f"Worked for {reloaded['durationSeconds']}s",
    )

    # The phase-2 guarantee, read from the source it persists to.
    rows = [r for r in output_rows() if (r.get("kind") or r.get("output_kind")) == "status"]
    mine = [r for r in rows if r.get("run_id") == run_id]
    print(f"\n      /agents/{AGENT}/output: {len(rows)} status rows, {len(mine)} for this run")
    for r in mine:
        print(f"        payload={json.dumps(r.get('payload'))[:160]}")
    check(
        "phase 2: the terminal status row is PERSISTED, not merely broadcast",
        len(mine) >= 1,
        f"{len(mine)} row(s)",
    )
    return conv


def leg_fail():
    print("=" * 78)
    print(f"6.3a  A FAILED RUN NAMES ITS FAILURE   agent={AGENT}")
    print("=" * 78)
    if not wait_idle():
        print(f"REFUSING: {AGENT} is still running an earlier turn.")
        sys.exit(1)
    conv, run_id = trigger("Say the single word: ok.")
    state = poll_until_settled(conv, seconds=90)
    show_state("6.3a — what the conversation says", state, run_id)
    check("6.3a the run is in the envelope", run_id in state["runs"], str(run_id))
    check(
        "6.3a its status is 'failed'",
        (state["runs"].get(run_id) or {}).get("status") == "failed",
        repr((state["runs"].get(run_id) or {}).get("status")),
    )
    check(
        "6.3a the turn is labelled 'Turn failed'",
        state["terminalLabel"] == "Turn failed",
        repr(state["terminalLabel"]),
    )
    time.sleep(1.5)
    reloaded = read_state(conv)
    show_state("6.3a — after a reload", reloaded, run_id)
    check(
        "6.3a the label survives a reload",
        reloaded["terminalLabel"] == "Turn failed",
        repr(reloaded["terminalLabel"]),
    )
    check(
        "6.3a the exit code survives a reload",
        reloaded["exitCode"] is not None,
        f"exit_code={reloaded['exitCode']!r}",
    )
    rows = [r for r in output_rows() if (r.get("kind") or r.get("output_kind")) == "status"]
    mine = [r for r in rows if r.get("run_id") == run_id]
    check(
        "6.3a phase 2: a persisted terminal status row for the failed run",
        len(mine) >= 1,
        f"{len(mine)} row(s): " + "; ".join(json.dumps(r.get("payload"))[:90] for r in mine),
    )
    return conv


def leg_interrupt_start():
    print("=" * 78)
    print(f"6.3b  AN INTERRUPTED RUN — leg 1, start a turn and leave it running   agent={AGENT}")
    print("=" * 78)
    if not wait_idle():
        print(f"REFUSING: {AGENT} is still running an earlier turn.")
        sys.exit(1)
    conv, run_id = trigger(LONG_PROMPT)
    t0 = time.time()
    while time.time() - t0 < STOP_AT:
        time.sleep(0.3)
    row = roster_row()
    print(f"  t={round(time.time() - t0, 1)}s  roster: {(row or {}).get('status')!r}")
    print()
    print(f"CONV={conv}")
    print(f"RUN={run_id}")
    print("Now kill the Hub PROCESS TREE and restart it, then re-run with LEG=interrupt-read.")


def leg_interrupt_read():
    conv = os.environ["CONV"]
    run_id = os.environ["RUN"]
    print("=" * 78)
    print("6.3b  AN INTERRUPTED RUN — leg 2, after the Hub came back")
    print("=" * 78)
    # The Hub reschedules the agent as part of reconciliation ("Draining N deferred
    # post-reconciliation schedule(s)"), so a NEW run starts within a second of the restart and
    # the interrupted turn is no longer the newest. Let that one finish, then read — otherwise
    # every assertion below is about the wrong turn.
    if not wait_idle(limit=120):
        print("  NOTE: the rescheduled run is still going; reading anyway.")
    state = read_state(conv)
    show_state("6.3b — what the conversation says after the restart", state, run_id)
    print("      per-turn render:")
    for r in state["rendered"]:
        print(
            f"        run={r['runId']}  status={r['status']!r:<14} "
            f"label={r['terminalLabel']!r:<22} worked_for={r['durationSeconds']}"
        )
    mine = next((r for r in state["rendered"] if r["runId"] == run_id), None)

    check("6.3b the run is in the envelope", run_id in state["runs"], str(run_id))
    check(
        "6.3b its status is 'interrupted'",
        (state["runs"].get(run_id) or {}).get("status") == "interrupted",
        repr((state["runs"].get(run_id) or {}).get("status")),
    )
    check("6.3b the interrupted run still has a turn on screen", mine is not None)
    check(
        "6.3b that turn is labelled 'Turn interrupted'",
        bool(mine) and mine["terminalLabel"] == "Turn interrupted",
        repr(mine and mine["terminalLabel"]),
    )
    check(
        "6.3b that turn still says what it cost",
        bool(mine) and mine["durationSeconds"] is not None,
        f"Worked for {mine and mine['durationSeconds']}s",
    )
    check(
        "6.3b the live indicator is gone once the rescheduled run has ended",
        not state["runVisiblyActive"],
        f"isRunning={state['isRunning']} settled={state['lastRunSettled']} "
        f"another={state['anotherRunIsUnderway']}",
    )
    # An interrupted run is exactly the case F190 could not survive: the terminal event is written
    # at RESTART time, so it is the newest event on the agent, but the run itself is old.
    _, tl = api("GET", f"/projects/{P}/agents/{AGENT}/timeline")
    ids = [e.get("id") for e in (tl.get("events") or [])]
    print(f"      timeline events returned: {len(ids)} (route truncates at 50)")


print(f"HUB={os.environ.get('AW_HUB')}  PROJECT={P}  AGENT={AGENT}  LEG={LEG}")
if LEG == "stop":
    leg_stop()
elif LEG == "fail":
    leg_fail()
elif LEG == "interrupt-start":
    leg_interrupt_start()
elif LEG == "interrupt-read":
    leg_interrupt_read()
else:
    print(f"unknown LEG={LEG}")
    sys.exit(2)

if PASS or FAIL:
    print()
    print(f"RESULT  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)
