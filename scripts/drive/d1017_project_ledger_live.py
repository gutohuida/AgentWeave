"""Live check for slice project-ledger: a merge on a scratch project appears in the open ledger's
lane without a reload.

The operator records evidence at a commit on a branch and lands the task; the merge into main is
the Hub's own. On the Hub `e2e.py hub-up` started (never :8000 or :8010), through a Vite dev
server pointed at it.

  AW_DEV_HUB=http://127.0.0.1:<port> npx vite --host 127.0.0.1 --port 5180     (from hub/ui)
  py -3.11 scripts/drive/d1017_project_ledger_live.py <project-id> <project-dir>
"""

import importlib.util
import pathlib
import subprocess
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


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def main(project, directory):
    root = pathlib.Path(directory)
    main_branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "master"
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = main_branch
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": "ledger live"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "ledger live",
        "summary": "A note file.", "problem": "Drive fixture for the ledger's live lane.",
        "scope": {"in_scope": ["note.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "note.txt MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the repo",
                                 "when": "listed", "then": "note.txt is there"}],
        "tasks": [{"key": "t1", "title": "Write note.txt", "description": "Add it.",
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

    git(root, "checkout", "-q", "-b", f"ledger-live-{task_id}")
    (root / "note.txt").write_text("a note\n", encoding="utf-8")
    git(root, "add", "note.txt")
    git(root, "commit", "-q", "-m", "note")
    sha = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "-q", main_branch)

    with Judge("d1017-project-ledger-live", hub="http://127.0.0.1:5180", key=e2e.key()) as j:
        page = j.page(project, mode="light", query="tab=activity")
        page.get_by_test_id("project-ledger").wait_for(timeout=30000)
        before = page.locator("[data-testid='ledger-merges'] > ul.aw-req-list > li").count()

        code, body = e2e.request("POST", f"{spec}/spec/evidence", {
            "identifier": "FR-1", "document": path, "summary": "note.txt added", "kind": "manual",
            "locator": "note.txt", "task_id": task_id, "commit": sha,
        })
        check("the evidence is recorded at the branch commit", code == 201, f"{code} {str(body)[:200]}")
        for step in ("in_progress", "completed"):
            e2e.request("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": step})
        code, landed = e2e.request("POST", f"/projects/{project}/tasks/{task_id}/land")
        check("the task lands", code == 200, f"{code} {str(landed)[:200]}")

        row = page.locator("[data-testid='ledger-merges'] > ul.aw-req-list > li").first
        try:
            page.wait_for_function(
                f"document.querySelectorAll(\"[data-testid='ledger-merges'] > ul.aw-req-list > li\").length > {before}",
                timeout=20000,
            )
            arrived = True
        except Exception:  # noqa: BLE001 - a timeout is the failure being checked
            arrived = False
        check("the merge appears in the open ledger without a reload", arrived, f"before={before}")
        if arrived:
            text = row.inner_text()
            check("it names the task and says merged", "Write note.txt" in text and "merged" in text, text[:120])
            j.shot(page, "after_merge")
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
