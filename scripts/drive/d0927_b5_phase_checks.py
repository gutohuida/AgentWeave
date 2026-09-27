"""b5 drive (2026-09-27): a document moves forward only through its checks.
Part A: F207's four calls verbatim over HTTP. Part B: Chromium on the served bundle, the phase bar's
Propose and Approve on an incomplete document. AW_HUB, AW_KEY, SHOT. Never :8000/:8010. No agent turns."""
import os, sys, subprocess, tempfile, pathlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, require_key, require_hub
from playwright.sync_api import sync_playwright

HUB = require_hub(); KEY = require_key()
assert not HUB.endswith((":8000", ":8010"))
R = []
def v(label, ok, detail=""):
    R.append(ok); print("  [%s] %s  %s" % ("OK " if ok else "BAD", label, detail))

TAG = str(int(time.time()) % 100000)
root = pathlib.Path(tempfile.gettempdir()) / ("b5drive-" + TAG); root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("b5 drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)
c, proj = api("POST", "/projects/open", {"path": str(root), "name": "b5-" + TAG})
PID = proj["id"]; S = "/projects/%s/project" % PID
print("project", PID)

print("A. F207's four calls, verbatim")
c, doc = api("POST", S + "/documents", {"title": "b5 empty"}); path = doc["path"]
v("1 create", c in (200, 201), "%s %s" % (c, path))
c, b = api("POST", S + "/documents/close-exploration?path=" + path)
v("2 close-exploration", c == 200, str(c))
c, b = api("POST", S + "/documents/propose?path=" + path)
print("   propose:", c, str(b)[:300])
v("3 propose -> 200 with blocking findings, not moved", c == 200 and len(b.get("blocking") or b.get("findings") or []) > 0, str(sorted(b)) if isinstance(b, dict) else "")
c, b = api("POST", S + "/documents/phase?path=%s&to=proposed" % path, {"reason": ""})
print("   phase->proposed:", c, str(b)[:400])
v("4a phase to=proposed refused (was 200)", c == 409, str(c))
c, b = api("POST", S + "/documents/phase?path=%s&to=approved" % path, {"reason": ""})
v("4b phase to=approved refused", c == 409, "%s %s" % (c, str(b)[:200]))
c, b = api("GET", S + "/spec?path=" + path)
print("   document phase:", (b.get("document") or b).get("phase") if isinstance(b, dict) else b)

print("B. Chromium: Propose and Approve refusals")
c, d2 = api("POST", S + "/documents", {"title": "b5 ui empty"}); p2 = d2["path"]
api("POST", S + "/documents/close-exploration?path=" + p2)
SEED = "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, PID)
shot = lambda pg, n: pg.screenshot(path=os.environ["SHOT"] + n + ".png")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}); pg.add_init_script(SEED)
    pg.goto(HUB + "/?project=%s&tab=spec&document=%s" % (PID, p2.replace("/", "%2F")), wait_until="domcontentloaded")
    pg.wait_for_timeout(3500); shot(pg, "_b0")
    print("   buttons:", [x.inner_text() for x in pg.get_by_role("button").all()][:40])
    for name in ("Propose", "Approve"):
        btn = pg.get_by_role("button", name=name, exact=False)
        if btn.count():
            btn.first.click(); pg.wait_for_timeout(2500); shot(pg, "_b_" + name)
            body = pg.inner_text("body")
            i = body.lower().find("complete")
            v("%s clicked; a refusal is on the page" % name, i >= 0 or "refus" in body.lower() or "blocking" in body.lower(), body[max(0, i - 100):i + 200].replace("\n", " | ") if i >= 0 else "no sentence found")
        else:
            print("   no %s button" % name)
    b.close()
c, b = api("GET", S + "/spec?path=" + p2)
print("   ui doc phase after clicks:", (b.get("document") or b).get("phase"))
print("RESULT", "PASS" if all(R) else "FAIL", "%d/%d" % (sum(R), len(R)))
