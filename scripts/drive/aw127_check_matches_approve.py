"""AW-127 drive: Check lists every gap Approve lists, and the panel says them in plain words.

Starts its own Hub on :8102 with a fresh database in the system temp directory (a project cannot be
opened inside a task checkout; never :8000 or :8010). One change document at step intake whose
criterion names no check, then: Check's warning codes must cover the 409 Approve answers with, and
in Chromium the approval panel's text has no snake_case code and no /api/ path.

    py -3.11 scripts/drive/aw127_check_matches_approve.py
"""

import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
import d1012_approval_warnings as w  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8102
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = pathlib.Path(tempfile.gettempdir()) / "aw127drive" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"
PATH = "spec/changes/ping-route/spec.json"


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text("# routes go here\n", encoding="utf-8")
    d.git(root, "add", "app.py")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "aw127"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    w.make_document(base, PATH, "A ping route")
    doc = w.payload("A ping route")
    doc["acceptance_criteria"] = [{"key": "ac-1", "requirement": "answers", "given": "g",
                                   "when": "w", "then": "t"}]
    code, out = d.api("PUT", f"{base}/project/documents/{PATH}/content", {"document": doc})
    assert code == 200, (code, out)
    q = urllib.parse.quote(PATH)

    code, out = d.api("POST", f"{base}/project/documents/check?path={q}")
    check_codes = set(w.codes(out.get("warnings")))
    version = out.get("content_version")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={q}&to=approved",
                      {"reason": "drive", "content_version": version})
    body = out if isinstance(out, dict) else json.loads(out)
    listed = (body.get("detail") or {}).get("warnings")
    approve_codes = set(w.codes(listed))
    d.check("1 Check's warnings cover every gap Approve lists",
            code == 409 and "steps_skipped" in approve_codes and approve_codes <= check_codes,
            f"check={sorted(check_codes)} approve={sorted(approve_codes)} {code} {str(out)[:300]}")

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{d.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        d.poll(lambda: page.get_by_role("button", name="Check", exact=True).count() == 1, 20)
        page.get_by_role("button", name="Check", exact=True).click()
        page.wait_for_timeout(3000)
        page.screenshot(path=str(d.SHOT) + "_checked.png", full_page=True)
        found = " | ".join(page.locator(".aw-sp-finding").all_inner_texts())
        approve = page.get_by_role("button", name="Approve", exact=True)
        d.poll(lambda: approve.count() >= 1, 10)
        approve.first.click()
        page.wait_for_timeout(2000)
        page.locator("button", has_text=re.compile(r"^\s*2\s*$")).first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path=str(d.SHOT) + "_afterapprove.png", full_page=True)
        text = " | ".join(page.locator("li", has_text=re.compile("skipped steps|say how")).all_inner_texts())
        browser.close()
    plain = lambda t: "/api/" not in t and not re.search(r"[a-z]+_[a-z_]+", t)  # noqa: E731
    d.check("2a the findings Check shows inline read in plain words",
            "skipped" in found and "acceptance criterion" in found and plain(found), repr(found[:500]))
    d.check("2b the Approve panel reads in plain words",
            "acceptance criterion" in text and "skipped" in text
            and "/api/" not in text and not re.search(r"[a-z]+_[a-z_]+", text), repr(text[:400]))


d.drive = drive

if __name__ == "__main__":
    d.main()
