"""Sweep B: open the Spec page screens on scratch :8032 in a real browser and screenshot each state."""
import sys
import traceback

from s1018_B_lib import e2e, P, OUT  # noqa
from uiharness import Judge

notes = []
which = sys.argv[1] if len(sys.argv) > 1 else "all"


def note(msg):
    print(msg)
    notes.append(msg)


def text(page, tid):
    loc = page.get_by_test_id(tid)
    return (loc.first.text_content() or "").strip() if loc.count() else f"<no {tid}>"


def safe(name, fn):
    try:
        fn()
    except Exception as exc:  # a failed step is recorded, never hidden
        note(f"!! {name}: {exc!r}"[:600])
        traceback.print_exc(limit=1)


def open_doc(j, path, mode="light", width=1440):
    page = j.page(P, mode=mode, width=width, query="tab=spec")
    page.get_by_test_id("spec-page").wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    parts = path.split("/")
    target = page.get_by_test_id(f"spec-tree-document-{path}")
    for i in range(2, len(parts)):
        if target.count():
            break
        page.get_by_test_id("spec-tree-directory-" + "/".join(parts[:i])).first.click()
        page.wait_for_timeout(700)
    target.first.click()
    page.wait_for_timeout(2500)
    return page


CH = "spec/changes/scarlet-minotaur/spec.json"
CAP = "spec/capabilities/interval-arithmetic/spec.json"
RM = "spec/changes/coral-griffin/spec.json"
WS = "spec/changes/with space/spec.json"
HW = "spec/changes/hand-written-fmt/spec.json"
BIG = "spec/changes/teal-kraken/spec.json"

if __name__ == "__main__":
    with Judge("s1018-sweepB", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
        def browser():
            page = j.page(P, mode="light", query="tab=spec")
            page.get_by_test_id("spec-page").wait_for(timeout=30000)
            page.wait_for_timeout(2500)
            j.shot(page, "01_spec_landing", full_page=True)
            safe("drift items expand", lambda: (page.get_by_text("spec manifest drift item").first.click(), page.wait_for_timeout(800)))
            j.shot(page, "01b_manifest_drift_open")
            note("manifest drift: " + (page.get_by_test_id("spec-document-panel").first.text_content() or "")[:1500])
            safe("browser open", lambda: (page.get_by_test_id("spec-rail-tree").first.click(), page.wait_for_timeout(1500)))
            j.shot(page, "01c_after_rail_tree", full_page=True)
            note("corpus strip: " + text(page, "spec-corpus-strip")[:800])
            note("untracked: " + text(page, "spec-corpus-untracked")[:500])
            note("corpus diagnostics: " + text(page, "spec-corpus-diagnostics")[:800])
            page.context.close()

        def change():
            page = open_doc(j, CH)
            j.shot(page, "02_change_top")
            j.shot(page, "02_change_full", full_page=True)
            note("phase: " + text(page, "spec-phase")[:400])
            note("rigor: " + text(page, "spec-rigor")[:300])
            safe("rigor history", lambda: (page.get_by_test_id("spec-rigor-history-toggle").click(), page.wait_for_timeout(800)))
            note("rigor history: " + text(page, "spec-rigor-history")[:800])
            note("coverage: " + text(page, "spec-coverage")[:800])
            safe("evidence toggle FR-2", lambda: (page.get_by_test_id("coverage-evidence-toggle-FR-2").click(), page.wait_for_timeout(1200)))
            j.shot(page, "03_change_coverage_evidence", full_page=True)
            note("evidence pieces FR-2: " + text(page, "evidence-pieces-FR-2")[:1500])
            note("approval report: " + text(page, "spec-approval-report")[:800])
            note("amendments: " + text(page, "spec-amendments")[:1200])
            note("drift panel: " + text(page, "spec-drift-panel")[:1200])
            safe("drift scan", lambda: (page.get_by_test_id("spec-drift-scan").click(), page.wait_for_timeout(2000)))
            note("drift after scan: " + text(page, "spec-drift-panel")[:800])
            j.shot(page, "04_change_after_scan", full_page=True)
            page.context.close()

        def capability():
            page = open_doc(j, CAP)
            j.shot(page, "05_capability_full", full_page=True)
            note("cap coverage: " + text(page, "spec-coverage")[:800])
            safe("retired toggle", lambda: (page.get_by_test_id("spec-retired-toggle").click(), page.wait_for_timeout(1000)))
            note("retired: " + text(page, "spec-retired")[:800])
            safe("retire dialog", lambda: (page.get_by_test_id("spec-retire-capability").click(), page.wait_for_timeout(1000)))
            j.shot(page, "06_retire_dialog")
            note("retire dialog absorbed-by: " + text(page, "retire-absorbed-by")[:400])
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            note("retire dialog after Escape present: " + str(page.get_by_test_id("retire-confirm").count()))
            page.context.close()

        def roadmap():
            page = open_doc(j, RM)
            j.shot(page, "07_roadmap_full", full_page=True)
            note("roadmap frame text: " + (page.locator("body").text_content() or "")[:100])
            page.context.close()

        def proposals():
            page = open_doc(j, WS)
            j.shot(page, "08_proposals_full", full_page=True)
            note("proposals: " + text(page, "spec-proposals-panel")[:1200])
            page.context.close()

        def handwritten():
            page = open_doc(j, HW)
            j.shot(page, "09_handwritten_full", full_page=True)
            note("hand-written coverage: " + text(page, "spec-coverage")[:500])
            note("hand-written phase: " + text(page, "spec-phase")[:300])
            page.context.close()

        def big():
            page = open_doc(j, BIG)
            j.shot(page, "10_big_top")
            safe("fold open", lambda: (page.get_by_test_id("fold-open").click(), page.wait_for_timeout(1500)))
            j.shot(page, "11_fold_dialog")
            note("fold state/error: " + text(page, "fold-state")[:400] + " | " + text(page, "fold-error")[:400])
            page.keyboard.press("Escape")
            page.context.close()

        def evidence_browser():
            page = j.page(P, mode="dark", query="tab=spec&view=evidence")
            safe("evidence browser", lambda: page.get_by_test_id("evidence-browser").wait_for(timeout=30000))
            page.wait_for_timeout(1500)
            j.shot(page, "12_evidence_browser", full_page=True)
            note("evidence browser: " + text(page, "evidence-browser")[:1500])
            rows = page.locator("[data-testid^='evidence-row-toggle-']")
            if rows.count():
                rows.first.click()
                page.wait_for_timeout(1200)
                j.shot(page, "13_evidence_open", full_page=True)
                note("open piece: " + text(page, "evidence-browser")[:2500])
            page.context.close()

        def story():
            page = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={CH}&focus=FR-1")
            safe("story", lambda: page.get_by_test_id("requirement-story").wait_for(timeout=30000))
            page.wait_for_timeout(2500)
            j.shot(page, "14_requirement_story", full_page=True)
            note("story: " + text(page, "requirement-story")[:2500])
            page.context.close()

        steps = dict(browser=browser, change=change, capability=capability, roadmap=roadmap, proposals=proposals,
                     handwritten=handwritten, big=big, evidence=evidence_browser, story=story)
        for name, fn in steps.items():
            if which in ("all", name):
                safe(name, fn)

    (OUT / f"screens_{which}.txt").write_text("\n".join(notes), encoding="utf-8")
