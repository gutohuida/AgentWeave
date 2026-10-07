"""Close an app-authored change's Hub records once its build is committed: record operator
evidence per requirement, then walk each change task pending -> in_progress -> completed -> land.

Commit first: the evidence footprint names HEAD, and integration skips on a dirty tree. A commit
already on the main branch lands as `already integrated`; nothing is merged.

  AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/close_change.py f440 f450
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

TESTS = "hub/tests/test_a_decided_task_withdraws_its_waiting_reviews.py"
CLAIM_TESTS = "hub/tests/test_a_run_claims_only_its_agents_or_nobodys_work.py"
READ_ONLY_TESTS = "hub/tests/test_a_read_only_agent_holds_no_task_work.py"

CHANGES = {
    "f440": {
        "document": "spec/changes/a-decided-task-withdraws-its-waiting-reviews/spec.html",
        "tasks": ["task-3c0c22f24a44", "task-93f9df045c6a", "task-2035432af11f"],
        "evidence": [
            ("FR-1", "task-93f9df045c6a", "test_result", TESTS,
             "Approve, land and revision_needed withdraw the queued review entry in the move's "
             "transaction with the verdict as its reason (4 of 5 tests failed on HEAD 1dbff33..)."),
            ("FR-1", "task-2035432af11f", "manual_observation",
             "scripts/drive/d1007_verdict_withdraws_review.py",
             "Driven on :8010 with a real Haiku reviewer mid-turn: 4/8 before, 8/8 after; landing "
             "withdrew the entry and no delivery was attempted at the reviewer's run end."),
            ("FR-2", "task-93f9df045c6a", "test_result", TESTS,
             "Each withdrawal is announced as queue_entry_withdrawn naming entry, agent, task and "
             "verdict."),
            ("FR-3", "task-93f9df045c6a", "test_result", TESTS,
             "A delivered entry, another task's entry and a work entry's queued state are left "
             "unchanged by an approval."),
        ],
    },
    "f450": {
        "document": "spec/changes/a-run-claims-only-its-agents-or-nobodys-work/spec.html",
        "tasks": ["task-151291e8d5a9", "task-e13de03d6ec0", "task-c89c9d9b17d6"],
        "evidence": [
            ("FR-1", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "An unbound run's claim of another agent's task is refused 403 naming the assignee "
             "and the operator's remedy; task, assignee and binding unchanged (failed on HEAD)."),
            ("FR-1", "task-c89c9d9b17d6", "manual_observation",
             "scripts/drive/d1007_claim_boundary_drive.py",
             "Driven on :8010 with real Haiku beta: 0/3 before (beta took alpha's task to "
             "completed), 3/3 after."),
            ("FR-2", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "A run's claim of an unassigned task makes its agent the assignee in the same "
             "transaction (failed on HEAD); also driven 3/3."),
            ("FR-3", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "Own-task claim, bound run and operator move behave as before (3 control tests), and "
             "test_run_task_binding.py stays green."),
        ],
    },
    "f425": {
        "document": "spec/changes/a-read-only-agent-holds-no-task-work/spec.html",
        "tasks": ["task-e12f21e11f3b", "task-e1bf77c9375a", "task-707ba7cd531f"],
        "evidence": [
            ("FR-1", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A read-only agent's task-work turn is refused 409 before any workspace, naming the "
             "agent, task and remedy; no run; a review turn and a writing agent's turn are unchanged."),
            ("FR-1", "task-707ba7cd531f", "manual_observation",
             "scripts/drive/d1007_read_only_drive.py",
             "Driven on :8010 with real Haiku: 1/6 before (the turn wrote NOTES.md into the project "
             "checkout), 6/6 after."),
            ("FR-2", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "Create and PATCH naming a read-only assignee answer 422 (the under_review handover "
             "stays allowed); its run's claim answers 403; nothing changes."),
            ("FR-3", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A flow gives the pending task to the writing agent, both when the read-only agent is "
             "free in the pool and when it is the job's own agent."),
        ],
    },
}


def close(name: str) -> None:
    change = CHANGES[name]
    for identifier, task_id, kind, locator, summary in change["evidence"]:
        code, res = api("POST", f"/projects/{P}/project/spec/evidence", {
            "identifier": identifier, "kind": kind, "locator": locator, "summary": summary,
            "task_id": task_id, "document": change["document"],
        })
        footprint = (res.get("footprint") or {}) if isinstance(res, dict) else {}
        print(name, "evidence", identifier, task_id, code,
              footprint.get("commit_sha", "")[:12] if code == 201 else json.dumps(res)[:300])
    for task_id in change["tasks"]:
        code, task = api("GET", f"/projects/{P}/tasks/{task_id}")
        if task["status"] == "approved":
            print(name, task_id, "already approved")
            continue
        for step in ("in_progress", "completed"):
            if task["status"] == step:
                continue
            code, task = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": step})
            if code != 200:
                raise SystemExit(f"{name} {task_id} -> {step}: {code} {json.dumps(task)[:400]}")
        code, task = api("POST", f"/projects/{P}/tasks/{task_id}/land")
        print(name, task_id, "land", code, task.get("status") if code == 200 else json.dumps(task)[:400])


for arg in sys.argv[1:]:
    close(arg)
