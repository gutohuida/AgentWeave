"""The Activity tab's Logs view and its filters, and F419, in Chromium against the served bundle.

    py -3.11 scripts/drive/s1023_ev_sse_logs.py <other-project-id>

Project A is the lib's P; the other project carries `betaother`, a task titled OTHERPROJECT and a
warn log `otherproject_probe`. Neither may appear on A's Logs or Activity views, live or loaded.
"""

import sys

from s1023_ev_sse_lib import B, P, e2e, req
from uiharness import Judge

OTHER = sys.argv[1]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def rows(page):
    out = []
    for r in page.locator(".log-row-main").all():
        spans = r.locator("> span").all()
        out.append(" | ".join(" ".join((s.text_content() or "").split()) for s in spans[1:]))
    return out


def other_leak(page):
    main = txt(page.locator("main"))
    return {k: (k in main) for k in ("betaother", "OTHERPROJECT", "otherproject_probe")}


with Judge("s1023-ev-sse-logs", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    page.locator("[aria-label='Activity view'] button", has_text="Logs").first.click()
    page.wait_for_timeout(4000)
    r = rows(page)
    print("LOGS rows:", len(r))
    for line in r[-8:]:
        print("   ", line[:200])
    print("leak of the other project (loaded):", other_leak(page))
    print("agent options:", [o.text_content() for o in page.locator("main select option").all()])
    j.shot(page, "logs_all", full_page=True)

    for sev in ("warn", "error", "debug", "all"):
        page.locator("main").get_by_role("button", name=sev, exact=True).first.click()
        page.wait_for_timeout(1500)
        r = rows(page)
        print(f"severity {sev}: {len(r)} rows; empty note:",
              txt(page.locator("main p", has_text="No entries match")), "|", [x[:90] for x in r[:3]])
    page.locator("main select").first.select_option("alpha")
    page.wait_for_timeout(2000)
    print("agent=alpha:", len(rows(page)))
    page.locator("main select").first.select_option("")
    page.wait_for_timeout(2000)
    for cat in ("runner", "jobs", "setup", "all"):
        page.locator("main").get_by_role("button", name=cat, exact=True).last.click()
        page.wait_for_timeout(1200)
        print(f"category {cat}: {len(rows(page))} rows")
    page.locator("main input[type='text']").first.fill("question")
    page.wait_for_timeout(1200)
    print("search 'question':", [x[:120] for x in rows(page)])
    page.locator("main input[type='text']").first.fill("")
    page.wait_for_timeout(1200)

    before = len(rows(page))
    print("POST log into A:", req("POST", f"{B}/logs", {"event_type": "drive_live_probe", "agent": "alpha",
                                                          "data": {"note": "live into A"}, "severity": "warn"})[0])
    print("POST log into OTHER:", req("POST", f"/projects/{OTHER}/logs", {
        "event_type": "otherproject_probe", "agent": "betaother", "data": {"note": "OTHERPROJECT live"},
        "severity": "error"})[0])
    page.wait_for_timeout(6000)
    after = rows(page)
    print(f"rows before {before}, after {len(after)} (no reload); probe present:",
          any("drive_live_probe" in x for x in after))
    print("leak of the other project (live):", other_leak(page))
    j.shot(page, "logs_live", full_page=True)

    page.locator("[aria-label='Activity view'] button", has_text="Activity").first.click()
    page.wait_for_timeout(3000)
    print("DIGEST:", [txt(x.locator(".aw-digest-sentence")) for x in page.locator(".aw-digest-row").all()][:8])
    print("leak of the other project (digest):", other_leak(page))
