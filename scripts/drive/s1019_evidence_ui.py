"""Sweep 2026-10-19: the Evidence view, URL focus, a requirement's story and the coverage bar's
controls on a stale piece, in a real browser against the served bundle.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_evidence_ui.py <project-id> <hub-url> <doc>
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, HUB, DOC = sys.argv[1], sys.argv[2], sys.argv[3]


def t(page, tid):
    loc = page.get_by_test_id(tid)
    return (loc.first.text_content() or "").strip() if loc.count() else f"<no {tid}>"


with Judge("s1019-evidence", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec&view=evidence")
    page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    rows = page.locator("[data-testid^='evidence-row-ev-']")
    print("evidence rows:", rows.count())
    for tid in ("evidence-filter-earlier", "evidence-filter-awaiting", "evidence-filter-accepted", "evidence-filter-rejected"):
        print(" ", tid, "->", t(page, tid))
    j.shot(page, "01_evidence_view", full_page=True)

    for ev, label in (("ev-c06a5106567f", "02_nonascii_path"), ("ev-b98dba63fe9a", "03_diff_500"),
                      ("ev-7b1c83591732", "04_no_commit_piece"), ("ev-17c09db60e4a", "05_cafe_mojibake")):
        page.get_by_test_id(f"evidence-row-toggle-{ev}").first.click()
        page.wait_for_timeout(2500)
        proof = page.get_by_test_id(f"evidence-proof-{ev}")
        print(f"open {ev}: proof={proof.count()}")
        if proof.count():
            print("   proof text:", (proof.first.text_content() or "")[:600].replace(chr(10), " "))
            j.shot(page, label, locator=page.get_by_test_id(f"evidence-row-{ev}").first)
        page.get_by_test_id(f"evidence-row-toggle-{ev}").first.click()
        page.wait_for_timeout(500)
    p = j.page(P, mode="light", query="tab=spec&view=evidence&focus=ev-c06a5106567f")
    p.wait_for_timeout(3000)
    print("focus=<piece id>:", t(p, "evidence-focus"), "| empty:", t(p, "evidence-empty")[:80])

    p = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus=FR-1")
    p.get_by_test_id("requirement-story").wait_for(timeout=30000)
    p.wait_for_timeout(2000)
    print("story statement:", t(p, "requirement-story-statement"))
    print("story text:", (p.get_by_test_id("requirement-story").first.text_content() or "")[:900].replace("\n", " "))
    j.shot(p, "06_story_FR1", full_page=True)
    p = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus=FR-3")
    p.get_by_test_id("requirement-story").wait_for(timeout=30000)
    p.wait_for_timeout(2000)
    print("story FR-3 drift:", t(p, "requirement-story-drift")[:400])
    j.shot(p, "07_story_FR3", full_page=True)
    p = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOC}&focus=FR-99")
    p.wait_for_timeout(4000)
    print("story FR-99:", t(p, "requirement-story-error")[:300], "| story present:", p.get_by_test_id("requirement-story").count())
    j.shot(p, "08_story_unknown", full_page=True)

    # the coverage bar on the document: Accept offered on an awaiting earlier-wording piece?
    p = j.page(P, mode="light", query="tab=spec")
    p.get_by_test_id("spec-page").wait_for(timeout=30000)
    p.wait_for_timeout(1500)
    parts = DOC.split("/")
    target = p.get_by_test_id(f"spec-tree-document-{DOC}")
    for i in range(2, len(parts)):
        if target.count():
            break
        p.get_by_test_id("spec-tree-directory-" + "/".join(parts[:i])).first.click()
        p.wait_for_timeout(700)
    target.first.click()
    p.wait_for_timeout(3000)
    btn = p.get_by_role("button", name="Evidence (4)")
    print("FR-1 evidence toggles:", p.get_by_role("button", name="Evidence (", exact=False).count())
    toggles = p.get_by_role("button", name="Evidence (", exact=False)
    if toggles.count():
        toggles.first.click()
        p.wait_for_timeout(1500)
        piece = p.get_by_test_id("evidence-piece-ev-fef4ef8f7dd3")
        print("awaiting stale piece shown:", piece.count(), (piece.first.text_content() or "")[:300] if piece.count() else "")
        if piece.count():
            accept = piece.get_by_role("button", name="Accept", exact=True)
            print("  Accept offered:", accept.count())
            if accept.count():
                accept.first.click()
                p.wait_for_timeout(1500)
                print("  after Accept:", t(p, "evidence-error-ev-fef4ef8f7dd3")[:300])
        j.shot(p, "09_coverage_bar_stale_accept", full_page=True)
