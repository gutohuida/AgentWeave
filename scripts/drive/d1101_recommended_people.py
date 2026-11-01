"""Acceptance drive for `every-task-comes-with-a-recommended-builder-and-checker` (FR-12, ac-drive).

Drives the trial Hub on :8010 (reusing one that answers, else starting one from this checkout's
`hub/`), never :8000. A scratch git project, a Haiku runner, and a roster of four agents:

  Author  -- writes the spec        Strong -- the "Opus" of the roster (named so, rebound to Haiku
  Cheap   -- the "Sonnet"                    before any build turn, so every turn is Haiku)
  Checker -- reviews and files the follow-up

Steps (each records its checks and the drive goes on, so one run on master shows every failure):

  A  Authoring. A real Haiku author is asked for a large spec with one hazardous (migration) and
     one routine (copy change) task. It must ask how to judge the models (A1); the drive answers
     'review the project record' and the author must read the per-model record (A2: a tool call
     naming the record, or its figures in the document's evidence, FR-13/FR-14). The submitted
     document gives every task a builder and checker (A3), a reason for each pick (A4), a checker
     that is not the builder (A5), and the two tasks different builders (A6).
  B  Build dialog, in Chromium. It opens with each task's picks selected (B1), their reasons
     visible beside the row (B2), and building as-is records exactly those picks (B3).
  C  The build runs as a flow at Reviewed until it finishes (C1); the drive then ages its end 30
     days back, as the fixture, so the warning has an age to name.
  D  Follow-up. The Checker files a task against the spec through the agent plane. It joins the
     finished build, which reopens under the same id, level and landing (D1), shows the reopening
     (D2), takes the build's people (D3), and the spec stops reading as done (D4). Firing the
     build's flow at most twice then starts the task with no other call (D5).
  E  Overview, in Chromium. The warning names the spec, the task, the filer and 30 days (E1);
     stopping from it stops the build (E2) and its flow starts nothing further (E3).

On master it fails at A1-A6 (no tool reads the record; the author submits no tasks, so the drive
seeds a document with picks and no reasons), B2 (no reasons shown), D1-D5 (the follow-up joins
nothing: no reopening, no assignee, the spec reads done, no flow starts it) and E1/E2.
The author may rename the document, so its path is re-read by id after every author turn.

Selectors the build is to provide (the Overview and Build dialog test ids, named here so the
follow-ups task and this drive agree): `build-task-reason-<task key>` beside each Build row,
`reopening-warning` on the Overview with `reopening-warning-stop` inside it. A task's reasons are
read from any `*reason*` key on the task that sits beside `builder` / `checker` (for example
`builder_reason`, `checker_reason`).

    py -3.11 scripts/drive/d1101_recommended_people.py
"""

import json
import re
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1101-recommended-people" / d.STAMP
AUTHOR, STRONG, CHEAP, CHECKER = "Author", "Strong", "Cheap", "Checker"
DOC_TITLE = "Notes and schema"
REQUEST = (
    "Write a LARGE (not fix-size) change spec for this project: two tasks. One is hazardous: a "
    "database migration adding a `notes` table (treat it as a migration with a rollback). The "
    "other is routine: change the wording of one sentence in README.md. Keep the real work tiny "
    "(each task only creates or edits one text file, as a scratch drive). Details, so you need not "
    "interview me: the `notes` table has columns id (integer primary key), body (text, not null) "
    "and created_at (timestamp); the migration is a single SQL file SCHEMA.md-style stand-in "
    "named SCHEMA.md. The README sentence 'This project keeps notes.' becomes 'This project keeps "
    "short notes for the team.' The motivation is that the team has nowhere to keep notes. None of "
    "this is built yet. Only the model choice is open, and I will answer that when you ask. "
    "The roster is "
    f"{AUTHOR} (you), {STRONG}, {CHEAP} and {CHECKER}. Follow the writing steps, go as far as "
    "submitting the document with a builder, checker and reason on every task."
)
ANSWER = (
    "Judge the models by reviewing this project's record only (not the web, not just what you "
    "know). Read it with your tool, state the sample sizes, then continue and submit the tasks."
)
TURN = 8 * 60
BUILD_LIMIT = 30 * 60


def turn(base, message, path):
    code, run = d.api("POST", f"{base}/agent/trigger",
                      {"agent": AUTHOR, "message": message, "spec_document": path})
    d.check("setup: the author turn starts", code in (200, 202), f"{code} {run}", fatal=True)
    run_id = run["run_id"]
    d.poll(lambda: d.ro("select status from runs where id=?", (run_id,))[0][0]
           not in ("running", "queued", "starting"), TURN, 3)
    return run_id


def reply(run_id):
    return "\n".join(c for (c,) in d.ro(
        "select content from agent_outputs where run_id=? and kind='text' order by sequence",
        (run_id,)))


def payload_of(root, path):
    """The document as the Hub holds it: the route's `content` is the rendered page, the payload
    is the file."""
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def current(base, doc_id):
    """The document's path and displayed phase now, by id: the author may have renamed it."""
    _, listed = d.api("GET", f"{base}/project/documents")
    for view in (listed or {}).get("documents") or []:
        if view.get("id") == doc_id:
            return view.get("path"), view.get("display_phase")
    return None, None


def tasks_of(root, path):
    return [t for t in payload_of(root, path).get("tasks") or [] if isinstance(t, dict)]


def reasons(task, who):
    return [v for k, v in task.items() if "reason" in k.lower() and who in k.lower()
            and isinstance(v, str) and v.strip()]


def seeded():
    def task(key, title, text, file, builder):
        return {"key": key, "title": title, "requirements": [key], "files": [file],
                "description": f"Create {file} holding the single line `{text}`, then move this "
                               "task to completed. Change nothing else.",
                "builder": builder, "checker": CHECKER}
    return {
        "schema_version": 1, "kind": "change-spec", "title": DOC_TITLE,
        "summary": "A notes table and a wording change.", "problem": "There are no notes.",
        "scope": {"in_scope": ["notes"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": "schema", "modal": "MUST", "statement": "SCHEMA.md MUST exist."},
            {"key": "copy", "modal": "MUST", "statement": "COPY.md MUST exist."}],
        "acceptance_criteria": [{
            "key": f"has-{k}", "requirement": k, "given": "the repository", "when": "listed",
            "then": "the file is there", "how_to_check": "ls", "checked_by": "agent"}
            for k in ("schema", "copy")],
        "tasks": [task("schema", "Add the notes table (migration)", "schema", "SCHEMA.md", STRONG),
                  task("copy", "Reword a sentence", "copy", "COPY.md", CHEAP)],
        "delivery": {"mode": "flow", "agent": STRONG, "builder": STRONG, "checker": CHECKER,
                     "builders": [STRONG, CHEAP], "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def build_of(pid, doc):
    return d.ro("select b.id, b.state, b.level, b.landing, b.stopped_at from builds b "
                "join spec_documents s on b.document_id=s.id "
                "where s.project_id=? and s.path=? order by b.created_at desc", (pid, doc))


def seed(pid):
    return ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            " localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))


def drive(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# Scratch\n\nThis project keeps notes.\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"people-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(base=base)
    d.api("PATCH", base, {"main_branch": "main"})
    _, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    _, opus = d.api("POST", f"{base}/runners", {"name": "Opus (named only)", "cli": "claude",
                                                 "model": "claude-opus-5-5"})
    _, sonnet = d.api("POST", f"{base}/runners", {"name": "Sonnet (named only)", "cli": "claude",
                                                   "model": "claude-sonnet-5-5"})
    for name, runner in ((AUTHOR, haiku), (STRONG, opus), (CHEAP, sonnet), (CHECKER, haiku)):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    # ---- A: authoring -------------------------------------------------------------------
    code, doc = d.api("POST", f"{base}/project/documents", {"kind": "change-spec"})
    d.check("setup: an exploring document", code == 201, f"{code} {doc}", fatal=True)
    doc_id = doc["id"]
    path = doc["path"]

    def author_turn(message):
        """One author turn; the path is re-read by id after it, as the author may have renamed."""
        nonlocal path
        run_id = turn(base, message, path)
        path = current(base, doc_id)[0] or path
        return run_id

    first = author_turn(REQUEST)
    said = reply(first)
    (d.TMP / "author-turn1.txt").write_text(said, encoding="utf-8")
    asks = re.search(r"web|search", said, re.I) and re.search(r"record|project'?s", said, re.I) \
        and "?" in said
    d.check("A1 the author asks which sources to judge the models by", bool(asks), said[:400])
    # The models are named to the author: Opus and Sonnet from the roster.
    d.check("A1b the author was told the roster's models", "opus" in said.lower() or
            "opus" in json.dumps(d.ro("select content from agent_outputs where run_id=?", (first,))).lower(),
            said[:200])

    second = author_turn(ANSWER)
    runs = [first, second]
    for nudge in range(3):
        if len(tasks_of(root, path)) >= 2:
            break
        runs.append(author_turn("Continue to the tasks step and submit the document with both "
                                "tasks, each with builder, checker and a reason for each."))
    quoted = urllib.parse.quote(path)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    written = payload_of(root, path)
    (d.TMP / "document.json").write_text(json.dumps(written, indent=1, default=str), encoding="utf-8")
    marks = "','".join(runs)
    touched = d.ro(f"select content from agent_outputs where run_id in ('{marks}') "
                   "and kind in ('tool_use','tool_call') ") or []
    blob = " ".join(c for (c,) in touched).lower()
    evidence = json.dumps(written.get("evidence"), default=str).lower()
    d.check("A2 the author read the per-model record (a tool call, with its figures in evidence)",
            bool(re.search(r"model[_ -]?record|per[_ -]?model|work[_ -]?tally", blob))
            and re.search(r"sample|n=|\b\d+ tasks?\b", evidence) is not None,
            f"calls={blob[:300]} evidence={evidence[:300]}")
    tasks = tasks_of(root, path)
    d.check("A3 every task names a builder and a checker",
            len(tasks) >= 2 and all(t.get("builder") and t.get("checker") for t in tasks),
            json.dumps(tasks, default=str)[:600])
    d.check("A4 every pick carries a reason",
            len(tasks) >= 2 and all(reasons(t, "builder") and reasons(t, "checker") for t in tasks),
            json.dumps(tasks, default=str)[:600])
    d.check("A5 no task's checker is its builder",
            all(t.get("builder") != t.get("checker") for t in tasks) and bool(tasks),
            json.dumps([(t.get("builder"), t.get("checker")) for t in tasks]))
    d.check("A6 the two tasks hold different builders",
            len({t.get("builder") for t in tasks}) >= 2,
            json.dumps([t.get("builder") for t in tasks]))
    if len(tasks) < 2:
        # The author did not get to a document with tasks (always so on master): seed one, with
        # picks and no reasons, so Build, the follow-up and Overview are driven and fail, if they
        # do, for their own reasons rather than all at once here.
        code, out = d.api("PUT", f"{base}/project/documents/{path}/content",
                          {"document": seeded()})
        d.check("setup: the author's document did not stand; a seeded one is saved instead",
                code == 200, f"{code} {str(out)[:400]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        tasks = tasks_of(root, path)
        d.check("setup: the seeded document holds two tasks", len(tasks) == 2, fatal=True)
    state["tasks"] = tasks

    # The "Opus" of the roster is rebound to Haiku: every build turn is Haiku.
    d.api("PATCH", f"{base}/agents/{STRONG}", {"runner_id": haiku["id"]})
    d.api("PATCH", f"{base}/agents/{CHEAP}", {"runner_id": haiku["id"]})
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:400]}", fatal=True)

    # ---- B: the Build dialog ------------------------------------------------------------
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(seed(pid))
        sent = []
        page.on("request", lambda r: sent.append(r.post_data) if r.method == "POST"
                and "/project/documents/build" in r.url else None)
        page.goto(f"{d.HUB}/?project={pid}&tab=spec&document={quoted.replace('/', '%2F')}",
                  wait_until="domcontentloaded")
        page.get_by_role("button", name="Build…").first.click(timeout=30000)
        page.get_by_test_id("build-dialog").wait_for(timeout=10000)
        page.screenshot(path=str(d.TMP / "build_dialog.png"), full_page=True)
        shown = {}
        for t in tasks:
            try:
                shown[t["key"]] = (page.get_by_test_id(f"build-task-builder-{t['key']}").input_value(),
                                   page.get_by_test_id(f"build-task-checker-{t['key']}").input_value())
            except Exception:  # noqa: BLE001 -- a row that is not there reads as not selected
                shown[t["key"]] = (None, None)
        d.check("B1 Build opens with each task's picks selected",
                bool(tasks) and all(shown[t["key"]] == (t.get("builder"), t.get("checker"))
                                    for t in tasks),
                f"shown={shown}")
        seen = {}
        for t in tasks:
            reason = page.get_by_test_id(f"build-task-reason-{t['key']}")
            seen[t["key"]] = reason.inner_text() if reason.count() else ""
        d.check("B2 each task's reasons are visible beside its row",
                all(all(r[:20] in seen[t["key"]] for r in reasons(t, "builder") + reasons(t, "checker"))
                    and seen[t["key"]] for t in tasks), f"seen={seen}")
        page.get_by_test_id("build-confirm").click()
        page.wait_for_timeout(5000)
        browser.close()
    body = json.loads(sent[0]) if sent else {}
    (d.TMP / "build_request.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    build = next((b for b in (read.get("builds") or []) if b.get("state") == "running"), None)
    state["build_id"] = (build or {}).get("id")
    d.check("B3 building as-is records exactly those picks",
            bool(build) and bool(tasks) and all((build.get("tasks") or {}).get(t["key"]) ==
                                {"builder": t.get("builder"), "checker": t.get("checker")}
                                for t in tasks), json.dumps(build, default=str)[:600])
    if not build:
        raise d.Stop("no running build")

    # ---- C: the build runs and finishes -------------------------------------------------
    ((job,),) = d.ro("select l.job_id from loops l join builds b on b.loop_id=l.id where b.id=?",
                     (state["build_id"],)) or [(None,)]
    start = time.time()
    while time.time() - start < BUILD_LIMIT:
        d.fire(base, job)
        d.wait_idle(pid, 4 * 60)
        if d.ro("select state from builds where id=?", (state["build_id"],))[0][0] != "running":
            break
        time.sleep(5)
    row = d.ro("select state, level, landing from builds where id=?", (state["build_id"],))[0]
    d.check("C1 the build finished by running out of work", row[0] == "finished", str(row), fatal=True)
    level, landing = row[1], row[2]
    con_args = (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 30 * 86400)),
                state["build_id"])
    import sqlite3
    con = sqlite3.connect(d.DB.as_posix(), timeout=30)
    con.execute("update builds set stopped_at=? where id=?", con_args)
    con.commit()
    con.close()

    # ---- D: the follow-up ---------------------------------------------------------------
    code, filed = d.as_agent(pid, CHECKER, "POST", "/tasks", {
        "title": "Add FOLLOWUP.md", "spec_document": path,
        "description": "Create FOLLOWUP.md holding the single line `follow-up`, then move this "
                       "task to completed. Change nothing else."})
    d.check("D0 the checker files a follow-up against the spec", code in (200, 201),
            f"{code} {str(filed)[:300]}", fatal=True)
    follow = filed["id"]
    after = build_of(pid, path)
    d.check("D1 the same build reads running at the same level and landing",
            bool(after) and after[0][0] == state["build_id"] and after[0][1] == "running"
            and after[0][2] == level and after[0][3] == landing, str(after[:2]))
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    mine = next((b for b in (read.get("builds") or []) if b.get("id") == state["build_id"]), {})
    d.check("D2 the build record shows the reopening", "reopen" in json.dumps(mine, default=str).lower(),
            json.dumps(mine, default=str)[:400])
    _, task = d.api("GET", f"{base}/tasks/{follow}")
    d.check("D3 the follow-up goes to the build's default builder",
            isinstance(task, dict) and task.get("assignee") == mine.get("builder")
            and bool(mine.get("builder")), f"{str(task)[:300]} builder={mine.get('builder')}")
    shown_phase = current(base, doc_id)[1]
    d.check("D4 the spec stops reading as done: it shows building", shown_phase == "building",
            f"display_phase={shown_phase}")
    new_job = (d.ro("select l.job_id from loops l join tasks t on t.loop_id=l.id where t.id=?",
                    (follow,)) or [(None,)])[0][0]
    started = False
    for _ in range(2):
        if new_job:
            d.fire(base, new_job)
            started = d.poll(lambda: d.ro("select 1 from runs where task_id=?", (follow,)), 90, 3)
        if started:
            break
    d.check("D5 a flow starts the follow-up within two firings, no other call", started,
            f"job={new_job}")
    d.wait_idle(pid, 4 * 60)

    # ---- E: the Overview warning --------------------------------------------------------
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(seed(pid))
        page.goto(f"{d.HUB}/?project={pid}&tab=overview", wait_until="domcontentloaded")
        warning = page.get_by_test_id("reopening-warning")
        try:
            warning.first.wait_for(timeout=30000)
            text = warning.first.inner_text()
        except Exception:  # noqa: BLE001 -- no warning on the page
            text = ""
        page.screenshot(path=str(d.TMP / "overview.png"), full_page=True)
        d.check("E1 the warning names the spec, the task, the filer and 30 days",
                bool(text) and DOC_TITLE.split()[0].lower() in (text + path).lower()
                and "Add FOLLOWUP.md" in text and CHECKER in text and "30 days" in text, text[:400])
        if text:
            page.get_by_test_id("reopening-warning-stop").first.click()
            page.wait_for_timeout(4000)
        browser.close()
    d.check("E2 stopping from the warning stops the build",
            d.ro("select state from builds where id=?", (state["build_id"],))[0][0] == "stopped",
            str(d.ro("select state from builds where id=?", (state["build_id"],))))
    before = d.ro("select count(*) from runs where project_id=?", (pid,))[0][0]
    if new_job:
        d.fire(base, new_job)
        d.wait_idle(pid, 2 * 60)
    d.check("E3 its flow starts nothing further",
            d.ro("select count(*) from runs where project_id=?", (pid,))[0][0] == before)


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
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed 2026-11-01 on master (no implementation; 16:47 run, artefacts drive1101-recommended-
# people/164714): 20 passed, 14 failed -- A1-A6, B2, D1-D5, E1, E2. Authoring: the real Haiku author
# never asked how to judge the models, no tool read a record, and submitted no tasks (the drive
# seeds a document with picks and no reasons so the rest runs). Build opens with the picks selected
# (B1, B3 pass) but shows no reasons (B2). The build finishes; the follow-up joins nothing: it stays
# pending with no assignee, the build stays finished, the spec's display_phase reads `done` (D1-D5),
# no warning is on Overview (E1) and the stop gets a 409 on a finished build (E2).
