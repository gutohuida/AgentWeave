"""Sweep row 5's screen half — what an operator sees of a run that was stopped, and of a message
the Hub dropped.

The API half measures what the Hub records. This asks the questions it cannot: after the operator
clicks Stop, does the surface they were watching say the run was *stopped* — and after the Hub
gives up on an operator's message, does anything on screen say so. Both are F187's shape, which by
row 4 had appeared at three sites.

It also drives the Workspace section of agent settings, whose own docstring
(`AgentSettingsPage.tsx:435-442`) says the provider-session rows are useful because of "the path:
this is where the agent's work actually happened".

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<project id> AW_AGENT=<an agent with a claude runner>
     AW_SHOTS=<dir> py -3.11 scripts/drive/t_sweep_row5_ui.py

This one starts and stops a REAL Haiku turn, because a stop is only observable against a process
that is actually running. Set AW_SKIP_TURN=1 to look at whatever the project already holds.

Every assertion about text an operator must READ goes through `page.inner_text("body")`, never
`page.content()` — row 3 lost a real defect to a green row because a needle matched the markup.

The Hub on :8011 serves `hub/hub/static/ui`, a committed build artefact, so what this captures is
the shipped bundle rather than `hub/ui/src`.
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
AGENT = os.environ["AW_AGENT"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""

A = f"/projects/{PROJECT}"
results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {shown}" if shown else ""))


# ---------------------------------------------------------------- a run to look at
#
# Started here rather than assumed, so the screen assertions below are about a stop this script
# watched happen. The turn is given time to *produce output* before being stopped: a run killed
# before it says anything cannot distinguish "the surface hides the stop" from "there was nothing
# to show".


def settle_agent():
    """Leave the agent idle with nothing pending, so the turn below is the only one in flight.

    Written after a first attempt measured nothing: the previous harness had left this agent
    blocked inside `ask_user`, so the trigger queued behind it and the stop landed on the *old*
    run. A screen assertion about a stop needs the stop to be the one this script made.
    """
    for _ in range(30):
        code, qs = api("GET", f"{A}/questions?status=pending")
        rows = (
            qs if isinstance(qs, list) else qs.get("questions", []) if isinstance(qs, dict) else []
        )
        for q in rows:
            api("POST", f"{A}/questions/{q['id']}/decline", {"reason": "row5 harness teardown"})
        api("POST", f"{A}/agent/{AGENT}/stop")
        code, agents = api("GET", f"{A}/agents")
        row = (
            next((a for a in agents if a["name"] == AGENT), None)
            if isinstance(agents, list)
            else None
        )
        code, qstat = api("GET", f"{A}/queue/{AGENT}/status")
        idle = row and row.get("status") != "running" and not (qstat or {}).get("running")
        if idle:
            # Drop anything still queued, so the trigger below starts immediately.
            code, entries = api("GET", f"{A}/queue/{AGENT}")
            for e in entries if isinstance(entries, list) else []:
                if e["state"] == "queued":
                    api("DELETE", f"{A}/queue/entries/{e['id']}")
            return True
        time.sleep(3)
    return False


RUN = None
CONV = None
STOPPED = False
if not os.environ.get("AW_SKIP_TURN"):
    check("the agent could be settled to idle before the stop is driven", settle_agent(), "")
    # Up to three attempts, because the stop has to land while the process is still alive and a
    # Haiku turn can finish inside the polling window — a stop that arrives late is answered 404
    # and measures nothing about the screen. The first version of this waited for three output
    # rows and stopped a run that had already completed.
    for _attempt in range(3):
        code, trig = api(
            "POST",
            f"{A}/agent/trigger",
            {
                "agent": AGENT,
                "message": (
                    "Write a detailed 1500-word essay about the history of the printing press. "
                    "Write it directly in your reply, in full prose, without using any tools."
                ),
            },
        )
        RUN = trig.get("run_id") if code == 200 else None
        CONV = trig.get("conversation_id") if code == 200 else None
        if not RUN:
            settle_agent()
            continue
        produced = 0
        for _ in range(40):
            time.sleep(1.5)
            code, out = api("GET", f"{A}/agents/{AGENT}/output")
            rows = [e for e in out if e.get("run_id") == RUN] if isinstance(out, list) else []
            produced = len(rows)
            if produced >= 1:
                break
        code, st = api("POST", f"{A}/agent/{AGENT}/stop")
        if code == 200:
            STOPPED = True
            break
        settle_agent()
    check("a run was started and stopped mid-turn", STOPPED, f"run {RUN}")
    # Wait for the run to actually settle, so the screen is not merely mid-flight.
    for _ in range(20):
        time.sleep(2)
        code, agents = api("GET", f"{A}/agents")
        row = (
            next((a for a in agents if a["name"] == AGENT), None)
            if isinstance(agents, list)
            else None
        )
        if row and row.get("status") != "running":
            break
    code, tl = api("GET", f"{A}/agents/{AGENT}/timeline")
    rows = tl if isinstance(tl, list) else []
    kinds = [e["event_type"] for e in rows if (e.get("data") or {}).get("run_id") == RUN]
    check(
        "the Hub recorded that this run was stopped rather than completed",
        "run_stopped" in kinds,
        str(kinds),
    )

    # The MECHANISM behind the screen assertion below, computed from the same payload the shipped
    # bundle reads. `runStatusByRunId` (agentTimelineModel.ts:187-199) assigns `result[runId]` for
    # every lifecycle event in iteration order, so the LAST one it sees wins — and this route sorts
    # `reverse=True` (agents.py, `events.sort(key=..., reverse=True)`). The last one it sees is
    # therefore the OLDEST, which is `run_started`, and `TERMINAL_LABEL['started']` is undefined.
    LIFECYCLE = {
        "run_started": "started",
        "run_completed": "completed",
        "run_failed": "failed",
        "run_stopped": "stopped",
        "run_interrupted": "interrupted",
    }
    check(
        "the timeline route answers newest-first",
        [e["timestamp"] for e in rows] == sorted((e["timestamp"] for e in rows), reverse=True),
        str([e["timestamp"] for e in rows[:3]]),
    )
    status_by_run = {}
    for e in rows:
        st = LIFECYCLE.get(e["event_type"])
        rid = (e.get("data") or {}).get("run_id")
        if st and isinstance(rid, str):
            status_by_run[rid] = st
    check(
        "THE STATUS MAP THE TIMELINE COMPONENT BUILDS AGREES WITH THE RUN'S REAL STATUS — "
        "every run resolving to 'started' means no terminal turn label can ever render",
        status_by_run.get(RUN) == "stopped",
        json.dumps(status_by_run),
    )
else:
    code, convs = api("GET", f"{A}/conversations")
    rows = convs.get("conversations", []) if isinstance(convs, dict) else []
    CONV = next((c["id"] for c in rows if c.get("agent") == AGENT), None)

CONV_URL = f"{HUB}/?project={PROJECT}&agent={AGENT}" + (f"&conversation={CONV}" if CONV else "")
WORKSPACE_URL = f"{HUB}/?project={PROJECT}&agent={AGENT}&settings=workspace"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 950})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    page.add_init_script(SEED)

    # ------------------------------------------------------ 1. the conversation after a stop
    page.goto(CONV_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.screenshot(path=str(OUT / "row5-01-after-stop.png"), full_page=False)
    text = page.inner_text("body")
    check("the conversation the stopped run belongs to is reachable", AGENT in text, page.title())
    check(
        "THE SURFACE THE OPERATOR WAS WATCHING SAYS THE RUN WAS STOPPED — a reload is the "
        "ordinary case, and it is the only case where the live SSE status line is gone",
        "stopped" in text.lower(),
        " / ".join(line for line in text.splitlines() if "run" in line.lower())[:300],
    )
    check(
        "and the partial output the stopped run did produce is still there to read",
        "printing press" in text.lower(),
        text[-300:].replace("\n", " / "),
    )

    # ------------------------------------------------------ 2. the composer offers Stop again
    check(
        "the agent is no longer shown as running",
        "running" not in text.lower().split("stopped")[0][-60:],
        text[:160].replace("\n", " / "),
    )

    # ------------------------------------------------------ 3. a message the Hub gave up on
    #
    # F188's operator half. The API leaves a `withdrawn` entry carrying `abandoned_reason`; the
    # question here is whether the operator is ever shown that their message was dropped.
    code, q = api("GET", f"{A}/queue/{AGENT}")
    abandoned = (
        [e for e in q if e.get("state") == "withdrawn" and e.get("abandoned_reason")]
        if isinstance(q, list)
        else []
    )
    if abandoned:
        # Its OWN conversation, not the one the stop happened in: an entry belongs to the
        # conversation it was addressed to, and looking anywhere else measures the harness.
        dropped_conv = abandoned[0].get("conversation_id")
        page.goto(
            f"{HUB}/?project={PROJECT}&agent={AGENT}"
            + (f"&conversation={dropped_conv}" if dropped_conv else ""),
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(4500)
        text = page.inner_text("body")
        page.screenshot(path=str(OUT / "row5-02-abandoned-message.png"), full_page=False)
        needle = abandoned[0]["content"][:24]
        check(
            "A MESSAGE THE HUB STOPPED TRYING TO DELIVER IS VISIBLE TO THE OPERATOR SOMEWHERE "
            "ON THE AGENT'S SURFACE",
            needle.lower() in text.lower() or "stopped retrying" in text.lower(),
            f"looking for {needle!r}",
        )
    else:
        check(
            "the project holds an abandoned entry to look for on screen",
            False,
            "none — run the API harness against this project first",
        )

    # ------------------------------------------------------ 4. the Workspace section's paths
    page.goto(WORKSPACE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4500)
    page.screenshot(path=str(OUT / "row5-03-workspace-sessions.png"), full_page=True)
    text = page.inner_text("body")
    check(
        "the agent's Workspace section is reachable by deep link", "Workspace" in text, page.title()
    )

    code, sess = api("GET", f"{A}/agent/sessions/{AGENT}")
    rows = sess.get("sessions", []) if code == 200 else []
    check("the API has a provider session for this agent", bool(rows), f"[{code}]")
    if rows:
        claimed = rows[0].get("path") or ""
        code, projrow = api("GET", f"{A}")
        root = pathlib.Path(projrow["working_directory"])
        check(
            "the session path is rendered on the page rather than only returned",
            claimed in text,
            claimed,
        )
        check(
            "THE PATH THE SCREEN SHOWS EXISTS — this section presents it as where the agent's "
            "work actually happened",
            bool(claimed) and (root / claimed).exists(),
            f"{claimed!r} under {root}: {(root / claimed).exists() if claimed else 'n/a'}",
        )
        wt = root / ".agentweave" / "worktrees" / AGENT
        check(
            "and a real answer was available to show instead",
            wt.exists(),
            f"{wt} exists: {wt.exists()}",
        )

    # ------------------------------------------------------ 5. console
    #
    # Nothing here provokes a 4xx deliberately, so an unfiltered assertion is honest.
    check(
        "the screens visited raised no console errors",
        not console_errors,
        " | ".join(console_errors[:3]),
    )

    browser.close()

print()
print(f"screenshots: {OUT}")
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} PASS")
for label, ok, det in results:
    if not ok:
        print(f"  FAIL  {label}" + (f" — {det[:200]}" if det else ""))
print("=" * 78)
sys.exit(0 if passed == len(results) else 1)
