"""Sweep row 5 — Runs.

The representative path from the e2e-loop coverage matrix (`SURVEY.md:26`): trigger, stop,
sessions, reconciliation, divergence, task binding. Routes are
`hub/hub/api/v1/agent_trigger.py` — `POST /agent/trigger` (:1212), `POST /agent/{agent}/stop`
(:1480) and `GET /agent/sessions/{agent}` (:2749) — over the modules `run_task_binding.py`,
`run_liveness.py` and `run_divergence.py`.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_sweep_row5_runs.py <pid> [other]

Two things here are measured against the operating system rather than against the Hub's own
record, because row 4 paid for the lesson that a self-report is evidence about the reporter:

  * STOP is judged by whether the spawned process tree is *gone* (a live process snapshot), not by
    whether the run row says `stopped`. What a run says about being stopped is not whether the
    process died.
  * the session path the API hands the screen is checked against the filesystem, because the
    screen presents it as "where the agent's work actually happened".

Set `AW_SKIP_TURN=1` for the API-shape half alone; the stop and session measurements need a real
Haiku turn and are skipped with it.
"""

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AW_PROJECT", "")
if not PID:
    sys.exit("usage: t_sweep_row5_runs.py <project-id> [other-project-id]")
OTHER = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AW_OTHER_PROJECT", "")

TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))

A = f"/projects/{PID}"
B = f"/projects/{OTHER}" if OTHER else None
AGENT = f"r5runner{TAG}"
ARCHIVED = f"r5arch{TAG}"

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {shown}" if shown else ""))


def detail_of(body):
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, list):
            return " | ".join(str(e.get("msg", e)) for e in d)
        if isinstance(d, dict):
            return str(d.get("message", d))
        if d is not None:
            return str(d)
    return str(body)


def names_what_would_work(text, *needles):
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


def db_run(run_id):
    """Read a run row directly. Read-only: the Hub owns this file and this only observes it."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(
            "SELECT id, status, pid, exit_code, error, ended_at FROM runs WHERE id = ?", (run_id,)
        )
        row = cur.fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return dict(zip(("id", "status", "pid", "exit_code", "error", "ended_at"), row, strict=True))


def process_table():
    """{pid: (ppid, name)} for every process on the machine."""
    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name "
            "| ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
    ).stdout
    try:
        rows = json.loads(out)
    except ValueError:
        return {}
    return {int(r["ProcessId"]): (int(r["ParentProcessId"] or 0), r["Name"]) for r in rows}


def descendants(pid, table):
    """*pid* plus everything under it, from a single process snapshot."""
    kids = {}
    for p, (parent, _name) in table.items():
        kids.setdefault(parent, []).append(p)
    seen, stack = [], [pid]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.append(cur)
        stack.extend(kids.get(cur, []))
    return [p for p in seen if p in table]


print("=" * 78)
print(f"ROW 5 — RUNS.  project: {PID}  other: {OTHER or '(none)'}  tag: {TAG}")
print("=" * 78)


def settle_agent():
    """Leave the agent idle with nothing pending before the stop is driven.

    A previous run of this harness can leave the agent blocked inside `ask_user`, and then this
    section's trigger queues behind it: the stop lands on the OLD run and every assertion below
    measures the harness rather than the product. Measured on run 2, 2026-09-01.
    """
    for _ in range(30):
        code, qs = api("GET", f"{A}/questions?status=pending")
        rows = (
            qs
            if isinstance(qs, list)
            else (qs.get("questions", []) if isinstance(qs, dict) else [])
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
        if row and row.get("status") != "running" and not (qstat or {}).get("running"):
            code, entries = api("GET", f"{A}/queue/{AGENT}")
            for e in entries if isinstance(entries, list) else []:
                if e["state"] == "queued":
                    api("DELETE", f"{A}/queue/entries/{e['id']}")
            return True
        time.sleep(3)
    return False


# ------------------------------------------------------------------ 1. request-shape refusals

code, bad = api("POST", f"{A}/agent/trigger", {"agent": "not a name!", "message": "hi"})
check("an agent name the validator rejects is refused at the request", code == 400, f"got {code}")
check(
    "that refusal says what a name may contain",
    names_what_would_work(detail_of(bad), "letters", "alphanumeric", "a-z", "hyphen", "underscore"),
    detail_of(bad),
)

code, bad = api(
    "POST", f"{A}/agent/trigger", {"agent": AGENT, "message": "hi", "session_mode": "sideways"}
)
check("an unknown session_mode is refused", code == 400, f"got {code}")
check(
    "that refusal enumerates the two modes that would work",
    "new" in detail_of(bad) and "resume" in detail_of(bad),
    detail_of(bad),
)

code, bad = api(
    "POST", f"{A}/agent/trigger", {"agent": AGENT, "message": "hi", "session_mode": "resume"}
)
check("resume with no session_id is refused", code == 400, f"got {code}")
check(
    "that refusal names the field that would satisfy it",
    "session_id" in detail_of(bad),
    detail_of(bad),
)

# ------------------------------------------------------------------ 2. environment refusals

code, arch = api("POST", f"{A}/agent/trigger", {"agent": ARCHIVED, "message": "hi"})
check("an archived agent cannot be triggered", code == 409, f"got {code}")
check(
    "the archived refusal names the repair",
    names_what_would_work(detail_of(arch), "unarchive"),
    detail_of(arch),
)

# An agent that does not exist at all. The interesting question is whether the Hub distinguishes
# "no such agent" from "an agent that cannot run" — the two need different operator actions.
ghost = f"r5ghost{TAG}"
code, gh = api("POST", f"{A}/agent/trigger", {"agent": ghost, "message": "hi"})
check(
    "triggering an agent that does not exist is refused rather than accepted",
    code != 200,
    f"got {code}: {detail_of(gh)}",
)
check(
    "and that refusal says the agent does not exist, rather than describing a runner",
    code != 200
    and names_what_would_work(
        detail_of(gh), "does not exist", "no such", "not found", "is not an agent"
    ),
    detail_of(gh),
)

# ------------------------------------------------------------------ 3. the project boundary

if B:
    code, olist = api("GET", f"{B}/conversations")
    rows = olist.get("conversations", []) if isinstance(olist, dict) else []
    foreign = rows[0].get("id") if rows else None
    if foreign:
        code, x = api(
            "POST",
            f"{A}/agent/trigger",
            {"agent": AGENT, "message": "hi", "conversation_id": foreign},
        )
        check(
            "a conversation id owned by another project is refused",
            code == 409,
            f"got {code}: {detail_of(x)}",
        )
        check(
            "and that refusal says what WOULD work — omit it, or name one of this agent's",
            names_what_would_work(
                detail_of(x), "omit", "without", "new conversation", "belongs to", "this agent"
            ),
            detail_of(x),
        )
    else:
        check("the other project has a conversation to borrow an id from", False, "none found")

code, x = api(
    "POST",
    f"{A}/agent/trigger",
    {"agent": AGENT, "message": "hi", "conversation_id": "conv-000000000000"},
)
check("a conversation id that does not exist is refused", code == 409, f"got {code}")
check(
    "that refusal distinguishes 'unavailable' from 'not yours', or says how to get a good one",
    names_what_would_work(detail_of(x), "omit", "does not exist", "unknown", "closed", "start"),
    detail_of(x),
)

# ------------------------------------------------------------------ 4. task binding at trigger

code, t = api(
    "POST", f"{A}/agent/trigger", {"agent": AGENT, "message": "hi", "task_id": "task-000000000000"}
)
check("a task id the project does not have is refused", code in (400, 404, 409), f"got {code}")
check(
    "that refusal names the id it could not find",
    "task-000000000000" in detail_of(t),
    detail_of(t),
)

code, task = api("POST", f"{A}/tasks", {"title": f"row5 decided {TAG}", "description": "x"})
TASK = task.get("id") if code in (200, 201) else None
check("a task can be created to test the decided-task refusal", TASK is not None, f"got {code}")
if TASK:
    code, _ = api("PATCH", f"{A}/tasks/{TASK}", {"status": "approved"})
    code, cur = api("GET", f"{A}/tasks/{TASK}")
    if cur.get("status") != "approved":
        # The lifecycle machine refuses a jump; walk the declared edges instead.
        for step in ("assigned", "in_progress", "completed", "under_review", "approved"):
            api("PATCH", f"{A}/tasks/{TASK}", {"status": step})
        code, cur = api("GET", f"{A}/tasks/{TASK}")
    check(
        "the task reached a decided status so the refusal can be provoked",
        cur.get("status") == "approved",
        str(cur.get("status")),
    )
    code, d = api("POST", f"{A}/agent/trigger", {"agent": AGENT, "message": "hi", "task_id": TASK})
    check(
        "a run cannot be started to work on a task the operator has already approved",
        code == 409,
        f"got {code}: {detail_of(d)}",
    )
    check(
        "and that refusal names both repairs — reopen it, or run without a task",
        names_what_would_work(detail_of(d), "revision_needed")
        and names_what_would_work(detail_of(d), "without naming a task"),
        detail_of(d),
    )

# ------------------------------------------------------------------ 5. stop, with nothing running
#
# Settled first: a run left over from a previous invocation makes this section measure the
# harness. Run 2 answered `200` here because the agent really was running.

settle_agent()
code, s = api("POST", f"{A}/agent/{AGENT}/stop")
check("stopping an agent with no run in progress is refused", code == 404, f"got {code}")
check("that refusal names the agent", AGENT in detail_of(s), detail_of(s))
code, s2 = api("POST", f"{A}/agent/{ghost}/stop")
check(
    "stopping an agent that does not exist says so, rather than reporting it merely idle",
    code == 404
    and names_what_would_work(
        detail_of(s2), "does not exist", "no such", "not found", "is not an agent"
    ),
    f"got {code}: {detail_of(s2)}",
)

# ------------------------------------------------------------------ 6. a worktree that cannot be cut
#
# Deterministic rather than incidental: a plain directory where the agent's worktree belongs is not
# a registered worktree, so `ensure_worktree` refuses (`worktrees.py:313-317`). This is the one
# spawn-time refusal reachable without breaking git, and the question it asks is not whether the
# Hub notices — it does — but what it then does with the operator's message.
#
# The rule this measures is `turn_scheduler.py:204-231`. A refusal that stops the *agent* running
# at all is `agent_wide`, and an agent-wide refusal must NOT count a delivery attempt: nothing is
# starving behind the entry, so dropping it "costs the operator the input the product promised to
# hold until they performed the repair (F96)". A blocked `.agentweave/worktrees/<agent>` with no
# task in play is exactly that condition — the comment's own carve-out is for a *task's* checkout,
# which this is not.

code, projrow = api("GET", f"{A}")
ROOT = (
    pathlib.Path(projrow["working_directory"])
    if code == 200 and projrow.get("working_directory")
    else None
)
check("the project reports the directory it was opened on", ROOT is not None, str(code))
if ROOT:
    blocked = ROOT / ".agentweave" / "worktrees" / AGENT
    # A SECOND run of this harness meets a *registered* worktree here, left by the first, and
    # planting a file inside one changes nothing — `ensure_worktree` accepts it and the turn runs.
    # Measured: run 2 reported the product broken by starting normally. Release it first, so the
    # condition under test is the same on every run.
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(blocked)], cwd=ROOT, capture_output=True
    )
    shutil.rmtree(blocked, ignore_errors=True)
    # `prune` is what actually deregisters it. Without this the path stays in `git worktree list`
    # pointing at a directory that no longer holds a checkout, `ensure_worktree` reads back the
    # branch it expects, and the turn runs — which is how run 2 reported the product working when
    # the condition under test had not been created (measured 2026-09-01).
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    check(
        "the agent's worktree could be released, so the block below is the condition under test",
        AGENT not in listing,
        listing.strip()[:200],
    )
    blocked.mkdir(parents=True, exist_ok=True)
    (blocked / "not-a-worktree.txt").write_text("occupied", encoding="utf-8")

    code, w = api("POST", f"{A}/agent/trigger", {"agent": AGENT, "message": f"blocked-{TAG}-0"})
    reason = str(w.get("waiting_reason") or detail_of(w))
    HEAD = w.get("queue_entry_id") if code == 200 else None
    check(
        "the operator is told why a turn whose worktree cannot be cut is not running",
        "worktree" in reason.lower(),
        f"[{code}] {reason}",
    )
    check(
        "and that sentence names the exact path and branch that are in the way",
        str(blocked) in reason and "refs/heads/" in reason,
        reason,
    )
    check(
        "and it says what would clear it, not only what failed",
        names_what_would_work(reason, "remove", "delete", "prune", "clear", "release"),
        reason,
    )

    # Three more schedules. Each `POST /agent/trigger` runs one, which is also what the
    # conversation view's Continue button does — F114's own measurement, at a different site.
    for i in range(1, 4):
        api("POST", f"{A}/agent/trigger", {"agent": AGENT, "message": f"blocked-{TAG}-{i}"})
        time.sleep(1.5)
    code, q = api("GET", f"{A}/queue/{AGENT}")
    entries = q if isinstance(q, list) else []
    head = next((e for e in entries if e["id"] == HEAD), None)
    check(
        "A REPAIRABLE, AGENT-WIDE WORKSPACE FAULT DOES NOT DESTROY THE OPERATOR'S MESSAGE — "
        "nothing else for this agent could run either way, so dropping it buys nobody a turn",
        head is not None and head["state"] != "withdrawn",
        json.dumps(
            {
                "state": head["state"],
                "attempts": head["delivery_attempts"],
                "abandoned_reason": (head.get("abandoned_reason") or "")[:160],
            }
            if head
            else {"head": "missing"}
        ),
    )

    # The contrast that makes the line above a defect rather than a policy: the *other* agent-wide
    # refusal, an unbound runner, is flagged `agent_wide=True` and holds its input at zero attempts
    # through the same number of schedules.
    UNBOUND = f"r5norun{TAG}"
    code, made = api(
        "POST",
        f"{A}/agents",
        {"name": UNBOUND, "provider": "claude", "model": "claude-haiku-4-5-20251001"},
    )
    api("PATCH", f"{A}/agents/{UNBOUND}", {"runner_id": None})
    for i in range(4):
        api("POST", f"{A}/agent/trigger", {"agent": UNBOUND, "message": f"unbound-{TAG}-{i}"})
        time.sleep(1.5)
    code, q2 = api("GET", f"{A}/queue/{UNBOUND}")
    ue = q2 if isinstance(q2, list) else []
    check(
        "CONTRAST — the unbound-runner refusal, which is the same kind of fault, holds every "
        "message at zero attempts",
        bool(ue) and all(e["state"] == "queued" and e["delivery_attempts"] == 0 for e in ue),
        json.dumps([(e["state"], e["delivery_attempts"]) for e in ue]),
    )

    shutil.rmtree(blocked, ignore_errors=True)
    # Clear what this section queued, so the real-turn half below starts from an empty queue.
    code, q = api("GET", f"{A}/queue/{AGENT}")
    for e in q if isinstance(q, list) else []:
        if e["state"] == "queued":
            api("DELETE", f"{A}/queue/entries/{e['id']}")

# ------------------------------------------------------------------ 7. real turns: stop, sessions


if os.environ.get("AW_SKIP_TURN"):
    print("\n(real turns skipped: AW_SKIP_TURN set)")
else:
    check("the agent could be settled to idle before the stop is driven", settle_agent(), "")
    long_prompt = (
        "Write a detailed 1500-word essay about the history of the printing press. "
        "Write it directly in your reply, in full prose, without using any tools."
    )
    code, trig = api("POST", f"{A}/agent/trigger", {"agent": AGENT, "message": long_prompt})
    show("POST /agent/trigger (long turn)", code, trig, limit=300)
    check("the long turn is accepted", code == 200, f"got {code}")
    RUN = trig.get("run_id") if code == 200 else None
    check("the accepted long turn started a run rather than queueing", bool(RUN), str(trig)[:200])

    # Wait for the Hub to record a pid — the run row is the only place it exists.
    row, spawn_pid = None, None
    for _ in range(40):
        row = db_run(RUN) if RUN else None
        if row and row.get("pid"):
            spawn_pid = row["pid"]
            break
        time.sleep(2)
    check("the Hub records the pid of the process it spawned", bool(spawn_pid), str(row))

    tree = []
    if spawn_pid:
        table = process_table()
        tree = descendants(spawn_pid, table)
        check(
            "that pid is a live process on this machine",
            spawn_pid in table,
            f"pid {spawn_pid}; tree {[(p, table[p][1]) for p in tree]}",
        )

    # Triggering the same agent while it is mid-turn: the invariant is one run per agent, so this
    # must be accepted and queued rather than started or refused.
    code, busy = api("POST", f"{A}/agent/trigger", {"agent": AGENT, "message": f"second {TAG}"})
    check("a second input while the agent is running is accepted", code == 200, f"got {code}")
    check(
        "it is queued rather than started — one run per agent",
        code == 200 and busy.get("status") == "queued",
        str(busy.get("status")),
    )
    check(
        "and the operator is told WHY it is waiting",
        code == 200 and bool(busy.get("waiting_reason")),
        str(busy.get("waiting_reason")),
    )

    # ---- the stop itself
    code, st = api("POST", f"{A}/agent/{AGENT}/stop")
    show("POST /agent/{agent}/stop", code, st, limit=300)
    check("the stop is accepted while the run is in progress", code == 200, f"got {code}")
    check(
        "the stop response names the run it signalled",
        code == 200 and st.get("run_id") == RUN,
        f"{st.get('run_id')} vs {RUN}",
    )

    # THE measurement. Not the record — the operating system.
    gone, survivors = False, []
    for _ in range(20):
        time.sleep(1.5)
        table = process_table()
        survivors = [p for p in tree if p in table]
        if not survivors:
            gone = True
            break
    check(
        "STOP KILLS THE PROCESS TREE, measured against the OS rather than the run record",
        gone,
        f"still alive: {survivors}",
    )

    final = None
    for _ in range(30):
        final = db_run(RUN)
        if final and final["status"] != "running":
            break
        time.sleep(2)
    check(
        "the run's recorded status settles on 'stopped', not 'failed'",
        bool(final) and final["status"] == "stopped",
        str(final),
    )

    # ---- what the stop left behind
    code, q = api("GET", f"{A}/queue/{AGENT}")
    entries = q if isinstance(q, list) else []
    delivered = [e for e in entries if e.get("state") == "delivered"]
    # A stop keeps its input `delivered` on purpose — the process DID receive it, and
    # `return_run_entries` fires only for `failed` (agent_trigger.py:2081-2085). What matters is
    # that every such entry is still attributable to the run that consumed it, so the operator can
    # see where their message went rather than finding it simply absent.
    check(
        "every entry the stopped run consumed still names the run that consumed it",
        all(e.get("delivered_in_run_id") for e in delivered),
        json.dumps([(e["state"], e.get("delivered_in_run_id")) for e in delivered]),
    )

    # The SECOND input was never delivered. A stop must not strand it.
    time.sleep(5)
    code, qstatus = api("GET", f"{A}/queue/{AGENT}/status")
    check(
        "input queued behind a stopped run is picked up rather than stranded",
        code == 200 and (qstatus.get("running") or qstatus.get("waiting_count", 0) == 0),
        json.dumps(qstatus) if code == 200 else str(code),
    )

    # ---- does the agent's own surface say WHY the run ended?
    code, out = api("GET", f"{A}/agents/{AGENT}/output")
    rows = [e for e in out if e.get("run_id") == RUN] if isinstance(out, list) else []
    text = " ".join(str(e.get("content")) for e in rows)
    check(
        "the agent's output stream says the run was stopped",
        names_what_would_work(text, "stopped"),
        text[-300:],
    )
    code, tl = api("GET", f"{A}/agents/{AGENT}/timeline")
    rows = tl if isinstance(tl, list) else []
    kinds = [e["event_type"] for e in rows if (e.get("data") or {}).get("run_id") == RUN]
    check(
        "the agent's timeline carries a run_stopped event for this run",
        "run_stopped" in kinds,
        str(kinds),
    )
    check(
        "the terminal status line is on the OUTPUT stream too, not only broadcast live — a "
        "reload is the ordinary way an operator returns to a run they stopped",
        (
            any(e.get("kind") == "status" for e in out if e.get("run_id") == RUN)
            if isinstance(out, list)
            else False
        ),
        str([e.get("kind") for e in out if isinstance(out, list) and e.get("run_id") == RUN]),
    )

    # ---- sessions
    code, sess = api("GET", f"{A}/agent/sessions/{AGENT}")
    rows = sess.get("sessions", []) if code == 200 else []
    check("the agent has at least one provider session recorded", bool(rows), f"got {code}")
    if rows:
        p = rows[0].get("path")
        check(
            "THE SESSION PATH THE SCREEN SHOWS IS A REAL PATH — the screen presents it as "
            "where the agent's work happened",
            bool(ROOT) and bool(p) and (ROOT / p).exists(),
            f"{p!r} under {ROOT}",
        )
        check(
            "the session row points at the workspace the turn actually ran in",
            bool(p) and AGENT in str(p) and "worktrees" in str(p),
            str(p),
        )

# ------------------------------------------------------------------ summary
print()
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} PASS")
for label, ok, det in results:
    if not ok:
        print(f"  FAIL  {label}" + (f" — {det[:200]}" if det else ""))
print("=" * 78)
sys.exit(0 if passed == len(results) else 1)
