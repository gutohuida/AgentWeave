"""Acceptance for the-thread-is-how-agentweave-shows-it-is-loading: the thread really weaves live.

Opens the Tasks and Vault screens with their Hub answers held back, so each screen has to wait,
and checks that the brand's loading thread is what shows: visible after the 300 ms hold, moving
between two frames 200 ms apart, and gone once the answers are released. A second pass asks for
reduced motion and checks the thread stands still, fully drawn.

Point it at a Vite dev server proxied to the trial Hub (never :8000):

  AW_DEV_HUB=http://127.0.0.1:8010 npx vite --port 5191      (from hub/ui)
  py -3.11 scripts/drive/d1023_loading_thread.py [ui-url] [project]

Defaults: http://127.0.0.1:5191, proj-d85a82bf4216. Against :8010 itself (the committed bundle)
it shows what master serves.
"""

import pathlib
import sys

from uiharness import Judge

KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


# (screen, tab test id, the Hub route its first load waits on)
SCREENS = [
    ("tasks", "project-tab-tasks", "/tasks"),
    ("vault", "project-tab-vault", "/vault"),
]

DASH = """el => { const p = el.querySelector('.aw-thread-a'), b = el.querySelector('.aw-thread-b');
  const s = (n) => { const c = getComputedStyle(n); return c.strokeDasharray + '|' + c.strokeDashoffset; };
  return p && b ? s(p) + '/' + s(b) : null; }"""


def drive(j, project, reduced):
    tag = "reduced" if reduced else "motion"
    for name, tab, route in SCREENS:
        page = j.page(project, mode="dark", reduced_motion=reduced)
        page.get_by_test_id(tab).first.wait_for(timeout=30000)
        held = []
        page.route(f"**/api/v1/projects/{project}{route}**", lambda r: held.append(r))
        page.get_by_test_id(tab).first.click()
        page.wait_for_timeout(600)
        thread = page.locator("svg[data-loading-thread]").first
        shown = thread.count() > 0 and thread.is_visible()
        check(f"{tag}/{name}: the thread shows while the screen waits", shown,
              f"{len(held)} answers held")
        if shown:
            holder = page.locator("[role=status]:has(svg[data-loading-thread])").first
            a = holder.evaluate(DASH)
            page.wait_for_timeout(200)
            b = holder.evaluate(DASH)
            if reduced:
                check(f"{tag}/{name}: it stands still, fully drawn", a == b and a.startswith("none"), f"{a}")
            else:
                check(f"{tag}/{name}: it moves between frames", a != b, f"{a} -> {b}")
            # centred in the space the content will take (a dropped size class left it top-left)
            box, svg = holder.bounding_box(), thread.bounding_box()
            off = abs((svg["x"] + svg["width"] / 2) - (box["x"] + box["width"] / 2)) + abs(
                (svg["y"] + svg["height"] / 2) - (box["y"] + box["height"] / 2))
            check(f"{tag}/{name}: it sits centred in the waiting panel", off < 4, f"{off:.0f}px off centre")
            j.shot(page, f"{tag}-{name}-waiting")
        for r in held:
            r.continue_()
        page.unroute(f"**/api/v1/projects/{project}{route}**")
        page.wait_for_timeout(2500)
        check(f"{tag}/{name}: the thread is gone once the answers arrive",
              page.locator("svg[data-loading-thread]").count() == 0)
        page.context.close()


def main(ui="http://127.0.0.1:5191", project="proj-d85a82bf4216"):
    with Judge("d1023-loading-thread", hub=ui, key=KEY) as j:
        drive(j, project, reduced=False)
        drive(j, project, reduced=True)
        if j.errors:
            print("page errors:", *j.errors[:5], sep="\n  ")
    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(*sys.argv[1:])
