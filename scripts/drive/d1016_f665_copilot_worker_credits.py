"""Live check for F665: a Copilot checkpoint's credits reach its worker line and the project total.

F665 was checked only at the route, on the work-PC drive's recorded figures (a Copilot worker call
spends premium requests). This drives one: a Copilot turn, then the operator's checkpoint on a
Copilot checkpoint runner, then `GET /accounting`.

  py -3.11 scripts/drive/d1016_f665_copilot_worker_credits.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Spends premium requests
(fix-D16 allows it). Exit 1 on any fail.
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
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def worker_rows(project):
    rows = e2e.ro().execute(
        "select kind, outcome, total_tokens, ai_nano_aiu, premium_requests from worker_invocations"
        " where project_id=? order by rowid",
        (project,),
    ).fetchall()
    return [dict(r) for r in rows]


def main(name):
    project = e2e.cmd_setup(name)
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Copilot", "cli": "copilot", "model": MODEL}
    )
    status, res = e2e.request(
        "POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner["id"]}
    )
    if status >= 300 and status != 409:
        raise SystemExit(f"agent -> {status}: {res}")
    e2e.call("PUT", f"/projects/{project}/settings", {"checkpoint_runner_id": runner["id"]})

    status, res = e2e.request(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": AGENT, "message": "Say hello in five words about a kettle. Do not use any tool."},
    )
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    run_id = res.get("run_id")
    conversation = res["conversation_id"]
    if not run_id:
        time.sleep(5)
        run_id = e2e.ro().execute(
            "select id from runs where conversation_id=? order by started_at desc limit 1",
            (conversation,),
        ).fetchone()["id"]
    final = e2e.wait_for(run_id, minutes=5)
    check("the Copilot turn completed", final == "completed", final)

    status, res = e2e.request("POST", f"/projects/{project}/conversations/{conversation}/checkpoint")
    check("the operator's checkpoint runs", status == 201, f"{status} {str(res)[:300]}")
    rows = worker_rows(project)
    print("worker rows:", rows)
    credited = [r for r in rows if r["ai_nano_aiu"] or r["premium_requests"]]
    check("the checkpoint's worker rows carry credits", bool(credited), str(rows))

    snap = e2e.call("GET", f"/projects/{project}/accounting")
    lines = {line["kind"]: line for line in snap.get("workers") or []}
    print("worker lines:", json.dumps(lines)[:800])
    checkpoint = lines.get("checkpoint") or {}
    check(
        "the checkpoint line shows its credits and counts a credited call",
        bool(checkpoint.get("ai_nano_aiu") or checkpoint.get("premium_requests"))
        and (checkpoint.get("credited_calls") or 0) >= 1,
        json.dumps(checkpoint)[:300],
    )
    turns = e2e.ro().execute(
        "select sum(ai_nano_aiu), sum(premium_requests) from turn_usage where project_id=?",
        (project,),
    ).fetchone()
    worker_aiu = sum(line.get("ai_nano_aiu") or 0 for line in lines.values())
    worker_premium = sum(line.get("premium_requests") or 0 for line in lines.values())
    project_credits = snap.get("project") or {}
    print("project:", json.dumps(project_credits)[:400], "turns:", tuple(turns))
    check(
        "the project's AI credits are turns plus workers",
        project_credits.get("ai_nano_aiu") == (turns[0] or 0) + worker_aiu,
        f"{project_credits.get('ai_nano_aiu')} vs {(turns[0] or 0)} + {worker_aiu}",
    )
    check(
        "the project's premium requests are turns plus workers",
        abs((project_credits.get("premium_requests") or 0) - ((turns[1] or 0) + worker_premium)) < 1e-9,
        f"{project_credits.get('premium_requests')} vs {(turns[1] or 0)} + {worker_premium}",
    )
    display = snap.get("preferred_display") or {}
    # An allowance reading outranks credits by design (F665 D3); this account reports one.
    expected = "allowance" if display.get("allowance") else "credits"
    check(f"the headline is {expected}", display.get("kind") == expected, json.dumps(display)[:300])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
