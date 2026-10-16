"""Drive for fix-D14 (F659) and fix-D15 (F652), in a real browser.

Starts its own Hub from source on :8112 with a fresh database (never :8000 or :8010), serving the
committed UI bundle. One project, one runner-less agent (nothing can spawn a turn), and:
  D15  in an existing conversation, pressing Explore creates no document; sending creates it and
       attaches it; a refused send (over 10,000 characters) leaves no document behind;
  D14  an approved task whose run proceeded without an answer shows one history line on its card,
       not the amber "Decided without you" block; a task still in progress keeps the block.
The timed-out question is written straight into this drive's own scratch database: a real one
needs an agent to wait out a deadline. Records every page error.

    py -3.11 scripts/drive/d1016_d14_d15_screens.py
"""

import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8112
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1016-d14-d15" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def documents(pid):
    rows = d.ro("select path from spec_documents where project_id=?", (pid,))
    return sorted(r[0] for r in rows)


def seed_proceeded(pid, task_id, qid):
    """A blocking question on `task_id` whose wait ended unanswered (scratch DB only)."""
    con = sqlite3.connect(str(d.DB))
    con.execute(
        "insert into questions (id, project_id, from_agent, question, answered, blocking, options,"
        " multi_select, answer_labels, batch_index, batch_size, created_at, declined,"
        " blocked_task_id, wait_ended_at) values (?,?,?,?,0,1,'[]',0,'[]',0,1,"
        " datetime('now','-1 hour'),0,?,datetime('now','-30 minutes'))",
        (qid, pid, "agent-a", "Which colour should the banner be?", task_id),
    )
    con.commit()
    con.close()


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "d14d15"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, runner = d.api("POST", f"{base}/runners", {"name": "claude r", "cli": "claude"})
    assert code in (200, 201), (code, runner)
    code, out = d.api("POST", f"{base}/agents", {"name": "agent-a", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    d.api("PATCH", f"{base}/agents/agent-a", {"runner_id": None})
    code, sent = d.api("POST", f"{base}/agent/trigger", {"agent": "agent-a", "message": "Hello there"})
    d.check("0 a conversation exists", code == 200 and sent.get("conversation_id"), f"{code} {sent}")

    code, done = d.api("POST", f"{base}/tasks", {"title": "Paint the banner"})
    assert code in (200, 201), (code, done)
    for status in ("in_progress", "completed", "under_review", "approved"):
        code, out = d.api("PATCH", f"{base}/tasks/{done['id']}", {"status": status})
    d.check("0b the task is approved", out.get("status") == "approved", f"{code} {str(out)[:200]}")
    code, live = d.api("POST", f"{base}/tasks", {"title": "Pick the font"})
    d.api("PATCH", f"{base}/tasks/{live['id']}", {"status": "in_progress"})
    seed_proceeded(pid, done["id"], "q-d14-approved")
    seed_proceeded(pid, live["id"], "q-d14-live")

    # In a try: the init script also runs in the spec preview's sandboxed iframe, where storage
    # throws -- the drive's error, not the app's.
    seed = (
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        "localStorage.setItem('agentweave-selected-project', %r); } catch (e) {}" % (d.KEY, d.HUB, pid)
    )
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_test_id(f"rail-agent-{pid}-agent-a").count() >= 1, 30)
        page.get_by_test_id(f"rail-agent-{pid}-agent-a").first.click()
        explore = page.get_by_test_id("composer-start-exploration")
        d.check("1 the conversation offers Explore", d.poll(lambda: explore.count() == 1, 20))

        before = documents(pid)
        explore.click()
        d.check("2 D15: Explore arms", d.poll(lambda: explore.get_attribute("aria-pressed") == "true", 5))
        time.sleep(2)
        d.check("3 D15: the press creates no document", documents(pid) == before, str(documents(pid)))

        box = page.get_by_role("textbox").last
        box.fill("x" * 10050)
        box.press("Enter")
        time.sleep(3)
        d.check("4 D15: a refused send leaves no document", documents(pid) == before, str(documents(pid)))
        d.check("5 D15: still armed after the refusal", explore.get_attribute("aria-pressed") == "true")

        box.fill("Let us explore a cache for this service.")
        box.press("Enter")
        d.check("6 D15: the send creates one document",
                d.poll(lambda: len(documents(pid)) == len(before) + 1, 15), str(documents(pid)))
        d.check("7 D15: the composer names it as attached",
                d.poll(lambda: page.get_by_test_id("composer-spec-control").count() == 1, 15))
        page.screenshot(path=str(d.SHOT) + "_explore.png", full_page=True)

        page.goto(f"{d.HUB}/?project={pid}", wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_test_id("project-tab-tasks").count() >= 1, 20)
        page.get_by_test_id("project-tab-tasks").first.click()
        history = page.get_by_test_id(f"task-proceeded-history-{done['id']}")
        d.check("8 D14: the approved task shows one history line", d.poll(lambda: history.count() >= 1, 20))
        d.check("9 D14: and no amber block",
                page.get_by_test_id(f"task-proceeded-{done['id']}").count() == 0)
        d.check("10 D14: the task in progress keeps its block",
                d.poll(lambda: page.get_by_test_id(f"task-proceeded-{live['id']}").count() >= 1, 10))
        page.screenshot(path=str(d.SHOT) + "_tasks.png", full_page=True)
        d.check("11 no page error", not errors, str(errors[:3]))
        browser.close()


d.drive = drive

if __name__ == "__main__":
    d.main()
