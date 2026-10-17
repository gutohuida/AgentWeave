"""Acceptance drive for slice `agentic-evidence` (vis-D1, vis-D4): the reviewer's verdict decides the
task's evidence, so nothing waits on the operator.

No agent holds `can_accept_evidence`. The operator does nothing after setup.

  approve leg   a builder appends 'item 1' to README.md, commits, records evidence and completes;
                a tester reviews and approves -> the task is approved, its evidence is accepted
                by the tester with a reason, the commit is merged into master, nothing surfaced.
  send-back leg a builder records evidence claiming 'item 2' without writing it; the tester finds
                README.md lacks it and sends the task back -> its evidence is rejected by the
                tester with a reason, and the task returns to the builder.

Before the build the approve leg ends `under_review` with a surfaced divergence (F672). Drives the
Hub `e2e.py hub-up` started (never :8000 or :8010). Four Haiku turns. Exit 1 when any check fails.

  py -3.11 scripts/drive/d1017_agentic_evidence.py <project-id> [builder] [tester]
"""

import importlib.util
import pathlib
import subprocess
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


def make_document(project, title, items):
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": title})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": title,
        "summary": "Requirements whose evidence the reviewer decides.",
        "problem": "Drive fixture for agentic evidence.",
        "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
        "requirements": [{"key": f"r{i}", "statement": f"The README MUST mention item {i}.",
                          "modal": "MUST"} for i in items],
        "acceptance_criteria": [{"key": f"c{i}", "requirement": f"r{i}", "given": "the README",
                                 "when": "read", "then": f"it mentions item {i}"} for i in items],
        "tasks": [{"key": f"t{i}", "title": f"Mention item {i}",
                   "description": f"Add 'item {i}' to README.md.", "requirements": [f"r{i}"]}
                  for i in items],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    e2e.call("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    e2e.request("POST", f"{spec}/documents/close-exploration?path={path}")
    e2e.request("POST", f"{spec}/documents/propose?path={path}")
    _, approved = e2e.request("POST", f"{spec}/documents/phase?path={path}&to=approved",
                              {"reason": "drive", "approve_anyway": True})
    return approved["tasks_created"]


def build(project, builder, task_id, instruction):
    e2e.call("PATCH", f"/projects/{project}/tasks/{task_id}", {"assignee": builder})
    run = e2e.cmd_turn(project, builder, instruction, task=task_id, fresh=True)
    if run is None:
        return False
    e2e.wait_for(run, 8)
    return True


def review(project, tester, task_id, message):
    before = len(runs_of(project, tester))
    code, body = e2e.request("POST", f"/projects/{project}/agent/trigger", {
        "agent": tester, "review_task_id": task_id, "message": message,
    })
    check(f"the review of {task_id} was dispatched", code == 200, f"{code} {str(body)[:200]}")
    wait_until(lambda: len(runs_of(project, tester)) > before and settled(project, tester), 600)


def main(project, builder="builder", tester="tester"):
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    granted = rows("select name from agents where project_id=? and can_accept_evidence=1", project)
    check("no agent holds the evidence grant", not granted, f"{granted}")
    t1, t2 = make_document(project, "agentic evidence", (1, 2))
    directory = rows("select working_directory from projects where id=?", project)[0]["working_directory"]

    # -- approve leg ------------------------------------------------------------------------------
    ok = build(project, builder, t1,
               f"Work task {t1}: append a line 'item 1' to README.md in your workspace and commit it "
               f"with git (message: item 1). Then call record_evidence once with identifier FR-1, "
               f"task_id {t1}, kind manual_observation, summary 'README mentions item 1'. Then move "
               f"task {t1} to completed. Reply DONE.")
    evidence = rows("select id, review_state from requirement_evidence where task_id=?", t1)
    status = rows("select status from tasks where id=?", t1)[0]["status"]
    check("approve leg: the builder recorded evidence and completed",
          ok and bool(evidence) and status == "completed", f"evidence={evidence} status={status}")
    if evidence and status == "completed":
        review(project, tester, t1,
               f"Review task {t1}: read README.md on the task's branch. If it mentions item 1, "
               f"approve it (update_task status approved, with notes saying what you checked). If "
               f"it does not, send it back (status revision_needed) with notes saying what is "
               f"missing. If a call is refused, end your turn and report the refusal word for word; "
               f"do not ask anyone.")
        status = rows("select status from tasks where id=?", t1)[0]["status"]
        reviews = rows("select r.decision, r.actor_kind, r.actor, r.reason from evidence_reviews r "
                       "join requirement_evidence e on e.id=r.evidence_id where e.task_id=?", t1)
        surfaced = rows("select outcome from run_divergences where task_id=? and outcome='surfaced'", t1)
        merged = rows("select outcome, commit_sha from task_integrations where task_id=? and "
                      "outcome='merged'", t1)
        readme = subprocess.run(["git", "-C", directory, "show", "master:README.md"],
                                capture_output=True, text=True).stdout
        check("approve leg: the task is approved", status == "approved", status)
        check("approve leg: the tester accepted the evidence, with a reason",
              any(r["decision"] == "accepted" and r["actor"] == tester and (r["reason"] or "").strip()
                  for r in reviews), f"{reviews}")
        check("approve leg: no evidence still awaiting",
              not rows("select id from requirement_evidence where task_id=? and review_state='awaiting'", t1))
        check("approve leg: the work merged into master", bool(merged) and "item 1" in readme,
              f"merged={merged}")
        check("approve leg: nothing surfaced to the operator", not surfaced, f"{surfaced}")

    # -- send-back leg ----------------------------------------------------------------------------
    ok = build(project, builder, t2,
               f"Work task {t2}: this is a test of review. Do NOT edit README.md. Make an empty "
               f"commit with git (git commit --allow-empty -m claim). Call record_evidence once with "
               f"identifier FR-2, task_id {t2}, kind manual_observation, summary 'README mentions "
               f"item 2'. Then move task {t2} to completed. Reply DONE.")
    evidence = rows("select id from requirement_evidence where task_id=?", t2)
    status = rows("select status from tasks where id=?", t2)[0]["status"]
    check("send-back leg: the builder recorded evidence and completed",
          ok and bool(evidence) and status == "completed", f"evidence={evidence} status={status}")
    if evidence and status == "completed":
        review(project, tester, t2,
               f"Review task {t2}: read README.md on the task's branch. If it mentions item 2, "
               f"approve it. If it does not, send it back (update_task status revision_needed) with "
               f"notes saying what is missing. If a call is refused, end your turn and report the "
               f"refusal word for word; do not ask anyone.")
        task = rows("select status, assignee from tasks where id=?", t2)[0]
        reviews = rows("select r.decision, r.actor, r.reason from evidence_reviews r join "
                       "requirement_evidence e on e.id=r.evidence_id where e.task_id=?", t2)
        check("send-back leg: the task went back to its builder",
              task["status"] == "revision_needed" and task["assignee"] == builder, f"{task}")
        check("send-back leg: the tester rejected the evidence, with a reason",
              any(r["decision"] == "rejected" and r["actor"] == tester and (r["reason"] or "").strip()
                  for r in reviews), f"{reviews}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
