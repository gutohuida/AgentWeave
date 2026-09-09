"""Second half of the F295 drive: what does the next start make of what the stop left behind?

`f295_shutdown_drive.py` stops a Hub with a real turn in flight and the stop is clean -- but it
leaves the database with a `Run` row this script exists to ask about. Cancelling the in-flight
run makes its failure tail hand the input back, which schedules a *successor* turn; the settle
cancels that successor too, and a task cancelled before it has run its first step never enters
its own `try`, so nothing marks its row. The row is born `running` and stays `running`.

That matters because `turn_scheduler.schedule_agent` refuses an agent that has a `running` row
(the reasoning is written out at `agent_trigger.py:2372-2394`) -- so if nothing repairs it, the
agent is wedged for every future trigger. `reconcile_interrupted_runs()` runs at startup and is
the thing that should repair it. This script restarts against the same database and measures
whether it does, and then triggers a turn to see whether the agent can actually run again.

Usage:  py -3.11 scripts/drive/f295_restart_reconciles.py <db-path> <bootstrap-key> <project-id>
"""

import json
import os
import pathlib
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave")
HUB_DIR = REPO / "hub"
PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"

DB = pathlib.Path(sys.argv[1])
KEY = sys.argv[2]
PROJECT = sys.argv[3]
LOG = DB.parent / "hub8011-restart.log"


def http(method, path, body=None, timeout=30, key=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if key:
        req.add_header("Authorization", "Bearer " + key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text, code = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        text, code = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"
    try:
        return code, json.loads(text)
    except ValueError:
        return code, text


def rows():
    c = sqlite3.connect(str(DB))
    try:
        return [
            tuple(r)
            for r in c.execute(
                "SELECT id, status, ended_at, substr(coalesce(error,''),1,60) FROM runs ORDER BY started_at"
            )
        ]
    finally:
        c.close()


def main():
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"ABORT: something is already listening on {PORT}")

    print("run rows BEFORE restart:")
    for r in rows():
        print("  ", r)

    env = dict(os.environ)
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(DB).replace("\\", "/")
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    env["AW_LOG_LEVEL"] = "INFO"
    # Not a context manager: the handle is the child's stdout and has to outlive
    # this block; it is closed after the process exits.
    logf = open(LOG, "wb")  # noqa: SIM115
    proc = subprocess.Popen(
        [
            "py",
            "-3.11",
            "-m",
            "uvicorn",
            "hub.main:app",
            "--port",
            str(PORT),
            "--host",
            "127.0.0.1",
        ],
        cwd=str(HUB_DIR),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print(f"restarted, pid {proc.pid}")
    for _ in range(60):
        time.sleep(2)
        code, _ = http("GET", "/health", timeout=5)
        if code == 200:
            break
    else:
        logf.close()
        proc.kill()
        sys.exit("ABORT: hub did not come back up")

    print("\nrun rows AFTER restart (reconcile_interrupted_runs has run):")
    after = rows()
    for r in after:
        print("  ", r)
    stuck = [r for r in after if r[1] == "running"]
    print(f"\nrows still 'running': {len(stuck)}  -> {stuck}")

    # The question that actually matters: can the agent take a turn again?
    code, roster = http("GET", f"/api/v1/projects/{PROJECT}/agents", key=KEY)
    agent = roster[0]["name"] if isinstance(roster, list) and roster else None
    print(f"agent: {agent}  status: {roster[0].get('status') if agent else None}")
    code, out = http(
        "POST",
        f"/api/v1/projects/{PROJECT}/agent/trigger",
        {"agent": agent, "session_mode": "new", "message": "Reply with the word OK."},
        key=KEY,
    )
    print(f"POST /agent/trigger after the restart [{code}] {str(out)[:220]}")
    new_run = out.get("run_id") if isinstance(out, dict) else None
    started = False
    for _ in range(40):
        time.sleep(1)
        code, lines = http(
            "GET", f"/api/v1/projects/{PROJECT}/agents/{agent}/output?limit=20", key=KEY
        )
        n = len(lines) if isinstance(lines, list) else 0
        code, roster = http("GET", f"/api/v1/projects/{PROJECT}/agents", key=KEY)
        st = roster[0].get("status") if isinstance(roster, list) and roster else None
        print(f"  status {st}  output lines {n}")
        if st == "idle" and n > 0:
            started = True
            break
        if n > 0:
            started = True
    print(f"\nnew run {new_run} produced output: {started}")

    os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    try:
        rc = proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        rc = None
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    logf.close()
    print(f"second shutdown rc={rc}")
    print("final run rows:")
    for r in rows():
        print("  ", r)
    print(f"kept: {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
