"""2026-10-22 tasks sweep, UI (real Chromium against the served bundle, scratch Hub hub-up tk1022 8114).

  board        every card: status line (data-reason, text, title), FR tally (title, data-awaiting-review),
               Retry buttons; then the agent filter and search
  deps         the Dependencies list: banner, groups, each row's text; does the filter/search apply here
  drawer KEY   a task's drawer: Story and Details text, Depends on, integration note, Land
  land KEY     press Land in the drawer; what refusal reaches the screen
  retry KEY    press the card's Retry; what the card and drawer then say

  py -3.11 scripts/drive/s1022_tk_ui.py <what> [key]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "board"
ARG = sys.argv[2] if len(sys.argv) > 2 else None
from s1022_tk_drive import S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]
NAMES = {v: k for k, v in S.items() if isinstance(v, str) and v.startswith("task-")}


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def cards(page):
    for card in page.locator("article.aw-task-card").all():
        tid = card.get_attribute("data-task-id")
        st = card.locator(f"[data-testid='task-card-status-{tid}']")
        reqs = card.locator(".aw-task-card-reqs")
        column = card.evaluate("e => (e.closest('[data-column]') || {}).dataset?.column || ''")
        print(f"CARD {NAMES.get(tid, tid)} col={column} tone={card.get_attribute('data-status-tone')}"
              f" | status={txt(st)} reason={st.first.get_attribute('data-reason') if st.count() else None}"
              f" title={st.first.get_attribute('title') if st.count() else None}"
              f" | reqs={txt(reqs)} awaiting={reqs.first.get_attribute('data-awaiting-review') if reqs.count() else None}"
              f" rtitle={reqs.first.get_attribute('title') if reqs.count() else None}"
              f" | retry={card.get_by_role('button', name='Retry').count()}")


def tasks_tab(j):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    return page


def drawer(page, key):
    tid = S[key]
    page.get_by_test_id(f"task-open-{tid}").click()
    page.wait_for_timeout(2500)
    d = page.get_by_test_id(f"task-drawer-{tid}")
    print(f"[{key}] STORY:", txt(d)[:1800])
    page.get_by_test_id(f"task-view-details-{tid}").click()
    page.wait_for_timeout(1500)
    print(f"[{key}] DETAILS:", txt(d)[:2500])
    print(f"[{key}] depends on:", txt(page.get_by_test_id(f"task-dependencies-{tid}")))
    print(f"[{key}] integration note:", txt(page.get_by_test_id(f"task-integrations-{tid}")))
    return d


with Judge("s1022-tasks", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "board":
        page = tasks_tab(j)
        cards(page)
        j.shot(page, "board")
        page.locator(".aw-board-filters").get_by_role("button", name="beta").click()
        page.wait_for_timeout(800)
        print("filter beta ->", [NAMES.get(c.get_attribute("data-task-id")) for c in page.locator("article.aw-task-card").all()])
        page.get_by_role("button", name="Everyone").click()
        page.get_by_label("Find a task").fill("H")
        page.wait_for_timeout(800)
        print("search 'H' ->", [NAMES.get(c.get_attribute("data-task-id")) for c in page.locator("article.aw-task-card").all()])
    elif WHAT == "deps":
        page = tasks_tab(j)
        page.get_by_role("radio", name="Dependencies").first.click()
        page.wait_for_timeout(1500)
        print("BANNER:", txt(page.locator(".aw-deps-banner")))
        for g in page.locator("section.aw-deps-group").all():
            print("GROUP:", g.get_attribute("aria-label"), "|", txt(g.locator(".aw-deps-group-head")))
            for row in g.locator("li.aw-deps-row").all():
                print("   ROW", NAMES.get((row.get_attribute("data-testid") or "")[10:]), row.get_attribute("data-dependency-state"),
                      "|", " ".join((row.text_content() or "").split()))
        j.shot(page, "deps", full_page=True)
        # Do the agent filter and the search the toolbar still shows apply to this view?
        page.locator(".aw-board-filters").get_by_role("button", name="beta").click()
        page.get_by_label("Find a task").fill("Add")
        page.wait_for_timeout(800)
        print("rows with filter beta + search 'Add':", page.locator("li.aw-deps-row").count(),
              [NAMES.get((r.get_attribute("data-testid") or "")[10:]) for r in page.locator("li.aw-deps-row").all()])
        hm = page.locator("section.aw-deps-group[aria-label='Made by hand'] .aw-deps-group-meta[title]")
        print("hand-made hint title:", hm.first.get_attribute("title") if hm.count() else None)
    elif WHAT == "drawer":
        page = tasks_tab(j)
        drawer(page, ARG)
        j.shot(page, f"drawer_{ARG}")
    elif WHAT == "land":
        page = tasks_tab(j)
        drawer(page, ARG)
        tid = S[ARG]
        land = page.get_by_test_id(f"task-land-{tid}")
        print("land button:", land.count(), txt(land))
        if land.count():
            land.first.click()
            page.wait_for_timeout(3000)
            print("refusal:", txt(page.get_by_test_id(f"task-status-refusal-{tid}")))
            print("land anyway:", page.get_by_test_id(f"task-land-anyway-{tid}").count())
        j.shot(page, f"land_{ARG}")
    elif WHAT == "retry":
        page = tasks_tab(j)
        tid = S[ARG]
        card = page.locator(f"article[data-task-id='{tid}']")
        print("before:", txt(card.locator(f"[data-testid='task-card-status-{tid}']")))
        card.get_by_role("button", name="Retry").click()
        page.wait_for_timeout(5000)
        print("after card:", txt(card.locator(f"[data-testid='task-card-status-{tid}']")), "| retry buttons:",
              card.get_by_role("button", name="Retry").count())
        cards(page)
        j.shot(page, f"retry_{ARG}")
    elif WHAT == "rename":
        page = tasks_tab(j)
        tid = S["H1"]
        page.get_by_test_id(f"task-open-{tid}").click()
        page.wait_for_timeout(1500)
        h = page.get_by_test_id(f"task-drawer-title-{tid}")
        h.click()
        inp = page.get_by_test_id(f"task-drawer-title-input-{tid}")
        print("input focused:", inp.evaluate("e => document.activeElement === e"))
        inp.fill("H1 renamed then cancelled")
        inp.press("Escape")
        page.wait_for_timeout(800)
        print("after Esc: drawer open:", page.get_by_test_id(f"task-drawer-{tid}").count(),
              "title:", txt(page.get_by_test_id(f"task-drawer-title-{tid}")))
        page.get_by_test_id(f"task-drawer-title-{tid}").click()
        inp.fill("   ")
        inp.press("Enter")
        page.wait_for_timeout(800)
        print("blank Enter -> page says:", "cannot be blank" in (page.locator("body").text_content() or ""))
        inp.fill("H1: renamed in the drawer")
        inp.press("Enter")
        page.wait_for_timeout(2000)
        print("after Enter: title:", txt(page.get_by_test_id(f"task-drawer-title-{tid}")),
              "| card:", txt(page.get_by_test_id(f"task-open-{tid}").locator(".aw-task-card-title")))
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        page.get_by_role("radio", name="Dependencies").first.click()
        page.wait_for_timeout(1000)
        print("deps rows naming it:", [" ".join((r.text_content() or "").split())[:90] for r in page.locator("li.aw-deps-row").all() if "renamed" in (r.text_content() or "")])
        j.shot(page, "rename")
    elif WHAT == "links":
        page = j.page(P, mode="light", query="tab=spec")
        page.wait_for_timeout(3000)
        doc = "spec/changes/shop-discount/spec.json"
        t = page.get_by_test_id(f"spec-tree-document-{doc}")
        print("tree item:", t.count())
        if t.count():
            t.first.click()
            page.wait_for_timeout(2500)
        fact = page.get_by_test_id("spec-health-requirements")
        print("requirements fact:", fact.count(), txt(fact))
        if fact.count():
            fact.first.click()
            page.wait_for_timeout(800)
            page.get_by_role("menuitem", name="Show details").click()
            page.wait_for_timeout(1500)
        link = page.get_by_test_id("coverage-tasks-link-FR-1")
        print("FR-1 tasks link:", link.count(), txt(link))
        if link.count():
            link.first.click()
            page.wait_for_timeout(3000)
            print("url:", page.url.split("?")[-1][:200])
            print("banner:", txt(page.get_by_test_id("tasks-requirement-filter-banner")))
            print("cards:", [NAMES.get(c.get_attribute("data-task-id")) for c in page.locator("article.aw-task-card").all()])
            j.shot(page, "links_filtered")
            page.get_by_role("radio", name="Dependencies").first.click()
            page.wait_for_timeout(800)
            print("deps rows under the filter:", page.locator("li.aw-deps-row").count())
            page.get_by_test_id("tasks-requirement-filter-clear").click()
            page.wait_for_timeout(1000)
            print("after clear deps rows:", page.locator("li.aw-deps-row").count())
            page.get_by_role("radio", name="Board").first.click()
            page.wait_for_timeout(800)
            tid = S["t-discount"]
            page.get_by_test_id(f"task-open-{tid}").click()
            page.wait_for_timeout(1500)
            page.get_by_test_id(f"task-view-details-{tid}").click()
            page.wait_for_timeout(800)
            serves = page.get_by_text("FR-1 — shop.price", exact=False)
            print("Serves FR-1 in drawer:", serves.count())
            if serves.count():
                serves.first.click()
                page.wait_for_timeout(3000)
                print("after Serves click url:", page.url.split("?")[-1][:200])
                print("main head:", txt(page.locator("main"))[:300])
            j.shot(page, "links_serves")
    elif WHAT == "delete":
        page = tasks_tab(j)
        tid = S[ARG]
        page.get_by_test_id(f"task-open-{tid}").click()
        page.wait_for_timeout(1500)
        page.get_by_test_id(f"task-view-details-{tid}").click()
        page.wait_for_timeout(800)
        page.get_by_test_id(f"task-delete-{tid}").click()
        page.wait_for_timeout(800)
        print("confirm text:", txt(page.get_by_test_id(f"task-delete-confirm-{tid}")))
        j.shot(page, f"delete_confirm_{ARG}")
        page.get_by_test_id("delete-confirm").click()
        page.wait_for_timeout(3000)
        print("drawer still open:", page.get_by_test_id(f"task-drawer-{tid}").count())
        body = page.locator("body").text_content() or ""
        print("page mentions kept/branch/unmerged:", [w for w in ("kept", "Kept", "branch", "unmerged") if w in body])
        page.goto(page.url.split("?")[0] + f"?project={P}&tab=activity")
        page.wait_for_timeout(4000)
        for label in ("Activity", "Ledger"):
            r = page.get_by_role("radio", name=label)
            if r.count():
                r.first.click()
                page.wait_for_timeout(2000)
            b = page.locator("main").text_content() or ""
            for needle in ("Kept", "kept", "task_checkout_kept", "deleted"):
                i = b.find(needle)
                if i >= 0:
                    print(f"[{label}] {needle}:", " ".join(b[max(0, i - 120):i + 220].split()))
            j.shot(page, f"delete_activity_{label}")
        page.goto(page.url.split("?")[0] + f"?project={P}&tab=environment&section=worktrees")
        page.wait_for_timeout(4000)
        b = page.locator("main").text_content() or ""
        i = b.find("Task deleted")
        print("worktrees 'Task deleted':", " ".join(b[max(0, i - 300):i + 200].split()) if i >= 0 else "<absent>")
        j.shot(page, "delete_worktrees", full_page=True)
