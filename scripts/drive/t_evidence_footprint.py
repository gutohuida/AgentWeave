"""T-EVIDENCE-FOOTPRINT: drive Q6's unreached evidence -> review path (Q7, iteration 11).

Builds a spec document + requirement + task from scratch in proj-bad259c0c9f2 (the Q6 fresh
project), records operator evidence naming a real fix commit that lives on an agent's branch
(agentweave/flowreviewer, commit bd03e4d3), and shows that the footprint actually captured names
a different commit entirely -- the operator's own checkout HEAD, still on the pre-fix seed commit.
See F71 in FINDINGS.md for the full account; this is the reproduction, kept for a future session
to re-run against the same rows (task-7f49caae3c6d, evidence ev-9d22a691db10) without re-deriving
the steps from a diff.
"""

from aw import api, show

P = "proj-bad259c0c9f2"

# 1. A document, a requirement, an acceptance criterion, a task -- the minimum that clears every
#    `blocking` gate `write_content` raises (no_requirements, non_goals_empty,
#    requirement_without_criterion, requirement_without_task).
code, doc = api("POST", f"/projects/{P}/project/documents", {"title": "cart evidence chain"})
show("create_document", code, doc)
path = doc["path"]

payload = {
    "schema_version": 1,
    "kind": doc["kind"],
    "title": "cart evidence chain",
    "summary": "Verify the evidence -> review -> approval -> integration chain end to end.",
    "problem": "Q6 never reached verdict/approval/integration; this document exists only to test that path.",
    "scope": {
        "in_scope": ["cart.py discount rounding"],
        "non_goals": ["Anything beyond apply_percent_discount"],
    },
    "requirements": [
        {
            "key": "discount-rounds-safely",
            "statement": "apply_percent_discount MUST NOT use float equality to detect a zero discount.",
            "modal": "MUST",
        }
    ],
    "acceptance_criteria": [
        {
            "key": "no-float-eq",
            "requirement": "discount-rounds-safely",
            "given": "a percent discount close to but not exactly zero due to float representation",
            "when": "apply_percent_discount runs",
            "then": "it does not silently no-op via float == 0.0",
        }
    ],
    "tasks": [
        {
            "key": "verify-discount-fix",
            "title": "Verify the discount float-equality fix with evidence",
            "description": "Confirm apply_percent_discount's float==0.0 fix and record evidence naming the commit.",
            "requirements": ["discount-rounds-safely"],
        }
    ],
    "algorithms": [],
    "design": "",
    "evidence": {"checked": [], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
}
code, res = api("PUT", f"/projects/{P}/project/documents/{path}/content", {"document": payload})
show("write_content", code, res)

code, res = api("POST", f"/projects/{P}/project/documents/close-exploration?path={path}")
show("close-exploration", code, res)
code, res = api("POST", f"/projects/{P}/project/documents/propose?path={path}")
show("propose", code, res)
code, res = api(
    "POST",
    f"/projects/{P}/project/documents/phase?path={path}&to=approved",
    {"reason": "operator drive, testing verdict/approval/integration chain"},
)
show("phase->approved", code, res)
task_id = res["tasks_created"][0]

# 2. Move the task through to under_review, reassigned to the reviewer -- deliberately NOT F70's
#    shortcut (this PATCH sequence reassigns; F70's did not).
code, res = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"assignee": "flowauthor", "status": "in_progress"})
show("assign+in_progress", code, res["status"] if code == 200 else res)

# 3. Record evidence naming the real fix commit (on agentweave/flowreviewer, not yet on master).
SHA = "bd03e4d3eec894c82159e51ed01ed3dc874287a0"
code, res = api(
    "POST",
    f"/projects/{P}/project/spec/evidence",
    {
        "identifier": "FR-1",
        "summary": "apply_percent_discount now uses math.isclose instead of float ==.",
        "kind": "test_result",
        "locator": SHA,
        "task_id": task_id,
        "document": path,
    },
)
show("record_evidence (footprint always null in THIS response -- see F71's second finding)", code, res)

code, res = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": "completed"})
code, res = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": "under_review", "assignee": "flowreviewer"})
show("under_review+reassign", code, res["status"] if code == 200 else res)

print()
print("Now compare what was recorded against what a review turn would actually be handed:")
print("  sqlite3 -readonly <db> \"select commit_sha, branch, reachable_from_main from")
print("    evidence_footprints where evidence_id='<the id above>'\"")
print("  -- expected (F71): commit_sha=052632357... (the pre-fix SEED commit), NOT", SHA)
print()
print("Or, exactly what a review turn's own wiring calls:")
print("  from hub.requirement_evidence import commit_for_task_review")
print(f"  await commit_for_task_review(session, {task_id!r})")
