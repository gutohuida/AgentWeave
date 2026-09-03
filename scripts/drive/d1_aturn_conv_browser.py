"""D-1: open a *named* conversation in the served bundle and read its terminal line.

The point is the seam: the timeline route that supplies `runs` is scoped to the **agent** and
capped at 50 events, while the conversation the operator is reading is scoped to the
**conversation**. Unrelated work in other conversations can therefore move the window past this
conversation's run.

    AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_aturn_conv_browser.py <agent> <conv-id-prefix>
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
PROJ = os.environ["AW_PROJECT"]
AGENT, NEEDLE = sys.argv[1], sys.argv[2]
SHOT = os.environ.get("SHOT")

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1500, "height": 1000})
    page.add_init_script(SEED)
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # Expand the agent in the sidebar to reveal its conversations.
    row = page.locator(f"text={AGENT}").first
    row.click()
    page.wait_for_timeout(1500)
    rail = page.locator("[aria-label='Switch to recent conversations']")
    print(f"--- recent-conversations rail toggle present: {rail.count()}")
    if rail.count():
        rail.first.click()
        page.wait_for_timeout(2000)
    body = page.inner_text("body")
    print("--- sidebar after expand (first 900 chars) ---")
    print(body[:900])
    hit = page.locator(f"text={NEEDLE}").first
    print(f"--- looking for {NEEDLE!r}: count={page.locator(f'text={NEEDLE}').count()}")
    if page.locator(f"text={NEEDLE}").count():
        hit.click()
        page.wait_for_timeout(3000)
    body = page.inner_text("body")
    counts = {L: body.count(L) for L in ("Turn failed", "Turn stopped", "Turn interrupted")}
    print(f"--- terminal labels: {counts}")
    print(f"--- turn boundaries: {page.locator('[data-turn-boundary]').count()}")
    w = page.locator("[data-testid='turn-worked-for']")
    print(f"--- stat lines: {w.count()} -> {[w.nth(i).inner_text() for i in range(w.count())]}")
    if SHOT:
        page.screenshot(path=SHOT)
        print(f"--- screenshot {SHOT}")
    print("--- conversation text ---")
    print(body[:2000])
    b.close()
