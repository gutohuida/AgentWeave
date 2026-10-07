"""Author F440's change document on the trial Hub, as the operator, and propose it.

Usage (Git Bash):
  export AW_HUB=http://127.0.0.1:8010 AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt) \
         AW_PROJECT=proj-d85a82bf4216
  MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/author_f440.py
"""

import json
import sys

sys.path.insert(0, "scripts/drive")
from aw import P, api  # noqa: E402

NAME = "a-decided-task-withdraws-its-waiting-reviews"
D = f"/projects/{P}/project"

PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "A decided task withdraws its waiting reviews",
    "summary": (
        "When a task is given a verdict (approved, rejected, or sent back with revision_needed), "
        "every review turn still queued for it is withdrawn in the same transaction and announced, "
        "instead of being delivered, refused up to three times and then given up (F440)."
    ),
    "problem": (
        "`run_task_binding._release_queued_entries_bound_to` clears `task_id` on a decided task's "
        "queued entries but keeps `review_task_id` on purpose, so a review queued for a task that is "
        "decided meanwhile stays `queued`. Its dispatch is refused (`agent_trigger`: \"not a status a "
        "review starts from\"), counted to `DELIVERY_ATTEMPT_LIMIT` (3), then withdrawn with a "
        "`queue_entry_abandoned` warning. Since `a-flow-stages-its-review-in-the-dispatch` a flow's "
        "own review waits as such an entry, so the window is wider; the refusal re-delivery was "
        "seen live on 2026-10-07 (attempts 1 -> 2 on the drive's task A). Each attempt is a refusal "
        "the operator reads as a fault, and until it is given up the entry books its reviewer."
    ),
    "scope": {
        "in_scope": [
            "Queued entries whose review_task_id names a task that reaches approved, rejected or "
            "revision_needed, on the task PATCH route and on land_task",
        ],
        "non_goals": [
            "Delivered entries (the record of a turn that happened)",
            "Work entries (task_id only), which keep today's release: task_id cleared, still queued",
            "A review queued for a task that is still reviewable or in review (in flight, D2 of the "
            "dispatch change)",
        ],
    },
    "requirements": [
        {
            "key": "withdrawn",
            "modal": "MUST",
            "statement": (
                "When a task moves to approved, rejected or revision_needed, every queued inbound "
                "entry whose review_task_id names that task MUST be withdrawn in the same "
                "transaction as the move, recording the verdict as the reason."
            ),
            "rationale": "A review of a decided task can only be refused; delivering it is noise.",
        },
        {
            "key": "announced",
            "modal": "MUST",
            "statement": (
                "Each entry withdrawn this way MUST be announced as queue_entry_withdrawn, naming "
                "the entry, its agent, the task and the verdict, so the queue the operator watches "
                "updates without a reload."
            ),
        },
        {
            "key": "untouched",
            "modal": "MUST",
            "statement": (
                "A verdict MUST NOT change a delivered entry, an entry naming another task, or a "
                "work entry's queued state."
            ),
        },
    ],
    "acceptance_criteria": [
        {
            "key": "approve",
            "requirement": "withdrawn",
            "given": "a completed task with a review entry queued for a busy reviewer",
            "when": "the operator approves the task with PATCH",
            "then": "the entry is withdrawn, carries the verdict as its reason, and no delivery is attempted",
        },
        {
            "key": "land",
            "requirement": "withdrawn",
            "given": "the same queued review entry",
            "when": "the operator lands the task",
            "then": "the entry is withdrawn in the landing's transaction",
        },
        {
            "key": "revise",
            "requirement": "withdrawn",
            "given": "a task under review with a second reviewer's review entry queued",
            "when": "the reviewer sends it back with revision_needed",
            "then": "the second entry is withdrawn",
        },
        {
            "key": "event",
            "requirement": "announced",
            "given": "a queued review entry",
            "when": "its task is approved",
            "then": "a queue_entry_withdrawn event names the entry, agent, task and verdict",
        },
        {
            "key": "others",
            "requirement": "untouched",
            "given": "a delivered review entry for the task, a queued review entry for another task, "
            "and a queued work entry for the task",
            "when": "the task is approved",
            "then": "the delivered entry and the other task's entry are unchanged; the work entry "
            "stays queued with task_id cleared, as today",
        },
        {
            "key": "drive",
            "requirement": "withdrawn",
            "given": "on the trial Hub, a review requested by hand for a reviewer mid-turn on a slow "
            "Haiku turn",
            "when": "the operator approves the task before that turn ends",
            "then": "the entry reads withdrawn with the verdict, and after the turn ends no review "
            "turn for the task starts and no refusal is recorded",
        },
    ],
    "tasks": [
        {
            "key": "tests",
            "title": "Failing tests for the verdict withdrawal",
            "description": "hub/tests/test_a_decided_task_withdraws_its_waiting_reviews.py: criteria "
            "approve, land, revise, event, others; each fails on HEAD except the controls.",
            "requirements": ["withdrawn", "announced", "untouched"],
            "files": ["hub/tests/test_a_decided_task_withdraws_its_waiting_reviews.py"],
        },
        {
            "key": "build",
            "title": "Withdraw review entries at the verdict",
            "description": "run_task_binding: withdraw_review_entries_for(session, task, verdict) — a "
            "conditional UPDATE in the caller's transaction (not _withdraw_if_queued, which commits); "
            "called from the PATCH route for the three verdicts and from land_task; events persisted "
            "with the move, broadcast after its commit.",
            "requirements": ["withdrawn", "announced", "untouched"],
            "depends_on": ["tests"],
            "files": ["hub/hub/run_task_binding.py", "hub/hub/api/v1/tasks.py"],
        },
        {
            "key": "drive",
            "title": "Acceptance drive on :8010",
            "description": "scripts/drive/d1007_verdict_withdraws_review.py, failing on the pre-fix "
            "Hub and passing after.",
            "requirements": ["withdrawn"],
            "depends_on": ["build"],
            "files": ["scripts/drive/d1007_verdict_withdraws_review.py"],
        },
    ],
    "algorithms": [],
    "design": (
        "Tier 1. Withdrawn, not merely unbound: the entry's only purpose was a review of work that "
        "is now decided, and an unbound review entry has no task to review. revision_needed is "
        "included because a review queued against the pre-revision work would be refused the same "
        "way, and the next review is staffed for the revised work. The withdrawal reuses the "
        "abandoned_reason column the refused-request path writes, so the queue route already shows it."
    ),
    "evidence": {"checked": [
        "run_task_binding._release_queued_entries_bound_to keeps review_task_id (docstring, D3 of "
        "every-run-knows-its-task)",
        "Only tasks.py's PATCH and land_task decide a review (every apply_transition caller read)",
        "inbound_queue._withdraw_if_queued commits on both branches, so it cannot run inside the move",
    ], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
    "delivery": {"mode": "none"},
}


def main():
    code, doc = api("POST", f"{D}/documents", {"title": PAYLOAD["title"], "kind": "change-spec",
                                                "path": f"spec/changes/{NAME}/spec.html"})
    print("create", code, json.dumps(doc)[:300])
    path = f"spec/changes/{NAME}/spec.html"  # 409 on a re-run: the document already exists
    code, res = api("PUT", f"{D}/documents/{path}/content", {"document": PAYLOAD})
    print("write", code, json.dumps(res)[:600])
    if code != 200:
        raise SystemExit("the content was refused; not proposing")
    code, res = api("POST", f"{D}/documents/close-exploration?path={path}")
    print("close-exploration", code, json.dumps(res)[:300])
    code, res = api("POST", f"{D}/documents/propose?path={path}")
    print("propose", code, json.dumps(res)[:600])


if __name__ == "__main__":
    main()
