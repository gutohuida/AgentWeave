"""Checkpoints x Accounting sweep 2026-10-22, UI (real Chromium, served bundle, :8122, profile ck1022).

overview -- the Overview's spend line (text, title, what it agrees with), its Ledger link (where it
            lands), the notice above it; Project settings -> Budgets beside it
ledger   -- the Activity tab's Ledger view: the spend figures
conv     -- a conversation (AW_CONV) with its banner stack and composer usage line
sheet    -- the Checkpoints sheet of AW_CONV

    AW_P=<project> [AW_CONV=<conversation>] py -3.11 scripts/drive/s1022_ck_ui.py <phase> [tag]
"""

import os
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1022_ck_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

CONV = os.environ.get("AW_CONV", "")
TAG = sys.argv[2] if len(sys.argv) > 2 else ""


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=200, after=400):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before) : i + after] for i in hits[:3])


def overview(j):
    page = j.page(P, mode="light", query="tab=overview")
    page.wait_for_timeout(5000)
    line = page.locator('[data-slot="spend-line"]')
    print("SPEND LINE:", line.count(), repr(" ".join((line.first.text_content() or "").split())) if line.count() else None,
          "title=", line.first.get_attribute("title") if line.count() else None)
    notice = page.locator(".aw-overview-notice")
    print("NOTICE:", repr(" ".join((notice.first.text_content() or "").split())) if notice.count() else "<none>")
    if notice.count():
        print("NOTICE controls:", [b.text_content() for b in notice.first.locator("a, button").all()])
    t = body(page)
    print("OVERVIEW words budget/cost/excludes/credits:", [w for w in ("budget", "excludes", "no reported cost", "credits", "Tokens", "estimate") if w.lower() in t.lower()])
    j.shot(page, f"overview{TAG}")
    if line.count():
        line.first.click()
        page.wait_for_timeout(3000)
        print("AFTER CLICK url:", page.url.split("?")[-1])
        t = body(page)
        print("AFTER CLICK has Ledger view?", "Ledger" in t, around(t, "spend", 80, 300)[:600])
        tabs = [b.text_content() for b in page.get_by_role("tab").all()] + [
            f"{b.text_content()}[{b.get_attribute('aria-pressed') or b.get_attribute('aria-selected') or b.get_attribute('data-state')}]"
            for b in page.locator('[role="radio"], [aria-pressed]').all()]
        print("AFTER CLICK view controls:", tabs[:20])
        j.shot(page, f"overview-click{TAG}")
    page = j.page(P, mode="light", query="tab=environment&section=budgets")
    page.wait_for_timeout(5000)
    t = body(page)
    i = t.find("Budget")
    print("BUDGETS:", t[i : i + 1800] if i >= 0 else t[-1800:])
    j.shot(page, f"budgets{TAG}", full_page=True)


def ledger(j):
    page = j.page(P, mode="light", query="tab=activity&view=ledger")
    page.wait_for_timeout(5000)
    t = body(page)
    print("URL", page.url.split("?")[-1])
    print("LEDGER:", around(t, "spend", 150, 900)[:1800])
    j.shot(page, f"ledger{TAG}", full_page=True)


def conv(j):
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(6000)
    t = body(page)
    print("CHECKPOINT:", around(t, "checkpoint", 150, 350)[:1200])
    print("BUDGET:", around(t, "budget", 150, 300)[:900])
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ismiss|ontinue", b.text_content() or "")])
    j.shot(page, f"conv{TAG}")


def sheet(j):
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)
    page.get_by_test_id("conversation-more").first.click()
    page.wait_for_timeout(800)
    page.get_by_test_id("conversation-checkpoints-toggle").first.click()
    page.wait_for_timeout(2500)
    panel = page.get_by_test_id("checkpoints-panel")
    print("SHEET:", " ".join((panel.first.text_content() or "").split())[:2500] if panel.count() else "<no panel>")
    print("SHEET buttons:", [b.text_content() for b in panel.first.get_by_role("button").all()] if panel.count() else [])
    j.shot(page, f"sheet{TAG}")


def job(j):
    """Jobs tab: press Run now on ping-beta with the budget spent; the toast, the row, the response."""
    from s1022_ck_lib import B, req
    jid = next(x["id"] for x in req("GET", f"{B}/jobs")[1] if x["name"] == "ping-beta")
    print("enable:", req("PATCH", f"{B}/jobs/{jid}", {"enabled": True})[0], "(yearly cron; disabled again below)")
    try:
        _job(j)
    finally:
        print("disable:", req("PATCH", f"{B}/jobs/{jid}", {"enabled": False})[0])


def _job(j):
    page = j.page(P, mode="light", query="tab=jobs")
    seen = []
    page.on("response", lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status, r.text()[:600]))
            if r.request.method == "POST" and "/run" in r.url else None)
    page.wait_for_timeout(4000)
    page.get_by_text("ping-beta").first.click()
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=re.compile("Run now")).first.click()
    page.wait_for_timeout(2500)
    toasts = page.locator('[data-sonner-toast], [role="status"], [role="alert"], .toast')
    print("TOASTS:", [" ".join((t.text_content() or "").split()) for t in toasts.all()][:6])
    print("RESPONSES:", seen)
    j.shot(page, f"job-run{TAG}")
    page.wait_for_timeout(8000)
    t = body(page)
    print("JOB AREA:", around(t, "ping-beta", 50, 700)[:1500])
    j.shot(page, f"job-after{TAG}")


def raise_(j):
    """Budgets: type a refused value, then a higher limit, by keyboard; read toast, notice, field."""
    page = j.page(P, mode="light", query="tab=environment&section=budgets")
    page.wait_for_timeout(4500)
    f = page.locator("#b-limit")
    for v in ("0", "abc", "1.25", "2"):
        f.click()
        f.press("Control+a")
        f.type(v)
        f.press("Enter")
        page.wait_for_timeout(1800)
        t = body(page)
        print(f"TYPED {v!r}: field={f.input_value()!r} limit-tile:", around(t, "LIMIT", 0, 60)[:120] if "LIMIT" in t else around(t, "Limit", 0, 60)[:120])
        print("   refusal/toast:", around(t, "Millions", 60, 80)[:200] if "Millions" in t else "-", "|", around(t, "Agents pause", 0, 80)[:160] if "Agents pause" in t else "-")
        print("   notice:", "Autonomous turns are paused" in t)
    j.shot(page, f"raise{TAG}", full_page=True)


def banner_text(page):
    t = body(page)
    for w in ("checkpoint threshold", "Checkpoint ready", "checkpoint is ready", "Checkpoint failed", "cut over", "was cut over", "Writing"):
        if w.lower() in t.lower():
            return around(t, w, 120, 360)[:700]
    return "<no checkpoint banner text>"


def flow(j):
    """On AW_CONV: Checkpoint now -> wait for the checkpoint -> Cut over -> the successor; the sheet."""
    from s1022_ck_lib import q
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    seen = []
    page.on("requestfinished", lambda r: seen.append((r.method, r.url.split("/api/v1")[-1].split("?")[0]))
            if r.method in ("POST", "PATCH") else None)
    page.wait_for_timeout(5000)
    print("BEFORE:", banner_text(page))
    if not page.get_by_role("button", name="Checkpoint now").count():
        print("no Checkpoint now offered; buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ismiss|ontinue|ut over", b.text_content() or "")])
    else:
        page.get_by_role("button", name="Checkpoint now").first.click()
    page.wait_for_timeout(2000)
    print("PRESSED:", banner_text(page))
    j.shot(page, "flow-pressed")
    for _ in range(60):
        rows = q("select id, status, trigger from checkpoints where conversation_id=?", CONV)
        rows = q("select id, status, trigger, probe_status from checkpoints where conversation_id=?", CONV)
        if rows and rows[-1]["status"] not in ("pending", "writing", "generating") and rows[-1]["probe_status"]:
            break
        page.wait_for_timeout(3000)
    print("CHECKPOINT ROWS:", rows)
    page.wait_for_timeout(4000)
    print("READY:", banner_text(page))
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ismiss|ontinue|ut over|iew", b.text_content() or "")])
    j.shot(page, "flow-ready")
    cut = page.get_by_role("button", name="Cut over")
    if cut.count():
        cut.first.click()
        page.wait_for_timeout(6000)
        print("AFTER CUT url:", page.url.split("?")[-1])
        print("AFTER CUT:", banner_text(page))
        print("AFTER CUT buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ontinue|tart|ut over", b.text_content() or "")])
        j.shot(page, "flow-cut")
    print("RESPONSES:", seen)
    print("CONVS:", q("select id, lifecycle, checkpoint_warning from conversations where agent='alpha'"))


def reload_mid(j):
    """Press the header Checkpoint, reload 3 s later (operator refreshes while 'Writing checkpoint…');
    wait for the Hub to finish; is the conversation cut over, and what does the page offer?"""
    from s1022_ck_lib import q
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)
    before = q("select id from checkpoints where conversation_id=?", CONV)
    btn = page.get_by_role("button", name=re.compile("^Checkpoint"))
    print("header buttons:", [(b.text_content(), b.get_attribute("aria-label")) for b in btn.all()])
    btn.first.click()
    page.wait_for_timeout(3000)
    print("PRESSED:", banner_text(page)[:300])
    page.reload(wait_until="domcontentloaded")
    for _ in range(60):
        rows = q("select id, status, trigger, probe_status, cut_over_to_conversation_id from checkpoints where conversation_id=?", CONV)
        new = [r for r in rows if r["id"] not in {b["id"] for b in before}]
        if new and new[-1]["probe_status"]:
            break
        page.wait_for_timeout(3000)
    page.wait_for_timeout(5000)
    print("NEW CHECKPOINT:", new)
    print("CONV:", q("select id, lifecycle, checkpoint_warning from conversations where agent='alpha'"))
    print("AFTER RELOAD:", banner_text(page)[:500])
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ut over|ontinue", b.text_content() or "")])
    j.shot(page, f"reload-mid{TAG}")


def press_wait(j):
    """Press the header Checkpoint and stay until the page moves to the successor."""
    from s1022_ck_lib import q
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={CONV}")
    page.wait_for_timeout(5000)
    page.get_by_role("button", name=re.compile("^Checkpoint")).first.click()
    for _ in range(40):
        page.wait_for_timeout(3000)
        if CONV not in page.url:
            break
    page.wait_for_timeout(3000)
    print("URL:", page.url.split("?")[-1])
    print("PAGE:", banner_text(page)[:500])
    print("CKPTS:", q("select id, status, trigger, cut_over_to_conversation_id from checkpoints where conversation_id=?", CONV))
    print("CONVS:", q("select id, lifecycle, checkpoint_warning from conversations where agent='alpha'"))
    print("ENTRIES:", q("select id, conversation_id, state, awaits_continue from inbound_queue_entries where agent='alpha' order by sequence"))
    print("buttons:", [b.text_content() for b in page.get_by_role("button").all() if re.search("heckpoint|ut over|ontinue", b.text_content() or "")])
    j.shot(page, f"press-wait{TAG}")


phase = sys.argv[1]
with Judge(f"s1022-ck-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {"overview": overview, "ledger": ledger, "conv": conv, "sheet": sheet, "job": job, "raise": raise_, "flow": flow, "reload_mid": reload_mid, "press_wait": press_wait}[phase](j)
