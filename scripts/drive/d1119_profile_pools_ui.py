"""UI click-through for pool-edit-ui (FR-3) and build-prefills-recommendation (FR-6).

Run after d1119_profile_pools_ui_setup.py (ids file in argv[1]); trial Hub on :8010 serving this
checkout's bundle. Screenshots go to scripts/drive/d1119-shots/.

    py -3.11 scripts/drive/d1119_profile_pools_ui.py <ids.json>
"""
import json
import pathlib
import sys

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

SHOTS = pathlib.Path(__file__).resolve().parent / "d1119-shots"
ids = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
pid, r, DOC = ids["pid"], ids["runners"], ids["doc"]
base = f"/projects/{pid}"


def builder():
    _, rows = d.api("GET", f"{base}/agents")
    rows = rows if isinstance(rows, list) else rows["agents"]
    return next(a for a in rows if a["name"] == "Builder")


def summary(a):
    return {"runner_id": a["runner_id"], "pool": [(e["model"], e["effort"], e["default"]) for e in a["pool"]]}


seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
d.api("PATCH", f"{base}/agents/Builder", {"pool": [
    {"runner_id": r["Haiku"], "effort": None, "default": True},
    {"runner_id": r["Sonnet"], "effort": None, "default": False}]})
before = builder()
print("before:", summary(before))
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 1100})
    pg.add_init_script(seed)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{d.HUB}/?project={pid}&agent=Builder&settings=running", wait_until="domcontentloaded")
    pg.get_by_text("Models it may run on").wait_for(timeout=30000)
    pg.screenshot(path=str(SHOTS / "1-pool-before.png"))
    # Add Claude Opus at high.
    pg.get_by_role("button", name="Runner to add to Builder").click()
    pg.get_by_role("menuitemradio", name="Opus 5.5").click()
    pg.get_by_role("button", name="Effort").click()
    pg.get_by_role("menuitemradio", name="High", exact=True).click()
    pg.screenshot(path=str(SHOTS / "2-add-opus-high.png"))
    pg.get_by_role("button", name="Add", exact=True).click()
    pg.get_by_text("Opus 5.5 · high").first.wait_for(timeout=15000)
    # Make it the default.
    pg.get_by_role("button", name="Make Opus 5.5 · high the default").click()
    d.poll(lambda: any(e["default"] and e["effort"] == "high" for e in builder()["pool"]), 15)
    # Remove the old entry (Haiku, now not the default).
    pg.get_by_role("button", name="Remove Haiku 5.5").click()
    d.poll(lambda: len(builder()["pool"]) == 2, 15)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(SHOTS / "3-pool-after.png"))
    after = builder()
    print("after:", summary(after))
    d.check("pool-edit-ui: pool is Opus high (default) + Sonnet; Haiku gone",
            sorted(summary(after)["pool"], key=str) == sorted([("claude-opus-5-5", "high", True), ("claude-sonnet-5-5", None, False)], key=str),
            str(summary(after)))
    d.check("pool-edit-ui: runner_id names the Opus runner", after["runner_id"] == r["Opus"], f"{after['runner_id']} vs {r['Opus']}")
    d.check("pool-edit-ui: the page shows the new default",
            pg.locator("li[data-default='true']").inner_text().startswith("Opus 5.5") or "Opus 5.5" in pg.locator("li[data-default='true']").inner_text(),
            pg.locator("li[data-default='true']").inner_text().replace("\n", " "))

    # Build dialog. Restore the pool to Haiku (default) + Sonnet first, as the setup left it.
    d.api("PATCH", f"{base}/agents/Builder", {"pool": [
        {"runner_id": r["Haiku"], "effort": None, "default": True},
        {"runner_id": r["Sonnet"], "effort": None, "default": False}]})
    pg.goto(f"{d.HUB}/?project={pid}&tab=spec&document={DOC}", wait_until="domcontentloaded")
    pg.get_by_role("button", name="Build…").first.click()
    pg.get_by_text("Who builds and checks").wait_for(timeout=30000)
    pg.wait_for_timeout(1500)
    dlg = pg.get_by_role("dialog")
    dlg.locator(".aw-bp-table").scroll_into_view_if_needed()
    pg.screenshot(path=str(SHOTS / "4-build-dialog.png"))
    for task, want in (("Add t-in.txt", "Sonnet 5.5"), ("Add t-out.txt", "Haiku 5.5"), ("Add t-plain.txt", "Haiku 5.5")):
        btn = dlg.get_by_role("button", name=f"{task}: builder’s model")
        got = btn.inner_text().strip()
        d.check(f"build-prefills-recommendation: {task} builder shows {want}", want in got, got)
    t_out = dlg.get_by_role("button", name="Add t-out.txt: builder’s model")
    t_out.click()
    opts = [o.inner_text().replace("\n", " ") for o in pg.get_by_role("menuitemradio").all()]
    pg.screenshot(path=str(SHOTS / "5-build-dropdown-pool.png"))
    print("t-out dropdown options:", opts)
    d.check("build-prefills-recommendation: dropdown lists exactly the pool (Haiku, Sonnet; no Opus)",
            len(opts) == 2 and any("Haiku" in o for o in opts) and any("Sonnet" in o for o in opts) and not any("Opus" in o for o in opts), str(opts))
    b.close()
d.check("no page errors", not errors, str(errors))
