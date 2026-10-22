"""2026-10-22 questions sweep, UI (real Chromium against the served bundle, scratch Hub hub-up qs1022 8113).

  needs    Overview's Needs you: order, "is waiting"/"is asking", detail; then alpha's row's
           "Open conversation" -- which conversation opens, and is its ask card there
  f860     conversation B: expand the send_message row, read the refusal sentence
  f804     conversation B while the question is open in A: type and send; message or answer?
  composer beta's conversation: a draft across reload, the @ completion, Ctrl+K
  keys     conversation A: press 1 on the ask card; is the question answered with "red"

  py -3.11 scripts/drive/s1022_qs_ui.py <what>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "needs"
from s1022_qs_drive import S, e2e, questions, ro  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def where(page, label):
    print(f"[{label}] url:", page.url.split("#")[0][-160:])
    print(f"[{label}] ask card 'Which colour':", page.get_by_text("Which colour for the border?", exact=False).count())
    ta = page.locator("textarea")
    print(f"[{label}] composer placeholder:", ta.first.get_attribute("placeholder") if ta.count() else "<none>")
    print(f"[{label}] main head:", txt(page.locator("main"))[:300])


with Judge("s1022-questions", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "needs":
        page = j.page(P, mode="light")
        page.wait_for_timeout(5000)
        for i, li in enumerate(page.locator(".aw-ov-need").all()):
            print(f"NEED {i}: {txt(li.locator('.aw-ov-need-title'))} | detail={txt(li.locator('.aw-ov-need-detail'))}"
                  f" | meta={txt(li.locator('.aw-ov-need-meta'))} | options={[txt(b) for b in [li.locator('.aw-ov-option')]]}"
                  f" | buttons={[ (b.text_content() or '').strip() for b in li.locator('.aw-ov-need-actions button').all()]}")
        j.shot(page, "needs_you")
        row = page.locator(".aw-ov-need", has_text="Which colour").first
        row.get_by_role("button", name="Open conversation").click()
        page.wait_for_timeout(5000)
        where(page, "after Open conversation")
        print("expected conversation (A):", S["A"], "| B:", S["B"])
        j.shot(page, "needs_open_conversation")
    elif WHAT == "f860":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['B']}")
        page.wait_for_timeout(6000)
        work = page.locator("summary", has_text="1 failed")
        print("work block toggles:", work.count(), txt(work))
        work.last.click()
        page.wait_for_timeout(800)
        print("tool rows:", [" ".join((b.text_content() or "").split())[:90] for b in page.locator("button[aria-expanded]").all()])
        rows = page.locator("button[aria-expanded]", has_text="failed")
        rows = page.locator("button[aria-expanded]").filter(has_text="send").or_(rows)
        print("send_message rows:", rows.count(), "| collapsed text:", txt(rows))
        if rows.count():
            rows.first.click()
            page.wait_for_timeout(800)
            body = rows.first.locator("xpath=..")
            print("EXPANDED:", txt(body)[:700])
            print("refusal sentence visible:", page.get_by_text("The operator is not a message recipient", exact=False).count())
        j.shot(page, "f860_expanded")
    elif WHAT == "f804":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['B']}")
        page.wait_for_timeout(6000)
        where(page, "B before")
        ta = page.locator("textarea").first
        ta.fill("blue please")
        ta.press("Enter")
        page.wait_for_timeout(4000)
        where(page, "B after send")
        print("queued text visible in B:", page.get_by_text("blue please", exact=False).count())
        j.shot(page, "f804_B_after")
        q = [x for x in questions() if x["id"] == S["Q_A2"]][0]
        print("question after typing in B:", {k: q.get(k) for k in ("answered", "answer", "declined")})
    elif WHAT == "composer":
        conv = ro("select id from conversations where agent='beta' order by sequence desc limit 1")[0]["id"]
        page = j.page(P, mode="light", query=f"agent=beta&conversation={conv}")
        page.wait_for_timeout(5000)
        ta = page.locator("textarea").first
        ta.fill("draft that should survive")
        page.wait_for_timeout(1500)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("draft after reload:", repr(page.locator("textarea").first.input_value()))
        ta = page.locator("textarea").first
        ta.fill("")
        ta.type("look at @ca")
        page.wait_for_timeout(1500)
        opts = page.get_by_role("option")
        print("@ options:", [(o.text_content() or "").strip()[:60] for o in opts.all()][:10])
        j.shot(page, "composer_at")
        if opts.count():
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            print("after Enter:", repr(page.locator("textarea").first.input_value()))
        page.locator("textarea").first.fill("")
        page.keyboard.press("Escape")
        page.locator("body").click()
        page.keyboard.press("Control+k")
        page.wait_for_timeout(800)
        dlg = page.get_by_role("dialog")
        print("Ctrl+K dialog:", dlg.count(), txt(dlg)[:200])
        print("focus in dialog:", page.evaluate("() => !!document.activeElement.closest('[role=dialog]')"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        print("dialog after Escape:", page.get_by_role("dialog").count())
        j.shot(page, "composer_after")
    elif WHAT == "keys":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['A']}")
        page.wait_for_timeout(6000)
        where(page, "A")
        page.locator("body").click()
        page.keyboard.press("1")
        page.wait_for_timeout(3000)
        q = [x for x in questions() if x["id"] == S["Q_A2"]][0]
        print("after pressing 1:", {k: q.get(k) for k in ("answered", "answer", "answer_labels")})
        j.shot(page, "keys_after")
