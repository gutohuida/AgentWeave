"""Conversations & composer, 2026-10-23: what the Ctrl+K palette finds for a conversation's title,
and what the rail's "Show archived (N)" says on a fresh load after an archive.

    py -3.11 scripts/drive/s1023_cv_palette.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="agent=beta")
    page.wait_for_timeout(6000)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(1000)
    lst = page.locator("[cmdk-list]")
    print("EMPTY QUERY:", norm(lst.text_content())[:800])
    for needle in ("beta", "say", "say hi", "Hello", "Renamed", "caf", "café", "silver", "Composer"):
        inp = page.locator("[cmdk-input]")
        inp.fill(needle)
        page.wait_for_timeout(700)
        print(f"{needle!r:12} ->", norm(lst.text_content())[:300])
    page.locator("[cmdk-input]").fill("say hi")
    page.wait_for_timeout(500)
    j.shot(page, "palette_say_hi")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    menu = page.get_by_test_id(f"agent-menu-{P}-alpha")
    menu.click()
    page.wait_for_timeout(500)
    print("ALPHA MENU:", [norm(t) for t in page.get_by_role("menuitem").all_text_contents()])
    j.shot(page, "rail_alpha_menu")
    print("console errors:", j.errors[:5])
