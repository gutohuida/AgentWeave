import json, pathlib, sys, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from drive import HERE, App, wait_loom, GEOM, selected_key, OUT, SCRATCH_KEY, check, results
from playwright.sync_api import sync_playwright
P = (HERE / "live_project.txt").read_text().strip()
HUB = "http://127.0.0.1:8021"
def post(path, body):
    req = urllib.request.Request(HUB + path, data=json.dumps(body).encode(), method="POST", headers={"Authorization": f"Bearer {SCRATCH_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r: return json.loads(r.read())
def get(path):
    req = urllib.request.Request(HUB + path, headers={"Authorization": f"Bearer {SCRATCH_KEY}"})
    with urllib.request.urlopen(req) as r: return json.loads(r.read())
with sync_playwright() as p:
    b = p.chromium.launch()
    app = App(b, "http://127.0.0.1:5193", SCRATCH_KEY, P)
    pg = app.page()
    wait_loom(pg); pg.wait_for_timeout(2500)
    pg.get_by_role("button", name="The beginning").click(); pg.wait_for_timeout(1500)
    g0 = pg.evaluate(GEOM); first = g0["beads"][0]["key"]
    check("live: the beginning selects the first knot", selected_key(pg) == first, first)
    pg.screenshot(path=str(OUT / "live_before.png"))
    t0 = time.perf_counter()
    msg = post(f"/api/v1/projects/{P}/messages", {"to": "haiku", "content": "Reply with the single word ok. Do not use any tools.", "subject": "live drive"})
    print("message", msg.get("id"))
    arrived = None
    end0 = (len(g0["beads"]), g0["labels"][-1]["text"])
    print("end before:", end0)
    while time.perf_counter() - t0 < 30:
        g = pg.evaluate(GEOM)
        if (len(g["beads"]), g["labels"][-1]["text"]) != end0:
            arrived = time.perf_counter() - t0; break
        pg.wait_for_timeout(100)
    print("end after:", (len(g["beads"]), g["labels"][-1]["text"]))
    try:
        print("thread now", [(k["kind"], k["title"][:50]) for k in get(f"/api/v1/projects/{P}/thread")["knots"]][-3:])
    except Exception as e:
        print("thread read failed", e)
    g1 = pg.evaluate(GEOM)
    newk = [bd for bd in g1["beads"] if bd["key"] not in {x["key"] for x in g0["beads"]}]
    check("ac-live: within five seconds the new activity is on the thread's present end", arrived is not None and arrived < 5 and (newk[-1]["x"] == max(x["x"] for x in g1["beads"]) if newk else g1["labels"][-1]["text"] != end0[1]), f"arrived after {arrived}s: {[k['key'] for k in newk]}")
    fb = next(x for x in g1["beads"] if x["key"] == first)
    fb0 = g0["beads"][0]
    check("ac-live: the first knot is still selected and still in view, not moved", selected_key(pg) == first and fb["sx"] == fb0["sx"], f"screen x {fb0['sx']} -> {fb['sx']}")
    pg.screenshot(path=str(OUT / "live_after.png"))
    # let the run finish, see the knot update in place
    pg.wait_for_timeout(25000)
    g2 = pg.evaluate(GEOM)
    print("after run:", [(x["key"]) for x in g2["beads"]][-3:], selected_key(pg) == first)
    pg.screenshot(path=str(OUT / "live_end.png"))
    b.close()
(OUT / "results_live.json").write_text(json.dumps(results, indent=1))
