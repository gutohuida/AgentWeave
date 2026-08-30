"""Row 19, the half that was never driven: kill the Hub with a run in flight.

The other two halves (two concurrent triggers for one agent, and a stop mid-turn) were driven
2026-08-29 and both held. This one was skipped every previous sweep because the Hub under the
drive was always carrying a fix under test.

What it asks, in order:

  1. A real Haiku turn is started and reaches `running` with a pid the Hub recorded.
  2. The Hub is killed with `Stop-Process -Force` -- no lifespan shutdown, so
     `terminate_all_active_runs()` never runs. This is a crash, not a bounce.
  3. Is the spawned CLI still alive after its parent died?  This file predicted YES on the
     reasoning that Windows reaps no grandchild -- and it is measured NO, twice, on
     2026-08-30 (F145). A Claude run is spawned through a ConPTY whose host process is the
     Hub's own child, so force-killing the Hub tears down the pseudoconsole and the attached
     `claude.exe` goes with it. That matters because `reconcile_interrupted_runs` skips any
     run whose `pid_alive(run.pid)` is still true: an orphan would be the wedging case, and
     there is no orphan.
  4. The Hub is restarted on the same database. What does the operator see: is the run still
     `running`, is the agent still busy, and can that agent be triggered again?

Step 4 is the finding-shaped one. A run left `running` forever wedges its agent permanently,
because `POST /agent/trigger` refuses while a run is in progress.

Usage:  AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_row19_crash.py
"""

import os
import subprocess
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "alpha"
PORT = os.environ.get("AW_PORT") or "8011"
DB = os.environ.get(
    "AW_DB", "sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0829/aw0829.db"
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("AW_HUBLOG", "C:/Users/huida/AppData/Local/Temp/aw0829/hub_crash.log")


def step(label):
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def ps(script):
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    return (out.stdout or "").strip() + (("\n" + out.stderr.strip()) if out.stderr.strip() else "")


def hub_pids():
    """Every python process serving this port, launcher and child alike."""
    raw = ps(
        "Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='py.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*uvicorn*--port {PORT}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    return [int(x) for x in raw.split() if x.strip().isdigit()]


def alive(pid):
    return ps(f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ 'yes' }} else {{ 'no' }}")


def proc_line(pid):
    return ps(
        f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
        "ForEach-Object { $_.Name + ' | started ' + $_.CreationDate + ' | ' + "
        "$_.CommandLine.Substring(0, [Math]::Min(110, $_.CommandLine.Length)) }"
    )


def hub_up(timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        code, _ = api("GET", "/projects", timeout=3)
        if code == 200:
            return True
        time.sleep(1)
    return False


def children_of(pid):
    """Every process whose parent is `pid`, as (pid, name) -- the spawned CLI lives here.

    No REST route exposes a run's pid, so the drive finds the spawned process the way an
    operator with Task Manager would: by parentage from the Hub process.
    """
    raw = ps(
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | "
        "ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.Name }"
    )
    out = []
    for line in raw.splitlines():
        bits = line.split(None, 1)
        if bits and bits[0].isdigit():
            out.append((int(bits[0]), bits[1] if len(bits) > 1 else "?"))
    return out


def descendants(pid, depth=3):
    seen = []
    frontier = [pid]
    for _ in range(depth):
        nxt = []
        for p in frontier:
            for cpid, cname in children_of(p):
                seen.append((cpid, cname))
                nxt.append(cpid)
        frontier = nxt
    return seen


def db_runs(limit=4):
    """Read the `runs` table directly. OBSERVATION ONLY -- no drive action goes through here.

    The Hub exposes no run-status route, so this is the only way to see what the operator's UI
    is being told from underneath: status, pid, ended_at, exit_code.
    """
    import sqlite3

    path = DB.split("///", 1)[1]
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT id, agent, status, pid, started_at, ended_at, exit_code "
            "FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def agent_row():
    code, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else body.get("agents", [])
    for a in rows:
        if a.get("name") == AGENT:
            return a
    return None


def wait_for(label, predicate, timeout=90, interval=2):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            print(f"  [{time.strftime('%H:%M:%S')}] {label}: yes")
            return value
        time.sleep(interval)
    print(f"  [{time.strftime('%H:%M:%S')}] {label}: TIMED OUT after {timeout}s")
    return None


def main():
    verdicts = []

    step("PRE. Preconditions")
    if not P or not AGENT:
        raise SystemExit("set AW_PROJECT and AW_AGENT -- this file must not fall back to a default")
    pre = agent_row()
    if pre is None:
        raise SystemExit(f"agent {AGENT!r} does not exist on {P}")
    if pre.get("archived") or not pre.get("runner_id"):
        raise SystemExit(f"agent {AGENT!r} must be open and bound to a runner")
    if pre.get("status") != "idle":
        raise SystemExit(
            f"agent {AGENT!r} is {pre.get('status')!r}, not idle -- a crash landing on somebody "
            "else's run reports on their turn, not this one"
        )
    if not hub_pids():
        raise SystemExit(f"no uvicorn is serving --port {PORT}; there is nothing to crash")
    print(f"  [OK ] {AGENT} idle and bound; a Hub is serving {PORT}")

    step("0. Baseline: agent idle, Hub pids")
    a = agent_row()
    print(f"  agent {AGENT}: status={a and a.get('status')}")
    pids = hub_pids()
    print(f"  hub pids: {pids}")
    for pid in pids:
        print("   ", proc_line(pid))

    step("1. Start a real turn long enough to still be running when the Hub dies")
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            # The crash has to land INSIDE the turn, so the turn needs a step that takes longer
            # than the ~13s it takes this file to reach the kill. It used to ask for `sleep 90`
            # through the Bash tool; Claude Code refuses a foreground sleep outright ("To wait for
            # a command you started, use run_in_background: true"), so that step failed instantly
            # and the turn was still running at the kill only by luck. A run of small sequential
            # writes is slow for a reason the CLI will not argue with.
            "message": (
                "Step 1: write the single line 'before the crash' to a new file named "
                "crash_before.txt in the project root. Step 2: write TWELVE more files named "
                "crash_step_01.txt through crash_step_12.txt, one tool call each, in order, "
                "each containing only its own number spelled out in words. Do not batch them "
                "and do not use a script. Step 3: only after all twelve exist, write the "
                "single line 'after the crash' to crash_after.txt. Do not skip a step."
            ),
        },
    )
    show("POST /agent/trigger", code, body, limit=700)
    if code >= 300:
        print("TRIGGER REFUSED -- nothing to crash on")
        return

    run_id = body.get("run_id")
    running = wait_for(
        "agent reports status=running",
        lambda: (lambda a: a if a and a.get("status") == "running" else None)(agent_row()),
        timeout=60,
    )
    if not running:
        print("FAIL -- the agent never went running")
        return

    for row in db_runs():
        print("  runs table:", row)
    child_pid = None
    for pid, name in descendants(hub_pids()[-1]):
        print(f"  hub descendant: {pid} {name}")
        if child_pid is None:
            child_pid = pid
    if child_pid is None:
        print("  no descendant process found -- the spawn may be in-process")

    print("  letting the turn get into its long step before the crash...")
    time.sleep(10)

    step("2. Kill the Hub HARD -- no lifespan shutdown, no terminate_all_active_runs()")
    pids = hub_pids()
    print(f"  killing {pids}")
    print(ps("Stop-Process -Id " + ",".join(str(p) for p in pids) + " -Force"))
    time.sleep(3)
    for pid in pids:
        print(f"  hub pid {pid} alive after kill: {alive(pid)}")
    code, _ = api("GET", "/projects", timeout=3)
    print(f"  GET /projects with the Hub dead: {code} (0 == no connection)")
    verdicts.append(("hub is really dead", code == 0))

    step("3. Is the spawned CLI orphaned or reaped?")
    # The subject is the pid the HUB RECORDED for this run, not the first process that happened to
    # come back from a parentage walk. That walk returns the ConPTY host (`OpenConsole.exe`) as
    # often as the CLI, and taking its first element answered this question about the console host
    # for one whole drive (F145). `runs.pid` is what `reconcile_interrupted_runs` itself consults.
    run_pid = next((r["pid"] for r in db_runs(6) if r["id"] == run_id), None)
    child_state = alive(run_pid) if run_pid else "n/a"
    print(f"  the run's own recorded pid {run_pid} alive: {child_state}")
    if run_pid:
        print("  ", proc_line(run_pid))
    if child_pid:
        print(f"  (context) first descendant {child_pid} alive: {alive(child_pid)}")
    for row in db_runs():
        print("  runs table (hub dead):", row)
    orphaned = child_state == "yes"
    if orphaned:
        print("  ORPHANED: nothing reaped the grandchild when its parent was killed.")
        print("  reconcile_interrupted_runs() skips any run whose pid is still alive,")
        print("  so this run is the interesting case, not the easy one.")

    step("4. Restart the Hub on the same database")
    subprocess.Popen(
        [
            "py",
            "-3.11",
            "-m",
            "uvicorn",
            "hub.main:app",
            "--port",
            PORT,
            "--host",
            "127.0.0.1",
        ],
        cwd=os.path.join(REPO, "hub"),
        env={
            **os.environ,
            "DATABASE_URL": DB,
            "AW_BOOTSTRAP_API_KEY": os.environ.get("AW_KEY", ""),
            "AW_TICKET_SECRET": os.environ.get("AW_TICKET_SECRET", "aw0829-ticket-secret"),
        },
        stdout=open(LOG, "ab"),
        stderr=subprocess.STDOUT,
    )
    up = hub_up()
    print(f"  hub answering again: {up}")
    verdicts.append(("hub restarted", bool(up)))
    if not up:
        return

    step("5. What does the operator see after the restart?")
    for row in db_runs():
        marker = "  <-- the crashed run" if row["id"] == run_id else ""
        print("  runs table:", row, marker)
    print(f"  spawned pid {child_pid} still alive after restart: {alive(child_pid) if child_pid else 'n/a'}")
    a = agent_row()
    print(f"  agent {AGENT} status now: {a and a.get('status')}")
    code, body = api("GET", f"/projects/{P}/events/history?limit=15")
    show("recent events", code, body, limit=2500)

    step("6. Can the agent be triggered again, or is it wedged?")
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "message": "Reply with the single word: alive. Nothing else."},
    )
    show("POST /agent/trigger (after the crash)", code, body, limit=800)
    verdicts.append(("agent triggerable after crash", code < 300))
    if code < 300:
        time.sleep(6)
        done = wait_for(
            "the post-crash turn finished",
            lambda: (lambda a: a if a and a.get("status") == "idle" else None)(agent_row()),
            timeout=150,
        )
        for row in db_runs(2):
            print("  runs table after:", row)
        verdicts.append(("post-crash turn ran to idle", bool(done)))

    step("7. Accounting: is the interrupted run's outcome recorded?")
    show("usage", *api("GET", f"/projects/{P}/accounting"), limit=1500)

    step("VERDICTS")
    for label, ok in verdicts:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"  orphaned child after hub kill: {orphaned}")


if __name__ == "__main__":
    main()
