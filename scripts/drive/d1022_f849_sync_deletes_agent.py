"""Acceptance drive for F849: a session sync that deletes an agent must not leave its open
conversations for a later agent of the same name.

Before: the conversation stayed `open`, GET /conversations listed it for the re-created agent, and
a trigger naming it resumed the deleted agent's provider session ("PONG"). After: the sync archived
it, the list shows none open, and the trigger is refused.

  py -3.11 scripts/drive/d1022_f849_sync_deletes_agent.py <project-id>

On a scratch Hub that `e2e.py hub-up` started, project set up with `setup`. One real Haiku turn.
"""

import importlib.util
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude" / "skills" / "e2e-loop" / "e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project):
    base = f"/projects/{project}"
    e2e.cmd_agent(project, "keeper", "-", "claude", HAIKU)
    e2e.cmd_agent(project, "gamma", "-", "claude", HAIKU)
    status, run = e2e.request(
        "POST", f"{base}/agent/trigger",
        {"agent": "gamma", "message": "Reply with the single word PONG and nothing else."},
    )
    check("gamma's turn was accepted", status == 200, str(status))
    conversation_id = run.get("conversation_id")
    for _ in range(90):
        row = e2e.ro().execute("select status from runs where id=?", (run.get("run_id"),)).fetchone()
        if row and row[0] not in ("running", "queued", "pending"):
            break
        time.sleep(2)
    session_id = e2e.ro().execute(
        "select provider_session_id from conversations where id=?", (conversation_id,)
    ).fetchone()[0]
    check("the turn left a provider session", bool(session_id), str(session_id))

    status, res = e2e.request("POST", f"{base}/session/sync", {"data": {"agents": {"keeper": {}}}})
    check("the sync deleted gamma", status == 200 and res.get("removed") == ["gamma"], f"{status} {res}")
    lifecycle = e2e.ro().execute(
        "select lifecycle from conversations where id=?", (conversation_id,)
    ).fetchone()[0]
    check("gamma's conversation is archived", lifecycle == "archived", lifecycle)

    status, runner = e2e.request("GET", f"{base}/runners")
    runner_id = next(r["id"] for r in runner if r.get("model") == HAIKU)
    status, _ = e2e.request("POST", f"{base}/agents", {"name": "gamma", "runner_id": runner_id})
    check("gamma was created again", status == 201, str(status))
    status, listed = e2e.request("GET", f"{base}/conversations?agent=gamma")
    open_ids = [c["id"] for c in (listed if isinstance(listed, list) else listed.get("conversations", []))]
    check("the new gamma has no open conversation", conversation_id not in open_ids, str(open_ids))
    status, res = e2e.request(
        "POST", f"{base}/agent/trigger",
        {"agent": "gamma", "conversation_id": conversation_id,
         "message": "What single word did you reply with earlier?"},
    )
    check("a trigger naming the old conversation is refused", status in (404, 409, 422, 400), f"{status} {str(res)[:200]}")
    print("\n%d failure(s)" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
