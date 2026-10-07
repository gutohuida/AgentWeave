"""Drive `the-corpus-is-indexed-arranged-and-adopted-from-the-app` task 3.1 on the trial Hub `:8010`.

A fresh project under `testbed/drive1007-corpus/` holds three documents written by hand (payload
blocks, no Hub records, no `spec/index.json`). In Chromium on the served bundle: the strip says no
usable index and 3 untracked; Adopt all 3; Rebuild index asks for a home; choose one; the index is
written; Place under... a second document under the home; its page shows the parent link; placing
the home under that child is refused as a cycle. A screenshot per step goes to `<project>/shots/`.

Usage: py -3.11 scripts/drive/d1007_corpus_drive.py
"""

import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hub"))

from playwright.sync_api import sync_playwright  # noqa: E402

from hub.spec_payload import SCHEMA_VERSION, validate_payload  # noqa: E402
from hub.spec_render import render_document  # noqa: E402

HUB = "http://127.0.0.1:8010"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DOCS = {
    "spec/home.html": "Home of the corpus",
    "spec/area.html": "An area",
    "spec/notes.html": "Notes",
}
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path,
        data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def write_documents(root: pathlib.Path) -> None:
    for path, title in DOCS.items():
        stored = {
            "schema_version": SCHEMA_VERSION,
            "kind": "capability",
            "title": title,
            "summary": f"{title}, written by hand for the corpus drive.",
            "requirements": [
                {"key": "alpha", "statement": f"{title} states one requirement", "modal": "MUST"}
            ],
        }
        html = render_document(validate_payload(stored), {}, phase="current", stored_payload=stored)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8", newline="\n")


def main():
    root = REPO / "testbed/drive1007-corpus" / time.strftime("proj-%H%M%S")
    root.mkdir(parents=True)
    write_documents(root)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@example.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "."],
        ["git", "commit", "-m", "hand-written spec"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    code, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = project["id"]
    print("project", code, pid, root)
    shots = root / "shots"
    shots.mkdir()

    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&document=spec/area.html", wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="spec-document-breadcrumb"]', timeout=30000)

        def picker():
            if not page.locator('[data-testid="spec-corpus-strip"]').is_visible():
                page.click('[data-testid="spec-document-breadcrumb"]')
                page.wait_for_selector('[data-testid="spec-corpus-strip"]', timeout=10000)
            return page.locator('[data-testid="spec-corpus-strip"]')

        strip = picker()
        page.screenshot(path=str(shots / "1-strip.png"))
        check("strip says no usable index", "No usable index" in strip.inner_text())
        check(
            "strip counts 3 untracked",
            "3 documents on disk are not tracked" in strip.inner_text(),
            strip.inner_text(),
        )

        page.click('[data-testid="spec-corpus-adopt-all"]')
        page.wait_for_selector('[data-testid="spec-corpus-adopt-result"]', timeout=15000)
        page.screenshot(path=str(shots / "2-adopted.png"))
        check("adopt all 3", "Adopted 3" in strip.inner_text(), strip.inner_text())

        page.click('[data-testid="spec-corpus-rebuild"]')
        page.wait_for_selector('[data-testid="spec-corpus-home-question"]', timeout=15000)
        page.screenshot(path=str(shots / "3-home-question.png"))
        check("rebuild asks for a home", True)

        page.select_option('[data-testid="spec-corpus-home-select"]', "spec/home.html")
        page.click('[data-testid="spec-corpus-home-confirm"]')
        page.wait_for_selector('[data-testid="spec-corpus-summary"]', timeout=15000)
        page.screenshot(path=str(shots / "4-indexed.png"))
        index = json.loads((root / "spec/index.json").read_text(encoding="utf-8"))
        check(
            "index written with the chosen home",
            index.get("home") == "spec/home.html" and len(index.get("documents", [])) == 3,
            json.dumps(index)[:300],
        )

        page.keyboard.press("Escape")
        page.wait_for_selector('[data-testid="spec-place-under"]', timeout=20000)
        page.click('[data-testid="spec-place-under"]')
        page.select_option('[data-testid="spec-place-under-select"]', "spec/home.html")
        page.screenshot(path=str(shots / "5-place-under.png"))
        page.click('[data-testid="spec-place-under-confirm"]')
        page.wait_for_selector('[data-testid="spec-place-under-form"]', state="detached", timeout=15000)
        index = json.loads((root / "spec/index.json").read_text(encoding="utf-8"))
        parent = {d["path"]: d.get("parent") for d in index["documents"]}.get("spec/area.html")
        check("area placed under home", parent == "spec/home.html", str(parent))
        area_html = (root / "spec/area.html").read_text(encoding="utf-8")
        check("area's page carries its navigation", "aw-nav" in area_html)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(shots / "6-placed.png"))

        page.goto(f"{HUB}/?project={pid}&tab=spec&document=spec/home.html", wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="spec-place-under"]', timeout=30000)
        page.click('[data-testid="spec-place-under"]')
        page.select_option('[data-testid="spec-place-under-select"]', "spec/area.html")
        page.click('[data-testid="spec-place-under-confirm"]')
        page.wait_for_selector('[data-testid="spec-place-under-refusal"]', timeout=15000)
        refusal = page.locator('[data-testid="spec-place-under-refusal"]').inner_text()
        page.screenshot(path=str(shots / "7-cycle-refused.png"))
        check("cycle refused with the Hub's reason", "not allowed" in refusal, refusal)
        browser.close()

    failed = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed; shots in {shots}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
