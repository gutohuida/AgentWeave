"""Drive step for an-estimate-that-misses-turns-says-so, tasks.md 3.1.

On the trial Hub `:8010` (per the task's explicit instruction, not a fresh drive Hub), project
proj-a7d532f5141f carries one `unavailable` turn (a real crash-reconciled run, produced by killing
the Hub process mid-run and restarting it) and three `measured` claude-haiku turns. Reads the
Budgets tab's rendered accounting label against the served bundle (no dev server).

Run: py -3.11 scripts/drive/d0928_unpriced_turns_label.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = "http://127.0.0.1:8010"
KEY = os.environ["AW_KEY"]
P = "proj-a7d532f5141f"

SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); "
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.add_init_script(SEED)

    pg.goto(HUB + f"/?project={P}&tab=budgets", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    body_text = pg.locator("body").inner_text()
    print("== Budgets tab body text contains 'excludes'? ==", "excludes" in body_text)
    print("== Budgets tab body text contains 'unavailable'/'Rate-limit'? ==",
          "Rate-limit" in body_text, "unavailable" in body_text.lower())
    # Print any line mentioning the estimate/allowance/excludes so the exact wording is on record.
    for line in body_text.splitlines():
        low = line.lower()
        if any(k in low for k in ("excludes", "estimate", "allowance", "unavailable", "usage")):
            print("LINE:", repr(line))
    pg.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "unpriced_budgets_tab.png"))
    b.close()
