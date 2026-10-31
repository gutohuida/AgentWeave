"""Drive for F1113, F1112 and F1114, 2026-10-31, on real Haiku turns and a real browser.

A flow build of one task, built by B. Two fix tasks stand in the Hub's own (the flow's loop, no
build, critical): one free to start, one that waits for the build's task so it is still open when
the build finishes. F = a free agent on the builders list; C = the reviewer.

  F1112  the free fix task goes to F, not to B who holds the build's work
  F1113  the build reads finished with a fix task open, its flow goes on, a real turn does that
         task, and the flow ends only when its queue has drained
  F1114  in a browser, a task held by B is given to F; the page says what started, F's real turn
         does it, and a second reassign during that turn is refused on the page

Starts the trial Hub on :8010 from this checkout unless one is already there.

    py -3.11 scripts/drive/d1031_a_flow_keeps_and_spreads_its_work.py
"""

import subprocess
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

d.TMP = d.TMP.parent.parent / "drive1031-keeps-and-spreads" / d.STAMP
DOC = "spec/changes/note-file/spec.json"
B, F, C = "B", "F", "C"
LIMIT = 15 * 60


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Note file",
        "summary": "One file.", "problem": "There is no note.",
        "scope": {"in_scope": ["NOTE.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "note", "modal": "MUST", "statement": "NOTE.md MUST exist."}],
        "acceptance_criteria": [{
            "key": "exists", "requirement": "note", "given": "the repository", "when": "listed",
            "then": "NOTE.md is there", "how_to_check": "ls", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Write the note", "requirements": ["note"], "builder": B,
                   "description": "Create NOTE.md holding the single line `note`, then move this "
                                  "task to completed. Change nothing else.",
                   "files": ["NOTE.md"]}],
        "delivery": {"mode": "flow", "agent": B, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def fix_body(name, loop, **more):
    return {"title": f"Write {name}", "priority": "critical", "loop_id": loop,
            "description": f"Create {name} holding the single line `fixed`, then move this task "
                           "to completed. Change nothing else.", **more}


def status_of(task):
    return d.ro("select status, assignee from tasks where id=?", (task,))[0]


def own_closed(task):
    return status_of(task)[0] == "approved"


def browser_check(pid, base, task):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(
            f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, "
            f"hubUrl: {d.HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {pid!r});"
        )
        page.goto(f"{d.HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        page.get_by_test_id(f"task-open-{task}").click(timeout=30000)
        details = page.get_by_role("button", name="Details")
        if details.count():
            details.first.click()
        page.get_by_test_id(f"task-reassign-menu-{task}").click(timeout=15000)
        page.get_by_test_id(f"task-reassign-menu-{task}-{F}").click()
        said = page.get_by_test_id(f"task-next-turn-{task}")
        said.wait_for(timeout=20000)
        text = said.inner_text()
        d.check("F1114 the page says what the reassign started", F in text, text)
        d.check("F1114 the Hub holds the new holder", status_of(task)[1] == F, str(status_of(task)))

        started = d.poll(lambda: d.ro(
            "select 1 from runs where task_id=? and agent=? and status='running'", (task, F)), 90, 0.25)
        d.check("F1114 F's real turn starts", bool(started))
        if started:
            page.get_by_test_id(f"task-reassign-menu-{task}").click(timeout=15000)
            page.get_by_test_id(f"task-reassign-menu-{task}-{B}").click()
            refused = page.get_by_text("is executing on it").first
            try:
                refused.wait_for(timeout=15000)
                d.check("F1114 a live run refuses, in the page", True)
            except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
                d.check("F1114 a live run refuses, in the page", False, str(exc)[:300])
            d.check("F1114 the refusal moved nothing", status_of(task)[1] == F, str(status_of(task)))
        page.screenshot(path=str(d.TMP / "reassign.png"))
        d.check("F1114 no page errors", not errors, str(errors[:3]))
        browser.close()


def main():
    hub = d.start_hub()
    root = d.TMP / "proj"
    state = {}
    try:
        root.mkdir(parents=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"keeps-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        d.api("PATCH", base, {"main_branch": "main"})
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (B, F, C):
            code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
            d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

        quoted = urllib.parse.quote(DOC)
        code, out = d.api("POST", f"{base}/project/documents",
                          {"title": "Note file", "kind": "change-spec", "path": DOC})
        d.check("setup: document created", code == 201, f"{code} {out}", fatal=True)
        code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
        d.check("setup: document saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                          {"reason": "drive", "approve_anyway": True,
                           "content_version": read.get("content_version")})
        d.check("setup: document approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                          {"driver": "flow", "level": "fast", "builders": [B, F, C], "landing": "main"})
        d.check("setup: built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        state.update(base=base, build_id=((out.get("build_outcome") or {}).get("build") or {}).get("id"))
        ((own, loop),) = d.ro("select t.id, t.loop_id from tasks t join spec_documents s "
                              "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, DOC))
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0]
        code, free_fix = d.api("POST", f"{base}/tasks", fix_body("FIX_A.md", loop))
        d.check("setup: the free fix task", code in (200, 201), f"{code} {free_fix}", fatal=True)
        code, late_fix = d.api("POST", f"{base}/tasks", fix_body("FIX_B.md", loop, depends_on=[own]))
        d.check("setup: the fix task that outlives the build", code in (200, 201),
                f"{code} {late_fix}", fatal=True)
        free_fix, late_fix = free_fix["id"], late_fix["id"]
        print(f"project {pid} own {own} fixes {free_fix} {late_fix} loop {loop} job {job}", flush=True)

        start = time.time()
        finished_with_fix_open = False
        flow_alive_then = False
        tasks = (own, free_fix, late_fix)
        done = {}
        while time.time() - start < LIMIT:
            d.fire(base, job)
            d.wait_idle(pid, 4 * 60)
            rows = {t: status_of(t) for t in tasks}
            print(f"  {int(time.time() - start)}s {rows}", flush=True)
            build_state = d.ro("select state from builds where id=?", (state["build_id"],))[0][0]
            if build_state == "finished" and not done.get(late_fix) and not finished_with_fix_open:
                finished_with_fix_open = True
                flow_alive_then = d.ro("select ending_state from loops where id=?", (loop,))[0][0] is None
            # A task made through the API lacks what the Hub's own fix task carries to be reviewed
            # without evidence, and reviews are not this drive's subject: once a real turn has
            # finished one, the operator closes it, which is what drains the queue.
            for task, (status, _) in rows.items():
                if status == "completed" and task != own:
                    d.api("PATCH", f"{base}/tasks/{task}", {"status": "rejected"})
                    done[task] = True
            if own_closed(own) and all(done.get(t) for t in (free_fix, late_fix)):
                break
            time.sleep(5)

        given = d.handouts(free_fix, review=False)
        d.check("F1112 the free fix task went to a free agent, not the builder",
                bool(given) and B not in given, str(given))
        d.check("F1112 the builder kept its own work", B in d.handouts(own, review=False),
                str(d.handouts(own, review=False)))
        d.check("F1113 the build finished with a fix task open", finished_with_fix_open)
        d.check("F1113 the flow stayed alive then", flow_alive_then)
        d.check("F1113 a real turn did the fix task after the build finished",
                done.get(late_fix) and subprocess.run(
                    ["git", "log", "--all", "--format=%h", "--", "FIX_B.md"], cwd=root,
                    capture_output=True, text=True).stdout.strip() != "",
                str(status_of(late_fix)))
        code, said = d.api("POST", f"{base}/jobs/{job}/run")
        d.check("F1113 pressing Run on the drained flow is not an error", code != 500, f"{code} {said}")
        ended = d.poll(lambda: d.ro("select ending_state from loops where id=?", (loop,))[0][0] == "completed", 30)
        d.check("F1113 the flow ended once its queue drained", bool(ended),
                str(d.ro("select ending_state from loops where id=?", (loop,))))

        code, held = d.api("POST", f"{base}/tasks", {
            "title": "Write MOVED.md", "assignee": B,
            "description": "Run a command that takes about 20 seconds (for example `sleep 20`), then "
                           "create MOVED.md holding the line `moved`, then move this task to completed."})
        d.check("setup: a task held by B", code in (200, 201), f"{code} {held}", fatal=True)
        browser_check(pid, base, held["id"])
        d.wait_idle(pid, 4 * 60)
        d.check("F1114 F's real turn did the work", status_of(held["id"])[0] in ("completed", "under_review", "approved"),
                str(status_of(held["id"])))
    except d.Stop:
        pass
    finally:
        d.stop_hub(hub)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed 2026-10-31 on agentweave/Architect: 26/26. The fix task went to C and B kept its own work; the
# build finished at its last approval and a real turn did the outliving fix task after it; F's real
# turn did the reassigned task, and a second reassign during it was refused on the page. Fix tasks are
# closed by the operator here, so their review and landing are not exercised.
