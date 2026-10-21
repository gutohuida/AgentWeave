"""Checkpoints x Accounting sweep 2026-10-21, UI (real Chromium, served bundle, :8153, profile c1021).

failed -- alpha's conversation over its threshold, checkpoint runner a Codex runner that cannot run
          here: press Checkpoint now, read the toast and the warning (F817)
reload -- the same conversation reloaded: is the banner still offering Checkpoint now?
unarch -- after a cutover: Show archived on alpha, Unarchive the predecessor from its row menu; what
          does the row say (F816)?
held   -- budget spent, alpha's peer entry held: type into alpha's own conversation from the
          composer; does it run (F814)?
budgets-- Environment -> Budgets and the Overview budget summary

    AW_P=<project> AW_CONV=<conversation> py -3.11 scripts/drive/s1021_c_ui.py <phase>
"""

import os
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1021_c_lib import P, e2e, q  # noqa: E402
from uiharness import Judge  # noqa: E402

CONV = os.environ.get("AW_CONV", "")


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=200, after=400):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before) : i + after] for i in hits[:3])


def ckpt_buttons(page):
    return [
        b.text_content()
        for b in page.get_by_role("button").all()
        if re.search("heckpoint|ismiss", b.text_content() or "")
    ]


def failed(j):
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
        if "checkpoint" in r.url
        else None,
    )
    page.wait_for_timeout(5000)
    print("BANNER:", around(body(page), "threshold", 100, 300))
    print("buttons:", ckpt_buttons(page))
    j.shot(page, "failed-before")
    page.get_by_role("button", name="Checkpoint now").first.click()
    page.wait_for_timeout(30000)
    print("responses:", seen)
    print("AFTER failed:", around(body(page), "failed", 150, 400))
    print("AFTER threshold:", around(body(page), "threshold", 100, 300))
    print("buttons:", ckpt_buttons(page))
    print("warning:", q("select checkpoint_warning from conversations where id=?", CONV))
    j.shot(page, "failed-after")


def reload_failed(j):
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(6000)
    t = body(page)
    print("RELOADED threshold:", around(t, "threshold", 100, 300))
    print("RELOADED failed:", around(t, "failed", 150, 300))
    print("buttons:", ckpt_buttons(page))
    j.shot(page, "failed-reloaded")


def unarch(j):
    page = j.page(P, mode="light", query="agent=alpha")
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
        if "archive" in r.url
        else None,
    )
    page.wait_for_timeout(5000)
    page.get_by_test_id(f"agent-menu-{P}-alpha").click()
    page.wait_for_timeout(600)
    page.get_by_test_id(f"agent-menu-{P}-alpha-archived").click()
    page.wait_for_timeout(2500)
    row = f"rail-archived-{CONV}"
    print("archived row:", page.get_by_test_id(row).count(), page.get_by_test_id(row).first.get_attribute("title") if page.get_by_test_id(row).count() else None)
    page.get_by_test_id(row).hover()
    page.get_by_test_id(f"{row}-menu").click()
    page.wait_for_timeout(600)
    page.get_by_test_id(f"{row}-menu-unarchive").click()
    page.wait_for_timeout(3000)
    err = page.get_by_test_id(f"{row}-error")
    print("responses:", seen)
    print("row error:", " ".join((err.first.text_content() or "").split()) if err.count() else "<none>")
    print("lifecycle:", q("select lifecycle from conversations where id=?", CONV))
    j.shot(page, "unarch-after")
    # And opening the archived predecessor itself: what does it say, and is its composer live?
    page.get_by_test_id(row).click()
    page.wait_for_timeout(4000)
    t = body(page)
    print("PRED opened:", around(t, "archived", 150, 300), "||", around(t, "conv-", 100, 200))
    ta = page.locator("textarea.composer-textarea")
    print("composer:", ta.count(), ta.first.get_attribute("placeholder") if ta.count() else None,
          ta.first.is_disabled() if ta.count() else None)
    j.shot(page, "unarch-pred-open")


def predsend(j):
    """The archived, cut-over predecessor opened from the rail: does its composer send, and where?"""
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
        if r.request.method == "POST"
        else None,
    )
    page.wait_for_timeout(5000)
    ta = page.locator("textarea.composer-textarea").first
    ta.click()
    ta.fill("Reply with the single word PRED.")
    page.get_by_role("button", name="Send message").first.click()
    page.wait_for_timeout(8000)
    t = body(page)
    print("responses:", seen)
    print("AFTER:", around(t, "PRED", 200, 400))
    print("convs:", q("select id, lifecycle from conversations where agent='alpha' order by sequence"))
    print("runs:", q("select id, conversation_id, session_id, status from runs where agent='alpha' order by started_at desc limit 2"))
    print("entries:", q("select id, conversation_id, state, waiting_reason from inbound_queue_entries where agent='alpha' order by sequence desc limit 2"))
    j.shot(page, "predsend-after")


def autospent(j):
    """`automatic` mode, budget spent: the reading only warned. What does gamma's banner say, and
    what does Checkpoint now do on a spent budget?"""
    page = j.page(P, mode="light", query=f"agent=gamma&conversation={CONV}")
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
        if "checkpoint" in r.url
        else None,
    )
    page.wait_for_timeout(5000)
    t = body(page)
    print("BANNER:", around(t, "threshold", 150, 400))
    print("budget words:", around(t, "budget", 150, 300))
    print("buttons:", ckpt_buttons(page))
    j.shot(page, "autospent-before")
    page.get_by_role("button", name="Checkpoint now").first.click()
    page.wait_for_timeout(20000)
    t = body(page)
    print("responses:", seen)
    print("AFTER:", around(t, "heckpoint", 150, 400))
    print("checkpoints:", q("select id, trigger, status from checkpoints where conversation_id=?", CONV))
    print("warning:", q("select checkpoint_warning from conversations where id=?", CONV))
    j.shot(page, "autospent-after")


def sheet(j):
    """The Checkpoints sheet on a conversation: the failed attempt, the ready one, and the successor."""
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)
    page.get_by_test_id("conversation-checkpoints-toggle").first.click()
    page.wait_for_timeout(2500)
    panel = page.get_by_test_id("checkpoints-panel")
    print("SHEET:", " ".join((panel.first.text_content() or "").split())[:2500] if panel.count() else "<no panel>")
    print("links in sheet:", [a.get_attribute("href") or a.text_content() for a in panel.first.locator("a, button").all()][:12] if panel.count() else [])
    j.shot(page, "sheet")


def held(j):
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)
    print("BEFORE budget:", around(body(page), "budget", 150, 300))
    ta = page.locator("textarea.composer-textarea").first
    ta.click()
    ta.fill("Reply with the single word OWN.")
    page.get_by_role("button", name="Send message").first.click()
    page.wait_for_timeout(6000)
    t = body(page)
    print("AFTER budget:", around(t, "budget", 150, 300))
    print("AFTER queued:", around(t, "Queued", 50, 200))
    print("entries:", q("select id, conversation_id, origin_type, state, waiting_reason from inbound_queue_entries where agent='alpha' order by sequence desc limit 3"))
    print("runs:", q("select id, conversation_id, status from runs where agent='alpha' order by started_at desc limit 2"))
    j.shot(page, "held-after-send")


def budgets(j):
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(5000)
    print("OVERVIEW budget:", around(body(page), "budget", 100, 500))
    j.shot(page, "overview", full_page=True)
    page = j.page(P, mode="light", query="tab=environment&section=budgets")
    page.wait_for_timeout(5000)
    t = body(page)
    i = t.find("Budgets", 400)
    print("BUDGETS:", t[i : i + 1800] if i >= 0 else t[-1800:])
    j.shot(page, "budgets", full_page=True)


phase = sys.argv[1]
with Judge(f"s1021-c-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {"failed": failed, "reload": reload_failed, "unarch": unarch, "predsend": predsend, "autospent": autospent, "held": held, "sheet": sheet, "budgets": budgets}[phase](j)
