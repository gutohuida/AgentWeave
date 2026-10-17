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
    # Cross-links: every mention of evidence opens the pieces it means.
    story = j.page(TERRA, mode="dark", query="tab=tasks")
    story.get_by_test_id("task-open-task-87ce01a67b0c").first.wait_for(timeout=30000)
    story.get_by_test_id("task-open-task-87ce01a67b0c").first.click()
    story.get_by_test_id("task-story-evidence-open-task-87ce01a67b0c").click()
    open_browser(story)
    check("the story's Evidence cell opens that task's pieces",
          "focus=task-87ce01a67b0c" in story.url
          and story.locator("[data-testid^='evidence-row-ev-']").count() == 10,
          story.url)
    story.context.close()
    doc = "spec/changes/terra-app-and-plugin-contract/spec.json"
    cover = j.page(TERRA, mode="light", query=f"tab=spec&document={doc}")
    cover.get_by_test_id("spec-coverage").wait_for(timeout=30000)
    cover.get_by_test_id("spec-coverage").locator("button").first.click()
    j.shot(cover, "coverage_row_light", locator=cover.get_by_test_id("coverage-row-FR-15"))
    cover.get_by_test_id("coverage-evidence-open-FR-15").click()
    open_browser(cover)
    groups = cover.locator("section[data-testid^='evidence-group-']")
    check("the coverage link focuses that document's FR-15 by its durable id",
          "focus=spreq-" in cover.url and groups.count() == 1, f"{cover.url} groups={groups.count()}")
    check("the focus chip names the document",
          "terra" in cover.get_by_test_id("evidence-focus").inner_text().lower(),
          cover.get_by_test_id("evidence-focus").inner_text())
    j.shot(cover, "coverage_focus_light")
    cover.locator("[data-testid^='evidence-row-toggle-']").first.click()
    cover.wait_for_timeout(1200)
    check("FR-15's wording reads now that the replica carries untracked spec files",
          "could not be read" not in cover.get_by_test_id("evidence-browser").inner_text())
    cover.context.close()
    check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))

print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
