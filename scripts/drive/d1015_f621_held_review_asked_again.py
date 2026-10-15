"""Drive F621: accepting the evidence a review waited on asks that reviewer again.

Before: a tester's approval was refused while the builder's evidence awaited the operator, its turn
ended without a verdict, and after the operator accepted the evidence nothing asked the tester again
-- the flow said "Ask tester again", which no control in the app does. After: the decision queues the
held review for the same reviewer, which records its verdict.

  py -3.11 scripts/drive/d1015_f621_held_review_asked_again.py <project-id> [builder] [tester]

Three Haiku turns (builder, held review, review asked again). Exit 1 when any check fails.
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


def rows(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def wait_until(predicate, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = predicate()
        if found:
            return found
        time.sleep(5)
    return predicate()


def runs_of(project, agent):
    return rows("select id, status from runs where project_id=? and agent=? order by started_at",
                project, agent)


def settled(project, agent):
    return all(r["status"] not in ("running", "queued", "starting") for r in runs_of(project, agent))


def main(project, builder="builder", tester="tester"):
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": "held review"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "held review",
        "summary": "One requirement whose evidence the operator decides.",
        "problem": "Drive fixture for F621.",
        "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "The README MUST mention item 1.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the README", "when": "read",
                                 "then": "it mentions item 1"}],
        "tasks": [{"key": "t1", "title": "Mention item 1", "description": "Add 'item 1' to README.md.",
                   "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    e2e.call("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    e2e.request("POST", f"{spec}/documents/close-exploration?path={path}")
    e2e.request("POST", f"{spec}/documents/propose?path={path}")
    _, approved = e2e.request("POST", f"{spec}/documents/phase?path={path}&to=approved", {"reason": "drive", "approve_anyway": True})
    [task_id] = approved["tasks_created"]
    e2e.call("PATCH", f"/projects/{project}/tasks/{task_id}", {"assignee": builder})

    run = e2e.cmd_turn(
        project, builder,
        f"Work task {task_id}: append a line 'item 1' to README.md in your workspace and commit it "
        f"with git (message: item 1). Then call record_evidence once with identifier FR-1, task_id "
        f"{task_id}, kind manual_observation, summary 'README mentions item 1'. Then move task "
        f"{task_id} to completed. Reply DONE.",
        task=task_id, fresh=True,
    )
    check("the builder's turn started", run is not None)
    if run is None:
        return
    e2e.wait_for(run, 6)
    evidence = rows("select id, review_state from requirement_evidence where task_id=?", task_id)
    status = rows("select status from tasks where id=?", task_id)[0]["status"]
    check("the builder recorded evidence and completed the task",
          bool(evidence) and status == "completed", f"evidence={evidence} status={status}")
    if not evidence or status != "completed":
        return

    code, body = e2e.request("POST", f"/projects/{project}/agent/trigger", {
        "agent": tester, "review_task_id": task_id,
        "message": f"Review task {task_id}: if README.md mentions item 1, approve it (update_task "
                   f"status approved). If the approval is refused, end your turn and report the "
                   f"refusal word for word; do not ask anyone.",
    })
    check("the review was dispatched", code == 200, f"{code} {str(body)[:200]}")
    wait_until(lambda: runs_of(project, tester) and settled(project, tester), 600)
    divergences = rows("select agent, policy_applied, outcome from run_divergences where task_id=?", task_id)
    status = rows("select status, assignee from tasks where id=?", task_id)[0]
    print(f"  after the first review: {status} divergences={divergences}")
    check("the review ended held, with nobody asked",
          status["status"] == "under_review" and any(d["outcome"] == "surfaced" for d in divergences),
          f"{status} {divergences}")

    first_runs = len(runs_of(project, tester))
    code, body = e2e.request("POST", f"{spec}/spec/evidence/{evidence[0]['id']}/decision",
                             {"decision": "accepted", "reason": "README checked by the operator"})
    check("the operator accepted the evidence", code == 200, f"{code} {str(body)[:200]}")
    asked = wait_until(lambda: len(runs_of(project, tester)) > first_runs, 120)
    check("the tester was asked again", bool(asked), f"runs={runs_of(project, tester)}")
    wait_until(lambda: settled(project, tester), 600)
    status = rows("select status from tasks where id=?", task_id)[0]["status"]
    outcome = rows("select outcome from run_divergences where task_id=? order by sequence", task_id)
    print(f"  after the decision: status={status} divergences={outcome}")
    check("the review recorded its verdict", status in ("approved", "revision_needed"), status)


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
