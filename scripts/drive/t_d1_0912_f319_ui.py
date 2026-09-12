"""D-1 2026-09-12, priority 3: what the operator SEES for a task F319 stranded.

Opens the served bundle as an operator, goes to the task board, and reads what it says about the
tasks `t_d1_0912_f319_reach.py` left behind: B1/B2 (`under_review`, held, no run), A (`completed`,
held by the refused reviewer) and C (restaffed, entry never delivered -- F320).

    AW_HUB=http://127.0.0.1:8016 AW_KEY=... AW_PROJECT=proj-... SHOTDIR=... \
        py -3.11 scripts/drive/t_d1_0912_f319_ui.py
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
SHOTDIR = os.environ.get("SHOTDIR", ".")

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1100})
    page.add_init_script(SEED)
    console = []
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:300]))
    requests = []
    page.on(
        "request", lambda r: requests.append(f"{r.method} {r.url}") if r.method != "GET" else None
    )
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(SHOTDIR, "f319-home.png"))
    for name in ("Tasks", "Board"):
        loc = page.get_by_role("button", name=name)
        if not loc.count():
            loc = page.get_by_text(name, exact=True)
        if loc.count():
            loc.first.click()
            print(f"clicked {name!r}")
            break
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(SHOTDIR, "f319-board.png"), full_page=True)
    body = page.inner_text("body")
    for title in ("B1 b2", "B2 b2", "A a1", "C a1"):
        i = body.find(title)
        print(f"--- {title!r}: {'present' if i >= 0 else 'ABSENT'}")
        if i >= 0:
            print("    " + body[max(0, i - 80) : i + 240].replace("\n", " | "))
    loc = page.get_by_text("B1 b2", exact=True)
    if loc.count():
        loc.first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTDIR, "f319-b1-detail.png"), full_page=True)
        print("--- B1 detail body (head):")
        print(page.inner_text("body")[:2500])
    print("--- non-GET requests the page made:")
    for r in requests:
        print("   ", r)
    for line in console:
        print("   ", line)
    b.close()
