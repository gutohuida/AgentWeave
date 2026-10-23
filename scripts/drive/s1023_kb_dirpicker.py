"""Keyboard & dialogs, 2026-10-23: the in-app folder browser inside Add project (never Browse...,
the native dialog). Enter on "Browse within the Hub instead", then one Escape: one layer?

    py -3.11 scripts/drive/s1023_kb_dirpicker.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, shot, step  # noqa: E402

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser)
    page.get_by_test_id("add-project").focus()
    step(page, "Enter", "Enter on Add project", wait=800)
    hit = None
    for _ in range(12):
        a = active(page)
        if (a.get("text") or "").startswith("Browse within the Hub"):
            hit = a
            break
        page.keyboard.press("Tab")
        page.wait_for_timeout(80)
    print("in-app browse button:", fmt(hit) if hit else None)
    if hit:
        step(page, "Enter", "Enter on in-app browse", wait=1500)
        print("  layers:", dialogs(page))
        shot(page, "dirpicker_open")
        step(page, "Escape", wait=600)
        print("  layers after one Escape:", dialogs(page))
        step(page, "Escape", wait=600)
        print("  layers after two:", dialogs(page))
    print("writes:", page.writes, "errors:", page.errors[:3])
    browser.close()
