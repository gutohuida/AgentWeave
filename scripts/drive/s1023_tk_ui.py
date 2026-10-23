"""2026-10-23 tasks sweep, UI (real Chromium against the served bundle, scratch Hub hub-up tk1023 8162).

  board        every named card (not the Z bulk ones): column, status line, assignee, priority
  drawer KEY   a task's drawer: Story and Details text
  rename KEY   Esc cancels, blank Enter, Enter saves; read back through the route
  delete KEY   Delete from the drawer: the confirm's text, then what the page says after
  filters      agent filter + search, and the requirement cross-tab link where one exists

  py -3.11 scripts/drive/s1023_tk_ui.py <what> [key]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "board"
ARG = sys.argv[2] if len(sys.argv) > 2 else None
from s1023_tk_drive import S, api, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]
NAMES = {v: k for k, v in S.items() if isinstance(v, str) and v.startswith("task-")}


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def cards(page):
    for card in page.locator("article.aw-task-card").all():
        tid = card.get_attribute("data-task-id")
        if tid not in NAMES:
            continue
        st = card.locator(f"[data-testid='task-card-status-{tid}']")
        column = card.evaluate("e => (e.closest('[data-column]') || {}).dataset?.column || ''")
        print(f"CARD {NAMES[tid]} col={column} tone={card.get_attribute('data-status-tone')}"
              f" | status={txt(st)} reason={st.first.get_attribute('data-reason') if st.count() else None}"
              f" | meta={txt(card.locator('.aw-task-card-meta'))}")
        reqs = card.locator(".aw-task-card-reqs")
        if reqs.count():
            print(f"     reqs={txt(reqs)} awaiting={reqs.first.get_attribute('data-awaiting-review')}"
                  f" title={reqs.first.get_attribute('title')}")


def tasks_tab(j):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    return page


def open_drawer(page, key):
    tid = S[key]
    page.get_by_test_id(f"task-open-{tid}").click()
    page.wait_for_timeout(2500)
    return page.get_by_test_id(f"task-drawer-{tid}")


with Judge("s1023-tasks", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "board":
        page = tasks_tab(j)
        print("cards on board:", page.locator("article.aw-task-card").count())
        cards(page)
        j.shot(page, "board")
    elif WHAT == "drawer":
        page = tasks_tab(j)
        d = open_drawer(page, ARG)
        tid = S[ARG]
        print(f"[{ARG}] STORY:", txt(d)[:3000])
        page.get_by_test_id(f"task-view-details-{tid}").click()
        page.wait_for_timeout(1500)
        print(f"[{ARG}] DETAILS:", txt(d)[:2500])
        j.shot(page, f"drawer_{ARG}")
    elif WHAT == "rename":
        page = tasks_tab(j)
        tid = S[ARG]
        open_drawer(page, ARG)
        h = page.get_by_test_id(f"task-drawer-title-{tid}")
        before = txt(h)
        h.click()
        inp = page.get_by_test_id(f"task-drawer-title-input-{tid}")
        print("input focused:", inp.evaluate("e => document.activeElement === e"))
        inp.fill("renamed then cancelled")
        inp.press("Escape")
        page.wait_for_timeout(800)
        print("after Esc: drawer open:", page.get_by_test_id(f"task-drawer-{tid}").count(),
              "| title:", txt(page.get_by_test_id(f"task-drawer-title-{tid}")), "| before:", before)
        print("route title after Esc:", api("GET", f"~/tasks/{tid}")[1]["title"])
        page.get_by_test_id(f"task-drawer-title-{tid}").click()
        inp.fill("   ")
        inp.press("Enter")
        page.wait_for_timeout(1000)
        body = page.locator("body").text_content() or ""
        print("blank Enter -> page mentions blank/empty:", [w for w in ("blank", "empty", "required") if w in body],
              "| route title:", api("GET", f"~/tasks/{tid}")[1]["title"])
        inp2 = page.get_by_test_id(f"task-drawer-title-input-{tid}")
        if not inp2.count():
            page.get_by_test_id(f"task-drawer-title-{tid}").click()
        page.get_by_test_id(f"task-drawer-title-input-{tid}").fill(before + " (renamed)")
        page.get_by_test_id(f"task-drawer-title-input-{tid}").press("Enter")
        page.wait_for_timeout(2000)
        print("after Enter: drawer title:", txt(page.get_by_test_id(f"task-drawer-title-{tid}")),
              "| card:", txt(page.get_by_test_id(f"task-open-{tid}").locator(".aw-task-card-title")),
              "| route:", api("GET", f"~/tasks/{tid}")[1]["title"])
        j.shot(page, f"rename_{ARG}")
    elif WHAT == "delete":
        page = tasks_tab(j)
        tid = S[ARG]
        open_drawer(page, ARG)
        page.get_by_test_id(f"task-view-details-{tid}").click()
        page.wait_for_timeout(800)
        page.get_by_test_id(f"task-delete-{tid}").click()
        page.wait_for_timeout(800)
        print("confirm text:", txt(page.get_by_test_id(f"task-delete-confirm-{tid}")))
        j.shot(page, f"delete_confirm_{ARG}")
        page.get_by_test_id("delete-confirm").click()
        page.wait_for_timeout(3500)
        print("drawer still open:", page.get_by_test_id(f"task-drawer-{tid}").count())
        body = page.locator("body").text_content() or ""
        print("page mentions kept/branch/unmerged:", [w for w in ("kept", "Kept", "branch", "unmerged") if w in body])
        print("card still on board:", page.get_by_test_id(f"task-open-{tid}").count())
        j.shot(page, f"delete_after_{ARG}")
        page.goto(page.url.split("?")[0] + f"?project={P}&tab=activity")
        page.wait_for_timeout(4000)
        for label in ("Activity", "Logs"):
            r = page.get_by_role("radio", name=label)
            if r.count():
                r.first.click()
                page.wait_for_timeout(2000)
            b = page.locator("main").text_content() or ""
            for needle in ("Kept", "kept", "deleted", "free to start", "released"):
                i = b.find(needle)
                if i >= 0:
                    print(f"[{label}] {needle}:", " ".join(b[max(0, i - 160):i + 220].split()))
            j.shot(page, f"delete_activity_{label}")
    elif WHAT == "land":
        page = tasks_tab(j)
        tid = S[ARG]
        open_drawer(page, ARG)
        page.get_by_test_id(f"task-view-details-{tid}").click()
        page.wait_for_timeout(1500)
        d = page.get_by_test_id(f"task-drawer-{tid}")
        b = txt(d)
        i = b.find("Approving")
        print("preview note:", b[i:i + 160] if i >= 0 else "<absent>")
        land = page.get_by_test_id(f"task-land-{tid}")
        print("land button:", land.count())
        if land.count():
            land.first.click()
            page.wait_for_timeout(3000)
            print("refusal:", txt(page.get_by_test_id(f"task-status-refusal-{tid}")))
            print("drawer status now:", api("GET", f"~/tasks/{tid}")[1]["status"])
        j.shot(page, f"land_{ARG}")
    elif WHAT == "filters":
        page = tasks_tab(j)
        flt = page.locator(".aw-board-filters")
        print("filter buttons:", [" ".join((b.text_content() or "").split()) for b in flt.get_by_role("button").all()])
        flt.get_by_role("button", name="beta").click()
        page.wait_for_timeout(800)
        print("filter beta ->", [NAMES.get(c.get_attribute("data-task-id"), "Z") for c in page.locator("article.aw-task-card").all()])
        page.get_by_role("button", name="Everyone").click()
        page.get_by_label("Find a task").fill("sub()")
        page.wait_for_timeout(800)
        print("search 'sub()' ->", [NAMES.get(c.get_attribute("data-task-id"), "Z") for c in page.locator("article.aw-task-card").all()])
        print("url:", page.url.split("?")[-1])
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        print("after reload search box:", page.get_by_label("Find a task").input_value(),
              "| cards:", page.locator("article.aw-task-card").count())
