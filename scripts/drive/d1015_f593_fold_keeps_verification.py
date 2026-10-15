"""Acceptance drive for F593: a folded requirement keeps the verification it earned.

Before: folding a verified change listed the capability's new requirement `unserved` with no
evidence, while the archived change kept counting `verified` in the project totals. After: the
capability's requirement is `verified`, naming the change requirement as `served_by`; the project
totals count it once, and the archived change's own coverage still lists its history.

  py -3.11 scripts/drive/d1015_f593_fold_keeps_verification.py <project-id>

No agent turns: the operator records the evidence and lands the task. Exit 1 when any check fails.
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []
CHANGE = "spec/changes/subtract/spec.json"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def change_payload():
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "Subtract",
        "summary": "The calculator subtracts.",
        "problem": "It only adds.",
        "scope": {"in_scope": ["subtraction"], "non_goals": ["division"]},
        "requirements": [
            {"key": "subtract", "modal": "SHALL", "statement": "The calculator SHALL subtract B from A."}
        ],
        "acceptance_criteria": [
            {
                "key": "k1", "requirement": "subtract", "given": "A=5, B=2",
                "when": "it subtracts", "then": "it prints 3", "how_to_check": "run it",
                "checked_by": "agent",
            }
        ],
        "tasks": [{"key": "t1", "title": "Subtract", "requirements": ["subtract"], "depends_on": []}],
        "delivery": {"mode": "none"},
    }


def coverage(project, document=None):
    query = f"?document={document}" if document else ""
    return e2e.call("GET", f"/projects/{project}/project/spec/coverage{query}")


def main(project):
    base = f"/projects/{project}/project/documents"
    created = e2e.call("POST", base, {"title": "Calculator", "kind": "capability"})
    capability, capability_id = created["path"], created["id"]
    change = e2e.call("POST", base, {"title": "Subtract", "kind": "change-spec", "path": CHANGE})
    e2e.call("PUT", f"{base}/{CHANGE}/content", {"document": change_payload()})
    e2e.call("POST", f"{base}/journey?path={CHANGE}", {"step": "delivery"})
    e2e.call("POST", f"{base}/propose?path={CHANGE}")
    approved = e2e.call("POST", f"{base}/phase?path={CHANGE}&to=approved",
                        {"reason": "", "approve_anyway": True})
    task_id = (approved.get("tasks_created") or [None])[0]
    check("approval created the task", task_id is not None, str(approved.get("tasks_created")))
    e2e.call("POST", f"/projects/{project}/project/spec/evidence", {
        "identifier": "FR-1", "kind": "manual_observation", "locator": "by hand",
        "summary": "5 - 2 printed 3", "task_id": task_id, "document": CHANGE,
    })
    for step in ("in_progress", "completed"):
        e2e.call("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": step})
    status, landed = e2e.request("POST", f"/projects/{project}/tasks/{task_id}/land")
    check("the task lands", status == 200, f"{status} {str(landed)[:200]}")
    before = [r for r in coverage(project)["requirements"] if r["document_id"] == change["id"]]
    check("the change's requirement is verified", [r["state"] for r in before] == ["verified"],
          str(before))

    status, folded = e2e.request("POST", f"{base}/{CHANGE}/fold", {"into": capability})
    check("the fold archives the change", status == 200 and folded.get("phase") == "archived",
          f"{status} {str(folded)[:200]}")

    report = coverage(project)
    mine = [r for r in report["requirements"] if r["document_id"] == capability_id]
    check("the capability's folded requirement is verified",
          [r["state"] for r in mine] == ["verified"], str(mine))
    check("it names the change requirement that serves it",
          bool(mine) and (mine[0].get("served_by") or {}).get("identifier") == "FR-1",
          str(mine[0].get("served_by") if mine else None))
    check("the archived change is out of the project totals",
          not any(r["document_id"] == change["id"] for r in report["requirements"])
          and report["totals"].get("verified") == 1, str(report["totals"]))
    history = coverage(project, CHANGE)["requirements"]
    check("the archived change's own coverage still lists it",
          [r["state"] for r in history] == ["verified"], str(history))


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
