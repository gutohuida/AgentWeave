"""Dependencies sweep 2026-10-23, part 4: an existing task checkout catches up with a prerequisite
approved later, and a conflicting one.

Phases (run in order, real Haiku turns between them via e2e.py turn --task):
  setup                 D, E (clean pair) and F, G (conflicting pair); E and G assigned to beta
  link                  E depends_on D, G depends_on F (after E and G have a checkout and a commit)
  approve <task>        operator walks a completed task to approved (under_review -> approved)
  show <task>           the task, its story tail and its checkout's git log
"""

import json
import subprocess
import sys

from s1023_dp_common import BASE, sc, show

DIR = "C:/Users/huida/Documents/aw-dp-1023"


def mk(title, desc, assignee=None):
    body = {"title": title, "description": desc}
    if assignee:
        body.update(assignee=assignee, status="assigned")
    code, t = sc.api("POST", f"{BASE}/tasks", body)
    print(code, t.get("id"), t.get("status"), t.get("assignee"), title)
    return t["id"]


def main(cmd, *args):
    if cmd == "setup":
        ids = {
            "D": mk("D: write d.txt", "Create d.txt containing the single line: from D.", "alpha"),
            "E": mk("E: write e.txt", "Create e.txt containing the single line: from E.", "beta"),
            "F": mk("F: shared.txt (F)", "Create shared.txt containing exactly: F says hello.",
                    "alpha"),
            "G": mk("G: shared.txt (G)", "Create shared.txt containing exactly: G says goodbye.",
                    "beta"),
        }
        print("IDS", json.dumps(ids))
    elif cmd == "link":
        for task, on in zip(args[0::2], args[1::2]):
            code, r = sc.api("POST", f"{BASE}/tasks/{task}/dependencies", {"depends_on": on})
            show(f"{task} depends_on {on}", code, r, 600)
            code, r = sc.api("GET", f"{BASE}/tasks/{task}")
            print("  status", r.get("status"), "dependency_state", r.get("dependency_state"))
    elif cmd == "approve":
        task = args[0]
        for st in ("under_review", "approved"):
            code, r = sc.api("PATCH", f"{BASE}/tasks/{task}", {"status": st})
            show(f"PATCH {task} -> {st}", code, r if code >= 300 else r.get("status"), 1500)
        code, r = sc.api("GET", f"{BASE}/tasks/{task}/integrations")
        show("integrations", code, r, 1200)
    elif cmd == "show":
        task = args[0]
        code, r = sc.api("GET", f"{BASE}/tasks/{task}")
        print("task", r.get("status"), r.get("dependency_state"), r.get("blocked_reason"))
        wt = sc.ro("select path, branch from task_worktrees where task_id=?", (task,)) \
            if sc.ro("select name from sqlite_master where name='task_worktrees'") else []
        print("task_worktrees", wt)
        out = subprocess.run(["git", "-C", DIR, "worktree", "list"], capture_output=True,
                             text=True).stdout
        print(out)
        for line in out.splitlines():
            if task in line:
                path = line.split()[0]
                print(subprocess.run(["git", "-C", path, "log", "--oneline", "--graph", "-12"],
                                     capture_output=True, text=True).stdout)
                print(subprocess.run(["git", "-C", path, "status", "--short"],
                                     capture_output=True, text=True).stdout)


if __name__ == "__main__":
    main(*sys.argv[1:])
