"""Keyboard & dialogs, 2026-10-23: a conversation, keyboard only.

  panel    at 900 px: More conversation actions -> Show side panel (a drawer at this width): focus in
           the drawer, Tab trapped, Escape closes it, focus to "Panel" (its own trigger)
  shiftk   Ctrl+Shift+K in a conversation (document search) -- one layer or two?
  archive  More -> Archive conversation (no confirm; a toast with Undo): where focus goes, and can
           the keyboard reach Undo? Then Undo by keyboard, if reachable.

    py -3.11 scripts/drive/s1023_kb_conv.py <conversation-id> [panel|shiftk|archive ...]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, q, shot, step, tab_cycle  # noqa: E402

CONV = sys.argv[1]
WHICH = sys.argv[2:] or ["panel", "shiftk", "archive"]


def menu_pick(page, label):
    more = page.get_by_test_id("conversation-more")
    more.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    items = page.evaluate("() => [...document.querySelectorAll('[role=menuitem]')].map(e => e.textContent.trim())")
    print("  menu:", items)
    for _ in range(len(items) + 1):
        if label in (active(page).get("text") or ""):
            break
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(70)
    print("  on item:", fmt(active(page)))
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    if "panel" in WHICH:
        print("== panel at 900")
        page = open_page(browser, f"agent=alpha&conversation={CONV}", width=900)
        page.wait_for_timeout(1500)
        menu_pick(page, "side panel")
        print("  +250ms:", fmt(active(page)), dialogs(page))
        page.wait_for_timeout(1200)
        a = active(page)
        print("  +1450ms:", fmt(a), dialogs(page))
        shot(page, "conv_panel_drawer_900")
        stops, escaped = tab_cycle(page, 15)
        print("  Tab x15 escaped:", escaped[:3])
        step(page, "Escape", wait=700)
        print("  layers:", dialogs(page))
        trig = page.get_by_test_id("conversation-open-document")
        if trig.count():
            trig.focus()
            step(page, "Enter", "Enter on Panel trigger", wait=900)
            print("  layers:", dialogs(page))
            stops, escaped = tab_cycle(page, 15)
            print("  Tab x15 escaped:", escaped[:3])
            step(page, "Escape", wait=700)
            print("  layers:", dialogs(page))
        page.context.close()
    if "shiftk" in WHICH:
        print("== Ctrl+Shift+K in a conversation")
        page = open_page(browser, f"agent=alpha&conversation={CONV}")
        page.wait_for_timeout(1500)
        page.get_by_test_id("conversation-more").focus()
        step(page, "Control+Shift+k", wait=800)
        print("  layers:", dialogs(page))
        shot(page, "conv_ctrl_shift_k")
        step(page, "Escape", wait=500)
        print("  layers after one Escape:", dialogs(page))
        step(page, "Escape", wait=500)
        print("  layers after two:", dialogs(page))
        page.context.close()
    if "archive" in WHICH:
        print("== archive conversation")
        page = open_page(browser, f"agent=alpha&conversation={CONV}")
        page.wait_for_timeout(1500)
        menu_pick(page, "Archive conversation")
        page.wait_for_timeout(1200)
        print("  after archive:", fmt(active(page)), "url:", page.url)
        shot(page, "conv_archived_toast")
        undo = page.get_by_role("button", name="Undo")
        print("  Undo visible:", undo.count() and undo.first.is_visible())
        reached = None
        for i in range(60):
            page.keyboard.press("Tab")
            page.wait_for_timeout(50)
            a = active(page)
            if (a.get("text") or "") == "Undo":
                reached = i + 1
                break
        print("  Undo reached by Tab after", reached, "presses")
        if reached:
            step(page, "Enter", "Enter on Undo", wait=1200)
        print("  archived now:", q("select * from conversations where id=?", CONV))
        page.context.close()
    if "sheets" in WHICH:
        print("== Checkpoints sheet (menu item) and the turn's trace drawer")
        page = open_page(browser, f"agent=alpha&conversation={CONV}")
        page.wait_for_timeout(1500)
        menu_pick(page, "Checkpoints")
        print("  +250ms:", fmt(active(page)), dialogs(page))
        page.wait_for_timeout(1200)
        print("  +1450ms:", fmt(active(page)), dialogs(page))
        shot(page, "conv_checkpoints_sheet")
        stops, escaped = tab_cycle(page, 10)
        print("  Tab x10 escaped:", escaped[:2])
        step(page, "Escape", wait=600)
        print("  layers:", dialogs(page))
        tr = page.get_by_role("button", name="trace").first
        if tr.count():
            tr.focus()
            o = fmt(active(page))
            step(page, "Enter", "Enter on trace", wait=1200)
            print("  layers:", dialogs(page))
            shot(page, "conv_trace_drawer")
            stops, escaped = tab_cycle(page, 10)
            print("  Tab x10 escaped:", escaped[:2])
            step(page, "Escape", wait=700)
            print("  layers:", dialogs(page), "opener was", o)
        page.context.close()
    browser.close()
