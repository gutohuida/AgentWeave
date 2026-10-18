"""Sweep A (2026-10-18): the conversation screen in Chromium -- composer draft survives reload,
the permissions pill's "Ask me" copy, the model pill, a turn sent from the composer with live
thinking (F578 on a 5.5 model) that should stay open while it runs, Hide diagnostics surviving a
reload, the side panel and its narrow-window drawer, Ctrl+K. One real turn.

    py -3.11 scripts/drive/s1018_A_composer_ui.py <agent>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import P, e2e, q  # noqa: E402

agent = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
errors = []


def goto(page):
    page.goto(f"{e2e.hub()}/?project={P}", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.get_by_text(agent, exact=True).first.click()
    page.wait_for_timeout(2500)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(P)))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    goto(page)
    box = page.locator("textarea").first
    box.fill("draft text 123 — sweep A")
    page.wait_for_timeout(1200)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    try:
        page.get_by_text(agent, exact=True).first.click()
        page.wait_for_timeout(2000)
    except Exception:  # noqa: BLE001
        pass
    print("draft after reload:", repr(page.locator("textarea").first.input_value()))
    # pills
    footer = page.locator("textarea").first.locator("xpath=ancestor::*[.//button][3]")
    print("composer footer text:", (footer.text_content() or "")[:300])
    try:
        page.get_by_role("button", name="Permissions").first.click()
    except Exception:  # noqa: BLE001
        page.locator("text=Permissions:").first.click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "perm_menu.png"))
    menu = page.locator("[role=menu], [role=listbox]").first
    print("permissions menu:", (menu.text_content() if menu.count() else "no menu")[:900])
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # send a turn from the composer
    box = page.locator("textarea").first
    box.fill("Think carefully about whether 2147483647 is prime. Then run exactly this with the Bash "
             "tool: py -3.11 -c \"import time; time.sleep(25)\" and then reply with yes or no.")
    box.press("Enter")
    t0 = time.time()
    run = None
    while time.time() - t0 < 60 and not run:
        rows = q("select id from runs where project_id=? and agent=? and status='running'", P, agent)
        run = rows[0]["id"] if rows else None
        time.sleep(1)
    print("run:", run)
    seen_open = None
    while run and time.time() - t0 < 150:
        tools = q("select count(*) n from agent_outputs where run_id=? and kind='tool_use'", run)[0]["n"]
        if tools:
            page.wait_for_timeout(3000)
            blocks = page.locator("details").all()
            state = [(d.get_attribute("open") is not None, (d.text_content() or "")[:90]) for d in blocks[-3:]]
            print("last work blocks while running:", state)
            seen_open = state
            page.screenshot(path=str(OUT / "live_running.png"))
            break
        time.sleep(1)
    print("status", e2e.wait_for(run, 4) if run else None)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "live_after.png"))
    body = page.locator("main").first.text_content() or ""
    for needle in ("Reasoned", "Thinking"):
        print(needle, needle in body)
    # hide diagnostics + reload
    btn = page.get_by_role("button", name="Hide diagnostics")
    print("hide button:", btn.count())
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(500)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        page.get_by_text(agent, exact=True).first.click()
        page.wait_for_timeout(2000)
        print("after reload: Show diagnostics present:", page.get_by_role("button", name="Show diagnostics").count())
        page.get_by_role("button", name="Show diagnostics").first.click()
    # side panel
    sp = page.locator("[aria-label='Show panel']")
    print("show panel controls:", sp.count())
    if sp.count():
        sp.first.click()
        page.wait_for_timeout(1200)
        tabs = page.locator("[role=tab]").all()
        print("panel tabs:", [t.text_content() for t in tabs])
        page.screenshot(path=str(OUT / "side_panel.png"))
    page.set_viewport_size({"width": 820, "height": 900})
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "narrow.png"))
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.keyboard.press("Control+k")
    page.wait_for_timeout(700)
    pal = page.locator("[role=dialog]").first
    print("palette:", pal.count(), (pal.text_content() or "")[:200] if pal.count() else "")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("focus after Esc:", page.evaluate("document.activeElement && (document.activeElement.tagName + ' ' + (document.activeElement.getAttribute('aria-label')||''))"))
    b.close()
print("errors:", errors[:10])
