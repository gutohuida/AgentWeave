"""Ledger sweep 2026-10-19, UI: the Activity tab's Ledger view, a conversation's Checkpoints sheet
(predecessor and successor), and the composer's @ picker on a non-ASCII file name, in a real browser
against the served bundle.

  py -3.11 scripts/drive/s1019_ledger_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1019_ledger_lib import S, api, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]
for name in ("builder", "rev"):
    print("rebind", name, api("PATCH", f"/projects/{P}/agents/{name}", {"runner_id": S["RUNNER"]})[0])


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


with Judge("s1019-ledger", hub=e2e.hub(), key=e2e.key()) as j:
    # 1. Activity -> Ledger (the default subview)
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(5000)
    led = page.get_by_test_id("project-ledger")
    print("LEDGER present:", led.count())
    print("LEDGER totals:", txt(page.get_by_test_id("ledger-totals")))
    print("LEDGER text:", txt(led)[:3500])
    links = led.locator("a, button")
    print("LEDGER links:", [(" ".join((links.nth(i).text_content() or "").split())[:40]) for i in range(min(links.count(), 30))])
    j.shot(page, "01_ledger", full_page=True)

    # 2. Checkpoints sheet on the archived predecessor, then on the successor
    for label, conv in (("pred", S["C1"]), ("succ", S.get("C2"))):
        page = j.page(P, mode="light", query=f"agent=builder&conversation={conv}")
        page.wait_for_timeout(5000)
        btn = page.get_by_role("button", name="Checkpoints")
        print(label, "Checkpoints button:", btn.count(), btn.first.get_attribute("title") if btn.count() else None)
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(2000)
            panel = page.get_by_test_id("checkpoints-panel")
            print(label, "PANEL:", txt(panel)[:2500])
            j.shot(page, f"02_checkpoints_{label}", full_page=False)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            print(label, "panel after Escape:", page.get_by_test_id("checkpoints-panel").count())
        banner = page.locator("[data-testid*='banner'], [role='status']")
        print(label, "banners:", [txt(banner.nth(i))[:200] for i in range(min(banner.count(), 5))])

    # 3. The composer's @ picker on the open conversation
    page = j.page(P, mode="light", query=f"agent=builder&conversation={S['C2']}")
    page.wait_for_timeout(5000)
    box = page.locator("textarea").first
    box.click()
    box.type("look at @notes")
    page.wait_for_timeout(1500)
    menu = page.locator("[role='listbox'] [role='option'], [role='option']")
    print("@notes options:", [txt(menu.nth(i)) for i in range(min(menu.count(), 8))])
    j.shot(page, "03_at_picker", full_page=False)
    if menu.count():
        menu.first.click()
        page.wait_for_timeout(500)
        print("composer after pick:", box.input_value())
    box.fill("")
    box.type("@logo")
    page.wait_for_timeout(1200)
    print("@logo options:", [txt(menu.nth(i)) for i in range(min(menu.count(), 8))])
    print("errors:", j.errors[:10])
