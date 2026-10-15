"""Drive F614 and F669 on a scratch Hub.

F614: under `acceptEdits` Claude itself refuses a Write outside the workspace, and the run used
to record `[{"kind": "outside", ...}]` and warn "alpha wrote outside its workspace" for a file that
never existed. After: `[]` and no `agent_wrote_outside_workspace` event, the file absent.
F669: a `work_dir` under `.agentweave/` is refused with 400 before any run.

  py -3.11 scripts/drive/d1015_f614_f669.py <project-id> [agent]

One Haiku turn.
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
    outside = pathlib.Path.home() / "Documents" / "aw-f614-outside" / "written.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    if outside.exists():
        outside.unlink()
    run_id = e2e.cmd_turn(
        project, agent,
        f"Use the Write tool to create the file {outside} containing the word hello. "
        "Do not use a shell. If the write is refused, say so and stop.",
        fresh=True, perm="acceptEdits",
    )
    check("the turn started", run_id is not None)
    if run_id is None:
        return
    e2e.wait_for(run_id, 5)
    check("the file was not written", not outside.exists())
    row = e2e.ro().execute(
        "select outside_workspace_writes w from runs where id=?", (run_id,)
    ).fetchone()
    check("the run records no outside write", row["w"] in ("[]",), str(row["w"]))
    events = e2e.ro().execute(
        "select count(*) n from event_logs where event_type='agent_wrote_outside_workspace' "
        "and json_extract(data,'$.run_id')=?", (run_id,)
    ).fetchone()["n"]
    check("and no Warn says it did", events == 0, f"{events} events")
    tools = [r["content"] for r in e2e.ro().execute(
        "select content from agent_outputs where run_id=? and kind in ('tool_use','tool_result')",
        (run_id,))]
    print("tool rows:", tools)

    # F669, on a read-only agent (the only kind a work_dir is for).
    e2e.request("POST", f"/projects/{project}/agents/reader669/archive")
    runner = next(r for r in e2e.call("GET", f"/projects/{project}/runners") if r["cli"] == "claude")
    e2e.request("POST", f"/projects/{project}/agents", {"name": "reader669", "runner_id": runner["id"]})
    e2e.call("PATCH", f"/projects/{project}/agents/reader669", {"config": {"read_only": True}})
    for work_dir in (".agentweave", ".agentweave/worktrees/alpha"):
        status, body = e2e.request("POST", f"/projects/{project}/agent/trigger",
                                   {"agent": "reader669", "message": "hi", "work_dir": work_dir})
        check(f"F669 work_dir {work_dir} is refused", status == 400 and ".agentweave" in str(body),
              f"{status} {str(body)[:140]}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
