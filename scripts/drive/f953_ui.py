"""F953 drive: with the token budget spent and a turn held by it, the Overview names the limit,
the use and the held turn, links to Budgets, and does not say "Nothing needs you".

  AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/f953_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

norm = lambda s: " ".join((s or "").split())  # noqa: E731

with Judge("f953", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", width=1440, query="tab=overview")
    page.wait_for_timeout(4000)
    alert = page.locator("[role=alert]")
    print("ALERT:", norm(alert.first.text_content()) if alert.count() else None)
    print("STATUS:", norm(page.locator(".aw-overview-status").first.text_content()))
    j.shot(page, "overview-spent")
    page.locator("[role=alert] button").first.click()
    page.wait_for_timeout(1500)
    print("AFTER CLICK:", page.url, "| Budgets heading:", page.get_by_text("Budgets").count())
    j.shot(page, "after-click")
    print("console errors:", j.errors[:5])
