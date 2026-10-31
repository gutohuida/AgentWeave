"""Drive for F1102, 2026-10-31: a build's builders list naming only the document's checker.

Roster X and Other (Haiku), delivery {agent: X, checker: X}, build {builders: [X], builder: X,
checker: X}, as filed from QA2's drive. Before the fix the task stayed pending with no assignee and
the board said only that the queue had stalled. X must now build, Other must get nothing, and with
the work finished the firing must say that X cannot review its own work.

Starts the trial Hub on :8010 from this checkout unless one is already there.

    py -3.11 scripts/drive/d1031_builders_list_of_the_judge.py
"""

import json
import subprocess
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1031-builders-judge" / d.STAMP
DOC = "spec/changes/note-file/spec.json"
X, OTHER = "X", "Other"
LIMIT = 8 * 60


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
        "delivery": {"mode": "flow", "agent": X, "checker": X, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


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
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"judge-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        state["base"] = base
        d.api("PATCH", base, {"main_branch": "main"})
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (X, OTHER):
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
                          {"driver": "flow", "level": "reviewed", "builders": [X], "builder": X,
                           "checker": X, "landing": "main"})
        d.check("setup: built with only the checker as builder", code == 200,
                f"{code} {str(out)[:600]}", fatal=True)
        state["build_id"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
        ((task, loop),) = d.ro("select t.id, t.loop_id from tasks t join spec_documents s "
                               "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, DOC))
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0]
        print(f"project {pid} task {task} loop {loop} job {job}", flush=True)

        start = time.time()
        task_status = None
        while time.time() - start < LIMIT:
            d.fire(base, job)
            d.wait_idle(pid, 4 * 60)
            ((task_status, assignee),) = d.ro("select status, assignee from tasks where id=?", (task,))
            print(f"  {int(time.time() - start)}s {task_status} assignee={assignee}", flush=True)
            if task_status in ("completed", "under_review", "approved"):
                break
            time.sleep(10)

        built = d.handouts(task, review=False)
        d.check("F1102 X is given the work", X in built, str(built))
        d.check("F1102 Other, off the list, is given nothing", OTHER not in built, str(built))
        d.check("F1102 X finishes the work on a real turn",
                task_status in ("completed", "under_review", "approved"), str(task_status))
        branch = subprocess.run(["git", "log", f"agentweave/task/{task}", "--format=%h %s", "--", "NOTE.md"],
                                cwd=root, capture_output=True, text=True, encoding="utf-8").stdout
        d.check("F1102 the work is on the task's branch", bool(branch.strip()), branch)

        d.fire(base, job)
        time.sleep(8)
        _, board = d.api("GET", f"{base}/loops/{loop}")
        said = json.dumps(board)
        log = (d.TMP / "hub.log").read_text(encoding="utf-8", errors="replace") if hub else ""
        print(f"  the loop reads: {said[:1500]}", flush=True)
        d.check("F1102 the stalled review names X as the reviewer it cannot use",
                f"'{X}' as its reviewer" in said or f"'{X}' as its reviewer" in log, said[:600])
    except d.Stop:
        pass
    finally:
        if state.get("build_id"):
            print("stopping the build:",
                  d.api("POST", f"{state['base']}/project/builds/{state['build_id']}/stop")[0])
        d.stop_hub(hub)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on 51e7bc4 plus this fix, 2026-10-31: 13/13, X built on a real Haiku turn in 45s, Other got
# nothing, and the loop's stall_reason named X. The branch check then was vacuous (d.git returns None);
# it was read by hand (see FINDINGS F1102) and this version asks git directly.
