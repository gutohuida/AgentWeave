"""Acceptance drive for slice requirement-story of the visibility roadmap: a requirement reworded
twice answers, from its detail route, every wording it has had, who changed each, and its drift.

No agent turn: the operator rewords through the document content route, which is the path every
rewording takes through the index. Runs against the Hub `e2e.py hub-up` started (never :8000 or
:8010). Exit 1 when a check fails.

  py -3.11 scripts/drive/d1017_requirement_story.py <project-id>
"""

import importlib.util
import pathlib
import sys

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []

WORDINGS = [
    "hello.py MUST print hello world.",
    "hello.py MUST print hello world followed by a newline.",
    "hello.py MUST print 'hello, world' followed by a newline.",
]


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def payload(kind, statement):
    return {
        "schema_version": 1, "kind": kind, "title": "requirement story",
        "summary": "A greeting script.", "problem": "Drive fixture for a requirement's story.",
        "scope": {"in_scope": ["hello.py"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": statement, "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "hello.py",
                                 "when": "run", "then": "it prints the greeting"}],
        "tasks": [{"key": "t1", "title": "Write hello.py", "description": "Print the greeting.",
                   "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }


def main(project):
    spec = f"/projects/{project}/project"
    doc = e2e.call("POST", f"{spec}/documents", {"title": "requirement story"})
    path = doc["path"]
    for wording in WORDINGS:
        code, body = e2e.request("PUT", f"{spec}/documents/{path}/content",
                                 {"document": payload(doc["kind"], wording)})
        check(f"the content takes the wording {wording[:30]!r}", code == 200, f"{code} {str(body)[:200]}")

    code, detail = e2e.request("GET", f"{spec}/spec/requirements/FR-1?document={path}")
    check("the requirement's detail answers", code == 200, f"{code} {str(detail)[:200]}")
    if code != 200:
        return
    requirement = detail.get("requirement") or {}
    check("it carries the current wording", requirement.get("statement") == WORDINGS[-1],
          repr(requirement.get("statement")))
    check("it names its document", (requirement.get("document") or {}).get("path") == path,
          repr(requirement.get("document")))
    revisions = detail.get("revisions")
    check("it lists its revisions", isinstance(revisions, list), repr(revisions)[:200])
    if not isinstance(revisions, list):
        return
    check("oldest first: created, then reworded twice",
          [r.get("classification") for r in revisions] == ["created", "reworded", "reworded"],
          repr([r.get("classification") for r in revisions]))
    check("each revision carries the wording it introduced",
          [r.get("statement") for r in revisions] == WORDINGS,
          repr([r.get("statement") for r in revisions]))
    check("each names who changed it",
          all(r.get("actor_kind") == "operator" and r.get("created_at") for r in revisions),
          repr([(r.get("actor_kind"), r.get("actor")) for r in revisions]))
    stored = e2e.ro().execute(
        "select id from spec_requirement_revisions where requirement_id = ? order by created_at, id",
        (requirement.get("id"),),
    ).fetchall()
    check("the revisions match spec_requirement_revisions",
          [row[0] for row in stored] == [r.get("id") for r in revisions],
          repr([row[0] for row in stored]))
    check("it lists drift, resolved included", isinstance(detail.get("drift"), list),
          repr(detail.get("drift"))[:200])


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        raise
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
