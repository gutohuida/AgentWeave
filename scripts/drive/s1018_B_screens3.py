"""Sweep B screens 3: decide evidence in the app, place-under dialog, document browser + corpus strip."""
from s1018_B_lib import e2e, P, OUT, rows  # noqa
from s1018_B_screens import open_doc, note, text, safe, notes  # noqa
from uiharness import Judge

D = "spec/changes/interval-intersection-for-the-intervals-library/spec.json"
E1, E2 = "ev-99582050603e", "ev-15b0a9274f6c"

with Judge("s1018-sweepB3", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
    page = open_doc(j, D)
    safe("expand coverage", lambda: (page.get_by_test_id("spec-coverage").locator("button").first.click(), page.wait_for_timeout(1000)))
    for ident in ("FR-1", "FR-2"):
        safe(f"toggle {ident}", lambda: (page.get_by_test_id(f"coverage-evidence-toggle-{ident}").first.click(), page.wait_for_timeout(1000)))
    j.shot(page, "30_awaiting_pieces", full_page=True)
    piece = page.get_by_test_id(f"evidence-piece-{E1}")
    note("piece E1: " + (piece.text_content() or "")[:600] if piece.count() else "no piece E1")

    def reject_flow():
        piece.get_by_role("button", name="Reject…").click()
        page.wait_for_timeout(400)
        btn = piece.get_by_role("button", name="Reject", exact=True)
        note("reject disabled with empty reason: " + str(btn.is_disabled()))
        piece.locator("input, textarea").first.fill("intersection is not implemented yet; this piece proves nothing")
        btn.click()
        page.wait_for_timeout(2000)
        j.shot(page, "31_after_reject", full_page=True)
    safe("reject flow", reject_flow)

    def accept_flow():
        p2 = page.get_by_test_id(f"evidence-piece-{E2}")
        note("piece E2 before: " + (p2.text_content() or "")[:400])
        p2.get_by_role("button", name="Accept").click()
        page.wait_for_timeout(2000)
        note("piece E2 after: " + (page.get_by_test_id(f"evidence-piece-{E2}").text_content() or "")[:400])
        err = page.get_by_test_id(f"evidence-error-{E2}")
        note("E2 error: " + ((err.text_content() or "") if err.count() else "none"))
    safe("accept flow", accept_flow)
    note("DB: " + str(rows("select id, review_state from requirement_evidence where id in (?,?)", E1, E2)))

    def place_under():
        page.get_by_test_id("spec-place-under").first.click()
        page.wait_for_timeout(800)
        j.shot(page, "32_place_under")
        sel = page.get_by_test_id("spec-place-under-select")
        opts = sel.locator("option").all_text_contents() if sel.count() else []
        note("place-under options: " + str(opts)[:600])
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        note("place-under form after Escape: " + str(page.get_by_test_id("spec-place-under-form").count()))
    safe("place under", place_under)
    page.context.close()

    # The document browser and its corpus strip.
    page = j.page(P, mode="dark", query="tab=spec")
    page.get_by_test_id("spec-page").wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    safe("open browser", lambda: (page.get_by_text("Specification", exact=True).first.click(), page.wait_for_timeout(2000)))
    j.shot(page, "33_document_browser", full_page=True)
    note("browser: " + text(page, "spec-document-browser")[:1500])
    note("corpus strip: " + text(page, "spec-corpus-strip")[:1200])
    page.context.close()

(OUT / "screens3.txt").write_text("\n".join(notes), encoding="utf-8")
