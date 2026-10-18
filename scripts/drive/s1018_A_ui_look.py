"""Sweep A (2026-10-18): open an agent's conversation in Chromium and record what it shows
(header state, work blocks expanded, subagent rows, diagnostics toggle). No agent turns.

    py -3.11 scripts/drive/s1018_A_ui_look.py <agent> <shot-name> [project-id]
"""

import json
import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import P as P0, e2e  # noqa: E402

agent, name = sys.argv[1], sys.argv[2]
P = sys.argv[3] if len(sys.argv) > 3 else P0
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1400})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(P)))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{e2e.hub()}/?project={P}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.get_by_text(agent, exact=True).first.click()
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / f"{name}_1.png"))
    for d in page.locator("details").all():
        try:
            if d.get_attribute("open") is None:
                d.locator("summary").first.click()
        except Exception:  # noqa: BLE001
            pass
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / f"{name}_2.png"), full_page=True)
    body = page.locator("main").first.text_content() or ""
    for needle in ("subagent", "Reasoned", "Thinking", "running", "Stop turn", "is responding",
                   "Hide diagnostics", "denied", "refused", "expired", "operator refused"):
        i = body.find(needle)
        print(f"{needle!r}: {'yes' if i >= 0 else 'no'}  {body[max(0, i-80):i+160]!r}" if i >= 0 else f"{needle!r}: no")
    b.close()
print("errors:", errors[:10])
