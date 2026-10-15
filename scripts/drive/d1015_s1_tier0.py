"""Drive the S1 Tier 0 fixes of FIX-PLAN-2026-10-15 against a scratch Hub: F620, F670, F608, F625.

  py -3.11 scripts/drive/d1015_s1_tier0.py <project-id> [agent]

The agent needs a Haiku runner (`e2e.py agent <project> alpha - claude haiku`). Costs one Haiku
turn (F608's held firing, delivered once the budget is cleared). F651 is not driven here: it needs a
question to time out mid-run and the agent to then poll `get_answer`, which a model does not do on
cue; its tests pin it.
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


def runs(project, agent):
    return e2e.ro().execute(
        "select count(*) n from runs where project_id=? and agent=?", (project, agent)
    ).fetchone()["n"]


def firing(job_id):
    return e2e.ro().execute(
        "select status, error_summary from job_runs where job_id=? order by fired_at desc limit 1",
        (job_id,),
    ).fetchone()


def job_entry(project, job_id):
    return e2e.ro().execute(
        "select id, state from inbound_queue_entries where project_id=? and job_id=? "
        "order by sequence desc limit 1",
        (project, job_id),
    ).fetchone()


def spend_the_budget(project):
    used = e2e.call("GET", f"/projects/{project}/accounting")["project"]["total_tokens"] or 0
    return e2e.request("PATCH", f"/projects/{project}/accounting/budget", {"token_budget": max(1, used // 2)})


def job(project, agent, name):
    return e2e.call(
        "POST",
        f"/projects/{project}/jobs",
        {"name": name, "agent": agent, "cron": "0 0 1 1 *", "enabled": True,
         "message": "Reply with the single word OK."},
    )["id"]


def main(project, agent="alpha"):
    # F620
    before = runs(project, agent)
    status, body = e2e.request("POST", f"/projects/{project}/agent/trigger", {"agent": agent, "message": "  "})
    check("F620 an empty message is refused", status == 422 and "empty" in str(body), f"{status}")
    check("F620 and no run started", runs(project, agent) == before)

    # F670
    status, body = e2e.request("PATCH", f"/projects/{project}/accounting/budget", {"token_budget": 2**63})
    check("F670 PATCH /budget past the bound is 422", status == 422, f"{status} {str(body)[:120]}")
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["token_budget"] = 2**64
    status, _ = e2e.request("PUT", f"/projects/{project}/settings", settings)
    check("F670 PUT /settings past the bound is 422", status == 422, str(status))

    # First a turn so the project has usage, so a budget can be spent.
    if (e2e.call("GET", f"/projects/{project}/accounting")["project"]["total_tokens"] or 0) == 0:
        run_id = e2e.cmd_turn(project, agent, "Reply with the single word OK.", fresh=True)
        e2e.wait_for(run_id, 5)

    # F608
    status, _ = spend_the_budget(project)
    check("budget set below usage", status == 200, str(status))
    held = job(project, agent, "f608-held")
    status, body = e2e.request("POST", f"/projects/{project}/jobs/{held}/run")
    check(
        "F608 a press on a spent budget answers 200 with the reason",
        status == 200 and body.get("waiting_reason") == "token budget exhausted",
        f"{status} {body}",
    )
    check("F608 the firing is in_progress, not failed", firing(held)["status"] == "in_progress",
          str(dict(firing(held))))

    # F625: a second waiting firing, withdrawn.
    gone = job(project, agent, "f625-withdrawn")
    e2e.request("POST", f"/projects/{project}/jobs/{gone}/run")
    entry = job_entry(project, gone)
    status, _ = e2e.request("DELETE", f"/projects/{project}/queue/entries/{entry['id']}")
    check("F625 the entry is withdrawn", status == 200, str(status))
    row = firing(gone)
    check("F625 its firing is stopped, naming why", row["status"] == "stopped"
          and "withdrawn" in (row["error_summary"] or ""), str(dict(row)))

    # F608 continued: clearing the budget delivers the held firing, which then completes.
    e2e.request("PATCH", f"/projects/{project}/accounting/budget", {"token_budget": None})
    deadline = time.time() + 240
    while time.time() < deadline and firing(held)["status"] == "in_progress":
        time.sleep(5)
    check("F608 the held firing ran once the budget was cleared",
          firing(held)["status"] == "completed", str(dict(firing(held))))
    for job_id in (held, gone):
        e2e.request("POST", f"/projects/{project}/jobs/{job_id}/archive")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    finally:
        e2e.request("PATCH", f"/projects/{sys.argv[1]}/accounting/budget", {"token_budget": None})
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
