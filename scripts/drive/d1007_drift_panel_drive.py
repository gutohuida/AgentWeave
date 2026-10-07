"""Drive `drift-is-scanned-and-answered-on-the-document` task 3.1 on the trial Hub `:8010`.

A git fixture, a `gate` document, operator evidence naming a file; the file changes. In Chromium on
the served bundle: Scan for drift shows the candidate; approving a linked task is refused with the
new remedy; Code corrected without reverting empties the strip, and a second tab follows without a
reload; Scan again brings the candidate back (F436); revert and scan -> nothing new. Screenshots in
`<project>/shots/`.

Usage: py -3.11 scripts/drive/d1007_drift_panel_drive.py
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
REPO = pathlib.Path(__file__).resolve().parents[2]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def git(root, *args):
    out = subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                         cwd=root, capture_output=True, text=True)
    assert out.returncode == 0, (args, out.stderr)
    return out.stdout.strip()


def commit(root, name, body, message):
    (root / name).write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", message)


def main():
    root = REPO / "testbed/drive1007-driftpanel" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    commit(root, "cart.py", "def discount(t, p):\n    return t * (1 - p / 100)\n", "seed")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}"
    api("PATCH", P, {"main_branch": "main"})

    _, doc = api("POST", f"{P}/project/documents", {"title": "drift panel"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": "drift panel", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["cart"], "non_goals": ["n"]},
        "requirements": [{"key": "pct", "statement": "cart MUST discount by percentage.", "modal": "MUST"}],
        "acceptance_criteria": [{"key": "c", "requirement": "pct", "given": "g", "when": "w", "then": "t"}],
        "tasks": [{"key": "t", "title": "verify", "description": "d", "requirements": ["pct"]}],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    _, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    identifier = res["identifiers"]["pct"]
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    api("POST", f"{P}/project/documents/propose?path={path}")
    code, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "drive"})
    task_id = res["tasks_created"][0]
    code, res = api("POST", f"{P}/project/documents/{path}/rigor", {"rigor": "gate", "reason": "drive"})
    print("rigor gate", code)
    code, ev = api("POST", f"{P}/project/spec/evidence", {
        "identifier": identifier, "summary": "discount(100, 10) == 90", "kind": "test_result",
        "locator": "cart.py", "task_id": task_id, "document": path,
    })
    print("evidence", code)
    commit(root, "cart.py", "def discount(t, p):\n    return t * (1 - p)\n", "regression")

    shots = root / "shots"
    shots.mkdir()
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    url = f"{HUB}/?project={pid}&tab=spec&document={path}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 950})
        context.add_init_script(seed)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="spec-drift-panel"]', timeout=60000)
        other = context.new_page()
        other.goto(url, wait_until="domcontentloaded")
        other.wait_for_selector('[data-testid="spec-drift-panel"]', timeout=60000)

        page.click('[data-testid="spec-drift-scan"]')
        page.wait_for_selector('[data-testid^="spec-drift-row-"]', timeout=20000)
        page.screenshot(path=str(shots / "1-candidate.png"))
        check("Scan for drift shows the candidate", page.locator('[data-testid^="spec-drift-row-"]').count() == 1)
        scanned = page.locator('[data-testid="spec-drift-scanned"]').inner_text()
        check("the scan says what it found", "1 new" in scanned and "1 on this document" in scanned, scanned)

        api("PATCH", f"{P}/tasks/{task_id}", {"status": "completed"})
        code, refused = api("POST", f"{P}/tasks/{task_id}/land")
        check("approval is refused with the new remedy", code == 409 and "the operator answers the drift candidate" in str(refused), str(refused)[:300])

        page.click('button:has-text("Code corrected")')
        page.wait_for_selector('[data-testid^="spec-drift-row-"]', state="detached", timeout=20000)
        page.screenshot(path=str(shots / "2-answered.png"))
        check("Code corrected empties the strip", page.locator('[data-testid^="spec-drift-row-"]').count() == 0)
        try:
            other.wait_for_selector('[data-testid^="spec-drift-row-"]', state="detached", timeout=20000)
            check("the second tab follows without a reload", True)
        except Exception as exc:  # noqa: BLE001
            check("the second tab follows without a reload", False, str(exc)[:120])
        other.screenshot(path=str(shots / "3-second-tab.png"))

        page.click('[data-testid="spec-drift-scan"]')
        page.wait_for_selector('[data-testid^="spec-drift-row-"]', timeout=20000)
        page.screenshot(path=str(shots / "4-asked-again.png"))
        check("the change still there is asked again (F436)", page.locator('[data-testid^="spec-drift-row-"]').count() == 1)

        page.click('button:has-text("Code corrected")')
        page.wait_for_selector('[data-testid^="spec-drift-row-"]', state="detached", timeout=20000)
        commit(root, "cart.py", "def discount(t, p):\n    return t * (1 - p / 100)\n", "revert")
        page.click('[data-testid="spec-drift-scan"]')
        page.wait_for_selector('[data-testid="spec-drift-scanned"]', timeout=20000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(shots / "5-reverted.png"))
        check("after the revert a scan raises nothing", page.locator('[data-testid^="spec-drift-row-"]').count() == 0,
              page.locator('[data-testid="spec-drift-scanned"]').inner_text())
        browser.close()

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {shots}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
