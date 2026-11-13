"""AW-128 drive: a new project opens on a welcome, suggestions fit it, a non-git folder offers a repository.

Starts its own Hub on :8103 with a fresh database in the system temp directory (never :8000 or
:8010). Opens a plain folder (not a git repository) as a project and, in Chromium:

  1. the Overview shows the first-run panel with Add an agent, the quickstart link, and the
     repository offer from the set-up list;
  2. with an agent added, the panel offers Ask <agent> for a change, which opens a new conversation
     whose suggestions are the empty-project ones;
  3. once the project has a task the panel is gone, and the suggestions are the ordinary ones.

Screenshots land beside the database. Run:  py -3.11 scripts/drive/aw128_first_run.py
"""

import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from aw import make_agent  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8103
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = pathlib.Path(tempfile.gettempdir()) / "aw128drive" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def drive():
    import aw

    aw.api = d.api
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    (root / "README.md").write_text("A folder with no repository.\n", encoding="utf-8")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "aw128"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    seed = (f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, hubUrl: {d.HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {pid!r});")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)

        def overview():
            page.goto(f"{d.HUB}/?project={pid}&tab=overview", wait_until="domcontentloaded")
            d.poll(lambda: page.locator(".aw-overview").count() == 1, 20)
            page.wait_for_timeout(1500)

        overview()
        panel = page.locator("[data-testid=first-run-panel]")
        page.screenshot(path=str(d.SHOT) + "_1_empty.png", full_page=True)
        d.check("1 the empty project's Overview shows the welcome, Add an agent and the quickstart",
                panel.count() == 1
                and panel.get_by_role("button", name="Add an agent").count() == 1
                and "quickstart" in panel.inner_text().lower(),
                panel.inner_text() if panel.count() else "no panel")
        d.check("1b the non-git folder's Overview offers the repository",
                page.locator("[data-testid=setup-item-repository]").count() == 1)

        code, out = make_agent(pid, "planner", bound=True)
        d.check("2a an agent is added", code < 300, f"{code} {str(out)[:200]}")
        overview()
        ask = panel.get_by_role("button", name="Ask planner for a change")
        page.screenshot(path=str(d.SHOT) + "_2_agent.png", full_page=True)
        d.check("2b the panel offers Ask planner for a change", ask.count() == 1)
        ask.click()
        d.poll(lambda: page.get_by_text("Describe a change you want").count() > 0, 15)
        page.screenshot(path=str(d.SHOT) + "_3_starters.png", full_page=True)
        d.check("2c the new conversation suggests what fits an empty project",
                page.get_by_text("Describe a change you want").count() == 1
                and page.get_by_text("Explain this codebase to me").count() == 1
                and page.get_by_text("Pick up the next task").count() == 0
                and page.get_by_text("Catch up on today").count() == 0)

        code, out = d.api("POST", f"/projects/{pid}/tasks", {"title": "First task", "description": "x", "assignee": "planner"})
        d.check("3a a task is created", code < 300, f"{code} {str(out)[:200]}")
        overview()
        page.screenshot(path=str(d.SHOT) + "_4_work.png", full_page=True)
        d.check("3b the welcome is gone once there is a task", page.locator("[data-testid=first-run-panel]").count() == 0)
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
