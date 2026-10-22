"""2026-10-22 spec sweep probe (keys), scratch Hub :8121: AW_P=proj-... py -3.11 scripts/drive/s1022_sp_keys.py"""
import sys; sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from s1022_sp_ui import *
with judge() as j:
    page = open_doc(j, "spec/changes/hdr-proposed/spec.json")
    def dialogs():
        d = page.locator("[role=dialog]")
        return [(d.nth(i).get_attribute("aria-label") or norm(d.nth(i).locator("h2, [id$=title]").first.text_content() if d.nth(i).locator("h2, [id$=title]").count() else "")[:40]) for i in range(d.count())]
    page.keyboard.press("Control+Shift+K"); page.wait_for_timeout(1200)
    print("Ctrl+Shift+K ->", dialogs(), "focus", focused(page))
    j.shot(page, "ctrl_shift_k")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    print("Esc ->", dialogs(), "focus", focused(page))
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    print("Esc ->", dialogs(), "focus", focused(page))
    page.locator("[data-testid=spec-document-breadcrumb]").click(); page.wait_for_timeout(1200)
    print("breadcrumb ->", dialogs(), "focus", focused(page))
    strip = page.locator("[data-testid=spec-corpus-strip]")
    page.locator("[data-testid=spec-corpus-rebuild]").click(); page.wait_for_timeout(2000)
    strip.locator("select").first.select_option("spec/roadmaps/hdr-road/spec.json"); page.wait_for_timeout(300)
    strip.locator("button").filter(has_text="Rebuild with this home").click(); page.wait_for_timeout(2500)
    print("after home:", norm(strip.text_content())[:700])
    j.shot(page, "home_chosen")
    page.keyboard.press("Escape"); page.wait_for_timeout(500)
    print("Esc ->", dialogs(), "focus", focused(page))
    page.wait_for_timeout(1500)
    facts = page.locator("[data-slot=health-fact]")
    print("facts now:", [norm(facts.nth(i).text_content()) for i in range(facts.count())])
