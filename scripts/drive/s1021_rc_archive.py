"""Reach sweep 2026-10-21, capability plane: an agent's `archive_job` always asks the operator
(the route answers 409 `operator_direction_required` with a permission request; the tool waits).
Turn 1: Deny on the card -> the agent is told it was not approved, the job stays. Turn 2: Allow ->
archived. Real browser on the served bundle; allow_agent_jobs on for the drive, off after.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_rc_archive.py <project-id> <agent>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, AGENT = sys.argv[1], sys.argv[2]


def norm(s):
    return " ".join((s or "").split())


def requests_for(run_id):
    s, rows = e2e.request("GET", f"/projects/{P}/permission-requests?pending_only=false")
    return [r for r in (rows if isinstance(rows, list) else []) if r.get("run_id") == run_id]


def run_status(run_id):
    return e2e.ro().execute("select status from runs where id=?", (run_id,)).fetchone()[0]


def job_state(job_id):
    jobs = e2e.call("GET", f"/projects/{P}/jobs?include_archived=true")
    j = next(x for x in jobs if x["id"] == job_id)
    return {k: j.get(k) for k in ("archived", "archived_at", "enabled")}


e2e.call("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": True})
s, job = e2e.request("POST", f"/projects/{P}/jobs", {
    "name": "archive-me", "agent": AGENT, "message": "Reply OK.", "cron": "0 4 * * *", "enabled": False})
print("JOB create", s, json.dumps(job)[:200])
JOB = job["id"]
try:
    with Judge("s1021-archive", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light")
        page.wait_for_timeout(3000)
        page.get_by_text(AGENT, exact=True).first.click()
        page.wait_for_timeout(2500)
        for turn_no, choice in [(int(n), c) for n, c in (x.split(":") for x in (sys.argv[3] if len(sys.argv) > 3 else "1:deny,2:allow").split(","))]:
            rid = e2e.cmd_turn(P, AGENT, (
                f"Call the AgentWeave archive_job tool exactly once with job_id '{JOB}'. Report what it "
                "returned or the refusal, word for word. Do not retry."), perm="workspace", fresh=True)
            seen = False
            deadline = time.time() + 300
            while time.time() < deadline and run_status(rid) in ("running", "queued", "starting", "pending"):
                for row in requests_for(rid):
                    if row["status"] != "pending" or seen:
                        continue
                    seen = True
                    print(f"T{turn_no} PENDING:", row["tool_name"], json.dumps(row.get("tool_input"))[:200])
                    card = page.locator(f"[data-testid='permission-request-{row['id']}']")
                    try:
                        card.wait_for(timeout=20000)
                        print(f"T{turn_no} CARD:", norm(card.text_content())[:600])
                        j.shot(page, f"0{turn_no}_archive_card")
                    except Exception as exc:  # noqa: BLE001
                        print("  card not visible:", str(exc)[:120])
                    page.locator(f"[data-testid='permission-{choice}-{row['id']}']").click()
                time.sleep(2)
            print(f"T{turn_no} RUN", rid, run_status(rid), "| saw a card:", seen, "| job:", job_state(JOB))
            e2e.dump_turn(rid)
        print("console errors:", j.errors[:8])
finally:
    st = job_state(JOB)
    if not st.get("archived"):
        e2e.request("POST", f"/projects/{P}/jobs/{JOB}/archive")
    e2e.call("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": False})
    print("FINAL job:", job_state(JOB))
