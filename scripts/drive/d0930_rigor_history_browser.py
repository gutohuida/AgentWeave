"""Drive `a-documents-rigor-history-and-retired-requirements-are-on-screen` task 3.1 in a browser.

Usage: AW_HUB=... AW_KEY=... py -3.11 scripts/drive/d0930_rigor_history_browser.py <project-id> <shots-dir>
A throwaway Hub only (never :8000 / :8010). Seeds through the API, then drives the app.
"""

import os
import sys

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PID, SHOTS = sys.argv[1], sys.argv[2]
os.makedirs(SHOTS, exist_ok=True)
S = "/projects/%s/project" % PID
HUB, KEY = os.environ["AW_HUB"], os.environ["AW_KEY"]


def payload(reqs):
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Rigor drive", "summary": "One.",
        "problem": "Drive.", "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
        "requirements": [{"key": k, "statement": "The README MUST mention %s." % k, "modal": "MUST"} for k in reqs],
        "acceptance_criteria": [], "tasks": [], "algorithms": [], "design": "",
        "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
    }


c, doc = api("POST", S + "/documents", {"title": "Rigor drive", "kind": "change-spec"})
print("create", c, doc.get("path"), doc.get("rigor"))
path = doc["path"]
print("write two", api("PUT", S + "/documents/%s/content" % path, {"document": payload(["alpha", "beta"])})[0])
c, reqs = api("GET", S + "/spec/requirements?document=" + path)
rows = reqs if isinstance(reqs, list) else reqs.get("requirements", reqs)
print("requirements", c, [(r["identifier"], r.get("state")) for r in rows])
beta = [r for r in rows if "beta" in str(r)][0]["identifier"]
c, task = api("POST", "/projects/%s/tasks" % PID, {"title": "Build " + beta, "requirement_ids": [beta], "spec_document": path})
print("task", c, task.get("id"))
print("write one", api("PUT", S + "/documents/%s/content" % path, {"document": payload(["alpha"])})[0])
c, reqs = api("GET", S + "/spec/requirements?document=" + path)
rows = reqs if isinstance(reqs, list) else reqs.get("requirements", reqs)
print("after drop", [(r["identifier"], r.get("state")) for r in rows])

SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, PID)
)
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1600, "height": 1000})
    pg.add_init_script(SEED)
    pg.goto(HUB + "/?project=%s&tab=spec&document=%s" % (PID, path.replace("/", "%2F")), wait_until="domcontentloaded")
    pg.get_by_test_id("spec-rigor").wait_for(timeout=15000)
    print("history toggle before any change:", pg.get_by_test_id("spec-rigor-history-toggle").count())
    pg.screenshot(path=SHOTS + "/01_sketch_no_history.png")

    # Promotion: a reason is optional, so Confirm is enabled with an empty box.
    pg.get_by_test_id("spec-rigor").select_option("gate")
    confirm = pg.get_by_test_id("spec-rigor-confirm")
    confirm.wait_for()
    btn = confirm.get_by_role("button", name="Confirm")
    print("promote: confirm enabled with no reason:", btn.is_enabled())
    pg.screenshot(path=SHOTS + "/02_promote_confirm.png")
    btn.click()
    pg.get_by_test_id("spec-rigor-history-toggle").wait_for(timeout=10000)
    pg.wait_for_timeout(800)
    print("after promote:", pg.get_by_test_id("spec-rigor").input_value(), "|", pg.get_by_test_id("spec-rigor-history-toggle").inner_text())

    # Demotion: Confirm is disabled until a reason is typed.
    pg.get_by_test_id("spec-rigor").select_option("sketch")
    confirm.wait_for()
    btn = confirm.get_by_role("button", name="Confirm")
    print("demote: confirm enabled with no reason:", btn.is_enabled())
    pg.screenshot(path=SHOTS + "/03_demote_needs_reason.png")
    pg.get_by_label("Reason for the change").fill("drive: gate was premature")
    print("demote: confirm enabled with a reason:", btn.is_enabled())
    btn.click()
    pg.wait_for_function(
        "() => document.querySelector('[data-testid=spec-rigor-history-toggle]')?.textContent.includes('(2)')",
        timeout=10000,
    )
    pg.get_by_test_id("spec-rigor-history-toggle").click()
    items = pg.get_by_test_id("spec-rigor-history").locator("li")
    print("history rows (newest first):")
    for i in range(items.count()):
        print("  ", items.nth(i).inner_text().replace("\n", " "))
    pg.screenshot(path=SHOTS + "/04_history_newest_first.png")

    # Retired requirements.
    toggle = pg.get_by_test_id("spec-retired-toggle")
    toggle.wait_for(timeout=10000)
    print("retired toggle:", toggle.inner_text())
    toggle.click()
    pg.get_by_test_id("spec-retired-expand-" + beta).click()
    detail = pg.get_by_test_id("spec-retired-detail-" + beta)
    detail.wait_for(timeout=10000)
    pg.wait_for_timeout(800)
    print("retired detail:", detail.inner_text().replace("\n", " | "))
    print("task row present:", pg.get_by_test_id("spec-retired-task-" + task["id"]).count())
    pg.screenshot(path=SHOTS + "/05_retired_with_task.png", full_page=True)
    br.close()

c, hist = api("GET", S + "/documents/%s/rigor-history" % path)
print("route history (oldest first):", c, [(h["from"], h["to"], h["reason"]) for h in (hist if isinstance(hist, list) else hist.get("history", []))])
