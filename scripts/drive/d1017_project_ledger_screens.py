"""Judge the project ledger (slice project-ledger) on the Terra replica, in a real browser.

    py -3.11 scripts/drive/terra_replica.py --up 8130
    AW_DEV_HUB=http://127.0.0.1:8130 npx vite --host 127.0.0.1 --port 5179     (from hub/ui)
    py -3.11 scripts/drive/d1017_project_ledger_screens.py
"""

import json
import sys
import urllib.request

from uiharness import Judge, replica

TERRA = "proj-cd006955cbe2"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def open_ledger(page):
    page.get_by_test_id("project-ledger").wait_for(timeout=30000)
    page.wait_for_timeout(1200)


hub, key, _db = replica()
request = urllib.request.Request(f"{hub}/api/v1/projects/{TERRA}/ledger",
                                 headers={"Authorization": f"Bearer {key}"})
with urllib.request.urlopen(request, timeout=60) as response:
    route = json.loads(response.read())

with Judge("d1017-project-ledger", hub="http://127.0.0.1:5179", key=key) as j:
    j.shots(TERRA, "ledger", open_ledger, query="tab=activity", full_page=True)
    page = j.page(TERRA, mode="dark", query="tab=activity")
    open_ledger(page)
    check("the Activity tab opens on the ledger", page.get_by_test_id("project-ledger").count() == 1)
    spend = page.get_by_test_id("ledger-total-spend").inner_text()
    check("total spend is the route's", spend == f"${route['spend']['total_usd']:.2f}", spend)
    merged = page.get_by_test_id("ledger-total-merged").inner_text()
    check("merged count is the route's", merged == str(route["totals"]["merged"]), merged)
    # The rest wait, inert, in a closed expander; only the preview is visible.
    rows = page.locator("[data-testid='ledger-merges'] > ul.aw-req-list > li")
    check("the merge lane previews its newest rows",
          rows.count() == min(8, len(route["merges"])) and
          rows.first.get_attribute("data-testid") == f"ledger-merge-{route['merges'][0]['id']}",
          str(rows.count()))
    notice = page.get_by_test_id("ledger-notice-context_warning").inner_text()
    check("context warnings are one counted row", str(route["notices"][0]["count"]) in notice, notice[:80])
    bars = page.get_by_test_id("ledger-spend-by-day").locator("button")
    bars.first.hover()
    page.wait_for_timeout(300)
    readout = page.locator(".aw-ledger-chart-readout").inner_text()
    check("hovering a day reads its spend", "$" in readout, readout)
    j.shot(page, "hover_dark")
    page.get_by_test_id("activity-subview-activity").click()
    page.wait_for_timeout(1500)
    folded = page.get_by_test_id("activity-folded-context_warning")
    check("the live log folds context warnings", folded.count() <= 1)
    j.shot(page, "live_dark")
    page.context.close()
    check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))

print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
