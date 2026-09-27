"""Drive step for a-runner-choice-names-its-model, tasks.md 3.1.

On the trial Hub `:8010` (per the task's explicit instruction, not a fresh drive Hub), two `Twin`
claude runners on two declared models already exist in project proj-572d52826e3a. This script reads
the runner select's rendered option texts in an agent's Settings, then both runner selects in
project settings, against the served bundle (no dev server).

Run: py -3.11 scripts/drive/d0927_twin_runner_labels.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = "http://127.0.0.1:8010"
KEY = os.environ["AW_KEY"]
P = "proj-572d52826e3a"
AGENT = "twinagent"

SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r})); "
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.add_init_script(SEED)

    print("== Agent Settings: runner select ==")
    pg.goto(HUB + f"/?project={P}&agent={AGENT}&settings=execution", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    found = False
    for sel in pg.locator("select").all():
        texts = [o.inner_text() for o in sel.locator("option").all()]
        if any("Twin" in t for t in texts):
            found = True
            for t in texts:
                print(repr(t))
    if not found:
        print("NO SELECT WITH 'Twin' OPTIONS FOUND on agent settings page")
    pg.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "twin_agent_settings.png"))

    print("== Project Settings: title-runner + checkpoint-runner selects ==")
    pg.goto(HUB + f"/?project={P}&tab=environment&section=settings", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    for sel in pg.locator("select").all():
        texts = [o.inner_text() for o in sel.locator("option").all()]
        if any("Twin" in t for t in texts):
            sel_id = sel.get_attribute("id")
            print(f"-- select id={sel_id!r} --")
            for t in texts:
                print(repr(t))
    pg.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "twin_project_settings.png"))

    print("== after choosing a Checkpoint model override (Sonnet 5) ==")
    ckpt_select = pg.get_by_label("Checkpoint runner")
    ckpt_select.select_option(label="Twin — Opus 5.5 (claude)")
    pg.wait_for_timeout(300)
    model_select = pg.get_by_label("Checkpoint model")
    model_select.select_option(label="Sonnet 5")
    pg.wait_for_timeout(300)
    idx = 0
    for sel in pg.locator("select").all():
        texts = [o.inner_text() for o in sel.locator("option").all()]
        if any("Twin" in t for t in texts):
            idx += 1
            for t in texts:
                print(f"select#{idx}:", repr(t))
    pg.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "twin_project_settings_override.png"))

    b.close()
