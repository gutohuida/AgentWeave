"""Drive for F411: the Jobs page shows the Hub's refusal when Run is declined.

Starts its own Hub from source on :8104 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. Opens a project, creates an agent with no runner bound and a plain job for it,
opens the Jobs tab in a real browser and presses Run:

  1. the press makes the Hub answer 500 (F412) -- the refusal exists to be shown;
  2. the page shows an alert carrying the Hub's sentence (before F411: nothing appeared);
  3. a screenshot of the page is kept.

No agent turn: no runner is bound, so nothing here can spawn one. Run from anywhere:
    py -3.11 scripts/drive/d1011_f411_run_refusal_ui.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8104
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1011-f411-run-refusal-ui" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f411"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, runner = d.api("POST", f"{base}/runners", {"name": "claude (drive)", "cli": "claude"})
    d.check("0 a runner is created", code in (200, 201), f"{code} {str(runner)[:300]}")
    code, out = d.api("POST", f"{base}/agents", {"name": "alpha", "runner_id": runner["id"]})
    d.check("0 the agent is created", code in (200, 201), f"{code} {str(out)[:300]}")
    code, out = d.api("PATCH", f"{base}/agents/alpha", {"runner_id": None})
    d.check("0 the agent is unbound", code == 200, f"{code} {str(out)[:300]}")
    code, job = d.api("POST", f"{base}/jobs", {
        "name": "f411", "agent": "alpha", "message": "say hi", "cron": "0 0 1 1 *",
        "purpose": "f411 drive", "enabled": True})
    d.check("0 the job is created", code in (200, 201), f"{code} {str(job)[:300]}")

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    answers = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.on("response", lambda r: answers.append((r.status, r.url))
                if "/run" in r.url else None)
        page.goto(f"{d.HUB}/?project={pid}&tab=jobs", wait_until="domcontentloaded")
        run = page.get_by_role("button", name="Run", exact=True)
        d.check("0 the Jobs tab shows a Run button", d.poll(lambda: run.count() >= 1, 20))
        before = page.get_by_role("alert").count()
        run.first.click()
        for _ in range(60):  # sync playwright delivers events only while it is called
            if answers:
                break
            page.wait_for_timeout(250)
        d.check("1 the Hub declines the press", bool(answers) and answers[0][0] >= 400,
                f"answers={answers}")
        alert = page.get_by_role("alert")
        shown = d.poll(lambda: alert.count() > before, 10)
        text = alert.first.inner_text() if shown else ""
        page.screenshot(path=str(d.SHOT) + "_run_refused.png", full_page=True)
        d.check("2 the page shows the Hub's sentence", shown and "runner" in text.lower(),
                f"alert={text!r}")
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
