"""Acceptance drive for F679 (spdoc-48a94dbf4a02): under "Ask me", a permission request a Claude
subagent raises reaches the operator as the subagent's.

Before: the request listed for the operator carried no trace of the subagent, so the card read as
the agent's own call.

  py -3.11 scripts/drive/d1018_f679_subagent_request.py <project-id> <agent>

The agent must be bound to a Claude Haiku runner on the Hub `e2e.py hub-up` started. The script
answers the request itself (Deny), so the run ends. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, agent):
    message = (
        "Use the Agent tool exactly once, with the description 'write marker', and tell the "
        "subagent to use the Write tool to create marker-f679.txt containing hi, and nothing else. "
        "Do not write the file yourself. Then reply DONE."
    )
    run_id = e2e.cmd_turn(project, agent, message, perm="manual", fresh=True)
    check("the turn started", bool(run_id))
    if not run_id:
        return
    seen = None
    deadline = time.time() + 240
    while time.time() < deadline and seen is None:
        status, rows = e2e.request(
            "GET", f"/projects/{project}/permission-requests?include_expired=true"
        )
        for row in rows if isinstance(rows, list) else []:
            if row.get("run_id") == run_id and row.get("status") == "pending":
                print("pending:", row["tool_name"], row.get("subagent"))
                if row.get("subagent"):
                    seen = row
                else:
                    e2e.request("POST", f"/projects/{project}/permission-requests/{row['id']}/decide", {"allow": True})
        time.sleep(2)
    check("a subagent's request was listed while pending", seen is not None)
    if seen:
        check(
            "it names the delegation",
            (seen["subagent"] or {}).get("description") == "write marker",
            str(seen["subagent"]),
        )
        check("it names the parent call", bool((seen["subagent"] or {}).get("parent_call_id")))
        e2e.request("POST", f"/projects/{project}/permission-requests/{seen['id']}/decide", {"allow": False})
    print("run:", e2e.wait_for(run_id, 5))
    e2e.dump_turn(run_id)


if __name__ == "__main__":
    try:
        main(*sys.argv[1:3])
    finally:
        print("FAILED: " + "; ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
