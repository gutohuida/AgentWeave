"""night-recheck F824 in Chromium (served bundle, :8160): delete a task from its drawer; count the
requests for the deleted task's story and when the card leaves the board.
    AW_P=<project> py -3.11 scripts/drive/s1021_r_ui.py <task-id>"""
import os, pathlib, sys, time
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-r1021.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402
P = os.environ["AW_P"]; tid = sys.argv[1]
with Judge("s1021-r", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(3000)
    hits = []
    page.on("response", lambda r: hits.append((time.time(), r.request.method, r.url.split("/api/v1")[-1], r.status)))
    page.get_by_test_id(f"task-open-{tid}").first.click()
    page.wait_for_timeout(1500)
    page.get_by_role("tab", name="Details").first.click() if page.get_by_role("tab", name="Details").count() else page.get_by_text("Details").first.click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Delete").first.click()
    page.wait_for_timeout(600)
    t0 = time.time(); hits.clear()
    page.get_by_role("button", name="Delete task").first.click()
    for sec in (2, 5, 10):
        page.wait_for_timeout(int((sec - (time.time() - t0)) * 1000))
        card = page.get_by_test_id(f"task-open-{tid}").count()
        story = [h for h in hits if tid in h[2] and "story" in h[2]]
        print(f"t+{sec}s card_present={card} story_requests={len(story)} statuses={sorted({h[3] for h in story})}")
    dt = [h[0] for h in hits if h[1] == "DELETE"][0]; print("delete calls:", [(h[1], h[3]) for h in hits if h[1] == "DELETE"]); [print("  dt=%+.2fs" % (h[0]-dt), h[1], h[2][:90], h[3]) for h in hits if tid in h[2]]
    j.shot(page, "after-delete", full_page=False)
