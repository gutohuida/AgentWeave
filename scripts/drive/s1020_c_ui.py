"""Checkpoints x Accounting sweep 2026-10-20, UI (real Chromium, served bundle, :8150).

spent -- budget spent: Overview budget summary, beta's conversation (budget_note?), alpha's held
         peer entry, gamma's checkpoint banner, both alpha Checkpoints sheets, the unarchived
         handed-over predecessor

py -3.11 scripts/drive/s1020_c_ui.py spent
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_c_lib import P, e2e, q  # noqa: E402
from uiharness import Judge  # noqa: E402


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=200, after=400):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before) : i + after] for i in hits[:3])


def conv_of(agent, origin=None):
    rows = q(
        "select id, lifecycle from conversations where project_id=? and agent=? order by sequence",
        P,
        agent,
    )
    return rows


def spent(j):
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(5000)
    t = body(page)
    print("OVERVIEW budget:", around(t, "budget"))
    j.shot(page, "spent-1-overview", full_page=True)

    beta = conv_of("beta")[-1]["id"]
    page = j.page(P, mode="light", query=f"agent=beta&conversation={beta}")
    page.wait_for_timeout(5000)
    t = body(page)
    print("\nBETA conv budget:", around(t, "budget"))
    j.shot(page, "spent-2-beta")

    peer = q(
        "select conversation_id from inbound_queue_entries where agent='alpha' and state='queued'"
    )[0]["conversation_id"]
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={peer}")
    page.wait_for_timeout(5000)
    t = body(page)
    print("\nALPHA held entry:", around(t, "budget"))
    j.shot(page, "spent-3-alpha-held")

    gamma = conv_of("gamma")[-1]["id"]
    page = j.page(P, mode="light", query=f"agent=gamma&conversation={gamma}")
    page.wait_for_timeout(5000)
    t = body(page)
    print("\nGAMMA banner:", around(t, "checkpoint", 100, 400))
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ismiss|Not now", b.text_content() or "")])
    j.shot(page, "spent-4-gamma-banner")

    for cid, tag in (("conv-5bf3fe5c7c84", "pred"), ("conv-1dbec82e6c34", "succ")):
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={cid}")
        page.wait_for_timeout(5000)
        t = body(page)
        print(f"\nALPHA {tag} top:", t[:200])
        print(f"ALPHA {tag} handed/successor:", around(t, "handed", 150, 300), "||", around(t, "continues", 150, 300))
        print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|Continue|Cut over|Open", b.text_content() or "")])
        toggle = page.get_by_test_id("conversation-checkpoints-toggle")
        print("checkpoints toggle:", toggle.count())
        if toggle.count():
            toggle.first.click()
            page.wait_for_timeout(2500)
            panel = page.get_by_test_id("checkpoints-panel")
            pt = " ".join((panel.first.text_content() or "").split()) if panel.count() else "<no panel>"
            print(f"SHEET {tag}:", pt[:1800])
            j.shot(page, f"spent-5-{tag}-sheet")
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
            print("after Escape, panel visible:", panel.count() and panel.first.is_visible())


def cont(j):
    peer = q(
        "select conversation_id from inbound_queue_entries where agent='alpha' and state='queued'"
    )[0]["conversation_id"]
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={peer}")
    seen = []
    page.on("response", lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status)) if "/continue" in r.url else None)
    page.wait_for_timeout(5000)
    btn = page.get_by_test_id("conversation-continue")
    print("continue control:", btn.count(), btn.first.text_content() if btn.count() else None)
    before = body(page)
    btn.first.click()
    page.wait_for_timeout(3000)
    after = body(page)
    print("responses:", seen)
    print("AFTER:", around(after, "budget", 300, 400))
    print("still offered:", btn.count())
    j.shot(page, "cont-after-click")


def pred(j):
    page = j.page(P, mode="light", query="agent=alpha&conversation=conv-5bf3fe5c7c84")
    page.wait_for_timeout(4000)
    box = page.get_by_placeholder(re.compile("Message alpha"))
    box.fill("Reply with the single word PRED.")
    page.keyboard.press("Enter")
    page.wait_for_timeout(4000)
    print("after send:", around(body(page), "PRED", 300, 300))
    j.shot(page, "pred-after-send")


def failed(j):
    conv = "conv-bcf112b0ce9b"
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={conv}")
    seen = []
    page.on("response", lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status)) if "checkpoint" in r.url or "cutover" in r.url else None)
    page.wait_for_timeout(5000)
    print("BANNER:", around(body(page), "threshold", 100, 300))
    page.get_by_role("button", name="Checkpoint now").first.click()
    page.wait_for_timeout(25000)
    t = body(page)
    print("responses:", seen)
    print("AFTER:", around(t, "checkpoint", 150, 400))
    print("convs:", q("select id, lifecycle, checkpoint_warning from conversations where agent='alpha' order by sequence"))
    j.shot(page, "failed-after-press")


def reload_failed(j):
    page = j.page(P, mode="light", query="agent=alpha&conversation=conv-bcf112b0ce9b")
    page.wait_for_timeout(6000)
    t = body(page)
    print("RELOADED threshold:", around(t, "threshold", 100, 200))
    print("RELOADED failed:", around(t, "failed", 150, 200))
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if "heckpoint" in (b.text_content() or "")])
    j.shot(page, "failed-reloaded")


def budgets(j):
    page = j.page(P, mode="light", query="tab=environment&section=budgets")
    page.wait_for_timeout(5000)
    t = body(page)
    i = t.find("Budgets", 400)
    print("BUDGETS:", t[i : i + 1500] if i >= 0 else t[-1500:])
    j.shot(page, "budgets", full_page=True)


phase = sys.argv[1]
with Judge(f"s1020-c-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {"spent": spent, "cont": cont, "pred": pred, "failed": failed, "reload": reload_failed, "budgets": budgets}[phase](j)
