"""Spec documents x Corpus & folding sweep 2026-10-22, UI (Chromium, served bundle on the scratch
Hub :8121, profile sp1022): the rebuilt Spec header (SpecDocumentHeader, SpecHealthLine,
SpecDocumentList, SpecPhaseParts).

  header <path>   open the document from the list; the breadcrumb, title, phase, rigor, kind; each
                  health fact's label and its popover text; the overflow menu's items; keyboard
  list            the document list's groups, counts, phase words, folds
  click <path> <testid>...  open the document and click each testid in turn, printing the header

    AW_P=proj-... py -3.11 scripts/drive/s1022_sp_ui.py <phase> [args]
"""

import json
import sys

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from s1022_sp_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def focused(page):
    return page.evaluate(
        "() => { const e = document.activeElement; if (!e) return null;"
        " return (e.tagName + ' ' + (e.getAttribute('data-testid') || e.getAttribute('aria-label') || '') + ' ' + (e.textContent || '').trim().slice(0, 50)); }"
    )


def judge():
    st = json.loads(e2e.STATE.read_text())
    key = e2e._key() if hasattr(e2e, "_key") else e2e.key()
    return Judge("s1022-spec", hub=st["hub"], key=key)


def open_doc(j, path, mode="light", width=1440):
    page = j.page(P, mode=mode, width=width, query="tab=spec")
    page.wait_for_timeout(4000)
    row = page.locator(f"[data-testid='spec-list-row-{path}']")
    if row.count():
        row.first.click()
    else:
        print("!! no list row for", path)
    page.wait_for_timeout(3500)
    return page


def popover_text(page):
    pop = page.locator("[role=menu]")
    return [norm(pop.nth(i).text_content()) for i in range(pop.count())]


def header(path, mode="light", width="1440"):
    with judge() as j:
        page = open_doc(j, path, mode, int(width))
        h = page.locator("[data-testid=spec-document-header]")
        print("URL", page.url)
        print("header:", norm(h.text_content())[:600] if h.count() else None)
        j.shot(page, f"header_{mode}_{width}")
        facts = page.locator("[data-slot=health-fact]")
        for i in range(facts.count()):
            f = facts.nth(i)
            tid = f.get_attribute("data-testid")
            print(f"FACT {tid} tone={f.get_attribute('data-tone')} label={norm(f.text_content())!r}")
            f.click()
            page.wait_for_timeout(700)
            print("   popover:", popover_text(page))
            j.shot(page, f"fact_{tid}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            print("   after Esc focus:", focused(page))
        more = page.locator("[data-testid=spec-more-actions]")
        if more.count():
            more.click()
            page.wait_for_timeout(500)
            print("MORE menu:", popover_text(page))
            j.shot(page, "more_menu")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            print("   after Esc focus:", focused(page))
        rig = page.locator("[data-testid=spec-rigor]")
        if rig.count():
            rig.click()
            page.wait_for_timeout(500)
            print("RIGOR menu:", popover_text(page))
            page.keyboard.press("Escape")
        crumb = page.locator("[data-testid=spec-document-breadcrumb]")
        print("breadcrumb:", crumb.count() and norm(crumb.text_content()), crumb.count() and crumb.get_attribute("title"))
        msgs = page.locator(".aw-spec-messages")
        print("messages:", msgs.count() and norm(msgs.text_content())[:800])
        reason = page.locator(".aw-spec-reason")
        print("primary reason:", [norm(reason.nth(i).text_content()) for i in range(reason.count())])
        btns = page.locator(".aw-spec-actions button")
        print("action buttons:", [norm(btns.nth(i).text_content()) or btns.nth(i).get_attribute("aria-label") for i in range(btns.count())])


def list_(mode="light"):
    with judge() as j:
        page = j.page(P, mode=mode, query="tab=spec")
        page.wait_for_timeout(4500)
        lst = page.locator("[data-testid=spec-document-list]")
        print("list:", norm(lst.text_content())[:1500] if lst.count() else None)
        groups = page.locator(".aw-spec-list-group")
        for i in range(groups.count()):
            g = groups.nth(i)
            print(" group", g.get_attribute("data-group"), "|", norm(g.text_content())[:300])
        j.shot(page, "list")


def click(path, *testids):
    with judge() as j:
        page = open_doc(j, path)
        for tid in testids:
            loc = page.locator(f"[data-testid='{tid}']")
            print("click", tid, "count", loc.count())
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(1500)
            h = page.locator("[data-testid=spec-document-header]")
            print("  header:", norm(h.text_content())[:700] if h.count() else None)
            print("  menus:", popover_text(page))
            j.shot(page, f"click_{tid}")



def fact(path, testid, item_text):
    """Open a health fact's popover and pick the item whose text is `item_text`; print what follows."""
    with judge() as j:
        page = open_doc(j, path)
        page.locator(f"[data-testid='{testid}']").click()
        page.wait_for_timeout(600)
        page.locator("[role=menuitem]").filter(has_text=item_text).first.click()
        page.wait_for_timeout(2500)
        alerts = page.locator("[role=status], [role=alert], .aw-toast, [data-sonner-toast]")
        print("toasts/alerts:", [norm(alerts.nth(i).text_content())[:300] for i in range(alerts.count())])
        det = page.locator("[data-testid^=spec-detail-]")
        print("detail:", det.count() and norm(det.first.text_content())[:1200])
        print("focus:", focused(page))
        j.shot(page, f"factpick_{testid}")



def picker(path, home=None):
    """Open the document search from the breadcrumb (and by Ctrl+Shift+K), read the corpus strip,
    press Rebuild index, choose `home` if asked, adopt the untracked document if offered."""
    with judge() as j:
        page = open_doc(j, path)
        page.keyboard.press("Control+Shift+K")
        page.wait_for_timeout(1200)
        dlg = page.locator("[role=dialog]")
        print("Ctrl+Shift+K dialog:", dlg.count(), "focus:", focused(page))
        if not dlg.count():
            page.locator("[data-testid=spec-document-breadcrumb]").click()
            page.wait_for_timeout(1200)
            print("breadcrumb dialog:", dlg.count(), "focus:", focused(page))
        strip = page.locator("[data-testid=spec-corpus-strip]")
        print("strip:", strip.count() and norm(strip.text_content())[:800])
        print("dialog text:", norm(dlg.first.text_content())[:1500] if dlg.count() else None)
        j.shot(page, "picker")
        rb = page.locator("[data-testid=spec-corpus-rebuild]")
        if rb.count():
            rb.click()
            page.wait_for_timeout(2500)
            print("after Rebuild:", norm(strip.text_content())[:900])
            j.shot(page, "picker_rebuilt")
            if home:
                sel = strip.locator("select")
                print("selects:", sel.count())
                if sel.count():
                    sel.first.select_option(home)
                    page.wait_for_timeout(300)
                    btns = strip.locator("button")
                    print("strip buttons:", [norm(btns.nth(i).text_content()) for i in range(btns.count())])
                    strip.locator("button").filter(has_text="Rebuild").first.click()
                    page.wait_for_timeout(2500)
                    print("after home:", norm(strip.text_content())[:900])
                    j.shot(page, "picker_home")
        adopt = page.locator("button").filter(has_text="Adopt")
        print("adopt buttons:", adopt.count(), [norm(adopt.nth(i).text_content()) for i in range(adopt.count())])
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        print("after Esc: dialogs", page.locator("[role=dialog]").count(), "focus:", focused(page))


if __name__ == "__main__":
    name = sys.argv[1]
    {"list": list_}.get(name, globals().get(name))(*sys.argv[2:])
