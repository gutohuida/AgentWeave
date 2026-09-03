"""a-turn-says-how-it-ended, phase 7 — the verification round drives the built change.

Phase 6 was the implementer checking its own work. This sitting did not write the code. It
re-runs phase 0's observations (`tasks.md` 0.2, 0.3, 0.4, 0.5) against the built product and
asks, for each one, whether it moved the way the change said it would.

The comparison is made *on one capture*. Every leg reads the three routes once and feeds the
same bytes to two transcriptions:

  * `f190_model.evaluate(entries, envelope["events"], running)` — the UI as it stood at phase 0.
  * `aturn_model.evaluate(entries, envelope["runs"], running)` — the UI as built.

That is what makes it a comparison rather than two drives. The phase-0 model is fed the
`events` half of the envelope, which is byte-identical to the bare list the route used to
return, so it computes exactly what the old UI would have computed from today's data.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... AGENT=p6driverp7 \
        LEG=stop|stopfast|two py -3.11 scripts/drive/t_aturn_p7.py

`f190_model.py` is the phase 0 baseline and is NOT edited to match the new code.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aturn_model  # noqa: E402
import f190_model  # noqa: E402
from aw import P, api  # noqa: E402

AGENT = os.environ.get("AGENT", "driver")
LEG = os.environ.get("LEG", "stop")
STOP_AT = float(os.environ.get("STOP_AT", "5"))
LONG_PROMPT = (
    "Write a 3000 word essay about the history of the bicycle, in full prose, "
    "one paragraph at a time. Use no tools and read no files."
)
SHORT_PROMPT = "Reply with exactly the word: pear. Use no tools and read no files."

PASS, FAIL = [], []


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  - ' + detail) if detail else ''}")


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
        sys.exit(f"  ABORT: {out}")
    return conv, run


def capture(conv):
    """One snapshot of all three routes — what a page load sees — evaluated by both models."""
    entries = aturn_model.chat_entries(conv, AGENT)
    events, runs = aturn_model.timeline(AGENT)
    row = aturn_model.roster_row(AGENT)
    running = (row or {}).get("status") == "running"
    return {
        "old": f190_model.evaluate(entries, events, running),
        "new": aturn_model.evaluate(entries, runs, running),
        "events": events,
        "runs": runs,
        "entries": entries,
        "running": running,
    }


def report(label, cap, run_id=None):
    old, new = cap["old"], cap["new"]
    built = {k: v.get("status") for k, v in new["runs"].items()}
    print(f"\n  --- {label}")
    print(f"      roster running        {cap['running']}")
    print(f"      PHASE 0 statusByRun   {json.dumps(old['statusByRun'], sort_keys=True)}")
    print(f"      BUILT   runs          {json.dumps(built, sort_keys=True)}")
    print(f"      PHASE 0 label         {old['terminalLabel']!r}")
    print(f"      BUILT   label         {new['terminalLabel']!r}")
    print(f"      BUILT   duration      {new['durationSeconds']}   exit={new['exitCode']}")
    print(
        f"      PHASE 0 settled={old['lastRunSettled']!s:<5} "
        f"another={old['anotherRunIsUnderway']!s:<5} INDICATOR={old['runVisiblyActive']}"
    )
    print(
        f"      BUILT   settled={new['lastRunSettled']!s:<5} "
        f"another={new['anotherRunIsUnderway']!s:<5} INDICATOR={new['runVisiblyActive']}"
    )
    if run_id:
        print(f"      run {run_id} in envelope: {run_id in new['runs']}")


def settle(conv, seconds=150):
    t0 = time.time()
    while time.time() - t0 < seconds:
        cap = capture(conv)
        if cap["new"]["lastRunSettled"] and not cap["running"]:
            return cap
        time.sleep(1.0)
    return capture(conv)


def status_rows_for(run_id):
    out = []
    for row in aturn_model.output_rows(AGENT):
        if row.get("run_id") != run_id:
            continue
        if row.get("kind") == "status" or row.get("output_kind") == "status":
            out.append(row)
    return out


# --------------------------------------------------------------------------- legs


def leg_stop(stop_at, tag):
    """Phase 0 task 0.2 (the headline), 0.5 (the reload), and 7.1a when stop_at is early."""
    conv, run = trigger(LONG_PROMPT)
    time.sleep(stop_at)
    code, body = api("POST", f"/projects/{P}/agent/{AGENT}/stop")
    print(f"  POST stop after {stop_at}s -> {code} {str(body)[:120]}")

    cap = settle(conv)
    report(f"{tag}: first read after the stop", cap, run)

    old, new = cap["old"], cap["new"]
    check(
        f"{tag} 0.2 baseline reproduces: the phase 0 UI shows NO terminal label on this data",
        old["terminalLabel"] is None,
        f"phase-0 model says {old['terminalLabel']!r}",
    )
    check(
        f"{tag} 0.2 baseline reproduces: phase 0 read every run as 'started'",
        bool(old["statusByRun"]) and set(old["statusByRun"].values()) == {"started"},
        json.dumps(old["statusByRun"], sort_keys=True),
    )
    check(
        f"{tag} 0.2 MOVED: the built turn names its stop",
        new["terminalLabel"] == "Turn stopped",
        f"built model says {new['terminalLabel']!r}",
    )
    check(
        f"{tag} the stopped run is in the envelope with its true status",
        (new["runs"].get(run) or {}).get("status") == "stopped",
        json.dumps(new["runs"].get(run), default=str),
    )
    check(
        f"{tag} 7.1a the same turn still reports what it cost (Worked for Xs)",
        isinstance(new["durationSeconds"], int),
        f"durationSeconds={new['durationSeconds']}",
    )
    if tag == "stopfast":
        # 7.1a is only the check it claims to be if the turn genuinely produced nothing.
        # Persisting the status row is what can take the duration line with it (task 4.5a), and
        # a turn that already has text would draw the line for other reasons.
        check(
            "stopfast 7.1a precondition: the turn produced no answer text at all",
            len(new["answerText"]) == 0,
            f"{len(new['answerText'])} text entries in the last turn",
        )
        check(
            "stopfast 7.1a the empty turn carries BOTH the label and the duration",
            new["terminalLabel"] == "Turn stopped" and isinstance(new["durationSeconds"], int),
            f"label={new['terminalLabel']!r} duration={new['durationSeconds']}",
        )
    check(
        f"{tag} the indicator has released",
        new["runVisiblyActive"] is False and new["lastRunSettled"] is True,
        f"settled={new['lastRunSettled']} visible={new['runVisiblyActive']}",
    )

    # 0.5 — the reload. A second full read of all three routes, which is what a page load does.
    time.sleep(2)
    again = capture(conv)
    report(f"{tag}: after a reload", again, run)
    check(
        f"{tag} 0.5 MOVED: the label survives a reload",
        again["new"]["terminalLabel"] == "Turn stopped",
        f"{again['new']['terminalLabel']!r}",
    )
    rows = status_rows_for(run)
    check(
        f"{tag} 0.5 MOVED: /output holds a status row for the stopped run "
        f"(phase 0 measured zero of nine)",
        len(rows) >= 1,
        f"{len(rows)} status rows: {json.dumps(rows[:1], default=str)[:240]}",
    )
    check(
        f"{tag} 0.5 the reloaded read still carries the exit code",
        again["new"]["exitCode"] is not None,
        f"exit={again['new']['exitCode']}",
    )
    return conv, run


def leg_two():
    """Phase 0 task 0.3 (the completed single-run case, which must NOT change) and 0.4
    (the multi-run indicator)."""
    conv, run1 = trigger(SHORT_PROMPT)
    cap1 = settle(conv)
    report("0.3: one completed run in the window", cap1, run1)
    old, new = cap1["old"], cap1["new"]
    check(
        "0.3 UNCHANGED: a completed single-run conversation releases in BOTH models",
        old["runVisiblyActive"] is False and new["runVisiblyActive"] is False,
        f"phase0={old['runVisiblyActive']} built={new['runVisiblyActive']}",
    )
    check(
        "0.3 UNCHANGED: signal 1 fires in both, on the status row the stream parser writes",
        old["signal1_entry"] is True and new["signal1_entry"] is True,
        f"phase0={old['signal1_entry']} built={new['signal1_entry']}",
    )
    check(
        "0.3 UNCHANGED: a completed turn draws no terminal label in either model",
        old["terminalLabel"] is None and new["terminalLabel"] is None,
        f"phase0={old['terminalLabel']!r} built={new['terminalLabel']!r}",
    )

    # A second turn in the SAME conversation. `session_mode` takes only "new" or "resume"
    # (`agent_trigger.py:1226`); naming the conversation is what continues it. Passing
    # "continue" here returns 400 and leaves the leg measuring one run, which is how this was
    # found.
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "conversation_id": conv, "message": SHORT_PROMPT},
    )
    run2 = out.get("run_id") if isinstance(out, dict) else None
    print(f"  second trigger -> {code}  run={run2}")
    check(
        "0.4 harness: the second trigger actually started a second run in this conversation",
        bool(run2) and run2 != run1,
        f"code={code} run2={run2} {str(out)[:160]}",
    )
    cap2 = settle(conv)
    report("0.4: two ended runs in the window", cap2, run2)
    old2, new2 = cap2["old"], cap2["new"]
    built2 = {k: v.get("status") for k, v in new2["runs"].items()}
    check(
        "0.4 baseline reproduces: with two ended runs the phase 0 UI still believes another "
        "run is underway",
        old2["anotherRunIsUnderway"] is True,
        f"phase-0 statusByRun={json.dumps(old2['statusByRun'], sort_keys=True)}",
    )
    check(
        "0.4 MOVED: the built UI knows every other run in the window has ended",
        new2["anotherRunIsUnderway"] is False,
        f"built runs={json.dumps(built2, sort_keys=True)}",
    )
    check(
        "0.4 MOVED: the built indicator is released by the run facts, not by the roster poll",
        new2["runVisiblyActive"] is False,
        f"built settled={new2['lastRunSettled']} another={new2['anotherRunIsUnderway']}",
    )
    check(
        "0.4 the older run is still covered by the envelope after a newer one ran",
        run1 in new2["runs"],
        f"runs keys={sorted(new2['runs'])}",
    )
    check(
        "0.4 the conversation really holds two turns, and each is drawn from its OWN run",
        len(new2["rendered"]) >= 2
        and {r["runId"] for r in new2["rendered"]} >= {run1, run2}
        and all(r["status"] == built2.get(r["runId"]) for r in new2["rendered"] if r["runId"]),
        json.dumps(new2["rendered"], default=str)[:300],
    )
    return conv, run1, run2


if __name__ == "__main__":
    print(f"=== a-turn phase 7 verification round - LEG={LEG}  project={P}  agent={AGENT}")
    if LEG == "stop":
        leg_stop(STOP_AT, "stop")
    elif LEG == "stopfast":
        leg_stop(float(os.environ.get("STOP_AT", "1.0")), "stopfast")
    elif LEG == "two":
        leg_two()
    else:
        sys.exit(f"unknown LEG={LEG}")

    print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
