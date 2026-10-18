"""Sweep A (2026-10-18): Environment screens in Chromium -- Instructions (clear asks first?),
Runners, Charters (empty charter in context), Settings groups, Overview Collaboration block, the
Add agent dialog's runner select ("{name} - {model} ({cli})"), and an agent's settings sections.
No agent turns. Prints visible text and writes screenshots.

    py -3.11 scripts/drive/s1018_A_env_screens.py
"""

import json
import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import P, e2e  # noqa: E402

OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
errors = []


def text(page, limit=1500):
    return " ".join((page.locator("main").first.text_content() or "").split())[:limit]


with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1100})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(P)))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{e2e.hub()}/?project={P}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    print("OVERVIEW:", text(page, 1200))
    page.screenshot(path=str(OUT / "overview.png"), full_page=True)
    # open the environment via the project's gear
    gear = page.locator("[aria-label='Configure aw-sweepA-1018']").first
    print("gear:", gear.get_attribute("aria-label") if gear.count() else None)
    if gear.count():
        gear.click()
        page.wait_for_timeout(2000)
    for label in ("Instructions", "Runners", "Charters", "Settings"):
        loc = page.locator("nav[aria-label='Environment sections']").get_by_text(label, exact=True)
        if not loc.count():
            print(label, "not found")
            continue
        loc.first.click()
        page.wait_for_timeout(2000)
        print(f"\n{label.upper()}:", text(page, 2500))
        page.screenshot(path=str(OUT / f"env_{label.lower()}.png"), full_page=True)
        if label == "Instructions":
            clear = page.get_by_role("button", name="Clear")
            print("clear buttons:", clear.count())
            if clear.count():
                clear.first.click()
                page.wait_for_timeout(800)
                dlg = page.locator("[role=dialog], [role=alertdialog]")
                print("after Clear, dialog:", dlg.count(), (dlg.first.text_content() or "")[:300] if dlg.count() else "")
                page.screenshot(path=str(OUT / "instructions_clear.png"))
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                print("instructions still set:", e2e.request("GET", f"/projects/{P}/project/instructions")[1]["content"][:40])
    b.close()
print("errors:", errors[:10])
