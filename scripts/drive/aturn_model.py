"""The *built* a-turn-says-how-it-ended UI, re-implemented in Python, plus the routes that feed it.

This is the successor to `f190_model.py`, which transcribes the UI as it stood at phase 0 — before
the change. Keep both: phase 7 compares the two baselines, and a transcription that has been edited
to match the new code can no longer speak for the old one.

What moved, and why this file exists at all:

  * `GET /agents/{name}/timeline` used to return a bare LIST of events. It now returns an ENVELOPE,
    `{"events": [...], "runs": {run_id: {status, exit_code, started_at, ended_at}}}`.
  * The client's `runStatusByRunId` reducer — which folded the *events* into a status map and so
    lost any run whose terminal event fell off the route's 50-row truncation (F190) — is DELETED.
    `AgentTimeline.tsx` reads `runs[runId].status` directly.
  * `Run.status == "running"` is renamed to `started` at the route boundary (design D5); every other
    value on the wire is the row's own.

Every function below is a line-for-line transcription of the source named above it. When the UI
changes, this file is wrong until it is changed with it.

Env: AW_HUB, AW_KEY, AW_PROJECT, AGENT.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aw import P, api  # noqa: E402

AGENT = os.environ.get("AGENT", "driver")

# ---------------------------------------------------------------- the shipped UI, in Python

# `AgentTimeline.tsx:53-58`
TERMINAL_STATUSES = {"completed", "failed", "stopped", "interrupted"}

# `AgentTimeline.tsx:60-64` — `completed` deliberately has no label.
TERMINAL_LABEL = {
    "failed": "Turn failed",
    "stopped": "Turn stopped",
    "interrupted": "Turn interrupted",
}


def is_success_completion_entry(entry):
    """`agentTimelineModel.ts:24-28`."""
    if entry.get("kind") != "agent_output" or entry.get("output_kind") != "status":
        return False
    payload = entry.get("payload")
    return isinstance(payload, dict) and payload.get("phase") == "completed"


def group_into_turns(entries):
    """`agentTimelineModel.ts:45-62`."""
    delivered = [e for e in entries if e.get("delivery_state") == "delivered"]
    turns, index = [], {}
    for e in delivered:
        key = e.get("run_id") or f"no-run-{e.get('id')}"
        if key not in index:
            index[key] = len(turns)
            turns.append({"runId": e.get("run_id"), "entries": []})
        turns[index[key]]["entries"].append(e)
    return turns


def run_duration_seconds(facts):
    """`AgentTimeline.tsx:85-91` — the run row's own timestamps, not a live counter.

    Returns None for a run still going, one with no `ended_at`, or one whose clock ran backwards.
    """
    if not facts or not facts.get("ended_at"):
        return None
    try:
        from datetime import datetime

        start = datetime.fromisoformat(facts["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(facts["ended_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError, KeyError):
        return None
    if end < start:
        return None
    return round((end - start).total_seconds())


def evaluate(entries, runs, is_running):
    """`AgentTimeline.tsx:146-174` and the per-turn render at `:237-289`, verbatim."""
    turns = group_into_turns(entries)
    last_turn = turns[-1] if turns else None
    last_run_id = last_turn["runId"] if last_turn else None

    signal_1 = bool(last_turn and any(is_success_completion_entry(e) for e in last_turn["entries"]))
    signal_2 = last_run_id is not None and (runs.get(last_run_id) or {}).get(
        "status"
    ) in TERMINAL_STATUSES
    last_run_settled = signal_1 or signal_2

    another = any(
        run_id != last_run_id and (facts or {}).get("status") not in TERMINAL_STATUSES
        for run_id, facts in runs.items()
    )

    last_status = (runs.get(last_run_id) or {}).get("status") if last_run_id else None

    # `AgentTimeline.tsx:237-289` — what EVERY turn on screen says, not only the newest. The
    # newest is what gates the live indicator; the label and the "Worked for Xs" line are drawn
    # per turn, and an interrupted run is routinely not the newest (the Hub reschedules the agent
    # on restart, so a fresh run appears underneath the interrupted one within a second).
    rendered = [
        {
            "runId": t["runId"],
            "status": (runs.get(t["runId"]) or {}).get("status") if t["runId"] else None,
            "terminalLabel": TERMINAL_LABEL.get(
                (runs.get(t["runId"]) or {}).get("status") or "", None
            )
            if t["runId"]
            else None,
            "durationSeconds": run_duration_seconds(runs.get(t["runId"])) if t["runId"] else None,
            "exitCode": (runs.get(t["runId"]) or {}).get("exit_code") if t["runId"] else None,
        }
        for t in turns
    ]

    return {
        "turns": len(turns),
        "rendered": rendered,
        "lastRunId": last_run_id,
        "runs": runs,
        "signal1_entry": signal_1,
        "signal2_runfacts": signal_2,
        "lastRunSettled": last_run_settled,
        "anotherRunIsUnderway": another,
        "isRunning": is_running,
        "runVisiblyActive": bool(is_running) and (not last_run_settled or another),
        # `AgentTimeline.tsx:255` — the divider under the turn.
        "terminalLabel": TERMINAL_LABEL.get(last_status) if last_status else None,
        # `AgentTimeline.tsx:280` -> `TurnBody`'s "Worked for Xs".
        "durationSeconds": run_duration_seconds(runs.get(last_run_id)) if last_run_id else None,
        "exitCode": (runs.get(last_run_id) or {}).get("exit_code") if last_run_id else None,
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


def chat_entries(conv_id, agent=AGENT):
    _, body = api("GET", f"/projects/{P}/agent/{agent}/chat/{conv_id}")
    return (body.get("entries") if isinstance(body, dict) else body) or []


def timeline(agent=AGENT):
    """The envelope. Returns (events, runs) — and REFUSES a bare list, because a bare list is
    exactly the pre-change shape and reading one as `{}` would make every check below vacuous."""
    _, body = api("GET", f"/projects/{P}/agents/{agent}/timeline")
    if not isinstance(body, dict) or "events" not in body or "runs" not in body:
        raise SystemExit(f"timeline route did not return the envelope: {str(body)[:300]}")
    return body["events"], body["runs"]


def output_rows(agent=AGENT):
    _, body = api("GET", f"/projects/{P}/agents/{agent}/output")
    if isinstance(body, dict):
        return body.get("lines") or body.get("output") or body.get("entries") or []
    return body if isinstance(body, list) else []


def read_state(conv_id, agent=AGENT):
    """One snapshot of everything the component sees — a fresh read of all three routes, which
    is exactly what a page reload does."""
    _, runs = timeline(agent)
    row = roster_row(agent)
    return evaluate(chat_entries(conv_id, agent), runs, (row or {}).get("status") == "running")


def wait_idle(agent=AGENT, limit=90):
    for _ in range(limit):
        row = roster_row(agent)
        if row is None or row.get("status") != "running":
            return True
        time.sleep(2)
    return False
