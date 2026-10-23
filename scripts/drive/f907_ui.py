"""F907 UI drive: the Activity tab's Activity view in Chromium against the served bundle.

  AW_E2E_STATE=... py -3.11 scripts/drive/f907_ui.py <project-id>
"""

import os
import pathlib
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f907.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = sys.argv[1]
txt = lambda loc: " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"  # noqa: E731

with Judge("f907", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
    page.wait_for_timeout(3000)
    for row in page.locator(".aw-digest-row").all():
        print(f"[{row.get_attribute('data-severity')}] {txt(row.locator('.aw-digest-sentence'))} | {txt(row.locator('.aw-digest-facts'))}")
    j.shot(page, "digest", full_page=True)
    warn = page.locator("[aria-label='Show'] button", has_text="Warnings")
    if warn.count():
        warn.first.click()
        page.wait_for_timeout(800)
        print("WARNINGS:", [txt(r.locator(".aw-digest-sentence")) for r in page.locator(".aw-digest-row").all()])
