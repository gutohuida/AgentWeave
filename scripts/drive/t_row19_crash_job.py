"""Row 19 x row 11: the Hub killed with a job firing.

`reconcile_stale_job_runs` is the second half of the startup reconciliation pass and nothing has
ever driven it. Its docstring:

    "Mark every `JobRun` row still `in_progress` whose firing has no live `Run` behind it as
     `failed` ... `JobRun` and `Run` share no foreign key, only `conversation_id`"

So the correlation it depends on is a join by convention, not by constraint — which is exactly the
kind of thing that works in a unit test and misses in production, and exactly what **F121** (one
firing, two `JobRun` rows) already found bending. This kills the Hub in the middle of a manual
firing and asks whether the job's history tells the operator the truth afterwards.

The job is disabled and archived in a `finally`. Do not pipe this through `head`: SIGPIPE kills it
before the `finally` runs and leaves a job enabled.

Usage:  AW_HUB=... AW_KEY=... AW_PROJECT=... AW_AGENT=... py -3.11 t_row19_crash_job.py
"""

import os
import subprocess
import sqlite3
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "beta"
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


def start_hub():
    subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", PORT, "--host", "127.0.0.1"],
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
    end = time.time() + 45
    while time.time() < end:
        code, _ = api("GET", "/projects", timeout=3)
        if code == 200:
            return True
        time.sleep(1)
    return False


def sql(q, a=()):
    conn = sqlite3.connect(DB.split("///", 1)[1])
    try:
        cur = conn.execute(q, a)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    verdicts = []
    job_id = None

    step("0. Preconditions")
    if not P or not AGENT or not DB:
        raise SystemExit("set AW_PROJECT, AW_AGENT and AW_DB")
    _, roster = api("GET", f"/projects/{P}/agents")
    pre = next((a for a in (roster or []) if a.get("name") == AGENT), None)
    if pre is None or pre.get("archived") or not pre.get("runner_id"):
        raise SystemExit(f"agent {AGENT!r} must exist, be open, and be bound to a runner")
    if pre.get("status") != "idle":
        raise SystemExit(f"agent {AGENT!r} is {pre.get('status')!r}, not idle")
    _, existing = api("GET", f"/projects/{P}/jobs")
    existing = existing if isinstance(existing, list) else (existing or {}).get("jobs", [])
    if any(j.get("enabled") for j in existing):
        raise SystemExit(f"a job is already enabled on {P}: "
                         f"{[j['id'] for j in existing if j.get('enabled')]}")
    if not hub_pids():
        raise SystemExit(f"no uvicorn is serving --port {PORT}; there is nothing to crash")
    print(f"  [OK ] {AGENT} idle and bound; no job enabled; a Hub is serving {PORT}")

    try:
        step("1. A job, fired by hand")
        code, body = api(
            "POST",
            f"/projects/{P}/jobs",
            {
                "name": "crash-drive",
                "agent": AGENT,
                "message": (
                    "Read calc.py, then read README.md, then reply with one sentence about "
                    "each. Use a separate tool call for each read."
                ),
                # Far enough out that only the manual firing below ever runs it.
                "cron": "0 4 1 1 *",
                "enabled": True,
            },
        )
        show("job", code, body, limit=700)
        if code >= 300:
            return
        job_id = body["id"]

        code, body = api("POST", f"/projects/{P}/jobs/{job_id}/run", {})
        show("fire", code, body, limit=500)

        t0 = time.time()
        runs = []
        while time.time() - t0 < 90:
            runs = sql("SELECT id,status,pid,conversation_id FROM runs WHERE agent = ? "
                       "AND status = 'running'", (AGENT,))
            if runs:
                break
            time.sleep(2)
        print("  running:", runs)
        jr = sql("SELECT id,job_id,status,fired_at,trigger,session_id,error_summary "
                 "FROM job_runs WHERE job_id = ?", (job_id,))
        print("  job_runs before the crash:", jr)
        verdicts.append(("the firing produced a live run and an in_progress JobRun",
                         bool(runs) and any(r["status"] == "in_progress" for r in jr)))

        step("2. Kill the Hub mid-firing")
        verdicts.append(("hub is really dead", kill_hub()))
        if not start_hub():
            print("FAIL -- hub did not come back")
            return

        step("3. What the reconciliation made of it")
        jr = sql("SELECT id,job_id,status,fired_at,trigger,session_id,error_summary "
                 "FROM job_runs WHERE job_id = ?", (job_id,))
        for row in jr:
            print("  job_run:", row)
        print("  runs:", sql("SELECT id,status,ended_at FROM runs WHERE agent = ? "
                             "ORDER BY started_at DESC LIMIT 3", (AGENT,)))
        verdicts.append(("no JobRun is left in_progress",
                         all(r["status"] != "in_progress" for r in jr)))
        verdicts.append(("the crashed firing is recorded as failed",
                         any(r["status"] == "failed" for r in jr)))

        step("4. What the operator reads: the job and its history")
        show("job", *api("GET", f"/projects/{P}/jobs/{job_id}"), limit=2000)
        show("history", *api("GET", f"/projects/{P}/jobs/{job_id}/history"), limit=2000)

        step("5. Does the error summary say anything useful?")
        for row in jr:
            print(f"  {row['id']} {row['status']}: {row.get('error_summary')!r}")

        step("6. And does the redelivered work still run?")
        t0 = time.time()
        while time.time() - t0 < 150:
            live = sql("SELECT id,status FROM runs WHERE agent = ? AND status = 'running'", (AGENT,))
            if not live:
                break
            time.sleep(3)
        after = sql("SELECT id,status,conversation_id,ended_at FROM runs WHERE agent = ? "
                    "ORDER BY started_at DESC LIMIT 3", (AGENT,))
        print("  runs after:", after)
        jr = sql("SELECT id,status,conversation_id,error_summary FROM job_runs WHERE job_id = ?",
                 (job_id,))
        print("  job_runs at the end:", jr)

        # The two verdicts the file was missing, and the reason it read 4/4 while getting the
        # operator's answer wrong (F147). `reconcile_interrupted_runs` RE-QUEUES the crashed
        # firing's input one line before `reconcile_stale_job_runs` writes it off, so the work
        # usually does complete -- on the firing's own conversation -- and the history still says
        # it failed.
        fired_conv = jr[0]["conversation_id"] if jr else None
        finished = [r for r in after
                    if r["conversation_id"] == fired_conv and r["status"] == "completed"]
        verdicts.append((
            "the crashed firing's work was redelivered and completed",
            bool(finished),
        ))
        verdicts.append((
            "...and the job's history says so rather than still reporting a failure",
            bool(finished) and all(r["status"] != "failed" for r in jr),
        ))

        step("VERDICTS")
        for label, ok in verdicts:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    finally:
        if job_id:
            print("\n--- cleanup ---")
            print(api("PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})[0],
                  "disabled")
            print(api("POST", f"/projects/{P}/jobs/{job_id}/archive", {})[0], "archived")
            code, body = api("GET", f"/projects/{P}/jobs")
            rows = body if isinstance(body, list) else body.get("jobs", [])
            print("jobs remaining:", [(r.get("id"), r.get("enabled")) for r in rows])


if __name__ == "__main__":
    main()
