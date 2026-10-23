"""F952 drive: the Overview's spend line and agent strip say what the Budgets page says.

Run after f952_seed.py, in Chromium against the served bundle; prints the spend line and the
agent rows.

  AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/f952_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

norm = lambda s: " ".join((s or "").split())  # noqa: E731

with Judge("f952", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", width=1440, query="tab=overview")
    page.wait_for_timeout(4000)
    line = page.locator("[data-slot=spend-line]")
    print("SPEND:", norm(line.first.text_content()) if line.count() else None)
    for row in page.locator(".aw-ov-row-end[title='Spent so far']").all():
        print("AGENT ROW:", norm(row.locator("xpath=ancestor::button").text_content()))
    j.shot(page, "overview")
    print("console errors:", j.errors[:5])
