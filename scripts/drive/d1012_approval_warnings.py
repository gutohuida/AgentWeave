"""Acceptance drive for `approve-lists-what-is-missing-and-can-approve-anyway` (approval-warnings
slice), 2026-10-09.

The slice's `drive` criterion (spec/changes/approve-lists-what-is-missing-and-can-approve-anyway/,
spdoc-9a9d313a4894). Starts its own Hub on :8101 with a fresh database (never :8000 or :8010),
serving the bundle built into hub/hub/static/ui, opens a project with two change documents, each with
a MUST requirement that has no criterion, one task and no other gap, left at step intake (size
small), and checks, in order:

  1. proposing the first answers 200 `proposed: true`, the gap under `warnings` and nothing under
     `blocking`;
  2. approving it without `approve_anyway` answers 409 `approval_warnings` naming the requirement's
     `requirement_without_criterion` and `steps_skipped`, and the document is still proposed;
  3. the same request with `approve_anyway: true` answers 200 and the document is approved;
  4. GET /project/documents carries both codes in `approval_warnings_overridden`, and the approval's
     phase event carries them as `warnings_overridden`;
  5. in Chromium the second document is proposed, Approve shows the gaps grouped by code, Approve
     anyway approves it, and the phase bar then shows what was overridden.

The contract it fixes for the build: the 409 is `{"detail": {"code": "approval_warnings",
"message": ..., "warnings": [{"code", "where", "message"}]}}`; propose answers `warnings` beside
`blocking`; the phase request body takes `approve_anyway: true`; the documents view carries
`approval_warnings_overridden` (a list of the same entries) while the document is approved; the
phase bar shows `[data-testid=approval-warnings]` with one `[data-testid=approval-warning-<code>]`
line per code, a button named "Approve anyway", and, once approved,
`[data-testid=approval-overridden]` with the same per-code lines.

Fails on today's Hub at check 1 (propose answers `blocking` requirement_without_criterion and the
document stays exploring). Stops at the first failure. No agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1012_approval_warnings.py
"""

import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8101
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-approval-warnings" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

GAP = "requirement_without_criterion"
SKIPPED = "steps_skipped"
FIRST = "spec/changes/ping-route/spec.json"
SECOND = "spec/changes/pong-route/spec.json"


def payload(title):
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "summary": f"{title}: GET answers 200 with a short body.",
        "problem": "The service has no route a caller can use to see that it is up.",
        "scope": {"in_scope": ["One route"], "non_goals": ["Authentication"]},
        "requirements": [{
            "key": "answers",
            "statement": "The route MUST answer 200 with a short body.",
            "modal": "MUST", "rationale": None, "party": None,
        }],
        "acceptance_criteria": [],
        "tasks": [{
            "key": "route", "title": "Add the route", "description": "Add it to app.py.",
            "requirements": ["answers"], "depends_on": [], "files": ["app.py"],
            "from": None, "reviewer": None,
        }],
        "algorithms": [],
        "design": "One handler.",
        "evidence": {"checked": ["app.py has no routes"], "limits": []},
        "lifecycle": "",
        "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
    }


def make_document(base, path, title):
    """Create the document with content, sized small at intake, exploration closed. Not proposed."""
    quoted = urllib.parse.quote(path)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": title, "kind": "change-spec", "path": path})
    assert code == 201, (code, out)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": payload(title)})
    assert code == 200, (code, out)
    code, out = d.api("POST", f"{base}/project/documents/journey?path={quoted}",
                      {"size": "small", "step": "intake", "reason": "drive setup"})
    assert code == 200, (code, out)
    code, out = d.api("POST", f"{base}/project/documents/close-exploration?path={quoted}")
    assert code == 200, (code, out)


def view(base, path):
    _, listed = d.api("GET", f"{base}/project/documents")
    return next((x for x in listed.get("documents", []) if x.get("path") == path), {})


def codes(items):
    return sorted({item.get("code") for item in items or [] if isinstance(item, dict)})


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service with no routes yet.\n", encoding="utf-8")
    (root / "app.py").write_text("# routes go here\n", encoding="utf-8")
    d.git(root, "add", "README.md", "app.py")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "warnings"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    make_document(base, FIRST, "A ping route")
    make_document(base, SECOND, "A pong route")
    first_q = urllib.parse.quote(FIRST)

    # 1: a gap does not stop proposal; it is listed.
    code, out = d.api("POST", f"{base}/project/documents/propose?path={first_q}")
    out = out if isinstance(out, dict) else {}
    d.check("1 propose passes the gap and lists it under warnings",
            code == 200 and out.get("proposed") is True and out.get("blocking") == []
            and GAP in codes(out.get("warnings")),
            f"{code} proposed={out.get('proposed')} blocking={codes(out.get('blocking'))} "
            f"warnings={codes(out.get('warnings'))}")

    # 2: approve says what is missing and does not move.
    phase = f"{base}/project/documents/phase?path={first_q}&to=approved"
    code, out = d.api("POST", phase, {"reason": "drive"})
    detail = out.get("detail", {}) if isinstance(out, dict) else {}
    if not detail and isinstance(out, str):
        try:
            detail = json.loads(out).get("detail", {})
        except ValueError:
            detail = {}
    listed = detail.get("warnings") if isinstance(detail, dict) else None
    gap = next((w for w in listed or [] if w.get("code") == GAP), {})
    still = view(base, FIRST)
    d.check("2 approve without approve_anyway answers 409 approval_warnings and stays proposed",
            code == 409 and detail.get("code") == "approval_warnings"
            and "answers" in str(gap.get("where", "")) + str(gap.get("message", ""))
            and SKIPPED in codes(listed) and still.get("phase") == "proposed",
            f"{code} detail={str(detail)[:300]} phase={still.get('phase')}")

    # 3: approve anyway approves.
    code, out = d.api("POST", phase, {"reason": "drive", "approve_anyway": True})
    d.check("3 approve_anyway approves", code == 200
            and view(base, FIRST).get("phase") == "approved", f"{code} {str(out)[:300]}")

    # 4: what was overridden is on the view and on the event.
    row = view(base, FIRST)
    overridden = row.get("approval_warnings_overridden")
    events = d.ro("select detail from spec_document_events where document_id=? "
                  "and detail like '%warnings_overridden%'", (row.get("id"),))
    d.check("4 the view and the approval's event carry the overridden gaps",
            {GAP, SKIPPED} <= set(codes(overridden)) and len(events) == 1
            and GAP in events[0][0],
            f"view={codes(overridden)} events={len(events)}")

    # 5: the same in the app.
    second_q = urllib.parse.quote(SECOND)
    code, out = d.api("POST", f"{base}/project/documents/propose?path={second_q}")
    assert code == 200 and out.get("proposed") is True, (code, out)
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        # The app has no document URL parameter: open the second document from the tree, as an
        # operator would (d1010's recipe).
        page.goto(f"{d.HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        target = page.locator(f'[data-testid="spec-tree-document-{SECOND}"]')
        d.poll(lambda: page.locator("[data-testid^=spec-tree-directory-]").count() > 0, 20)
        closed = page.locator("[data-testid^=spec-tree-directory-][aria-expanded=false]")
        for _ in range(6):
            if target.count() or not closed.count():
                break
            closed.first.click()
        d.poll(lambda: target.count() == 1, 10)
        if target.count() == 1:
            target.click()
        shown = d.poll(lambda: page.locator("[data-testid=spec-phase]").count() == 1
                       and page.locator("[data-testid=spec-phase]").inner_text() == "proposed", 20)
        page.screenshot(path=str(d.SHOT) + "_proposed.png", full_page=True)
        d.check("5 the second document opens in the app, proposed", shown,
                f"spec-phase elements={page.locator('[data-testid=spec-phase]').count()}")
        page.get_by_role("button", name="Approve", exact=True).click()
        warned = d.poll(lambda: page.locator("[data-testid=approval-warnings]").count() == 1, 15)
        lines = [line.get_attribute("data-testid").removeprefix("approval-warning-")
                 for line in page.locator("[data-testid^=approval-warning-]").all()]
        page.screenshot(path=str(d.SHOT) + "_warnings.png", full_page=True)
        still = view(base, SECOND)
        anyway = page.get_by_role("button", name="Approve anyway")
        d.check("5a Approve shows the gaps grouped by code and the document stays proposed",
                warned and GAP in lines and SKIPPED in lines
                and anyway.count() == 1 and still.get("phase") != "approved",
                f"lines={lines} phase={view(base, SECOND).get('phase')}")
        anyway.click()
        approved = d.poll(
            lambda: page.locator("[data-testid=spec-phase]").inner_text() == "approved", 15)
        shown = d.poll(lambda: page.locator("[data-testid=approval-overridden]").count() == 1, 15)
        kept = [line.get_attribute("data-testid").removeprefix("approval-warning-")
                for line in page.locator("[data-testid=approval-overridden] "
                                         "[data-testid^=approval-warning-]").all()]
        page.screenshot(path=str(d.SHOT) + "_overridden.png", full_page=True)
        browser.close()
    d.check("5b Approve anyway approves and the phase bar shows what was overridden",
            approved and shown and GAP in kept, f"approved={approved} overridden={kept}")


d.drive = drive

if __name__ == "__main__":
    d.main()
