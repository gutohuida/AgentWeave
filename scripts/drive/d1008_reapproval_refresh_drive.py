"""Acceptance drive for `re-approving-an-amended-document-refreshes-its-open-tasks` (F535): 'drive'.

On `:8010`, in a fresh testbed project: an approved change with requirements `a` and `b` and tasks
`t1` (a, left open), `t2` (a, landed, so approved) and `t3` (b, left open). The operator reopens it,
retires `a`, adds `c`, retitles `t1` and points it at `b` and `c`, points `t2` at `c`, drops `t3`, and
approves again. Then `t1` keeps its id and status with the new title and links to `b` and `c` only;
`t2` and `t3` are unchanged; nothing is created; and the approval report, in Chromium on the bundle
`:8010` serves, shows `t1` refreshed, `t2` still linking the retired `a`, and `t3` no longer declared.
No agent turn is spent.

Usage: py -3.11 scripts/drive/d1008_reapproval_refresh_drive.py
"""

import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HUB = "http://127.0.0.1:8010"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-refresh"
CHANGE = "spec/changes/widgets-shine/spec.html"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{HUB}/api/v1{path}", data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def requirement(key):
    return {"key": key, "statement": f"A widget MUST {key}.", "modal": "MUST"}


def criterion(key):
    return {"key": f"{key}-c", "requirement": key, "given": "g", "when": "w", "then": "t"}


def change(requirement_keys, tasks):
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Widgets shine", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["x"], "non_goals": ["n"]},
        "requirements": [requirement(k) for k in requirement_keys],
        "acceptance_criteria": [criterion(k) for k in requirement_keys], "tasks": tasks,
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }


def approve(P, document):
    code, res = api("PUT", f"{P}/documents/{CHANGE}/content", {"document": document})
    assert code == 200, res
    api("POST", f"{P}/documents/close-exploration?path={CHANGE}")
    _, res = api("POST", f"{P}/documents/propose?path={CHANGE}")
    assert res.get("phase") == "proposed", res
    _, res = api("POST", f"{P}/documents/phase?path={CHANGE}&to=approved", {})
    assert res.get("phase") == "approved", res
    return res


def task_view(pid, task_id):
    code, res = api("GET", f"/projects/{pid}/tasks/{task_id}")
    assert code == 200, res
    links = sorted((link["identifier"], link["state"]) for link in res.get("requirement_links") or [])
    return res, links


def main():
    root = OUT / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("refresh drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}/project"
    print("project", pid, root)

    code, res = api("POST", f"{P}/documents", {"title": "Widgets shine", "kind": "change-spec", "path": CHANGE})
    assert code == 201, res
    first = approve(P, change(["a", "b"], [
        {"key": "t1", "title": "Old title", "description": "old", "requirements": ["a"]},
        {"key": "t2", "title": "Closed one", "description": "closed", "requirements": ["a"]},
        {"key": "t3", "title": "Dropped one", "description": "dropped", "requirements": ["b"]},
    ]))
    ids = {task["key"]: task["id"] for task in first["approval_outcome"]["created"]}
    for step in ("in_progress", "completed"):
        code, res = api("PATCH", f"/projects/{pid}/tasks/{ids['t2']}", {"status": step})
        assert code == 200, res
    code, res = api("POST", f"/projects/{pid}/tasks/{ids['t2']}/land")
    assert code == 200 and res["status"] == "approved", res
    t3_before, t3_links_before = task_view(pid, ids["t3"])

    code, res = api("POST", f"{P}/documents/phase?path={CHANGE}&to=exploring", {"reason": "amend"})
    assert code == 200, res
    second = approve(P, change(["b", "c"], [
        {"key": "t1", "title": "New title", "description": "new", "requirements": ["b", "c"]},
        {"key": "t2", "title": "Closed one, renamed", "description": "x", "requirements": ["c"]},
    ]))
    outcome = second.get("approval_outcome") or {}
    print(json.dumps(outcome, indent=1)[:2500])

    check("re-approval created no task", second.get("tasks_created") == [], second.get("tasks_created"))
    t1, t1_links = task_view(pid, ids["t1"])
    check("t1 has the new title", t1["title"] == "New title", t1["title"])
    check("t1 is still pending", t1["status"] == "pending", t1["status"])
    check("t1 links b and c only", t1_links == [("FR-2", "active"), ("FR-3", "active")], t1_links)
    t2, t2_links = task_view(pid, ids["t2"])
    check("t2 is unchanged, still linking the retired a",
          (t2["title"], t2["status"], t2_links) == ("Closed one", "approved", [("FR-1", "retired")]),
          (t2["title"], t2["status"], t2_links))
    t3, t3_links = task_view(pid, ids["t3"])
    check("t3 is unchanged", (t3["title"], t3["status"], t3_links) == (t3_before["title"], t3_before["status"], t3_links_before),
          (t3["title"], t3["status"], t3_links))
    refreshed = {entry.get("key") for entry in outcome.get("refreshed") or []}
    closed = {entry.get("key") for entry in outcome.get("closed_linking_retired") or []}
    undeclared = {entry.get("key") for entry in outcome.get("no_longer_declared") or []}
    check("the report lists t1 refreshed, t2 closed linking retired, t3 undeclared",
          (refreshed, closed, undeclared) == ({"t1"}, {"t2"}, {"t3"}), (refreshed, closed, undeclared))

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&document={CHANGE}", wait_until="domcontentloaded")
        page.locator('[data-testid="spec-approval-report"]').wait_for(timeout=30000)
        for testid, key in (("approval-refreshed", "t1"), ("approval-closed-retired", "t2"),
                            ("approval-no-longer-declared", "t3")):
            locator = page.locator(f'[data-testid="{testid}"]', has_text=key)
            check(f"the app's report shows {testid} for {key}", locator.count() == 1)
        page.screenshot(path=str(OUT / "report.png"))
        browser.close()

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
