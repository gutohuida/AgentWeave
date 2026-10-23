"""Conversations & composer, 2026-10-23: does the Spec tab's own list name a fresh, unindexed
exploration by its title or by its minted folder name (the side panel's tree shows the folder)?

    py -3.11 scripts/drive/s1023_cv_spec.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light")
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Spec").first.click() if page.get_by_role("button", name="Spec").count() else page.get_by_text("Spec", exact=True).first.click()
    page.wait_for_timeout(4000)
    text = norm(page.locator("main").first.text_content())
    print("SPEC TAB:", text[:700])
    print("has title:", "Composer drive change" in text, "| has folder name:", "silver-fenrir" in text)
    j.shot(page, "spec_tab_list")
