"""Acceptance drive for F663/F664: a call-mode turn starts with an empty calls directory.

Before: `prepare_calls_dir` never removed a file, so a new conversation followed the prompt's
example `1.json`, and a write tool that refuses an unread existing file (Copilot's `create`, Claude
Haiku 4.5's `Write`) failed on the leftover; the work-PC turn cost twice the first. After: a turn
in the agent's own worktree finds the directory empty, and both texts ask for a new name per call.

  py -3.11 scripts/drive/d1016_f663_calls_dir_clean.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Two Haiku turns in call mode
(`hub_client: "cli"`), each in a new conversation; stale `1.json`..`3.json` are planted in the
agent's worktree between them. Exit 1 on any fail.
"""

import importlib.util
import json
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "shimmer"
STALE = {"title": "F663-STALE", "description": "left by an earlier turn"}
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def ask(title):
    return (
        f"Call the AgentWeave tool create_task with title {title!r}, description 'drive check' "
        f"and assignee {AGENT!r}, with no requirements. Do not ask me anything; then stop."
    )


def turn(project, message):
    status, res = e2e.request(
        "POST", f"/projects/{project}/agent/trigger", {"agent": AGENT, "message": message}
    )
    if status >= 300:
        raise SystemExit(f"trigger -> {status}: {res}")
    run_id = res["run_id"]
    return run_id, e2e.wait_for(run_id, minutes=6)


def outputs(run_id):
    return e2e.ro().execute(
        "select kind, content, payload from agent_outputs where run_id=? "
        "order by timestamp, sequence, id",
        (run_id,),
    ).fetchall()


def failed_tools(run_id):
    bad = []
    for row in outputs(run_id):
        if row["kind"] != "tool_result":
            continue
        try:
            payload = json.loads(row["payload"] or "{}")
        except ValueError:
            continue
        if payload.get("is_error"):
            bad.append((row["content"] or "")[:200])
    return bad


def task_titles(project):
    return [
        r["title"]
        for r in e2e.ro().execute("select title from tasks where project_id=?", (project,))
    ]


def main(name):
    project = e2e.cmd_setup(name)
    directory = pathlib.Path(e2e.PROJECTS) / name
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU}
    )
    status, res = e2e.request(
        "POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner["id"]}
    )
    if status >= 300 and status != 409:
        raise SystemExit(f"agent -> {status}: {res}")
    e2e.call("PATCH", f"/projects/{project}/agents/{AGENT}", {"config": {"hub_client": "cli"}})

    first, first_status = turn(project, ask("F663-ONE"))
    check("turn 1 completes", first_status == "completed", f"{first} {first_status}")
    calls = directory / ".agentweave" / "worktrees" / AGENT / ".agentweave" / "calls"
    check("turn 1 ran in the agent's own worktree", calls.is_dir(), str(calls))
    check("turn 1 created its task", "F663-ONE" in task_titles(project), str(task_titles(project)))
    for n in (1, 2, 3):
        (calls / f"{n}.json").write_text(json.dumps(STALE), encoding="utf-8")

    second, second_status = turn(project, ask("F663-TWO"))
    check("turn 2 completes", second_status == "completed", f"{second} {second_status}")
    titles = task_titles(project)
    check("turn 2 created its task", "F663-TWO" in titles, str(titles))
    check("no task came from a leftover file", "F663-STALE" not in titles, str(titles))
    bad = failed_tools(second)
    check("turn 2 had no failed tool call (no write refused on a leftover)", not bad, str(bad))
    left = sorted(p.name for p in calls.glob("*.json") if "F663-STALE" in p.read_text("utf-8"))
    check("no leftover survived turn 2's start", not left, str(left))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # noqa: BLE001 - a raise is a failure, never ALL PASS
        failures.append(f"raised: {exc!r}")
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
