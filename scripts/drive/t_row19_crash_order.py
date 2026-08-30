"""Row 19 x row 5: a crash re-queues an entry while the operator sends a second message.

`return_run_entries` (`hub/hub/inbound_queue.py`) deliberately preserves two fields on an entry
it puts back, and its docstring names the exact failure that made both deliberate:

    every later input, including a request for a fresh conversation, queues behind the one doing
    the killing

`sequence` is kept because ordering is by `sequence` and an operator's first message should not
lose its place. `conversation_id` is kept because an entry belonging to no conversation cannot be
scheduled at all. Both are right in isolation. Together they say something the repo has asserted
in unit tests and **never driven with a real second message**: after a crash, the returned entry
still controls the next turn, and a message the operator sends into the dead window -- which
`/agent/trigger` always puts on a *fresh* conversation -- cannot ride on it, because
`schedule_agent` filters the batch to `entry.conversation_id == conversation.id`.

So the question this file exists to answer is not "is it delayed" -- the code says it is. It is:

    is the second message ever delivered at all, or is it stranded behind the first?

Shape: trigger a long turn on conversation A; kill the Hub mid-turn; poll the port with a raw TCP
connect (NOT an HTTP request -- the address-observing middleware drains the deferred
post-reconciliation schedule from the first request the Hub serves, so an HTTP liveness poll would
hand the race away); then POST the second message as the first HTTP request the restarted Hub
sees. Then read which entry the Hub delivers first, on whose conversation, and whether the second
one ever runs.

Usage:  AW_HUB=... AW_KEY=... AW_PROJECT=... AW_AGENT=driver py -3.11 t_row19_crash_order.py
"""

import os
import socket
import sqlite3
import subprocess
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-1964cdedffe2"
AGENT = os.environ.get("AW_AGENT") or "driver"
PORT = os.environ.get("AW_PORT") or "8011"
DB = os.environ.get(
    "AW_DB", "sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0830/aw0830.db"
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("AW_HUBLOG", "C:/Users/huida/AppData/Local/Temp/aw0830/hub_crash.log")
TICKET_SECRET = os.environ.get("AW_TICKET_SECRET", "aw0830-ticket-secret")
#: Unique per run, so no assertion below can be satisfied by a previous drive's row.
STAMP = str(int(time.time()))


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


def kill_hub():
    pids = hub_pids()
    ps("Stop-Process -Id " + ",".join(str(p) for p in pids) + " -Force")
    time.sleep(3)
    code, _ = api("GET", "/projects", timeout=3)
    print(f"  killed {pids}; GET /projects -> {code}")
    return code == 0


def spawn_hub():
    subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", PORT, "--host", "127.0.0.1"],
        cwd=os.path.join(REPO, "hub"),
        env={
            **os.environ,
            "DATABASE_URL": DB,
            "AW_BOOTSTRAP_API_KEY": os.environ.get("AW_KEY", ""),
            "AW_TICKET_SECRET": TICKET_SECRET,
            # Set while chasing why the crash log stopped at "Waiting for application startup."
            # for every process in the file. Buffering was the obvious suspect and was WRONG --
            # setting this changed nothing, which is what turned the investigation towards the
            # real cause, F151 (migrations disabling every existing logger at startup). Kept
            # anyway: a Hub this harness is about to **force-kill** never gets to flush, so an
            # unbuffered stream is the right thing for a crash drive regardless.
            "PYTHONUNBUFFERED": "1",
        },
        stdout=open(LOG, "ab"),
        stderr=subprocess.STDOUT,
    )


def wait_port_open(timeout=60):
    """Wait for the port to accept a TCP connection, WITHOUT sending an HTTP request.

    This is the whole reason the second message can land in the dead window at all.
    `main.py`'s `_observe_bound_address` middleware fires `drain_deferred_schedules()` on the
    **first request the Hub serves** -- so polling `GET /projects` for liveness would itself be
    the request that redelivers the returned entry, and the "operator types the instant the Hub is
    back" case would be untestable from this harness. A bare `connect()` completes the moment
    uvicorn binds and sends no request at all.
    """
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", int(PORT)), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def wait_http(timeout=45):
    end = time.time() + timeout
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


def entry_row(entry_id):
    if not entry_id:
        return None
    rows = sql(
        "SELECT id,sequence,state,delivery_attempts,conversation_id,delivered_in_run_id,"
        "delivered_at,abandoned_reason,waiting_reason FROM inbound_queue_entries WHERE id = ?",
        (entry_id,),
    )
    return rows[0] if rows else None


def brief(row):
    if not row:
        return None
    return {
        k: row[k]
        for k in (
            "id",
            "sequence",
            "state",
            "delivery_attempts",
            "conversation_id",
            "delivered_in_run_id",
        )
    }


def agent_status():
    _, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else body.get("agents", [])
    return next((a["status"] for a in rows if a["name"] == AGENT), None)


def wait_running(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if agent_status() == "running":
            return True
        time.sleep(2)
    return False


def preconditions():
    """Refuse to start unless the fixture is in the state this drive assumes."""
    step("0a. Preconditions")
    if not P or not AGENT or not DB:
        raise SystemExit("set AW_PROJECT, AW_AGENT and AW_DB")
    if not os.path.exists(DB.split("///", 1)[1]):
        raise SystemExit(f"no database at {DB}")
    _, roster = api("GET", f"/projects/{P}/agents")
    roster = roster if isinstance(roster, list) else (roster or {}).get("agents", [])
    pre = next((a for a in roster if a.get("name") == AGENT), None)
    if pre is None or pre.get("archived") or not pre.get("runner_id"):
        raise SystemExit(f"agent {AGENT!r} must exist, be open, and be bound to a runner")
    if pre.get("status") != "idle":
        raise SystemExit(f"agent {AGENT!r} is {pre.get('status')!r}, not idle")
    _, jobs = api("GET", f"/projects/{P}/jobs")
    jobs = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs", [])
    if any(j.get("enabled") for j in jobs):
        raise SystemExit(f"a job is already enabled on {P}")
    queued = sql(
        "SELECT id,state FROM inbound_queue_entries WHERE agent = ? AND state = 'queued'", (AGENT,)
    )
    if queued:
        raise SystemExit(f"{AGENT} already has queued input: {queued}")
    if not hub_pids():
        raise SystemExit(f"no uvicorn is serving --port {PORT}; there is nothing to crash")
    print(f"  [OK ] {AGENT} idle and bound, nothing queued; no job enabled; a Hub serves {PORT}")


def cleanup():
    """Leave the fixture as found: nothing queued for this agent, agent idle, a Hub on the port."""
    print("\n--- cleanup ---")
    if not hub_pids():
        print("  no Hub on the port; restarting it so the fixture is left usable")
        spawn_hub()
        wait_http()
    end = time.time() + 240
    while time.time() < end:
        if agent_status() == "idle":
            break
        time.sleep(5)
    print("  agent:", agent_status())
    q = sql(
        "SELECT id,state FROM inbound_queue_entries WHERE agent = ? AND state = 'queued'", (AGENT,)
    )
    if q:
        print(f"  WARNING: {len(q)} entries still queued for {AGENT}: {q}")
        for row in q:
            code, _ = api("DELETE", f"/projects/{P}/queue/{AGENT}/{row['id']}")
            print(f"    withdraw {row['id']} -> {code}")
    _, jobs = api("GET", f"/projects/{P}/jobs")
    jobs = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs", [])
    print("  jobs:", [(j.get("id"), j.get("enabled")) for j in jobs])


def main():
    verdicts = []
    preconditions()

    step("1. Message one -- a long turn on conversation A")
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                f"Say the word FIRST-{STAMP}. Then count slowly from 1 to 30, printing each "
                "number on its own line and thinking briefly about each one before the next."
            ),
        },
    )
    show("trigger msg1", code, body, limit=600)
    if code >= 300:
        return
    entry1 = body.get("queue_entry_id")
    conv_a = body.get("conversation_id")
    print("  entry1:", brief(entry_row(entry1)))

    step("2. Crash the Hub with that turn in flight")
    if not wait_running():
        print("  FAIL -- the agent never went running; there is nothing to crash")
        return
    time.sleep(6)
    running = sql(
        "SELECT id,status,conversation_id FROM runs WHERE agent = ? AND status = 'running'",
        (AGENT,),
    )
    print("  running:", running)
    verdicts.append(("the crash landed on a live run", bool(running)))
    kill_hub()

    step("3. Restart, and send message two as the first HTTP request the new Hub sees")
    log_offset = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    t_spawn = time.time()
    spawn_hub()
    if not wait_port_open():
        print("  FAIL -- the port never opened")
        return
    print(f"  port open after {time.time() - t_spawn:.1f}s; POSTing msg2 now")
    code, body2 = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            # Deliberately trivial and deliberately distinguishable: if this ever runs, its own
            # words appear in the agent's output and nothing else in the fixture says them.
            #
            # Phrased WITHOUT "ignore any other instruction", which is what the first version
            # said. Haiku read that as a prompt-injection attempt, refused it, and went off to
            # work on an unrelated task -- and the assertion below passed anyway, because the
            # token appeared in the run's `thinking` rows while the agent explained why it would
            # not comply. A drive that asks an agent to do something must not phrase the ask like
            # an attack on the agent.
            "message": (
                f"This is a connectivity check. Reply with just this token: SECOND-{STAMP}. "
                "Do not read any files, do not use any tools, and do not start any other work."
            ),
        },
        timeout=120,
    )
    show("trigger msg2 (dead-window follow-up)", code, body2, limit=800)
    entry2 = conv_b = None
    if code >= 300:
        print("  msg2 was refused outright -- that is itself the answer; recording and continuing")
        verdicts.append(("the dead-window message was accepted at all", False))
    else:
        entry2 = body2.get("queue_entry_id")
        conv_b = body2.get("conversation_id")
        verdicts.append(("the dead-window message was accepted at all", bool(entry2)))
    print("  entry1:", brief(entry_row(entry1)))
    print("  entry2:", brief(entry_row(entry2)))

    # WHO redelivered the first entry? Startup reconciliation cannot do it by itself: it runs
    # inside `lifespan()`, before the Hub has served a request, so `bound_address` is empty and
    # `_schedule_or_defer` parks the agent instead. `_observe_bound_address` drains that park from
    # the **first request the Hub serves** -- and with the TCP-only liveness poll above, that
    # first request is the operator's own follow-up. So the operator's second message is what
    # restarts the turn that then makes it wait.
    #
    # Asserted on the OBSERVABLE, not on the Hub's log -- and it stays that way even now that the
    # log works. The log was tried first and could not answer: running migrations at startup called
    # `fileConfig` on `alembic.ini` without `disable_existing_loggers=False`, disabling
    # `uvicorn.error` and every `hub.*` module logger for the life of the process, so
    # `drain_deferred_schedules`'s own WARNING was never written and an absent line proved nothing.
    # That is F151, found here and fixed. The drain count below is now real evidence and is printed
    # for the reader, but the VERDICT is kept on the queue state, which does not depend on a log
    # level, a handler, or where stdout was pointed. What is decisive: the entry was already
    # `delivered` into a NEW run by the time this POST's response came back, having been
    # `delivered` into the killed run before it.
    #
    # `log_offset` is captured anyway, so this reads only lines this drive's Hub wrote -- the log
    # is opened "ab" and every crash harness ever run has appended to it.
    drained = []
    try:
        with open(LOG, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(log_offset)
            drained = [ln.strip() for ln in fh if "Draining" in ln]
    except OSError as exc:  # noqa: BLE001
        print("  could not read the hub log:", exc)
    print(f"  drain lines in the hub log: {len(drained)}"
          "   (before F151 was fixed this was always 0 -- the Hub could not speak)")
    r1_now = entry_row(entry1)
    verdicts.append(
        (
            "the follow-up's own request is what un-parked the crashed turn: by the time its "
            "response returned, entry one was already redelivered into a new run",
            bool(r1_now)
            and r1_now["state"] == "delivered"
            and r1_now["delivery_attempts"] == 1
            and r1_now["delivered_in_run_id"] not in (None, running[0]["id"] if running else None),
        )
    )

    step("4. What the two entries carry -- the preserved fields, measured")
    r1, r2 = entry_row(entry1), entry_row(entry2)
    verdicts.append(
        (
            "the returned entry kept its place in arrival order (sequence preserved)",
            bool(r1) and bool(r2) and r1["sequence"] < r2["sequence"],
        )
    )
    verdicts.append(
        (
            "the returned entry kept its original conversation",
            bool(r1) and r1["conversation_id"] == conv_a,
        )
    )
    verdicts.append(
        (
            "the follow-up opened a FRESH conversation, as /agent/trigger always does",
            bool(conv_b) and conv_b != conv_a,
        )
    )
    print(f"  conv A {conv_a}  conv B {conv_b}")

    step("5. Which entry does the resumed Hub deliver first, and on whose conversation?")
    # Poll until *something* is delivered. Whichever entry that is, is the answer.
    first_delivered, deadline = None, time.time() + 120
    while time.time() < deadline:
        a, b = entry_row(entry1), entry_row(entry2)
        if a and a["state"] == "delivered":
            first_delivered = ("entry1", a)
            break
        if b and b["state"] == "delivered":
            first_delivered = ("entry2", b)
            break
        time.sleep(1)
    print(
        "  first delivered:",
        first_delivered[0] if first_delivered else None,
        brief(first_delivered[1]) if first_delivered else None,
    )
    verdicts.append(
        (
            "the crash's own entry is delivered first, not the newer message",
            bool(first_delivered) and first_delivered[0] == "entry1",
        )
    )
    run_rows = sql(
        "SELECT id,status,conversation_id,session_id,initiator FROM runs WHERE agent = ? "
        "ORDER BY started_at DESC LIMIT 4",
        (AGENT,),
    )
    print("  recent runs:", run_rows)
    redelivery = None
    if first_delivered:
        redelivery = next(
            (r for r in run_rows if r["id"] == first_delivered[1]["delivered_in_run_id"]), None
        )
    verdicts.append(
        (
            "...and the redelivered turn runs on conversation A, the one that was killed",
            bool(redelivery) and redelivery["conversation_id"] == conv_a,
        )
    )
    b_now = entry_row(entry2)
    verdicts.append(
        (
            "the follow-up did NOT ride along on that turn -- different conversation, filtered out",
            bool(b_now) and b_now["state"] == "queued",
        )
    )

    step("6. While it waits, is the follow-up visible to the operator?")
    code, qbody = api("GET", f"/projects/{P}/queue/{AGENT}")
    show("GET /queue/{agent}", code, qbody, limit=1500)
    code, sbody = api("GET", f"/projects/{P}/queue/{AGENT}/status")
    show("GET /queue/{agent}/status", code, sbody, limit=1200)
    q_rows = qbody.get("entries") if isinstance(qbody, dict) else qbody
    # `state == "queued"`, not merely present: this route returns the agent's whole queue history
    # including withdrawn entries, so "is it in the list" would pass for a message that had been
    # dropped. The operator's question is whether it is shown as still coming.
    mine = next((e for e in (q_rows or []) if e.get("id") == entry2), None) if entry2 else None
    print("  the follow-up as the operator sees it:", mine)
    verdicts.append(
        (
            "the operator's queue route shows the follow-up as still queued, not merely present",
            bool(mine) and mine.get("state") == "queued",
        )
    )

    step("7. THE QUESTION: is the follow-up ever delivered, or stranded behind the crash?")
    # Bounded generously -- turn one is a 30-count and this is a freshly restarted Hub.
    deadline = time.time() + 420
    while time.time() < deadline:
        b = entry_row(entry2)
        if b and b["state"] != "queued":
            break
        time.sleep(3)
    b_final = entry_row(entry2)
    print("  entry2 final:", b_final)
    verdicts.append(
        (
            "the follow-up is eventually delivered, not stranded behind the crash",
            bool(b_final) and b_final["state"] == "delivered",
        )
    )
    run2 = None
    if b_final and b_final.get("delivered_in_run_id"):
        rows = sql(
            "SELECT id,status,conversation_id,session_id,initiator FROM runs WHERE id = ?",
            (b_final["delivered_in_run_id"],),
        )
        run2 = rows[0] if rows else None
    print("  the run that carried it:", run2)
    verdicts.append(
        (
            "...on ITS OWN conversation B, not folded into the crashed one",
            bool(run2) and run2["conversation_id"] == conv_b,
        )
    )

    step("8. Did the second message's own words actually reach the agent?")
    # Wait for that run to finish before reading its output, not for the agent to be idle: a
    # third turn could start behind it and `idle` would then describe the wrong thing.
    deadline = time.time() + 300
    while run2 and time.time() < deadline:
        rows = sql("SELECT id,status FROM runs WHERE id = ?", (run2["id"],))
        if rows and rows[0]["status"] != "running":
            break
        time.sleep(3)
    outs = (
        sql(
            "SELECT kind,content FROM agent_outputs WHERE run_id = ? ORDER BY sequence, id",
            (run2["id"],),
        )
        if run2
        else []
    )
    # `kind == "text"` ONLY. The first version of this check searched every row, and passed on a
    # `thinking` row in which the agent was reasoning about the message and deciding NOT to obey
    # it -- the token was present, the reply was not. `thinking` is the agent talking to itself
    # and `tool_use` is a call it made; the assistant's actual answer is `text`, and that is the
    # only surface on which "the agent answered" is a true statement.
    #
    # F139 also applies: every tool RESULT renders as the literal string "tool completed", so no
    # tool's return value is in here either. Asking for plain text is what makes this checkable.
    said = "\n".join((o.get("content") or "") for o in outs if o.get("kind") == "text")
    every = "\n".join((o.get("content") or "") for o in outs)
    print(f"  {len(outs)} output rows on that run; {len(said)} chars of assistant text")
    print("  text:", said[-500:].replace("\n", " | ") if said else "(none)")
    if f"SECOND-{STAMP}" in every and f"SECOND-{STAMP}" not in said:
        print("  NOTE: the token appears only outside the reply -- the agent saw it and did not "
              "answer with it")
    verdicts.append(
        (
            f"the agent ANSWERED the follow-up, in its reply text (SECOND-{STAMP})",
            f"SECOND-{STAMP}" in said,
        )
    )

    step("9. Events, the operator's actual view")
    code, body = api("GET", f"/projects/{P}/events/history?limit=70")
    rows = body.get("events") if isinstance(body, dict) else body
    for e in rows or []:
        if e.get("type") in ("context_warning", "agent_output"):
            continue
        print(f"  {str(e.get('timestamp'))[11:19]} {e.get('type')} {str(e.get('data'))[:170]}")

    step("VERDICTS")
    for label, ok in verdicts:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"\nENTRY1={entry1} CONV_A={conv_a}\nENTRY2={entry2} CONV_B={conv_b}")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
