"""Live drive for `2026-08-27-work-is-isolated-per-task`, task 8.8.

Two tasks for one agent, work committed in each task's own checkout, approve the first, and
confirm by `git log` that the second task's commits are **not** on the main branch. That is F58,
driven rather than asserted.

**Blast radius.** Creates its own throwaway project directory and registers it. It refuses to run
against `proj-5e960453` (this repository) or `proj-18e5d4e0` (ledger-stress), which is the
condition the operator attached to letting this change be implemented unattended.

Usage:  py -3.11 scripts/drive/t_task_isolation.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aw import api  # noqa: E402

FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
ROOT = Path(os.environ.get("AW_DRIVE_ROOT", r"C:\Users\huida\Documents\drive-f58-2026-08-27"))


def git(cwd, *args, check=True):
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result.stdout.strip()


def step(label):
    print(f"\n=== {label}")


def make_repo():
    ROOT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / ".git").exists():
        git(ROOT, "init", "-q", "-b", "main")
        git(ROOT, "config", "user.email", "drive@example.com")
        git(ROOT, "config", "user.name", "Drive")
        (ROOT / "README.md").write_text("base\n", encoding="utf-8")
        git(ROOT, "add", "-A")
        git(ROOT, "commit", "-q", "-m", "base")
    return git(ROOT, "rev-parse", "HEAD")


def main():
    step("make the throwaway repository")
    print(f"base commit {make_repo()[:12]} at {ROOT}")

    step("register the throwaway project")
    # `POST /projects/open` registers an existing directory; the repo is created just above.
    code, body = api("POST", "/projects/open", {"path": str(ROOT), "name": ROOT.name})
    if code not in (200, 201):
        raise SystemExit(f"could not register the project: {code} {body}")
    project = body
    pid = project["id"]
    print(f"project {pid} at {project.get('working_directory')}")
    if pid in FORBIDDEN:
        raise SystemExit(f"REFUSING: {pid} is a protected project")

    step("set the main branch")
    code, body = api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    print(code, json.dumps(body, default=str)[:200] if not isinstance(body, str) else body[:200])

    step("a document with one requirement, written as the operator")
    doc_path = "spec/changes/f58-drive/spec.html"
    code, body = api("POST", f"/projects/{pid}/project/documents",
                     {"path": doc_path, "title": "F58 drive"})
    print("  create:", code)
    code, body = api("PUT", f"/projects/{pid}/project/documents/{doc_path}/content", {
        "document": {
            "schema_version": 1,
            "kind": "change-spec",
            "title": "F58 drive",
            "requirements": [
                {"key": "alpha", "statement": "Work is isolated per task", "modal": "MUST"}
            ],
        }
    })
    print("  content:", code, json.dumps(body, default=str)[:200] if not isinstance(body, str) else body[:200])

    step("create two tasks, the first linked to the requirement")
    ids = []
    for title, reqs in (("F58 drive: first task", ["FR-1"]), ("F58 drive: second task", None)):
        payload = {"title": title}
        if reqs:
            payload["requirement_ids"] = reqs
        code, body = api("POST", f"/projects/{pid}/tasks", payload)
        if code != 201:
            raise SystemExit(f"task create failed: {code} {body}")
        ids.append(body["id"])
        print(f"  {body['id']}  {title}  requirements={reqs}")
    first, second = ids

    step("provision each task's checkout and commit work in it")
    # Provisioned through the Hub's own function, in the Hub's own repository, exactly as a
    # task-bound turn would — without spending a model turn on a one-line file.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))
    from hub import worktrees  # noqa: E402

    base = git(ROOT, "rev-parse", "main")
    shas = {}
    for task_id, filename in ((first, "first.py"), (second, "second.py")):
        checkout = worktrees.ensure_task_worktree(ROOT, task_id, base, ())
        (checkout / filename).write_text(f"# work for {task_id}\n", encoding="utf-8")
        git(checkout, "add", filename)
        git(checkout, "-c", "user.email=d@e.com", "-c", "user.name=D", "commit", "-q", "-m",
            f"work for {task_id}")
        shas[task_id] = git(checkout, "rev-parse", "HEAD")
        print(f"  {task_id} -> {checkout}")
        print(f"     branch {git(checkout, 'rev-parse', '--abbrev-ref', 'HEAD')}  sha {shas[task_id][:12]}")

    step("the two checkouts are siblings of main, not of each other")
    for task_id in (first, second):
        branch = worktrees.task_branch_name(task_id)
        contains = git(ROOT, "branch", "--contains", shas[task_id], check=False)
        print(f"  {branch} tip {shas[task_id][:12]} is on: {contains.split()}")

    step("operator records evidence naming the first task's commit (F71's locator)")
    code, body = api("POST", f"/projects/{pid}/project/spec/evidence", {
        "identifier": "FR-1",
        "summary": "the first task's work is in this commit",
        "locator": shas[first],
        "task_id": first,
    })
    print("  record:", code)
    if code == 201:
        fp = body.get("footprint") or {}
        print(f"     footprint commit {str(fp.get('commit_sha'))[:12]}  branch {fp.get('branch')}"
              f"  reachable_from_main={fp.get('reachable_from_main')}")
        print(f"     names the task's own commit: {fp.get('commit_sha') == shas[first]}")
    else:
        print("     ", json.dumps(body, default=str)[:500])

    step("approve the FIRST task")
    for status in ("assigned", "in_progress", "completed", "under_review", "approved"):
        code, body = api("PATCH", f"/projects/{pid}/tasks/{first}", {"status": status})
        print(f"  -> {status}: {code}")
        if code != 200:
            print("     ", json.dumps(body, default=str)[:600])
            break

    step("THE ASSERTION: what is on main")
    on_main = git(ROOT, "log", "--format=%H %s", "main").splitlines()
    for line in on_main:
        print("  ", line)
    first_landed = any(shas[first] in ln for ln in on_main)
    second_landed = any(shas[second] in ln for ln in on_main)
    print(f"\n  first task's commit on main:  {first_landed}")
    print(f"  second task's commit on main: {second_landed}   <-- must be False (F58)")
    print(f"  second.py exists in the working tree: {(ROOT / 'second.py').exists()}   <-- must be False")

    step("checkout release (design D5)")
    for task_id in (first, second):
        path = worktrees.task_worktree_path(ROOT, task_id)
        branch = worktrees.task_branch_name(task_id)
        exists = git(ROOT, "rev-parse", "--verify", "--quiet", branch, check=False)
        print(f"  {task_id}: checkout exists={path.exists()}  branch kept={bool(exists)}")

    print("\n=== VERDICT")
    if second_landed:
        print("  FAILED — F58 reproduced: the second task's work shipped with the first's approval.")
        return 1
    if not first_landed:
        print("  INCONCLUSIVE — the approved task's own work did not land; read the steps above.")
        return 2
    print("  PASSED — the approved task's work landed and the other task's did not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
