"""Reach sweep 2026-10-21, UI (real browser, served bundle on the scratch Hub):

  1. F794 on screen: the read-grant refusal in Activity -> Activity and in cla's conversation;
  2. F795: the agent page's Granted reach -> own -> an unparseable host -> Save shows the Hub's
     field-and-message sentence, not only "Could not save the granted reach.";
  3. the project Reach group's refused save, for comparison.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_rc_reach_ui.py <project-id>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1020_reach as R  # noqa: E402
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = sys.argv[1]
GRANT = "granted for reading only"


def norm(s):
    return " ".join((s or "").split())


with Judge("s1021-reach", hub=e2e.hub(), key=e2e.key()) as j:
    # 1a. Activity -> Activity.
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(4000)
    page.get_by_role("radiogroup", name="Activity view").get_by_role("radio", name="Activity").click()
    page.wait_for_timeout(3000)
    body = norm(page.locator("main").first.text_content())
    print("ACTIVITY has read-grant sentence:", GRANT in body, "| outside:", "outside your workspace" in body)
    idx = body.find("refused")
    print("ACTIVITY around 'refused':", body[max(0, idx - 80): idx + 360])
    j.shot(page, "01_activity")
    # 1b. Logs.
    page.get_by_role("radiogroup", name="Activity view").get_by_role("radio", name="Logs").click()
    page.wait_for_timeout(3000)
    body = norm(page.locator("main").first.text_content())
    print("LOGS has read-grant sentence:", GRANT in body)
    j.shot(page, "02_logs")

    # 1c. cla's conversation.
    page = j.page(P, mode="light")
    page.wait_for_timeout(3000)
    page.get_by_text("cla", exact=True).first.click()
    page.wait_for_timeout(4000)
    for summ in page.locator("details.work-disclosure > summary").all():
        summ.click()
        page.wait_for_timeout(500)
    for _ in range(20):
        closed = page.locator("details.work-disclosure button[aria-expanded=false]")
        if not closed.count():
            break
        try:
            closed.first.click(timeout=2000)
        except Exception:  # noqa: BLE001 -- a row that re-rendered under the click
            pass
        page.wait_for_timeout(200)
    page.wait_for_timeout(1000)
    body = norm(page.locator("main").first.text_content())
    print("CONVERSATION has read-grant sentence:", GRANT in body, "| tool failed:", "tool failed" in body)
    for needle in ("Bash", "Write"):
        k = body.find(needle)
        print(f"CONVERSATION around {needle}:", body[max(0, k - 60): k + 300] if k >= 0 else "<absent>")
    j.shot(page, "03_conversation", full_page=True)

    if __import__("os").environ.get("ONLY_SCREEN"):
        print("console errors:", j.errors[:8])
        raise SystemExit(0)
    # 2. F795 on the agent page (ui-finesse: a switch "Own granted reach for cla" and chips that
    #    save on each change; a refusal shows "That change was not saved." under the heading).
    def add_host(pg, scope, value, how="enter"):
        scope.get_by_role("button", name="Add", exact=True).first.click()
        pg.get_by_role("menuitem", name="A host…").click()
        box = scope.get_by_role("textbox", name="Host", exact=True)
        box.fill(value)
        if how == "enter":
            box.press("Enter")
        else:  # F796: leave the field without pressing Enter
            pg.locator("h1, h2").first.click()
        pg.wait_for_timeout(2500)

    def shown(pg):
        notes = pg.locator("[role=alert], [data-tone=error], .aw-settings-notice")
        return [norm(notes.nth(i).text_content())[:300] for i in range(notes.count())]

    page2 = j.page(P, mode="light", query="agent=cla&settings=execution")
    page2.wait_for_timeout(5000)
    sw = page2.get_by_role("switch", name="Own granted reach for cla").first
    print("AGENT switch before:", sw.get_attribute("aria-checked"))
    if sw.get_attribute("aria-checked") != "true":
        sw.click()
    page2.wait_for_timeout(2500)
    print("AGENT own after switch:", json.dumps(R.roster(P)["cla"].get("reach_grants")))
    scope = page2
    print("AGENT Add buttons on page:", page2.get_by_role("button", name="Add", exact=True).count())
    add_host(page2, scope, "http://bad host")
    print("AGENT bad save notices:", shown(page2))
    print("AGENT stored after bad save:", json.dumps(R.roster(P)["cla"].get("reach_grants")))
    j.shot(page2, "04_agent_bad_save")
    add_host(page2, scope, "localhost:*", how="blur")
    print("AGENT after blur-add good host:", json.dumps(R.roster(P)["cla"].get("reach_grants")), "| notices:", shown(page2))
    j.shot(page2, "04b_agent_good_host")
    sw.click()
    page2.wait_for_timeout(2000)
    print("AGENT after switch off:", json.dumps(R.roster(P)["cla"].get("reach_grants")))

    # 3. The project Reach group's refused save.
    R.settings(P, default_permission_mode=None, reach_grants=None)
    page3 = j.page(P, mode="light", query="tab=environment&section=settings")
    page3.wait_for_timeout(5000)
    lab = page3.get_by_text("Granted reach", exact=True).first
    print("PROJECT 'Granted reach' label present:", lab.count())
    lab.scroll_into_view_if_needed()
    print("PROJECT Add buttons on page:", page3.get_by_role("button", name="Add", exact=True).count())
    add_host(page3, page3, "http://bad host")
    print("PROJECT bad save notices:", shown(page3))
    s = e2e.call("GET", f"/projects/{P}/settings")
    print("PROJECT stored:", json.dumps(s["reach_grants"]))
    j.shot(page3, "05_project_bad_save")
    print("console errors:", j.errors[:8])
