"""Conversations & composer, 2026-10-23: unarchive from the rail, then rename and archive from the
conversation header, measuring how long the rail takes to follow each (polled every 250 ms).

    py -3.11 scripts/drive/s1023_cv_rail.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e, q  # noqa: E402
from uiharness import Judge  # noqa: E402

CONV = "conv-9c177acf95dd"


def norm(s):
    return " ".join((s or "").split())


def row(c):
    return q("select lifecycle, title from conversations where id=?", c)[0]


def until(page, label, predicate, limit=25):
    t0 = time.time()
    while time.time() - t0 < limit:
        if predicate():
            print(f"  {label}: after {time.time() - t0:.2f}s")
            return True
        page.wait_for_timeout(250)
    print(f"  {label}: NOT within {limit}s")
    return False


def rail_text(page):
    r = page.get_by_test_id(f"rail-conversation-{CONV}")
    return norm(r.text_content()) if r.count() else None


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(6000)
    sse = page.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('/events')).map(e => e.name.split('?')[0])")
    print("SSE resources:", sse[:3])
    print("DB before:", row(CONV))
    main = page.locator("main").first
    print("notice on archived conversation:", norm(main.text_content())[:200])
    j.shot(page, "rail_00_archived_open")

    # 1. unarchive from the rail
    page.get_by_test_id(f"agent-menu-{P}-alpha").click()
    page.wait_for_timeout(400)
    page.get_by_role("menuitem", name="Show archived").first.click()
    page.wait_for_timeout(800)
    arch = page.get_by_test_id(f"rail-archived-{CONV}")
    print("archived row:", norm(arch.text_content()) if arch.count() else None)
    arch.hover()
    page.get_by_test_id(f"rail-archived-{CONV}-menu").click()
    page.wait_for_timeout(300)
    items = page.get_by_role("menuitem")
    print("archived row menu:", [norm(t) for t in items.all_text_contents()])
    page.get_by_test_id(f"rail-archived-{CONV}-menu-unarchive").click()
    until(page, "DB unarchived", lambda: row(CONV)["lifecycle"] == "open", 10)
    until(page, "rail shows it open", lambda: rail_text(page) is not None)
    j.shot(page, "rail_01_unarchived")

    # 2. rename from the header
    new = f"Header rename {time.strftime('%H%M%S')}"
    page.locator("[data-slot=convbar-title]").click()
    inp = page.get_by_label("Conversation title")
    inp.fill(new)
    inp.press("Enter")
    until(page, "DB renamed", lambda: row(CONV)["title"] == new, 10)
    until(page, "header renamed", lambda: new in norm(page.locator("[data-slot=convbar-title]").text_content()), 10)
    until(page, "rail renamed", lambda: new in (rail_text(page) or ""))
    print("  rail now:", rail_text(page))

    # 3. archive from the header
    page.get_by_test_id("conversation-more").click()
    page.wait_for_timeout(300)
    page.get_by_role("menuitem", name="Archive conversation").click()
    until(page, "DB archived", lambda: row(CONV)["lifecycle"] == "archived", 10)
    until(page, "rail drops it from the open list", lambda: rail_text(page) is None)
    j.shot(page, "rail_02_after_header_archive")
    print("  composer:", norm(page.locator("[data-slot=composer]").last.text_content())[:200] if page.locator("[data-slot=composer]").count() else None)
    print("  main top:", norm(main.text_content())[:300])
    print("console errors:", j.errors[:5])
