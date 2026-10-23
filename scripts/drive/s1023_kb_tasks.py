"""Keyboard & dialogs, 2026-10-23: the task drawer, keyboard only.

  open   the card's open button -> Enter: focus in the drawer; Tab trapped; Escape closes, focus back
  rename the title: Enter saves once (count PATCHes), Escape cancels without closing the drawer
  delete Delete -> the inline confirm: where focus goes; one Escape (confirm only, or the drawer too?)
  status the status menu inside the drawer: Escape closes only the menu
  narrow the same at 760 px wide

    py -3.11 scripts/drive/s1023_kb_tasks.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import active, dialogs, fmt, open_page, req, B, shot, step, tab_cycle  # noqa: E402

status, tasks = req("GET", f"{B}/tasks")
items = tasks.get("tasks", tasks) if isinstance(tasks, dict) else tasks
T = next(t["id"] for t in items if t["title"].startswith("Kb task one"))
print("task", T)


def tab_until(page, pred, limit=30):
    for _ in range(limit):
        page.keyboard.press("Tab")
        page.wait_for_timeout(70)
        a = active(page)
        if pred(a):
            return a
    return None


def details(page):
    a = tab_until(page, lambda a: a.get("text") == "Details" and a.get("inDialog") is not None)
    print("  Details toggle reached by Tab:", bool(a))
    step(page, "Enter", "Enter on Details", wait=600)


def drawer(width):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = open_page(browser, "tab=tasks", width=width)
        page.wait_for_timeout(1500)
        print(f"===== width {width}")
        opener = page.get_by_test_id(f"task-open-{T}")
        opener.focus()
        o = active(page)
        print("opener:", fmt(o))
        step(page, "Enter", "Enter on card", wait=900)
        print("layers:", dialogs(page))
        shot(page, f"task_drawer_open_{width}")
        stops, escaped = tab_cycle(page, 30)
        print("Tab x30 escaped:", escaped[:3])
        a = step(page, "Escape", wait=700)
        print("layers after Escape:", dialogs(page), "back on opener:", a.get("testid") == o.get("testid"))

        print("-- rename")
        opener.focus()
        step(page, "Enter", wait=900)
        title = page.get_by_test_id(f"task-drawer-title-{T}")
        print("title tabIndex:", title.evaluate("e => [e.tagName, e.tabIndex, e.getAttribute('role')]"))
        reached = False
        for _ in range(30):
            page.keyboard.press("Tab")
            page.wait_for_timeout(60)
            if page.evaluate("() => !!document.activeElement.closest('[data-testid^=task-drawer-title]')"):
                reached = True
                break
        print("title reached by Tab:", reached, "(not reachable: a click is the only way to rename)")
        title.click()
        page.wait_for_timeout(300)
        print("  after click on title ->", fmt(active(page)))
        page.keyboard.press("Control+a")
        page.keyboard.type("Kb task one renamed")
        before = len(page.writes)
        step(page, "Enter", "Enter in title input", wait=900)
        print("writes on Enter:", page.writes[before:])
        print("layers:", dialogs(page))
        page.get_by_test_id(f"task-drawer-title-{T}").click()
        page.wait_for_timeout(300)
        page.keyboard.type(" xx")
        step(page, "Escape", "Escape in title input", wait=600)
        print("layers after Escape in input:", dialogs(page))
        step(page, "Escape", "second Escape", wait=600)
        print("layers:", dialogs(page))

        print("-- delete confirm")
        opener = page.get_by_test_id(f"task-open-{T}")
        opener.focus()
        step(page, "Enter", wait=900)
        details(page)
        a = tab_until(page, lambda a: (a.get("testid") or "").startswith("task-delete-"))
        print("  Delete reached by Tab:", fmt(a) if a else None)
        step(page, "Enter", "Enter on Delete", wait=600)
        conf = page.get_by_test_id(f"task-delete-confirm-{T}")
        print("inline confirm visible:", conf.is_visible())
        shot(page, f"task_delete_confirm_{width}")
        step(page, "Escape", "Escape with confirm open", wait=700)
        print("layers:", dialogs(page), "confirm visible:", conf.count() and conf.is_visible())
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        print("-- status menu in drawer")
        opener = page.get_by_test_id(f"task-open-{T}")
        opener.focus()
        step(page, "Enter", wait=900)
        details(page)
        found = None
        for _ in range(30):
            page.keyboard.press("Tab")
            page.wait_for_timeout(80)
            a = active(page)
            if a.get("inDialog") is not None and (a.get("testid") or "").startswith("task-status-menu"):
                found = a
                break
        print("status control:", fmt(found) if found else None)
        if found:
            step(page, "Enter", "Enter on status", wait=600)
            print("menus:", page.evaluate("() => [...document.querySelectorAll('[role=menu]')].length"))
            step(page, "Escape", "Escape in menu", wait=600)
            print("menus:", page.evaluate("() => [...document.querySelectorAll('[role=menu]')].length"), "layers:", dialogs(page))
        print("errors:", page.errors[:4])
        browser.close()


drawer(1440)
drawer(760)
