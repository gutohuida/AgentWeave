"""2026-10-20 sweep, evidence x drift: in Chromium, a completed task held by its author whose Land is
refused -- does the drawer give the operator the "send the task back" the refusal names?

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_v_ui2.py <hub-url> <task-id>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from s1020_v_lib import MEMO, request  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB, TASK = sys.argv[1], sys.argv[2]
P = json.loads(MEMO.read_text())["project"]


def t(scope, tid):
    loc = scope.get_by_test_id(tid)
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else f"<no {tid}>"


print("task before:", {k: request("GET", f"/projects/{P}/tasks/{TASK}")[1].get(k) for k in ("status", "assignee")})
with Judge("s1020-evidence-drawer", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    page.get_by_test_id(f"task-open-{TASK}").first.dispatch_event("click")
    page.wait_for_timeout(2500)
    page.get_by_test_id(f"task-view-details-{TASK}").first.click()
    page.wait_for_timeout(2000)
    land = page.get_by_test_id(f"task-land-{TASK}")
    print("Land it offered:", land.count())
    if land.count():
        land.first.click()
        page.wait_for_timeout(3000)
    refusal = page.locator("[data-testid^='task-land-refusal'], [data-testid^='task-status-refusal'], [role='alert']")
    print("refusal on screen:", " ".join((refusal.first.text_content() or "").split())[:1500] if refusal.count() else "<none>")
    j.shot(page, "01_land_refused", full_page=True)
    menu = page.get_by_test_id(f"task-status-menu-{TASK}")
    print("status control:", menu.count())
    if menu.count():
        menu.first.click()
        page.wait_for_timeout(1200)
        items = page.get_by_role("menuitem")
        names = [" ".join((items.nth(k).text_content() or "").split()) for k in range(items.count())]
        print("status menu offers:", names)
        j.shot(page, "02_status_menu", full_page=True)
        back = [k for k, n in enumerate(names) if "revision" in n.lower() or "send" in n.lower() or "back" in n.lower()]
        print("a send-back item:", [names[k] for k in back] or "<none>")
        rev = [k for k, n in enumerate(names) if "review" in n.lower()]
        if rev:
            items.nth(rev[0]).click()
            page.wait_for_timeout(2500)
            print("after", names[rev[0]], "->", t(page, f"task-status-refusal-{TASK}")[:700])
            j.shot(page, "03_under_review_refused", full_page=True)
print("task after:", {k: request("GET", f"/projects/{P}/tasks/{TASK}")[1].get(k) for k in ("status", "assignee")})
