"""2026-10-22 spec sweep probe (actions), scratch Hub :8121: AW_P=proj-... py -3.11 scripts/drive/s1022_sp_actions.py"""
import sys; sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from s1022_sp_ui import *
P2 = "spec/changes/hdr-proposed/spec.json"
with judge() as j:
    page = open_doc(j, P2)
    # Approve -> gaps -> Approve anyway
    page.locator(".aw-spec-actions button").filter(has_text="Approve").first.click(); page.wait_for_timeout(2500)
    h = page.locator("[data-testid=spec-document-header]")
    print("after Approve:", norm(h.text_content())[:900])
    j.shot(page, "approve_gaps")
    aa = page.locator("button").filter(has_text="Approve anyway")
    print("approve anyway buttons:", aa.count(), "focus:", focused(page))
    if aa.count():
        aa.first.click(); page.wait_for_timeout(3000)
        print("after anyway:", norm(h.text_content())[:900])
        j.shot(page, "approved_anyway")
    # Rigor: promote to gate from the chip
    page.locator("[data-testid=spec-rigor]").click(); page.wait_for_timeout(500)
    page.locator("[role=menuitemradio]").filter(has_text="Gate").click(); page.wait_for_timeout(1000)
    conf = page.locator("[data-testid=spec-rigor-confirm]")
    print("rigor confirm:", conf.count() and norm(conf.text_content()), "focus:", focused(page))
    if conf.count():
        conf.locator("button").filter(has_text="Confirm").click(); page.wait_for_timeout(2000)
    print("after gate:", norm(h.text_content())[:600])
    # Demote back without reason
    page.locator("[data-testid=spec-rigor]").click(); page.wait_for_timeout(500)
    page.locator("[role=menuitemradio]").filter(has_text="Sketch").click(); page.wait_for_timeout(1000)
    print("demote confirm:", norm(conf.text_content()) if conf.count() else None)
    btn = conf.locator("button").filter(has_text="Confirm")
    print("confirm disabled w/o reason:", btn.is_disabled() if btn.count() else None)
    page.keyboard.press("Escape"); page.wait_for_timeout(400)
    print("after Esc confirm still shown:", conf.count())
    conf.locator("input").fill("drive: back to sketch"); btn.click(); page.wait_for_timeout(2000)
    print("after demote:", norm(h.text_content())[:500])
    # History in the menu?
    page.locator("[data-testid=spec-more-actions]").click(); page.wait_for_timeout(500)
    print("MORE:", popover_text(page))
    hist = page.locator("[role=menuitem]").filter(has_text="History")
    if hist.count():
        hist.first.click(); page.wait_for_timeout(1200)
        hl = page.locator("[data-testid=spec-rigor-history]")
        print("history:", hl.count() and norm(hl.text_content()))
    else:
        page.keyboard.press("Escape")
    j.shot(page, "rigor_history")
