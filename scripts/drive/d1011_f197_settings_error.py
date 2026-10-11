"""Drive for F197: a failed project-settings query shows a named failure with a Retry, not a
skeleton that never ends.

Starts its own Hub from source on :8106 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. One project. A real browser opens Environment > Settings with the settings
route answering 500 (intercepted in the browser, so the bundle is the real one): the page must say
the settings could not be loaded, quote the Hub's reason, hide the form, and show no skeleton. The
route is then restored and Retry pressed: the form must appear with the project's stored name.

No agent turn: no agent exists. Run from anywhere:
    py -3.11 scripts/drive/d1011_f197_settings_error.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8106
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1011-f197-settings-error" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

REASON = "settings table unreadable (drive)"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("tiny\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f197-proj"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    code, stored = d.api("GET", f"/projects/{pid}/settings")
    d.check("0 the real settings route answers 200", code == 200, f"{code} {stored}")

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    failing = {"on": True}
    hits = {"n": 0}

    def settings_route(route):
        if failing["on"]:
            hits["n"] += 1
            route.fulfill(status=500, content_type="application/json",
                          body='{"detail": "%s"}' % REASON)
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.route(f"**/api/v1/projects/{pid}/settings", settings_route)
        page.goto(f"{d.HUB}/?project={pid}&tab=environment&section=settings",
                  wait_until="domcontentloaded")
        alert = page.get_by_role("alert").filter(has_text="settings could not be loaded")
        d.check("1 the failure is named in an alert", d.poll(lambda: alert.count() >= 1, 40),
                f"hits={hits['n']}")
        page.wait_for_timeout(1000)
        text = alert.first.inner_text()
        d.check("2 the Hub's reason is quoted", REASON in text, text)
        d.check("3 no skeleton is left standing",
                page.get_by_label("Loading project settings").count() == 0)
        d.check("4 the form is hidden", page.get_by_label("Project name").count() == 0
                and page.get_by_role("button", name="Save settings").count() == 0)
        page.screenshot(path=str(d.SHOT) + "_error.png", full_page=True)

        failing["on"] = False
        page.get_by_role("button", name="Retry").click()
        name = page.get_by_label("Project name")
        d.check("5 Retry loads the form", d.poll(lambda: name.count() == 1, 20))
        d.check("6 the form holds the stored name", name.input_value() == stored["name"],
                f"{name.input_value()!r} vs {stored['name']!r}")
        d.check("7 the alert is gone", alert.count() == 0)
        page.screenshot(path=str(d.SHOT) + "_recovered.png", full_page=True)
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
