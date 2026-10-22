"""2026-10-22 evidence sweep in Chromium against the served bundle (after s1022_ev_drive.py):
the Evidence view with F852's no-work piece and the landed FR-2 piece opened, Task grouping, the
view by keyboard (Tab to a row, Enter opens it, the filter chips), the FR-2 story, and the coverage
bar's pieces for FR-2/FR-3.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1022_ev_ui.py <hub-url>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import MEMO, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB = sys.argv[1]
M = json.loads(MEMO.read_text())
P, DOC = M["project"], M["doc"]
NOWORK, WORK = M["nowork_pieces"][0], M["work_pieces"][0]


def t(scope, tid):
    loc = scope.get_by_test_id(tid)
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else f"<no {tid}>"


with Judge("s1022-evidence", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec&view=evidence")
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("groups:", [page.locator("[data-testid^='evidence-group-']").nth(k).get_attribute("data-testid")
                      for k in range(page.locator("[data-testid^='evidence-group-']").count())])
    for ev in (NOWORK, WORK):
        page.get_by_test_id(f"evidence-row-toggle-{ev}").click()
        page.wait_for_timeout(2500)
        print(f"\n{ev} opened:", t(page, f"evidence-row-{ev}")[:1400])
        j.shot(page, f"01_open_{ev}", locator=page.get_by_test_id(f"evidence-row-{ev}").first)

    # Task grouping
    page.get_by_test_id("evidence-group-task").click()
    page.wait_for_timeout(1200)
    heads = page.locator(".aw-evidence-group-head")
    print("\ntask grouping heads:", [" ".join((heads.nth(k).text_content() or "").split()) for k in range(heads.count())])
    j.shot(page, "02_grouped_by_task", full_page=True)
    link = page.get_by_test_id(f"evidence-row-task-{WORK}")
    print("row task link:", link.first.text_content() if link.count() else "<none>")

    # Keyboard: a fresh page, Tab until a row toggle has focus, Enter opens it, Enter again closes.
    page = j.page(P, mode="light", query="tab=spec&view=evidence")
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    reached = None
    for k in range(60):
        page.keyboard.press("Tab")
        tid = page.evaluate("document.activeElement && document.activeElement.getAttribute('data-testid')")
        if tid and tid.startswith("evidence-row-toggle-"):
            reached = (k + 1, tid)
            break
    print("\nkeyboard: first row toggle after", reached)
    if reached:
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        ev = reached[1].removeprefix("evidence-row-toggle-")
        print("  after Enter, data-open =", page.get_by_test_id(f"evidence-row-{ev}").get_attribute("data-open"))
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        print("  after Enter again, data-open =", page.get_by_test_id(f"evidence-row-{ev}").get_attribute("data-open"))
        focus_ok = page.evaluate("document.activeElement && document.activeElement.getAttribute('data-testid')")
        print("  focus stays on:", focus_ok)
    # filter chips by keyboard
    page.get_by_test_id("evidence-filter-accepted").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    print("  accepted filter rows:", page.locator("[data-testid^='evidence-row-ev-']").count(),
          "chip:", t(page, "evidence-filter-accepted"))
    page.get_by_test_id("evidence-search").fill("total")
    page.wait_for_timeout(800)
    print("  accepted + 'total':", page.locator("[data-testid^='evidence-row-ev-']").count(),
          "|", t(page, "evidence-empty")[:200])
    j.shot(page, "03_filtered_empty")

    for ident in ("FR-2", "FR-3"):
        page = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus={ident}")
        page.get_by_test_id("requirement-story").wait_for(timeout=30000)
        page.wait_for_timeout(2000)
        print(f"\n{ident} story:", t(page, "requirement-story")[:1200])
        j.shot(page, f"04_story_{ident}", full_page=True)

    page = j.page(P, mode="light", query=f"tab=spec&document={DOC}")
    page.get_by_test_id("spec-health-requirements").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("\nhealth line:", " | ".join(t(page, f"spec-health-{k}") for k in ("requirements", "drift", "tasks")))
    page.get_by_test_id("spec-health-requirements").click()
    page.wait_for_timeout(800)
    page.get_by_role("menuitem", name="Show details").click()
    page.wait_for_timeout(1500)
    for ident in ("FR-2", "FR-3"):
        tg = page.get_by_test_id(f"coverage-evidence-toggle-{ident}")
        if tg.count():
            tg.first.click()
            page.wait_for_timeout(1500)
            print(f"  bar pieces {ident}:", t(page, f"evidence-pieces-{ident}")[:700])
            pc = page.get_by_test_id(f"evidence-pieces-{ident}")
            if pc.count():
                j.shot(page, f"05_bar_{ident}", locator=pc.first)
        else:
            print(f"  no evidence toggle for {ident}")
