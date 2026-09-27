"""b10 drive (2026-09-27): a loop is stopped, archived and delegated from its own tab.
API half + Chromium half against the served bundle. AW_HUB, AW_KEY, AW_PROJECT, SHOT (file prefix). Never :8000/:8010."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, require_key, require_hub, P
from playwright.sync_api import sync_playwright

HUB = require_hub(); KEY = require_key()
assert not HUB.endswith((":8000", ":8010"))
A = "/projects/%s" % P
R = []
def v(label, ok, detail=""):
    R.append(ok); print("  [%s] %s  %s" % ("OK " if ok else "BAD", label, detail))

def mkloop(name):
    c, j = api("POST", A + "/jobs", {"name": name, "agent": "alpha", "message": "Write hello.txt containing hi, then stop.",
        "cron": "0 0 1 1 *", "purpose": "b10 drive", "enabled": True,
        "initial_tasks": [{"title": "Write hello.txt", "description": "Create hello.txt containing hi."}]})
    assert c in (200, 201), (c, j)
    return j.get("id") or j.get("job_id"), (j.get("loop") or {}).get("id")

def loop(lid): return api("GET", "%s/loops/%s" % (A, lid))[1]
def events(lid): return [e.get("event_type") for e in loop(lid).get("events", [])]

jobA, la = mkloop("b10-A"); jobB, lb = mkloop("b10-B"); jobC, lc = mkloop("b10-C")
print("loops", la, lb, lc)
SEED = "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
shot = lambda pg, n: pg.screenshot(path=os.environ["SHOT"] + n + ".png")
def txt(pg, tid):
    l = pg.locator("[data-testid=%s]" % tid)
    return l.first.inner_text().replace("\n", " | ") if l.count() else None
def tabtext(pg): return pg.locator("[data-testid=loop-tab]").inner_text().replace("\n", " | ")
def poll(pg, fn, secs=20):
    """seconds until fn() is true, or None"""
    for i in range(int(secs * 4)):
        if fn(): return round(i * 0.25, 2)
        pg.wait_for_timeout(250)
    return None
def open_panel(page):
    page.get_by_role("button", name="Show panel").click(); page.wait_for_timeout(800)
def loops_index(page):
    page.get_by_text("Loops", exact=True).first.click(); page.wait_for_timeout(1000)
def row(page, lid): return page.locator("[data-testid=loops-index-row-%s]" % lid)

with sync_playwright() as p:
    b = p.chromium.launch()
    def mk():
        pg = b.new_page(viewport={"width": 1600, "height": 1000}); pg.add_init_script(SEED)
        pg.goto(HUB, wait_until="domcontentloaded"); pg.wait_for_timeout(2500)
        pg.get_by_text("alpha", exact=True).first.click(); pg.wait_for_timeout(1500)
        pg.get_by_placeholder("Message alpha…").fill("Reply with the single word ok.")
        pg.keyboard.press("Enter"); pg.wait_for_timeout(12000)
        return pg
    page = mk()
    open_panel(page); shot(page, "02_panel")
    loops_index(page); shot(page, "03_index")
    row(page, la).click(); page.wait_for_timeout(1500); shot(page, "04_tab")

    print("H1 loop A: Stop beside the stop-condition line")
    print("  stop-condition:", txt(page, "loop-tab-stop-condition")); print("  controller:", txt(page, "loop-tab-controller"))
    v("stop condition line says operator", "operator" in (txt(page, "loop-tab-stop-condition") or ""))
    v("Stop button present", page.get_by_role("button", name="Stop", exact=True).count() == 1)
    v("controller line reads naturally", "decided by you" in (txt(page, "loop-tab-controller") or ""))

    print("H2 delegate, take back")
    def until(needle):
        for i in range(40):
            page.wait_for_timeout(250)
            if needle in (txt(page, "loop-tab-controller") or ""): return (i + 1) * 0.25
        return None
    page.get_by_role("button", name="Let alpha decide").click(); t1 = until("decided by alpha"); shot(page, "05_delegated")
    v("controller updated without reload (delegated)", t1 is not None, "after %ss; API control=%s" % (t1, loop(la).get("queue_control") or loop(la).get("control")))
    page.get_by_role("button", name="Decide them yourself").click(); t2 = until("decided by you")
    v("controller back to you", t2 is not None, "after %ss" % t2)
    ev = events(la); print("  events:", ev)
    v("two loop_control_changed rows in GET /loops", ev.count("loop_control_changed") == 2)

    print("H3 stop A with a reason")
    page.get_by_role("button", name="Stop", exact=True).click(); page.wait_for_timeout(500)
    v("confirm text present", "No firing starts after this" in (txt(page, "loop-tab-stop-confirm") or ""), txt(page, "loop-tab-stop-confirm"))
    page.locator("[data-testid=loop-tab-stop-confirm] input").fill("drive: done testing")
    page.get_by_role("button", name="Stop loop").click(); t = poll(page, lambda: "Stopped early" in tabtext(page)); print("  stopped badge after", t, "s"); shot(page, "06_stopped")
    body = tabtext(page)
    v("badge reads Stopped early: <reason>", "Stopped early" in body and "drive: done testing" in body, body[:200])
    v("Stop button gone", page.get_by_role("button", name="Stop", exact=True).count() == 0)
    lp = loop(la); print("  loop:", lp.get("ending_state"), lp.get("stop_reason"))
    v("API: stopped + reason", lp.get("ending_state") == "stopped" and lp.get("stop_reason") == "drive: done testing")
    v("API: one loop_stopped event", events(la).count("loop_stopped") == 1, str(events(la)))

    print("H4 archive A")
    page.get_by_role("button", name="Archive", exact=True).click(); page.wait_for_timeout(400)
    page.get_by_role("button", name="Archive loop").click(); page.wait_for_timeout(2000); shot(page, "07_archived")
    v("API: archived_at set", bool(loop(la).get("archived_at")))
    loops_index(page)
    t = poll(page, lambda: row(page, la).count() == 0); print("  index dropped archived loop after", t, "s")
    v("archived loop left the index", t is not None)
    page.locator("[data-testid=loops-index-include-archived]").click(force=True); page.wait_for_timeout(800)
    poll(page, lambda: row(page, la).count() == 1); r = row(page, la)
    v("Show archived brings it back, marked Archived", r.count() == 1 and "rchived" in r.inner_text(), r.inner_text().replace("\n", " | ") if r.count() else "")
    shot(page, "08_index_archived")

    print("H5 second tab SSE + H5a refused stop")
    page.locator("[data-testid=loops-index-include-archived]").click(force=True); page.wait_for_timeout(500)
    row(page, lb).click(); page.wait_for_timeout(1500)
    page2 = mk(); open_panel(page2); loops_index(page2); row(page2, lb).click(); page2.wait_for_timeout(1500)
    page.get_by_role("button", name="Stop", exact=True).click(); page.wait_for_timeout(400)   # confirm open in tab 1
    page2.get_by_role("button", name="Stop", exact=True).click(); page2.wait_for_timeout(300)
    page2.locator("[data-testid=loop-tab-stop-confirm] input").fill("second tab reason")
    page2.get_by_role("button", name="Stop loop").click(); t = poll(page, lambda: "second tab reason" in tabtext(page)); print("  tab1 SSE update after", t, "s")
    b1 = tabtext(page); print("  tab1 after tab2 stop:", b1[:250]); shot(page, "09_tab1_sse")
    v("tab 1 updated without reload via SSE", "second tab reason" in b1)
    v("tab 1 no longer offers Stop", page.get_by_role("button", name="Stop", exact=True).count() == 0 and page.get_by_role("button", name="Stop loop").count() == 0)
    c, out = api("PATCH", "%s/jobs/%s" % (A, jobB), {"stop_reason": "late stop"})
    print("  late PATCH:", c, json.dumps(out, default=str)[:400])
    v("late stop is 409 not 500", c == 409)
    lpb = loop(lb)
    v("record unchanged: reason kept, one loop_stopped", lpb.get("stop_reason") == "second tab reason" and events(lb).count("loop_stopped") == 1, str(events(lb)))
    page2.close()

    print("H5a-2 blank reason falls back")
    loops_index(page); row(page, lc).click(); page.wait_for_timeout(1500)
    page.get_by_role("button", name="Stop", exact=True).click(); page.wait_for_timeout(300)
    page.get_by_role("button", name="Stop loop").click(); poll(page, lambda: "Stopped early" in tabtext(page))
    body = tabtext(page)
    v("badge reads Stopped by the operator", "Stopped by the operator" in body, body[:200]); shot(page, "10_blank_reason")
    b.close()
print("SUMMARY", sum(R), "ok of", len(R))
