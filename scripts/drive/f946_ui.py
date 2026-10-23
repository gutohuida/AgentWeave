"""F946 drive: the Spec header does not say "Vault agrees" when no vault check ever ran.

A proposed change on a project whose spec-vault-check job is off, opened in Chromium: prints the
header's vault fact, then presses "Check against the vault" and prints the toast.

  AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/f946_ui.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_sp_lib import DOCS, P, e2e, payload, req  # noqa: E402
from uiharness import Judge  # noqa: E402

norm = lambda s: " ".join((s or "").split())  # noqa: E731

path = "spec/changes/vault-hdr/spec.json"
req("POST", DOCS, {"path": path, "title": "vault-hdr"})
print("PUT", req("PUT", f"{DOCS}/{path}/content", {"document": payload("vault-hdr", "vault-hdr", keys=("alpha", "beta"))})[0])
print("warnings route:", req("GET", f"/projects/{P}/vault/warnings?path={path}"))
with Judge("f946", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", width=1440, query="tab=spec")
    page.wait_for_timeout(4000)
    row = page.locator(f"[data-testid='spec-list-row-{path}']")
    print("row", row.count())
    if row.count():
        row.first.click()
    page.wait_for_timeout(3500)
    fact = page.get_by_test_id("spec-health-vault")
    print("FACT:", norm(fact.text_content()) if fact.count() else None)
    if fact.count():
        fact.first.click()
        page.wait_for_timeout(800)
        j.shot(page, "vault_fact_open")
        page.get_by_role("menuitem", name="Check against the vault").first.click()
        page.wait_for_timeout(2500)
        j.shot(page, "vault_check_toast")
        print("TOAST:", norm(page.locator("[role=status], [data-sonner-toast], .aw-toast").all_text_contents().__str__()))
    print("console errors:", j.errors[:5])
