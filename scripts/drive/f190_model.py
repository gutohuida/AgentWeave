"""The shipped UI's run-status predicates, re-implemented in Python, plus the three routes
that feed them.

Shared by `t_f190_phase0_observe.py` and `t_f190_phase0_stop.py` so both legs of F190's phase 0
evaluate the *same* code. Every function below is a line-for-line transcription of the source
named above it; when the UI changes, this file is wrong until it is changed with it.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aw import P, api  # noqa: E402

AGENT = os.environ.get("AGENT", "driver")

# ---------------------------------------------------------------- the shipped UI, in Python

LIFECYCLE_EVENT_STATUS = {
    "run_started": "started",
    "run_completed": "completed",
    "run_failed": "failed",
    "run_stopped": "stopped",
    "run_interrupted": "interrupted",
}
TERMINAL_STATUSES = {"completed", "failed", "stopped", "interrupted"}
TERMINAL_LABEL = {
    "failed": "Turn failed",
    "stopped": "Turn stopped",
    "interrupted": "Turn interrupted",
}


def is_success_completion_entry(entry):
    if entry.get("kind") != "agent_output" or entry.get("output_kind") != "status":
        return False
    payload = entry.get("payload")
    return isinstance(payload, dict) and payload.get("phase") == "completed"


def group_into_turns(entries):
    delivered = [e for e in entries if e.get("delivery_state") == "delivered"]
    turns, index = [], {}
    for e in delivered:
        key = e.get("run_id") or f"no-run-{e.get('id')}"
        if key not in index:
            index[key] = len(turns)
            turns.append({"runId": e.get("run_id"), "entries": []})
        turns[index[key]]["entries"].append(e)
    return turns


def run_status_by_run_id(events):
    """`agentTimelineModel.ts:187-199` — unconditional assignment, so the LAST event seen wins."""
    result = {}
    for event in events:
        status = LIFECYCLE_EVENT_STATUS.get(event.get("event_type"))
        run_id = (event.get("data") or {}).get("run_id")
        if status and isinstance(run_id, str):
            result[run_id] = status
    return result


def evaluate(entries, events, is_running):
    """`AgentTimeline.tsx:113-139`, verbatim."""
    turns = group_into_turns(entries)
    status_by_run = run_status_by_run_id(events)
    last_turn = turns[-1] if turns else None
    last_run_id = last_turn["runId"] if last_turn else None
    signal_1 = bool(last_turn and any(is_success_completion_entry(e) for e in last_turn["entries"]))
    signal_2 = last_run_id is not None and status_by_run.get(last_run_id) in TERMINAL_STATUSES
    last_run_settled = signal_1 or signal_2
    another = any(
        rid != last_run_id and st not in TERMINAL_STATUSES for rid, st in status_by_run.items()
    )
    return {
        "turns": len(turns),
        "lastRunId": last_run_id,
        "statusByRun": status_by_run,
        "signal1_entry": signal_1,
        "signal2_lifecycle": signal_2,
        "lastRunSettled": last_run_settled,
        "anotherRunIsUnderway": another,
        "isRunning": is_running,
        "runVisiblyActive": bool(is_running) and (not last_run_settled or another),
        "terminalLabel": TERMINAL_LABEL.get(status_by_run.get(last_run_id or "")),
        "answerText": [
            e
            for e in (last_turn["entries"] if last_turn else [])
            if e.get("kind") == "agent_output" and e.get("output_kind") == "text"
        ],
    }


# ------------------------------------------------------------------------------- transport


def roster_row(name=AGENT):
    _, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    for row in rows:
        if row.get("name") == name:
            return row
    return None


def chat_entries(conv_id):
    _, body = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{conv_id}")
    return (body.get("entries") if isinstance(body, dict) else body) or []


def timeline_events():
    _, body = api("GET", f"/projects/{P}/agents/{AGENT}/timeline")
    return body if isinstance(body, list) else []


def output_rows():
    _, body = api("GET", f"/projects/{P}/agents/{AGENT}/output")
    if isinstance(body, dict):
        return body.get("lines") or body.get("output") or body.get("entries") or []
    return body if isinstance(body, list) else []


def wait_idle(limit=90):
    for _ in range(limit):
        row = roster_row()
        if row is None or row.get("status") != "running":
            return True
        time.sleep(2)
    return False


def watch(conv_id, seconds, label, stop_after=None):
    """Poll the three routes and evaluate the gate on every snapshot.

    Returns the list of snapshots where any of the four observable booleans changed, so the
    output is a transition log rather than a wall of identical rows.
    """
    print(f"\n--- watching: {label}")
    transitions, previous, t0, stopped = [], None, time.time(), False
    while time.time() - t0 < seconds:
        now = round(time.time() - t0, 1)
        row = roster_row()
        state = evaluate(
            chat_entries(conv_id), timeline_events(), (row or {}).get("status") == "running"
        )
        key = (
            state["isRunning"],
            state["signal1_entry"],
            state["signal2_lifecycle"],
            state["runVisiblyActive"],
            len(state["answerText"]),
            json.dumps(state["statusByRun"], sort_keys=True),
        )
        if key != previous:
            previous = key
            state["t"] = now
            transitions.append(state)
            print(
                f"  t={now:>5}s  running={state['isRunning']!s:<5} "
                f"sig1_entry={state['signal1_entry']!s:<5} "
                f"sig2_lifecycle={state['signal2_lifecycle']!s:<5} "
                f"settled={state['lastRunSettled']!s:<5} "
                f"another={state['anotherRunIsUnderway']!s:<5} "
                f"VISIBLE_INDICATOR={state['runVisiblyActive']!s:<5} "
                f"answers={len(state['answerText'])} "
                f"statusByRun={state['statusByRun']}"
            )
        if stop_after is not None and not stopped and now >= stop_after:
            code, body = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
            print(f"  t={now:>5}s  >>> POST stop -> {code} {str(body)[:120]}")
            stopped = True
        # The run is over, the roster has caught up, and nothing has moved for three seconds.
        if (
            stop_after is None
            and not state["isRunning"]
            and state["turns"] > 0
            and now > 6
            and state["answerText"]
            and transitions
            and now - transitions[-1]["t"] > 3
        ):
            break
        time.sleep(0.6)
    return transitions
