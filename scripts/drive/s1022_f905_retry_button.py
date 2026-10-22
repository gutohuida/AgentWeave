"""night F905 in Chromium (served bundle): a task approved with a skip a retry can never clear
shows its "Not merged" line on the board card and no Retry button; the list payload says why.
    AW_P=<project> py -3.11 scripts/drive/s1022_f905_retry_button.py <task-id>"""
import os, pathlib, sys
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f902.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402
P = os.environ["AW_P"]; tid = sys.argv[1]
with Judge("s1022-f905", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(3000)
    line = page.get_by_test_id(f"task-card-status-{tid}")
    print("status line count:", line.count(), "reason:", line.get_attribute("data-reason") if line.count() else None,
          "text:", line.inner_text() if line.count() else None)
    card = page.locator(f"article[data-task-id='{tid}']")
    print("Retry buttons on the card:", card.get_by_role("button", name="Retry").count())
    j.shot(page, "card", full_page=False)
