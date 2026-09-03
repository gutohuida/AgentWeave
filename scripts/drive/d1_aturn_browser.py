"""D-1: what the *browser* renders for a stopped, failed and clean turn.

The phase-6 and phase-7 harnesses evaluated `aturn_model.py`, a Python transcription of the built
component. Nothing has yet asked the served bundle on :8011. This opens it as an operator, clicks
to the agent's conversation and reads the terminal line, the stat line and the working indicator
off the DOM.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 scripts/drive/d1_aturn_browser.py \
        <agent> [expected-terminal-label]
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
PROJ = os.environ["AW_PROJECT"]
AGENT = sys.argv[1]
EXPECT = sys.argv[2] if len(sys.argv) > 2 else None
SHOT = os.environ.get("SHOT")

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1500, "height": 1000})
    page.add_init_script(SEED)
    console = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:300]))
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:300]))
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    # Reach the agent. The UI has no router: click.
    clicked = False
    for sel in (f"text={AGENT}",):
        loc = page.locator(sel).first
        if loc.count():
            loc.click()
            clicked = True
            break
    page.wait_for_timeout(3500)
    print(f"clicked agent tile: {clicked}")

    body = page.inner_text("body")
    print("--- terminal labels present in the DOM:")
    for label in ("Turn failed", "Turn stopped", "Turn interrupted"):
        print(f"    {label!r}: {label in body}")
    worked = page.locator("[data-testid='turn-worked-for']")
    print(f"--- stat line ('turn-worked-for') count={worked.count()}")
    for i in range(worked.count()):
        print(f"      {worked.nth(i).inner_text()!r}")
    print(f"--- turn boundaries: {page.locator('[data-turn-boundary]').count()}")
    counts = {L: body.count(L) for L in ("Turn failed", "Turn stopped", "Turn interrupted")}
    print(f"--- terminal-label OCCURRENCES: {counts}  total={sum(counts.values())}")
    if console:
        print("--- console:")
        for line in console[:15]:
            print(f"      {line}")
    if SHOT:
        page.screenshot(path=SHOT, full_page=True)
        print(f"--- screenshot {SHOT}")
    if EXPECT:
        print(f"RESULT expected={EXPECT!r} present={EXPECT in body}")
    print("--- body head ---")
    print(body[:1500])
    b.close()
