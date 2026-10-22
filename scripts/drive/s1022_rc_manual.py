"""Reach sweep 2026-10-22 (copy of s1021_rc_manual.py): "Ask me" reached through the PROJECT default (no per-run posture), judged in a real browser.

One Haiku turn under `manual`, four steps: `git status` (F453: pre-approved?), Write approve-me.txt
(Allow on the card), Write deny-me.txt (Deny on the card), Write expire-me.txt (left to expire;
the agent's permission timeout is 45 s). Reads each card's text (what Workspace only would decide),
then the Overview's Permission decisions list.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_rc_manual.py <project-id> <agent>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, AGENT = sys.argv[1], sys.argv[2]


def norm(s):
    return " ".join((s or "").split())


def requests_for(run_id):
    s, rows = e2e.request("GET", f"/projects/{P}/permission-requests?include_expired=true")
    return [r for r in (rows if isinstance(rows, list) else []) if r.get("run_id") == run_id]


def run_status(run_id):
    return e2e.ro().execute("select status from runs where id=?", (run_id,)).fetchone()[0]


e2e.call("PATCH", f"/projects/{P}/agents/{AGENT}", {"permission_timeout_seconds": 45})
with Judge("s1022-manual", hub=e2e.hub(), key=e2e.key()) as j:
    msg = ("Do these four steps in order, one tool call each, and do not retry anything that is "
           "refused: 1. Run `git status` with the Bash tool. 2. Use the Write tool to create "
           "approve-me.txt containing ok. 3. Use the Write tool to create deny-me.txt containing no. "
           "4. Use the Write tool to create expire-me.txt containing late. Then reply with one line "
           "per step saying what happened, quoting any refusal word for word.")
    rid = e2e.cmd_turn(P, AGENT, msg, perm=None, fresh=True)
    page = j.page(P, mode="light")
    page.wait_for_timeout(3000)
    page.get_by_text(AGENT, exact=True).first.click()
    page.wait_for_timeout(2500)
    handled = set()
    deadline = time.time() + 360
    while time.time() < deadline and run_status(rid) in ("running", "queued", "starting", "pending"):
        for row in requests_for(rid):
            if row["status"] != "pending" or row["id"] in handled:
                continue
            target = json.dumps(row.get("tool_input") or {})[:160]
            print("PENDING:", row["tool_name"], target, "| workspace_verdict:", row.get("workspace_verdict"))
            card = page.locator(f"[data-testid='permission-request-{row['id']}']")
            try:
                card.wait_for(timeout=20000)
                print("  CARD:", norm(card.text_content())[:500])
            except Exception as exc:  # noqa: BLE001
                print("  card not visible:", str(exc)[:120])
                card = None
            handled.add(row["id"])
            if "expire-me" in target:
                j.shot(page, "03_expire_card")
                print("  leaving it to expire")
                continue
            if "deny-me" in target:
                j.shot(page, "02_deny_card")
                page.locator(f"[data-testid='permission-deny-{row['id']}']").click()
            else:
                j.shot(page, "01_allow_card" if "approve-me" in target else "00_other_card")
                page.locator(f"[data-testid='permission-allow-{row['id']}']").click()
        time.sleep(2)
    print("RUN", rid, run_status(rid))
    page.wait_for_timeout(3000)
    for row in requests_for(rid):
        print("FINAL:", row["tool_name"], row["status"], json.dumps(row.get("tool_input"))[:90],
              {k: row.get(k) for k in ("decided_by", "decided_at", "reason", "decision_reason")})
    wd = pathlib.Path(e2e.ro().execute("select working_directory from projects where id=?", (P,)).fetchone()[0])
    for name in ("approve-me.txt", "deny-me.txt", "expire-me.txt"):
        hits = [str(p) for p in wd.rglob(name)]
        print("FILE", name, hits)
    e2e.dump_turn(rid)
    j.shot(page, "04_after_turn", full_page=True)
    # The Overview's Permission decisions list.
    page2 = j.page(P, mode="light", query="tab=overview")
    page2.wait_for_timeout(4000)
    dec = page2.get_by_test_id("permission-decisions")
    print("DECISIONS present:", dec.count())
    if dec.count():
        dec.first.locator("summary").click()
        page2.wait_for_timeout(2500)
        print("DECISIONS:", norm(dec.first.text_content())[:900])
        j.shot(page2, "05_decisions", locator=dec.first)
    print("console errors:", j.errors[:8])
e2e.call("PATCH", f"/projects/{P}/agents/{AGENT}", {"permission_timeout_seconds": None})
