"""Live drive for `2026-08-28-a-review-started-by-hand-can-finish`, phase 4 (F76).

One authored task carries all three drives, because they are the same task in three states:

* **4.1** a review started **by hand** reaches a verdict recorded on the task, with no operator
  bookkeeping between the dispatch and the verdict — the finding itself;
* **4.2** naming the task's own author as its reviewer is refused, and nothing is spawned;
* **4.2b** dispatching a review at a task that is not awaiting one is refused, naming the status
  it is actually in. Driven against the task *after* the verdict, which is a non-reviewable status
  that already carries evidence naming a commit — the combination that makes
  `commit_for_task_review` an insufficient guard, and therefore the case worth driving.

**Waiting is outcome-based, deliberately.** The first version of this script polled
`GET /projects/{id}/runs/{run_id}`, which does not exist, so it timed out for ten minutes on a run
that had already succeeded and then reported `TIMED OUT` for a completed turn. Polling for the
state the step is *for* cannot lie that way.

**Blast radius.** Operator-side calls only, against an existing throwaway project. Refuses to run
against `proj-5e960453` (this repository) or `proj-18e5d4e0` (the operator's own drive project).

Usage:
    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-... \
    AW_REQUIREMENT=FR-1 AW_DOCUMENT=spec/changes/saffron-selkie/spec.html \
    py -3.11 scripts/drive/t_review_by_hand.py
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aw import P, api, show  # noqa: E402

FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
AUTHOR = os.environ.get("AW_AUTHOR", "builder")
REVIEWER = os.environ.get("AW_REVIEWER", "reviewer")
REQUIREMENT = os.environ.get("AW_REQUIREMENT", "FR-1")
DOCUMENT = os.environ.get("AW_DOCUMENT", "")
REUSE_TASK = os.environ.get("AW_TASK", "")

failures = []


def step(label):
    print(f"\n=== {label}", flush=True)


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}", flush=True)
    if detail:
        print(f"      {detail}", flush=True)
    if not ok:
        failures.append(label)
    return ok


def task_state(task_id):
    code, body = api("GET", f"/projects/{P}/tasks/{task_id}")
    if code != 200 or not isinstance(body, dict):
        return None, None
    return body.get("status"), body.get("assignee")


def evidence_for(task_id):
    """Evidence rows this task carries, as the operator sees them."""
    code, body = api("GET", f"/projects/{P}/project/spec/evidence")
    if code != 200:
        return []
    rows = body if isinstance(body, list) else body.get("evidence", [])
    return [r for r in rows if r.get("task_id") == task_id]


def wait_until(label, predicate, *, limit=720, every=10):
    """Poll for the outcome the step is about, never for a run id."""
    deadline = time.time() + limit
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(every)
    print(f"      (gave up waiting for {label} after {limit}s)", flush=True)
    return None


def trigger(agent, message, **extra):
    body = {"agent": agent, "message": message}
    body.update(extra)
    return api("POST", f"/projects/{P}/agent/trigger", body)


def main():
    if not P:
        raise SystemExit("Set AW_PROJECT.")
    if P in FORBIDDEN:
        raise SystemExit(f"Refusing to drive {P}: blast-radius rule.")

    code, projects = api("GET", "/projects")
    names = {p["id"]: p.get("name") for p in projects} if isinstance(projects, list) else {}
    print(f"Hub project list: {names}", flush=True)
    check("the Hub answered its project list", code == 200 and bool(names))

    step("Work to review: a completed task carrying evidence that names a commit")
    if REUSE_TASK:
        task_id = REUSE_TASK
        print(f"reusing {task_id}", flush=True)
    else:
        code, task = api(
            "POST",
            f"/projects/{P}/tasks",
            {
                "title": "F76 drive: add a REVIEWBYHAND line to review-probe.md",
                "description": (
                    "Create review-probe.md containing exactly the single line REVIEWBYHAND. "
                    "Commit it. Then move the task to completed."
                ),
                "assignee": AUTHOR,
            },
        )
        show("task created", code, task, limit=200)
        if code not in (200, 201) or not isinstance(task, dict):
            raise SystemExit("could not create the task")
        task_id = task["id"]
        trigger(AUTHOR, f"Do task {task_id}. Follow its description exactly.", task_id=task_id)
        wait_until(
            "the author to finish", lambda: task_state(task_id)[0] == "completed", limit=720
        )

    status, assignee = task_state(task_id)
    print(f"task: status={status} assignee={assignee}", flush=True)

    if not evidence_for(task_id):
        # The author's first turn committed the work and never recorded evidence -- which is a
        # known live shape (`test_a_review_needs_something_to_review.py`), not a surprise. A
        # review needs a commit to check out, so ask for the evidence explicitly.
        step("The task has no evidence yet, so ask its author to record some")
        doc = f" The document is {DOCUMENT}." if DOCUMENT else ""
        code, resp = trigger(
            AUTHOR,
            f"You already did task {task_id} and committed the work. Now record evidence for it: "
            f"call record_evidence with task_id {task_id} and requirement identifier "
            f"{REQUIREMENT}.{doc} Summarise what you changed. Do nothing else.",
        )
        show("author asked for evidence", code, resp, limit=300)
        wait_until("evidence to appear", lambda: bool(evidence_for(task_id)), limit=720)

    rows = evidence_for(task_id)
    if not check("the task carries evidence", bool(rows), f"{len(rows)} row(s)"):
        raise SystemExit("no evidence: a review has nothing to check out, so F76 cannot be driven")

    status, assignee = task_state(task_id)
    if status != "completed":
        raise SystemExit(f"the task is {status!r}, not 'completed'; the drive needs a review target")

    step("4.2 - the author is refused as its own reviewer, and nothing is spawned")
    code, refusal = trigger(AUTHOR, f"Review {task_id}.", review_task_id=task_id)
    show("author-as-reviewer", code, refusal, limit=400)
    detail = refusal.get("detail", "") if isinstance(refusal, dict) else str(refusal)
    check("refused", code in (403, 409), f"got {code}")
    check(
        "the refusal is the guard's own sentence",
        "the agent recorded as completing it" in detail,
        detail[:220],
    )
    check("the task is untouched", task_state(task_id) == (status, assignee), f"{task_state(task_id)}")

    step("4.1 - a review started BY HAND staffs the task, and the reviewer can finish it")
    code, resp = trigger(
        REVIEWER,
        f"Review task {task_id}. The work adds review-probe.md containing REVIEWBYHAND. If that "
        f"is what you find, approve it by moving the task to approved. Record your verdict "
        f"through the task itself, not in prose.",
        review_task_id=task_id,
    )
    show("reviewer dispatched by hand", code, resp, limit=400)
    if code != 200:
        raise SystemExit("the reviewer could not be dispatched")

    # This is F76, and it is true before the turn produces anything at all.
    staffed = task_state(task_id)
    check(
        "the task is staffed to the reviewer at dispatch",
        staffed[0] in ("under_review", "approved") and staffed[1] == REVIEWER,
        f"status={staffed[0]} assignee={staffed[1]}",
    )

    final = wait_until(
        "the reviewer's verdict",
        lambda: task_state(task_id)[0] in ("approved", "revision_needed", "rejected")
        and task_state(task_id),
        limit=900,
    )
    final = final or task_state(task_id)
    check(
        "the reviewer reached a verdict through the task itself",
        final[0] in ("approved", "revision_needed", "rejected"),
        f"status={final[0]} assignee={final[1]}",
    )

    step("4.2b - a task that is not awaiting review is refused, naming its actual status")
    code, refusal = trigger(REVIEWER, f"Review {task_id} again.", review_task_id=task_id)
    show("review of a decided task", code, refusal, limit=400)
    detail = refusal.get("detail", "") if isinstance(refusal, dict) else str(refusal)
    check("refused", code in (403, 409), f"got {code}")
    check("the refusal names the status", final[0] in detail, detail[:220])
    check("the task is untouched", task_state(task_id) == final, f"{task_state(task_id)}")

    print(f"\nTask driven: {task_id}", flush=True)
    print("\nALL CHECKS PASSED" if not failures else "FAILURES:", flush=True)
    for f in failures:
        print(f"  - {f}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
