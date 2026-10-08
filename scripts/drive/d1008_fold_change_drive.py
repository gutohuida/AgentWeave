"""Acceptance drive for `a-finished-change-is-folded-into-its-capability`: the 'drive' criterion.

On `:8010`, in a fresh testbed project: a capability document, and an approved change whose one task
is landed. In Chromium on the bundle `:8010` serves, the operator opens the change, sees it is shipped
but not in a capability, presses Fold into capability, picks the capability and confirms. Then the
capability's file carries the change's requirement under `<slug>-<key>`, one merge row names the
change, and the change is archived. No agent turn is spent.

Usage: py -3.11 scripts/drive/d1008_fold_change_drive.py
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HUB = "http://127.0.0.1:8010"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-fold"
CAPABILITY = "spec/capabilities/widgets/spec.html"
CHANGE = "spec/changes/widgets-glow/spec.html"
FOLDED_KEY = "widgets-glow-glow"
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


def payload(kind, title, requirements, criteria, tasks):
    return {
        "schema_version": 1, "kind": kind, "title": title, "summary": "s", "problem": "p",
        "scope": {"in_scope": ["x"], "non_goals": ["n"]},
        "requirements": requirements, "acceptance_criteria": criteria, "tasks": tasks,
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
        **({"delivery": {"mode": "none"}} if kind == "change-spec" else {}),
    }


def setup():
    root = OUT / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("fold drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}/project"

    code, res = api("POST", f"{P}/documents", {"title": "Widgets", "kind": "capability", "path": CAPABILITY})
    assert code == 201, res
    capability = payload("capability", "Widgets", [
        {"key": "widgets-exist", "statement": "A widget MUST exist.", "modal": "MUST"},
    ], [
        {"key": "widgets-exist-c", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "t"},
    ], [])
    # After the build a capability is written only through a merge (one naming no change is an edit);
    # today the merge refuses an empty from_changes and the direct write is the only way in.
    code, res = api("POST", f"{P}/documents/{CAPABILITY}/merge", {"payload": capability, "from_changes": []})
    if code != 200:
        code, res = api("PUT", f"{P}/documents/{CAPABILITY}/content", {"document": capability})
    assert code == 200, res

    code, res = api("POST", f"{P}/documents", {"title": "Widgets glow", "kind": "change-spec", "path": CHANGE})
    assert code == 201, res
    change = payload("change-spec", "Widgets glow", [
        {"key": "glow", "statement": "A widget MUST glow when hovered.", "modal": "MUST"},
    ], [
        {"key": "glow-c", "requirement": "glow", "given": "a widget", "when": "it is hovered", "then": "it glows"},
    ], [
        {"key": "t", "title": "Make widgets glow", "description": "d", "requirements": ["glow"]},
    ])
    code, res = api("PUT", f"{P}/documents/{CHANGE}/content", {"document": change})
    assert code == 200, res
    api("POST", f"{P}/documents/close-exploration?path={CHANGE}")
    _, res = api("POST", f"{P}/documents/propose?path={CHANGE}")
    assert res.get("phase") == "proposed", res
    _, res = api("POST", f"{P}/documents/phase?path={CHANGE}&to=approved", {})
    assert res.get("phase") == "approved", res
    (task_id,) = res["tasks_created"]
    for step in ("in_progress", "completed"):
        code, res = api("PATCH", f"/projects/{pid}/tasks/{task_id}", {"status": step})
        assert code == 200, res
    code, res = api("POST", f"/projects/{pid}/tasks/{task_id}/land")
    assert code == 200 and res["status"] == "approved", res
    return pid, root


def main():
    pid, root = setup()
    print("project", pid, root)
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&document={CHANGE}", wait_until="domcontentloaded")
        page.locator('[data-testid="spec-phase"]').wait_for(timeout=30000)
        try:
            state = page.locator('[data-testid="fold-state"]')
            state.wait_for(timeout=10000)
            check("the bar says the change is shipped but not in a capability",
                  state.get_attribute("data-state") == "ready", state.inner_text())
            page.locator('[data-testid="fold-open"]').click()
            page.locator('[data-testid="fold-capability"]').select_option(CAPABILITY)
            key = page.locator('[data-testid="fold-req-key-glow"]')
            key.wait_for(timeout=10000)
            check("the draft names the folded key", key.input_value() == FOLDED_KEY, key.input_value())
            page.screenshot(path=str(OUT / "fold-dialog.png"))
            page.locator('[data-testid="fold-confirm"]').click()
            page.locator('[data-testid="spec-phase"]', has_text="archived").wait_for(timeout=15000)
            check("the bar shows the change archived", True)
        except Exception as exc:  # the action is absent on today's Hub
            check("the fold action exists in the app", False, str(exc).splitlines()[0])
        page.screenshot(path=str(OUT / "after.png"))
        browser.close()

    text = (root / CAPABILITY).read_text(encoding="utf-8")
    check(f"the capability's file carries {FOLDED_KEY}", f'"key": "{FOLDED_KEY}"' in text)
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    merges = db.execute(
        "select count(*) from spec_document_merges m join spec_documents d on d.id = m.change_document_id"
        " where d.project_id = ? and d.path = ?", (pid, CHANGE),
    ).fetchone()[0]
    check("one merge row names the change", merges == 1, f"{merges} rows")
    phase = db.execute(
        "select phase from spec_documents where project_id = ? and path = ?", (pid, CHANGE)
    ).fetchone()[0]
    check("the change is archived", phase == "archived", phase)

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
