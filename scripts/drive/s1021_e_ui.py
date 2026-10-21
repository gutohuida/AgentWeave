"""2026-10-21 evidence sweep, in Chromium against the served bundle: the Evidence view with builder's
no-commit FR-3 piece opened (F761's residue: what its diff shows), FR-3's story after a
criterion-only change and FR-1's after a rewording (F833), the coverage bar's Evidence toggle, and
the drift candidate answered on screen.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_e_ui.py <hub-url>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from s1020_v_lib import MEMO, request  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB = sys.argv[1]
M = json.loads(MEMO.read_text())
P, DOC = M["project"], M["doc"]
NOCOMMIT = M["f761_pieces"][0]
DRIFT = M["drift"]


def t(scope, tid):
    loc = scope.get_by_test_id(tid)
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else f"<no {tid}>"


with Judge("s1021-evidence", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec&view=evidence")
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("evidence rows:", page.locator("[data-testid^='evidence-row-ev-']").count())
    print("no-commit row:", t(page, f"evidence-row-{NOCOMMIT}")[:400])
    tog = page.get_by_test_id(f"evidence-row-toggle-{NOCOMMIT}")
    if tog.count() and "--doc-only" not in sys.argv:
        tog.first.click()
        page.wait_for_timeout(3000)
        print("no-commit row opened:", t(page, f"evidence-row-{NOCOMMIT}")[:1200])
        j.shot(page, "01_nocommit_row_open", locator=page.get_by_test_id(f"evidence-row-{NOCOMMIT}").first)

    for ident in ([] if "--doc-only" in sys.argv else ["FR-3", "FR-1"]):
        page = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus={ident}")
        page.get_by_test_id("requirement-story").wait_for(timeout=30000)
        page.wait_for_timeout(2000)
        print(f"{ident} story:", t(page, "requirement-story")[:1200])
        j.shot(page, f"02_story_{ident}", full_page=True)

    page = j.page(P, mode="light", query=f"tab=spec&document={DOC}")
    page.get_by_test_id("spec-health-requirements").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("health line:", " | ".join(t(page, f"spec-health-{k}") for k in ("requirements", "drift", "tasks")))
    # The ui-finesse page keeps the coverage bar and the drift panel behind the health line's menus.
    page.get_by_test_id("spec-health-requirements").click()
    page.wait_for_timeout(800)
    print("requirements menu:", " ".join((page.locator(".aw-health-pop").first.text_content() or "").split())[:400])
    page.get_by_role("menuitem", name="Show details").click()
    page.wait_for_timeout(1500)
    toggles = page.locator("[data-testid^='coverage-evidence-toggle-']")
    print("evidence toggles on the document:", toggles.count(), [toggles.nth(k).text_content() for k in range(toggles.count())])
    for ident in ("FR-1", "FR-3"):
        tg = page.get_by_test_id(f"coverage-evidence-toggle-{ident}")
        if tg.count():
            tg.first.click()
            page.wait_for_timeout(1200)
            print(f"  pieces {ident}:", t(page, f"evidence-pieces-{ident}")[:600])
            pc = page.get_by_test_id(f"evidence-pieces-{ident}")
            if pc.count():
                j.shot(page, f"03_bar_pieces_{ident}", locator=pc.first)
    page.get_by_test_id("spec-health-drift").click()
    page.wait_for_timeout(800)
    print("drift menu:", " ".join((page.locator(".aw-health-pop").first.text_content() or "").split())[:300])
    page.get_by_role("menuitem", name="Show details").click()
    page.wait_for_timeout(1500)
    panel = page.get_by_test_id("spec-drift-panel")
    print("drift panel:", t(page, "spec-drift-panel")[:800])
    row = page.locator(f"[data-testid='spec-drift-row-{DRIFT}']")
    if row.count():
        row.first.scroll_into_view_if_needed()
        j.shot(page, "04_drift_open", locator=panel.first)
        row.get_by_role("button", name="Code corrected").click()
        page.wait_for_timeout(2500)
        print("after Code corrected:", t(page, "spec-drift-panel")[:600])
        j.shot(page, "05_drift_answered", locator=panel.first)

st, dl = request("GET", f"/projects/{P}/project/spec/drift?document={DOC}")
print("drift after:", [(x["id"], x["state"], x["resolution"]) for x in dl["drift"]])
st, cov = request("GET", f"/projects/{P}/project/spec/coverage?document={DOC}")
print("coverage after:", [(e["identifier"], e["state"]) for e in cov["requirements"]])
