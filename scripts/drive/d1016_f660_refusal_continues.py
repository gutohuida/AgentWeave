"""Acceptance drive for F660: a refused Copilot call does not end the turn.

Before: the Hub's refusal of a root Copilot call ended the turn -- `tool_result` "The user rejected
this tool call.", then `Run completed (exit 0).`, no agent text after the refusal and nothing on
the record saying why. After: one `copilot.refusal_continued` diagnostic, agent text after it, and
`run_completed` carrying `stop_reason: end_turn` and `refusal_continuations: 1`.

  py -3.11 scripts/drive/d1016_f660_refusal_continues.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Two Copilot turns on
claude-haiku-5.5, which spend premium requests (fix-D16 allows it):
  A. Edit files: the agent is told to list `C:\\Python*`, outside its workspace; the judge refuses.
  B. Ask me: the agent is told to run `echo hi`; the operator's card is denied.
Exit 1 on any fail.
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

MODEL = "claude-haiku-5.5"
AGENT = "copilot1"
ASK_OUTSIDE = (
    "Use your shell tool to run exactly this PowerShell command, and nothing else first: "
    "`Get-ChildItem 'C:\\Python*'`. Then tell me what it printed. Do not ask me anything."
)
ASK_ECHO = (
    "Use your shell tool to run exactly `echo hi`, and nothing else first. Then tell me what it "
    "printed. Do not ask me anything."
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


def lifecycle(run_id):
    rows = e2e.ro().execute(
        "select event_type, data from event_logs where event_type in "
        "('run_completed','run_failed','run_stopped')"
    ).fetchall()
    found = [(r["event_type"], json.loads(r["data"] or "{}")) for r in rows]
    return [(t, d) for t, d in found if d.get("run_id") == run_id]


def trigger(project, message, mode):
    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": AGENT, "message": message, "overrides": {"permission_mode": mode}},
    )
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    return res["run_id"]


def deny_cards(project, run_id, minutes=4):
    """Deny every card the run raises until it ends; returns how many were denied."""
    denied = 0
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        cards = e2e.call("GET", f"/projects/{project}/permission-requests")
        cards = cards if isinstance(cards, list) else cards.get("requests", [])
        for card in cards:
            if card.get("run_id") == run_id and card.get("status") == "pending":
                status, res = e2e.request(
                    "POST",
                    f"/projects/{project}/permission-requests/{card['id']}/decide",
                    {"allow": False},
                )
                print("denied", card.get("tool_name"), status)
                denied += 1
        state = e2e.ro().execute("select status from runs where id=?", (run_id,)).fetchone()
        if state and state["status"] != "running":
            return denied
        time.sleep(2)
    return denied


def judge_turn(name, run_id, decided_by):
    final = e2e.wait_for(run_id, minutes=6)
    check(f"{name}: the run completed", final == "completed", final)
    rows = outputs(run_id)
    print(f"{name} rows:", [(k, c[:60]) for k, c, _ in rows])
    refused = [
        i
        for i, (k, c, p) in enumerate(rows)
        if k == "tool_result" and "rejected" in (c + json.dumps(p)).lower()
    ]
    check(f"{name}: a tool call was refused", bool(refused), str(rows)[:400])
    continued = [
        (i, p)
        for i, (k, _, p) in enumerate(rows)
        if k == "diagnostic" and p.get("code") == "copilot.refusal_continued"
    ]
    check(f"{name}: one copilot.refusal_continued row", len(continued) == 1, str(continued)[:300])
    if continued:
        index, payload = continued[0]
        check(
            f"{name}: it names who refused",
            (payload.get("facts") or {}).get("decided_by") == decided_by,
            str(payload)[:300],
        )
        after = [c for k, c, _ in rows[index + 1 :] if k == "text" and c.strip()]
        check(f"{name}: the agent wrote text after it", bool(after), str(after)[:300])
    ended = lifecycle(run_id)
    payload = ended[-1][1] if ended else {}
    check(f"{name}: run_completed carries stop_reason end_turn", payload.get("stop_reason") == "end_turn", str(payload)[:300])
    check(
        f"{name}: run_completed carries refusal_continuations 1",
        payload.get("refusal_continuations") == 1,
        str(payload)[:300],
    )
    status_rows = [p for k, _, p in rows if k == "status" and p.get("phase") == "completed"]
    check(
        f"{name}: the closing status row carries the stop reason",
        bool(status_rows) and status_rows[-1].get("stop_reason") == "end_turn",
        str(status_rows)[-300:],
    )


def main(name):
    project = e2e.cmd_setup(name)
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Copilot haiku", "cli": "copilot", "model": MODEL}
    )
    status, res = e2e.request(
        "POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner["id"]}
    )
    if status >= 300 and status != 409:
        raise SystemExit(f"agent -> {status}: {res}")

    run_a = trigger(project, ASK_OUTSIDE, "acceptEdits")
    print("A run", run_a)
    judge_turn("A (judge)", run_a, "hub")

    run_b = trigger(project, ASK_ECHO, "manual")
    print("B run", run_b)
    denied = deny_cards(project, run_b)
    check("B (operator): a card was denied", denied >= 1, str(denied))
    judge_turn("B (operator)", run_b, "operator")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
