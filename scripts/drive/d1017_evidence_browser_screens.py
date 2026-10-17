"""Judge the evidence browser (slice evidence-browser) on the Terra replica, in a real browser.

    py -3.11 scripts/drive/terra_replica.py --up 8130
    AW_DEV_HUB=http://127.0.0.1:8130 npx vite --port 5179     (from hub/ui)
    py -3.11 scripts/drive/d1017_evidence_browser_screens.py
"""

import sys

from uiharness import Judge, replica

TERRA = "proj-cd006955cbe2"
DEV = "http://127.0.0.1:5179"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def open_browser(page):
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(1200)


_hub, key, _db = replica()
with Judge("d1017-evidence-browser", hub=DEV, key=key) as j:
    j.shots(TERRA, "browser", open_browser, query="tab=spec&view=evidence")
    page = j.page(TERRA, mode="dark", query="tab=spec&view=evidence")
    open_browser(page)
    rows = page.locator("[data-testid^='evidence-row-ev-']")
    check("the browser lists Terra's evidence", rows.count() >= 40, f"{rows.count()} rows")
    check("the Spec rail offers Evidence", page.get_by_test_id("spec-rail-evidence").count() == 1)
    page.get_by_test_id("evidence-filter-rejected").click()
    page.wait_for_timeout(400)
    check("the rejected filter narrows to the 3 rejections", rows.count() == 3, f"{rows.count()}")
    first = page.locator("[data-testid^='evidence-row-toggle-']").first
    first.click()
    page.wait_for_timeout(1500)
    j.shot(page, "rejected_open_dark", full_page=False)
    page.get_by_test_id("evidence-filter-all").click()
    page.get_by_test_id("evidence-group-task").click()
    page.wait_for_timeout(600)
    j.shot(page, "by_task_dark")
    page.context.close()
    focused = j.page(TERRA, mode="light", query="tab=spec&view=evidence&focus=task-87ce01a67b0c")
    open_browser(focused)
    check("a task focus narrows to its pieces",
          focused.locator("[data-testid^='evidence-row-ev-']").count() == 10,
          str(focused.locator("[data-testid^='evidence-row-ev-']").count()))
    j.shot(focused, "focused_light")
    focused.context.close()
    check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))

print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
