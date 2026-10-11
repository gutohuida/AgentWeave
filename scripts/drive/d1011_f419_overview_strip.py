"""Drive for F419: the Overview activity strip shows only the selected project's events, and a
'warn' event paints its dot amber.

Starts its own Hub from source on :8105 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. Two projects, each with a runner-less agent and a plain job. A real browser
opens project A's Overview, then Run is pressed through the API for B's job and A's job (each is
declined with a warn-severity event). The strip on A's Overview must name A's agent and never B's,
and the dot of A's warn event must be amber.

No agent turn: no runner is bound, so nothing here can spawn one. Run from anywhere:
    py -3.11 scripts/drive/d1011_f419_overview_strip.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8105
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1011-f419-overview-strip" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def make_project(tag):
    root = d.TMP / f"proj-{tag}"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"f419-{tag}"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    code, runner = d.api("POST", f"{base}/runners", {"name": f"claude {tag}", "cli": "claude"})
    assert code in (200, 201), (code, runner)
    agent = f"agent-{tag}"
    code, out = d.api("POST", f"{base}/agents", {"name": agent, "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    code, out = d.api("PATCH", f"{base}/agents/{agent}", {"runner_id": None})
    assert code == 200, (code, out)
    code, job = d.api("POST", f"{base}/jobs", {
        "name": f"f419-{tag}", "agent": agent, "message": "say hi", "cron": "0 0 1 1 *",
        "purpose": "f419 drive", "enabled": True})
    assert code in (200, 201), (code, job)
    return project["id"], base, job["id"], agent


def drive():
    pid_a, base_a, job_a, agent_a = make_project("a")
    pid_b, base_b, job_b, agent_b = make_project("b")

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid_a))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{d.HUB}/?project={pid_a}", wait_until="domcontentloaded")
        d.check("0 project A's Overview is open",
                d.poll(lambda: page.get_by_role("heading", name="Attention").count() >= 1, 30))
        page.wait_for_timeout(1500)  # let the SSE stream connect before events are made

        code, out = d.api("POST", f"{base_b}/jobs/{job_b}/run")
        d.check("1 B's Run is declined", code >= 400, f"{code} {str(out)[:200]}")
        code, out = d.api("POST", f"{base_a}/jobs/{job_a}/run")
        d.check("2 A's Run is declined", code >= 400, f"{code} {str(out)[:200]}")

        # The Run refusals above are info events; a warn-severity one is posted through the logs
        # route (the same path the Hub's own warn events broadcast on), once per project.
        for base, agent in ((base_b, agent_b), (base_a, agent_a)):
            code, out = d.api("POST", f"{base}/logs", {
                "event_type": "drive_warning", "agent": agent, "severity": "warn", "data": {}})
            d.check(f"3 warn event posted for {agent}", code == 201, f"{code} {str(out)[:200]}")
        types = d.ro("select project_id, event_type, severity from event_logs order by id")
        d.check("4 the Hub logged events for both projects",
                {t[0] for t in types} >= {pid_a, pid_b}, f"{types}")
        d.check("4 A has a warn-severity event",
                any(t[0] == pid_a and t[2] == "warn" for t in types), f"{types}")

        # The strip re-reads the buffer when the page's queries move (OverviewPage.tsx), so move one:
        # a task in A makes the tasks query refetch, as any real board change would.
        code, out = d.api("POST", f"{base_a}/tasks", {"title": "refresh the strip"})
        d.check("4 a task is created in A", code == 201, f"{code} {str(out)[:200]}")

        pills = page.locator(".overview-activity-pill")
        d.check("5 A's Overview shows an Activity strip", d.poll(lambda: pills.count() >= 1, 20))
        page.wait_for_timeout(1000)
        text = " | ".join(pills.all_inner_texts())
        page.screenshot(path=str(d.SHOT) + "_strip.png", full_page=True)
        d.check("6 the strip names A's agent", agent_a in text, f"strip={text!r}")
        d.check("7 the strip never names B's agent", agent_b not in text, f"strip={text!r}")
        amber = page.locator(".overview-activity-pill > span:first-child").evaluate_all(
            "els => els.map(e => e.style.background)")
        d.check("8 the warn event's dot is amber", "var(--amber)" in amber, f"dots={amber}")
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
