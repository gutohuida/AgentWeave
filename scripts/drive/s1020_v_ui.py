"""2026-10-20 sweep, evidence x drift, in a real browser against the served bundle: the Evidence
view with a piece recorded before a criterion amend (awaiting, earlier wording), the coverage bar's
FR-2 row and its pieces, FR-2's story after a criterion-only change, and the drift panel with a
candidate re-raised after "Code corrected" and one on a merged line of work, answered on screen.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_v_ui.py <hub-url>
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
STALE = "ev-a650d4cd3b7a"


def t(scope, tid):
    loc = scope.get_by_test_id(tid)
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else f"<no {tid}>"


def open_doc(j):
    page = j.page(P, mode="light", query=f"tab=spec&document={DOC}")
    page.wait_for_timeout(5000)
    return page


with Judge("s1020-evidence", hub=HUB, key=e2e.key()) as j:
    # --- the Evidence view ---
    page = j.page(P, mode="light", query="tab=spec&view=evidence")
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("evidence rows:", page.locator("[data-testid^='evidence-row-ev-']").count())
    for key in ("earlier", "awaiting", "accepted", "rejected"):
        print(f"  filter {key}:", t(page, f"evidence-filter-{key}"))
    print("stale awaiting row:", t(page, f"evidence-row-{STALE}")[:400])
    j.shot(page, "01_evidence_view", full_page=True)
    page.get_by_test_id(f"evidence-row-toggle-{STALE}").first.click()
    page.wait_for_timeout(2500)
    print("stale row opened:", t(page, f"evidence-row-{STALE}")[:900])
    j.shot(page, "02_stale_row_open", locator=page.get_by_test_id(f"evidence-row-{STALE}").first)
    awaiting = page.get_by_test_id("evidence-filter-awaiting")
    if awaiting.count():
        awaiting.first.click()
        page.wait_for_timeout(1500)
        print("awaiting filter rows:", [r.get_attribute("data-testid") for r in page.locator("[data-testid^='evidence-row-ev-']").all()])

    # --- the document: coverage bar and FR-2's pieces ---
    page = open_doc(j)
    body = " ".join((page.get_by_test_id("spec-page").first.text_content() or "").split()) if page.get_by_test_id("spec-page").count() else ""
    i = body.find("FR-2")
    print("FR-2 on the document:", body[max(0, i - 100): i + 400] if i >= 0 else "<FR-2 absent>")
    toggles = page.get_by_role("button", name="Evidence (", exact=False)
    print("evidence toggles:", toggles.count(), [toggles.nth(k).text_content() for k in range(toggles.count())])
    for k in range(toggles.count()):
        toggles.nth(k).click()
        page.wait_for_timeout(800)
    piece = page.get_by_test_id(f"evidence-piece-{STALE}")
    print("stale piece in the bar:", t(page, f"evidence-piece-{STALE}")[:600])
    if piece.count():
        print("  Accept offered:", piece.get_by_role("button", name="Accept", exact=True).count())
        j.shot(page, "03_bar_stale_piece", locator=piece.first)
    pieces = page.get_by_test_id("evidence-pieces-FR-2")
    if pieces.count():
        j.shot(page, "04_bar_FR2_pieces", locator=pieces.first)

    # --- the drift panel ---
    panel = page.get_by_test_id("spec-drift-panel")
    print("drift panel:", t(page, "spec-drift-panel")[:1500])
    if panel.count():
        panel.first.scroll_into_view_if_needed()
        j.shot(page, "05_drift_panel", locator=panel.first)
        scan = page.get_by_test_id("spec-drift-scan")
        if scan.count():
            scan.first.click()
            page.wait_for_timeout(3000)
            print("after Scan for drift:", t(page, "spec-drift-scanned"))
        rows = page.locator("[data-testid^='spec-drift-row-']")
        ids = [r.get_attribute("data-testid") for r in rows.all()]
        print("drift rows:", ids)
        merged = page.locator("[data-testid='spec-drift-row-drift-9b9299a5f611']")
        if merged.count():
            merged.get_by_role("button", name="No change").click()
            page.wait_for_timeout(2500)
            print("after No change on the merged-line row: rows now",
                  [r.get_attribute("data-testid") for r in page.locator("[data-testid^='spec-drift-row-']").all()])
        j.shot(page, "06_drift_after_answer", locator=panel.first)

    # --- FR-2's story ---
    page = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus=FR-2")
    page.get_by_test_id("requirement-story").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("FR-2 story:", t(page, "requirement-story")[:1500])
    j.shot(page, "07_story_FR2", full_page=True)

st, dl = request("GET", f"/projects/{P}/project/spec/drift?document={DOC}")
print("drift states after:", [(x["id"], x["state"], x["resolution"]) for x in dl["drift"]])
