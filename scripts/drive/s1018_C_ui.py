"""Sweep C UI scenes on Hub :8033, in a real Chromium. `py -3.11 s1018_C_ui.py <scene> [args]`.

Screenshots and text dumps go to the sweepC scratchpad.
"""
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

from s1018_C_lib import P, e2e

OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepC\ui")
OUT.mkdir(parents=True, exist_ok=True)
HUB = e2e.hub()
KEY = e2e.key()


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("shot", OUT / f"{name}.png")


def text(page, sel="main", limit=4000):
    loc = page.locator(sel).first
    try:
        t = loc.text_content(timeout=5000) or ""
    except Exception as exc:  # noqa: BLE001
        t = f"<no {sel}: {exc}>"
    return " ".join(t.split())[:limit]


def open_agent(page, agent):
    page.get_by_test_id(f"rail-agent-{P}-{agent}").first.click()
    time.sleep(3)


def tab(page, name):
    page.get_by_test_id(f"project-tab-{name}").first.click()
    time.sleep(2.5)


def scene_agent(page, agent, tag=""):
    open_agent(page, agent)
    shot(page, f"agent_{agent}{tag}")
    print("TEXT:", text(page, "body", 6000)[-4000:])


def scene_tasks(page, task_id=None):
    tab(page, "tasks")
    shot(page, "tasks_board")
    print("BOARD:", text(page, "body", 3000))
    dep = page.get_by_test_id("tasks-view-dependencies")
    if dep.count():
        dep.first.click()
        time.sleep(2)
        shot(page, "tasks_dependencies")
        print("DEPS:", text(page, "body", 3000))
        page.get_by_test_id("tasks-view-board").first.click()
        time.sleep(1.5)
    if task_id:
        page.get_by_test_id(f"task-open-{task_id}").first.click()
        time.sleep(2.5)
        shot(page, f"task_drawer_{task_id}")
        print("DRAWER:", text(page, f"[data-testid='task-drawer-{task_id}']", 6000))
        views = page.locator(f"[data-testid^='task-view-'][data-testid$='-{task_id}']")
        for i in range(views.count()):
            v = views.nth(i)
            tid = v.get_attribute("data-testid")
            v.click()
            time.sleep(1.5)
            shot(page, f"task_drawer_{task_id}_{tid}")
            print(f"VIEW {tid}:", text(page, f"[data-testid='task-drawer-{task_id}']", 5000))


def scene_jobs(page):
    tab(page, "jobs")
    shot(page, "jobs")
    print("JOBS:", text(page, "body", 5000))
    for i in range(5):
        exp = page.get_by_label("Expand job details")
        if not exp.count():
            break
        exp.first.click()
        time.sleep(1.5)
    shot(page, "jobs_expanded")
    print("JOBS-EXP:", text(page, "body", 8000))
    arch = page.get_by_test_id("jobs-filter-archived")
    if arch.count():
        arch.first.click()
        time.sleep(2)
        shot(page, "jobs_archived")
        print("ARCHIVED:", text(page, "body", 5000))


def scene_panel(page, agent):
    open_agent(page, agent)
    page.get_by_label("Show panel").first.click()
    time.sleep(2)
    shot(page, f"panel_{agent}")
    print("PANEL:", text(page, "body", 6000)[-4000:])
    loops = page.get_by_test_id("panel-launch-loops")
    if loops.count():
        loops.first.click()
        time.sleep(2)
        shot(page, f"panel_{agent}_loops")
        print("PANEL-LOOPS:", text(page, "[data-testid='panel-tab-content']", 4000))
        inc = page.get_by_test_id("loops-index-include-archived")
        if inc.count():
            inc.first.check(force=True)
            time.sleep(1.5)
            shot(page, f"panel_{agent}_loops_archived")
            print("PANEL-LOOPS+ARCHIVED:", text(page, "[data-testid='panel-tab-content']", 4000))
        res = page.get_by_test_id("loops-index-results").locator("button")
        n = res.count()
        print("loop rows:", n)
        for i in range(min(n, 3)):
            page.get_by_test_id("loops-index-results").locator("button").nth(i).click()
            time.sleep(2)
            shot(page, f"panel_{agent}_loop_{i}")
            print(f"LOOP-TAB {i}:", text(page, "[data-testid='loop-tab']", 5000))
            st = page.get_by_test_id("loop-tab-settings")
            if st.count():
                st.first.click()
                time.sleep(1)
                print(f"LOOP-SETTINGS {i}:", text(page, "[data-testid='loop-tab']", 3000))
                shot(page, f"panel_{agent}_loop_{i}_settings")
            page.get_by_test_id("panel-launch-loops")
            tabs = page.get_by_test_id("panel-tab-strip").get_by_text("Loops", exact=True)
            if tabs.count():
                tabs.first.click()
                time.sleep(1)


def main():
    scene, args = sys.argv[1], sys.argv[2:]
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, P)
    )
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        page.add_init_script(seed)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{HUB}/?project={P}", wait_until="domcontentloaded")
        time.sleep(4)
        try:
            globals()[f"scene_{scene}"](page, *args)
        finally:
            print("PAGE ERRORS:", errors)
            browser.close()


if __name__ == "__main__":
    main()
