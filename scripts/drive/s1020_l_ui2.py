"""Sweep 2026-10-20 :8160 UI, part 2: the archived Codex loop's failed firings on the Jobs tab."""

import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_l_lib import P, e2e  # noqa: E402
from s1020_l_ui import around, body  # noqa: E402
from uiharness import Judge  # noqa: E402

with Judge("s1020-l2", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=jobs")
    page.wait_for_timeout(4000)
    page.get_by_text(re.compile(r"^archived", re.I)).first.click()
    page.wait_for_timeout(2000)
    exp = page.locator('[aria-label="Expand job details"]')
    for i in reversed(range(exp.count())):
        try:
            exp.nth(i).click(timeout=3000)
        except Exception:
            pass
    page.wait_for_timeout(1500)
    t = body(page)
    print("ARCHIVED loop E:", around(t, "loop E", 50, 700))
    j.shot(page, "jobs-archived", full_page=True)
