"""Drive a-firing-is-counted-once-however-many-agents-it-starts (task 3.1) on a live Hub.

A flow with two startable tasks and two Haiku agents; press Run once. `GET /jobs/{id}` must read
`run_count: 1` while its history holds two rows sharing one `fired_at`. The job is disabled and
archived at the end.
Needs AW_HUB and AW_KEY naming a drive Hub (never :8000).
"""

import pathlib
import subprocess
import sys
import time

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, task_rows  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"firing-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("firing drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": "firing-" + TAG})
assert c in (200, 201), (c, proj)
PID = proj["id"]
S = "/projects/%s" % PID
D = S + "/project"
print("project", PID)

c, rn = api("POST", S + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
assert c == 201, (c, rn)
for n in ("one", "two"):
    c, b = api("POST", S + "/agents", {"name": n, "runner_id": rn["id"]})
    print("agent", n, c)

c, doc = api("POST", D + "/documents", {"title": "firing drive"})
path = doc["path"]
pl = {
    "schema_version": 1, "kind": doc["kind"], "title": "firing drive", "summary": "Two tasks.",
    "problem": "Drive.", "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
    "requirements": [{"key": "r1", "statement": "The README MUST be read.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "g", "when": "w", "then": "t"}],
    "tasks": [
        {"key": "t1", "title": "Read README (one)", "description": "Say done and stop.", "requirements": ["r1"]},
        {"key": "t2", "title": "Read README (two)", "description": "Say done and stop.", "requirements": ["r1"]},
    ],
    "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off", "open_questions": [],
}
if doc["kind"] == "change-spec":
    pl["delivery"] = {"mode": "none"}
print("write", api("PUT", D + "/documents/%s/content" % path, {"document": pl})[0])
print("close", api("POST", D + "/documents/close-exploration?path=" + path)[0])
c, b = api("POST", D + "/documents/propose?path=" + path)
print("propose", c, b.get("phase"), b.get("blocking"))
c, b = api("POST", D + "/documents/phase?path=%s&to=approved" % path, {"reason": "drive"})
print("approve", c, b.get("phase"))
DOCID = b.get("id") or path

c, job = api("POST", S + "/jobs", {
    "name": "Firing drive", "agent": "one", "cron": "0 3 * * *", "session_mode": "new",
    "message": "Say the single word done, then stop. Do not use any tools.",
    "purpose": "Drive run_count", "spec_document_id": DOCID,
})
assert c == 201, (c, job)
JID = job["id"]
loop = (job.get("loop") or {}).get("id")
c, t = api("GET", S + "/tasks?loop_id=%s" % loop)
print("queue", [(x["id"], x["status"]) for x in task_rows(t)])


def settle(label):
    for _ in range(60):
        time.sleep(5)
        c, ag = api("GET", S + "/agents")
        if all(a.get("status") != "running" for a in ag):
            break
    c, j = api("GET", S + "/jobs/%s" % JID)
    hist = j.get("history") or []
    fired = sorted({h.get("fired_at") for h in hist})
    print("%s: run_count=%s history_rows=%d distinct_fired_at=%d" % (label, j.get("run_count"), len(hist), len(fired)))
    for h in hist:
        print("   ", h.get("fired_at"), h.get("status"), h.get("agent") or h.get("conversation_id"))
    return j, hist, fired


try:
    c, r = api("POST", S + "/jobs/%s/run" % JID)
    print("press 1:", c, str(r)[:300])
    j, hist, fired = settle("after press 1")
    ok1 = j.get("run_count") == 1 and len(hist) == 2 and len(fired) == 1
    print("VERDICT press 1 (run_count 1, two rows, one fired_at):", "PASS" if ok1 else "FAIL")
finally:
    c, b = api("PATCH", S + "/jobs/%s" % JID, {"enabled": False})
    print("disable", c)
    c, b = api("POST", S + "/jobs/%s/archive" % JID)
    print("archive", c)
    c, jobs = api("GET", S + "/jobs")
    print("jobs left enabled", [x["name"] for x in (jobs if isinstance(jobs, list) else jobs.get("jobs", [])) if x.get("enabled")])
print("AW_PROJECT=%s" % PID)
