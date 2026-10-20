"""Reach sweep 2026-10-20, UI: Environment -> Settings -> Reach (default posture, granted reach:
a refused save, a good save read back, a host typed but not added), and the agent page's
Execution -> Granted reach (inherit shows the project's; own; a refused save). Real browser,
served bundle on the scratch Hub (hub-up 8142).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_reach_ui.py <project-id>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1020_reach as R  # noqa: E402
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = sys.argv[1]
READ_ROOT = str(R.READ_ROOT)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def stored():
    s = e2e.call("GET", f"/projects/{P}/settings")
    return {k: s[k] for k in ("default_permission_mode", "reach_grants")}


R.settings(P, default_permission_mode=None, reach_grants=None)
with Judge("s1020-reach", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=environment&section=settings")
    page.wait_for_timeout(5000)
    editor = page.get_by_test_id("reach-grants-editor")
    print("EDITOR present:", editor.count())
    editor.first.scroll_into_view_if_needed()
    print("POSTURE options:", page.get_by_label("Default permissions").first.locator("option").all_text_contents())
    # 1. A relative root: what does the screen say when the Hub refuses the save?
    editor.get_by_role("button", name="Add root").click()
    page.get_by_label("Granted root 1", exact=True).fill("notes")
    page.get_by_role("button", name="Save settings").click()
    page.wait_for_timeout(2500)
    alerts = page.locator("[role=alert], .text-red, [style*='var(--red)']")
    print("AFTER BAD SAVE stored:", json.dumps(stored()))
    print("AFTER BAD SAVE red text:", [" ".join((alerts.nth(i).text_content() or "").split())[:300] for i in range(alerts.count())])
    j.shot(page, "01_bad_root_save", locator=editor.first.locator("xpath=ancestor::form[1]"))
    # 2. A good save: absolute read root, {temp}, a host added with Enter, a posture.
    page.get_by_label("Granted root 1", exact=True).fill(READ_ROOT)
    editor.get_by_role("button", name="Add the temp folder").click()
    host = page.get_by_role("textbox", name="Granted host", exact=True)
    host.fill("localhost:*")
    host.press("Enter")
    page.get_by_label("Default permissions").first.select_option("workspace")
    # 3. A host typed and not added: is it saved, dropped silently, or warned about?
    host.fill("registry.npmjs.org")
    page.get_by_role("button", name="Save settings").click()
    page.wait_for_timeout(2500)
    print("AFTER GOOD SAVE stored:", json.dumps(stored()))
    print("HOST DRAFT still in field:", host.input_value())
    j.shot(page, "02_good_save", locator=editor.first)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    ed = page.get_by_test_id("reach-grants-editor").first
    print("AFTER RELOAD editor text:", txt(ed)[:400],
          "| root1:", page.get_by_label("Granted root 1", exact=True).input_value())

    # The agent page.
    page2 = j.page(P, mode="light", query="agent=cla&settings=execution")
    page2.wait_for_timeout(5000)
    sel = page2.get_by_label("Granted reach for cla").first
    print("AGENT select options:", sel.locator("option").all_text_contents() if sel.count() else "<absent>")
    row = sel.locator("xpath=ancestor::div[2]")
    j.shot(page2, "03_agent_inherit", locator=row)
    sel.select_option("own")
    page2.wait_for_timeout(2500)
    agent = R.roster(P)["cla"]
    print("AGENT own after select:", json.dumps(agent.get("reach_grants")))
    # A refused save on the agent: an unparseable host.
    ahost = page2.get_by_role("textbox", name="Granted host", exact=True)
    ahost.fill("http://bad host")
    ahost.press("Enter")
    page2.get_by_role("button", name="Save granted reach").click()
    page2.wait_for_timeout(2500)
    reds = page2.locator("[style*='var(--red)']")
    print("AGENT bad save red text:", [" ".join((reds.nth(i).text_content() or "").split())[:300] for i in range(reds.count())])
    print("AGENT stored after bad save:", json.dumps(R.roster(P)["cla"].get("reach_grants")))
    j.shot(page2, "04_agent_bad_save", locator=row)
    sel.select_option("inherit")
    page2.wait_for_timeout(2000)
    print("AGENT after inherit:", json.dumps(R.roster(P)["cla"].get("reach_grants")))
    print("console errors:", j.errors[:8])

R.settings(P, default_permission_mode=None, reach_grants=None)
