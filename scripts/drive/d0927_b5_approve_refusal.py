import os, sys
sys.path.insert(0, "scripts/drive"); sys.stdout.reconfigure(encoding="utf-8")
from aw import api
from playwright.sync_api import sync_playwright
import json
PID = sys.argv[1]; S = "/projects/%s/project" % PID; HUB = os.environ["AW_HUB"]; KEY = os.environ["AW_KEY"]
c, doc = api("POST", S + "/documents", {"title": "b5 approve"}); path = doc["path"]
pl = {"schema_version": 1, "kind": doc["kind"], "title": "b5 approve", "summary": "One.", "problem": "Drive.",
 "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
 "requirements": [{"key": "r1", "statement": "The README MUST mention item 1.", "modal": "MUST"}],
 "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "g", "when": "w", "then": "t"}],
 "tasks": [{"key": "t1", "title": "Check", "description": "d", "requirements": ["r1"]}],
 "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": []}
print("write", api("PUT", S + "/documents/%s/content" % path, {"document": pl})[0])
api("POST", S + "/documents/close-exploration?path=" + path)
c, b = api("POST", S + "/documents/propose?path=" + path); print("propose", c, b.get("phase"), b.get("blocking"))
bad = dict(pl, requirements=[], tasks=[], acceptance_criteria=[])
c, b = api("PUT", S + "/documents/%s/content" % path, {"document": bad}); print("damage", c, str(b)[:200])
c, b = api("GET", S + "/spec?path=" + path); print("phase", (b.get("document") or b).get("phase"))
SEED = "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, PID)
with sync_playwright() as p:
    br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1600, "height": 1000}); pg.add_init_script(SEED)
    pg.goto(HUB + "/?project=%s&tab=spec&document=%s" % (PID, path.replace("/", "%2F")), wait_until="domcontentloaded"); pg.wait_for_timeout(3500)
    btn = pg.get_by_role("button", name="Approve", exact=False); print("approve buttons", btn.count())
    if btn.count():
        btn.first.click(); pg.wait_for_timeout(2500)
        pg.screenshot(path="testbed/scratch/b5shots/_c_approve.png")
    br.close()
c, b = api("GET", S + "/spec?path=" + path); print("phase after", (b.get("document") or b).get("phase"))
