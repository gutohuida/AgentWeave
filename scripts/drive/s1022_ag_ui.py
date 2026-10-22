"""Agents x Charters x Inbound queue sweep 2026-10-22, UI (real Chromium, served bundle, :8116).

sync     -- gamma's conversation open; a sync deletes gamma: rail, header, page, Activity, Logs,
            then gamma re-created: does the new one inherit anything (F849/F850)
charters -- Project settings -> Charters: dialog focus, blank refused, create, edit, bound delete,
            unbound delete with confirm, focus return
agent    -- beta's settings: the seven sections, charter bound from there and read back

py -3.11 scripts/drive/s1022_ag_ui.py <phase>
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1022_ag_lib import HAIKU, P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def body(page):
    return norm(page.locator("body").text_content())


def around(text, needle, before=200, after=400):
    i = text.find(needle)
    return text[max(0, i - before) : i + after] if i >= 0 else f"<no {needle!r}>"


def rail(page):
    nav = page.locator("aside, nav")
    return norm(nav.first.text_content()) if nav.count() else "<no rail>"


def active(page):
    return page.evaluate(
        "() => { const e = document.activeElement; return e ? (e.tagName + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.textContent || '').slice(0, 60)) : null }"
    )


def sync(j):
    conv = q("select id from conversations where project_id=? and agent='gamma'", P)[0]["id"]
    page = j.page(P, mode="light", query=f"agent=gamma&conversation={conv}")
    page.wait_for_timeout(5000)
    print("BEFORE rail:", rail(page)[:400])
    print("BEFORE page:", body(page)[:300])
    j.shot(page, "sync-0-before")
    status, res = req("POST", f"projects/{P}/session/sync", {"data": {"agents": {"alpha": {}, "beta": {}}}})
    print("sync ->", status, json.dumps(res)[:300])
    for wait in (3000, 5000):
        page.wait_for_timeout(wait)
        print(f"+{wait}ms rail gamma mentions:", rail(page).count("gamma"), "| rail:", rail(page)[:400])
    out = body(page)
    print("LIVE PAGE:", out[:600])
    print("textareas:", page.locator("textarea").count())
    j.shot(page, "sync-1-live")
    print("conv lifecycle:", q("select lifecycle from conversations where id=?", conv))
    print("job:", q("select name, agent, enabled, archived_at from ai_jobs where project_id=?", P))
    after(j, page)


def after(j, page=None):
    if page is None:
        page = j.page(P, mode="light")
        page.wait_for_timeout(3000)
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=activity", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    out = body(page)
    print("ACTIVITY gamma:", around(out, "gamma", 300, 400))
    j.shot(page, "sync-2-activity", full_page=True)
    for label in ("Logs", "Ledger"):
        tab = page.get_by_role("tab", name=label)
        if not tab.count():
            tab = page.get_by_role("button", name=label)
        if tab.count():
            tab.first.click()
            page.wait_for_timeout(2500)
            print(f"{label.upper()} gamma:", around(body(page), "gamma", 300, 400))
            j.shot(page, f"sync-3-{label.lower()}")
    # Re-create gamma: the new agent should start with nothing of the old one.
    rid = next(r["id"] for r in req("GET", f"projects/{P}/runners")[1] if r.get("model") == HAIKU)
    status, res = req("POST", f"projects/{P}/agents", {"name": "gamma", "runner_id": rid})
    print("recreate ->", status, res.get("id") if isinstance(res, dict) else res)
    page.goto(page.url.split("?")[0] + f"?project={P}&agent=gamma", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    print("NEW GAMMA rail:", rail(page)[:500])
    print("NEW GAMMA page:", body(page)[:500])
    j.shot(page, "sync-4-recreated")
    page.goto(page.url.split("?")[0] + f"?project={P}&tab=jobs", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    print("JOBS:", around(body(page), "gamma nightly", 200, 400))
    j.shot(page, "sync-5-jobs")


def views(j):
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    for label in ("Activity", "Logs"):
        page.get_by_role("radio", name=label).first.click()
        page.wait_for_timeout(3000)
        out = body(page)
        for who in ("gamma", "delta"):
            i = out.find(f"{who} was removed")
            print(f"{label.upper()} '{who} was removed':", i >= 0, "|", around(out, f"{who} agent removed", 150, 150) if i < 0 else around(out, f"{who} was removed", 100, 200))
        j.shot(page, f"views-{label.lower()}", full_page=True)


def held(j):
    entry = q("select id, conversation_id from inbound_queue_entries where project_id=? and agent='beta' and state='queued' and hop_depth=2", P)[0]
    page = j.page(P, mode="light", query=f"agent=beta&conversation={entry['conversation_id']}")
    seen = []
    page.on("response", lambda r: seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status)) if "/queue/entries/" in r.url else None)
    page.wait_for_timeout(5000)
    out = body(page)
    print("HELD NOTE:", around(out, "hop", 400, 400))
    conts = page.get_by_role("button", name="Continue")
    xs = page.locator("button[title*='Withdraw' i], button[aria-label*='Withdraw' i], button[aria-label*='Discard' i]")
    print("Continue:", conts.count(), "| withdraw/discard:", xs.count(), [norm(x.get_attribute("aria-label") or x.get_attribute("title") or x.text_content()) for x in xs.all()])
    j.shot(page, "held-1", full_page=True)
    if conts.count():
        conts.first.click()
        page.wait_for_timeout(1500)
        dlg = page.locator("[role=dialog], [role=alertdialog]")
        if dlg.count():
            print("CONFIRM:", norm(dlg.first.text_content())[:300])
        page.wait_for_timeout(20000)
        print("responses:", seen, "| Continue now:", conts.count())
        print("AFTER:", body(page)[-900:])
        j.shot(page, "held-2", full_page=True)
    print("entry:", q("select state, hop_depth, delivered_in_run_id from inbound_queue_entries where id=?", entry["id"]))
    print("events:", q("select event_type, data from event_logs where project_id=? and event_type like 'queue_entry_rel%'", P))


def open_settings(page, section):
    page.get_by_role("button", name="Project settings").first.click()
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=section).first.click()
    page.wait_for_timeout(1500)


def charters(j):
    page = j.page(P, mode="light")
    page.wait_for_timeout(4000)
    gear = page.get_by_role("button", name="Project settings")
    print("gear buttons:", gear.count())
    open_settings(page, "Charters")
    out = body(page)
    print("CHARTERS PAGE:", around(out, "Charters", 0, 900))
    j.shot(page, "ch-0-list", full_page=True)
    new = page.get_by_role("button", name="New charter")
    print("new buttons:", new.count())
    new.first.click()
    page.wait_for_timeout(700)
    dlg = page.get_by_role("dialog", name="New charter")
    print("dialog:", dlg.count(), "| focus:", active(page))
    save = dlg.get_by_role("button", name="Save")
    print("save disabled blank:", save.is_disabled())
    dlg.get_by_label("Charter name").fill("   ")
    print("save disabled whitespace:", save.is_disabled())
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("after Escape dialogs:", page.get_by_role("dialog").count(), "| focus:", active(page))
    new.first.click()
    page.wait_for_timeout(600)
    dlg = page.get_by_role("dialog", name="New charter")
    dlg.get_by_label("Charter name").fill("n" * 257)
    dlg.get_by_label("Charter content").fill("too long a name")
    dlg.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1200)
    alert = dlg.locator("[role=alert]")
    print("257-char ALERT:", norm(alert.first.text_content()) if alert.count() else "<none>")
    j.shot(page, "ch-1-long")
    dlg.get_by_label("Charter name").fill("Doc Writer")
    dlg.get_by_label("Charter content").fill("# Doc Writer\n\nYou write the README.\n")
    dlg.get_by_role("button", name="Save").click()
    page.wait_for_timeout(1500)
    print("after create dialogs:", page.get_by_role("dialog").count(), "| focus:", active(page))
    out = body(page)
    print("LIST has Doc Writer:", "Doc Writer" in out, "|", around(out, "Doc Writer", 100, 300))
    j.shot(page, "ch-2-created", full_page=True)
    # Edit it.
    edit = page.get_by_role("button", name="Edit Doc Writer")
    if not edit.count():
        edit = page.locator("button", has_text="Edit").filter(has=page.locator(":scope")).nth(0)
    print("edit buttons:", page.get_by_role("button", name="Edit Doc Writer").count(),
          "| all edit-like:", [norm(b.get_attribute("aria-label") or b.text_content()) for b in page.locator("button").all() if "dit" in (b.get_attribute("aria-label") or b.text_content() or "")][:12])
    if page.get_by_role("button", name="Edit Doc Writer").count():
        page.get_by_role("button", name="Edit Doc Writer").click()
        page.wait_for_timeout(600)
        dlg = page.get_by_role("dialog", name="Edit Doc Writer")
        print("edit focus:", active(page))
        dlg.get_by_label("Charter content").fill("# Doc Writer\n\nYou write the README and the CHANGELOG.\n")
        dlg.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1200)
    print("db:", q("select name, substr(content,1,80) c from charters where project_id=? and name like 'Doc%'", P))
    # Bound delete: Developer is bound to alpha.
    dels = [norm(b.get_attribute("aria-label") or "") for b in page.locator("button").all() if "elete" in (b.get_attribute("aria-label") or b.text_content() or "")]
    print("delete-like buttons:", dels[:12])
    dev = page.get_by_role("button", name="Delete Developer")
    if dev.count():
        dev.click()
        page.wait_for_timeout(600)
        ad = page.get_by_role("alertdialog")
        print("CONFIRM:", norm(ad.first.text_content()) if ad.count() else "<none>", "| focus:", active(page))
        ad.get_by_role("button", name="Delete charter").click()
        page.wait_for_timeout(1500)
        out = body(page)
        print("BOUND DELETE notice:", around(out, "was not deleted", 50, 300), "| focus:", active(page))
        j.shot(page, "ch-3-bound-delete", full_page=True)
    dw = page.get_by_role("button", name="Delete Doc Writer")
    if dw.count():
        dw.click()
        page.wait_for_timeout(600)
        ad = page.get_by_role("alertdialog")
        print("CONFIRM DW:", norm(ad.first.text_content()) if ad.count() else "<none>")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        print("after Escape:", page.get_by_role("alertdialog").count(), "| focus:", active(page))
        dw.click()
        page.wait_for_timeout(500)
        page.get_by_role("alertdialog").get_by_role("button", name="Delete charter").click()
        page.wait_for_timeout(1500)
        out = body(page)
        print("after delete has Doc Writer:", "Doc Writer" in out, "| still 'was not deleted':", "was not deleted" in out,
              "| focus:", active(page))
        j.shot(page, "ch-4-deleted", full_page=True)


def agent(j):
    page = j.page(P, mode="light", query="agent=beta&settings=identity")
    page.wait_for_timeout(4000)
    for section in ("Identity", "Execution", "Charter", "Interaction", "Context", "Access", "Workspace"):
        page.get_by_role("button", name=section).first.click()
        page.wait_for_timeout(1500)
        main = page.locator("main")
        text = norm(main.first.text_content()) if main.count() else body(page)
        print(f"== {section}: {text[:700]}")
        j.shot(page, f"agent-{section.lower()}", full_page=True)
    # Charter: bind Code Reviewer from the picker; then a charter deleted elsewhere, picked here.
    page.get_by_role("button", name="Charter").first.click()
    page.wait_for_timeout(1200)
    pick = page.get_by_label("Charter for beta")
    cr = next(c["id"] for c in req("GET", f"projects/{P}/charters")[1] if c["name"] == "Code Reviewer")
    pick.select_option(cr)
    page.wait_for_timeout(1500)
    print("bound:", q("select name, charter_id from agents where project_id=? and name='beta'", P), "| want", cr)
    uw = next(c["id"] for c in req("GET", f"projects/{P}/charters")[1] if c["name"] == "Underwriter")
    print("delete Underwriter elsewhere ->", req("DELETE", f"projects/{P}/charters/{uw}")[0])
    pick.select_option(uw)
    page.wait_for_timeout(2000)
    out = norm(page.locator("main").first.text_content())
    print("STALE PICK:", around(out, "Charter for", 50, 600) if "Charter for" in out else out[:900])
    print("select value now:", pick.input_value(), "| db:", q("select charter_id from agents where project_id=? and name='beta'", P))
    j.shot(page, "agent-stale-charter", full_page=True)


phase = sys.argv[1]
with Judge(f"s1022-ag-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {"sync": sync, "after": after, "views": views, "held": held, "charters": charters, "agent": agent}[phase](j)
