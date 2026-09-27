"""r1a drive (2026-09-27): a flow is configured from its own tab. Chromium on the served bundle.
Start a flow on the Spec destination (doc-r1g) and from the conversation panel (doc-r1h); seeded approved change-spec rows; change the
agent from the loop tab, see it pending, let one firing apply it. AW_HUB, AW_KEY, AW_PROJECT, SHOT. Never :8000/:8010."""
import os, sys, datetime
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
SEED = "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
shot = lambda pg, n: pg.screenshot(path=os.environ["SHOT"] + n + ".png")
def poll(pg, fn, secs=20):
    for i in range(int(secs * 4)):
        if fn(): return round(i * 0.25, 2)
        pg.wait_for_timeout(250)
    return None
def loops(): return api("GET", A + "/loops")[1]
stop = (datetime.datetime.now() + datetime.timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M")

def start_flow(pg, name, cron):
    pg.locator("[data-testid=spec-start-flow]").click(); pg.wait_for_timeout(600)
    pg.locator("#flow-name").fill(name)
    pg.locator("#flow-agent").select_option("alpha")
    pg.locator("#flow-message").fill("Reply with the single word ok.")
    pg.locator("#flow-cron").fill(cron)
    pg.locator("#flow-stop-at").fill(stop)
    shot(pg, "_dialog_" + name)
    pg.get_by_role("button", name="Start", exact=False).last.click()

with sync_playwright() as p:
    b = p.chromium.launch()
    def mk(url):
        pg = b.new_page(viewport={"width": 1600, "height": 1000}); pg.add_init_script(SEED)
        pg.goto(HUB + url, wait_until="domcontentloaded"); pg.wait_for_timeout(3000)
        return pg

    print("H1 Spec destination: Start a flow on doc-r1g")
    pg = mk("/?project=%s&tab=spec&document=spec%%2Fdoc-r1g.html" % P)
    v("Start a flow offered, no flow link", pg.locator("[data-testid=spec-start-flow]").count() == 1 and pg.locator("[data-testid=spec-flow-link]").count() == 0)
    start_flow(pg, "r1a-spec", "0 0 1 1 *")
    t = poll(pg, lambda: pg.locator("[data-testid=spec-flow-link]").count() == 1)
    v("document names the flow at once (Spec destination)", t is not None, "after %ss: %s" % (t, pg.locator("[data-testid=spec-flow-link]").first.inner_text() if t is not None else "-"))
    L = [l for l in loops() if l.get("spec_document_id") == "doc-r1g"]
    v("Hub: one loop declares the document", len(L) == 1, str([(l["id"], l.get("agent"), l.get("spec_document_id")) for l in L]))
    shot(pg, "_h1")
    lid = L[0]["id"]

    print("H2 conversation panel: Start a flow on doc-r1h")
    pg2 = mk("/?project=%s&agent=alpha&document=spec%%2Fdoc-r1h.html" % P)
    shot(pg2, "_h2_before")
    v("panel shows Start a flow", pg2.locator("[data-testid=spec-start-flow]").count() == 1)
    if pg2.locator("[data-testid=spec-start-flow]").count() == 1:
        start_flow(pg2, "r1a-conv", "0 0 1 1 *")
        t = poll(pg2, lambda: pg2.locator("[data-testid=spec-flow-link]").count() == 1)
        v("document names the flow at once (conversation panel)", t is not None, "after %ss" % t)
        shot(pg2, "_h2")
    pg2.close()

    print("H3 open the flow's tab from the link; change the agent")
    pg.locator("[data-testid=spec-flow-link]").click(); pg.wait_for_timeout(2000)
    v("loop tab open", pg.locator("[data-testid=loop-tab]").count() == 1)
    v("URL carries no document=", "document=" not in pg.url, pg.url)
    shot(pg, "_h3_tab")
    read = lambda: pg.locator("[data-testid=loop-tab-settings-read]").inner_text().replace("\n", " | ") if pg.locator("[data-testid=loop-tab-settings-read]").count() else None
    print("   read:", read())
    pg.locator("[data-testid=loop-tab-settings]").get_by_role("button", name="Edit").click(); pg.wait_for_timeout(500)
    pg.locator("[data-testid=loop-tab-settings-form] select").select_option("beta")
    shot(pg, "_h3_form")
    pg.locator("[data-testid=loop-tab-settings-form]").get_by_role("button", name="Save").click()
    pend = lambda: pg.locator("[data-testid=loop-tab-pending-edit]").count() == 1
    t_pend = poll(pg, pend, 40)
    v("pending panel appears after Save", t_pend is not None and t_pend < 5, "after %ss" % t_pend)
    shot(pg, "_h3_saved")
    if t_pend is not None: print("   pending:", pg.locator("[data-testid=loop-tab-pending-edit]").inner_text().replace(chr(10), " | "))
    txt = read() or ""
    print("   read after save:", txt)
    x = api("GET", "%s/loops/%s" % (A, lid))[1]
    print("   API agent=%r pending_agent=%r pending_edit=%r" % (x.get("agent"), x.get("pending_agent"), x.get("pending_edit")))
    v("agent still alpha in force, beta pending (API)", x.get("agent") == "alpha" and "beta" in str(x.get("pending_agent") or x.get("pending_edit")))
    v("tab shows beta as pending, not in force", "beta" in txt and "alpha" in txt, txt)

    print("H4 cadence changed from the tab to every minute; one firing applies the staged agent")
    pg.locator("[data-testid=loop-tab-settings]").get_by_role("button", name="Edit").click(); pg.wait_for_timeout(500)
    pg.locator("[data-testid=loop-tab-settings-form] label:has-text('Cadence') input").fill("* * * * *")
    pg.locator("[data-testid=loop-tab-settings-form]").get_by_role("button", name="Save").click(); pg.wait_for_timeout(2500)
    shot(pg, "_h4_cadence"); print("   read:", read())
    x = api("GET", "%s/loops/%s" % (A, lid))[1]
    print("   API agent=%r pending_agent=%r pending_edit=%r" % (x.get("agent"), x.get("pending_agent"), x.get("pending_edit")))
    ok = None
    for i in range(50):
        pg.wait_for_timeout(3000)
        x = api("GET", "%s/loops/%s" % (A, lid))[1]
        if x.get("agent") == "beta": ok = i * 3; break
    v("agent in force is beta after a firing", ok is not None, "after ~%ss; pending_agent=%r" % (ok, x.get("pending_agent")))
    t_beta = poll(pg, lambda: "Default agent: beta" in (read() or ""), 40)
    v("tab shows beta in force within 5s of the firing", t_beta is not None and t_beta < 5, "after %ss" % t_beta)
    v("pending panel gone", not pend())
    shot(pg, "_h4"); print("   read:", read())
    print("   events:", [e.get("event_type") for e in x.get("events", [])])
    for j in api("GET", A + "/jobs")[1]:
        if j["enabled"]: api("PATCH", A + "/jobs/" + j["id"], {"enabled": False})
    b.close()
print("%d/%d" % (sum(R), len(R)))
