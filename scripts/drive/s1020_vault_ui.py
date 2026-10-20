"""Vault sweep 2026-10-20, UI: the Vault tab after bulk adds by path (entry names with their folder,
the private one an agent added, the pending report with no runner behind it) and Environment ->
Manager (each job's row, the firings with their outcome). Real browser, served bundle on the
scratch Hub (hub-up 8143).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_vault_ui.py <project-id>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_vault import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = sys.argv[1]


def txt(loc):
    return " ".join((loc.text_content() or "").split())


with Judge("s1020-vault", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=vault")
    page.wait_for_timeout(5000)
    vault = page.get_by_test_id("vault-page")
    print("VAULT page present:", vault.count())
    entries = page.locator("[data-testid^='vault-entry-']")
    print("ENTRIES:", entries.count())
    for i in range(min(entries.count(), 20)):
        print("  ", txt(entries.nth(i))[:160])
    j.shot(page, "01_vault")
    for label in ("Reports", "Contradictions"):
        tab = page.get_by_role("tab", name=label)
        if not tab.count():
            tab = page.get_by_role("button", name=label)
        if tab.count():
            tab.first.click()
            page.wait_for_timeout(1500)
            print(f"{label.upper()} view:", txt(vault.first)[:900])
            j.shot(page, f"02_{label.lower()}")
        else:
            print(f"{label}: no tab or button")

    page2 = j.page(P, mode="light", query="tab=environment&section=manager")
    page2.wait_for_timeout(5000)
    for key in ("conversation-titles", "vault-distillation", "vault-reports", "spec-vault-check"):
        row = page2.get_by_test_id(f"manager-job-{key}")
        print("JOB", key, ":", txt(row.first)[:300] if row.count() else "<absent>")
    firings = page2.locator("[data-testid^='manager-firing-']")
    print("FIRINGS:", firings.count())
    for i in range(firings.count()):
        print("  ", txt(firings.nth(i))[:300])
    j.shot(page2, "03_manager")
