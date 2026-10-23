"""Keyboard & dialogs, 2026-10-23: Project instructions' clear-confirm, keyboard only.

Type instructions, Save (Tab to it, Enter), empty the editor, Save -> the confirm. Where focus lands
on open, one Escape, where focus goes; then again, and confirm with Clear (F941 (b) recheck).

    py -3.11 scripts/drive/s1023_kb_instructions.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, shot, step, tab_cycle  # noqa: E402


def to_save(page):
    # Save sits above the editor (OtherSettings.tsx: the header row), so it is behind Shift+Tab.
    for _ in range(10):
        page.keyboard.press("Shift+Tab")
        page.wait_for_timeout(80)
        a = active(page)
        print("    tab:", fmt(a))
        if a.get("text") == "Save":
            return True
    return False


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser, "tab=environment&section=instructions")
    ta = page.locator("textarea").first
    ta.wait_for(state="visible")
    page.wait_for_timeout(1500)
    ta.focus()
    print("editor:", fmt(active(page)))
    page.keyboard.press("Control+a")
    page.keyboard.type("Always answer in one sentence.")
    print("Save reached:", to_save(page))
    before = len(page.writes)
    step(page, "Enter", "Enter on Save", wait=1200)
    print("writes:", page.writes[before:])
    for attempt in ("escape", "confirm"):
        ta.focus()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        print("Save reached:", to_save(page))
        o = active(page)
        step(page, "Enter", "Enter on Save (empty)", wait=800)
        print("  layers:", dialogs(page))
        shot(page, f"instructions_clear_{attempt}")
        stops, escaped = tab_cycle(page, 6)
        print("  Tab x6 escaped:", escaped[:2], "stops:", sorted({fmt(s) for s in stops}))
        if attempt == "escape":
            a = step(page, "Escape", wait=600)
            print("  layers:", dialogs(page), "back on Save:", a.get("text") == o.get("text"))
            print("  editor value:", repr(ta.input_value()))
        else:
            for _ in range(6):
                if "Clear" in (active(page).get("text") or ""):
                    break
                page.keyboard.press("Tab")
                page.wait_for_timeout(80)
            before = len(page.writes)
            step(page, "Enter", "Enter on Clear", wait=1200)
            print("  writes:", page.writes[before:], "layers:", dialogs(page))
    print("errors:", page.errors[:3])
    browser.close()
