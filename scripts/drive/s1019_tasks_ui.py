"""Tasks sweep 2026-10-19, UI: the task drawer's Story and Details (checks row with earlier runs,
integration note, Land refusal over a pre-existing failure), and the Activity feed's line for the
flow's unstaffed review, in a real browser against the served bundle.

  py -3.11 scripts/drive/s1019_tasks_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1019_tasks_lib import P, S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

CLAMP, SUB, MUL, DIV = "task-c1d7a30f3a47", "task-960d7005a969", S["mul"], S["div"]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def drawer(j, tid):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    page.get_by_test_id(f"task-open-{tid}").first.click()
    page.wait_for_timeout(2500)
    return page


with Judge("s1019-tasks", hub=e2e.hub(), key=e2e.key()) as j:
    # 1. t-clamp's story: two send-backs, six runs, checks, two integration rows.
    page = drawer(j, CLAMP)
    story = page.get_by_test_id(f"task-story-{CLAMP}")
    print("CLAMP story present:", story.count())
    print("CLAMP summary:", txt(page.get_by_test_id(f"task-story-summary-{CLAMP}"))[:400])
    print("CLAMP story text:", txt(story)[:3000])
    links = story.locator("a[href*='conv-'], a[href*='conversation']")
    print("CLAMP conversation links:", links.count(), [links.nth(i).get_attribute("href") for i in range(min(links.count(), 8))])
    j.shot(page, "01_clamp_story", full_page=True)

    # 2. t-sub's story: completed, then the flow refused to staff its review -- is that said?
    page = drawer(j, SUB)
    st = page.get_by_test_id(f"task-story-{SUB}")
    print("SUB story text:", txt(st)[:1500])
    print("SUB story mentions the unstaffed review:", "reviewer" in txt(st).lower())
    j.shot(page, "02_sub_story", full_page=True)

    # 3. mul: Details -> checks row with earlier runs, integration note (skips + merge).
    page = drawer(j, MUL)
    page.get_by_test_id(f"task-view-details-{MUL}").first.click()
    page.wait_for_timeout(1500)
    checks = page.get_by_test_id(f"task-checks-{MUL}")
    print("MUL checks row:", txt(checks)[:400])
    toggle = page.get_by_test_id(f"task-checks-history-toggle-{MUL}")
    print("MUL history toggle:", txt(toggle))
    if toggle.count():
        toggle.first.click()
        page.wait_for_timeout(800)
    runs = page.locator("[data-testid^='task-check-run-']")
    print("MUL earlier runs:", [txt(runs.nth(i)) for i in range(runs.count())])
    print("MUL integration note:", txt(page.get_by_test_id(f"task-integrations-{MUL}"))[:600])
    j.shot(page, "03_mul_details", full_page=True)

    # 4. div: latest run failed only because main fails -- does the row say so? Land refusal.
    page = drawer(j, DIV)
    page.get_by_test_id(f"task-view-details-{DIV}").first.click()
    page.wait_for_timeout(1500)
    print("DIV checks row:", txt(page.get_by_test_id(f"task-checks-{DIV}"))[:700])
    land = page.get_by_test_id(f"task-land-{DIV}")
    print("DIV land button:", txt(land))
    if land.count():
        land.first.click()
        page.wait_for_timeout(2500)
        print("DIV land refusal:", txt(page.get_by_test_id(f"task-status-refusal-{DIV}"))[:700])
        print("DIV land anyway offered:", page.get_by_test_id(f"task-land-anyway-{DIV}").count())
    j.shot(page, "04_div_details_land", full_page=True)

    # 5. Activity feed: the review_unstaffed sentence.
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    body = " ".join((page.locator("main").first.text_content() or "").split())
    i = body.lower().find("review")
    print("ACTIVITY mentions unstaffed review:", "names 'rev' as its reviewer" in body or "could not" in body.lower(),
          body[max(0, i - 200):i + 400] if i >= 0 else "<no 'review' on the page>")
    j.shot(page, "05_activity", full_page=True)
    print("page errors:", j.errors[:5])
