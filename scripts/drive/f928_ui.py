"""F928 UI drive: a permission card sits in the conversation whose run asked.

Conversation A is finished; a fresh turn in conversation B calls archive_job and waits. With the
panel left on A the card must be absent and the bar must say A is not the one waiting; opening B
shows the card; Allow reaches the run.

  AW_E2E_STATE=... py -3.11 scripts/drive/f928_ui.py <project-id> <agent>
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, AGENT = sys.argv[1], sys.argv[2]
norm = lambda s: " ".join((s or "").split())  # noqa: E731

e2e.call("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": True})
s, job = e2e.request("POST", f"/projects/{P}/jobs", {
    "name": "archive-me", "agent": AGENT, "message": "Reply OK.", "cron": "0 4 * * *", "enabled": False})
JOB = job["id"]
try:
    with Judge("f928", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light")
        page.wait_for_timeout(3000)
        page.get_by_text(AGENT, exact=True).first.click()
        page.wait_for_timeout(2500)
        rid = e2e.cmd_turn(P, AGENT, (
            f"Call the AgentWeave archive_job tool exactly once with job_id '{JOB}'. Report what it "
            "returned, word for word. Do not retry."), perm="workspace", fresh=True)
        row = None
        deadline = time.time() + 240
        while time.time() < deadline and row is None:
            st, rows = e2e.request("GET", f"/projects/{P}/permission-requests")
            row = next((r for r in rows if r.get("run_id") == rid and r["status"] == "pending"), None)
            time.sleep(2)
        print("PENDING:", row and (row["id"], row["conversation_id"], row["tool_name"]))
        page.wait_for_timeout(5000)
        print("PANEL ON A: cards =", page.locator("[data-testid='permission-requests']").count())
        note = page.locator("[data-testid='conversation-busy-elsewhere']")
        print("PANEL ON A: bar =", norm(note.first.text_content()) if note.count() else "<absent>")
        j.shot(page, "01_on_the_other_conversation")
        note.locator("button").first.click()
        page.wait_for_timeout(2500)
        card = page.locator(f"[data-testid='permission-request-{row['id']}']")
        print("PANEL ON B: card =", card.count(), norm(card.first.text_content())[:200] if card.count() else "")
        j.shot(page, "02_on_the_asking_conversation")
        page.locator(f"[data-testid='permission-allow-{row['id']}']").click()
        time.sleep(15)
        print("RUN:", e2e.ro().execute("select status from runs where id=?", (rid,)).fetchone()[0])
        print("console errors:", j.errors[:5])
finally:
    jobs = e2e.call("GET", f"/projects/{P}/jobs?include_archived=true")
    me = next((x for x in jobs if x["id"] == JOB), None)
    if me and not me.get("archived_at"):
        e2e.request("POST", f"/projects/{P}/jobs/{JOB}/archive")
    e2e.call("PUT", f"/projects/{P}/settings", {"allow_agent_jobs": False})
