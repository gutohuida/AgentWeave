"""D-1 2026-09-09: open one *named* conversation on screen and read its turn labels.

`d1_aturn_conv_browser.py` selects the conversation by a text needle off the rail preview. That
is exactly the fixture defect the night window recorded on 2026-09-09: two conversations opened
with the same first message are indistinguishable that way, and it silently measured the wrong
one. This selects by `data-testid="rail-conversation-<id>"`, which is the id the rail renders.

    AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_0909_conv_screen.py <agent> <conversation-id>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = require_key()
PROJ = os.environ["AW_PROJECT"]
AGENT, CONV = sys.argv[1], sys.argv[2]
SHOT = os.environ.get("SHOT")

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1500, "height": 1100})
    page.add_init_script(SEED)
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.locator(f"text={AGENT}").first.click()
    page.wait_for_timeout(1500)
    # The conversations are children of the agent row in the tree and are not rendered until the
    # row is expanded. The recent-conversations rail is a *different* view whose rows carry no
    # conversation id at all, which is why selecting there can only ever be a text match.
    exp = page.locator(f"[data-testid='agent-expander-{PROJ}-{AGENT}']")
    print(f"--- agent expander: count={exp.count()}")
    if exp.count():
        exp.first.click()
        page.wait_for_timeout(2000)
    target = page.locator(f"[data-testid='rail-conversation-{CONV}']")
    print(f"--- rail-conversation-{CONV}: count={target.count()}")
    if not target.count():
        print("--- ABORT: the rail does not carry that conversation")
        print(page.inner_text("body")[:800])
        b.close()
        sys.exit(2)
    target.first.click()
    page.wait_for_timeout(3500)
    body = page.inner_text("body")
    counts = {L: body.count(L) for L in ("Turn stopped", "Turn failed", "Turn interrupted",
                                         "Turn completed", "NOT DELIVERED")}
    print(f"--- label occurrences: {counts}")
    print(f"--- turn boundaries: {page.locator('[data-turn-boundary]').count()}")
    w = page.locator("[data-testid='turn-worked-for']")
    print(f"--- stat lines: {w.count()} -> {[w.nth(i).inner_text() for i in range(w.count())]}")
    if SHOT:
        page.screenshot(path=SHOT, full_page=True)
        print(f"--- screenshot {SHOT}")
    print("--- conversation pane text ---")
    print(body[-2500:])
    b.close()
