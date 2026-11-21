"""Observe the profile model pool, chat model choice and the entry points to a profile's settings.

Observation only (edits nothing under hub/ or src/). Needs a fresh drive Hub (never :8000/:8010):
  AW_HUB, AW_KEY, AW_PROJECT   the Hub, its key, a project with runners `haiku`/`haiku45` and a
                               profile Builder whose pool holds both (see testbed/drive1121-pool/ids.json)
Free observations only. The three real Haiku turns of the original drive (a chat on Haiku 4.5, the
same thread switched to Haiku 5.5, a task-bound run carrying a chat override) were done by hand and
are not reproduced here. Screenshots go to testbed/drive1121-pool/shots/.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, "scripts/drive")
from aw import api  # noqa: E402

PID = os.environ["AW_PROJECT"]
S = "testbed/drive1121-pool/shots/"
U = f"{os.environ['AW_HUB']}/?project={PID}"
sys.stdout.reconfigure(encoding="utf-8")
POP = r"""()=>{const e=document.querySelector('[role=listbox],[role=menu]');return e?e.innerText.replace(/\n/g,' | '):'(no popup)'}"""

print("model catalog:")
_, cat = api("GET", "/model-catalog")
for p in cat["providers"]:
    print(" ", p["provider"], len(p["models"]), "models;", {c["id"]: [v["id"] for v in c["values"]] for c in p["controls"]})
_, runners = api("GET", f"/projects/{PID}/runners")
print("runners:", [(r["name"], r["cli"], r["model"]) for r in runners])

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    pg.goto(U + "&agent=Builder&settings=running")
    pg.wait_for_timeout(2500)
    print("Manage runners / Add a runner links:", pg.get_by_text("Manage runners").count(), pg.get_by_text("Add a runner").count())
    pg.get_by_label("Runner to add to Builder").click()
    pg.wait_for_timeout(500)
    print("Add a model lists:", pg.evaluate(POP))
    pg.screenshot(path=S + "13_pool_add_runner_open.png")
    pg.goto(U + "&agent=Builder")
    pg.wait_for_timeout(2500)
    pg.get_by_text("Model:").first.click()
    pg.wait_for_timeout(500)
    print("composer picker:", pg.evaluate(POP))
    pg.goto(U)
    pg.wait_for_timeout(2500)
    pg.get_by_label("Open Builder, Idle").click()
    pg.wait_for_timeout(1000)
    print("Overview row click ->", pg.url.split("//")[1])
    pg.goto(U)
    pg.wait_for_timeout(2500)
    pg.get_by_test_id("agent-details-toggle-Builder").click()
    pg.get_by_text("Profile settings").first.click()
    pg.wait_for_timeout(1000)
    print("Overview Details -> Profile settings ->", pg.url.split("//")[1])
    pg.goto(U)
    pg.wait_for_timeout(2500)
    pg.get_by_role("button", name="no charter").first.click()
    pg.wait_for_timeout(1000)
    print("Overview 'no charter' chip ->", pg.url.split("//")[1])
    pg.goto(U)
    pg.wait_for_timeout(2500)
    pg.get_by_label("Add profile to pooldrive").click()
    pg.wait_for_timeout(600)
    print("Create profile: native selects =", pg.locator("[role=dialog] select").count(),
          "| placeholder =", pg.locator("[role=dialog] input").first.get_attribute("placeholder"))

for label, ov in [("off-pool model", {"model": "claude-opus-5-5"}), ("off-pool runner", {"runner_id": "runner-x"})]:
    c, body = api("POST", f"/projects/{PID}/agent/trigger", {"agent": "Builder", "message": "Reply with just the word ok.", "overrides": ov})
    print(label, "->", c, json.dumps(body))
