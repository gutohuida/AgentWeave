"""Acceptance drive for `the-operator-can-delete-a-document-a-task-or-an-archived-agent` (F532).

On `:8010`, in a fresh testbed project: an approved change with its task, a standalone task, and an
archived agent bound to its own runner. In Chromium on the bundle `:8010` serves, the operator deletes
the standalone task from its detail drawer and the change from its phase bar. Then, through the API,
the runner the archived agent holds is deleted. Afterwards: both tasks and the change are gone (its
file too), the runner is gone, and the archived agent is still there with no runner. No agent turn
is spent.

Usage: py -3.11 scripts/drive/d1008_delete_drive.py
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
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-delete"
CHANGE = "spec/changes/widgets-glow/spec.html"
HAIKU = "claude-haiku-4-5-20251001"
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


def setup():
    root = OUT / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("delete drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"

    _, runner = api("POST", f"{P}/runners", {"name": "Retired runner", "cli": "claude", "model": HAIKU})
    code, res = api("POST", f"{P}/agents", {"name": "retiree", "runner_id": runner["id"]})
    assert code in (200, 201), res
    code, res = api("POST", f"{P}/agents/retiree/archive", {})
    assert code == 200, res

    code, res = api("POST", f"{P}/project/documents", {"title": "Widgets glow", "path": CHANGE})
    assert code == 201, res
    change = {
        "schema_version": 1, "kind": "change-spec", "title": "Widgets glow", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["x"], "non_goals": ["n"]},
        "requirements": [{"key": "glow", "statement": "A widget MUST glow.", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "glow-c", "requirement": "glow", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t", "title": "Make widgets glow", "description": "d", "requirements": ["glow"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    code, res = api("PUT", f"{P}/project/documents/{CHANGE}/content", {"document": change})
    assert code == 200, res
    api("POST", f"{P}/project/documents/close-exploration?path={CHANGE}")
    api("POST", f"{P}/project/documents/propose?path={CHANGE}")
    _, res = api("POST", f"{P}/project/documents/phase?path={CHANGE}&to=approved", {})
    assert res.get("phase") == "approved", res
    (change_task,) = res["tasks_created"]

    code, task = api("POST", f"{P}/tasks", {"title": "A task nobody should work"})
    assert code == 201, task
    return pid, root, runner["id"], change_task, task["id"]


def main():
    pid, root, runner_id, change_task, standalone = setup()
    P = f"/projects/{pid}"
    print("project", pid, root)
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)

        page.goto(f"{HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        try:
            page.get_by_text("A task nobody should work").first.click(timeout=30000)
            page.locator(f'[data-testid="task-delete-{standalone}"]').click(timeout=10000)
            page.screenshot(path=str(OUT / "task-delete-confirm.png"))
            page.locator('[data-testid="delete-confirm"]').click(timeout=10000)
            page.get_by_text("A task nobody should work").first.wait_for(state="detached", timeout=15000)
            check("the task was deleted from its detail drawer", True)
        except Exception as exc:
            check("the task drawer offers Delete", False, str(exc).splitlines()[0])

        page.goto(f"{HUB}/?project={pid}&tab=spec&document={CHANGE}", wait_until="domcontentloaded")
        try:
            page.locator('[data-testid="spec-phase"]').wait_for(timeout=30000)
            page.locator('[data-testid="spec-delete"]').click(timeout=10000)
            page.screenshot(path=str(OUT / "document-delete-confirm.png"))
            page.locator('[data-testid="delete-confirm"]').click(timeout=10000)
            page.locator('[data-testid="spec-phase"]').wait_for(state="detached", timeout=15000)
            check("the change was deleted from its phase bar", True)
        except Exception as exc:
            check("the phase bar offers Delete", False, str(exc).splitlines()[0])
        page.screenshot(path=str(OUT / "after.png"))
        browser.close()

    code, _ = api("GET", f"{P}/tasks/{standalone}")
    check("the standalone task is gone", code == 404, str(code))
    code, _ = api("GET", f"{P}/tasks/{change_task}")
    check("the change's task went with it", code == 404, str(code))
    code, _ = api("GET", f"{P}/project/spec?path={CHANGE}")
    check("the change is gone", code == 404, str(code))
    check("the change's file is gone", not (root / CHANGE).exists())

    code, res = api("DELETE", f"{P}/runners/{runner_id}")
    check("the runner only an archived agent held deletes", code == 204, f"{code} {str(res)[:200]}")
    code, agents = api("GET", f"{P}/agents?lifecycle=all")
    retiree = [a for a in agents if a.get("name") == "retiree"] if code == 200 else []
    check("the archived agent is still there", len(retiree) == 1, str(code))
    if retiree:
        check("the archived agent no longer names the runner", not retiree[0].get("runner_id"),
              str(retiree[0].get("runner_id")))

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
