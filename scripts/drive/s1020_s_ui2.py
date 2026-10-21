"""2026-10-20 spec sweep, browser follow-up: the corpus strip on the Spec tab's document browser
(untracked file -> Adopt all, Rebuild index), and Delete document from its dialog.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_s_ui2.py <project-id> <hub-url> <delete-doc>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from s1019_spec_lib import request  # noqa: E402
from uiharness import Judge  # noqa: E402

P, HUB, DEL = sys.argv[1:4]
BASE = f"/projects/{P}/project"


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


with Judge("s1020-spec2", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec")
    page.wait_for_timeout(5000)
    strip = page.get_by_test_id("spec-corpus-strip")
    if not strip.count():
        page.get_by_role("button", name="Tool ").first.click()  # the document picker in the toolbar
        page.wait_for_timeout(2500)
        strip = page.get_by_test_id("spec-corpus-strip")
    print("corpus strip:", txt(strip)[:800])
    j.shot(page, "01_corpus_strip", full_page=True)
    adopt = page.get_by_test_id("spec-corpus-adopt-all")
    if adopt.count():
        adopt.first.click()
        page.wait_for_timeout(3000)
        print("adopt result:", txt(page.get_by_test_id("spec-corpus-adopt-result"))[:800])
        print("unadoptable:", txt(page.get_by_test_id("spec-corpus-unadoptable"))[:400])
    rebuild = page.get_by_test_id("spec-corpus-rebuild")
    if rebuild.count():
        rebuild.first.click()
        page.wait_for_timeout(3000)
        for tid in ("spec-corpus-summary", "spec-corpus-diagnostics", "spec-corpus-home-question",
                    "spec-corpus-nothing", "spec-corpus-error", "spec-corpus-index"):
            print(tid + ":", txt(page.get_by_test_id(tid))[:500])
    j.shot(page, "02_after_adopt_rebuild", full_page=True)

    if not DEL:
        sys.exit(0)
    page = j.page(P, mode="light", query=f"tab=spec&document={DEL}")
    page.wait_for_timeout(5000)
    page.get_by_test_id("spec-delete").first.click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Delete document").click()
    page.wait_for_timeout(3000)
    print("after Delete document: listed:", any(d["path"] == DEL for d in request("GET", f"{BASE}/documents")[1]["documents"]),
          "| url:", page.url[-120:], "| main:", txt(page.locator("main"))[:300])
    j.shot(page, "03_after_delete", full_page=True)
