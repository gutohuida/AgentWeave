"""Vault sweep 2026-10-23, UI: what the operator sees of a report the reports job referred because
it was shown only the first 50,000 characters of the source (F960), the corrected report beside it,
and the disputed fact in the reader. Real browser, served bundle on the scratch Hub.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1023_vault_ui.py <project-id> <fact-id>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_vault import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, FACT = sys.argv[1], sys.argv[2]


def txt(loc):
    return " ".join((loc.text_content() or "").split())


with Judge("s1023-vault", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=vault")
    page.wait_for_timeout(5000)
    vault = page.get_by_test_id("vault-page")
    print("VAULT page present:", vault.count())
    for label in ("Reports", "Review"):
        tab = page.get_by_role("tab", name=label)
        if not tab.count():
            tab = page.get_by_role("button", name=label)
        if tab.count():
            tab.first.click()
            page.wait_for_timeout(1500)
            print(f"{label.upper()} view:", txt(vault.first)[:1600])
            j.shot(page, f"01_{label.lower()}")
            break
    else:
        print("no Reports/Review control")
    entry = page.get_by_test_id(f"vault-entry-{FACT}")
    if not entry.count():
        page.get_by_role("tab", name="Library").first.click() if page.get_by_role(
            "tab", name="Library"
        ).count() else None
        page.wait_for_timeout(1000)
        entry = page.get_by_test_id(f"vault-entry-{FACT}")
    print("FACT entry present:", entry.count())
    if entry.count():
        entry.first.click()
        page.wait_for_timeout(1500)
        print("READER:", txt(vault.first)[:900])
        j.shot(page, "02_reader")
