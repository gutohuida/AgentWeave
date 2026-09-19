"""F218 live drive: POST /spec/evidence's 201 must carry latest_review immediately.

record() auto-accepts operator-recorded evidence and writes the EvidenceReview row in the
same transaction record_evidence() commits, but the handler used to return the response
without ever fetching that review -- so the 201 read latest_review: null even though the
very next GET on the same row already showed it accepted. This drives that exact sequence
against a fresh throwaway Hub/project and asserts the 201 body itself, not a follow-up GET.
"""

from aw import api, show, P

code, doc = api("POST", f"/projects/{P}/project/documents", {"title": "f218 evidence review"})
show("create_document", code, doc)
path = doc["path"]

payload = {
    "schema_version": 1,
    "kind": doc["kind"],
    "title": "f218 evidence review",
    "summary": "Drive F218: operator evidence's own 201 must carry its auto-review.",
    "problem": "POST /spec/evidence omitted latest_review while its sibling decision route did not.",
    "scope": {"in_scope": ["calc.add"], "non_goals": ["anything else"]},
    "requirements": [
        {"key": "adds-correctly", "statement": "add MUST return the sum of its two arguments.", "modal": "MUST"}
    ],
    "acceptance_criteria": [
        {
            "key": "sum-check",
            "requirement": "adds-correctly",
            "given": "two integers",
            "when": "add runs",
            "then": "it returns their sum",
        }
    ],
    "tasks": [
        {
            "key": "verify-add",
            "title": "Verify add with evidence",
            "description": "Record operator evidence for adds-correctly.",
            "requirements": ["adds-correctly"],
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
    {"reason": "drive F218"},
)
show("phase->approved", code, res)
task_id = res["tasks_created"][0]

code, res = api(
    "POST",
    f"/projects/{P}/project/spec/evidence",
    {
        "identifier": "FR-1",
        "summary": "manually confirmed add(2, 3) == 5",
        "kind": "test_result",
        "task_id": task_id,
        "document": path,
    },
)
show("record_evidence (the 201 itself)", code, res)
assert code == 201, res
assert res["latest_review"] is not None, "F218: latest_review is null in the 201 response"
assert res["latest_review"]["decision"] == "accepted"
print("\nF218 PASS: the 201 already carries the auto-review, decision =", res["latest_review"]["decision"])

evidence_id = res["id"]
code, followup = api("GET", f"/projects/{P}/project/spec/evidence")
show("GET /spec/evidence (follow-up, for comparison)", code, followup)
