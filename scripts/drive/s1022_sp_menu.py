"""2026-10-22 spec sweep probe (menu), scratch Hub :8121: AW_P=proj-... py -3.11 scripts/drive/s1022_sp_menu.py"""
import sys; sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from s1022_sp_ui import *
with judge() as j:
    page = open_doc(j, "spec/changes/hdr-main/spec.json", mode="dark", width=900)
    j.shot(page, "narrow_dark")
    h = page.locator("[data-testid=spec-document-header]")
    box = h.bounding_box(); print("header box at 900:", box)
    facts = page.locator("[data-slot=health-fact]")
    print("facts:", [norm(facts.nth(i).text_content()) for i in range(facts.count())])
    # keyboard: focus More actions, open with Enter, arrow to Archive, Enter
    page.locator("[data-testid=spec-more-actions]").focus()
    page.keyboard.press("Enter"); page.wait_for_timeout(500)
    print("menu open focus:", focused(page))
    for _ in range(6):
        page.keyboard.press("ArrowDown"); page.wait_for_timeout(120)
        f = focused(page)
        if "Archive" in (f or ""): break
    print("on:", focused(page))
    page.keyboard.press("Enter"); page.wait_for_timeout(1200)
    d = page.locator("[role=dialog], [role=alertdialog]")
    print("archive dialog:", d.count(), d.count() and norm(d.first.text_content())[:600], "focus:", focused(page))
    j.shot(page, "archive_dialog")
    page.keyboard.press("Escape"); page.wait_for_timeout(600)
    print("after Esc focus:", focused(page))
    # Delete document dialog
    page.locator("[data-testid=spec-more-actions]").click(); page.wait_for_timeout(400)
    page.locator("[data-testid=spec-delete]").click(); page.wait_for_timeout(1200)
    print("delete dialog:", d.count() and norm(d.first.text_content())[:900], "focus:", focused(page))
    j.shot(page, "delete_dialog")
    page.keyboard.press("Escape"); page.wait_for_timeout(600)
    print("after Esc focus:", focused(page))
    # Start a flow dialog
    page.locator(".aw-spec-actions button").filter(has_text="Start a flow").click(); page.wait_for_timeout(1200)
    print("flow dialog:", d.count() and norm(d.first.text_content())[:900], "focus:", focused(page))
    j.shot(page, "flow_dialog")
    page.keyboard.press("Escape"); page.wait_for_timeout(600)
    print("after Esc focus:", focused(page))
