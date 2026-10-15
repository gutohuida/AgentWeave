"""Acceptance drive for F611 (fix-D8): the operator's own edit applies at contract rigor.

Before: the operator's PUT at `contract` became a pending proposal; approve said nothing, the
approved document lacked the edit, and the proposal then went stale and vanished. After: the write
applies, records no proposal, and the approved document keeps it.

  py -3.11 scripts/drive/d1015_f611_operator_edit_applies.py <project-id>

No agent turns. Exit 1 when any check fails.
"""

import importlib.util
import json
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []
PATH = "spec/changes/gated-edit/spec.json"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def payload(criteria):
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "Gated edit",
        "summary": "A change at contract rigor.",
        "problem": "The operator edits a gated document.",
        "scope": {"in_scope": ["one thing"], "non_goals": ["anything else"]},
        "requirements": [
            {"key": "r1", "modal": "SHALL", "statement": "The thing SHALL happen."}
        ],
        "acceptance_criteria": [
            {
                "key": key,
                "requirement": "r1",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "look",
                "checked_by": "agent",
            }
            for key in criteria
        ],
        "tasks": [{"key": "t1", "title": "Do it", "requirements": ["r1"], "depends_on": []}],
        "delivery": {"mode": "none"},
    }


def criteria(project):
    """The stored file is the payload (`spec.json`), read as the Hub wrote it."""
    directory = e2e.ro().execute(
        "select working_directory from projects where id=?", (project,)
    ).fetchone()[0]
    stored = json.loads((pathlib.Path(directory) / PATH).read_text(encoding="utf-8"))
    return sorted(c["key"] for c in stored.get("acceptance_criteria", []))


def main(project):
    base = f"/projects/{project}/project/documents"
    e2e.call("POST", base, {"title": "Gated edit", "kind": "change-spec", "path": PATH})
    e2e.call("PUT", f"{base}/{PATH}/content", {"document": payload(["k1", "k2"])})
    e2e.call("POST", f"{base}/journey?path={PATH}", {"step": "delivery"})
    e2e.call("POST", f"{base}/{PATH}/rigor", {"rigor": "contract"})

    status, res = e2e.request("PUT", f"{base}/{PATH}/content", {"document": payload(["k1", "k2", "k3"])})
    check("the operator's write is accepted", status == 200, f"{status} {str(res)[:200]}")
    check("the write records no proposal", not (res or {}).get("proposals"), str((res or {}).get("proposals")))
    check("the edit is in the document", criteria(project) == ["k1", "k2", "k3"], str(criteria(project)))

    status, res = e2e.request("POST", f"{base}/propose?path={PATH}")
    check("propose answers 200", status == 200, f"{status} {str(res)[:200]}")
    status, res = e2e.request(
        "POST", f"{base}/phase?path={PATH}&to=approved", {"reason": "", "approve_anyway": True}
    )
    check("approve answers 200", status == 200, f"{status} {str(res)[:300]}")
    check("the approved document keeps the edit", criteria(project) == ["k1", "k2", "k3"],
          str(criteria(project)))
    pending = e2e.call("GET", f"{base}/{PATH}/proposals")
    rows = pending if isinstance(pending, list) else pending.get("proposals", [])
    check("nothing is left pending", rows == [], str(rows)[:200])


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
