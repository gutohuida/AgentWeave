"""Acceptance drive for F240: worker spend counts against the budget.

Before: a checkpoint, its probe and a conversation title spent tokens that reached no total and no
budget, and an exhausted budget paused turns while the workers kept spending. After: every worker
call is a `workers` line, the project total and the budget include them, and at exhaustion an
autonomous worker call (the titler) is not spawned while the operator's Checkpoint still runs.

  py -3.11 scripts/drive/d1016_f240_worker_spend.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Haiku throughout: the titles job
and the checkpoint runner on the agent's runner. Exit 1 on any fail.
"""

import importlib.util
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "spender"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def turn(project, message, conversation=None):
    body = {"agent": AGENT, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    status, res = e2e.request("POST", f"/projects/{project}/agent/trigger", body)
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    return res["run_id"], res["conversation_id"], e2e.wait_for(res["run_id"], minutes=4)


def _has_total():
    columns = {r[1] for r in e2e.ro().execute("PRAGMA table_info(worker_invocations)")}
    return "total_tokens" in columns


def workers(project):
    # Before the migration there is no total_tokens column; NULL keeps the checks honest.
    total = "sum(total_tokens)" if _has_total() else "NULL"
    return {
        row["kind"]: row
        for row in e2e.ro().execute(
            f"select kind, count(*) n, {total} total, "
            "group_concat(outcome) outcomes from worker_invocations where project_id=? "
            "group by kind",
            (project,),
        )
    }


def wait_for_kind(project, kind, outcome, seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        row = workers(project).get(kind)
        if row and outcome in (row["outcomes"] or ""):
            return row
        time.sleep(3)
    return workers(project).get(kind)


def turn_sum(project):
    row = e2e.ro().execute(
        "select sum(total_tokens) from turn_usage where project_id=? and status='measured'",
        (project,),
    ).fetchone()
    return row[0] or 0


def worker_sum(project):
    if not _has_total():
        return 0
    row = e2e.ro().execute(
        "select sum(total_tokens) from worker_invocations where project_id=?", (project,)
    ).fetchone()
    return row[0] or 0


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
    e2e.call("PATCH", f"/projects/{project}/manager/jobs/conversation-titles", {"enabled": True})
    e2e.call("PUT", f"/projects/{project}/settings", {"checkpoint_runner_id": runner["id"]})

    run1, conversation, st1 = turn(project, "Say hello in five words about a kettle.")
    check("turn 1 completes", st1 == "completed", f"{run1} {st1}")
    title = wait_for_kind(project, "conversation_title", "ok")
    check("the title call is a worker row with a total", bool(title and title["total"]), str(title))

    status, res = e2e.request("POST", f"/projects/{project}/conversations/{conversation}/checkpoint")
    check("the operator's checkpoint runs", status == 201, f"{status} {str(res)[:200]}")
    rows = workers(project)
    check(
        "checkpoint and probe are worker rows with totals",
        all(rows.get(k) and rows[k]["total"] for k in ("checkpoint", "checkpoint_probe")),
        str({k: dict(v) for k, v in rows.items()}),
    )

    snap = e2e.call("GET", f"/projects/{project}/accounting")
    kinds = [w["kind"] for w in snap.get("workers") or []]
    check(
        "accounting lists the worker lines in kind order",
        kinds == ["checkpoint", "checkpoint_probe", "conversation_title"],
        str(kinds),
    )
    expected = turn_sum(project) + worker_sum(project)
    check(
        "project total = turns + workers",
        snap["project"]["total_tokens"] == expected,
        f"{snap['project']['total_tokens']} vs {expected}",
    )
    check("the budget reads the same total", snap["budget"]["used_tokens"] == expected)

    e2e.call("PATCH", f"/projects/{project}/accounting/budget", {"token_budget": expected - 1})
    run2, conversation2, st2 = turn(project, "Name one colour of a kettle, one word.")
    check("an operator turn still runs at exhaustion", st2 == "completed", f"{run2} {st2}")
    gated = wait_for_kind(project, "conversation_title", "budget_exhausted", seconds=40)
    check(
        "the titler is not spawned at exhaustion",
        bool(gated and "budget_exhausted" in (gated["outcomes"] or "")),
        str(dict(gated) if gated else None),
    )
    before = worker_sum(project)
    status, res = e2e.request(
        "POST", f"/projects/{project}/conversations/{conversation2}/checkpoint"
    )
    check("the operator's checkpoint runs at exhaustion", status == 201, f"{status}")
    check("and it is counted", worker_sum(project) > before, f"{before} -> {worker_sum(project)}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
