"""2026-10-23 Flows & review drive, UI: the flow document's Spec page after the tester's amendment
(amendments panel "not reviewed", coverage, header facts).

  AW_P=proj-... py -3.11 scripts/drive/s1023_lb_ui3.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

DOC = "spec/changes/lb-flow/spec.json"
with Judge("s1023-lb3", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec")
    page.wait_for_timeout(4000)
    page.get_by_test_id(f"spec-list-row-{DOC}").first.click()
    page.wait_for_timeout(5000)
    text = " ".join((page.locator("main").first.text_content() or "").split())
    for word in ("not reviewed", "Not reviewed", "amend", "Amend", "tester"):
        i = text.find(word)
        print(word, "->", text[max(0, i - 200): i + 400] if i >= 0 else "ABSENT")
    j.shot(page, "spec", full_page=True)
    print("console errors:", j.errors[:5])
