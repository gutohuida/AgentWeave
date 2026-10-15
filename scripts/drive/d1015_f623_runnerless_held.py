"""Drive F623: a message to an agent with no runner is said to be held, and the team says why.

Before: alpha's `send_message` to runnerless gamma answered plain success, the Team block listed
gamma as `runner=native` and the palette read "Native". After: the tool's answer carries
`held: no_runner` and a delivery note, the Team block says "no runner", and the roster's
`display_model` reads "No runner".

  py -3.11 scripts/drive/d1015_f623_runnerless_held.py <project-id> [agent]

Needs `agent` bound to a runner and an agent `gamma` with none. One Haiku turn.
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


def main(project, agent="alpha"):
    roster = {a["name"]: a for a in e2e.call("GET", f"/projects/{project}/agents")}
    check("gamma reads 'No runner'", roster["gamma"]["display_model"] == "No runner",
          roster["gamma"]["display_model"])
    context = e2e.call("GET", f"/projects/{project}/agents/agent-context?agent={agent}")
    text = str(context)
    check("the Team block says gamma has no runner", "`gamma`: no runner" in text)
    check("the Team block no longer says runner=native for gamma", "`gamma`: runner=native" not in text)

    run_id = e2e.cmd_turn(
        project, agent,
        "Use the agentweave send_message tool once to send gamma the message 'ping'. Then reply "
        "with the tool's full JSON answer, verbatim, and say whether gamma received it.",
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
    check("the tool answer carries the hold", "no_runner" in said and "has no runner" in said,
          said[-400:])
    queued = e2e.ro().execute(
        "select count(*) from inbound_queue_entries where project_id=? and agent='gamma' "
        "and state='queued'", (project,)
    ).fetchone()[0]
    check("the entry waits for gamma", queued >= 1, str(queued))


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
