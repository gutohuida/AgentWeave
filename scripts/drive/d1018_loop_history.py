"""Acceptance drive for `a-loops-history-records-its-creation-and-queue-additions` (F570), 2026-10-10.

The change's `drive` criterion (spdoc-ae4ba4e73d46 on :8010, task drive-first). Starts its own Hub on
:8104 with a fresh database (never :8000 or :8010). One Haiku agent, alice, bound to a Claude runner.
Steps, in the order the criterion's `when` gives:

  1. the operator creates a loop for alice with two initial tasks (POST /jobs); the loop's events
     read loop_created (operator, door jobs) and one loop_tasks_added (source initial_tasks, 2 tasks);
  2. the operator adds a third task with the loop's id (POST /tasks); one more loop_tasks_added
     (source create_task, operator);
  3. a real Haiku turn of alice is asked to create_task with the loop's id; one more
     loop_tasks_added whose actor is agent alice with her run id;
  4. the operator approves a change document whose delivery starts a flow for alice; the flow's loop
     reads loop_created (operator, door approval, the document's path) and one loop_tasks_added
     (source flow_built: approval materialises first, then the flow takes the unowned tasks) listing
     the document's tasks;
  5. the first loop is fired once by hand (POST /jobs/{id}/run): its job gains a run, its events
     gain nothing;
  6. in Chromium, the first loop's tab has a History section (testid loop-tab-events) with one
     sentence row (testid loop-tab-event) per event, newest first, the addition naming alice.

Event contract the build fixes (D3): `GET /loops/{id}` events carry `event_type`, `agent` (set for
agent actors only) and `data`. loop_created.data = {by, door, agent, purpose, document, document_path};
loop_tasks_added.data = {by, source, tasks: [{id, title}]}; by = {kind: "operator"|"agent", agent,
run_id}; door is "jobs" or "approval"; source is "initial_tasks", "create_task", "document" or
"flow_built" (a loop already holding the document gets "document" at approval).

Fails on today's Hub at check 1 (no loop_created). Stops at the first failure. One Haiku turn from
check 3 (and one to open the page at check 6).

    py -3.11 scripts/drive/d1018_loop_history.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8104
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1018-loop-history" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

DOC = "spec/changes/greeting/spec.json"


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Greeting",
        "summary": "A greeting file exists.", "problem": "There is no greeting.",
        "scope": {"in_scope": ["hello.txt"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": "hello", "modal": "MUST", "rationale": None, "party": None,
             "statement": "The project MUST contain hello.txt holding the word hi."},
        ],
        "acceptance_criteria": [
            {"key": "hello-ok", "requirement": "hello", "given": "the project", "when": "hello.txt is read",
             "then": "it holds hi", "how_to_check": "cat hello.txt", "checked_by": "agent"},
        ],
        "tasks": [
            {"key": "t-one", "title": "Write hello.txt", "description": "Create it.", "requirements": ["hello"],
             "depends_on": [], "files": ["hello.txt"], "from": None, "reviewer": None},
            {"key": "t-two", "title": "Check hello.txt", "description": "Read it back.",
             "requirements": ["hello"], "depends_on": ["t-one"], "files": ["hello.txt"], "from": None,
             "reviewer": None},
        ],
        "algorithms": [], "design": "One file.", "evidence": {"checked": [], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "flow", "agent": "alice", "reviewer": None, "stop_when_queue_empties": True,
                     "stop_at": None, "cron": "0 0 1 1 *"},
    }


def wait_idle(pid, secs=300):
    end = time.time() + secs
    time.sleep(3)
    while time.time() < end:
        if not d.ro("select count(*) from runs where project_id=? and status='running'", (pid,))[0][0]:
            return True
        time.sleep(4)
    return False


def events_of(base, loop_id, kind=None):
    code, out = d.api("GET", f"{base}/loops/{loop_id}")
    assert code == 200, (code, out)
    rows = out.get("events") or []
    return [e for e in rows if kind is None or e.get("event_type") == kind]


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# greeting\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "greeting"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    code, out = d.api("POST", f"{base}/agents", {"name": "alice", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    # 1: the operator creates a loop for alice with two initial tasks.
    code, job = d.api("POST", f"{base}/jobs", {
        "name": "history-one", "agent": "alice", "message": "Work the queue.", "cron": "0 0 1 1 *",
        "purpose": "history drive", "enabled": False,
        "initial_tasks": [{"title": "First seeded", "description": "One."},
                          {"title": "Second seeded", "description": "Two."}]})
    assert code in (200, 201), (code, job)
    job_id, loop_id = job["id"], (job.get("loop") or {}).get("id")
    assert loop_id, job
    created = events_of(base, loop_id, "loop_created")
    added = events_of(base, loop_id, "loop_tasks_added")
    c0 = (created[0].get("data") or {}) if created else {}
    a0 = (added[0].get("data") or {}) if added else {}
    d.check("1 the loop's events carry loop_created (operator, jobs) and one loop_tasks_added of its initial tasks",
            len(created) == 1 and (c0.get("by") or {}).get("kind") == "operator" and c0.get("door") == "jobs"
            and len(added) == 1 and a0.get("source") == "initial_tasks" and len(a0.get("tasks") or []) == 2,
            f"created={created} added={added}")

    # 2: the operator adds a task with the loop's id.
    code, out = d.api("POST", f"{base}/tasks", {"title": "Third by operator", "description": "Three.",
                                               "assignee": "alice", "loop_id": loop_id})
    assert code in (200, 201), (code, out)
    added = events_of(base, loop_id, "loop_tasks_added")
    sources = sorted((e.get("data") or {}).get("source") for e in added)
    d.check("2 an operator create with the loop's id adds one more loop_tasks_added (create_task)",
            sources == ["create_task", "initial_tasks"], f"{sources}")

    # 3: a real Haiku turn of alice creates a task with the loop's id.
    message = (f"Call the create_task tool once with title 'Fourth by alice', description 'Four.' and "
               f"loop_id '{loop_id}'. Do nothing else, then reply done.")
    code, run = d.api("POST", f"{base}/agent/trigger", {"agent": "alice", "message": message})
    assert code in (200, 202), (code, run)
    run_id = run["run_id"]
    wait_idle(pid)
    added = events_of(base, loop_id, "loop_tasks_added")
    mine = [e for e in added if ((e.get("data") or {}).get("by") or {}).get("agent") == "alice"]
    by = ((mine[0].get("data") or {}).get("by") or {}) if mine else {}
    d.check("3 alice's create_task adds a loop_tasks_added naming alice and her run",
            len(mine) == 1 and by.get("kind") == "agent" and by.get("run_id") == run_id
            and any(t.get("title") == "Fourth by alice" for t in (mine[0]["data"].get("tasks") or [])),
            f"run={run_id} added={added}")

    # 4: the operator approves a change document whose delivery starts a flow.
    code, out = d.api("POST", f"{base}/project/documents", {"title": "Greeting", "kind": "change-spec",
                                                           "path": DOC})
    assert code == 201, (code, out)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    assert code == 200, (code, out)
    import urllib.parse
    quoted = urllib.parse.quote(DOC)
    d.api("POST", f"{base}/project/documents/journey?path={quoted}",
          {"size": "small", "step": "delivery", "reason": "drive setup"})
    d.api("POST", f"{base}/project/documents/close-exploration?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/propose?path={quoted}")
    assert code == 200 and out.get("proposed"), (code, out)
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True})
    assert code == 200, (code, out)
    _, loops = d.api("GET", f"{base}/loops")
    flow = next((x for x in loops if x.get("spec_document_id") and x["id"] != loop_id), None)
    flow_id = (flow or {}).get("id")
    created = events_of(base, flow_id, "loop_created") if flow_id else []
    added = events_of(base, flow_id, "loop_tasks_added") if flow_id else []
    c1 = (created[0].get("data") or {}) if created else {}
    a1 = (added[0].get("data") or {}) if added else {}
    d.check("4 the flow's loop has loop_created (operator, approval, the document) and one loop_tasks_added (flow_built)",
            len(created) == 1 and (c1.get("by") or {}).get("kind") == "operator" and c1.get("door") == "approval"
            and c1.get("document_path") == DOC and len(added) == 1 and a1.get("source") == "flow_built"
            and len(a1.get("tasks") or []) == 2, f"flow={flow_id} created={created} added={added}")

    # 5: a firing by hand adds a run and no loop event.
    before = len(events_of(base, loop_id))
    runs_before = len(d.api("GET", f"{base}/jobs/{job_id}/history")[1] or [])
    # Created disabled so it cannot fire on its own (its cron is yearly as well); enabled only to
    # allow the one hand firing, and disabled again straight after.
    code, out = d.api("PATCH", f"{base}/jobs/{job_id}", {"enabled": True})
    assert code == 200, (code, out)
    code, out = d.api("POST", f"{base}/jobs/{job_id}/run")
    assert code in (200, 202), (code, out)
    wait_idle(pid)
    time.sleep(2)
    d.api("PATCH", f"{base}/jobs/{job_id}", {"enabled": False})
    runs_after = len(d.api("GET", f"{base}/jobs/{job_id}/history")[1] or [])
    after = len(events_of(base, loop_id))
    d.check("5 a firing adds a run to the job's history and nothing to the loop's events",
            runs_after == runs_before + 1 and after == before, f"runs {runs_before}->{runs_after} events {before}->{after}")

    # 6: the tab shows the history as sentences.
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(seed)
        page.goto(d.HUB, wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_text("alice", exact=True).count() > 0, 20)
        page.get_by_text("alice", exact=True).first.click()
        page.get_by_placeholder("Message alice…").fill("Reply with the single word ok.")
        page.keyboard.press("Enter")
        wait_idle(pid)
        page.get_by_role("button", name="Show panel").click()
        page.get_by_text("Loops", exact=True).first.click()
        row = page.locator(f"[data-testid=loops-index-row-{loop_id}]")
        d.poll(lambda: row.count() == 1, 15)
        row.click()
        d.poll(lambda: page.locator("[data-testid=loop-tab-events]").count() == 1, 15)
        rows = page.locator("[data-testid=loop-tab-event]")
        texts = [rows.nth(i).inner_text() for i in range(rows.count())]
        page.screenshot(path=str(d.SHOT) + "_tab.png", full_page=True)
        browser.close()
    d.check("6 the tab's History section lists each event as a sentence, the addition naming alice",
            len(texts) == 4 and "alice" in " ".join(texts).lower() and "Fourth by alice" in " ".join(texts),
            f"{texts}")


d.drive = drive

if __name__ == "__main__":
    d.main()
