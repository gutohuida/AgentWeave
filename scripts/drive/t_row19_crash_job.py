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
        print("  runs after:", sql("SELECT id,status,ended_at FROM runs WHERE agent = ? "
                                   "ORDER BY started_at DESC LIMIT 3", (AGENT,)))
        jr = sql("SELECT id,status,error_summary FROM job_runs WHERE job_id = ?", (job_id,))
        print("  job_runs at the end:", jr)

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
