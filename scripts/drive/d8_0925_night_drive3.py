"""0925 night drive part 3: the task drawer's history says which flow moved a task."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import require_key
from playwright.sync_api import sync_playwright
HUB = os.environ["AW_HUB"]; KEY = require_key(); PROJ = os.environ["AW_PROJECT"]
if ":8000" in HUB or ":8010" in HUB: sys.exit("refusing")
SEED = f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}})); localStorage.setItem('agentweave-selected-project', {PROJ!r});"
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={"width": 1500, "height": 1100})
    page.add_init_script(SEED); page.goto(HUB, wait_until="domcontentloaded"); page.wait_for_timeout(2500)
    for name in ("Tasks", "Board"):
        l = page.get_by_role("link", name=name); bt = page.get_by_role("button", name=name)
        if l.count(): l.first.click(); break
        if bt.count(): bt.first.click(); break
    page.wait_for_timeout(2000)
    t = page.locator("text=drive task one")
    print("task cards:", t.count())
    if t.count():
        t.first.click(); page.wait_for_timeout(2000)
    body = page.inner_text("body")
    print("moved lines:", [ln for ln in body.splitlines() if "moved" in ln.lower()][:6])
    page.screenshot(path="testbed/scratch/drawer0925.png", full_page=True)
    if not t.count(): print(body[:600])
    b.close()
