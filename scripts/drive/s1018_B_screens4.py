from s1018_B_lib import e2e, P, OUT, rows  # noqa
from s1018_B_screens import open_doc, note, safe, notes  # noqa
from uiharness import Judge
D = "spec/changes/interval-intersection-for-the-intervals-library/spec.json"; E1 = "ev-99582050603e"
with Judge("s1018-sweepB4", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
    page = open_doc(j, D)
    page.get_by_test_id("spec-coverage").locator("button").first.click(); page.wait_for_timeout(800)
    page.get_by_test_id("coverage-evidence-toggle-FR-1").first.click(); page.wait_for_timeout(1000)
    piece = page.get_by_test_id(f"evidence-piece-{E1}")
    def flow():
        piece.get_by_role("button", name="Reject…").click(); page.wait_for_timeout(400)
        btn = piece.get_by_role("button", name="Reject", exact=True)
        note("reject disabled with empty reason: " + str(btn.is_disabled()))
        piece.locator("input, textarea").first.fill("   ")
        note("reject disabled with blank reason: " + str(btn.is_disabled()))
        piece.locator("input, textarea").first.fill("intersection is not implemented yet; this piece proves nothing")
        btn.click(); page.wait_for_timeout(2000)
        j.shot(page, "40_after_reject", full_page=True)
        note("after: " + (page.get_by_test_id(f"evidence-piece-{E1}").text_content() or "")[:400])
    safe("reject", flow)
    note("DB: " + str(rows("select id, review_state from requirement_evidence where id=?", E1)))
    page.context.close()
(OUT / "screens4.txt").write_text("\n".join(notes), encoding="utf-8")
