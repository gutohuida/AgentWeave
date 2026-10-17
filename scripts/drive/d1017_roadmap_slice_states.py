"""Acceptance drive for F579 + F674: a roadmap shows which of its slices are done, and a change
document that names no slice is asked to, as a gap.

No agent turn. On the Hub `e2e.py hub-up` started (never :8000 or :8010). Exit 1 when a check fails.

  py -3.11 scripts/drive/d1017_roadmap_slice_states.py <project-id>
"""

import importlib.util
import pathlib
import re
import sys
import uuid

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def change(kind, title, roadmap=None):
    payload = {
        "schema_version": 1, "kind": kind, "title": title,
        "summary": "Drive fixture.", "problem": "Drive fixture for roadmap slice states.",
        "scope": {"in_scope": ["a file"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "r1", "statement": "The file MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the repo",
                                 "when": "listed", "then": "the file is there"}],
        "tasks": [{"key": "t1", "title": "Write it", "description": "Add it.", "requirements": ["r1"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    if roadmap:
        payload["roadmap"] = roadmap
    return payload


def write(spec, title, payload):
    doc = e2e.call("POST", f"{spec}/documents", {"title": title, "kind": payload["kind"]})
    payload["kind"] = doc["kind"]
    code, body = e2e.request("PUT", f"{spec}/documents/{doc['path']}/content", {"document": payload})
    if code != 200:
        raise SystemExit(f"write {title}: {code} {str(body)[:300]}")
    e2e.request("POST", f"{spec}/documents/close-exploration?path={doc['path']}")
    e2e.request("POST", f"{spec}/documents/propose?path={doc['path']}")
    return doc["path"]


def main(project):
    spec = f"/projects/{project}/project"
    tag = uuid.uuid4().hex[:6]
    roadmap = {
        "schema_version": 1, "kind": "roadmap", "title": f"slices {tag}",
        "summary": "Two slices.", "problem": "Drive fixture roadmap.",
        "scope": {"in_scope": ["two slices"], "non_goals": ["more"]},
        "slices": [
            {"key": "first", "title": "The first slice", "intent": "Build one thing.", "done": "It exists."},
            {"key": "second", "title": "The second slice", "intent": "Build another.", "done": "It exists too.",
             "builds_after": ["first"]},
        ],
        "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
    }
    roadmap_path = write(spec, f"slices {tag}", roadmap)
    code, body = e2e.request("POST", f"{spec}/documents/phase?path={roadmap_path}&to=approved",
                             {"reason": "drive", "approve_anyway": True})
    check("the roadmap is approved", code == 200 and body.get("phase") == "approved", f"{code} {str(body)[:200]}")

    first_path = write(spec, f"first {tag}", change("change-spec", f"first {tag}",
                                                    {"document": roadmap_path, "slice": "first"}))
    code, body = e2e.request("POST", f"{spec}/documents/phase?path={first_path}&to=approved",
                             {"reason": "drive", "approve_anyway": True})
    check("the first slice's document is approved", code == 200, f"{code} {str(body)[:200]}")

    code, page = e2e.request("GET", f"{spec}/spec?path={roadmap_path}")
    html = page.get("content", "") if isinstance(page, dict) else ""
    first = re.search(r'<li id="slice-first".*?</li>', html, flags=re.S)
    second = re.search(r'<li id="slice-second".*?</li>', html, flags=re.S)
    check("the first slice shows approved and names its document",
          bool(first) and "approved" in first.group(0) and first_path in first.group(0),
          first.group(0)[:300] if first else "no slice-first item")
    check("the second slice shows it is not started",
          bool(second) and "not started" in second.group(0),
          second.group(0)[:300] if second else "no slice-second item")

    loose_path = write(spec, f"loose {tag}", change("change-spec", f"loose {tag}"))
    code, body = e2e.request("POST", f"{spec}/documents/phase?path={loose_path}&to=approved", {"reason": "drive"})
    text = str(body)
    check("approving a document that names no slice lists the unclaimed slice as a gap",
          code == 409 and "roadmap_slice_unclaimed" in text and "second" in text, f"{code} {text[:400]}")
    code, body = e2e.request("POST", f"{spec}/documents/phase?path={loose_path}&to=approved",
                             {"reason": "drive", "approve_anyway": True})
    check("approving anyway succeeds", code == 200, f"{code} {str(body)[:200]}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        print(f"[FAIL] drive raised {exc!r}"[:300])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
