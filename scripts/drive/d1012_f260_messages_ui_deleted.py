"""Drive for F260: the dead Messages UI subtree is deleted, and the app built without it still
loads and reaches a conversation surface.

Starts its own Hub from source on :8110 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. One project with a runner-less agent. A real browser opens the project's
Overview, then the agent's conversation surface. It records every page error and every failed
asset request, and checks the bundle the Hub serves carries no trace of the deleted hooks, and
that the source tree no longer holds them.

No agent turn: no runner is bound, so nothing here can spawn one. Run from anywhere:
    py -3.11 scripts/drive/d1012_f260_messages_ui_deleted.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8110
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f260-messages-ui" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

UI_SRC = d.REPO / "hub" / "ui" / "src"
BUNDLE = d.REPO / "hub" / "hub" / "static" / "ui"


def drive():
    d.check("0 components/messages/ is gone from the source",
            not (UI_SRC / "components" / "messages").exists())
    d.check("0 api/messages.ts is gone from the source", not (UI_SRC / "api" / "messages.ts").exists())
    bundle_js = "".join(p.read_text(encoding="utf-8", errors="replace")
                        for p in (BUNDLE / "assets").glob("*.js"))
    d.check("1 the committed bundle names none of the deleted hooks",
            not any(w in bundle_js for w in ("useMessageHistory", "useMarkRead", "MessagesFeed")))

    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f260"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    code, runner = d.api("POST", f"{base}/runners", {"name": "claude r", "cli": "claude"})
    assert code in (200, 201), (code, runner)
    code, out = d.api("POST", f"{base}/agents", {"name": "agent-a", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, project["id"]))
    errors, failed = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: failed.append(f"{r.status} {r.url}")
                if r.status >= 400 and "/assets/" in r.url else None)
        page.goto(f"{d.HUB}/?project={project['id']}", wait_until="domcontentloaded")
        d.check("2 the Overview loads",
                d.poll(lambda: page.get_by_role("heading", name="Attention").count() >= 1, 30))
        page.wait_for_timeout(1000)
        rail = page.get_by_test_id(f"rail-agent-{project['id']}-agent-a")
        d.check("3 the agent is in the rail", d.poll(lambda: rail.count() >= 1, 20))
        rail.first.click()
        d.check("4 the agent's conversation surface renders",
                d.poll(lambda: page.get_by_test_id("conversation-header").count() >= 1, 20))
        page.screenshot(path=str(d.SHOT) + "_conversation.png", full_page=True)
        d.check("5 no page error", not errors, str(errors[:3]))
        d.check("6 no asset request failed", not failed, str(failed[:3]))
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
