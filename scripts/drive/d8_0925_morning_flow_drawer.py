"""Morning drive: the task drawer's history for a two-task FLOW (job kind flow), matching
`a-flows-own-moves-are-recorded-as-the-flows` task 3.2. Pattern copied from last night's
`d8_0925_night_drive3.py`, which drove a LOOP's drawer; this one opens both of a flow's tasks.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ["AW_HUB"]
KEY = require_key()
PROJ = os.environ["AW_PROJECT"]
if ":8000" in HUB or ":8010" in HUB:
    sys.exit("refusing")
TITLES = ["drive5 task alpha", "drive5 task beta"]
SEED = (
    f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, "
    f"hubUrl: {HUB!r}}})); localStorage.setItem('agentweave-selected-project', {PROJ!r});"
)
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1500, "height": 1100})
    page.add_init_script(SEED)
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    for name in ("Tasks", "Board"):
        link = page.get_by_role("link", name=name)
        btn = page.get_by_role("button", name=name)
        if link.count():
            link.first.click()
            break
        if btn.count():
            btn.first.click()
            break
    page.wait_for_timeout(2000)
    for title in TITLES:
        print(f"\n=== {title} ===")
        card = page.locator(f"text={title}")
        print("task cards:", card.count())
        if not card.count():
            continue
        card.first.click()
        page.wait_for_timeout(2000)
        body = page.inner_text("body")
        moved_lines = [ln for ln in body.splitlines() if "moved" in ln.lower()]
        print("moved lines:", moved_lines[:10])
        safe = title.replace(" ", "_")
        page.screenshot(path=f"testbed/scratch/drawer0925morning_{safe}.png", full_page=True)
        if not moved_lines:
            print(body[:1200])
        # Close the drawer (Escape) before opening the next card.
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    b.close()
