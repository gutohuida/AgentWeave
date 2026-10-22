"""2026-10-22 evidence sweep, the drift strip in Chromium (after s1022_ev_drift.py): the re-raised
candidate's row (F834: does it say the evidence's earlier candidate was answered?), then Scan for
drift with the repository's .git moved aside (what the operator reads), restored after.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1022_ev_ui2.py <hub-url>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import MEMO, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB = sys.argv[1]
M = json.loads(MEMO.read_text())
P, DOC, DIR = M["project"], M["doc"], pathlib.Path(M["dir"])


def t(scope, tid):
    loc = scope.get_by_test_id(tid)
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else f"<no {tid}>"


with Judge("s1022-evidence-drift", hub=HUB, key=e2e.key()) as j:
    page = j.page(P, mode="light", query=f"tab=spec&document={DOC}")
    page.get_by_test_id("spec-health-drift").wait_for(timeout=30000)
    page.wait_for_timeout(2000)
    print("health line:", " | ".join(t(page, f"spec-health-{k}") for k in ("requirements", "drift", "tasks")))
    page.get_by_test_id("spec-health-drift").click()
    page.wait_for_timeout(800)
    page.get_by_role("menuitem", name="Show details").click()
    page.wait_for_timeout(1500)
    print("drift panel:", t(page, "spec-drift-panel")[:900])
    j.shot(page, "01_reraised", locator=page.get_by_test_id("spec-drift-panel").first)

    git_dir, aside = DIR / ".git", DIR / ".git-aside"
    git_dir.rename(aside)
    try:
        page.get_by_test_id("spec-drift-scan").click()
        page.wait_for_timeout(3000)
        print("scan with .git gone:", t(page, "spec-drift-scanned"))
        print("panel then:", t(page, "spec-drift-panel")[:500])
        j.shot(page, "02_scan_no_repo", locator=page.get_by_test_id("spec-drift-panel").first)
    finally:
        aside.rename(git_dir)
    print("restored:", git_dir.is_dir())
