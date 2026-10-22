"""2026-10-22 traces sweep, UI (real Chromium against the served bundle, scratch Hub hub-up tr1022 8112).

  f844     with alpha blocked on a question in A: conversation B's bar, Stop, placeholder; then A's
  digest   the Activity tab's Activity view: every digest row's sentence, and the raw events behind
           the stopped and failed turns' rows

  live     digest open while the question is answered through the route and the turn ends:
           does the live row turn from "is working" into "worked" without a reload

  py -3.11 scripts/drive/s1022_tr_ui.py [f844|digest|live]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "digest"
from s1022_tr_drive import S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def bar(page, label):
    main = page.locator("main")
    print(f"[{label}] Stop turn buttons:", page.get_by_role("button", name="Stop turn").count())
    print(f"[{label}] 'busy in' text:", page.get_by_text("busy in", exact=False).count(),
          "| 'waiting on your answer':", page.get_by_text("waiting on your answer", exact=False).count(),
          "| 'is responding':", page.get_by_text("is responding", exact=False).count())
    ta = page.locator("textarea")
    print(f"[{label}] composer placeholder:", ta.first.get_attribute("placeholder") if ta.count() else "<none>")
    print(f"[{label}] top of main:", txt(main)[:400])


with Judge("s1022-traces", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "f844":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['B']}")
        page.wait_for_timeout(6000)
        bar(page, "B")
        j.shot(page, "f844_B")
        link = page.get_by_role("button", name="Open").or_(page.get_by_role("link", name="Open"))
        print("[B] Open link count:", link.count())
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['A']}")
        page.wait_for_timeout(6000)
        bar(page, "A")
        j.shot(page, "f844_A")
    elif WHAT == "live":
        import time
        from s1022_tr_drive import api, ro
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(4000)
        page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
        page.wait_for_timeout(3000)
        top = lambda: [txt(r.locator(".aw-digest-sentence")) for r in page.locator(".aw-digest-row").all()[:4]]
        print("BEFORE:", top())
        st, res = api("PATCH", f"~/questions/{S['Q']}", {"answer": "red"})
        print("answer", st, str(res)[:200])
        end = time.time() + 120
        while time.time() < end and ro("select status from runs where id=?", (S["RUN_ASK"],))[0]["status"] == "running":
            time.sleep(3)
        print("run:", ro("select status from runs where id=?", (S["RUN_ASK"],)))
        page.wait_for_timeout(8000)
        print("AFTER (no reload):", top())
        print("NOTE:", txt(page.locator(".aw-activity-count")))
        j.shot(page, "digest_live_after")
    else:
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(4000)
        btn = page.locator("[aria-label='Activity view'] button", has_text="Activity")
        print("activity view buttons:", btn.count())
        btn.first.click()
        page.wait_for_timeout(4000)
        print("NOTE:", txt(page.locator(".aw-activity-count")))
        for day in page.locator(".aw-digest-day").all():
            print("DAY:", txt(day.locator(".aw-digest-day-label")))
            for row in day.locator(".aw-digest-row").all():
                sev = row.get_attribute("data-severity")
                print(f"  [{sev}] {txt(row.locator('.aw-digest-time'))} | {txt(row.locator('.aw-digest-sentence'))}"
                      f" | {txt(row.locator('.aw-digest-detail'))} | {txt(row.locator('.aw-digest-facts'))}")
        print("beta anywhere:", page.get_by_text("beta", exact=False).count(),
              "| OTHER anywhere:", page.get_by_text("OTHER", exact=True).count())
        j.shot(page, "digest_all", full_page=True)
        rows = page.locator(".aw-digest-row")
        for i in range(rows.count()):
            s = txt(rows.nth(i).locator(".aw-digest-sentence"))
            if "is working" in s or "stopped" in s or "failed" in s:
                rows.nth(i).locator("[data-slot='digest-row']").click()
                page.wait_for_timeout(500)
                print(f"OPENED '{s}':", txt(rows.nth(i).locator(".aw-digest-raw"))[:500])
        j.shot(page, "digest_opened", full_page=True)
        warn = page.locator("[aria-label='Show'] button", has_text="Warnings")
        if warn.count():
            warn.first.click()
            page.wait_for_timeout(800)
            print("WARNINGS FILTER:", [txt(r.locator(".aw-digest-sentence")) for r in page.locator(".aw-digest-row").all()])
