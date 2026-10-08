"""Acceptance drive for `a-fold-can-retire-what-the-change-supersedes` (F533): the 'drive' criterion.

On `:8010`, in a fresh testbed project: a capability holding `old-rule` and `widgets-exist` (criteria
`widgets-exist-c`, `widgets-exist-d`), and an approved change whose one task is landed. In Chromium on
the bundle `:8010` serves, the operator folds the change and, in the same dialog, retires `old-rule`
and the criterion `widgets-exist-c`. Then the capability's file holds the folded requirement,
`widgets-exist` and `widgets-exist-d`, and neither `old-rule`, its criterion, nor `widgets-exist-c`.
No agent turn is spent.

Usage: py -3.11 scripts/drive/d1008_fold_retire_drive.py
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
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-foldretire"
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
        {"key": "old-rule", "statement": "A widget MUST never glow.", "modal": "MUST"},
    ], [
        {"key": "widgets-exist-c", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "dark"},
        {"key": "widgets-exist-d", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "t"},
        {"key": "old-rule-c", "requirement": "old-rule", "given": "g", "when": "w", "then": "never"},
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
            page.locator('[data-testid="fold-open"]').click(timeout=10000)
            page.locator('[data-testid="fold-capability"]').select_option(CAPABILITY)
            page.locator('[data-testid="fold-req-key-glow"]').wait_for(timeout=10000)
            page.locator('[data-testid="fold-retire-toggle"]').click(timeout=10000)
            page.locator('[data-testid="fold-retire-req-old-rule"]').check()
            page.locator('[data-testid="fold-retire-crit-widgets-exist-c"]').check()
            page.screenshot(path=str(OUT / "fold-retire-dialog.png"))
            page.locator('[data-testid="fold-confirm"]').click()
            page.locator('[data-testid="spec-phase"]', has_text="archived").wait_for(timeout=15000)
            check("the fold with retirements went through", True)
        except Exception as exc:  # the retire section is absent on today's Hub
            check("the retire section exists in the fold dialog", False, str(exc).splitlines()[0])
        page.screenshot(path=str(OUT / "after.png"))
        browser.close()

    text = (root / CAPABILITY).read_text(encoding="utf-8")
    for key in (FOLDED_KEY, "widgets-exist", "widgets-exist-d"):
        check(f"the capability keeps {key}", f'"key": "{key}"' in text)
    for key in ("old-rule", "old-rule-c", "widgets-exist-c"):
        check(f"the capability no longer holds {key}", f'"key": "{key}"' not in text)

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
