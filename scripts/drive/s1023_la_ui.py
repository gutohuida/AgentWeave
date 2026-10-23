"""Jobs & loops drive 2026-10-23, UI (real Chromium, served bundle, :8111).

jobs <name> [<name> ...]  -- Jobs screen: each named job's row text, then Run now and the switch;
                             what reaches the screen (notice / toast)
looptab <loop_id>          -- the loop's side-panel tab text

py -3.11 scripts/drive/s1023_la_ui.py <phase> [args]
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1023_la_lib import P, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def row_of(page, name):
    return page.locator("ul[aria-label='Jobs'] > li").filter(has_text=name).first


def jobs(*names):
    with Judge("s1023-la-jobs", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="tab=jobs")
        page.wait_for_timeout(5000)
        j.shot(page, "jobs-0", full_page=True)
        for name in names:
            row = row_of(page, name)
            print(f"\n=== {name}\nROW:", norm(row.text_content())[:500])
            run = row.get_by_role("button", name=re.compile("Run now"))
            print("run enabled:", run.is_enabled())
            if run.is_enabled():
                run.click()
                page.wait_for_timeout(2500)
                print("AFTER RUN body-notice:", notice(page))
                print("TOASTS:", toasts(page))
            sw = row.get_by_role("switch")
            if sw.count():
                print("switch:", sw.first.get_attribute("aria-label"), sw.first.get_attribute("aria-checked"))
                if sw.first.get_attribute("aria-checked") == "false":
                    sw.first.click()
                    page.wait_for_timeout(2500)
                    print("AFTER RESUME notice:", notice(page))
                    print("TOASTS:", toasts(page))
                    print("switch now:", sw.first.get_attribute("aria-checked"))
            j.shot(page, f"jobs-{re.sub('[^a-z0-9]+', '-', name.lower())}", full_page=True)
        print("ERRORS", j.errors)


def notice(page):
    for sel in ("[role='alert']", ".aw-jobs-notice", "[data-testid='jobs-notice']"):
        loc = page.locator(sel)
        if loc.count():
            return " | ".join(norm(loc.nth(i).text_content()) for i in range(loc.count()))[:800]
    return "<no alert>"


def toasts(page):
    loc = page.locator(".aw-toast")
    return " | ".join(norm(loc.nth(i).text_content()) for i in range(loc.count()))[:800] or "<no toast>"


def looptab(loop_id, agent="alpha"):
    with Judge("s1023-la-loop", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query=f"agent={agent}")
        page.wait_for_timeout(4000)
        page.locator('[data-testid="conversation-more"]').first.click()
        page.wait_for_timeout(400)
        page.locator('[data-testid="conversation-toggle-panel"]').first.click()
        page.wait_for_timeout(800)
        if page.locator('[data-testid="loops-index-tab"]').count() == 0:
            page.locator('[data-testid="panel-tab-add"]').first.click()
            page.wait_for_timeout(500)
            page.get_by_role("menuitem", name=re.compile("Loops", re.I)).first.click()
            page.wait_for_timeout(1500)
        page.locator(f'[data-testid="loops-index-row-{loop_id}"]').first.click()
        page.wait_for_timeout(2500)
        t = norm(page.locator('[data-testid="panel-tab-content"]').text_content())
        print("LOOPTAB:", t[:3000])
        j.shot(page, f"looptab-{loop_id}", full_page=True)
        print("ERRORS", j.errors)


def open_loop(page, loop_id):
    page.locator('[data-testid="conversation-more"]').first.click()
    page.wait_for_timeout(400)
    page.locator('[data-testid="conversation-toggle-panel"]').first.click()
    page.wait_for_timeout(800)
    if page.locator('[data-testid="loops-index-tab"]').count() == 0:
        page.locator('[data-testid="panel-tab-add"]').first.click()
        page.wait_for_timeout(500)
        page.get_by_role("menuitem", name=re.compile("Loops", re.I)).first.click()
        page.wait_for_timeout(1500)
    if page.locator(f'[data-testid="loops-index-row-{loop_id}"]').count() == 0:
        sa = page.get_by_text("Show archived")
        if sa.count():
            sa.first.click()
            page.wait_for_timeout(1200)
    page.locator(f'[data-testid="loops-index-row-{loop_id}"]').first.click()
    page.wait_for_timeout(2500)
    return page.locator('[data-testid="loop-tab"]').first


def tabtext(page):
    return norm(page.locator('[data-testid="loop-tab"]').first.text_content())


def flowc(loop_id):
    """Flow C: Edit -> uncheck stop-when-empty -> Save (want the refusal, nothing sent); edit the
    purpose -> Save (staged); Let alpha decide / Decide them yourself; Stop with a reason."""
    with Judge("s1023-la-flowc", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=alpha")
        page.wait_for_timeout(4000)
        tab = open_loop(page, loop_id)
        print("TAB0:", tabtext(page)[:1500])
        sent = []
        page.on("request", lambda r: sent.append(f"{r.method} {r.url}") if r.method in ("PATCH", "POST") else None)
        tab.get_by_role("button", name="Edit").first.click()
        page.wait_for_timeout(600)
        tab.get_by_label("Stop when the queue empties").uncheck()
        tab.get_by_role("button", name="Save").first.click()
        page.wait_for_timeout(1500)
        print("NO-STOP alert:", [norm(a.text_content()) for a in tab.get_by_role("alert").all()], "sent:", sent)
        j.shot(page, "flowc-1-nostop", full_page=True)
        tab.get_by_label("Stop when the queue empties").check()
        purpose = tab.locator("textarea, input[type=text]").first
        purpose.fill("Flow C, purpose edited in the tab")
        tab.get_by_role("button", name="Save").first.click()
        page.wait_for_timeout(2500)
        print("STAGED tab:", tabtext(page)[:1500], "sent:", sent)
        j.shot(page, "flowc-2-staged", full_page=True)
        b = tab.get_by_role("button", name=re.compile("Let .* decide"))
        print("delegate buttons:", b.count())
        if b.count():
            b.first.click(); page.wait_for_timeout(2000)
            print("AFTER DELEGATE:", norm(tab.locator('[data-testid="loop-tab-controller"]').text_content()))
            tab.get_by_role("button", name="Decide them yourself").first.click(); page.wait_for_timeout(2000)
            print("AFTER TAKE BACK:", norm(tab.locator('[data-testid="loop-tab-controller"]').text_content()))
        tab.get_by_role("button", name="Stop", exact=True).first.click()
        page.wait_for_timeout(600)
        print("STOP confirm:", norm(tab.locator('[data-testid="loop-tab-stop-confirm"]').text_content()))
        tab.locator('[data-testid="loop-tab-stop-confirm"] input').fill("UI drive: stopping flow C on purpose")
        tab.get_by_role("button", name="Stop loop").first.click()
        page.wait_for_timeout(3000)
        print("ENDED tab:", tabtext(page)[:2000])
        j.shot(page, "flowc-3-ended", full_page=True)
        print("ERRORS", j.errors)


def ended(loop_id):
    with Judge("s1023-la-ended", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=alpha")
        page.wait_for_timeout(4000)
        open_loop(page, loop_id)
        print("TAB:", tabtext(page)[:2500])
        j.shot(page, f"ended-{loop_id}", full_page=True)
        print("ERRORS", j.errors)


def latency(loop_id, agent="alpha"):
    """How long the loop tab takes to show a Delegate / Take back the Hub already applied."""
    import time as _t
    with Judge("s1023-la-latency", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query=f"agent={agent}")
        page.wait_for_timeout(4000)
        tab = open_loop(page, loop_id)
        resp = []
        page.on("response", lambda r: resp.append((round(_t.time() - t0, 2), r.request.method, r.url.split("/api/v1/")[-1][:70], r.status)))
        ctl = tab.locator('[data-testid="loop-tab-controller"]')
        for label in (re.compile("Let .* decide"), re.compile("Decide them yourself")):
            before = norm(ctl.text_content())
            t0 = _t.time()
            tab.get_by_role("button", name=label).first.click(timeout=5000)
            while _t.time() - t0 < 30 and norm(ctl.text_content()) == before:
                page.wait_for_timeout(250)
            print(f"{label.pattern}: tab changed after {_t.time() - t0:.1f}s ->", norm(ctl.text_content()))
            print("  responses:", [r for r in resp if "loops" in r[2] or "jobs" in r[2]][:12])
            resp.clear()
        print("ERRORS", j.errors)


def storm(loop_id, agent="alpha"):
    """Count the loop tab's GETs: idle, then in the 10 s after one Delegate press."""
    import collections, time as _t
    with Judge("s1023-la-storm", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query=f"agent={agent}")
        page.wait_for_timeout(4000)
        tab = open_loop(page, loop_id)
        seen = []
        page.on("request", lambda r: seen.append((_t.time(), r.method, r.url.split("/api/v1/")[-1].split("?")[0][-60:])))
        page.wait_for_timeout(10000)
        print("IDLE 10s:", collections.Counter(f"{m} {u}" for _, m, u in seen).most_common(8))
        seen.clear()
        ctl = tab.locator('[data-testid="loop-tab-controller"]')
        tab.get_by_role("button", name=re.compile("Let .* decide")).first.click()
        page.wait_for_timeout(10000)
        print("AFTER PRESS 10s:", collections.Counter(f"{m} {u}" for _, m, u in seen).most_common(8))
        print("controller:", norm(ctl.text_content()))
        seen.clear()
        page.wait_for_timeout(10000)
        print("NEXT 10s:", collections.Counter(f"{m} {u}" for _, m, u in seen).most_common(8))
        tab.get_by_role("button", name="Decide them yourself").first.click()
        page.wait_for_timeout(3000)
        print("ERRORS", j.errors)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
