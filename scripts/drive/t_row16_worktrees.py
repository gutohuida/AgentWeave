"""Row 16 WORKTREES -- two writing agents on one file in parallel worktrees.

Real surface only. No row inserts. Haiku turns.
"""

import os
import sys
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
# Hard-wired to one night's fixture until 2026-08-30, along with an unused REPO constant naming a
# directory on this machine. The two agents have to be different and both bound, which `preflight`
# now asserts rather than assuming.
A1 = os.environ.get("AW_AGENT_A") or "alpha"
A2 = os.environ.get("AW_AGENT_B") or "beta"
# Row 17 merges these two branches into each other. They must edit the SAME file -- that is the
# point -- but the function names are per-run so a second run is not silently merging the first
# run's already-merged work and calling the absence of a conflict a pass.
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
TARGET = "calc.py"


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


def preflight():
    step("PRE. Preconditions")
    c, rows = api("GET", f"/projects/{P}/agents")
    if c != 200:
        sys.exit(f"cannot list agents on {P}: {c}")
    if A1 == A2:
        sys.exit("AW_AGENT_A and AW_AGENT_B must differ -- one agent cannot conflict with itself")
    for name in (A1, A2):
        row = next((a for a in rows if a["name"] == name), None)
        if row is None:
            sys.exit(f"agent {name!r} does not exist on {P}")
        if row.get("archived"):
            sys.exit(f"agent {name!r} is archived")
        if not row.get("runner_id"):
            sys.exit(f"agent {name!r} has no runner and cannot be triggered")
        if row.get("status") != "idle":
            sys.exit(f"agent {name!r} is {row.get('status')!r}, not idle")
    c, st = api("GET", f"/projects/{P}/settings")
    print(f"  [OK ] {A1} and {A2} bound and idle; main branch is {st.get('main_branch')!r}; "
          f"target {TARGET}, run tag {RUN}")


def main():
    preflight()
    step("0. Baseline worktree state")
    show("worktrees", *api("GET", f"/projects/{P}/worktrees"))
    show("conflicts", *api("GET", f"/projects/{P}/worktrees/conflicts"))
    show(f"{A1} workspace", *api("GET", f"/projects/{P}/worktrees/{A1}"))

    step("1. Two tasks, one per agent, both naming the SAME file")
    tasks = {}
    for agent, verb in ((A1, f"multiply_{RUN}"), (A2, f"divide_{RUN}")):
        c, b = api(
            "POST",
            f"/projects/{P}/tasks",
            {
                "title": f"Add a {verb} function to {TARGET}",
                "description": (
                    f"Edit {TARGET} in your working directory. Append a function "
                    f"`{verb}(a, b)` at the END of the file, in the same style as the existing "
                    f"add/sub. Change nothing else and do not reorder what is already there. "
                    f"Do not run git. Reply with the final contents of {TARGET}."
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
    for agent in (A1, A2):
        c, b = trigger(
            agent,
            "Do the task you have been assigned. Keep it to one small edit.",
            task_id=tasks[agent],
        )
        show(f"trigger {agent}", c, b)
    wait_idle([A1, A2])

    step("3. Worktrees after both turns")
    show("worktrees", *api("GET", f"/projects/{P}/worktrees"))
    show(f"{A1} workspace", *api("GET", f"/projects/{P}/worktrees/{A1}"))
    show(f"{A2} workspace", *api("GET", f"/projects/{P}/worktrees/{A2}"))

    step("4. Conflicts")
    show("conflicts", *api("GET", f"/projects/{P}/worktrees/conflicts"), limit=4000)

    step("5. Tasks now")
    for agent, tid in tasks.items():
        show(f"task {agent}", *api("GET", f"/projects/{P}/tasks/{tid}"), limit=1500)

    print("\nTASKS=" + repr(tasks))


if __name__ == "__main__":
    main()
