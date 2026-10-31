"""Drive for F1103, F1110 and the done rule, 2026-10-31, on real Haiku turns and a real browser.

The repository's main is red: `tests/test_red.py` fails on main, and the project's check runs pytest.
A Reviewed flow build of one task, whose document names C to check and whose dialog names B as both
builder and checker.

  F1103      C builds, because the build's record says B checks; B then reviews
  F1110      the check's failure is listed on the build as only caught, with the fix task the Hub
             filed for it; the page shows it
  done rule  the spec reads done once the task's work is on main, whatever the fix task is doing
  landing    a Hub-filed fix task is really reviewed and landed after the build finished, and the
             flow ends only then

Starts the trial Hub on :8010 from this checkout unless one is already there.

    py -3.11 scripts/drive/d1031b_done_means_landed.py
"""

import subprocess
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

d.TMP = d.TMP.parent.parent / "drive1031b-done-means-landed" / d.STAMP
DOC = "spec/changes/note-file/spec.json"
B, C, F = "B", "C", "F"
LIMIT = 25 * 60
RED = "tests/test_red.py"


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Note file",
        "summary": "One file.", "problem": "There is no note.",
        "scope": {"in_scope": ["NOTE.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "note", "modal": "MUST", "statement": "NOTE.md MUST exist."}],
        "acceptance_criteria": [{
            "key": "exists", "requirement": "note", "given": "the repository", "when": "listed",
            "then": "NOTE.md is there", "how_to_check": "ls", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Write the note", "requirements": ["note"],
                   "description": "Create NOTE.md holding the single line `note`, then move this "
                                  "task to completed. Change nothing else.",
                   "files": ["NOTE.md"]}],
        "delivery": {"mode": "flow", "agent": B, "checker": C, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def status_of(task):
    return d.ro("select status, assignee from tasks where id=?", (task,))[0]


def main():
    hub = d.start_hub()
    root = d.TMP / "proj"
    state = {}
    try:
        (root / "tests").mkdir(parents=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
        (root / RED).write_text("def test_red():\n    assert False\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"done-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        d.api("PATCH", base, {"main_branch": "main"})
        code, out = d.api("PUT", f"{base}/settings", {"checks": [{
            "name": "tests", "command": f'"{sys.executable}" -m pytest -q tests', "timeout_seconds": 120}]})
        d.check("setup: the check", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (B, C, F):
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
                          {"driver": "flow", "level": "reviewed", "builder": B, "checker": B,
                           "landing": "main"})
        d.check("setup: built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        state.update(base=base)
        build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
        ((own, loop),) = d.ro("select t.id, t.loop_id from tasks t join spec_documents s "
                              "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, DOC))
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0]
        print(f"project {pid} own {own} loop {loop} job {job} root {root}", flush=True)

        def fix_ids():
            return [r[0] for r in d.ro(
                "select id from tasks where project_id=? and id<>?", (pid, own))]

        def shown():
            _, documents = d.api("GET", f"{base}/project/documents")
            return next(x for x in documents["documents"] if x["path"] == DOC)["display_phase"]

        start = time.time()
        phases = []
        waited_to_land = False
        while time.time() - start < LIMIT:
            d.fire(base, job)
            for _ in range(int(4 * 60 / 3)):
                _, card = d.api("GET", f"{base}/tasks/{own}")
                waited_to_land = waited_to_land or bool(card.get("waiting_to_land"))
                if not d.runs_busy(pid):
                    break
                time.sleep(3)
            rows = {t: status_of(t) for t in (own, *fix_ids())}
            phase = shown()
            phases.append(phase)
            build_state = d.ro("select state from builds where id=?", (build_id,))[0][0]
            print(f"  {int(time.time() - start)}s {build_state} {phase} {rows}", flush=True)
            ended = d.ro("select ending_state from loops where id=?", (loop,))[0][0]
            if ended:
                break
            time.sleep(5)

        d.check("F1103 C, the document's checker, built", C in d.handouts(own, review=False),
                str(d.handouts(own, review=False)))
        d.check("F1103 B, not C, reviewed", d.handouts(own, review=True)[:1] == [B],
                str(d.handouts(own, review=True)))
        d.check("own task approved", status_of(own)[0] == "approved", str(status_of(own)))
        on_main = subprocess.run(["git", "show", "main:NOTE.md"], cwd=root, capture_output=True,
                                 text=True).stdout
        d.check("its work is on main", "note" in on_main, on_main)
        print(f"  saw waiting_to_land on the card: {waited_to_land}", flush=True)

        _, spec = d.api("GET", f"{base}/project/spec?path={quoted}")
        (build,) = spec["builds"]
        caught = build.get("caught") or []
        d.check("F1110 the failure is on the build", any("test_red" in str(c.get("test")) for c in caught),
                str(caught)[:500])
        row = next((c for c in caught if "test_red" in str(c.get("test"))), {})
        d.check("F1110 it reads only caught", row.get("origin") == "caught", str(row))
        d.check("F1110 it names the fix task", bool(row.get("fix_task")), str(row))
        fixes = fix_ids()
        # From the record: a build and its fix task can both close between two of this drive's reads.
        stopped = d.ro("select stopped_at from builds where id=?", (build_id,))[0][0]
        closed = [d.ro("select max(created_at) from task_transitions where task_id=? and "
                       "to_status in ('approved', 'rejected')", (t,))[0][0] for t in fixes]
        d.check("the fix task outlived the finished build", bool(closed) and all(
            c and c > stopped for c in closed), f"build {stopped}, fix {closed}, shown {phases}")
        d.check("the Hub filed a fix task", bool(fixes), str(fixes))
        d.check("the spec reads done", shown() == "done", shown())
        for task in fixes:
            d.check(f"fix task {task} was really reviewed",
                    bool(d.handouts(task, review=True)), str(status_of(task)))
            d.check(f"fix task {task} closed", status_of(task)[0] in ("approved", "rejected"),
                    str(status_of(task)))
        d.check("the flow ended once its queue drained",
                bool(d.ro("select ending_state from loops where id=?", (loop,))[0][0]))

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
            page.goto(f"{d.HUB}/?project={pid}&tab=spec&spec={quoted}", wait_until="domcontentloaded")
            try:
                list_ = page.get_by_test_id("build-caught")
                list_.first.wait_for(timeout=30000)
                d.check("F1110 the page shows it", "test_red" in list_.first.inner_text(),
                        list_.first.inner_text()[:300])
            except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
                d.check("F1110 the page shows it", False, str(exc)[:300])
            page.screenshot(path=str(d.TMP / "caught.png"), full_page=True)
            d.check("no page errors", not errors, str(errors[:3]))
            browser.close()
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

# Observed 2026-10-31 on agentweave/Architect, 24/25 with the check above still reading its status
# between polls: C built and B reviewed; the build finished at 22:31:42, the Hub's fix task was approved
# at 22:31:56 and both landed at 22:32:44, the spec reading building until then and done after; the page
# listed the failure as only caught with its fix task. waiting_to_land was seen on the card's route.
