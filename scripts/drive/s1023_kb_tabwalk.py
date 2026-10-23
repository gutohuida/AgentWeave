"""Keyboard & dialogs, 2026-10-23: walk the shell's tab order from a fresh load, printing every stop
and whether it draws a focus ring (outline or box-shadow), then Ctrl+K from the body.

    py -3.11 scripts/drive/s1023_kb_tabwalk.py [count]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, fmt, open_page, shot  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 45

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser)
    print("start:", fmt(active(page)))
    ringless = []
    for i in range(N):
        page.keyboard.press("Tab")
        page.wait_for_timeout(120)
        a = active(page)
        ring = a.get("outline") or a.get("shadow")
        print(f"{i:2} {fmt(a)}  ring={ring}")
        if not ring:
            ringless.append(fmt(a))
        if i in (3, 12, 25):
            shot(page, f"tabwalk_{i}")
    print("STOPS WITHOUT A RING:", len(ringless))
    for r in ringless:
        print("   ", r)
    print("errors:", page.errors[:5])
    browser.close()
