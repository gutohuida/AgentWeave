"""A Copilot task's cost in Chromium (served bundle): the task drawer's story reads the run's AI
credits where a Claude run reads dollars, and never "$0.00" or "—" for a run that charged credits.
    AW_P=<project> py -3.11 scripts/drive/d1022_task_story_credits.py <task-id>"""
import os, pathlib, sys
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-credits1022.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402
P = os.environ["AW_P"]; tid = sys.argv[1]
with Judge("d1022-task-credits", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(3000)
    page.locator(f"article[data-task-id='{tid}']").first.click()
    summary = page.get_by_test_id(f"task-story-summary-{tid}")
    summary.wait_for(timeout=15000)
    cost = summary.locator(".aw-story-value").first.inner_text()
    print("summary cost:", repr(cost))
    runs = page.locator("[data-testid^='story-event-run-']")
    for i in range(runs.count()):
        print("run row:", repr(runs.nth(i).inner_text()[:160]))
    sub = summary.locator(".aw-story-sub").first.inner_text()
    print("summary sub:", repr(sub))
    ok = cost.strip().replace(".", "").isdigit() and sub.startswith("AI credits")
    print("PASS" if ok else "FAIL", "the summary reads the credit amount, its unit on the line below")
    j.shot(page, "drawer", full_page=False)
