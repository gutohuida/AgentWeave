"""Spec documents x Corpus & folding sweep 2026-10-23, UI (Chromium, served bundle on the scratch
Hub :8114, profile sp1023):

  reports <path>  the amendments panel after a real reporter's two cannot-satisfy reports were
                  answered (one rejected, one accepted)
  delete <path>   More actions -> Delete document… -> the confirm (focus) -> confirm; then the
                  page: SpecDeletedNote, the header, the URL (F829)

    AW_P=proj-... py -3.11 scripts/drive/s1023_sp_ui.py <phase> <path>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_sp_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def focused(page):
    return page.evaluate(
        "() => { const e = document.activeElement; if (!e) return null;"
        " return (e.tagName + ' ' + (e.getAttribute('data-testid') || e.getAttribute('aria-label') || '')"
        " + ' ' + (e.textContent || '').trim().slice(0, 50)); }"
    )


def open_doc(j, path):
    page = j.page(P, mode="light", query="tab=spec")
    page.wait_for_timeout(4000)
    row = page.locator(f"[data-testid='spec-list-row-{path}']")
    if row.count():
        row.first.click()
    else:
        # Never act on whatever document happens to be open (2026-10-23: a re-run on an already
        # deleted document deleted the default one instead).
        raise SystemExit(f"!! no list row for {path}; refusing to act on another document")
    page.wait_for_timeout(3500)
    return page


def reports(path):
    with Judge("s1023-spec", hub=e2e.hub(), key=e2e.key()) as j:
        page = open_doc(j, path)
        panel = page.locator("[data-testid=spec-amendments]")
        print("PANEL count", panel.count())
        if panel.count():
            panel.first.scroll_into_view_if_needed()
            print("PANEL:", norm(panel.first.text_content())[:2500])
        task_rows = page.locator("text=Make count_words")
        print("task mentions:", task_rows.count())
        j.shot(page, "01_reports")
        print("errors:", j.errors[:5])


def delete(path):
    with Judge("s1023-spec", hub=e2e.hub(), key=e2e.key()) as j:
        page = open_doc(j, path)
        print("URL before", page.url)
        print("HEADER before:", norm(page.locator("[data-testid=spec-document-header]").text_content())[:300])
        page.locator("[data-testid=spec-more-actions]").click()
        page.wait_for_timeout(500)
        page.locator("[data-testid=spec-delete]").click()
        page.wait_for_timeout(800)
        dialog = page.get_by_role("alertdialog").or_(page.get_by_role("dialog"))
        print("DIALOG:", norm(dialog.first.text_content())[:800] if dialog.count() else None)
        print("focus in dialog:", focused(page))
        j.shot(page, "02_delete_confirm")
        dialog.first.get_by_role("button", name="Delete document").click()
        page.wait_for_timeout(4000)
        note = page.locator("[data-testid=spec-deleted-note]")
        print("NOTE:", norm(note.text_content()) if note.count() else None)
        h = page.locator("[data-testid=spec-document-header]")
        print("HEADER after:", norm(h.text_content())[:300] if h.count() else None)
        print("URL after", page.url)
        j.shot(page, "03_after_delete")
        print("errors:", j.errors[:8])


if __name__ == "__main__":
    {"reports": reports, "delete": delete}[sys.argv[1]](sys.argv[2])
