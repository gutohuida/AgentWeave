"""Judge the task story (slice task-story) on the Terra replica, in a real browser.

    py -3.11 scripts/drive/terra_replica.py --up 8130
    AW_DEV_HUB=http://127.0.0.1:8130 npx vite --port 5179     (from hub/ui; serves the source)
    py -3.11 scripts/drive/d1017_task_story_screens.py

The dev server serves hub/ui/src, so nothing touches the committed bundle the operator's :8000
serves. Shoots the drawer's Story view at both widths and modes, the proof opened, frame strips of
the entry stagger and the proof opening, a reduced-motion pass and a keyboard pass. Fails on any
console or page error, or a check below.
"""

import sys

from uiharness import Judge, replica

TERRA = "proj-cd006955cbe2"
TASK = "task-87ce01a67b0c"
DEV = "http://127.0.0.1:5179"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def open_drawer(page, task=TASK):
    page.get_by_test_id("project-tab-tasks").first.wait_for(timeout=30000)
    page.get_by_test_id("project-tab-tasks").first.click()
    page.get_by_test_id(f"task-open-{task}").first.wait_for(timeout=20000)
    page.get_by_test_id(f"task-open-{task}").first.click()
    page.get_by_test_id(f"task-drawer-{task}").wait_for(timeout=15000)


def settle(page, task=TASK):
    page.get_by_test_id(f"task-story-{task}").wait_for(timeout=15000)
    page.wait_for_timeout(900)


def drawer(page, task=TASK):
    return page.get_by_test_id(f"task-drawer-{task}")


_hub, key, _db = replica()
with Judge("d1017-task-story", hub=DEV, key=key) as j:
    # 1. The default view, both widths and modes.
    j.shots(TERRA, "story", lambda p: (open_drawer(p), settle(p)), locator=drawer)

    page = j.page(TERRA, mode="dark")
    open_drawer(page)
    settle(page)
    switch = page.get_by_test_id(f"task-view-story-{TASK}")
    check("the drawer opens on the Story view", switch.get_attribute("aria-pressed") == "true")
    events = page.locator(f"[data-testid='task-story-events-{TASK}'] > li")
    check("the story lists events", events.count() > 5, f"{events.count()} events")
    summary = page.get_by_test_id(f"task-story-summary-{TASK}").inner_text()
    check("the summary names the state and a cost", "approved" in summary and "$" in summary, summary.replace("\n", " | "))

    # 2. Open the proof of the first piece that names a commit.
    toggles = page.locator("[data-testid^='evidence-proof-toggle-']")
    check("evidence pieces offer their proof", toggles.count() > 0, f"{toggles.count()} toggles")
    if toggles.count():
        first = toggles.first
        piece = first.get_attribute("data-testid").replace("evidence-proof-toggle-", "")
        first.scroll_into_view_if_needed()
        box = drawer(page).bounding_box()
        j.frames(page, "proof_opening", lambda p: first.click(), count=7, interval_ms=55,
                 clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
        page.wait_for_timeout(1200)
        proof = page.get_by_test_id(f"evidence-proof-{piece}")
        text = proof.inner_text()
        check("the proof shows the requirement's wording", "requirement" in text.lower() and len(text) > 60, text[:120].replace("\n", " | "))
        diff = page.get_by_test_id(f"evidence-diff-{piece}")
        check("the proof shows the diff of the work", diff.count() == 1, "no diff rendered")
        proof.scroll_into_view_if_needed()
        j.shot(page, "proof_open_dark", locator=drawer(page))
        j.set_mode(page, "light")
        page.wait_for_timeout(400)
        j.shot(page, "proof_open_light", locator=drawer(page))
        j.set_mode(page, "dark")

    # 3. Details still holds every control.
    page.get_by_test_id(f"task-view-details-{TASK}").click()
    page.wait_for_timeout(500)
    check("Details shows the task's facts", page.locator(".task-detail-facts").count() == 1)
    j.shot(page, "details_dark", locator=drawer(page))
    page.context.close()

    # 4. The entry stagger, as frames.
    page = j.page(TERRA, mode="dark")
    page.get_by_test_id("project-tab-tasks").first.wait_for(timeout=30000)
    page.get_by_test_id("project-tab-tasks").first.click()
    page.get_by_test_id(f"task-open-{TASK}").first.wait_for(timeout=20000)
    j.frames(page, "story_entry", lambda p: p.get_by_test_id(f"task-open-{TASK}").first.click(),
             count=8, interval_ms=55, clip={"x": 330, "y": 0, "width": 780, "height": 520})
    page.context.close()

    # 5. Reduced motion: everything is visible in the first frame after it renders.
    page = j.page(TERRA, mode="light", reduced_motion=True)
    open_drawer(page)
    page.get_by_test_id(f"task-story-{TASK}").wait_for(timeout=15000)
    page.wait_for_timeout(120)
    opacities = page.eval_on_selector_all(
        f"[data-testid='task-story-events-{TASK}'] > li",
        "items => items.map(i => getComputedStyle(i).opacity)",
    )
    check("reduced motion: no event waits invisible", all(o == "1" for o in opacities), str(set(opacities)))
    j.shot(page, "reduced_motion_light", locator=drawer(page))

    # 6. Keyboard: the view switch and a proof toggle take focus visibly.
    page.get_by_test_id(f"task-view-details-{TASK}").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check("the keyboard switches to Details",
          page.get_by_test_id(f"task-view-details-{TASK}").get_attribute("aria-pressed") == "true")
    page.get_by_test_id(f"task-view-story-{TASK}").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    j.shot(page, "keyboard_focus_light", locator=drawer(page))
    page.context.close()

    check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))

print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
