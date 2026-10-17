"""Acceptance drive for `evidence-carries-what-it-takes-to-judge-it` (slice evidence-worth-reading,
vis-D5): a real builder records evidence with the command it ran and its output, and the Hub returns
that output, the requirement's wording and the diff of the work.

One Haiku turn on the Hub `e2e.py hub-up` started (never :8000 or :8010). Exit 1 when a check fails.

  py -3.11 scripts/drive/d1017_evidence_worth_reading.py <project-id> [builder]
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project, builder="builder"):
    settings = e2e.call("GET", f"/projects/{project}/settings")
    settings["main_branch"] = "master"
    e2e.call("PUT", f"/projects/{project}/settings", settings)
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": "worth reading"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "worth reading",
        "summary": "A greeting script.", "problem": "Drive fixture for evidence worth reading.",
        "scope": {"in_scope": ["hello.py"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "hello.py MUST print hello world.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "hello.py",
                                 "when": "run", "then": "it prints hello world"}],
        "tasks": [{"key": "t1", "title": "Write hello.py", "description": "Print hello world.",
                   "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    e2e.call("PUT", f"{spec}/documents/{path}/content", {"document": payload})
    e2e.request("POST", f"{spec}/documents/close-exploration?path={path}")
    e2e.request("POST", f"{spec}/documents/propose?path={path}")
    _, approved = e2e.request("POST", f"{spec}/documents/phase?path={path}&to=approved",
                              {"reason": "drive", "approve_anyway": True})
    [task_id] = approved["tasks_created"]
    e2e.call("PATCH", f"/projects/{project}/tasks/{task_id}", {"assignee": builder})

    run = e2e.cmd_turn(
        project, builder,
        f"Work task {task_id}: create hello.py containing print('hello world') and commit it with "
        f"git (message: hello). Run `python hello.py`. Then call record_evidence once with "
        f"identifier FR-1, task_id {task_id}, kind test_result, summary 'hello.py prints hello "
        f"world', command 'python hello.py', output set to exactly what that command printed, and "
        f"covers 'full'. Then move task {task_id} to completed. Reply DONE.",
        task=task_id, fresh=True,
    )
    check("the builder's turn started", run is not None)
    if run is None:
        return
    e2e.wait_for(run, 8)

    code, listed = e2e.request("GET", f"{spec}/spec/evidence")
    rows = [r for r in (listed.get("evidence", []) if isinstance(listed, dict) else [])
            if r.get("task_id") == task_id]
    check("the builder recorded one piece", len(rows) == 1, f"{code} {len(rows)}")
    if not rows:
        return
    piece = rows[0]
    check("it carries the command", piece.get("command") == "python hello.py", repr(piece.get("command")))
    check("it carries the output", "hello world" in (piece.get("output") or ""), repr(piece.get("output")))
    check("it says it covers fully", piece.get("covers") == "full", repr(piece.get("covers")))
    requirement = piece.get("requirement") or {}
    check("it names the requirement's wording",
          requirement.get("identifier") == "FR-1" and "hello world" in (requirement.get("statement") or ""),
          repr(requirement))
    code, diff = e2e.request("GET", f"{spec}/spec/evidence/{piece['id']}/diff")
    files = diff.get("files", []) if isinstance(diff, dict) else []
    check("the diff shows hello.py", code == 200 and any(f.get("path") == "hello.py" for f in files),
          f"{code} {[f.get('path') for f in files]} {str(diff)[:200]}")
    check("the diff carries the added line",
          any("+print('hello world')" in (f.get("patch") or "") or '+print("hello world")' in (f.get("patch") or "")
              for f in files))


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
