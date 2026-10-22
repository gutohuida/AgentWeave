"""2026-10-22 spec sweep probe (focus), scratch Hub :8121: AW_P=proj-... py -3.11 scripts/drive/s1022_sp_focus.py"""
import sys; sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from s1022_sp_ui import *
with judge() as j:
    page = open_doc(j, "spec/changes/hdr-explore/spec.json")
    d = page.locator("[role=dialog], [role=alertdialog]")
    for tid in ("spec-delete", "spec-archive"):
        page.locator("[data-testid=spec-more-actions]").click(); page.wait_for_timeout(400)
        page.locator(f"[data-testid={tid}]").click()
        for t in (200, 1500):
            page.wait_for_timeout(t)
            print(tid, f"+{t}ms dialogs={d.count()} focus:", focused(page),
                  "in dialog:", page.evaluate("() => !!document.activeElement.closest('[role=dialog],[role=alertdialog]')"))
        page.keyboard.press("Tab"); page.wait_for_timeout(200)
        print("  Tab ->", focused(page), "in dialog:", page.evaluate("() => !!document.activeElement.closest('[role=dialog],[role=alertdialog]')"))
        page.keyboard.press("Escape"); page.wait_for_timeout(600)
        print("  Esc -> dialogs", d.count(), "focus", focused(page))
