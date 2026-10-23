"""2026-10-23 Questions row, UI (Chromium against the served bundle, scratch Hub hub-up qa1023 8116).

  f909     Overview (Needs you rows, agent cards) and the rail, after asking runs ended unanswered
  waiting  alpha blocked on its batch: Overview card (F910), Needs you, rail
  f804     conversation X while the batch is open in A: type and send -> message or answer?
  f911     Overview: alpha's question row -> Open conversation -> which conversation
  keys     conversation A: where is focus on load; press 1 (with focus on body / in the composer);
           does it select; then send; then the next question's X (decline)

  py -3.11 scripts/drive/s1023_qa_ui.py <what>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "f909"
from s1023_qa_drive import S, e2e, questions, ro, qrow  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def overview(page, label):
    for i, li in enumerate(page.locator(".aw-ov-need").all()):
        print(f"[{label}] NEED {i}: {txt(li.locator('.aw-ov-need-title'))} | detail={txt(li.locator('.aw-ov-need-detail'))}"
              f" | meta={txt(li.locator('.aw-ov-need-meta'))}"
              f" | buttons={[(b.text_content() or '').strip() for b in li.locator('.aw-ov-need-actions button').all()]}")
    for row in page.locator(".aw-ov-agent-row").all():
        print(f"[{label}] AGENT CARD: state={row.get_attribute('data-state')} | {' '.join((row.text_content() or '').split())}")
    for agent in ("alpha", "beta", "gamma"):
        loc = page.locator(f"[data-testid=rail-agent-attention-{P}-{agent}]")
        print(f"[{label}] rail {agent} 'waiting' marker:", loc.count(), txt(loc))
    dots = page.locator("[data-testid$=-attention]")
    print(f"[{label}] rail conversation attention dots:", [(d.get_attribute('data-testid'), d.get_attribute('aria-label')) for d in dots.all()])
    summary = page.locator(".aw-ov-summary, [data-slot=overview-summary]")
    print(f"[{label}] summary:", txt(summary)[:200])


def where(page, label):
    print(f"[{label}] url:", page.url.split("#")[0][-160:])
    cards = page.locator("[data-testid^=agent-question-q-]")
    print(f"[{label}] ask cards:", [c.get_attribute("data-testid") for c in cards.all()])
    ta = page.locator("textarea")
    print(f"[{label}] composer placeholder:", ta.first.get_attribute("placeholder") if ta.count() else "<none>")


def focus(page):
    return page.evaluate("() => { const a = document.activeElement; return a ? `${a.tagName} ${a.getAttribute('aria-label') || a.getAttribute('placeholder') || a.className}`.slice(0, 120) : null }")


with Judge("s1023-questions", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT in ("f909", "waiting", "f911"):
        page = j.page(P, mode="light")
        page.wait_for_timeout(6000)
        overview(page, WHAT)
        j.shot(page, f"{WHAT}_overview")
        if WHAT == "f911":
            row = page.locator(".aw-ov-need", has_text="Which colour").first
            if not row.count():
                row = page.locator(".aw-ov-need", has_text="alpha").first
            row.get_by_role("button", name="Open conversation").click()
            page.wait_for_timeout(5000)
            where(page, "after Open conversation")
            print("asking conversation A:", S["A"], "| X:", S["X"])
            j.shot(page, "f911_after_open")
        if WHAT == "f909":
            for conv, agent in ((S.get("CONV_T1S"), "gamma"), (S.get("CONV_T1"), "beta")):
                if not conv:
                    continue
                p2 = j.page(P, mode="light", query=f"agent={agent}&conversation={conv}")
                p2.wait_for_timeout(6000)
                where(p2, f"{agent} conversation")
                stale = p2.locator("[data-testid=agent-question-stale]")
                print(f"[{agent}] 'no longer waiting' chip:", stale.count())
                print(f"[{agent}] header:", txt(p2.locator("header, [data-slot=conversation-bar]"))[:300])
                j.shot(p2, f"f909_{agent}_conversation")
    elif WHAT == "f804":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['X']}")
        page.wait_for_timeout(6000)
        where(page, "X before")
        ta = page.locator("textarea").first
        ta.fill("blue please")
        ta.press("Enter")
        page.wait_for_timeout(4000)
        where(page, "X after send")
        print("queued text visible in X:", page.get_by_text("blue please", exact=False).count())
        j.shot(page, "f804_X_after")
        for q in questions():
            if q["id"] in S["Q_A"]:
                print("question after typing in X:", q["id"], {k: q.get(k) for k in ("answered", "answer", "declined")})
        print("alpha queue:", ro("select id, state, conversation_id, substr(content,1,120) c from inbound_queue_entries where agent='alpha' order by sequence"))
    elif WHAT == "keys":
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['A']}")
        page.wait_for_timeout(6000)
        where(page, "A")
        print("focus on load:", focus(page))
        q1 = S["Q_A"][0]
        opt0 = page.locator(f"[data-testid=agent-question-option-{q1}-0]")
        print("option 0 text:", txt(opt0), "| kbd badge:", txt(opt0.locator("kbd")))
        j.shot(page, "keys_before")
        # 1) with focus wherever the page put it
        page.keyboard.press("1")
        page.wait_for_timeout(600)
        print("after '1' at load focus: option0 selected =", opt0.get_attribute("data-selected"),
              "| composer value =", repr(page.locator("textarea").first.input_value()))
        # 2) with focus off any field
        page.locator("textarea").first.fill("")
        page.locator(f"[data-testid=agent-question-{q1}] p").first.click()
        print("focus after clicking the question text:", focus(page))
        page.keyboard.press("2")
        page.wait_for_timeout(600)
        opt1 = page.locator(f"[data-testid=agent-question-option-{q1}-1]")
        print("after '2' off-field: option1 selected =", opt1.get_attribute("data-selected"), "| option0 =", opt0.get_attribute("data-selected"))
        page.keyboard.press("1")
        page.wait_for_timeout(600)
        print("after '1' off-field: option0 selected =", opt0.get_attribute("data-selected"), "| option1 =", opt1.get_attribute("data-selected"))
        page.keyboard.press("9")
        page.wait_for_timeout(300)
        print("after '9' (no such option): selected =", [opt0.get_attribute("data-selected"), opt1.get_attribute("data-selected")])
        print("question after keys only (no send):", qrow(q1))
        j.shot(page, "keys_selected")
        # Enter off-field: does it submit?
        page.keyboard.press("Enter")
        page.wait_for_timeout(2500)
        print("after Enter off-field:", qrow(q1))
        if not qrow(q1)[0]["answered"]:
            send = page.get_by_role("button", name="Send")
            if not send.count():
                send = page.locator("button[aria-label*=end i], button[type=submit]")
            print("send buttons:", [(b.get_attribute("aria-label"), (b.text_content() or "").strip()) for b in send.all()][:5])
            send.first.click()
            page.wait_for_timeout(3000)
        print("Q1 after send:", [{k: q.get(k) for k in ("answered", "answer", "answer_labels")} for q in questions() if q["id"] == q1])
        page.wait_for_timeout(2000)
        where(page, "A after Q1")
        j.shot(page, "keys_after_send")
        if len(S["Q_A"]) > 1:
            q2 = S["Q_A"][1]
            x = page.locator(f"[data-testid=agent-question-decline-{q2}]")
            print("decline control for Q2:", x.count(), x.get_attribute("aria-label") if x.count() else None)
            if x.count():
                x.click()
                page.wait_for_timeout(1500)
                dlg = page.get_by_role("dialog")
                print("dialog after X:", dlg.count(), txt(dlg)[:200])
                if dlg.count():
                    j.shot(page, "decline_confirm")
                    btn = dlg.get_by_role("button").filter(has_text="ismiss").or_(dlg.get_by_role("button").filter(has_text="ecline"))
                    print("dialog buttons:", [(b.text_content() or '').strip() for b in dlg.get_by_role("button").all()])
                    if btn.count():
                        btn.first.click()
                page.wait_for_timeout(2500)
            print("Q2 after decline:", [{k: q.get(k) for k in ("answered", "declined")} for q in questions() if q["id"] == q2])
            where(page, "A after decline")
            j.shot(page, "after_decline")
    if WHAT == "keys2":
        # Q1 was answered by a bare '1' at load focus (BODY). Now Q2: a digit typed in the composer
        # must not answer; then decline Q2 with its X; the multi-question counter.
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={S['A']}")
        page.wait_for_timeout(6000)
        where(page, "A (Q2)")
        print("counter:", txt(page.locator("[data-testid=agent-question-count]")))
        q2 = S["Q_A"][1]
        ta = page.locator("textarea").first
        ta.click()
        page.keyboard.press("2")
        page.wait_for_timeout(1500)
        print("after '2' in composer: composer =", repr(ta.input_value()), "| Q2 row:", qrow(q2))
        ta.fill("")
        j.shot(page, "keys2_before_decline")
        x = page.locator(f"[data-testid=agent-question-decline-{q2}]")
        print("decline control:", x.count(), x.get_attribute("aria-label") if x.count() else None)
        x.click()
        page.wait_for_timeout(1500)
        dlg = page.get_by_role("dialog")
        print("dialog after X:", dlg.count(), txt(dlg)[:200])
        page.wait_for_timeout(2500)
        print("Q2 after X:", qrow(q2), [{k: q.get(k) for k in ("answered", "declined")} for q in questions() if q["id"] == q2])
        where(page, "A after decline")
        print("counter:", txt(page.locator("[data-testid=agent-question-count]")))
        j.shot(page, "keys2_after_decline")
    print("console errors:", j.errors[:5])
