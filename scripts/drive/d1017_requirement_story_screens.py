"""Judge a requirement's story (slice requirement-story) on the Terra replica, in a real browser.

    py -3.11 scripts/drive/terra_replica.py --up 8130
    AW_DEV_HUB=http://127.0.0.1:8130 npx vite --host 127.0.0.1 --port 5179     (from hub/ui)
    py -3.11 scripts/drive/d1017_requirement_story_screens.py

Terra's FR-3 of terra-app-and-plugin-contract was revised three times, every time before the Hub
kept wordings (migration 0131), so each revision must say its wording was not recorded.
"""

import sqlite3
import pathlib
import sys

from uiharness import Judge, replica

TERRA = "proj-cd006955cbe2"
DOC = "spec/changes/terra-app-and-plugin-contract/spec.json"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def open_story(page):
    page.get_by_test_id("requirement-story").wait_for(timeout=30000)
    page.wait_for_timeout(1200)


_hub, key, db = replica()
con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True)
stored = [
    row[0]
    for row in con.execute(
        "select v.id from spec_requirement_revisions v join spec_requirements r on r.id = "
        "v.requirement_id join spec_documents d on d.id = r.document_id where d.path = ? and "
        "r.identifier = 'FR-3' order by v.created_at, v.id",
        (DOC,),
    )
]

with Judge("d1017-requirement-story", hub="http://127.0.0.1:5179", key=key) as j:
    j.shots(TERRA, "story", open_story, query=f"tab=spec&view=requirement&document={DOC}&focus=FR-3")

    cover = j.page(TERRA, mode="dark", query=f"tab=spec&document={DOC}")
    cover.get_by_test_id("spec-coverage").wait_for(timeout=30000)
    cover.get_by_test_id("spec-coverage").locator("button").first.click()
    cover.get_by_test_id("coverage-history-FR-3").click()
    open_story(cover)
    shown = [
        el.get_attribute("data-testid").replace("requirement-revision-", "")
        for el in cover.locator("[data-testid^='requirement-revision-sprev-']").all()
    ]
    check("the coverage row's history opens FR-3's story", "view=requirement" in cover.url, cover.url)
    check("its revisions are spec_requirement_revisions, in order", shown == stored, f"{shown} vs {stored}")
    check("each says its wording was not recorded",
          cover.locator("[data-testid^='requirement-revision-unrecorded-']").count() == len(stored))
    statement = cover.get_by_test_id("requirement-story-statement").inner_text()
    check("the current wording reads", len(statement) > 20 and "could not be read" not in statement, statement[:80])
    cover.get_by_test_id("requirement-story-back").click()
    cover.get_by_test_id("spec-coverage").wait_for(timeout=15000)
    check("back returns to the document", f"document={DOC.replace('/', '%2F')}" in cover.url or DOC in cover.url,
          cover.url)
    cover.context.close()

    browser = j.page(TERRA, mode="light", query="tab=spec&view=evidence")
    browser.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    browser.wait_for_timeout(800)
    browser.locator("[data-testid^='evidence-group-history-']").first.click()
    open_story(browser)
    check("an evidence group's history opens a story", "view=requirement" in browser.url, browser.url)
    j.shot(browser, "from_evidence_light")
    browser.context.close()
    check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))

print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
