"""Conversations & composer, 2026-10-23: the composer's triggers (@file, $skill, /model), the three
pills, a draft across a reload, and a refused first send from an armed exploration (beta archived
between page load and Send) -- does the exploration it created get deleted?

    py -3.11 scripts/drive/s1023_cv_composer.py [triggers|refused]
"""

import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import B, DIR, P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def step(name, fn):
    print(f"\n--- {name}")
    try:
        fn()
    except Exception as exc:
        print(f"  !! {name} not reached: {type(exc).__name__}: {str(exc)[:300]}")
        traceback.print_exc(limit=1)


def box(page):
    return page.locator("[data-slot=composer] textarea").last


def options(page):
    lb = page.get_by_role("listbox")
    if not lb.count():
        return None
    opts = lb.last.get_by_role("option")
    return [norm(opts.nth(i).text_content()) for i in range(opts.count())]


def type_trigger(page, text):
    b = box(page)
    b.fill("")
    b.click()
    b.type(text, delay=60)
    page.wait_for_timeout(700)
    return options(page)


which = sys.argv[1] if len(sys.argv) > 1 else "triggers"
with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    if which == "triggers":
        page = j.page(P, mode="light", query="agent=alpha")
        page.wait_for_timeout(5000)

        def at_file():
            print("  '@sec' options:", type_trigger(page, "look at @sec"))
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            print("  after Enter:", repr(box(page).input_value()))
            print("  '@' (all) options:", type_trigger(page, "@"))
            print("  '@caf' options:", type_trigger(page, "@caf"))
            j.shot(page, "composer_01_at")

        def skill():
            print("  '$' options:", type_trigger(page, "$"))
            j.shot(page, "composer_02_skill")
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            print("  after Enter:", repr(box(page).input_value()))

        def slash():
            print("  '/mo' options:", type_trigger(page, "/mo"))
            page.keyboard.press("Enter")
            page.wait_for_timeout(800)
            print("  after Enter value:", repr(box(page).input_value()))
            menu = page.get_by_role("menu")
            dlg = page.get_by_role("dialog")
            lb = page.get_by_role("listbox")
            print("  opened: menus", menu.count(), "dialogs", dlg.count(), "listboxes", lb.count(),
                  "| focus:", page.evaluate("document.activeElement && (document.activeElement.getAttribute('aria-label') || document.activeElement.textContent || '').slice(0,80)"))
            if menu.count():
                print("  menu text:", norm(menu.last.text_content())[:400])
            j.shot(page, "composer_03_slash_model")
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

        def pills():
            row = page.locator("[data-slot=composer-control-row-leading]").last
            btns = row.get_by_role("button")
            names = [norm(btns.nth(i).text_content()) for i in range(btns.count())]
            print("  pills:", names)
            for i, name in enumerate(names):
                if not name or name.startswith("Explore"):
                    continue
                btns.nth(i).click()
                page.wait_for_timeout(600)
                menu = page.get_by_role("menu")
                lb = page.get_by_role("listbox")
                dlg = page.get_by_role("dialog")
                target = menu.last if menu.count() else (lb.last if lb.count() else (dlg.last if dlg.count() else None))
                print(f"  [{name}] ->", norm(target.text_content())[:500] if target else "nothing opened")
                j.shot(page, f"composer_04_pill_{i}")
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)

        def draft():
            b = box(page)
            b.fill("draft survives reload QZX-77")
            page.wait_for_timeout(1500)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            print("  after reload:", repr(box(page).input_value()))
            j.shot(page, "composer_05_draft_after_reload")
            box(page).fill("")
            page.wait_for_timeout(1200)

        for name, fn in (("@file", at_file), ("$skill", skill), ("/model", slash), ("pills", pills), ("draft", draft)):
            step(name, fn)

    else:
        before = {d["path"] for d in req("GET", f"{B}/project/documents")[1]["documents"]}
        page = j.page(P, mode="light", query="agent=beta&conversation=__new__")
        page.wait_for_timeout(5000)
        try:
            page.get_by_test_id("composer-start-exploration").click(timeout=15000)
            page.wait_for_timeout(500)
            box(page).fill("An idea about widgets that should never become a document")
            st, res = req("POST", f"{B}/agents/beta/archive")
            print("archive beta ->", st, str(res)[:200])
            page.get_by_role("button", name="Send message").click()
            page.wait_for_timeout(5000)
            alerts = page.get_by_role("alert")
            print("ALERTS:", [norm(alerts.nth(i).text_content()) for i in range(alerts.count())])
            j.shot(page, "composer_06_refused_first_send")
            after = {d["path"] for d in req("GET", f"{B}/project/documents")[1]["documents"]}
            print("NEW DOCUMENTS LEFT:", sorted(after - before))
            print("on disk:", sorted(p.relative_to(DIR).as_posix() for p in (DIR / "spec").rglob("spec.json")))
        finally:
            st, res = req("POST", f"{B}/agents/beta/unarchive")
            print("unarchive beta ->", st, str(res)[:200])
    print("console errors:", j.errors[:6])
