"""Acceptance drive for the Running tab (SPSRT-3), part 5: FR-9 ac-live's progress half.

A two-task flow build ("Pair", Fast, landing nowhere; theta and iota2, independent (a chain would make theta the acceptance drive), both Builder's) in
the drive's project. Page A shows Running (All) and is never reloaded once the watch starts. The
drive fires the flow; once theta is done (approved by the operator through the API if the flow has
not approved it within a few minutes), it fires again so Builder takes iota2, and checks that page A's
row now reads 1/2 tasks with Builder on the second task.

    py -3.11 scripts/drive/d1112_running_progress.py
"""

import json
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d
import d1112_running_look as look
import d1112_running_setup as setup
from playwright.sync_api import sync_playwright

LIMIT = 20 * 60
PATH = f"spec/changes/pair-{time.strftime('%H%M')}/spec.json"
TITLE = f"Pair {time.strftime('%H%M')}"


def stamp(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def main():
    state = json.loads((look.OUT / "state.json").read_text(encoding="utf-8"))
    base, pid = state["base"], state["pid"]
    tasks = [setup.note("theta", "Write the theta note", "Builder"),
             setup.note("iota2", "Write the second note", "Builder")]
    quoted = urllib.parse.quote(PATH)
    d.api("POST", f"{base}/project/documents", {"title": TITLE, "kind": "change-spec", "path": PATH})
    d.api("PUT", f"{base}/project/documents/{PATH}/content", {"document": setup.doc(TITLE, tasks)})
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
          {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "fast", "builders": ["Builder"], "checker": "Checker",
                       "landing": "nowhere"})
    d.check("pair: built", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    rows = d.ro("select t.id, t.loop_id from tasks t join spec_documents s on t.spec_document_id=s.id "
                "where s.project_id=? and s.path=? order by t.created_at", (pid, PATH))
    first = [r[0] for r in rows if r[0]]
    theta = d.ro("select id from tasks where id in (%s) and title='Write the theta note'" % ",".join("?" * len(first)), tuple(first))[0][0]
    job = d.ro("select job_id from loops where id=?", (rows[0][1],))[0][0]

    def status(task):
        return d.ro("select status from tasks where id=?", (task,))[0][0]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        a = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        a.on("pageerror", lambda e: errors.append(str(e)))
        look.open_narrow(a, state, "dark")
        a.get_by_role("radio", name="All").first.click()
        loads = a.evaluate("performance.getEntriesByType('navigation').length")
        seen = [None]

        def watch():
            text = look.row_text(a, TITLE) if hasattr(look, "row_text") else None
            if text is None:
                text = a.evaluate(
                    "(t) => { for (const li of document.querySelectorAll('[data-testid=running-tab] li.aw-run-item')) {"
                    " if (li.querySelector('.aw-run-title')?.textContent === t) return li.dataset.phase + ' | ' + li.innerText.replace(/\\n/g, ' / '); }"
                    " return null }", TITLE)
            if text != seen[0]:
                seen[0] = text
                stamp(text)
            return text or ""

        watch()
        d.poll(lambda: not d.runs_busy(pid), 300, every=3)
        d.fire(base, job)
        start = time.time()
        theta_done_at = None
        last_fire = time.time()
        while time.time() - start < LIMIT:
            row = watch()
            if status(theta) == "approved" and theta_done_at is None:
                theta_done_at = time.time()
                stamp("theta approved")
            if theta_done_at is None and status(theta) == "completed" and time.time() - start > 240:
                code, out = d.api("PATCH", f"{base}/tasks/{theta}", {"status": "approved", "notes": "drive"})
                stamp(f"operator approves theta: {code} {str(out)[:160]}")
            if "1/2" in row and "Write the second note" in row and ("building" in row or "next on" in row):
                a.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "live-next-task.png"))
                d.check("ac-live: the row reads 1/2 with Builder on the next task, on page A without a reload",
                        a.evaluate("performance.getEntriesByType('navigation').length") == loads, row)
                break
            if time.time() - last_fire > 40 and not d.runs_busy(pid):
                d.fire(base, job)
                last_fire = time.time()
            time.sleep(2)
        else:
            d.check("ac-live: the row moved to the next task within the limit", False, seen[0] or "")
        d.check("no page errors on page A", not errors, str(errors[:3]))
        browser.close()
    code, out = d.api("POST", f"{base}/project/builds/{out_build(base, PATH)}/stop")
    stamp(f"pair build stopped: {code}")
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


def out_build(base, path):
    _, builds = d.api("GET", f"{base}/project/builds")
    return next(b["id"] for b in builds["builds"] if b["document_title"] == TITLE)


if __name__ == "__main__":
    main()
