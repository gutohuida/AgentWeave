"""Conversations & composer, 2026-10-23: rename (header and API refusals), Ctrl+K palette, the Hide
diagnostics preference across a reload, archive from the header and unarchive from the rail.

    py -3.11 scripts/drive/s1023_cv_lifecycle.py
"""

import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import B, P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402

CONV = "conv-9c177acf95dd"
NAME = "Renamed by drive — café ✓"


def norm(s):
    return " ".join((s or "").split())


def step(name, fn):
    print(f"\n--- {name}")
    try:
        fn()
    except Exception as exc:
        print(f"  !! {name} not reached: {type(exc).__name__}: {str(exc)[:300]}")
        traceback.print_exc(limit=1)


def row(c):
    return q("select lifecycle, title, title_set_by_operator from conversations where id=?", c)[0]


def focus(page):
    return page.evaluate("document.activeElement && (document.activeElement.getAttribute('data-testid') || document.activeElement.getAttribute('aria-label') || document.activeElement.tagName)")


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)

    def rename_ui():
        page.locator("[data-slot=convbar-title]").click()
        inp = page.get_by_label("Conversation title")
        inp.fill(NAME)
        inp.press("Enter")
        page.wait_for_timeout(1500)
        print("  DB:", row(CONV))
        print("  header:", norm(page.locator("[data-slot=convbar-title]").text_content()))
        print("  rail:", norm(page.get_by_test_id(f"rail-conversation-{CONV}").text_content()))
        # A blank rename from the header
        page.locator("[data-slot=convbar-title]").click()
        inp = page.get_by_label("Conversation title")
        inp.fill("   ")
        inp.press("Enter")
        page.wait_for_timeout(1500)
        alerts = page.get_by_role("alert")
        print("  blank rename -> DB:", row(CONV)["title"], "| header:", norm(page.locator("[data-slot=convbar-title]").text_content()),
              "| alerts:", [norm(alerts.nth(i).text_content()) for i in range(alerts.count())])
        j.shot(page, "life_01_rename")

    def rename_api():
        for title in ("", "   ", "x" * 121, "x" * 120, NAME):
            st, res = req("PATCH", f"{B}/agent/alpha/conversations/{CONV}", {"title": title})
            print(f"  PATCH title len={len(title)} -> {st} {str(res)[:160] if st >= 300 else res.get('title', '')[:40]}")
        st, res = req("PATCH", f"{B}/agent/alpha/conversations/conv-nope", {"title": "x"})
        print("  unknown conversation ->", st, str(res)[:200])
        st, res = req("PATCH", f"{B}/agent/beta/conversations/{CONV}", {"title": "x"})
        print("  another agent's conversation ->", st, str(res)[:200])

    def palette():
        page.locator("body").click(position={"x": 700, "y": 400})
        opener = focus(page)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(800)
        print("  focus in palette:", focus(page))
        page.keyboard.type("café", delay=50)
        page.wait_for_timeout(800)
        items = page.locator("[cmdk-item]")
        print("  items for 'café':", [norm(items.nth(i).text_content())[:70] for i in range(items.count())])
        j.shot(page, "life_02_palette")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        print("  after Escape focus:", focus(page), "(opener was", opener, ")")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(600)
        page.keyboard.type("say hi", delay=40)
        page.wait_for_timeout(700)
        items = page.locator("[cmdk-item]")
        print("  items for 'say hi':", [norm(items.nth(i).text_content())[:70] for i in range(items.count())])
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        print("  after Enter URL:", page.url, "| focus:", focus(page))
        page.goto(page.url.split("?")[0] + f"?project={P}&agent=alpha&conversation={CONV}", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

    def diagnostics():
        page.get_by_test_id("conversation-more").click()
        page.wait_for_timeout(400)
        item = page.get_by_role("menuitem", name="Hide diagnostics")
        print("  menu has Hide diagnostics:", item.count())
        item.click()
        page.wait_for_timeout(400)
        print("  localStorage:", page.evaluate("localStorage.getItem('aw.conversation.diagnostics.v1')"))
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        page.get_by_test_id("conversation-more").click()
        page.wait_for_timeout(400)
        print("  after reload, menu offers:", [norm(t) for t in page.get_by_role("menuitem").all_text_contents() if "iagnostics" in t])
        page.get_by_role("menuitem", name="Show diagnostics").click()
        page.wait_for_timeout(400)

    def archive():
        page.get_by_test_id("conversation-more").click()
        page.wait_for_timeout(400)
        page.get_by_role("menuitem", name="Archive conversation").click()
        page.wait_for_timeout(1500)
        dlg = page.get_by_role("alertdialog")
        if not dlg.count():
            dlg = page.get_by_role("dialog")
        print("  confirm:", norm(dlg.last.text_content())[:300] if dlg.count() else None)
        if dlg.count():
            btns = dlg.last.get_by_role("button")
            print("  confirm buttons:", [norm(btns.nth(i).text_content()) for i in range(btns.count())], "| focus:", focus(page))
            dlg.last.get_by_role("button", name="Archive").last.click()
            page.wait_for_timeout(1500)
        print("  DB:", row(CONV))
        print("  URL:", page.url)
        main = page.locator("main").first
        print("  main:", norm(main.text_content())[:400])
        j.shot(page, "life_03_archived")

    def unarchive():
        menu = page.get_by_test_id("agent-menu-" + P + "-alpha")
        menu.click()
        page.wait_for_timeout(400)
        items = page.get_by_role("menuitem")
        print("  agent menu:", [norm(t) for t in items.all_text_contents()])
        page.get_by_role("menuitem", name="Show archived").first.click()
        page.wait_for_timeout(800)
        r = page.get_by_test_id(f"rail-archived-{CONV}")
        print("  archived row:", r.count(), norm(r.text_content()) if r.count() else None)
        r.hover()
        page.get_by_test_id(f"rail-archived-{CONV}-menu").click()
        page.wait_for_timeout(400)
        page.get_by_test_id(f"rail-archived-{CONV}-menu-unarchive").click()
        page.wait_for_timeout(1500)
        print("  DB:", row(CONV))
        print("  rail row now:", page.get_by_test_id(f"rail-conversation-{CONV}").count())
        j.shot(page, "life_04_unarchived")

    for name, fn in (("rename (UI)", rename_ui), ("rename (API refusals)", rename_api), ("Ctrl+K", palette),
                     ("Hide diagnostics", diagnostics), ("archive", archive), ("unarchive", unarchive)):
        step(name, fn)
    print("console errors:", j.errors[:6])
