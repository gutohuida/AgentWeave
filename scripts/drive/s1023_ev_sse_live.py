"""F251 live staleness, in Chromium against the served bundle (scratch Hub :8119, profile ev1023).

Each mode opens a screen, makes one change through the operator API (the way another window or an
agent would), waits, reads the screen without a reload, then reloads and reads it again.

  decline   Activity digest + Overview while an operator-seeded question is declined
            (`question_declined`, not on useSSE's allowlist)
  rename    the rail and the conversation header while the conversation is renamed through the
            route (`conversation_updated`)
  jobarch   the Jobs tab while a disabled job is archived through the route (`job_archived`)
  projdel   the rail while a second project is deleted through the route (`project_deleted`)

  py -3.11 scripts/drive/s1023_ev_sse_live.py <mode> [arg]
"""

import json
import sys
import time

from s1023_ev_sse_lib import B, P, e2e, q, req
from uiharness import Judge

WHAT = sys.argv[1]
ARG = sys.argv[2] if len(sys.argv) > 2 else None
WAIT_MS = 12000


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def digest_rows(page):
    return [txt(r.locator(".aw-digest-sentence")) for r in page.locator(".aw-digest-row").all()]


def open_digest(j):
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
    page.wait_for_timeout(3000)
    return page


with Judge("s1023-ev-sse-live", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "decline":
        st, qn = req("POST", f"{B}/questions", {
            "from_agent": "alpha", "question": "Which border colour should the drive use?",
            "header": "Border", "multi_select": False,
            "options": [{"label": "red", "description": "red"}, {"label": "blue", "description": "blue"}]})
        print("seed question", st, json.dumps(qn)[:200])
        page = open_digest(j)
        ov = j.page(P, mode="light", query="tab=overview")
        ov.wait_for_timeout(5000)
        print("DIGEST BEFORE:", digest_rows(page)[:4], "| note:", txt(page.locator(".aw-activity-count")))
        print("NEEDS BEFORE:", [txt(n.locator(".aw-ov-need-title")) for n in ov.locator(".aw-ov-need").all()])
        st, res = req("POST", f"{B}/questions/{qn['id']}/decline", {})
        print("decline", st, json.dumps(res)[:200])
        page.wait_for_timeout(WAIT_MS)
        print("DIGEST AFTER (no reload):", digest_rows(page)[:4], "| note:", txt(page.locator(".aw-activity-count")))
        print("NEEDS AFTER (no reload):", [txt(n.locator(".aw-ov-need-title")) for n in ov.locator(".aw-ov-need").all()])
        j.shot(page, "decline_digest_live")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
        page.wait_for_timeout(3000)
        print("DIGEST AFTER RELOAD:", digest_rows(page)[:4], "| note:", txt(page.locator(".aw-activity-count")))
        print("events:", q("select event_type, timestamp from event_logs where project_id=? order by timestamp desc limit 3", P))
    elif WHAT == "rename":
        conv = ARG or q("select id from conversations where project_id=? and agent='alpha' and lifecycle='open'"
                        " order by sequence desc limit 1", P)[0]["id"]
        page = j.page(P, mode="light", query=f"agent=alpha&conversation={conv}")
        page.wait_for_timeout(6000)
        side, main = page.locator("[data-testid='sidebar']"), page.locator("main")
        print("RAIL BEFORE:", txt(side)[:300])
        print("MAIN TOP BEFORE:", txt(main)[:160])
        new = f"Renamed by drive {time.strftime('%H%M%S')}"
        st, res = req("PATCH", f"{B}/agent/alpha/conversations/{conv}", {"title": new})
        print("rename", st, json.dumps(res)[:200])
        page.wait_for_timeout(WAIT_MS)
        print("RAIL AFTER (no reload) has new title:", new in txt(side), "|", txt(side)[:300])
        print("MAIN TOP AFTER (no reload) has new title:", new in txt(main), "|", txt(main)[:160])
        j.shot(page, "rename_live")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        side, main = page.locator("[data-testid='sidebar']"), page.locator("main")
        print("RAIL AFTER RELOAD has new title:", new in txt(side), "| MAIN:", new in txt(main))
    elif WHAT == "jobarch":
        st, job = req("POST", f"{B}/jobs", {"name": "drive-archive-probe", "agent": "alpha",
                                             "message": "noop", "cron": "0 3 * * *", "enabled": False})
        print("job create", st, json.dumps(job)[:300])
        jid = job.get("id") if isinstance(job, dict) else None
        page = j.page(P, mode="light", query="tab=jobs")
        page.wait_for_timeout(5000)
        main = page.locator("main")
        print("JOBS BEFORE lists probe:", "drive-archive-probe" in txt(main), "|", txt(main)[:300])
        st, res = req("POST", f"{B}/jobs/{jid}/archive", {})
        print("archive", st, json.dumps(res)[:200])
        page.wait_for_timeout(WAIT_MS)
        print("JOBS AFTER (no reload):", txt(main)[:400])
        j.shot(page, "jobarch_live")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("JOBS AFTER RELOAD:", txt(page.locator("main"))[:400])
        print("job row:", q("select id, enabled, archived_at from ai_jobs where id=?", jid))
    elif WHAT == "projdel":
        other = ARG
        page = j.page(P, mode="light", query="tab=overview")
        page.wait_for_timeout(5000)
        side = page.locator("[data-testid='sidebar']")
        sel = f"[data-testid='rail-project-{other}']"
        print("RAIL BEFORE has other:", page.locator(sel).count(), "|", txt(side)[:300])
        st, res = req("DELETE", f"/projects/{other}")
        print("delete", st, json.dumps(res)[:200])
        page.wait_for_timeout(WAIT_MS)
        print("RAIL AFTER (no reload) has other:", page.locator(sel).count(), "|", txt(side)[:300])
        j.shot(page, "projdel_live")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("RAIL AFTER RELOAD has other:", page.locator(sel).count())
