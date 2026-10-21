"""Vault sweep 2026-10-21, UI: the Reports list's "Look into it" button on a pending report (F801),
pressed in a real browser on the served bundle of a scratch Hub (hub-up 8151). Prints what the
report card says after the press (the refusal, or the background note and later the answer).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_v_ui.py <project-id> <report-id> <label> [wait-s] [again-s]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_vault import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, REPORT, LABEL = sys.argv[1], sys.argv[2], sys.argv[3]
WAIT = int(sys.argv[4]) if len(sys.argv) > 4 else 3
# A second press this many seconds after the first (0: none) -- what the card allows meanwhile.
AGAIN = int(sys.argv[5]) if len(sys.argv) > 5 else 0


def txt(loc):
    return " ".join((loc.text_content() or "").split())


with Judge("s1021-vault", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=vault")
    page.wait_for_timeout(4000)
    tab = page.get_by_role("tab", name="Reports")
    if not tab.count():
        tab = page.get_by_role("button", name="Reports")
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(1500)
    button = page.get_by_test_id(f"vault-report-{REPORT}-review")
    card = button.locator("xpath=ancestor::article[1]")
    print("BUTTON present:", button.count())
    if button.count():
        print("BEFORE:", txt(card)[:400])
        button.click()
        if AGAIN:
            page.wait_for_timeout(AGAIN * 1000)
            print("BETWEEN:", txt(card)[:400], "| enabled:", button.is_enabled())
            if button.is_enabled():
                button.click()
                print("PRESSED AGAIN")
        page.wait_for_timeout(WAIT * 1000)
        print("AFTER:", txt(card)[:600] if card.count() else "<card gone>")
    j.shot(page, f"{LABEL}_after")
    reports = page.locator("article").filter(has_text="Report ")
    for i in range(reports.count()):
        print("  CARD", txt(reports.nth(i))[:400])
