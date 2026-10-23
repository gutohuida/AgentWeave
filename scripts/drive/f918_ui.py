"""F918 UI drive: the Vault Add dialog refuses a .docx per file and still takes a .txt.

  py -3.11 scripts/drive/f918_ui.py <project-id> <dir holding minutes.docx and notes.txt>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_reach import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
norm = lambda s: " ".join((s or "").split())  # noqa: E731

with Judge("f918", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=vault")
    page.wait_for_selector("[data-testid=vault-page]", timeout=20000)
    page.wait_for_timeout(1500)
    print("PAGE:", norm(page.locator("body").text_content())[:400])
    page.get_by_test_id("vault-upload-open").click(timeout=5000)
    page.get_by_test_id("vault-upload-file").set_input_files(
        [str(DIR / "minutes.docx"), str(DIR / "notes.txt")])
    page.get_by_test_id("vault-upload-submit").click()
    page.wait_for_timeout(3000)
    dialog = page.get_by_role("dialog")
    print("DIALOG after add:", dialog.count(), norm(dialog.text_content())[:500] if dialog.count() else "")
    j.shot(page, "docx_refused")
    st, m = e2e.request("GET", f"/projects/{P}/vault/map")
    print("MAP:", [(x["name"], x["media_type"]) for x in m["entries"]])
    print("console errors:", j.errors[:5])
