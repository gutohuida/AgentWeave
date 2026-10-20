"""Jobs & loops x Flows x Resilience sweep 2026-10-20, UI (real Chromium, served bundle, :8160).

py -3.11 scripts/drive/s1020_l_ui.py
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_l_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=150, after=350):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before): i + after] for i in hits[:3])


def main():
  with Judge("s1020-l", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=jobs")
    page.wait_for_timeout(5000)
    t = body(page)
    print("JOBS fired:", around(t, "fired", 80, 80))
    print("JOBS failed:", around(t, "failed", 200, 200))
    print("JOBS loop A:", around(t, "loop A", 50, 400))
    j.shot(page, "jobs-1", full_page=True)
    exp = page.locator('[aria-label="Expand job details"]')
    print("expanders", exp.count())
    for i in reversed(range(exp.count())):
        try:
            exp.nth(i).click(timeout=3000)
        except Exception as e:
            print("expand", i, type(e).__name__)
        page.wait_for_timeout(400)
    page.wait_for_timeout(1500)
    t = body(page)
    print("JOBS expanded failed:", around(t, "failed", 250, 250))
    print("JOBS expanded loop D:", around(t, "loop D", 50, 600))
    j.shot(page, "jobs-2-expanded", full_page=True)
    runs = page.get_by_role("button", name=re.compile(r"^Run$", re.I))
    print("run buttons", runs.count(), [runs.nth(i).is_enabled() for i in range(runs.count())])

    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    page.get_by_text("Write D.txt").first.click()
    page.wait_for_timeout(2500)
    t = body(page)
    print("DRAWER D.txt:", around(t, "git repository", 300, 300))
    print("DRAWER retry:", around(t, "Retry", 100, 100))
    j.shot(page, "task-d-drawer", full_page=True)

    page = j.page(P, mode="light", query="agent=alpha&conversation=conv-51d3e850125f")
    page.wait_for_timeout(5000)
    t = body(page)
    print("CONV interrupted:", around(t, "interrupt", 200, 300))
    print("CONV restart:", around(t, "restart", 200, 300))
    j.shot(page, "alpha-interrupted", full_page=True)


if __name__ == "__main__":
    main()
