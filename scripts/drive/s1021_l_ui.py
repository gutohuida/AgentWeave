"""Jobs & loops x Flows x Resilience sweep 2026-10-21, UI (real Chromium, served bundle, :8159).

    AW_P=proj-... py -3.11 scripts/drive/s1021_l_ui.py <step>
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1021_l_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=150, after=350):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before): i + after] for i in hits[:3])


def open_loops(page):
    page.locator('[data-testid="conversation-more"]').first.click()
    page.wait_for_timeout(400)
    page.locator('[data-testid="conversation-toggle-panel"]').first.click()
    page.wait_for_timeout(800)
    if page.locator('[data-testid="loops-index-tab"]').count() == 0:
        page.locator('[data-testid="panel-tab-add"]').first.click()
        page.wait_for_timeout(500)
        page.get_by_role("menuitem", name=re.compile("Loops", re.I)).first.click()
        page.wait_for_timeout(1500)


def loops():
    with Judge("s1021-l", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=beta")
        page.wait_for_timeout(4000)
        open_loops(page)
        idx = page.locator('[data-testid="loops-index-tab"]')
        print("INDEX:", " ".join((idx.text_content() or "").split())[:1500])
        for sel in page.locator('[data-testid^="loops-index-stall-"]').all():
            print("STALL", sel.get_attribute("data-testid"), sel.text_content())
        j.shot(page, "loops-index", full_page=True)
        page.get_by_text("Show archived").first.click()
        page.wait_for_timeout(1500)
        print("INDEX+ARCH:", " ".join((idx.text_content() or "").split())[:1500])
        for lid in sys.argv[2:]:
            page.locator(f'[data-testid="loops-index-row-{lid}"]').first.click()
            page.wait_for_timeout(2500)
            t = " ".join((page.locator('[data-testid="panel-tab-content"]').text_content() or "").split())
            print(f"LOOPTAB {lid}:", t[:2500])
            j.shot(page, f"looptab-{lid}", full_page=True)
        print("ERRORS", j.errors)



def drawer():
    """The task drawer of a task whose integration failed: its note, Try again, and after."""
    tid = sys.argv[2]
    with Judge("s1021-l", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="tab=tasks")
        page.wait_for_timeout(4000)
        page.locator(f'[data-testid="task-open-{tid}"]').first.click()
        page.wait_for_timeout(2500)
        note = page.locator(f'[data-testid="task-integrations-{tid}"]')
        print("NOTE before:", " ".join((note.first.text_content() or "").split()) if note.count() else "<no note>")
        j.shot(page, "drawer-before", full_page=True)
        btn = page.locator(f'[data-testid="task-integration-retry-{tid}"]')
        print("retry buttons", btn.count())
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(5000)
            print("NOTE after:", " ".join((note.first.text_content() or "").split()))
            t = body(page)
            print("TOASTS:", around(t, "merge", 200, 300))
            j.shot(page, "drawer-after", full_page=True)
        print("ERRORS", j.errors)


if __name__ == "__main__":
    globals()[sys.argv[1]]()
