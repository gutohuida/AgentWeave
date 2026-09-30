"""Drive `a-pending-proposal-can-be-withdrawn` task 3.1, browser half: two windows on one `gate`
document's proposals; window A withdraws one and rejects another, window B only watches.

Usage: AW_HUB=... AW_KEY=... py -3.11 scripts/drive/d0930_withdraw_browser.py <project-id> <path> <shots-dir>
Run after d0930_withdraw_agent.py. A throwaway Hub only (never :8000 / :8010).
"""

import os
import sys

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PID, PATH, SHOTS = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(SHOTS, exist_ok=True)
HUB, KEY = os.environ["AW_HUB"], os.environ["AW_KEY"]
S = "/projects/%s/project" % PID
SEED = (
    "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
    "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, PID)
)
URL = HUB + "/?project=%s&tab=spec&document=%s" % (PID, PATH.replace("/", "%2F"))


def rows(pg):
    return sorted(
        el.get_attribute("data-testid").removeprefix("proposal-row-")
        for el in pg.query_selector_all("[data-testid^=proposal-row-]")
    )


def gone(pg, key):
    pg.wait_for_selector("[data-testid=proposal-row-%s]" % key, state="detached", timeout=15000)


with sync_playwright() as p:
    br = p.chromium.launch()
    wins = []
    for _ in range(2):  # two contexts: two independent app sessions, as two windows are
        ctx = br.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(SEED)
        pg = ctx.new_page()
        pg.goto(URL, wait_until="domcontentloaded")
        pg.get_by_test_id("spec-proposals-panel").wait_for(timeout=15000)
        pg.wait_for_selector("[data-testid=proposal-row-alpha]", timeout=15000)
        wins.append(pg)
    a, b = wins
    print("A rows", rows(a), "| B rows", rows(b))
    print("A header:", a.get_by_test_id("spec-proposals-panel").locator("span").first.inner_text())
    a.screenshot(path=SHOTS + "/01_A_three_pending.png")

    # Withdraw alpha in A.
    a.get_by_test_id("proposal-row-alpha").get_by_role("button", name="Withdraw").click()
    gone(a, "alpha")
    gone(b, "alpha")
    print("after withdraw: A", rows(a), "| B", rows(b))
    a.screenshot(path=SHOTS + "/02_A_after_withdraw.png")
    b.screenshot(path=SHOTS + "/03_B_after_withdraw.png")

    # Reject gamma in A with a reason; B watches.
    row = a.get_by_test_id("proposal-row-gamma")
    row.get_by_role("button", name="Reject", exact=True).click()
    row.get_by_placeholder("Reason (optional)").fill("drive: not wanted")
    a.screenshot(path=SHOTS + "/04_A_rejecting.png")
    row.get_by_role("button", name="Confirm reject").click()
    gone(a, "gamma")
    gone(b, "gamma")
    print("after reject: A", rows(a), "| B", rows(b))
    a.screenshot(path=SHOTS + "/05_A_after_reject.png")
    b.screenshot(path=SHOTS + "/06_B_after_reject.png")
    br.close()

import sqlite3  # noqa: E402

db = "file:" + os.environ["AW_DB"].replace("\\", "/") + "?mode=ro"
con = sqlite3.connect(db, uri=True)
cols = [r[1] for r in con.execute("pragma table_info(spec_edit_proposals)")]
extra = [c for c in ("decided_by", "decision_reason", "reason", "decided_at") if c in cols]
for r in con.execute("select unit_key, status%s from spec_edit_proposals order by created_at" % "".join(", " + c for c in extra)):
    print("row", r)
con.close()
print("pending via route:", [p["unit_key"] for p in api("GET", S + "/documents/%s/proposals" % PATH)[1]["proposals"]])
