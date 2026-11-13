"""Drive F1171 (AW-123): a flow resumes a sent-back task while its job's agent is mid-turn.

A flow whose job agent `owner` is in a long turn of its own, and whose one task is then sent back
to an idle `builder`. A firing must start `builder` on that task while `owner` is still running;
before the fix every firing was refused with no record, the press answering 409 "owner is already
running a turn". The job is created disabled so no firing races the scene. Two Haiku agents; the
job is disabled and archived at the end.
Needs AW_HUB and AW_KEY naming a drive Hub (never :8000), and AW_DB its SQLite file.
"""

import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, task_rows  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = (
    pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch")
    / f"sendback-{TAG}"
)
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("send-back drive\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "a@example.invalid"],
    ["git", "config", "user.name", "a"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "x"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": "sendback-" + TAG})
assert c in (200, 201), (c, proj)
PID = proj["id"]
S = "/projects/%s" % PID
D = S + "/project"
print("project", PID)

c, rn = api("POST", S + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
assert c == 201, (c, rn)
for n in ("owner", "builder"):
    c, b = api("POST", S + "/agents", {"name": n, "runner_id": rn["id"]})
    print("agent", n, c)

c, doc = api("POST", D + "/documents", {"title": "send-back drive"})
path = doc["path"]
pl = {
    "schema_version": 1,
    "kind": doc["kind"],
    "title": "send-back drive",
    "summary": "One task.",
    "problem": "Drive.",
    "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
    "requirements": [{"key": "r1", "statement": "The README MUST be read.", "modal": "MUST"}],
    "acceptance_criteria": [
        {"key": "c1", "requirement": "r1", "given": "g", "when": "w", "then": "t"}
    ],
    "tasks": [
        {
            "key": "t1",
            "title": "Read README",
            "description": "Say done and stop.",
            "requirements": ["r1"],
        }
    ],
    "algorithms": [],
    "design": "",
    "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
}
if doc["kind"] == "change-spec":
    pl["delivery"] = {"mode": "none"}
print("write", api("PUT", D + "/documents/%s/content" % path, {"document": pl})[0])
print("close", api("POST", D + "/documents/close-exploration?path=" + path)[0])
_, spec = api("GET", D + "/spec?path=" + path)
c, b = api(
    "POST",
    D + "/documents/phase?path=%s&to=approved" % path,
    {"reason": "drive", "content_version": spec.get("content_version"), "approve_anyway": True},
)
print("approve", c, b.get("phase"))
DOCID = b.get("id") or path

c, job = api(
    "POST",
    S + "/jobs",
    {
        "name": "Send-back drive",
        "agent": "owner",
        "cron": "0 3 * * *",
        "session_mode": "new",
        "message": "Say the single word done, then stop. Do not use any tools.",
        "purpose": "Drive F1171",
        "spec_document_id": DOCID,
        "enabled": False,
    },
)
assert c == 201, (c, job)
JID = job["id"]
LOOP = (job.get("loop") or {}).get("id")
c, t = api("GET", S + "/tasks?loop_id=%s" % LOOP)
TASK = task_rows(t)[0]["id"]
print("queue task", TASK, "job enabled:", job.get("enabled"))


def _rows(sql, *args):
    """The drive Hub's own database, read-only (AW_DB)."""
    db = sqlite3.connect("file:%s?mode=ro" % os.environ["AW_DB"], uri=True)
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


def builder_runs_on(task_id):
    return _rows(
        "select id, status, started_at from runs where agent = 'builder' and task_id = ?", task_id
    )


def owner_running():
    return bool(
        _rows(
            "select id from runs where agent = 'owner' and project_id = ? and status = 'running'",
            PID,
        )
    )


try:
    # The task is the builder's, walked by the operator up to the point it is sent back.
    print("reassign", api("POST", S + "/tasks/%s/reassign" % TASK, {"agent": "builder"})[0])
    # The reassign briefs the builder itself; let that turn finish so it cannot mask the flow.
    for _ in range(90):
        time.sleep(2)
        runs = builder_runs_on(TASK)
        if runs and all(r[1] != "running" for r in runs):
            break
    print("builder's reassign turn:", builder_runs_on(TASK))
    for status in ("in_progress", "completed"):
        _, now = api("GET", S + "/tasks/%s" % TASK)
        if now.get("status") in ("completed",) or now.get("status") == status:
            continue
        c, b = api("PATCH", S + "/tasks/%s" % TASK, {"status": status})
        print("->", status, c, "" if c == 200 else str(b)[:300])
    before = {r[0] for r in builder_runs_on(TASK)}
    # The job's agent goes into a long turn of its own, outside the flow.
    c, r = api(
        "POST",
        S + "/agent/trigger",
        {
            "agent": "owner",
            "message": "Write a numbered list of 800 distinct animal names, one per line. "
            "Do not use any tools.",
        },
    )
    print("owner trigger", c, str(r)[:120])
    for _ in range(60):
        time.sleep(1)
        if owner_running():
            break
    print("owner's run is running:", owner_running())
    # Now the send-back, and the flow switched on.
    c, b = api(
        "PATCH",
        S + "/tasks/%s" % TASK,
        {"status": "revision_needed", "reason_class": "defect", "notes": "Sent back (drive)."},
    )
    print("-> revision_needed", c, "" if c == 200 else str(b)[:300])
    print("enable", api("PATCH", S + "/jobs/%s" % JID, {"enabled": True})[0])
    print("before press: owner running:", owner_running())
    pressed, r = api("POST", S + "/jobs/%s/run" % JID)
    print("press:", pressed, str(r)[:300])
    started = False
    for _ in range(10):
        time.sleep(3)
        on_task = [r for r in builder_runs_on(TASK) if r[0] not in before]
        busy = owner_running()
        print("  new builder runs on task", on_task, "owner running:", busy)
        if on_task:
            started = busy
            break
    briefings = _rows(
        "select origin_type, job_id, arrived_at, delivered_in_run_id from inbound_queue_entries"
        " where agent = 'builder' and task_id = ? order by sequence",
        TASK,
    )
    print("builder's briefings on the task:", briefings)
    print("job runs:", _rows("select id, fired_at, status from job_runs where job_id = ?", JID))
    started = started and any(b[0] == "job" for b in briefings)
    print(
        "VERDICT (the flow briefs builder on the sent-back task while owner runs):",
        "PASS" if started else "FAIL",
    )
finally:
    print("disable", api("PATCH", S + "/jobs/%s" % JID, {"enabled": False})[0])
    print("archive", api("POST", S + "/jobs/%s/archive" % JID)[0])
print("AW_PROJECT=%s" % PID)
