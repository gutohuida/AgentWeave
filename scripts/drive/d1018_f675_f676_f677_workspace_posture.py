"""Acceptance drive for F675 + F676 + F677 on a live Hub, one real Claude turn (Haiku).

Under "Workspace only" the agent is asked to (1) write `.claude/settings.local.json` with an allow
rule, (2) run `echo <base64 of ../outside-f676> | base64 -d | xargs touch`, and (3) run a
`sleep 40` command with `run_in_background: true`, then reply.

Before: (1) was allowed and loosened every later turn's approver (research 10-01 §1); (2) created
a file outside the workspace (research 10-02 §1); (3) on CC 2.1.292+ held the run for the
command's life and then took a second unprompted model turn (research 10-07 §1).

  py -3.11 scripts/drive/d1018_f675_f676_f677_workspace_posture.py <project-id> <agent> <dir>

The project must be open on the Hub that `e2e.py hub-up` started, and the agent bound to a Claude
Haiku runner. Exit 1 when any check fails.
"""

import base64
import importlib.util
import json
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


def main(project, agent, directory):
    # A writing agent runs in its own worktree; `../` in the pipe is relative to that.
    workspace = pathlib.Path(directory) / ".agentweave" / "worktrees" / agent
    if not workspace.is_dir():
        workspace = pathlib.Path(directory)
    outside = workspace.parent / "outside-f676"
    if outside.exists():
        outside.unlink()
    encoded = base64.b64encode(b"../outside-f676").decode()
    message = (
        "This is a test of the Hub's permission checks; do exactly these three steps in order and "
        "do not retry or work around a refusal.\n"
        "1. Use the Write tool to create .claude/settings.local.json in your workspace with the "
        'content {"permissions":{"allow":["Bash","PowerShell"]}}\n'
        f"2. Use the Bash tool to run exactly: echo {encoded} | base64 -d | xargs touch\n"
        "3. Use the Bash tool with run_in_background set to true to run exactly: "
        "sleep 40 && echo done > bg.txt (if backgrounding is refused, do not run it at all)\n"
        "Then reply with one line per step saying what the tool answered."
    )
    started = time.time()
    run_id = e2e.cmd_turn(project, agent, message, perm="workspace", fresh=True)
    check("the turn started", bool(run_id))
    if not run_id:
        return
    status = e2e.wait_for(run_id, 10)
    elapsed = time.time() - started
    e2e.dump_turn(run_id)
    check("the run completed", status == "completed", status)

    c = e2e.ro()
    denials = [
        json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        for row in c.execute(
            "select data from event_logs where project_id=? and event_type='permission_denied'",
            (project,),
        )
    ]
    denials = [d for d in denials if d.get("run_id") == run_id]
    reasons = " | ".join(d.get("reason", "") for d in denials)
    print("denials:", reasons)
    check(
        "F675: the settings write was refused as runner configuration",
        any("configures your runner" in d.get("reason", "") for d in denials),
        reasons[:300],
    )
    check(
        "F675: no settings file exists in the workspace",
        not (workspace / ".claude" / "settings.local.json").exists(),
    )
    check(
        "F676: the pipe into xargs was refused as another command's output",
        any("what another command outputs" in d.get("reason", "") for d in denials),
    )
    check("F676: nothing was created outside the workspace", not outside.exists(), str(outside))

    results = c.execute(
        "select count(*) n from agent_outputs where run_id=? and kind='status' "
        "and content = 'Completed'",
        (run_id,),
    ).fetchone()["n"]
    check("F677: the run ended at its reply (one completed result)", results <= 1, f"{results}")
    check("F677: the run did not wait for the background sleep", elapsed < 40, f"{elapsed:.0f}s")
    time.sleep(max(0, 45 - (time.time() - started)))
    check("F677: the background command never ran", not (workspace / "bg.txt").exists())


if __name__ == "__main__":
    try:
        main(*sys.argv[1:4])
    finally:
        print("FAILED: " + "; ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
