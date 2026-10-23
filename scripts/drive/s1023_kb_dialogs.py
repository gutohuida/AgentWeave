"""Keyboard & dialogs, 2026-10-23: every dialog reachable on a fresh project, keyboard only.

For each: focus the opener, press Enter, then read `document.activeElement`
  (a) where focus lands on open (a confirm should land on Cancel, never the destructive button)
  (b) 12 Tabs and 12 Shift+Tabs: any stop outside the dialog
  (c) one Escape: how many layers close
  (d) where focus is after the close (the opener?)
  (e) re-open, Tab to the dismiss button, Enter: it closes and does not re-open

    py -3.11 scripts/drive/s1023_kb_dialogs.py [name ...]
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import P, active, dialogs, fmt, open_page, shot, tab_cycle  # noqa: E402

RESULTS = []


def same(a, b):
    return all(a.get(k) == b.get(k) for k in ("tag", "testid", "aria", "id", "text"))


def check(page, name, opener, dismiss=r"^(Cancel|Keep .*|Close)$", confirm=False, key="Enter"):
    print(f"== {name}")
    opener.scroll_into_view_if_needed()
    opener.focus()
    page.wait_for_timeout(200)
    o = active(page)
    print("  opener:", fmt(o))
    base = len(dialogs(page))
    page.keyboard.press(key)
    page.wait_for_timeout(900)
    a1 = active(page)
    layers = dialogs(page)
    print("  on open:", fmt(a1), "layers:", layers)
    if len(layers) <= base:
        print("  !! nothing opened")
        RESULTS.append((name, "did not open"))
        return
    shot(page, f"dlg_{name}_open")
    notes = []
    if a1.get("inDialog") is None:
        notes.append("focus not in dialog on open")
    if confirm and not re.match(dismiss, a1.get("text") or a1.get("aria") or ""):
        notes.append(f"confirm focus on {a1.get('text') or a1.get('aria')!r}, not Cancel")
    stops, escaped = tab_cycle(page, 12)
    sstops, sescaped = tab_cycle(page, 12, shift=True)
    print("  tab stops:", sorted({fmt(s) for s in stops})[:10])
    if escaped or sescaped:
        notes.append(f"Tab leaves the dialog: {(escaped + sescaped)[:2]}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    after = dialogs(page)
    a2 = active(page)
    print("  after Escape:", fmt(a2), "layers:", after)
    if len(after) != base:
        notes.append(f"one Escape left {len(after)} layers (base {base}): {after}")
    if not same(a2, o):
        notes.append(f"Escape: focus went to {fmt(a2)}")
    # (e) re-open, Tab to the dismiss button, press Enter on it
    if len(after) == base:
        opener.focus()
        page.keyboard.press(key)
        page.wait_for_timeout(800)
        hit = None
        for _ in range(25):
            a = active(page)
            if a.get("inDialog") is not None and re.match(dismiss, a.get("text") or a.get("aria") or ""):
                hit = a
                break
            page.keyboard.press("Tab")
            page.wait_for_timeout(80)
        if hit is None:
            notes.append("no dismiss button reached by Tab")
        else:
            page.keyboard.press("Enter")
            page.wait_for_timeout(700)
            a3 = active(page)
            l3 = dialogs(page)
            print(f"  Enter on {hit.get('text') or hit.get('aria')!r}:", fmt(a3), "layers:", l3)
            if len(l3) != base:
                notes.append(f"Enter on dismiss left {l3}")
            elif not same(a3, o):
                notes.append(f"Enter on dismiss: focus went to {fmt(a3)}")
    print("  RESULT:", notes or "held")
    RESULTS.append((name, notes or "held"))


def btn(page, text):
    return page.get_by_role("button", name=re.compile(text)).first


def run(browser, which):
    if "agent" in which:
        page = open_page(browser)
        check(page, "add-agent", page.get_by_test_id(f"rail-add-agent-{P}"))
        page.context.close()
    if "runner" in which:
        page = open_page(browser, "tab=environment&section=runners")
        check(page, "new-runner", btn(page, r"New runner"))
        check(page, "edit-runner", btn(page, r"^Edit"), dismiss=r"^(Cancel|Close)$")
        page.context.close()
    if "charter" in which:
        page = open_page(browser, "tab=environment&section=charters")
        check(page, "new-charter", btn(page, r"New charter"))
        check(page, "delete-charter", btn(page, r"^Delete"), confirm=True)
        page.context.close()
    if "project" in which:
        page = open_page(browser, "tab=environment&section=settings")
        check(page, "delete-project", btn(page, r"Delete project"), confirm=True)
        page.context.close()
    if "job" in which:
        page = open_page(browser, "tab=jobs")
        check(page, "new-job", btn(page, r"New job"))
        page.context.close()
    if "vault" in which:
        page = open_page(browser, "tab=vault")
        check(page, "vault-add", page.get_by_test_id("vault-upload-open"))
        check(page, "vault-storage", page.get_by_role("button", name="Vault storage"))
        page.context.close()
    if "archive-agent" in which:
        page = open_page(browser, "agent=alpha&settings=identity")
        check(page, "archive-agent", page.get_by_test_id("agent-archive-toggle"), confirm=True)
        page.context.close()
    if "add-project" in which:
        # Open and dismiss only: nothing here presses Browse (the native folder dialog).
        page = open_page(browser)
        check(page, "add-project", page.get_by_test_id("add-project"))
        page.context.close()
    if "checks" in which:
        page = open_page(browser, "tab=environment&section=settings")
        check(page, "project-check", btn(page, r"Add check"))
        page.context.close()


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    which = sys.argv[1:] or ["agent", "runner", "charter", "project", "job", "vault", "archive-agent", "checks"]
    run(browser, which)
    browser.close()
print("\nSUMMARY")
for name, res in RESULTS:
    print(f"  {name:16} {res}")
