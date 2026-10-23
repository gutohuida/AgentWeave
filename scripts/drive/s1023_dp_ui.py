"""Dependencies sweep 2026-10-23, UI: the Dependencies list against the API, and the drawer's
"Depends on" picker refusing a cycle (Chromium against the served bundle, scratch Hub :8161).

  deps            banner, groups, rows (with dependency state); the API's view of the same tasks;
                  then whether the agent chip and "Find a task" filter the list (F914)
  cycle A C       open A's drawer, pick C (which already waits on A), Add: what reaches the screen
  drawer T        a task drawer's Details text and Depends on block

  py -3.11 scripts/drive/s1023_dp_ui.py <what> [ids...]
"""

import sys

from s1023_dp_common import BASE, PROJECT, sc
from uiharness import Judge

WHAT = sys.argv[1] if len(sys.argv) > 1 else "deps"
ARGS = sys.argv[2:]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def tasks_tab(j):
    page = j.page(PROJECT, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    return page


with Judge("s1023-dp", hub=sc.hub(), key=sc.CFG["key"]) as j:
    if WHAT == "deps":
        code, pg = sc.api("GET", f"{BASE}/tasks?limit=500")
        api_rows = {t["id"]: t for t in pg["tasks"]}
        page = tasks_tab(j)
        page.get_by_role("radio", name="Dependencies").first.click()
        page.wait_for_timeout(2000)
        print("BANNER:", txt(page.locator(".aw-deps-banner")))
        seen = set()
        for g in page.locator("section.aw-deps-group").all():
            print("GROUP:", g.get_attribute("aria-label"), "|", txt(g.locator(".aw-deps-group-head")))
            for row in g.locator("li.aw-deps-row").all():
                tid = (row.get_attribute("data-testid") or "")[9:]
                seen.add(tid)
                t = api_rows.get(tid, {})
                api_pre = [(p["title"][:14], p["status"]) for p in t.get("prerequisites") or []]
                print(f"   ROW {tid} ui_state={row.get_attribute('data-dependency-state')} "
                      f"api_state={t.get('dependency_state')} api_status={t.get('status')} "
                      f"api_prereqs={api_pre}\n       | {' '.join((row.text_content() or '').split())}")
        print("in API, not on screen:", sorted(set(api_rows) - seen))
        j.shot(page, "deps", full_page=True)
        page.locator(".aw-board-filters").get_by_role("button", name="beta").click()
        page.get_by_label("Find a task").fill("notes")
        page.wait_for_timeout(1000)
        print("F914: rows with chip beta + search 'notes':", page.locator("li.aw-deps-row").count())
        hm = page.locator("section.aw-deps-group[aria-label='Made by hand'] .aw-deps-group-meta[title]")
        print("F915 hand-made hint title:", hm.first.get_attribute("title") if hm.count() else None)
    elif WHAT == "overlap":
        # Two unordered same-file pairs; propose through the API, then press Approve on screen.
        from s1023_dp_common import doc_route, make_doc

        path, code, res, _ = make_doc("Two same-file pairs", [
            {"key": "t1", "title": "Add add()", "description": "add", "requirements": ["r1"],
             "files": ["lib.py"]},
            {"key": "t2", "title": "Add sub()", "description": "sub", "requirements": ["r2"],
             "files": ["lib.py"]},
            {"key": "t3", "title": "Add fmt()", "description": "fmt", "requirements": ["r3"],
             "files": ["util.py"]},
            {"key": "t4", "title": "Add parse()", "description": "parse", "requirements": ["r4"],
             "files": ["util.py"]},
        ])
        print("PUT warnings:", [w["message"] for w in res.get("warnings", [])])
        sc.api("POST", doc_route("close-exploration", path))
        code, res = sc.api("POST", doc_route("propose", path))
        print("propose overlap warnings:",
              [w["message"] for w in res.get("warnings", []) if w["code"] == "unordered_file_overlap"])
        page = j.page(PROJECT, mode="light", query="tab=spec")
        page.wait_for_timeout(4000)
        page.get_by_test_id(f"spec-tree-document-{path}").first.click()
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="Approve", exact=True).first.click()
        page.wait_for_timeout(2500)
        print("ON SCREEN:", txt(page.get_by_test_id("approval-warning-unordered_file_overlap")))
        j.shot(page, "overlap_approve")
    elif WHAT in ("cycle", "drawer"):
        tid = ARGS[0]
        page = tasks_tab(j)
        page.get_by_test_id(f"task-open-{tid}").first.click()
        page.wait_for_timeout(2500)
        details = page.get_by_test_id(f"task-view-details-{tid}")
        if details.count():
            details.click()
            page.wait_for_timeout(1500)
        print("DEPENDS ON:", txt(page.get_by_test_id(f"task-dependencies-{tid}")))
        if WHAT == "drawer":
            print("DRAWER:", txt(page.get_by_test_id(f"task-drawer-{tid}"))[:2500])
        else:
            other = ARGS[1]
            page.get_by_test_id(f"task-dependency-picker-{tid}").select_option(other)
            page.get_by_test_id(f"task-dependency-add-{tid}").click()
            page.wait_for_timeout(2000)
            print("REFUSAL ON SCREEN:", txt(page.get_by_test_id(f"task-dependency-refusal-{tid}")))
        j.shot(page, f"{WHAT}_{tid}")
