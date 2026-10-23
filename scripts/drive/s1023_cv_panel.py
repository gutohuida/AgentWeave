"""Conversations & composer, 2026-10-23: the side panel's six tab kinds (specs, files, loops and a
spec, file and loop detail), Insert into composer, the files tab on a binary and a huge file, and a
narrow window turning the panel into a drawer.

    py -3.11 scripts/drive/s1023_cv_panel.py
"""

import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

LOOP = "loop-aa06f2001908"


def norm(s):
    return " ".join((s or "").split())


def step(name, fn):
    print(f"\n--- {name}")
    try:
        fn()
    except Exception as exc:  # a step that cannot be reached is a result, not a crash
        print(f"  !! {name} not reached: {type(exc).__name__}: {str(exc)[:300]}")
        traceback.print_exc(limit=1)


def tabs(page):
    loc = page.locator("[data-testid^=panel-tab-]")
    ids = [loc.nth(i).get_attribute("data-testid") for i in range(loc.count())]
    return [i for i in ids if not i.startswith(("panel-tab-close", "panel-tab-strip", "panel-tab-content", "panel-tab-add"))]


def add_tab(page, label):
    page.get_by_test_id("panel-tab-add").click()
    page.wait_for_timeout(400)
    item = page.get_by_test_id(f"panel-tab-add-{label.lower()}")
    if item.count():
        item.click()
    else:  # already open: the plus offers only what is not open, so go to its tab
        page.keyboard.press("Escape")
        page.get_by_test_id(f"panel-tab-{label.lower()}").click()
    page.wait_for_timeout(1200)


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="agent=alpha")
    page.wait_for_timeout(5000)
    ws = page.get_by_test_id("conversation-workspace")

    def open_panel():
        page.get_by_test_id("conversation-more").click()
        page.wait_for_timeout(400)
        page.get_by_test_id("conversation-toggle-panel").click()
        page.wait_for_timeout(1500)
        print("  workspace:", ws.get_attribute("data-panel"), ws.get_attribute("data-layout"))
        empty = page.get_by_test_id("panel-empty-state")
        print("  empty state:", norm(empty.text_content()) if empty.count() else None)
        j.shot(page, "panel_01_open")

    def specs():
        page.get_by_test_id("panel-launch-specs").click()
        page.wait_for_timeout(1500)
        content = page.get_by_test_id("panel-tab-content")
        print("  specs index:", norm(content.text_content())[:400])
        page.get_by_test_id("spec-tree-document-spec/changes/silver-fenrir/spec.json").click()
        page.wait_for_timeout(2000)
        print("  tabs:", tabs(page))
        print("  spec detail:", norm(page.get_by_test_id("panel-tab-content").text_content())[:300])
        j.shot(page, "panel_02_spec")

    def files():
        add_tab(page, "Files")
        print("  files index:", norm(page.get_by_test_id("files-index-tab").text_content())[:300])
        page.get_by_test_id("file-tree-file-secret.txt").click()
        page.wait_for_timeout(1500)
        print("  file tab:", norm(page.get_by_test_id("file-tab").text_content())[:200])
        page.get_by_role("button", name="Insert into composer").click()
        page.wait_for_timeout(800)
        print("  composer value after Insert:", repr(page.locator("[data-slot=composer] textarea").last.input_value()))
        j.shot(page, "panel_03_file_insert")

    def file_kinds():
        for path in ("blob.bin", "huge.txt", "docs/notes.md"):
            add_tab(page, "Files")
            tree = page.get_by_test_id(f"file-tree-file-{path}")
            if not tree.count():
                page.get_by_test_id("file-tree-directory-docs").click()
                page.wait_for_timeout(500)
            tree.click()
            page.wait_for_timeout(1500)
            ft = page.get_by_test_id("file-tab")
            print(f"  {path}:", norm(ft.text_content())[:300])
            j.shot(page, f"panel_04_{path.replace('/', '_')}")

    def loops():
        add_tab(page, "Loops")
        print("  loops index:", norm(page.get_by_test_id("loops-index-tab").text_content())[:300])
        page.get_by_test_id(f"loops-index-row-{LOOP}").click()
        page.wait_for_timeout(1500)
        print("  loop detail:", norm(page.get_by_test_id("panel-tab-content").text_content())[:400])
        j.shot(page, "panel_05_loop")

    def kinds():
        ids = tabs(page)
        print("  open tabs:", ids)
        found = {k for k in ("specs", "files", "loops") if f"panel-tab-{k}" in ids}
        for prefix in ("spec:", "file:", "loop:"):
            if any(i.startswith(f"panel-tab-{prefix}") for i in ids):
                found.add(prefix)
        print("  KINDS FOUND:", sorted(found), "of 6")

    def narrow():
        page.set_viewport_size({"width": 820, "height": 900})
        page.wait_for_timeout(1500)
        print("  narrow workspace:", ws.get_attribute("data-panel"), ws.get_attribute("data-layout"))
        j.shot(page, "panel_06_narrow_closed")
        opener = page.get_by_test_id("conversation-open-document")
        print("  drawer opener:", opener.count(), norm(opener.text_content()) if opener.count() else None)
        if opener.count():
            opener.click()
            page.wait_for_timeout(1200)
            dlg = page.get_by_role("dialog")
            print("  drawer dialogs:", dlg.count(), "| focused:", page.evaluate("document.activeElement && (document.activeElement.getAttribute('data-testid') || document.activeElement.tagName)"))
            j.shot(page, "panel_07_drawer")
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
            print("  after Escape, dialogs:", page.get_by_role("dialog").count(), "| focus:",
                  page.evaluate("document.activeElement && (document.activeElement.getAttribute('data-testid') || document.activeElement.tagName)"))

    for name, fn in (("open panel", open_panel), ("specs", specs), ("files + insert", files),
                     ("binary/huge/non-ascii", file_kinds), ("loops", loops), ("kinds", kinds), ("narrow", narrow)):
        step(name, fn)
    print("console errors:", j.errors[:5])
