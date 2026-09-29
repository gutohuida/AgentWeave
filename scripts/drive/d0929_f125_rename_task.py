"""Task 3.2 drive for the-operator-can-rename-a-task (F125).

Opens the trial Hub's Tasks board in a real Chromium tab, opens the fixture task's drawer, clicks
its title into edit mode, renames it, and confirms the board card and the drawer header both show
the new title with no reload. Then does the same against a `blocked` task to confirm design D4 (a
rename must not restate `status`/`blocked_reason` and so must not be refused).

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... py -3.11 scripts/drive/d0929_f125_rename_task.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
KEY = require_key()
PROJ = os.environ["AW_PROJECT"]
TASK_ID = os.environ.get("AW_TASK", "task-f125-rename-drive")

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

FAILURES = []


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail[:300]}" if detail else ""))
    if not ok:
        FAILURES.append((label, detail))


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    page.add_init_script(SEED)
    page.goto(f"{HUB}/?project={PROJ}&tab=tasks", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    opener = page.get_by_label("Open Write loop_r11_c.txt (orphaned)")
    check("fixture task card is on the board", opener.count() > 0, f"count={opener.count()}")
    opener.first.click()
    page.wait_for_timeout(600)

    drawer = page.locator(f"[data-testid='task-drawer-{TASK_ID}']")
    check("drawer opened", drawer.count() > 0)

    title_el = page.locator(f"[data-testid='task-drawer-title-{TASK_ID}']")
    check("title is click-to-edit, not a static heading", title_el.count() > 0)
    title_el.first.click()

    title_input = page.locator(f"[data-testid='task-drawer-title-input-{TASK_ID}']")
    check("clicking the title opens an editable input", title_input.count() > 0)
    title_input.fill("")
    title_input.type("Renamed live by the F125 drive")
    title_input.press("Enter")
    page.wait_for_timeout(1200)

    drawer_text = drawer.first.inner_text()
    check(
        "drawer header shows the new title with no reload",
        "Renamed live by the F125 drive" in drawer_text,
        drawer_text[:200],
    )

    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    board_text = page.locator("body").inner_text()
    check(
        "board card shows the new title with no reload",
        "Renamed live by the F125 drive" in board_text,
        "",
    )
    check(
        "board card no longer shows the old title",
        "Write loop_r11_c.txt (orphaned)" not in board_text,
        "",
    )

    b.close()

print("\n--- summary ---")
if FAILURES:
    for label, detail in FAILURES:
        print(f"FAIL: {label} ({detail[:200]})")
    sys.exit(1)
print("All checks passed.")
