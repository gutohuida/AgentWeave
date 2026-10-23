"""2026-10-23 Flows & review drive, UI: what the operator reads about a review the gate refused
(tester's stale-evidence approval) -- the Overview's Needs you, the task card, its drawer and story.

  AW_P=proj-... py -3.11 scripts/drive/s1023_lb_ui2.py <task-id>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


task = sys.argv[1]
with Judge("s1023-lb2", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(5000)
    print("=== OVERVIEW\n", norm(page.locator("main").first.text_content())[:3000])
    j.shot(page, "overview", full_page=True)
    page.context.close()
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(5000)
    print("\n=== CARD\n", norm(page.get_by_test_id(f"task-open-{task}").text_content())[:800])
    page.get_by_test_id(f"task-open-{task}").click()
    page.wait_for_timeout(4000)
    dialog = page.get_by_role("dialog").last
    body = dialog if dialog.count() else page.locator("aside").last
    print("\n=== DRAWER\n", norm(body.text_content())[:6000])
    j.shot(page, "drawer", full_page=True)
    print("console errors:", j.errors[:5])
