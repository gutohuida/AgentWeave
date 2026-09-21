"""Does the served Activity feed render a live run_divergence_resolved at all? (d1-drive 2026-09-13)

Opens the Activity tab, PATCHes TID to TO (default under_review) -- a TRUE resolution of its open
divergence -- and counts the feed line. Measured: task_updated renders live, run_divergence_resolved
does not (F251). AW_HUB AW_KEY AW_PROJECT TID SHOT [TO].
"""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aw import api, require_key
from playwright.sync_api import sync_playwright
HUB, KEY, P, TID = os.environ["AW_HUB"], require_key(), os.environ["AW_PROJECT"], os.environ["TID"]
SHOT = os.environ["SHOT"]
SEED = f"""sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {P!r});"""
with sync_playwright() as pw:
    br = pw.chromium.launch(); page = br.new_page(viewport={"width": 1500, "height": 1000})
    page.add_init_script(SEED)
    streams = []
    page.on("request", lambda r: streams.append(r.url) if r.url.endswith("/api/v1/events") else None)
    page.goto(HUB, wait_until="domcontentloaded"); page.wait_for_timeout(3000)
    page.get_by_role("button", name="Activity", exact=True).first.click(); page.wait_for_timeout(3000)
    line = f"open divergence on {TID} resolved"
    before = page.inner_text("body").count(line)
    c, b = api("PATCH", f"/projects/{P}/tasks/{TID}", {"status": os.environ.get("TO", "under_review")})
    print("PATCH", c, json.dumps(b)[:300])
    page.wait_for_timeout(12000)
    body = page.inner_text("body")
    print("page opened the event stream:", streams)
    print(f"feed lines '{line}': before={before} after={body.count(line)}")
    for ln in body.splitlines():
        if TID in ln or "divergence" in ln: print("  feed:", ln[:200])
    page.screenshot(path=SHOT, full_page=True); br.close()
