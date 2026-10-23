"""Keyboard & dialogs, 2026-10-23: the Spec page's dialogs, keyboard only.

On the approved change `sapphire-pegasus` and the capability `kb-capability`:
  primary   the header's primary button (Start flow / Fold) -> Enter
  menu      More actions -> each item that opens a dialog (Start flow, Archive, Delete, Retire):
            where focus is 200 ms and 1500 ms after, one Escape, where focus goes after

    py -3.11 scripts/drive/s1023_kb_spec.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, shot, tab_cycle  # noqa: E402

CHANGE = "spec/changes/sapphire-pegasus/spec.json"
CAP = "spec/capabilities/kb-capability/spec.json"


def open_doc(page, path):
    t = page.get_by_test_id(f"spec-list-row-{path}")
    t.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)


def report(page, label, opener):
    print(f"  {label}: +200ms", fmt(active(page)), dialogs(page))
    page.wait_for_timeout(1300)
    a = active(page)
    print(f"  {label}: +1500ms", fmt(a))
    shot(page, f"spec_{label}")
    stops, escaped = tab_cycle(page, 10)
    print(f"  {label}: Tab x10 escaped:", escaped[:2])
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    print(f"  {label}: after Escape", fmt(active(page)), dialogs(page), "opener was", opener)


def via_menu(page, item_testid, label):
    more = page.get_by_test_id("spec-more-actions")
    more.focus()
    opener = fmt(active(page))
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    items = page.evaluate(
        "() => [...document.querySelectorAll('[role=menuitem]')].map(e => e.getAttribute('data-testid') || e.textContent.trim())"
    )
    print(f"  menu items: {items}")
    if item_testid not in items:
        print(f"  {label}: not offered")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return
    for _ in range(len(items) + 1):
        if active(page).get("testid") == item_testid:
            break
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(80)
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    report(page, label, opener)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser, "tab=spec")
    page.wait_for_timeout(1000)
    print("== change")
    open_doc(page, CHANGE)
    btns = page.evaluate(
        "() => [...document.querySelectorAll('[data-testid=spec-start-flow],[data-testid=fold-open]')].map(e => e.getAttribute('data-testid'))"
    )
    print("  primary buttons:", btns)
    for tid in btns:
        b = page.get_by_test_id(tid)
        b.focus()
        opener = fmt(active(page))
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        report(page, f"primary_{tid}", opener)
    for tid, label in (("spec-start-flow", "menu_start_flow"), ("spec-archive", "menu_archive"), ("spec-delete", "menu_delete")):
        via_menu(page, tid, label)
    print("== capability")
    open_doc(page, CAP)
    via_menu(page, "spec-retire-capability", "menu_retire")
    print("errors:", page.errors[:4])
    print("writes:", page.writes)
    browser.close()
