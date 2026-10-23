"""Keyboard & dialogs, 2026-10-23: the Ctrl+K palette, keyboard only.

  a  from a focused rail button: opens, focus in the input, Escape closes, focus back on the button
  b  arrows + Enter open a task; where focus goes
  c  Ctrl+K while the Add-agent dialog is open: what opens, what Tab and Escape do
  d  Ctrl+K inside the composer textarea; Ctrl+Shift+K in a conversation (F948 (2)'s twin)

    py -3.11 scripts/drive/s1023_kb_palette.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, shot, step, tab_cycle  # noqa: E402


def tab_to(page, testid=None, aria=None, limit=40):
    for _ in range(limit):
        page.keyboard.press("Tab")
        page.wait_for_timeout(90)
        a = active(page)
        if (testid and (a.get("testid") or "").startswith(testid)) or (aria and aria in (a.get("aria") or "")):
            return a
    raise SystemExit(f"never reached {testid or aria}")


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    print("== a: from a rail button")
    page = open_page(browser)
    tab_to(page, testid="rail-agent-")
    print("  opener:", fmt(active(page)))
    a = step(page, "Control+k")
    print("  layers:", dialogs(page))
    step(page, "Escape")
    print("  layers:", dialogs(page))

    print("== b: arrows + Enter")
    step(page, "Control+k")
    page.keyboard.type("Kb task two")
    page.wait_for_timeout(400)
    sel = page.evaluate("() => (document.querySelector('[cmdk-item][data-selected=true]') || {}).textContent")
    print("  selected:", sel)
    step(page, "ArrowDown")
    sel2 = page.evaluate("() => (document.querySelector('[cmdk-item][data-selected=true]') || {}).textContent")
    print("  after ArrowDown:", sel2)
    step(page, "ArrowUp")
    a = step(page, "Enter", wait=1200)
    print("  url:", page.url, "layers:", dialogs(page))
    shot(page, "palette_b_after_enter")
    step(page, "Escape", wait=600)
    print("  url after Escape:", page.url, "layers:", dialogs(page))
    page.context.close()

    print("== c: Ctrl+K over the Add-agent dialog")
    page = open_page(browser)
    tab_to(page, testid="rail-add-agent-")
    step(page, "Enter", "Enter on Add agent", wait=800)
    print("  layers:", dialogs(page))
    step(page, "Control+k", wait=600)
    print("  layers:", dialogs(page))
    shot(page, "palette_c_over_dialog")
    stops, escaped = tab_cycle(page, 4)
    print("  Tab x4 in palette:", [fmt(s) for s in stops])
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("  after one Escape:", dialogs(page), fmt(active(page)))
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("  after two Escapes:", dialogs(page), fmt(active(page)))
    page.context.close()

    print("== d: Ctrl+K in the composer")
    page = open_page(browser, query="agent=alpha")
    page.wait_for_timeout(1500)
    ta = page.locator("textarea").first
    ta.focus()
    page.keyboard.type("draft text ")
    print("  composer:", fmt(active(page)))
    step(page, "Control+k")
    print("  layers:", dialogs(page))
    step(page, "Escape")
    print("  composer value:", repr(ta.input_value()))
    step(page, "Control+Shift+k", wait=700)
    print("  Ctrl+Shift+K layers:", dialogs(page))
    shot(page, "palette_d_ctrl_shift_k")
    step(page, "Escape")
    print("  layers after one Escape:", dialogs(page))
    step(page, "Escape")
    print("  layers after two:", dialogs(page))
    print("errors:", page.errors[:5])
    browser.close()
