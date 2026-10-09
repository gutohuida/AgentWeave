"""Acceptance drive for `a-change-is-reconciled-with-its-code-before-it-is-folded` (reconcile-and-
measure slice), 2026-10-09.

The slice's `drive` criterion (spdoc-61efd5e5f6a4 on :8010). Starts its own Hub on :8103 with a fresh
database (never :8000 or :8010). The project's app.py serves /ping and an unrequested /debug, and no
/health. One Haiku agent, rex. An approved change document requires /ping and /health. Checks:

  1. the operator asks rex to reconcile the change (POST .../documents/{path}/reconcile) -- 202;
  2. rex's turn records a reconcile result: a `missing` gap naming the /health requirement and an
     `unrequested` gap naming /debug; GET /spec's fold_state.reconcile carries it;
  3. a review send-back on the /health task and an operator defect caught `after-fold` are recorded;
     GET /project/spec/defects lists the change with a reconcile, a review and an after-fold defect;
  4. in Chromium, with both tasks decided, the phase bar shows the reconcile result, the fold dialog
     shows it, and the spec page's defects section counts the change's defects by step.

The contract it fixes for the build: operator `POST /projects/{id}/project/documents/{path}/reconcile`
`{agent}` (202, starts the turn); agent `POST /agent-actions/spec/documents/reconcile` `{path, summary,
gaps: [{class, requirement?, where, summary}]}` and MCP `record_reconcile`; `fold_state.reconcile` =
`{state: "recorded"|"none", author, run_id, at, counts: {class: n}, gaps, summary}`; operator
`POST /projects/{id}/project/documents/{path}/defects` `{summary, caught_by}`;
`GET /projects/{id}/project/spec/defects` -> `{"changes": [{document_id, path, title, defects:
[{source, caught_by, summary, at}], by_step: {step: n}}]}`; testids `reconcile-result` (phase bar and
fold dialog), `spec-defects`, `spec-defects-row` (one per change).

Fails on today's Hub at check 1. Stops at the first failure. One Haiku turn from check 2.

    py -3.11 scripts/drive/d1014_reconcile.py
"""

import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8103
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1014-reconcile" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

DOC = "spec/changes/service-routes/spec.json"
APP = '''"""A tiny HTTP service."""
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            body = b"pong"
        elif self.path == "/debug":
            body = repr(dict(self.headers)).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
'''


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Service routes",
        "summary": "The service answers /ping and /health.",
        "problem": "Callers cannot tell whether the service is up.",
        "scope": {"in_scope": ["/ping", "/health"], "non_goals": ["Authentication"]},
        "requirements": [
            {"key": "ping", "modal": "MUST", "rationale": None, "party": None,
             "statement": "GET /ping MUST answer 200 with the body pong."},
            {"key": "health", "modal": "MUST", "rationale": None, "party": None,
             "statement": "GET /health MUST answer 200 with the body ok."},
        ],
        "acceptance_criteria": [
            {"key": "ping-ok", "requirement": "ping", "given": "the service running", "when": "GET /ping",
             "then": "200 pong", "how_to_check": "curl localhost:8765/ping", "checked_by": "agent"},
            {"key": "health-ok", "requirement": "health", "given": "the service running",
             "when": "GET /health", "then": "200 ok", "how_to_check": "curl localhost:8765/health",
             "checked_by": "agent"},
        ],
        "tasks": [
            {"key": "t-ping", "title": "Serve /ping", "description": "In app.py.", "requirements": ["ping"],
             "depends_on": [], "files": ["app.py"], "from": None, "reviewer": None},
            {"key": "t-health", "title": "Serve /health", "description": "In app.py.",
             "requirements": ["health"], "depends_on": ["t-ping"], "files": ["app.py"], "from": None,
             "reviewer": None},
        ],
        "algorithms": [], "design": "One handler.", "evidence": {"checked": ["app.py"], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None, "stop_when_queue_empties": False,
                     "stop_at": None, "cron": "*/5 * * * *"},
    }


def wait_idle(pid, secs=600):
    end = time.time() + secs
    time.sleep(3)
    while time.time() < end:
        if not d.ro("select count(*) from runs where project_id=? and status='running'", (pid,))[0][0]:
            return True
        time.sleep(5)
    return False


def move(base, task_id, *statuses):
    for status in statuses:
        code, out = d.api("PATCH", f"{base}/tasks/{task_id}", {"status": status, "notes": "drive"})
        assert code == 200, (status, code, out)


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "app.py").write_text(APP, encoding="utf-8")
    (root / "README.md").write_text("# service\n", encoding="utf-8")
    d.git(root, "add", "app.py", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "service"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    code, out = d.api("POST", f"{base}/agents", {"name": "rex", "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)

    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents", {"title": "Service routes", "kind": "change-spec",
                                                           "path": DOC})
    assert code == 201, (code, out)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    assert code == 200, (code, out)
    health_id = out["identifiers"]["health"]
    d.api("POST", f"{base}/project/documents/journey?path={quoted}",
          {"size": "small", "step": "delivery", "reason": "drive setup"})
    d.api("POST", f"{base}/project/documents/close-exploration?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/propose?path={quoted}")
    assert code == 200 and out.get("proposed"), (code, out)
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True})
    assert code == 200, (code, out)
    tasks = {row[1]: row[0] for row in d.ro(
        "select id, spec_task_key from tasks where project_id=?", (pid,))}

    # 1: the operator asks rex to reconcile.
    code, out = d.api("POST", f"{base}/project/documents/{DOC}/reconcile", {"agent": "rex"})
    d.check("1 the operator asks rex to reconcile the change", code == 202, f"{code} {str(out)[:300]}")
    wait_idle(pid)

    # 2: the turn recorded the result.
    _, spec = d.api("GET", f"{base}/project/spec?path={quoted}")
    result = ((spec if isinstance(spec, dict) else {}).get("fold_state") or {}).get("reconcile") or {}
    gaps = result.get("gaps") or []
    missing = [g for g in gaps if g.get("class") == "missing"
               and (g.get("requirement") in ("health", health_id) or "health" in str(g).lower())]
    unrequested = [g for g in gaps if g.get("class") == "unrequested" and "debug" in str(g).lower()]
    d.check("2 rex records missing /health and unrequested /debug; fold_state carries it",
            result.get("state") == "recorded" and result.get("author") == "rex"
            and bool(missing) and bool(unrequested), f"{str(result)[:600]}")

    # 3: a review send-back and an operator defect; the report.
    move(base, tasks["t-health"], "in_progress", "completed", "under_review", "revision_needed")
    code, out = d.api("POST", f"{base}/project/documents/{DOC}/defects",
                      {"summary": "/health answered 500 under load in production", "caught_by": "after-fold"})
    assert code in (200, 201), (code, out)
    _, report = d.api("GET", f"{base}/project/spec/defects")
    change = next((c for c in (report or {}).get("changes", []) if c.get("path") == DOC), {})
    steps = change.get("by_step") or {}
    d.check("3 the defects report lists the change's reconcile, review and after-fold defects",
            steps.get("reconcile", 0) >= 1 and steps.get("review") == 1 and steps.get("after-fold") == 1,
            f"by_step={steps}")

    # 4: the app shows it.
    move(base, tasks["t-health"], "rejected")
    move(base, tasks["t-ping"], "rejected")
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{d.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        target = page.locator(f'[data-testid="spec-tree-document-{DOC}"]')
        d.poll(lambda: page.locator("[data-testid^=spec-tree-directory-]").count() > 0, 20)
        closed = page.locator("[data-testid^=spec-tree-directory-][aria-expanded=false]")
        for _ in range(6):
            if target.count() or not closed.count():
                break
            closed.first.click()
        d.poll(lambda: target.count() == 1, 10)
        if target.count() == 1:
            target.click()
        bar = d.poll(lambda: page.locator("[data-testid=reconcile-result]").count() >= 1, 20)
        bar_text = page.locator("[data-testid=reconcile-result]").first.inner_text() if bar else ""
        page.screenshot(path=str(d.SHOT) + "_bar.png", full_page=True)
        opened = False
        if page.locator("[data-testid=fold-open]").count():
            page.locator("[data-testid=fold-open]").click()
            opened = d.poll(lambda: page.locator("[role=dialog] [data-testid=reconcile-result]").count() == 1, 15)
        page.screenshot(path=str(d.SHOT) + "_dialog.png", full_page=True)
        if opened:
            page.keyboard.press("Escape")
        page.goto(f"{d.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        shown = d.poll(lambda: page.locator("[data-testid=spec-defects-row]").count() >= 1, 20)
        row_text = page.locator("[data-testid=spec-defects-row]").first.inner_text() if shown else ""
        page.screenshot(path=str(d.SHOT) + "_defects.png", full_page=True)
        browser.close()
    d.check("4 the phase bar and the fold dialog show the reconcile result; the spec page counts defects",
            "missing" in bar_text.lower() and opened and "reconcile" in row_text.lower()
            and "after-fold" in row_text.lower(),
            f"bar={bar_text[:200]!r} dialog={opened} row={row_text[:200]!r}")


d.drive = drive

if __name__ == "__main__":
    d.main()
