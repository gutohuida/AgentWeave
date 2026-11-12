"""Acceptance drive for `the-side-panel-s-running-tab-builds-loops-and-jobs-and-what-needs-me`
(SPSRT-3), 2026-11-12 -- part 1: the scenario.

A scratch git repository opened as a new project on the trial Hub :8010 (started from this checkout
by `d1029_build_plan_in_spec.start_hub` if none answers), with four Haiku agents, and in it:

  flow      "Two notes"        a flow build at Reviewed, t2 after t1, Builder building, Checker checking
  question  "Ask first"        a flow build whose one task tells Asker to call ask_user (blocking) first
  lead      "Lead notes"       a lead-driven build (lead: Lead)
  done      "Finished notes"   a hand build whose one task the operator approves, so the build finishes
  early     "Stopped notes"    a hand build the operator stops
  loop      "Stalled loop"     a plain loop whose only task waits on a task nobody will do
  job       "Monday digest"    a scheduled job, on, Mondays 09:00
  paused    "Paused digest"    the same, off

Flow jobs are on a never-firing cron and are fired by hand (`d1112_running_fire.py`), so the drive
decides when an agent takes a task. Writes the ids to `testbed/running-drive/state.json`.

    py -3.11 scripts/drive/d1112_running_setup.py
"""

import json
import pathlib
import sys
import tempfile
import time
import urllib.parse

import d1029_build_plan_in_spec as d

OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "running-drive"
ROOT = pathlib.Path(tempfile.gettempdir()) / "drive1112-running" / d.STAMP / "proj"
NEVER = "0 0 1 1 *"
AGENTS = ("Builder", "Checker", "Asker", "Lead")


def doc(title, tasks):
    reqs = [t["key"] for t in tasks]
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}: notes in the repository.", "problem": "The repository has no notes.",
        "scope": {"in_scope": [t["files"][0] for t in tasks], "non_goals": ["Anything else"]},
        "requirements": [{"key": k, "modal": "MUST", "statement": f"The repository MUST hold {k}.md."}
                         for k in reqs],
        "acceptance_criteria": [{
            "key": f"has-{k}", "requirement": k, "given": "the repository", "when": "listed",
            "then": f"{k}.md is there", "how_to_check": "ls", "checked_by": "agent"} for k in reqs],
        "tasks": tasks,
        "delivery": {"mode": "flow", "agent": "Builder", "checker": "Checker",
                     "stop_when_queue_empties": True, "cron": NEVER,
                     "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def note(key, title, builder, after=(), first=""):
    return {
        "key": key, "title": title, "requirements": [key], "files": [f"{key}.md"],
        "description": (first + f"Create {key}.md at the repository root holding the single line "
                        f"`{key}`, record evidence for the requirement, then move this task to "
                        "completed. Change nothing else."),
        "builder": builder, "reviewer": "Checker", "depends_on": list(after),
    }


DOCS = {
    "flow": ("spec/changes/two-notes/spec.json", "Two notes",
             [note("alpha", "Write the alpha note", "Builder"),
              note("beta", "Write the beta note", "Builder", after=["alpha"])]),
    "question": ("spec/changes/ask-first/spec.json", "Ask first",
                 [note("gamma", "Ask, then write the gamma note", "Asker", first=(
                     "Before anything else, call the ask_user tool once, blocking, with the single "
                     "question \"Should the gamma note be written in lower case?\" (header \"Case\", "
                     "options \"Lower\" and \"Upper\"), and wait for the answer. Then: "))]),
    "lead": ("spec/changes/lead-notes/spec.json", "Lead notes",
             [note("delta", "Write the delta note", "Lead")]),
    "done": ("spec/changes/finished-notes/spec.json", "Finished notes",
             [note("epsilon", "Write the epsilon note", "Builder")]),
    "early": ("spec/changes/stopped-notes/spec.json", "Stopped notes",
              [note("zeta", "Write the zeta note", "Builder")]),
}

BUILDS = {
    "flow": {"driver": "flow", "level": "reviewed", "builders": ["Builder"], "checker": "Checker",
             "landing": "main"},
    "question": {"driver": "flow", "level": "reviewed", "builders": ["Asker"], "checker": "Checker",
                 "landing": "main"},
    "lead": {"driver": "lead", "lead": "Lead", "level": "reviewed", "builders": ["Lead"],
             "checker": "Checker", "landing": "main"},
    "done": {"driver": "hand", "level": "fast", "landing": "nowhere"},
    "early": {"driver": "hand", "level": "fast", "landing": "nowhere"},
}


def main():
    hub = d.start_hub()
    print("hub process started here:", hub.pid if hub else None)
    OUT.mkdir(parents=True, exist_ok=True)
    ROOT.mkdir(parents=True)
    d.git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "README.md").write_text("Scratch.\n", encoding="utf-8")
    d.git(ROOT, "add", ".")
    d.git(ROOT, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(ROOT), "name": f"running-{d.STAMP}"})
    d.check("project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    d.check("Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    for name in AGENTS:
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        d.check(f"agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    state = {"pid": pid, "base": base, "root": str(ROOT), "builds": {}, "jobs": {}}
    for key, (path, title, tasks) in DOCS.items():
        quoted = urllib.parse.quote(path)
        code, out = d.api("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec", "path": path})
        d.check(f"{key}: document created", code == 201, f"{code} {out}", fatal=True)
        code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": doc(title, tasks)})
        d.check(f"{key}: document saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                          {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
        d.check(f"{key}: approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}", BUILDS[key])
        d.check(f"{key}: built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        build = ((out.get("build_outcome") or {}).get("build") or {})
        rows = d.ro("select t.id, t.loop_id, t.title from tasks t join spec_documents s on t.spec_document_id=s.id "
                    "where s.project_id=? and s.path=? order by t.created_at", (pid, path))
        loop = rows[0][1] if rows else None
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0] if loop else None
        state["builds"][key] = {"id": build.get("id"), "path": path, "title": title,
                                "tasks": [r[0] for r in rows], "loop": loop, "job": job}
        print(f"  {key}: build {build.get('id')} loop {loop} job {job} tasks {[r[0] for r in rows]}")

    # The finished build: the operator approves its one task. The stopped one: the operator stops it.
    for task in state["builds"]["done"]["tasks"]:
        code, out = d.api("PATCH", f"{base}/tasks/{task}", {"status": "approved", "notes": "drive"})
        d.check("done: its task approved", code == 200, f"{code} {str(out)[:400]}")
    code, out = d.api("POST", f"{base}/project/builds/{state['builds']['early']['id']}/stop")
    d.check("early: stopped", code == 200, f"{code} {str(out)[:400]}")

    # A plain loop that would stall: its one task depends on a task outside it that nobody does.
    code, blocker = d.api("POST", f"{base}/tasks", {
        "title": "Decide the note format", "description": "Nobody will do this in the drive.",
        "priority": "low"})
    d.check("stall: the prerequisite task", code in (200, 201), f"{code} {str(blocker)[:300]}")
    code, out = d.api("POST", f"{base}/jobs", {
        "name": "Stalled loop", "agent": "Builder", "message": "Work the queue.", "cron": NEVER,
        "purpose": "Write notes once the format is decided.", "stop_when_queue_empties": True,
        "initial_tasks": [{"title": "Write the eta note", "description": "Create eta.md.",
                           "depends_on": [blocker.get("id")]}]})
    d.check("stall: the loop", code == 201, f"{code} {str(out)[:400]}")
    state["jobs"]["loop"] = out.get("id")
    for key, name, enabled in (("job", "Monday digest", True), ("paused", "Paused digest", False)):
        code, out = d.api("POST", f"{base}/jobs", {
            "name": name, "agent": "Lead", "message": "Summarise the week.", "cron": "0 9 * * 1",
            "enabled": enabled})
        d.check(f"{key}: the job", code == 201, f"{code} {str(out)[:300]}")
        state["jobs"][key] = out.get("id")

    (OUT / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    _, builds = d.api("GET", f"{base}/project/builds")
    for b in builds.get("builds", []):
        print(f"  build {b['document_title']!r}: {b['state']} {b['driver']} {b['tasks_done']}/{b['tasks_total']}"
              f" q={b['open_questions']} stopped_at={b['stopped_at']}")
    _, loops = d.api("GET", f"{base}/loops?include_archived=true")
    for lp in loops if isinstance(loops, list) else []:
        print(f"  loop {lp.get('label')!r}: stall={lp.get('stall_reason')!r} doc={lp.get('spec_document_id')}")
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed; state in {OUT / 'state.json'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    time.sleep(0)
    main()
