"""Agents x Inbound queue sweep 2026-10-21, UI (real Chromium, served bundle, :8154).

abandon  -- kappa (a Codex runner that cannot run here): its abandoned message's block
addagent -- Add agent with a name differing from alpha's only in case (F811 on screen)
pickers  -- archived eps absent from the board's assignee filter, the job form, Ctrl+K
removed  -- a sync deletes kappa while its conversation is open: the rail, the page, Activity

py -3.11 scripts/drive/s1021_a_ui.py abandon|addagent|pickers|removed
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1021_a_lib import P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def body(page):
    return norm(page.locator("body").text_content())


def around(text, needle, before=200, after=400):
    i = text.find(needle)
    return text[max(0, i - before) : i + after] if i >= 0 else f"<no {needle!r}>"


def kappa_conv():
    return q("select id from conversations where project_id=? and agent='kappa'", P)[0]["id"]


def abandon(j):
    page = j.page(P, mode="light", query=f"agent=kappa&conversation={kappa_conv()}")
    page.wait_for_timeout(5000)
    out = body(page)
    print("ABANDONED:", around(out, "stopped retrying", 300, 500))
    print("LAST ATTEMPT:", around(out, "Last attempt", 50, 400))
    j.shot(page, "abandon-1")


def addagent(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Add agent to this project").first.click()
    page.wait_for_timeout(800)
    dialog = page.locator("[aria-labelledby='agent-create-title']")
    print("dialog:", dialog.count())
    dialog.locator("input[data-dialog-initial-focus]").fill("Alpha")
    dialog.locator("button[aria-label='Provider']").click()
    page.wait_for_timeout(400)
    dialog.locator("[role=option]").filter(has_text="Claude").first.click()
    page.wait_for_timeout(600)
    model = dialog.locator("select[aria-label='Model']")
    if model.count():
        haiku = [o.get_attribute("value") for o in model.locator("option").all()
                 if "haiku" in (o.get_attribute("value") or "").lower()]
        if haiku:
            model.select_option(haiku[0])
    print("selects:", [norm(s.text_content())[:80] for s in dialog.locator("select").all()])
    submit = dialog.get_by_role("button").filter(has_text="Create").last
    if not submit.count():
        submit = dialog.get_by_role("button").last
    print("submit:", norm(submit.text_content()), "disabled:", submit.is_disabled())
    submit.click()
    page.wait_for_timeout(1500)
    alert = dialog.locator("[role=alert]")
    print("ALERT:", norm(alert.first.text_content()) if alert.count() else "<none>")
    j.shot(page, "addagent-1")
    print("agents:", q("select name, lifecycle from agents where project_id=?", P))


def pickers(j):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    out = body(page)
    print("tasks page mentions eps:", "eps" in out, "| alpha:", "alpha" in out)
    page.goto(page.url.split("?")[0] + "?tab=jobs", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    new = page.get_by_role("button", name="New job")
    if new.count():
        new.first.click()
        page.wait_for_timeout(800)
    opts = [norm(o.text_content()) for o in page.locator("option").all()]
    print("job form options with @:", [o for o in opts if o.startswith("@")])
    page.keyboard.press("Control+k")
    page.wait_for_timeout(600)
    page.keyboard.type("ep")
    page.wait_for_timeout(600)
    pal = page.locator("[cmdk-list]")
    print("palette for 'ep':", norm(pal.first.text_content())[:300] if pal.count() else "<none>")
    j.shot(page, "pickers-1")


def removed(j):
    conv = kappa_conv()
    page = j.page(P, mode="light", query=f"agent=kappa&conversation={conv}")
    page.wait_for_timeout(5000)
    print("before: kappa in rail:", "kappa" in norm(page.locator("nav, aside").first.text_content()))
    names = {r["name"]: {} for r in q("select name from agents where project_id=?", P)}
    names.pop("kappa")
    status, res = req("POST", f"projects/{P}/session/sync", {"data": {"agents": names}})
    print("sync ->", status, json.dumps(res)[:200])
    page.wait_for_timeout(4000)
    out = body(page)
    print("LIVE PAGE after sync:", out[:200], "...")
    print("kappa mentions live:", out.count("kappa"), "|", around(out, "agent archived", 200, 200))
    j.shot(page, "removed-1-live")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    out = body(page)
    print("after reload kappa mentions:", out.count("kappa"))
    print("RAIL ROW:", around(out, "agent archived", 250, 150))
    print("COMPOSER:", page.locator("textarea").count(), "textareas")
    j.shot(page, "removed-2-reload")
    page.goto(page.url.split("?")[0] + "?tab=activity", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    out = body(page)
    print("ACTIVITY kappa:", around(out, "kappa", 200, 300))
    print("ACTIVITY zeta:", around(out, "zeta", 200, 200))
    j.shot(page, "removed-3-activity")


def held(j):
    """beta's reply held at the hop budget in alpha's conversation: the note, then its X."""
    entry = q(
        "select id, conversation_id from inbound_queue_entries where project_id=? and agent='alpha' "
        "and state='queued' and hop_depth=2",
        P,
    )[0]
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={entry['conversation_id']}")
    seen = []
    page.on(
        "response",
        lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
        if "/queue/entries/" in r.url
        else None,
    )
    page.wait_for_timeout(5000)
    out = body(page)
    print("HELD NOTE:", around(out, "hop budget", 300, 300))
    xs = page.locator("button[title=\"Withdraw before it's delivered\"]")
    conts = page.get_by_role("button", name="Continue")
    print("withdraw buttons:", xs.count(), "| Continue:", conts.count())
    j.shot(page, "held-1")
    discard = page.get_by_role("button", name="Discard")
    print("discard buttons:", discard.count(), "| focus before:", page.evaluate("() => document.activeElement && document.activeElement.textContent"))
    discard.first.click()
    page.wait_for_timeout(800)
    dlg = page.locator("[role=dialog], [role=alertdialog]")
    if dlg.count():
        print("CONFIRM:", norm(dlg.first.text_content())[:300])
        dlg.first.get_by_role("button").filter(has_text="Discard").last.click()
    page.wait_for_timeout(2500)
    print("responses:", seen, "| discard now:", discard.count(), "| Continue now:", conts.count())
    print("AFTER:", around(body(page), "PONG", 200, 200))
    j.shot(page, "held-2")
    print("entry:", q("select state, abandoned_reason from inbound_queue_entries where id=?", entry["id"]))
    print("events:", q("select event_type, data from event_logs where project_id=? and event_type like 'queue_entry_w%'", P))


def refused(j):
    """The conversation a read-only-refused trigger left behind."""
    page = j.page(P, mode="light", query="agent=alpha&conversation=conv-cbf513918571")
    page.wait_for_timeout(5000)
    out = body(page)
    print("REFUSED CONV:", around(out, "Reply with OK", 300, 300))
    j.shot(page, "refused-1")


phase = sys.argv[1]
with Judge(f"s1021-a-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {"abandon": abandon, "addagent": addagent, "pickers": pickers, "removed": removed,
     "held": held, "refused": refused}[phase](j)
