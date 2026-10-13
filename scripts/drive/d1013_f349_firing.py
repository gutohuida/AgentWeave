"""Drive F349 slice 3 (design D6) on a scratch Hub from source: a job firing whose events are now
written through `persist_accepted_event` and whose start goes through `schedule_accepted` still
fires, records and runs as before.

A real lock cannot be timed between the firing's commit and its schedule (SQLite waits 30 s for a
writer), so the failure itself is pinned by
`hub/tests/test_accepted_input_is_answered_as_accepted.py`; this drive shows the happy path of the
changed firing path in a real process, with one real Haiku turn:

1. A job on a Haiku-bound agent, pressed with `POST /jobs/<id>/run`: 200 and a `job_run_id`.
2. Its `queue_entry_queued` and `job_fired` events are recorded (now each in its own session).
3. Its turn runs and completes, and the `JobRun` reaches `completed`, not `failed`.

The job is disabled at the end. Needs AW_HUB, AW_KEY, AW_DB (the scratch Hub's SQLite, read only).
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

DB = os.environ["AW_DB"]
TAG = time.strftime("%H%M%S")
root = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / f"f349f-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("f349 firing drive\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "a@example.invalid"],
    ["git", "config", "user.name", "a"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "x"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

failures = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def rows(query, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"f349f-{TAG}"})
if c not in (200, 201):
    show("open", c, proj)
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"
c, _ = api("POST", f"{A}/session/sync", {"data": {"agents": {"firer": {}}}})
check("agent created", c == 200, c)
c, runner = api(
    "POST",
    f"{A}/runners",
    {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
)
check("runner created", c == 201, c)
c, _ = api("PATCH", f"{A}/agents/firer", {"runner_id": runner["id"]})
check("runner bound", c == 200, c)

c, job = api(
    "POST",
    f"{A}/jobs",
    {
        "name": f"f349 firing {TAG}",
        "agent": "firer",
        "message": "Reply with the single word done. Do not use any tools.",
        "cron": "0 0 1 1 *",
    },
)
check("job created", c == 201, c)
if c != 201:
    show("job", c, job)
    sys.exit(1)
JOB = job["id"]
try:
    c, pressed = api("POST", f"{A}/jobs/{JOB}/run")
    check("press answered 200", c == 200, (c, pressed))
    run_id = (pressed or {}).get("job_run_id")
    check("press names its job run", bool(run_id), pressed)

    for kind in ("queue_entry_queued", "job_fired"):
        found = [
            d
            for (d,) in rows(
                "select data from event_logs where project_id=? and event_type=?", (PID, kind)
            )
            if json.loads(d).get("job_id") == JOB
        ]
        check(f"{kind} recorded", len(found) == 1, len(found))

    deadline = time.time() + 180
    status = None
    while time.time() < deadline:
        got = rows("select status, error_summary from job_runs where id=?", (run_id,))
        status = got[0] if got else None
        if status and status[0] not in ("fired", "in_progress"):
            break
        time.sleep(2)
    check("the job run completed", bool(status) and status[0] == "completed", status)
    runs = rows("select status from runs where project_id=? and agent='firer'", (PID,))
    check("one real turn ran and completed", runs == [("completed",)], runs)
finally:
    c, _ = api("PATCH", f"{A}/jobs/{JOB}", {"enabled": False})
    print(f"job disabled: {c}")

print(f"\n{len(failures)} failed" if failures else "\nall passed")
sys.exit(1 if failures else 0)
