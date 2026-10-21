"""Agents x Inbound queue sweep 2026-10-20, UI (real Chromium, served bundle, :8149).

cont     -- Continue on a held entry with the budget unchanged
held     -- a hop-held entry in alpha's conversation: its note, Continue after the budget was
            raised elsewhere (the refusal, on screen or not), then Continue for real
withdraw -- a queued entry for a runner-less agent: its "not started" reason and the X;
            then a stale X after the entry was withdrawn behind the page's back

py -3.11 scripts/drive/s1020_a_ui.py held|withdraw
"""

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_a_lib import P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def txt(page):
    return " ".join((page.get_by_test_id("conversation-output").first.text_content() or "").split())


def settings(**change):
    _, cur = req("GET", f"/projects/{P}/settings")
    body = {k: v for k, v in cur.items() if k not in ("warnings",)}
    body.update(change)
    status, res = req("PUT", f"/projects/{P}/settings", body)
    print(
        "PUT settings",
        change,
        "->",
        status,
        res.get("hop_budget") if isinstance(res, dict) else res,
    )


def watch_responses(page, tag):
    seen = []
    page.on(
        "response",
        lambda r: (
            seen.append((r.request.method, r.url.split("/api/v1")[-1], r.status))
            if "/queue/entries/" in r.url
            else None
        ),
    )
    return seen


def held(j):
    entry = q(
        "select id, conversation_id from inbound_queue_entries where project_id=? and agent='alpha' "
        "and state='queued'",
        P,
    )[0]
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={entry['conversation_id']}")
    seen = watch_responses(page, "held")
    page.wait_for_timeout(5000)
    out = txt(page)
    i = out.find("hop budget")
    print("NOTE:", out[max(0, i - 300) : i + 400] if i >= 0 else "<no 'hop budget' text>")
    cont = page.get_by_role("button", name="Continue")
    print("Continue buttons:", cont.count())
    j.shot(page, "held-1")
    settings(hop_budget=6)
    page.wait_for_timeout(3000)
    print("after budget raised elsewhere -> Continue buttons:", cont.count())
    if cont.count():
        cont.first.click()
        page.wait_for_timeout(2500)
        print("responses:", seen)
        after = txt(page)
        print("screen after stale Continue (tail):", after[-500:])
        j.shot(page, "held-2-stale-continue")
    print("entry:", q("select state, hop_depth from inbound_queue_entries where id=?", entry["id"]))
    settings(hop_budget=1)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    print("after reload, budget 1 -> Continue buttons:", cont.count())
    if cont.count():
        cont.first.click()
        page.wait_for_timeout(4000)
        print("responses:", seen)
        j.shot(page, "held-3-continue")
    print(
        "entry:",
        q(
            "select state, hop_depth, delivered_in_run_id from inbound_queue_entries where id=?",
            entry["id"],
        ),
    )
    print(
        "released events:",
        q(
            "select data from event_logs where project_id=? and event_type="
            "'queue_entry_released'",
            P,
        ),
    )


def cont(j):
    """Continue on a held entry, the budget unchanged: the entry delivers at depth 0."""
    entry = q(
        "select id, conversation_id from inbound_queue_entries where project_id=? and agent='alpha' "
        "and state='queued'",
        P,
    )[0]
    page = j.page(P, mode="light", query=f"agent=alpha&conversation={entry['conversation_id']}")
    seen = watch_responses(page, "cont")
    page.wait_for_timeout(5000)
    cont_buttons = page.get_by_role("button", name="Continue")
    print("Continue buttons:", cont_buttons.count())
    cont_buttons.first.click()
    page.wait_for_timeout(4000)
    print("responses:", seen, "| Continue buttons now:", cont_buttons.count())
    j.shot(page, "cont-1")
    print(
        "entry:",
        q(
            "select state, hop_depth, delivered_in_run_id from inbound_queue_entries where id=?",
            entry["id"],
        ),
    )
    print(
        "released events:",
        q(
            "select data from event_logs where project_id=? and event_type="
            "'queue_entry_released'",
            P,
        ),
    )


def charters(j):
    """Environment -> Charters: duplicates, create with a blank name, edit, delete a bound one."""
    page = j.page(P, mode="light", query="tab=environment&section=charters")
    page.wait_for_timeout(5000)
    names = [
        b.get_attribute("aria-label")[7:]
        for b in page.locator("button[aria-label^='Delete ']").all()
    ]
    print("charters listed:", names)
    page.get_by_role("button", name="New Charter").click()
    page.wait_for_timeout(600)
    dialog = page.locator("[aria-labelledby='charter-form-title']")
    print(
        "form open:",
        dialog.count(),
        "| focus:",
        page.evaluate(
            "() => document.activeElement && document.activeElement.getAttribute('aria-label')"
        ),
    )
    page.get_by_label("Charter name").fill("   ")
    page.get_by_label("Charter content").fill("blank-named")
    submit = dialog.get_by_role("button").last
    print("blank name -> submit:", submit.text_content(), "| disabled:", submit.is_disabled())
    j.shot(page, "charters-1-blank")
    page.get_by_label("Charter name").fill("UI charter")
    submit.click()
    page.wait_for_timeout(1500)
    print("after create, dialog open:", dialog.count())
    print(
        "rows:",
        q("select name, length(content) n from charters where project_id=? order by created_at", P)[
            -3:
        ],
    )
    page.locator("button[aria-label='Delete Code Reviewer']").first.click()
    page.wait_for_timeout(700)
    confirm = page.locator("[aria-labelledby='delete-charter-title']")
    print("delete dialog:", " ".join((confirm.text_content() or "").split())[:400])
    print(
        "focus:",
        page.evaluate("() => document.activeElement && document.activeElement.textContent"),
    )
    confirm.get_by_role("button").filter(has_text="Delete").last.click()
    page.wait_for_timeout(1500)
    alert = page.locator("[role=alert]")
    print(
        "alert:",
        " ".join((alert.first.text_content() or "").split()) if alert.count() else "<none>",
    )
    j.shot(page, "charters-2-bound-delete")


def unarchive(j):
    """An archived agent's old conversation: the notice, then Unarchive from it."""
    conv = q(
        "select id from conversations where project_id=? and agent='eps' order by sequence", P
    )[0]["id"]
    page = j.page(P, mode="light", query=f"agent=eps&conversation={conv}")
    page.wait_for_timeout(5000)
    body = " ".join((page.locator("body").text_content() or "").split())
    i = body.find("archived")
    print("NOTICE:", body[max(0, i - 150) : i + 250] if i >= 0 else "<no 'archived' text>")
    rail = page.locator("nav, aside").first
    print("eps in rail text:", "eps" in (rail.text_content() or ""))
    j.shot(page, "unarchive-1")
    btn = page.get_by_role("button", name="Unarchive eps")
    print("Unarchive button:", btn.count())
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(2500)
        print(
            "lifecycle:",
            q("select name, lifecycle from agents where project_id=? and lower(name)='eps'", P),
        )
        print("notice still:", page.get_by_role("button", name="Unarchive eps").count())
        j.shot(page, "unarchive-2")


def withdraw(j):
    rid = q("select runner_id from agents where project_id=? and name='eps'", P)[0]["runner_id"]
    req("PATCH", f"/projects/{P}/agents/eps", {"runner_id": None})
    for msg in ("first queued for eps", "second queued for eps"):
        status, res = req("POST", f"/projects/{P}/agent/trigger", {"agent": "eps", "message": msg})
        print("trigger", status, res.get("waiting_reason"), res.get("queue_entry_id"))
    conv = res["conversation_id"]
    page = j.page(P, mode="light", query=f"agent=eps&conversation={conv}")
    seen = watch_responses(page, "withdraw")
    page.wait_for_timeout(5000)
    out = txt(page)
    i = out.find("first queued")
    print("ENTRY TEXT:", out[max(0, i - 200) : i + 500])
    xs = page.locator('button[title="Withdraw before it\'s delivered"]')
    print("withdraw buttons:", xs.count())
    j.shot(page, "withdraw-1")
    if xs.count():
        xs.first.click()
        page.wait_for_timeout(2500)
        print("responses:", seen, "| withdraw buttons now:", xs.count())
    # Stale: withdraw the other entry behind the page's back, then click its X if still drawn.
    left = q(
        "select id from inbound_queue_entries where project_id=? and agent='eps' and state='queued'",
        P,
    )
    print("left queued:", left)
    if left:
        print("API withdraw:", req("DELETE", f"/projects/{P}/queue/entries/{left[0]['id']}")[0])
        page.wait_for_timeout(3000)
        print("after API withdraw -> withdraw buttons on page:", xs.count())
        if xs.count():
            xs.first.click()
            page.wait_for_timeout(2000)
            print("responses:", seen, "| tail:", txt(page)[-300:])
    j.shot(page, "withdraw-2")
    print(
        "eps entries:",
        q("select id, state from inbound_queue_entries where project_id=? and agent='eps'", P),
    )
    req("PATCH", f"/projects/{P}/agents/eps", {"runner_id": rid})


phase = sys.argv[1]
with Judge(f"s1020-a-{phase}", hub=e2e.hub(), key=e2e.key()) as j:
    {
        "held": held,
        "cont": cont,
        "charters": charters,
        "unarchive": unarchive,
        "withdraw": withdraw,
    }[phase](j)
