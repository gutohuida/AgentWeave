"""Acceptance drive for `drift-watches-the-files-its-evidence-is-about` (F427, F217), on `:8010`.

Run **before** the build (task 0.5: it must fail in the defect's direction) and after it (3.1).

Leg 1 (F427): operator evidence naming `cart.py`, accepted; a commit to `other.py` only.
  Today: a drift candidate (the footprint watches the whole tree). After: nothing.
  Control: a commit to `cart.py` raises exactly one candidate, both before and after.
Leg 2 (F217): operator evidence naming a commit on a feature branch (`cart.py` changed there),
  accepted; the branch is merged into `main` with --no-ff; detect once; then `cart.py` changes on
  `main`. Today: nothing (compared against the feature branch, which did not move). After: one.

Usage: py -3.11 scripts/drive/d1007_drift_watch_drive.py
"""

import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010/api/v1"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
REPO = pathlib.Path(__file__).resolve().parents[2]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path, data, {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def git(root, *args):
    result = subprocess.run(
        ["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def commit(root, name, body, message):
    (root / name).write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def approved_document(P, key):
    _, doc = api("POST", f"{P}/project/documents", {"title": f"drift watch {key}"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": f"drift watch {key}",
        "summary": "s", "problem": "p", "scope": {"in_scope": ["cart"], "non_goals": ["n"]},
        "requirements": [{"key": key, "statement": "cart MUST discount by percentage.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": key, "given": "g", "when": "w", "then": "t"}],
        "tasks": [{"key": "t", "title": "verify", "description": "d", "requirements": [key]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    code, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    assert code == 200, ("content", code, res)
    identifier = res["identifiers"][key]
    for step in ("close-exploration", "propose"):
        code, res = api("POST", f"{P}/project/documents/{step}?path={path}")
        assert code == 200, (step, code, res)
    code, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "drive"})
    assert code == 200, ("approve", code, res)
    return path, identifier, res["tasks_created"][0]


def evidence(P, path, identifier, task_id, locator):
    code, ev = api("POST", f"{P}/project/spec/evidence", {
        "identifier": identifier, "summary": "verified", "kind": "test_result",
        "locator": locator, "task_id": task_id, "document": path,
    })
    assert code == 201, ev
    api("POST", f"{P}/project/spec/evidence/{ev['id']}/decision", {"decision": "accepted", "reason": "drive"})
    return ev


def detect(P):
    code, res = api("POST", f"{P}/project/spec/drift/detect")
    assert code == 200, res
    return res.get("raised", [])


def main():
    root = REPO / "testbed/drive1007-driftwatch" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    commit(root, "cart.py", "def discount(t, p):\n    return t * (1 - p / 100)\n", "seed cart")
    commit(root, "other.py", "x = 1\n", "seed other")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    P = f"/projects/{project['id']}"
    api("PATCH", f"/projects/{project['id']}", {"main_branch": "main"})

    # Leg 1 -- F427.
    path, identifier, task_id = approved_document(P, "leg-one")
    ev = evidence(P, path, identifier, task_id, "cart.py")
    print("leg 1 footprint:", json.dumps(ev.get("footprint"))[:300])
    detect(P)
    commit(root, "other.py", "x = 2\n", "unrelated change")
    raised = detect(P)
    check("leg 1: a commit to a file the evidence is not about raises nothing", raised == [], f"raised {raised}")
    commit(root, "cart.py", "def discount(t, p):\n    return t * (1 - p / 100.0)\n", "the watched file")
    raised = detect(P)
    check("leg 1 control: a commit to cart.py raises a candidate", len(raised) >= 1, f"raised {raised}")

    # Leg 2 -- F217.
    path2, identifier2, task2 = approved_document(P, "leg-two")
    git(root, "checkout", "-q", "-b", "feature/discount")
    fix = commit(root, "cart.py", "def discount(t, p):\n    return round(t * (1 - p / 100.0), 2)\n", "fix on branch")
    ev2 = evidence(P, path2, identifier2, task2, fix)
    print("leg 2 footprint:", json.dumps(ev2.get("footprint"))[:300])
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "merge feature", "feature/discount")
    detect(P)
    commit(root, "cart.py", "def discount(t, p):\n    return t\n", "regression on main")
    raised = detect(P)
    check("leg 2 (F217): a change on main to merged work raises a candidate", len(raised) >= 1, f"raised {raised}")

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; project {root}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
