"""Acceptance drive for `a-capability-can-be-retired` (F536): 'drive'.

On `:8010`, in a fresh testbed project: capabilities `old` (2 requirements) and `new`. The operator
opens `old` in Chromium on the bundle `:8010` serves, presses Retire, gives a reason and picks `new`
as absorbing it. Then `old` is archived, its 2 requirements are retired, the phase event names the
reason and `new`, a merge into `old` is refused, a reindex leaves its requirements retired, and
`spec/index.json` lists it as archived. No agent turn is spent.

Usage: py -3.11 scripts/drive/d1008_retire_capability_drive.py
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
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-retire"
OLD = "spec/capabilities/old/spec.html"
NEW = "spec/capabilities/new/spec.html"
REASON = "Describes nothing the product does any more."
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


def capability(title, keys):
    return {
        "schema_version": 1, "kind": "capability", "title": title, "summary": "s",
        "requirements": [{"key": k, "statement": f"A widget MUST {k}.", "modal": "MUST"} for k in keys],
        "acceptance_criteria": [
            {"key": f"{k}-c", "requirement": k, "given": "g", "when": "w", "then": "t"} for k in keys
        ],
    }


def states(pid, path):
    """Each requirement's own state (FR-1, FR-2 are old's), and whether coverage still counts any."""
    _, docs = api("GET", f"/projects/{pid}/project/documents")
    doc_id = next(d["id"] for d in docs["documents"] if d["path"] == path)
    _, cov = api("GET", f"/projects/{pid}/project/spec/coverage")
    counted = [r["state"] for r in cov["requirements"] if r["document_id"] == doc_id]
    own = []
    for identifier in ("FR-1", "FR-2"):
        _, res = api("GET", f"/projects/{pid}/project/spec/requirements/{identifier}?document={path}")
        own.append(res["requirement"]["state"] if isinstance(res, dict) else res)
    return own, counted


def main():
    root = OUT / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("retire drive\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    P = f"/projects/{pid}/project"
    print("project", pid, root)

    for path, title, keys in ((OLD, "Old", ["a", "b"]), (NEW, "New", ["c"])):
        code, res = api("POST", f"{P}/documents", {"title": title, "kind": "capability", "path": path})
        assert code == 201, res
        code, res = api("POST", f"{P}/documents/{path}/merge",
                        {"payload": capability(title, keys), "from_changes": [], "note": "seed"})
        assert code == 200, res
    code, res = api("POST", f"{P}/spec/reindex", {"home": NEW})
    assert code == 200, res
    print("old before:", states(pid, OLD))

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&document={OLD}", wait_until="domcontentloaded")
        button = page.locator('[data-testid="spec-retire-capability"]')
        try:
            button.wait_for(timeout=20000)
            offered = True
        except Exception:
            offered = False
        check("the capability's view offers Retire", offered)
        if offered:
            button.click()
            page.locator('[data-testid="retire-reason"]').fill(REASON)
            page.locator('[data-testid="retire-absorbed-by"]').select_option(NEW)
            page.locator('[data-testid="retire-confirm"]').click()
            page.locator('[data-testid="spec-retired-note"]').wait_for(timeout=20000)
        page.screenshot(path=str(root / "retired.png"))
        browser.close()

    _, docs = api("GET", f"{P}/documents")
    phase = next(d["phase"] for d in docs["documents"] if d["path"] == OLD)
    check("old is archived", phase == "archived", phase)
    check("its 2 requirements are retired and leave coverage", states(pid, OLD) == (["retired", "retired"], []), states(pid, OLD))
    _, spec = api("GET", f"{P}/spec?path={OLD}")
    last = (spec.get("retired") or {}) if isinstance(spec, dict) else {}
    check("GET /spec says why it was retired and what absorbed it (from its phase event)",
          last.get("reason") == REASON and last.get("absorbed_by") == NEW, last)
    code, res = api("POST", f"{P}/documents/{OLD}/merge",
                    {"payload": capability("Old", ["a", "b", "z"]), "from_changes": [], "note": "late"})
    check("a merge into old is refused", code == 409, (code, str(res)[:200]))
    api("POST", f"{P}/spec/reindex", {})
    check("a reindex leaves them retired", states(pid, OLD) == (["retired", "retired"], []), states(pid, OLD))
    index_file = root / "spec/index.json"
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {"documents": []}
    status = next((d.get("status") for d in index["documents"] if d["path"] == OLD), None)
    check("spec/index.json lists old as archived", status == "archived", status)
    _, specs = api("GET", f"{P}/specs")
    check("the index still reads as valid", specs["manifest"]["state"] != "invalid",
          [d["code"] for d in specs.get("diagnostics", [])])

    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {root}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
