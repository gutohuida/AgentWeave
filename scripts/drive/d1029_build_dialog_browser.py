"""Browser drive for the Build dialog (`ac-dialog-prefill`, FR-3), 2026-10-29.

The companion of `d1029_build_plan_in_spec.py`, which drives the build route but not the dialog.
It reuses that drive's trial Hub handling (:8010, started from this checkout's `hub/` unless one
already answers), opens a scratch project with Haiku-bound agents Developer, QA, DeveloperOpus and
QA2, and approves a document whose delivery names default builder Developer and default checker QA
and whose t1 names builder DeveloperOpus and checker QA2. Then, in Chromium against the served
bundle:

  1. Build opens with Developer and QA selected as the defaults, and t1 showing DeveloperOpus and
     QA2 (t2 names nobody and shows the defaults' blanks);
  2. confirming without changes sends exactly those people to the build route;
  3. the build the Hub records carries them, labelled the operator's.

    py -3.11 scripts/drive/d1029_build_dialog_browser.py
"""

import json
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent / (d.STAMP + "-dialog")
DEFAULT_BUILDER, DEFAULT_CHECKER, T1_BUILDER, T1_CHECKER = "Developer", "QA", "DeveloperOpus", "QA2"
AGENTS = (DEFAULT_BUILDER, DEFAULT_CHECKER, T1_BUILDER, T1_CHECKER)


def payload():
    document = d.payload()
    document["tasks"][0].update(builder=T1_BUILDER, checker=T1_CHECKER)
    document["tasks"][0].pop("reviewer", None)
    document["tasks"][1].pop("builder", None)
    document["tasks"][1].pop("reviewer", None)
    document["delivery"] = dict(
        d.DELIVERY, agent=DEFAULT_BUILDER, builder=DEFAULT_BUILDER, checker=DEFAULT_CHECKER,
        builders=[DEFAULT_BUILDER],
    )
    return document


def drive(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the Build dialog drive.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open",
                          {"path": str(root), "name": f"builddialog-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(base=base)
    d.api("PATCH", base, {"main_branch": "main"})
    code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    for name in AGENTS:
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)
    quoted = urllib.parse.quote(d.DOC)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Hello file", "kind": "change-spec", "path": d.DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{d.DOC}/content", {"document": payload()})
    d.check("setup: the document saves", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    version = read.get("content_version") if isinstance(read, dict) else None
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True, "content_version": version})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    running = d.ro("select id from builds where project_id=? and state='running'", (pid,))
    d.check("setup: approval leaves no running build", not running, f"{running}", fatal=True)

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            " localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    sent = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(seed)
        page.on("request", lambda r: sent.append(r.post_data) if r.method == "POST"
                and "/project/documents/build" in r.url else None)
        page.goto(f"{d.HUB}/?project={pid}&tab=spec&document={quoted.replace('/', '%2F')}",
                  wait_until="domcontentloaded")
        try:
            page.get_by_role("button", name="Build…").first.wait_for(timeout=30000)
        except Exception:
            page.screenshot(path=str(d.TMP / "no_build_button.png"), full_page=True)
            d.check("1 the spec page offers Build", False, "see no_build_button.png", fatal=True)
        page.get_by_role("button", name="Build…").first.click()
        dialog = page.get_by_test_id("build-dialog")
        dialog.wait_for(timeout=10000)
        page.screenshot(path=str(d.TMP / "build_dialog.png"), full_page=True)

        def value(test_id):
            return page.get_by_test_id(test_id).input_value()

        shown = {k: value(k) for k in ("build-builder", "build-checker", "build-task-builder-t1",
                                       "build-task-checker-t1", "build-task-builder-t2",
                                       "build-task-checker-t2")}
        d.check("1a Developer and QA are selected as the defaults",
                shown["build-builder"] == DEFAULT_BUILDER and shown["build-checker"] == DEFAULT_CHECKER,
                f"{shown}")
        d.check("1b t1 shows DeveloperOpus and QA2",
                shown["build-task-builder-t1"] == T1_BUILDER
                and shown["build-task-checker-t1"] == T1_CHECKER, f"{shown}")
        d.check("1c t2, which names nobody, shows the defaults' blanks",
                shown["build-task-builder-t2"] == "" and shown["build-task-checker-t2"] == "",
                f"{shown}")
        page.get_by_test_id("build-confirm").click()
        page.wait_for_timeout(4000)
        page.screenshot(path=str(d.TMP / "after_confirm.png"), full_page=True)
        browser.close()

    body = json.loads(sent[0]) if sent else {}
    (d.TMP / "build_request.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    d.check("2 confirming without changes sends exactly those people",
            body.get("builder") == DEFAULT_BUILDER and body.get("checker") == DEFAULT_CHECKER
            and (body.get("task_builders") or {}).get("t1") == T1_BUILDER
            and (body.get("task_checkers") or {}).get("t1") == T1_CHECKER
            and not (body.get("task_builders") or {}).get("t2")
            and not (body.get("task_checkers") or {}).get("t2"),
            json.dumps(body))
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    build = next((b for b in (read.get("builds") or []) if b.get("state") == "running"), None)
    state.update(build_id=(build or {}).get("id"))
    d.check("3 the Hub records the build as the operator's with those people",
            bool(build) and build.get("chosen_by") == "operator"
            and build.get("builder") == DEFAULT_BUILDER and build.get("checker") == DEFAULT_CHECKER
            and (build.get("tasks") or {}).get("t1") == {"builder": T1_BUILDER, "checker": T1_CHECKER},
            json.dumps(build)[:600])


def main():
    proc = d.start_hub()
    state = {}
    d.TMP.mkdir(parents=True, exist_ok=True)
    try:
        drive(state)
    except d.Stop:
        pass
    finally:
        try:
            d.tidy(state)
        finally:
            d.stop_hub(proc)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on task-a85075abe995's branch (88c8b2c + this drive), 2026-10-29 (artefacts
# drive1029-build-plan-in-spec/212021-dialog): 15 passed, 0 failed. The dialog opens with Developer and
# QA as the defaults and t1 as DeveloperOpus/QA2, and confirming sends exactly those people. The
# spec page's approval bar for the same document still read "names no reviewer" (F1088).
