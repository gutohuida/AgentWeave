"""Keyboard & dialogs, 2026-10-23: Escape on the composer's completion popups (`@file`, `/`,
`$skill`) in an existing conversation: one Escape closes the popup only; the draft is kept; the
conversation stays.

    py -3.11 scripts/drive/s1023_kb_composer.py <conversation-id>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, shot  # noqa: E402

CONV = sys.argv[1]


def popups(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('[role=listbox],[role=menu],[data-radix-popper-content-wrapper]')]"
        ".filter(e => e.offsetParent !== null).length"
    )


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser, f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(1500)
    ta = page.locator("textarea").first
    for trigger in ("@", "/", "$"):
        ta.focus()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        page.keyboard.type(f"draft {trigger}")
        page.wait_for_timeout(900)
        n = popups(page)
        shot(page, f"composer_popup_{'at' if trigger == '@' else 'slash' if trigger == '/' else 'dollar'}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        print(f"{trigger!r}: popups open={n} -> after Escape popups={popups(page)}; focus {fmt(active(page))};"
              f" draft {ta.input_value()!r}; url still conv: {CONV in page.url}; layers {dialogs(page)}")
    print("errors:", page.errors[:3])
    browser.close()
