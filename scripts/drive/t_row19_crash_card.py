"""Row 19 x row 14: the Hub killed while an operator's permission card is open.

The crash drive (`t_row19_crash.py`) ran both its specimens in default posture, so
`reconcile_interrupted_runs`' call to `expire_pending_for_run` was never exercised. Its comment
says why it is there:

    "a Hub bounced while an operator decision was on screen leaves a row nobody will ever poll
     again, and without this the card outlives not just its run but the Hub process that served it"

So this asks what an operator sees. A card is on screen. The Hub dies. What is the card when the
Hub comes back, what happens if the operator answers it anyway, and does the work get another
chance at asking?

Usage:  AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=... AW_AGENT=... py -3.11 t_row19_crash_card.py
"""

import os
import subprocess
import sqlite3
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-1964cdedffe2"
AGENT = os.environ.get("AW_AGENT") or "peer"
PORT = os.environ.get("AW_PORT") or "8011"
DB = os.environ.get(
    "AW_DB", "sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0830/aw0830.db"
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("AW_HUBLOG", "C:/Users/huida/AppData/Local/Temp/aw0830/hub_crash.log")
TICKET_SECRET = os.environ.get("AW_TICKET_SECRET", "aw0830-ticket-secret")
#: Unique per run. A drive prompt that names a fixed filename contaminates its own next run --
#: the second run's "did the file appear?" check passes on the first run's leftover.
NOTE = os.environ.get("AW_NOTE") or f"card_crash_note_{int(time.time())}.txt"
#: Where the agent's write lands. Per-agent worktree, not the project root -- proving the write
#: happened means looking where the agent actually works.
WORKSPACE = os.environ.get(
    "AW_WORKSPACE",
    "C:/Users/huida/Documents/drive-0830-sweep/.agentweave/worktrees/"
    + (os.environ.get("AW_AGENT") or "peer"),
)


def step(label):
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def ps(script):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True
    )
    return (r.stdout or "").strip()


def hub_pids():
    raw = ps(
        "Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='py.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*uvicorn*--port {PORT}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    return [int(x) for x in raw.split() if x.isdigit()]


def start_hub():
    subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", PORT, "--host", "127.0.0.1"],
        cwd=os.path.join(REPO, "hub"),
        env={
            **os.environ,
            "DATABASE_URL": DB,
            "AW_BOOTSTRAP_API_KEY": os.environ.get("AW_KEY", ""),
            "AW_TICKET_SECRET": TICKET_SECRET,
        },
        stdout=open(LOG, "ab"),
        stderr=subprocess.STDOUT,
    )
    end = time.time() + 45
    while time.time() < end:
        code, _ = api("GET", "/projects", timeout=3)
        if code == 200:
            return True
        time.sleep(1)
    return False


def sql(query, args=()):
    conn = sqlite3.connect(DB.split("///", 1)[1])
    try:
        cur = conn.execute(query, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def cards():
    code, body = api("GET", f"/projects/{P}/permission-requests")
    rows = body.get("permission_requests") if isinstance(body, dict) else body
    return code, (rows or [])


def open_cards():
    """Cards the operator can still answer.

    Keyed on `status == "pending"`, NOT on `decided_at`: an EXPIRED card carries
    `decided_at = None` and `decided_by = None` -- nobody decided it -- so a decided_at filter
    reads an expired card as open. The first run of this harness did exactly that. The list route
    hides expired rows by default (`pending_only`), so the mistake was invisible there and would
    have surfaced as a wrong verdict elsewhere.
    """
    _, rows = cards()
    return [r for r in rows if r.get("status") == "pending" and not r.get("dismissed")]


def agent_row():
    _, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else body.get("agents", [])
    return next((a for a in rows if a.get("name") == AGENT), None)


def wait_for(label, predicate, timeout=90, interval=2):
    end = time.time() + timeout
    while time.time() < end:
        v = predicate()
        if v:
            print(f"  [{time.strftime('%H:%M:%S')}] {label}: yes")
            return v
        time.sleep(interval)
    print(f"  [{time.strftime('%H:%M:%S')}] {label}: TIMED OUT after {timeout}s")
    return None


def preconditions():
    """Refuse to start unless the fixture is in the state this drive assumes.

    Copied from `t_row19_crash_job.py`. Three of the four crash harnesses read a green-looking
    verdict off a fixture that was already dirty before this block existed.
    """
    step("0. Preconditions")
    if not P or not AGENT or not DB:
        raise SystemExit("set AW_PROJECT, AW_AGENT and AW_DB")
    if not os.path.exists(DB.split("///", 1)[1]):
        raise SystemExit(f"no database at {DB}")
    pre = agent_row()
    if pre is None or pre.get("archived") or not pre.get("runner_id"):
        raise SystemExit(f"agent {AGENT!r} must exist, be open, and be bound to a runner")
    if pre.get("status") != "idle":
        raise SystemExit(f"agent {AGENT!r} is {pre.get('status')!r}, not idle")
    if open_cards():
        raise SystemExit(f"a permission card is already open: {[c['id'] for c in open_cards()]}")
    _, jobs = api("GET", f"/projects/{P}/jobs")
    jobs = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs", [])
    if any(j.get("enabled") for j in jobs):
        raise SystemExit(f"a job is already enabled on {P}")
    if not hub_pids():
        raise SystemExit(f"no uvicorn is serving --port {PORT}; there is nothing to crash")
    if not os.path.isdir(WORKSPACE):
        raise SystemExit(f"no worktree at {WORKSPACE}; the write check would be unfalsifiable")
    if os.path.exists(os.path.join(WORKSPACE, NOTE)):
        raise SystemExit(f"{NOTE} already exists in the worktree; pick another AW_NOTE")
    print(f"  [OK ] {AGENT} idle and bound; no card, no job; a Hub is serving {PORT}")
    print(f"  [OK ] worktree {WORKSPACE} exists and does not already hold {NOTE}")


def cleanup():
    """Leave the fixture as it was found: no open card, no run in flight, nothing queued."""
    print("\n--- cleanup ---")
    for c in open_cards():
        code, _ = api("POST", f"/projects/{P}/permission-requests/{c['id']}/decide",
                      {"allow": False})
        print(f"  denied leftover card {c['id']} -> {code}")
    settled = wait_for("agent back to idle", lambda: (lambda a: a and a.get("status") == "idle")(agent_row()),
                       timeout=180, interval=5)
    if not settled:
        print("  WARNING: agent is not idle; the fixture is NOT clean")
    q = sql("SELECT id,state FROM inbound_queue_entries WHERE agent = ? AND state = 'queued'",
            (AGENT,))
    if q:
        print(f"  WARNING: {len(q)} entries still queued for {AGENT}: {q}")
    print("  cards now:", [(c["id"], c.get("status")) for c in cards()[1]][:6])


def main():
    verdicts = []
    preconditions()

    step("1. A run in manual posture, so a card goes on screen")
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                f"Write the single line 'survived the crash' to a new file named {NOTE} in the "
                "project root, using the Write tool. Then stop."
            ),
            # Posture travels in `overrides` -- a top-level permission_mode is now a 422 (F116).
            "overrides": {"permission_mode": "manual"},
        },
    )
    show("POST /agent/trigger (manual)", code, body, limit=600)
    if code >= 300:
        return
    run_id = body.get("run_id")

    card = wait_for("a permission card is open", lambda: (open_cards() or [None])[0], timeout=120)
    if not card:
        print("FAIL -- no card, nothing to crash on")
        return
    print(f"  card {card.get('id')} tool={card.get('tool_name')} run={card.get('run_id')}")
    print("  db row:", sql("SELECT id,status,decided_by,decided_at,run_id FROM permission_requests "
                           "WHERE id = ?", (card["id"],)))

    step("2. Kill the Hub with the card on screen")
    pids = hub_pids()
    print(f"  killing {pids}")
    ps("Stop-Process -Id " + ",".join(str(p) for p in pids) + " -Force")
    time.sleep(3)
    code, _ = api("GET", "/projects", timeout=3)
    print(f"  GET /projects with the Hub dead: {code}")
    verdicts.append(("hub is really dead", code == 0))

    step("3. Restart, and read the card back")
    up = start_hub()
    print(f"  hub answering again: {up}")
    if not up:
        return
    print("  db row after restart:", sql("SELECT id,status,decided_by,decided_at,run_id "
                                         "FROM permission_requests WHERE id = ?", (card["id"],)))
    print("  the run:", sql("SELECT id,status,pid,ended_at,exit_code FROM runs WHERE id = ?", (run_id,)))
    still_open = [c for c in open_cards() if c["id"] == card["id"]]
    print(f"  still on the operator's screen: {bool(still_open)}")
    verdicts.append(("the card did not outlive its Hub", not still_open))

    step("4. What if the operator answers it anyway? (the card was on screen when it died)")
    code, body = api(
        "POST",
        f"/projects/{P}/permission-requests/{card['id']}/decide",
        # The field is `allow`, a bool. `{"decision": "allow"}` is a 422 -- which the first run of
        # this harness sent, and then read the refusal as proof that a dead card cannot be
        # answered. It proved only that the harness could not spell the request.
        {"allow": True},
    )
    show("POST decide (allow) on the crashed card", code, body, limit=900)
    verdicts.append(("deciding a dead card is refused, not silently accepted", code == 409))

    step("5. Did the work get another chance to ask?")
    time.sleep(4)
    print("  runs:", sql("SELECT id,agent,status,ended_at FROM runs WHERE agent = ? "
                         "ORDER BY started_at DESC LIMIT 3", (AGENT,)))
    print("  queue:", sql("SELECT id,state,delivery_attempts,abandoned_reason FROM inbound_queue_entries "
                          "WHERE agent = ? ORDER BY sequence DESC LIMIT 3", (AGENT,)))
    new_card = wait_for(
        "a fresh card for the redelivered work",
        lambda: (lambda cs: cs[0] if cs and cs[0]["id"] != card["id"] else None)(open_cards()),
        timeout=150,
    )
    verdicts.append(("the redelivered turn asks again", bool(new_card)))
    if new_card:
        print(f"  new card {new_card['id']} run={new_card.get('run_id')} tool={new_card.get('tool_name')}")
        code, body = api(
            "POST",
            f"/projects/{P}/permission-requests/{new_card['id']}/decide",
            {"allow": True},
        )
        show("POST decide (allow) on the fresh card", code, body, limit=600)
        wrote = wait_for(
            "the file the run asked permission for exists",
            lambda: os.path.exists(os.path.join(WORKSPACE, NOTE)),
            timeout=90,
        )
        verdicts.append(("the allowed write actually landed", bool(wrote)))
        settled = wait_for(
            "the agent went idle again",
            lambda: (lambda a: a if a and a.get("status") == "idle" else None)(agent_row()),
            timeout=150,
        )
        verdicts.append(("the work completed after the crash", bool(settled)))

    step("6. Events the operator would have seen")
    code, body = api("GET", f"/projects/{P}/events/history?limit=40")
    rows = body.get("events") if isinstance(body, dict) else body
    for e in rows or []:
        if e.get("type") not in ("context_warning", "agent_output"):
            print(f"  {e.get('timestamp','')[11:19]} {e.get('type')} {str(e.get('data'))[:150]}")

    step("VERDICTS")
    for label, ok in verdicts:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
