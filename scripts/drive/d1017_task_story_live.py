"""Acceptance for slice task-story: a live run adds events to an open story without a reload.

Drives the scratch Hub `e2e.py hub-up` started (never :8000 or :8010) through a Vite dev server
proxied to it (`AW_DEV_HUB=<hub> npx vite --port 5180`). Opens a task's drawer, sends a Haiku turn
on that task, and waits for the run and its evidence to appear in the open story.

  py -3.11 scripts/drive/d1017_task_story_live.py <project-id> [agent]
"""

import importlib.util
import pathlib
import sys
import time

from uiharness import Judge

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

DEV = "http://127.0.0.1:5180"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, agent="builder"):
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": "live story"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "live story",
        "summary": "A note file.", "problem": "Drive fixture for the live story.",
        "scope": {"in_scope": ["NOTE.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "NOTE.md MUST say ready.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "NOTE.md",
                                 "when": "read", "then": "it says ready"}],
        "tasks": [{"key": "t1", "title": "Write NOTE.md", "description": "Say ready.",
                   "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    e2e.call("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    e2e.request("POST", f"{spec}/documents/close-exploration?path={path}")
    e2e.request("POST", f"{spec}/documents/propose?path={path}")
    _, approved = e2e.request("POST", f"{spec}/documents/phase?path={path}&to=approved",
                              {"reason": "drive", "approve_anyway": True})
    [task_id] = approved["tasks_created"]
    e2e.call("PATCH", f"/projects/{project}/tasks/{task_id}", {"assignee": agent})

    with Judge("d1017-task-story-live", hub=DEV, key=e2e.key()) as j:
        page = j.page(project, mode="dark")
        page.get_by_test_id("project-tab-tasks").first.wait_for(timeout=30000)
        page.get_by_test_id("project-tab-tasks").first.click()
        page.get_by_test_id(f"task-open-{task_id}").first.wait_for(timeout=20000)
        page.get_by_test_id(f"task-open-{task_id}").first.click()
        story = page.get_by_test_id(f"task-story-events-{task_id}")
        story.wait_for(timeout=15000)
        before = story.locator(":scope > li").count()
        check("the open story starts small", before <= 2, f"{before} events")

        run = e2e.cmd_turn(
            project, agent,
            f"Work task {task_id}: write NOTE.md containing the word ready and commit it with git "
            f"(message: ready). Call record_evidence once with identifier FR-1, task_id {task_id}, "
            f"kind manual_observation, summary 'NOTE.md says ready', command 'type NOTE.md', "
            f"output 'ready', covers 'full'. Then move task {task_id} to completed. Reply DONE.",
            task=task_id, fresh=True,
        )
        check("the turn started", run is not None)
        deadline = time.time() + 480
        seen_run = seen_evidence = False
        fresh = 0
        while time.time() < deadline and not (seen_run and seen_evidence):
            seen_run = page.locator("[data-testid^='story-event-run-']").count() > 0
            seen_evidence = page.locator("[data-testid^='story-event-ev-']").count() > 0
            fresh = max(fresh, page.locator("li[data-fresh='true']").count())
            page.wait_for_timeout(500)
        check("the run appeared in the open story, without a reload", seen_run)
        check("its evidence appeared in the open story, without a reload", seen_evidence)
        check("arrivals are marked fresh (they glow once)", fresh > 0, f"{fresh} fresh")
        e2e.wait_for(run, 6)
        page.wait_for_timeout(4000)
        j.shot(page, "live_after_dark", locator=page.get_by_test_id(f"task-drawer-{task_id}"))
        check("no console or page errors", not j.errors, "; ".join(j.errors[:3]))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
