"""Keyboard & dialogs, 2026-10-23: Ctrl+K pressed while a dialog (Add agent) or the task drawer is
open. The palette opens on top; then one Tab, typed text, and Escapes -- where does each go?

    py -3.11 scripts/drive/s1023_kb_palette_over.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import P, active, dialogs, fmt, open_page, req, B, shot  # noqa: E402

_s, tasks = req("GET", f"{B}/tasks")
items = tasks.get("tasks", tasks) if isinstance(tasks, dict) else tasks
T = items[0]["id"]


def probe(page, label):
    page.keyboard.press("Control+k")
    page.wait_for_timeout(600)
    print(f"  [{label}] Ctrl+K ->", fmt(active(page)), dialogs(page))
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    print(f"  [{label}] Tab ->", fmt(active(page)), dialogs(page))
    page.keyboard.type("zz")
    page.wait_for_timeout(300)
    vals = page.evaluate(
        "() => [...document.querySelectorAll('input,textarea')].filter(e => (e.value||'').includes('zz')).map(e => (e.getAttribute('aria-label')||e.id||e.placeholder||e.tagName))"
    )
    print(f"  [{label}] typed 'zz' landed in:", vals)
    shot(page, f"palette_over_{label}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print(f"  [{label}] Escape 1 ->", fmt(active(page)), dialogs(page))
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print(f"  [{label}] Escape 2 ->", fmt(active(page)), dialogs(page))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = open_page(browser)
    page.get_by_test_id(f"rail-add-agent-{P}").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("Add agent open:", fmt(active(page)))
    probe(page, "add_agent")
    page.context.close()

    page = open_page(browser, "tab=tasks")
    page.get_by_test_id(f"task-open-{T}").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("drawer open:", fmt(active(page)))
    probe(page, "task_drawer")
    browser.close()
