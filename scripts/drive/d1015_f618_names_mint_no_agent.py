"""Drive F618: a name that was never an agent is refused by every agent-keyed route, and mints none.

Before: `POST /agents/{name}/heartbeat`, `/output`, `/compact`, `/new-session` answered 201 for any
name, and `GET /agents` then listed it (and the Hub's own `hub` sender) as an open agent the
Overview counted against the agent budget. After: the writes 404 by name, compact/new-session are
gone (decision fix-D9), the reads 404 by name, and the roster is the agents table.

  py -3.11 scripts/drive/d1015_f618_names_mint_no_agent.py <project-id> [agent]

No agent turns. Exit 1 when any check fails.
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


def roster(project):
    return sorted(a["name"] for a in e2e.call("GET", f"/projects/{project}/agents"))


def main(project, agent="alpha"):
    before = roster(project)
    check("the real agent is listed", agent in before, str(before))

    for path, body in (
        ("heartbeat", {"status": "active", "message": "hi"}),
        ("output", {"content": "hello"}),
    ):
        for name in ("ghost", "operator", "a%20b%20c"):
            status, res = e2e.request("POST", f"/projects/{project}/agents/{name}/{path}", body)
            check(
                f"{path} under {name!r} is refused",
                status == 404 and "is not an agent" in str(res),
                f"{status} {str(res)[:120]}",
            )
    for path in ("compact", "new-session"):
        status, res = e2e.request("POST", f"/projects/{project}/agents/{agent}/{path}")
        check(f"{path} is gone", status in (404, 405), f"{status} {str(res)[:120]}")
    for url in (
        f"/projects/{project}/agents/ghost/timeline",
        f"/projects/{project}/agents/ghost/output",
        f"/projects/{project}/agent/sessions/ghost",
    ):
        status, res = e2e.request("GET", url)
        check(f"GET {url.split(project)[1]} is refused", status == 404, f"{status}")

    status, _ = e2e.request(
        "POST", f"/projects/{project}/agents/{agent}/heartbeat", {"status": "active"}
    )
    check("a real agent's heartbeat still lands", status == 201, str(status))
    status, _ = e2e.request("POST", f"/projects/{project}/agents/{agent}/output", {"content": "x"})
    check("a real agent's output still lands", status == 201, str(status))

    after = roster(project)
    check("the roster is unchanged", after == before, f"{before} -> {after}")
    check("the Hub's own sender is not an agent", "hub" not in after)
    rows = e2e.ro().execute(
        "select count(*) from agent_heartbeats where project_id=? and agent!=?", (project, agent)
    ).fetchone()[0]
    check("no heartbeat row under another name", rows == 0, str(rows))
    summary = next(p for p in e2e.call("GET", "/projects") if p["id"] == project)
    names = sorted(a["name"] for a in summary["agents"])
    check("the project header agrees with the roster", names == after, f"{names} vs {after}")


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
