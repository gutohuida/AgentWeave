"""Acceptance drive for `a-tasks-prerequisites-can-be-declared-at-creation-and-in-its-drawer` (F571), 2026-10-10.

The change's `drive` criterion (spdoc-e28ec0fff9f3 on :8010, task drive-first). Starts its own Hub on
:8105 with a fresh database (never :8000 or :8010). One Haiku agent, alice, bound to a Claude runner.
Steps, in the order the criterion's `when` gives:

  1. the operator creates task D with depends_on [A] (POST /tasks); GET /tasks/{D} lists A in
     prerequisites and GET /tasks/{A} lists D in dependents;
  2. a creation naming an unknown id, and one naming its own id, are each refused 422 with the
     offending id in the detail, and neither leaves a task behind;
  3. a real Haiku turn of alice is asked to create_task C with depends_on naming A's id; C's
     prerequisites list A (C's creator is alice's run);
  4. in Chromium the operator opens B's drawer: the Depends on section says B depends on nothing,
     the picker adds A, the section then lists A with its status, and GET /tasks/{B} agrees;
  5. the drawer's remove button takes A off again: the section says B depends on nothing and
     GET /tasks/{B} has no prerequisites;
  6. A's drawer: picking C (which already depends on A) is refused, the drawer shows the Hub's
     refusal sentence (testid task-dependency-refusal-<id>) and A's prerequisites stay empty.

Drawer contract the build fixes (D4, D5): inside the drawer body, a section
`task-dependencies-<task>` holding one `task-dependency-<task>-<prereq>` row per prerequisite (title
and status), a `task-dependency-remove-<task>-<prereq>` button per row, a
`task-dependencies-empty-<task>` line "depends on nothing" when there are none, a native select
`task-dependency-picker-<task>` (options labelled "title (id)", every other task not already a
prerequisite, cycle-forming ones included), an `task-dependency-add-<task>` button, and
`task-dependency-refusal-<task>` showing the route's detail sentence after a refused add.

Fails on today's Hub at check 1 (POST /tasks refuses depends_on as an extra field). Stops at the
first failure. One Haiku turn at check 3.

    py -3.11 scripts/drive/d1019_task_depends_on.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8105
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1019-task-depends-on" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def wait_idle(pid, secs=300):
    end = time.time() + secs
    time.sleep(3)
    while time.time() < end:
        if not d.ro("select count(*) from runs where project_id=? and status='running'", (pid,))[0][0]:
            return True
        time.sleep(4)
    return False


def prereq_ids(base, task_id):
    code, out = d.api("GET", f"{base}/tasks/{task_id}")
    assert code == 200, (code, out)
    return sorted(p["id"] for p in out.get("prerequisites") or [])


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# depends\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "depends"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    code, out = d.api("POST", f"{base}/agents", {"name": "alice", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    def make(title):
        code, out = d.api("POST", f"{base}/tasks", {"title": title, "description": title, "assignee": "alice"})
        assert code in (200, 201), (code, out)
        return out["id"]

    task_a, task_b = make("Task A first"), make("Task B second")

    # 1: the operator creates D with depends_on [A].
    code, out = d.api("POST", f"{base}/tasks", {"title": "Task D after A", "description": "D.",
                                               "assignee": "alice", "depends_on": [task_a]})
    task_d = out.get("id") if code in (200, 201) else None
    dependents = []
    if task_d:
        dependents = [x["id"] for x in d.api("GET", f"{base}/tasks/{task_a}")[1].get("dependents") or []]
    d.check("1 POST /tasks with depends_on [A] makes D depend on A, and A lists D among its dependents",
            task_d is not None and prereq_ids(base, task_d) == [task_a] and task_d in dependents,
            f"code={code} out={out}")

    # 2: unknown and own ids refuse the whole creation.
    _, before = d.api("GET", f"{base}/tasks")
    count_before = len(before if isinstance(before, list) else before.get("items", before))
    code1, out1 = d.api("POST", f"{base}/tasks", {"title": "Unknown prerequisite", "description": "x",
                                                  "assignee": "alice", "depends_on": [task_a, "task-nope"]})
    code2, out2 = d.api("POST", f"{base}/tasks", {"title": "Own prerequisite", "description": "x",
                                                  "assignee": "alice", "id": "task-self-ref",
                                                  "depends_on": ["task-self-ref"]})
    _, after = d.api("GET", f"{base}/tasks")
    count_after = len(after if isinstance(after, list) else after.get("items", after))
    d.check("2 an unknown id and the task's own id each refuse 422 naming the id, and leave no task",
            code1 == 422 and "task-nope" in str(out1) and code2 == 422 and "task-self-ref" in str(out2)
            and count_after == count_before, f"{code1} {out1} / {code2} {out2} / {count_before}->{count_after}")

    # 3: a real Haiku turn of alice creates C with depends_on naming A.
    message = (f"Call the create_task tool once with title 'Task C by alice', description 'C.' and "
               f"depends_on ['{task_a}']. Do nothing else, then reply done.")
    code, run = d.api("POST", f"{base}/agent/trigger", {"agent": "alice", "message": message})
    assert code in (200, 202), (code, run)
    wait_idle(pid)
    _, tasks = d.api("GET", f"{base}/tasks")
    rows = tasks if isinstance(tasks, list) else tasks.get("items", [])
    task_c = next((t["id"] for t in rows if t.get("title") == "Task C by alice"), None)
    d.check("3 alice's create_task with depends_on makes C depend on A",
            task_c is not None and prereq_ids(base, task_c) == [task_a], f"run={run} c={task_c}")

    # 4-6: the drawer.
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))

    def section(page, task_id):
        return page.locator(f"[data-testid=task-dependencies-{task_id}]")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed)
        page.goto(f"{d.HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        d.poll(lambda: page.locator(f"[data-testid=task-open-{task_b}]").count() == 1, 20)
        page.locator(f"[data-testid=task-open-{task_b}]").click()
        d.poll(lambda: section(page, task_b).count() == 1, 10)
        empty_text = page.locator(f"[data-testid=task-dependencies-empty-{task_b}]")
        was_empty = empty_text.count() == 1 and "depends on nothing" in empty_text.inner_text().lower()
        page.locator(f"[data-testid=task-dependency-picker-{task_b}]").select_option(value=task_a)
        page.locator(f"[data-testid=task-dependency-add-{task_b}]").click()
        row = page.locator(f"[data-testid=task-dependency-{task_b}-{task_a}]")
        d.poll(lambda: row.count() == 1, 10)
        row_text = row.inner_text() if row.count() else ""
        page.screenshot(path=str(d.SHOT) + "_added.png", full_page=True)
        d.check("4 B's drawer says it depends on nothing, then lists A with its status after the add; GET agrees",
                was_empty and "Task A first" in row_text and prereq_ids(base, task_b) == [task_a],
                f"empty={was_empty} row={row_text!r} api={prereq_ids(base, task_b)}")

        page.locator(f"[data-testid=task-dependency-remove-{task_b}-{task_a}]").click()
        d.poll(lambda: page.locator(f"[data-testid=task-dependencies-empty-{task_b}]").count() == 1, 10)
        d.check("5 the remove button takes A off: the drawer says it depends on nothing and GET agrees",
                page.locator(f"[data-testid=task-dependencies-empty-{task_b}]").count() == 1
                and prereq_ids(base, task_b) == [], f"api={prereq_ids(base, task_b)}")

        page.locator(f"[data-testid=task-drawer-close-{task_b}]").click()
        page.locator(f"[data-testid=task-open-{task_a}]").click()
        d.poll(lambda: section(page, task_a).count() == 1, 10)
        page.locator(f"[data-testid=task-dependency-picker-{task_a}]").select_option(value=task_c)
        page.locator(f"[data-testid=task-dependency-add-{task_a}]").click()
        refusal = page.locator(f"[data-testid=task-dependency-refusal-{task_a}]")
        d.poll(lambda: refusal.count() == 1, 10)
        refusal_text = refusal.inner_text() if refusal.count() else ""
        page.screenshot(path=str(d.SHOT) + "_refused.png", full_page=True)
        browser.close()
    d.check("6 A's drawer shows the cycle refusal sentence when C is picked, and A gains no prerequisite",
            "directly or through others" in refusal_text and prereq_ids(base, task_a) == [],
            f"refusal={refusal_text!r} api={prereq_ids(base, task_a)}")


d.drive = drive

if __name__ == "__main__":
    d.main()
