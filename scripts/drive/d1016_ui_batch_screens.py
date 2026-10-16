"""Drive for the 2026-10-16 UI batch: the screens it changed, in a real browser.

Starts its own Hub from source on :8111 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. One project, one runner-less agent (nothing can spawn a turn), one job that is
archived, and one queued message so the agent has a conversation. A real Chromium then checks:
  F636  the Overview links to questions and permission decisions with no question open;
  F637  the Jobs page does not call an all-archived project empty, and lists the archived job;
  F635  Ctrl+K gives focus back to the control that had it, on Escape;
  F634  at a narrow width, the conversation's "Show panel" toggle opens the panel drawer;
and records every page error.

    py -3.11 scripts/drive/d1016_ui_batch_screens.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8111
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1016-ui-batch" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "uibatch"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, runner = d.api("POST", f"{base}/runners", {"name": "claude r", "cli": "claude"})
    assert code in (200, 201), (code, runner)
    code, out = d.api("POST", f"{base}/agents", {"name": "agent-a", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    code, out = d.api("PATCH", f"{base}/agents/agent-a", {"runner_id": None})
    code, job = d.api(
        "POST",
        f"{base}/jobs",
        {"name": "Nightly audit", "agent": "agent-a", "message": "go", "cron": "0 9 * * *", "enabled": False},
    )
    assert code in (200, 201), (code, job)
    code, out = d.api("POST", f"{base}/jobs/{job['id']}/archive")
    d.check("0 the job is archived", code == 200, f"{code} {out}")
    # A conversation to open: the message queues (no runner is bound, so no turn can start).
    code, sent = d.api("POST", f"{base}/agent/trigger", {"agent": "agent-a", "message": "Hello there"})
    d.check("0b a conversation exists", code == 200 and sent.get("conversation_id"), f"{code} {sent}")

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid)
    )
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
        d.check("1 the Overview loads",
                d.poll(lambda: page.get_by_role("heading", name="Attention").count() >= 1, 30))

        link = page.get_by_test_id("overview-questions-link")
        d.check("2 F636: the questions link shows with no question open",
                d.poll(lambda: link.count() == 1, 15))
        link.click()
        d.check("3 F636: it opens the page holding the permission decisions",
                d.poll(lambda: page.get_by_test_id("permission-decisions").count() == 1, 15))
        page.screenshot(path=str(d.SHOT) + "_questions.png", full_page=True)

        page.get_by_test_id("project-tab-jobs").first.click()
        d.check("4 F637: an all-archived project is not called empty",
                d.poll(lambda: page.get_by_text("No active or paused jobs").count() == 1, 15)
                and page.get_by_text("No jobs yet").count() == 0)
        page.get_by_role("button", name="Show archived").click()
        d.check("5 F637: the archived job is listed",
                d.poll(lambda: page.get_by_test_id(f"archived-job-{job['id']}").count() == 1, 10))
        page.screenshot(path=str(d.SHOT) + "_jobs.png", full_page=True)

        tab = page.get_by_test_id("project-tab-jobs").first
        tab.focus()
        page.keyboard.press("Control+k")
        d.check("6 F635: Ctrl+K opens the palette",
                d.poll(lambda: page.get_by_placeholder("Search conversations, agents, documents, tasks…").count() == 1, 10))
        page.keyboard.press("Escape")
        d.check("7 F635: Escape gives focus back to the tab that had it",
                d.poll(lambda: page.evaluate("document.activeElement && document.activeElement.dataset.testid") == "project-tab-jobs", 5),
                str(page.evaluate("document.activeElement && document.activeElement.outerHTML.slice(0, 120)")))

        page.set_viewport_size({"width": 700, "height": 900})
        rail = page.get_by_test_id(f"rail-agent-{pid}-agent-a")
        if rail.count() == 0:
            page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_test_id(f"rail-agent-{pid}-agent-a").count() >= 1, 20)
        page.get_by_test_id(f"rail-agent-{pid}-agent-a").first.click()
        toggle = page.get_by_test_id("conversation-toggle-panel")
        d.check("8 the conversation renders with its panel toggle", d.poll(lambda: toggle.count() >= 1, 20))
        toggle.first.click()
        d.check("9 F634: at 700 px the toggle opens the panel drawer",
                d.poll(lambda: page.get_by_test_id("workspace-drawer").count() == 1, 10))
        page.screenshot(path=str(d.SHOT) + "_narrow_panel.png", full_page=True)
        d.check("10 no page error", not errors, str(errors[:3]))
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
