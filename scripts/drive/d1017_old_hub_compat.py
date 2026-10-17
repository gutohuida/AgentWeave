"""The committed bundle against a Hub that predates this session's routes (the operator's :8000
until it restarts): the Activity tab, the Spec tab's evidence view and a conversation still open
cleanly. Runs a Hub built from an older commit on a scratch profile, through Vite.

    git worktree add --detach testbed/oldhub-9ceed90 9ceed90
    AW_REPO_ROOT=<that worktree> py -3.11 .claude/skills/e2e-loop/e2e.py hub-up d1017oldhub 8128
    AW_DEV_HUB=http://127.0.0.1:8128 npx vite --host 127.0.0.1 --port 5181     (from hub/ui)
    py -3.11 scripts/drive/d1017_old_hub_compat.py <project-id>
"""

import importlib.util
import pathlib
import sys

from uiharness import Judge

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project):
    with Judge("d1017-old-hub-compat", hub="http://127.0.0.1:5181", key=e2e.key()) as j:
        page = j.page(project, mode="light", query="tab=activity")
        page.get_by_test_id("ledger-unavailable").wait_for(timeout=30000)
        check("the Activity tab falls back to the live log on a Hub without the ledger",
              page.get_by_test_id("ledger-unavailable").count() == 1
              and page.get_by_test_id("ledger-error").count() == 0)
        j.shot(page, "activity_old_hub")
        page.goto(page.url.replace("tab=activity", "tab=spec&view=evidence"))
        page.get_by_test_id("evidence-browser").wait_for(timeout=30000)
        check("the evidence view opens", page.get_by_test_id("evidence-browser").count() == 1)
        task = e2e.call("POST", f"/projects/{project}/tasks", {"title": "Old hub task"})
        page.goto(page.url.split("?")[0] + f"?project={project}&tab=tasks")
        page.get_by_test_id(f"task-open-{task['id']}").first.wait_for(timeout=30000)
        page.get_by_test_id(f"task-open-{task['id']}").first.click()
        page.get_by_test_id(f"task-drawer-{task['id']}").wait_for(timeout=15000)
        page.wait_for_timeout(1500)
        check("the drawer opens on Details, with no Story switch, on a Hub without /story",
              page.get_by_test_id(f"task-view-story-{task['id']}").count() == 0
              and page.get_by_test_id(f"task-story-{task['id']}").count() == 0)
        j.shot(page, "drawer_old_hub")
        page.context.close()
        # 404s from routes this Hub lacks are expected answers; anything else is a failure.
        unexpected = [e for e in j.errors if "404" not in e]
        check("no console or page errors beyond the expected 404s", not unexpected, "; ".join(unexpected[:3]))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        print(f"[FAIL] drive raised {exc!r}"[:300])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
