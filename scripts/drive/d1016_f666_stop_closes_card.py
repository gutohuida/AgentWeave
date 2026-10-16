"""Acceptance drive for F666: Stop closes the tool card it interrupted.

Before: a run stopped while a shell command ran recorded `tool_use` and then `Run stopped` with no
`tool_result`, so the card read "awaiting result" for ever. After: a closing `tool_result` with the
same call id and `status: "interrupted"` sits between them, and the chat route returns that order.

  py -3.11 scripts/drive/d1016_f666_stop_closes_card.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). One Haiku turn (Claude, PTY path)
told to run a 240-second Python sleep (Claude Code blocks a bare
`sleep 240` itself); Stop is pressed once its `tool_use` is recorded. Exit 1 on any fail.
"""

import importlib.util
import json
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "sleeper"
ASK = (
    "Run exactly this command with your Bash tool, in the foreground, and wait for it to finish: "
    "`py -3.11 -c \"import time; time.sleep(240); print('done')\"`. Do not ask me anything and do "
    "not run anything else first."
)
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def outputs(run_id):
    rows = e2e.ro().execute(
        "select kind, content, payload from agent_outputs where run_id=? "
        "order by timestamp, sequence, id",
        (run_id,),
    ).fetchall()
    return [(r["kind"], r["content"], json.loads(r["payload"] or "{}")) for r in rows]


def main(name):
    project = e2e.cmd_setup(name)
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU}
    )
    status, res = e2e.request(
        "POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner["id"]}
    )
    if status >= 300 and status != 409:
        raise SystemExit(f"agent -> {status}: {res}")

    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": AGENT, "message": ASK, "overrides": {"permission_mode": "bypassPermissions"}},
    )
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    run_id = res["run_id"]

    deadline = time.time() + 180
    while time.time() < deadline:
        if any(kind == "tool_use" and "time.sleep" in json.dumps(p) for kind, _, p in outputs(run_id)):
            break
        time.sleep(2)
    uses = [p for kind, _, p in outputs(run_id) if kind == "tool_use"]
    check("the sleep was called", any("time.sleep" in json.dumps(p) for p in uses), str(uses)[:300])
    time.sleep(3)

    status, res = e2e.request("POST", f"/projects/{project}/agent/{AGENT}/stop")
    check("Stop is accepted", status == 200, f"{status} {res}")
    final = e2e.wait_for(run_id, minutes=2)
    check("the run is stopped", final == "stopped", final)

    rows = outputs(run_id)
    print("rows:", [(k, c[:40]) for k, c, _ in rows])
    sleep_ids = [p.get("call_id") for k, _, p in rows if k == "tool_use" and "time.sleep" in json.dumps(p)]
    call_id = sleep_ids[-1] if sleep_ids else None
    results = [(i, p) for i, (k, _, p) in enumerate(rows) if k == "tool_result" and p.get("call_id") == call_id]
    check("the sleep call has exactly one result", len(results) == 1, str(results)[:300])
    if results:
        index, payload = results[0]
        check("it is the closing row", payload.get("status") == "interrupted", str(payload)[:300])
        check("it is not an error", payload.get("is_error") is False, str(payload)[:300])
        check("the status row is last, after it", rows[-1][0] == "status" and index < len(rows) - 1, rows[-1][1])
    check("the status row says stopped", rows and rows[-1][1].startswith("Run stopped"), rows[-1][1] if rows else "")

    conversation = e2e.latest_conversation(project, AGENT)
    chat = e2e.call("GET", f"/projects/{project}/agent/{AGENT}/chat/{conversation}")
    kinds = [
        (e.get("output_kind"), (e.get("payload") or {}).get("status"))
        for e in chat["entries"]
        if e.get("run_id") == run_id and e.get("output_kind") in ("tool_use", "tool_result", "status")
    ]
    tail = kinds[-3:]
    check(
        "the chat route returns tool_use, the closing result, then the status row",
        [k for k, _ in tail] == ["tool_use", "tool_result", "status"] and tail[1][1] == "interrupted",
        str(kinds),
    )
    facts = (chat.get("runs") or {}).get(run_id) or {}
    check("the chat route carries the run's stopped facts", facts.get("status") == "stopped", str(facts))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
