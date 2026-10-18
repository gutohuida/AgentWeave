"""Sweep A (2026-10-18): "Ask me" on a live Hub, judged in a real browser.

Turn 1 (F679): the agent delegates a Write to a subagent; the card must say "From a subagent: ...".
The drive answers the subagent's card with the card's own Deny button.
Turn 2: the agent asks for (a) `git status` (F453: pre-approved?), (b) Write approve-me.txt
(Allow on the card), (c) Write .claude/settings.local.json (F675: what does the card's
Workspace-only advice say? Deny), (d) Write expire-me.txt (left unanswered until it expires).

    py -3.11 scripts/drive/s1018_A_perm_ui.py <agent>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
OUT.mkdir(exist_ok=True)
errors = []


def pending(run_id):
    s, rows = req("GET", f"/projects/{P}/permission-requests?include_expired=true")
    return [r for r in (rows if isinstance(rows, list) else []) if r.get("run_id") == run_id]


def open_conversation(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 940})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(P))
    )
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{e2e.hub()}/?project={P}", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.get_by_text(agent, exact=True).first.click()
    page.wait_for_timeout(2500)
    return page


def wait_card(page, rid, timeout=20):
    loc = page.locator(f"[data-testid='permission-request-{rid}']")
    try:
        loc.wait_for(timeout=timeout * 1000)
        return loc
    except Exception as exc:  # noqa: BLE001
        print("card not visible:", exc)
        return None


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    # ---- turn 1: subagent
    msg = ("Use the Agent tool exactly once, with the description 'write marker', and tell the "
           "subagent to use the Write tool to create marker-a.txt containing hi, and nothing else. "
           "Do not write the file yourself. Then reply DONE.")
    r1 = e2e.cmd_turn(P, agent, msg, perm="manual", fresh=True)
    page = open_conversation(browser)
    seen = None
    deadline = time.time() + 240
    while time.time() < deadline and not seen:
        for row in pending(r1):
            if row["status"] == "pending":
                print("pending:", row["tool_name"], row.get("subagent"), row.get("workspace_verdict"))
                if row.get("subagent"):
                    seen = row
                else:
                    req("POST", f"/projects/{P}/permission-requests/{row['id']}/decide", {"allow": True})
        time.sleep(2)
    if seen:
        card = wait_card(page, seen["id"])
        if card:
            print("CARD TEXT:", card.text_content())
            page.screenshot(path=str(OUT / "f679_card.png"))
            page.locator(f"[data-testid='permission-deny-{seen['id']}']").click()
            page.wait_for_timeout(2000)
    print("r1", e2e.wait_for(r1, 4))
    page.screenshot(path=str(OUT / "f679_after.png"), full_page=False)
    rows = page.locator("text=subagent:").all()
    print("timeline subagent rows:", [r.text_content()[:120] for r in rows[:5]])
    print("decision row:", q("select tool_name, status, decision_reason from permission_requests where run_id=?", r1) if q("select 1 from pragma_table_info('permission_requests') where name='decision_reason'") else q("select * from permission_requests where run_id=?", r1))
    e2e.dump_turn(r1)
    page.context.close()

    # ---- turn 2: approve, deny (runner config), expire; git status pre-approved?
    req("PATCH", f"/projects/{P}/agents/{agent}", {"permission_timeout_seconds": 45})
    msg = ("Do these four steps in order, one tool call each, and do not retry anything that is "
           "refused: 1. Run `git status` with the Bash tool. 2. Use the Write tool to create "
           "approve-me.txt containing ok. 3. Use the Write tool to create .claude/settings.local.json "
           "containing {} . 4. Use the Write tool to create expire-me.txt containing late. "
           "Then reply with one line per step saying what happened.")
    r2 = e2e.cmd_turn(P, agent, msg, perm="manual")
    page = open_conversation(browser)
    handled = set()
    deadline = time.time() + 300
    while time.time() < deadline:
        st = q("select status from runs where id=?", r2)[0]["status"]
        if st not in ("running", "queued", "starting", "pending"):
            break
        for row in pending(r2):
            if row["status"] != "pending" or row["id"] in handled:
                continue
            ti = row.get("tool_input") or {}
            target = json.dumps(ti)[:160]
            print("pending:", row["tool_name"], target, "| verdict:", row.get("workspace_verdict"))
            card = wait_card(page, row["id"])
            if card:
                print("  CARD TEXT:", card.text_content()[:600])
            handled.add(row["id"])
            if "approve-me" in target:
                page.screenshot(path=str(OUT / "approve_card.png"))
                page.locator(f"[data-testid='permission-allow-{row['id']}']").click()
            elif "settings.local" in target:
                page.screenshot(path=str(OUT / "f675_card.png"))
                page.locator(f"[data-testid='permission-deny-{row['id']}']").click()
            elif "expire-me" in target:
                page.screenshot(path=str(OUT / "expire_card_before.png"))
                print("  leaving it to expire")
            else:
                print("  unexpected ask; allowing via card")
                page.locator(f"[data-testid='permission-allow-{row['id']}']").click()
        time.sleep(2)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUT / "after_turn2.png"))
    print("r2", e2e.wait_for(r2, 3))
    for r in pending(r2):
        print("final:", r["tool_name"], r["status"], json.dumps(r.get("tool_input"))[:100],
              {k: r.get(k) for k in r if k in ("decision", "reason", "decided_by", "expired_at", "allowed")})
    e2e.dump_turn(r2)
    denied = q("select data from event_logs where project_id=? and event_type='permission_denied' order by timestamp desc limit 5", P)
    print("denied events:", denied)
    page.context.close()
    browser.close()
print("console/page errors:", errors[:10])
