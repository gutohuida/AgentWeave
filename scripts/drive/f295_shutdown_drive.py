"""Drive F295: does a real Hub process stop cleanly with a background run in flight?

Three rounds and 14 mutations checked the *argument* for
`2026-09-07-a-dead-connection-is-never-handed-back-out`; this checks the *product*. It starts a
Hub from source on 8011 against a throwaway database, gets a real Haiku turn running as an
in-process background task, and then asks the process to stop the way a Ctrl-C asks it to --
which is the only path that reaches the `lifespan` teardown at all.

Why Ctrl-Break and not `agentweave stop`: on Windows the CLI's stop is `taskkill /F`, which is
`TerminateProcess` with no signal and no teardown (filed separately as F297). uvicorn installs
`handle_exit` for SIGBREAK on Windows, so `CTRL_BREAK_EVENT` to a child started in its own
process group is the local equivalent of Ctrl-C -- and it is the shutdown path this change exists
to make terminate.

Never 8000 (the operator's real usage) and never 8010's database: this script names its own
database under the temp tree and refuses to run if 8011 is already listening.

Usage:  py -3.11 scripts/drive/f295_shutdown_drive.py [--no-run]
        --no-run  is the control: the same shutdown with nothing in flight.
"""

import json
import os
import pathlib
import re
import secrets
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
HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
TMP = pathlib.Path(os.environ.get("TEMP", r"C:\Users\huida\AppData\Local\Temp")) / f"f295drive{TAG}"
DB = TMP / "f295.db"
LOG = TMP / "hub8011.log"
KEY = "aw_live_" + secrets.token_hex(16)

WITH_RUN = "--no-run" not in sys.argv


def http(method, path, body=None, timeout=30, key=KEY):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
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


def _run_unfinished(run_id):
    """True while the run row has no `ended_at`. Read straight from sqlite, deliberately.

    The Hub exposes no route that answers "is this run still going" -- the roster's status is
    per-agent and the output endpoint only proves a run once started -- and the shutdown being
    measured here is worthless if the run had already finished.
    """
    if not run_id:
        return False
    c = sqlite3.connect(str(DB))
    try:
        row = c.execute("SELECT status, ended_at FROM runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        c.close()
    return bool(row) and row[1] is None


def run_rows():
    """Every run row, in creation order -- including the ones the stop itself created.

    Cancelling the in-flight run makes its failure tail hand the input back, which schedules a
    successor; the settle cancels that successor before it has run a step, so its own `except`
    never fires and its row is born `running` and stays there. Printing every row is how that is
    seen at all -- looking only at the run this script triggered would show a clean stop.
    """
    c = sqlite3.connect(str(DB))
    try:
        return c.execute("SELECT id, status, ended_at FROM runs ORDER BY started_at").fetchall()
    finally:
        c.close()


def port_is_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def newer_than(started_at):
    """Any .py under hub/hub or src newer than the process start means the drive is of stale code."""
    late = []
    for root in (HUB_DIR / "hub", REPO / "src"):
        for p in root.rglob("*.py"):
            if p.stat().st_mtime > started_at:
                late.append(p)
    return late


def main():
    if port_is_open(PORT):
        sys.exit(f"ABORT: something is already listening on {PORT}")
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(DB).replace("\\", "/")
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    env["AW_LOG_LEVEL"] = "INFO"
    env.pop("AW_PROJECT", None)

    print(f"db  {DB}")
    print(f"log {LOG}")
    started_at = time.time()
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
    print(f"uvicorn pid {proc.pid}, own process group")

    up = False
    for _ in range(60):
        time.sleep(2)
        code, body = http("GET", "/health", timeout=5, key=None)
        if code == 200:
            up = True
            print(f"health [{code}] {json.dumps(body)[:200]}")
            break
        if proc.poll() is not None:
            break
    if not up:
        logf.close()
        print(LOG.read_text(encoding="utf-8", errors="replace")[-4000:])
        if proc.poll() is None:
            proc.kill()
        sys.exit("ABORT: hub did not come up")

    late = newer_than(started_at)
    print(
        f"stale-code check: {len(late)} .py newer than process start"
        + ("" if not late else " -> " + ", ".join(str(p) for p in late[:5]))
    )
    if late:
        proc.kill()
        sys.exit("ABORT: the process is running stale code")

    run_id, in_flight = None, False
    if WITH_RUN:
        proj_dir = TMP / "project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "README.md").write_text(f"f295 drive {TAG}\n", encoding="utf-8")
        code, proj = http(
            "POST", "/api/v1/projects/open", {"path": str(proj_dir), "name": f"f295-{TAG}"}
        )
        print(f"POST /projects/open [{code}] {str(proj)[:200]}")
        if code not in (200, 201):
            proc.kill()
            sys.exit("ABORT: could not open a project")
        proj_id = proj["id"]
        code, r = http(
            "POST",
            f"/api/v1/projects/{proj_id}/runners",
            {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU},
        )
        print(f"POST /runners [{code}] {str(r)[:200]}")
        agent = f"f295{TAG}"
        code, a = http(
            "POST", f"/api/v1/projects/{proj_id}/agents", {"name": agent, "runner_id": r["id"]}
        )
        print(f"POST /agents [{code}] {str(a)[:200]}")
        code, _ = http(
            "PATCH",
            f"/api/v1/projects/{proj_id}/agents/{agent}",
            {"default_permission_mode": "bypassPermissions"},
        )
        print(f"PATCH agent permission [{code}]")

        # The turn has to still be running when the break arrives, and "count to 40" is not that:
        # the first attempt at this drive counted, finished in 10s, and the break then landed on
        # an idle Hub while the probe still reported `in_flight` because output had arrived.
        # Output lines are evidence a run *started*, never that it is still going. A blocking
        # shell command is, and it is bounded so nothing outlives the drive.
        code, out = http(
            "POST",
            f"/api/v1/projects/{proj_id}/agent/trigger",
            {
                "agent": agent,
                "session_mode": "new",
                "message": (
                    "Run exactly this command and wait for it to finish: "
                    'py -3.11 -c "import time; time.sleep(120)"'
                    "  Then reply DONE. Do not do anything else."
                ),
            },
        )
        run_id = out.get("run_id") if isinstance(out, dict) else None
        conv_id = out.get("conversation_id") if isinstance(out, dict) else None
        print(f"POST /agent/trigger [{code}] run={run_id} conv={conv_id}")
        if not run_id:
            proc.kill()
            sys.exit(f"ABORT: no run started: {out}")

        # There is no /runs route; in-flight is read the way the UI reads it -- the roster's
        # status field, plus output lines actually arriving from the spawned process.
        state, lines = None, 0
        for _ in range(40):
            time.sleep(1)
            code, roster = http("GET", f"/api/v1/projects/{proj_id}/agents")
            if isinstance(roster, list):
                for row in roster:
                    if row.get("name") == agent:
                        state = row.get("status")
            code, out_lines = http(
                "GET", f"/api/v1/projects/{proj_id}/agents/{agent}/output?limit=50"
            )
            lines = len(out_lines) if isinstance(out_lines, list) else 0
            print(f"  agent status: {state}   output lines: {lines}")
            if lines > 0 and state not in ("idle", "offline", None):
                break
        # The authority on "still in flight" is the run row, not the roster and not the output:
        # a finished run leaves `ended_at` set, and that is checked in the same breath as the
        # break below rather than inferred a minute earlier.
        in_flight = _run_unfinished(run_id)
        print(f"  run row unfinished at break time: {in_flight}")
        if not in_flight:
            print(
                f"  WARNING: the run has already ended (status {state}); this shutdown has "
                "nothing in flight and is a control, not the measurement"
            )

    log_before = LOG.stat().st_size
    if WITH_RUN:
        in_flight = _run_unfinished(run_id)
        print(f"run row unfinished immediately before the break: {in_flight}")
    print("\n--- sending CTRL_BREAK_EVENT (the Ctrl-C path uvicorn actually handles on Windows)")
    t0 = time.time()
    os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    try:
        rc = proc.wait(timeout=120)
        elapsed = time.time() - t0
        print(f"process exited rc={rc} after {elapsed:.2f}s")
        hung = False
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        hung = True
        rc = None
        print(f"process DID NOT EXIT after {elapsed:.0f}s -- killing")
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        proc.wait(timeout=30)
    logf.close()

    # Sliced as BYTES, not characters: `log_before` is a file size, and the migration banner
    # carries multibyte characters, so slicing a decoded str by it lands in the wrong place and
    # silently drops the first lines the shutdown wrote. Cost one FAIL on the control run before
    # it was noticed.
    tail = LOG.read_bytes()[log_before:].decode("utf-8", "replace")
    print("\n--- log written after the break -------------------------------------------")
    print(tail[-6000:])
    print("--- end of log ------------------------------------------------------------")

    checks = {
        "process exited rather than hanging": not hung,
        "uvicorn reported 'Application shutdown complete'": "Application shutdown complete" in tail,
        "no settle-bound WARNING": "did not settle" not in tail,
        "no dead-worker guard WARNING": "dead aiosqlite worker" not in tail.lower(),
        "no 'Event loop is closed' on the way out": "Event loop is closed" not in tail,
        "no traceback after the break": "Traceback (most recent call last)" not in tail,
    }
    print()
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\nshutdown seconds: {elapsed:.2f}   run in flight: {in_flight}   rc: {rc}")
    for line in tail.splitlines():
        if re.search(r"WARNING|ERROR|Shutdown:", line):
            print("  log> " + line.strip()[:200])
    print("\nrun rows the stop left behind:")
    for row in run_rows():
        print("   ", row)
    print(f"\nkept: {LOG}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
