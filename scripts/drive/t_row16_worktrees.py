"""Row 16 WORKTREES -- two writing agents on one file in parallel worktrees.

Real surface only. No row inserts. Haiku turns.
"""

import os
import sys
import time

from aw import api, show

REPO = r"C:\Users\huida\Documents\drive-wt-0829"
P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"


def trigger(agent, message, task_id=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if task_id:
        body["task_id"] = task_id
    return api("POST", f"/projects/{P}/agent/trigger", body, timeout=30)


def agent_status(name):
    c, b = api("GET", f"/projects/{P}/agents")
    for a in b:
        if a["name"] == name:
            return a["status"]
    return "?"


def wait_idle(names, limit=420):
    t0 = time.time()
    while time.time() - t0 < limit:
        st = {n: agent_status(n) for n in names}
        if all(s in ("idle", "error", "offline") for s in st.values()):
            print(f"  settled after {int(time.time()-t0)}s: {st}")
            return st
        time.sleep(5)
    print(f"  TIMEOUT after {limit}s: { {n: agent_status(n) for n in names} }")
    return None


def step(label):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


def main():
    step("0. Baseline worktree state")
    show("worktrees", *api("GET", f"/projects/{P}/worktrees"))
    show("conflicts", *api("GET", f"/projects/{P}/worktrees/conflicts"))
    show("alpha workspace", *api("GET", f"/projects/{P}/worktrees/alpha"))

    step("1. Two tasks, one per agent, both naming the SAME file")
    tasks = {}
    for agent, verb in (("alpha", "multiply"), ("beta", "divide")):
        c, b = api(
            "POST",
            f"/projects/{P}/tasks",
            {
                "title": f"Add a {verb} function to calc.py",
                "description": (
                    f"Edit calc.py in your working directory. Append a function "
                    f"`{verb}(a, b)` that returns a {verb[:3]} of the two arguments, "
                    f"in the same style as the existing add/sub. Change nothing else. "
                    f"Do not run git. Reply with the final contents of calc.py."
                ),
                "assignee": agent,
                "priority": "high",
            },
        )
        show(f"task for {agent}", c, b)
        if c >= 300:
            sys.exit(1)
        tasks[agent] = b["id"]

    step("2. Both agents run in parallel, bound to their tasks")
    for agent in ("alpha", "beta"):
        c, b = trigger(
            agent,
            "Do the task you have been assigned. Keep it to one small edit.",
            task_id=tasks[agent],
        )
        show(f"trigger {agent}", c, b)
    wait_idle(["alpha", "beta"])

    step("3. Worktrees after both turns")
    show("worktrees", *api("GET", f"/projects/{P}/worktrees"))
    show("alpha workspace", *api("GET", f"/projects/{P}/worktrees/alpha"))
    show("beta workspace", *api("GET", f"/projects/{P}/worktrees/beta"))

    step("4. Conflicts")
    show("conflicts", *api("GET", f"/projects/{P}/worktrees/conflicts"), limit=4000)

    step("5. Tasks now")
    for agent, tid in tasks.items():
        show(f"task {agent}", *api("GET", f"/projects/{P}/tasks/{tid}"), limit=1500)

    print("\nTASKS=" + repr(tasks))


if __name__ == "__main__":
    main()
