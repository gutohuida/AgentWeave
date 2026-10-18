"""Sweep A (2026-10-18): the Delete-project dialog in Chromium on a throwaway project, keyboard
behaviour (focus on open, Escape, Enter), then what it leaves on disk and what reopening the folder
does.

    py -3.11 scripts/drive/s1018_A_delete_ui.py <project-id> <project-name> <dir>
"""

import json
import pathlib
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import e2e, req  # noqa: E402

pid, name, d = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(pid)))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{e2e.hub()}/?project={pid}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.locator(f"[aria-label='Configure {name}']").first.click()
    page.wait_for_timeout(1500)
    page.locator("nav[aria-label='Environment sections']").get_by_text("Settings", exact=True).first.click()
    page.wait_for_timeout(1500)
    opener = page.get_by_role("button", name="Delete project…")
    opener.scroll_into_view_if_needed()
    opener.click()
    page.wait_for_timeout(600)
    print("focus on open:", page.evaluate("document.activeElement.getAttribute('aria-label')"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    print("dialog after Escape:", page.locator("[role=dialog]").count(), "focus:", page.evaluate("document.activeElement.textContent"))
    opener.click()
    page.wait_for_timeout(400)
    page.keyboard.type(name[:-1])
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    print("Enter with wrong name; still listed:", req("GET", f"/projects/{pid}")[0])
    page.keyboard.type(name[-1])
    page.screenshot(path=str(OUT / "delete_dialog.png"))
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "after_delete.png"))
    print("after delete GET:", req("GET", f"/projects/{pid}")[0], "url:", page.url)
    b.close()
print("left on disk:", sorted(p.name for p in (d / ".agentweave").iterdir()) if (d / ".agentweave").exists() else "nothing")
s, res = req("POST", "/projects/open", {"path": str(d)})
print("reopen:", s, json.dumps(res)[:400])
print("marker now:", (d / ".agentweave" / "project.json").read_text() if (d / ".agentweave" / "project.json").exists() else None)
if s < 300:
    print("delete the reopened one:", req("DELETE", f"/projects/{res['id']}")[0])
print("errors:", errors[:10])
