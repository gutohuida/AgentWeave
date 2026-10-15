"""Drive S4's Tier 0 fixes after F618: F645, F642, F648.

- F645: a refused trigger for an unknown agent leaves no conversation and no queue entry.
- F642: a task's assignee is an open agent of the project, on create and on PATCH.
- F648: the agent-budget refusal an agent's `request_agent` meets names the remedies.

  py -3.11 scripts/drive/d1015_s4_names.py <project-id> [agent]

One Haiku turn (F648). Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def count(sql, *args):
    return e2e.ro().execute(sql, args).fetchone()[0]


def main(project, agent="alpha"):
    # F645
    status, res = e2e.request(
        "POST", f"/projects/{project}/agent/trigger", {"agent": "ghost3", "message": "typo send"}
    )
    check("trigger to an unknown agent is refused", status == 409, f"{status} {str(res)[:100]}")
    for table in ("conversations", "inbound_queue_entries"):
        n = count(f"select count(*) from {table} where project_id=? and agent='ghost3'", project)
        check(f"the refusal left no {table} row", n == 0, str(n))

    # F642
    status, res = e2e.request(
        "POST", f"/projects/{project}/tasks", {"title": "for a ghost", "assignee": "ghost"}
    )
    check("create with an unknown assignee is refused", status == 422, f"{status} {res}")
    task = e2e.call("POST", f"/projects/{project}/tasks", {"title": "s4 drive", "assignee": agent})
    status, res = e2e.request("PATCH", f"/projects/{project}/tasks/{task['id']}", {"assignee": "ghost"})
    check("PATCH to an unknown assignee is refused", status == 422, f"{status} {res}")
    held = e2e.call("GET", f"/projects/{project}/tasks/{task['id']}")["assignee"]
    check("the task keeps its holder", held == agent, str(held))
    roster = sorted(a["name"] for a in e2e.call("GET", f"/projects/{project}/agents"))
    check("the roster holds no ghost", "ghost" not in roster, str(roster))

    # F648: a budget of 1 with one open agent; the agent asks for another.
    e2e.call("PUT", f"/projects/{project}/settings", {"agent_budget": 1})
    run_id = e2e.cmd_turn(
        project, agent,
        "Call the agentweave request_agent tool once with name 'helper2', template "
        f"'{agent}' and task 'help'. Then reply with the tool's exact answer, verbatim.",
        fresh=True,
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    said = " ".join(
        row[0] or ""
        for row in e2e.ro().execute(
            "select content from agent_outputs where run_id=? order by timestamp, sequence", (run_id,)
        )
    )
    check(
        "the refusal the agent met names archive and Settings",
        "budget exhausted" in said and "archive" in said and "Settings" in said,
        said[-300:],
    )
    check("no agent was created", count(
        "select count(*) from agents where project_id=? and name='helper2'", project) == 0)


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
