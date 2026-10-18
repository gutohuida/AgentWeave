"""Sweep B screens 2: coverage bar + Evidence toggle, task drawer story, Activity ledger, hand-written wait."""
import sys

from s1018_B_lib import e2e, P, OUT  # noqa
from s1018_B_screens import open_doc, note, text, safe, notes  # noqa  (module guarded by which)
from uiharness import Judge

CH = "spec/changes/scarlet-minotaur/spec.json"
CAP = "spec/capabilities/interval-arithmetic/spec.json"
which = sys.argv[1] if len(sys.argv) > 1 else "all"

with Judge("s1018-sweepB2", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
    if which in ("all", "coverage"):
        for path, tag in ((CH, "change"), (CAP, "cap")):
            page = open_doc(j, path)
            safe("expand coverage", lambda: (page.get_by_test_id("spec-coverage").locator("button").first.click(), page.wait_for_timeout(1200)))
            j.shot(page, f"20_{tag}_coverage_open", full_page=True)
            note(f"{tag} coverage open: " + text(page, "spec-coverage")[:1500])
            for ident in ("FR-1", "FR-2", "FR-3", "FR-4"):
                t = page.get_by_test_id(f"coverage-evidence-toggle-{ident}")
                if t.count():
                    safe(f"toggle {ident}", lambda: (t.first.click(), page.wait_for_timeout(1200)))
                    note(f"{tag} {ident} pieces: " + text(page, f"evidence-pieces-{ident}")[:1200])
            j.shot(page, f"21_{tag}_coverage_evidence", full_page=True)
            page.context.close()
    if which in ("all", "tasks"):
        page = j.page(P, mode="light", query="tab=tasks")
        page.wait_for_timeout(3000)
        j.shot(page, "22_tasks_board", full_page=True)
        opener = page.get_by_test_id("task-open-task-26c07baafa80")
        if opener.count():
            opener.first.click()
            page.wait_for_timeout(2500)
            j.shot(page, "23_task_drawer", full_page=True)
            note("drawer: " + (page.locator("[role='dialog']").first.text_content() or "")[:3000])
        else:
            note("no task-open-task-26c07baafa80 on the board")
        page.context.close()
    if which in ("all", "activity"):
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(3500)
        j.shot(page, "24_activity", full_page=True)
        note("activity: " + (page.locator("main").first.text_content() or "")[:4000])
        page.context.close()
    if which in ("all", "handwritten"):
        page = open_doc(j, "spec/changes/hand-written-fmt/spec.json")
        page.wait_for_timeout(15000)
        j.shot(page, "25_handwritten_after_15s")
        note("hand-written body after 15s: " + (page.get_by_test_id("spec-page").first.text_content() or "")[:800])
        page.context.close()

(OUT / f"screens2_{which}.txt").write_text("\n".join(notes), encoding="utf-8")
