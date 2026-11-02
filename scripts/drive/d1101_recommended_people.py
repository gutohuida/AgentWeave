"""Acceptance drive for `every-task-comes-with-a-recommended-builder-and-checker` (FR-12, ac-drive).

Drives the trial Hub on :8010 (reusing one that answers, else starting one from this checkout's
`hub/`), never :8000. A scratch git project, a Haiku runner, and a roster of four agents:

  Author  -- writes the spec        Strong -- the "Opus" of the roster (named so, rebound to Haiku
  Cheap   -- the "Sonnet"                    before any build turn, so every turn is Haiku)
  Checker -- reviews and files the follow-up

Steps (each records its checks and the drive goes on, so one run on master shows every failure):

  A  Authoring. A real Haiku author is asked for a large spec with one hazardous (migration) and
     one routine (copy change) task. It must ask how to judge the models (A1, by ask_user or in
     text); the drive answers through the question's route ('review the project record') and the
     author must read the per-model record (A2: a tool call naming the record, with its figures
     in the document's evidence, FR-13/FR-14). The author's document must be buildable (A7:
     requirements declared, every task linked to one) and approve without approve_anyway (A8);
     only then does A9 hold. A document that is not buildable is replaced by a seeded one so the
     rest is seen, but that run cannot pass. The submitted
     document gives every task a builder and checker (A3), a reason for each pick (A4), a checker
     that is not the builder (A5), and the two tasks different builders (A6).
  B  Build dialog, in Chromium. It opens with each task's picks selected (B1), their reasons
     visible beside the row (B2), and building as-is records exactly those picks (B3).
  C  The build runs as a flow at Reviewed until it finishes (C1); the drive then ages its end 30
     days back, as the fixture, so the warning has an age to name.
  D  Follow-up. The Checker files a task against the spec's requirements through the agent plane
     (B4 first shows that such a filing joins a running build). It joins the
     finished build, which reopens under the same id, level and landing (D1), shows the reopening
     (D2), takes the build's people (D3), and the spec stops reading as done (D4). Firing the
     build's flow at most twice then starts the task with no other call (D5).
  E  Overview, in Chromium. The warning names the spec, the task, the filer and 30 days (E1);
     stopping from it stops the build (E2) and its flow starts nothing further (E3).

The author is walked through the journey as the operator would, in one conversation (answering
'continue' to each step, and pressing it on when a turn leaves the step where it was; the models
question is answered only once asked; approval gaps go back to the author). A turn is every run the
author does until it is idle: the trigger may answer 'queued' with no run, and an answer delivered
late starts a run nobody triggered. A walk that runs out of turns says so (A0, A0b) and goes on.
On master it fails at A1/A2/A4 (no tool reads the record; picks carry no reasons), B2 (no
reasons shown), D1-D5 (the follow-up joins nothing: no reopening, no assignee, the spec reads
done, no flow starts it) and E1/E2. Whether the master author writes a buildable document varies
from run to run; if not, the drive seeds one (picks, no reasons) and A7-A9 fail as well.
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
    "submitting the document with a builder, checker and reason on every task. Set the "
    f"document's delivery to a flow run by {STRONG} that stops when its queue empties, and give "
    "every acceptance criterion both a `how_to_check` and a `checked_by` (agent or human): the "
    "Hub refuses a criterion without either. Order the tasks so the Hub accepts them: the first "
    "task depends on nothing and every other task has it in `depends_on` (the first is the "
    "acceptance drive the rest wait on)."
)
FLOW_DELIVERY = {"mode": "flow", "agent": STRONG, "builder": STRONG, "checker": CHECKER,
                 "builders": [STRONG, CHEAP], "stop_when_queue_empties": True,
                 "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}}
ANSWER = (
    "Judge the models by reviewing this project's record only (not the web, not just what you "
    "know). Read it with your tool, state the sample sizes, then continue and submit the tasks."
)
PRESS_ON = (
    "Nothing more is coming on this step: everything I can tell you is in my request, repeated "
    "below. Decide anything it leaves out yourself and say what you decided; every acceptance "
    "criterion is `checked_by` agent. The model choice is not one of those: leave who builds and "
    "checks undecided until the tasks step, whose instructions say how to settle it. Write only "
    "this step's part with submit_spec_document, keeping everything already written, then call "
    "advance_spec_step once and read what the next step says: I have chosen to continue."
    "\n\nMy request: "
) + REQUEST
TURN = 8 * 60
TURNS = 12
BUILD_LIMIT = 30 * 60


def open_questions(run_ids):
    """The ask_user questions these runs left unanswered: (id, text, options, multi_select)."""
    if not run_ids:
        return []
    marks = ",".join("?" * len(run_ids))
    out = []
    for qid, text, options, multi in d.ro(
            "select id, question, options, multi_select from questions where created_by_run_id "
            f"in ({marks}) and answered=0 and declined=0 order by created_at", tuple(run_ids)):
        try:
            options = json.loads(options) if isinstance(options, str) else options
        except ValueError:
            options = []
        out.append((qid, text, options or [], bool(multi)))
    return out


def trigger(base, message, path, conversation=None):
    """Triggers the author, in its conversation once it has one. Returns the conversation id. The
    answer holds no run when the input was queued, so the caller waits on the author, not on a run."""
    body = {"agent": AUTHOR, "message": message, "spec_document": path}
    if conversation:
        body["conversation_id"] = conversation
    code, run = d.api("POST", f"{base}/agent/trigger", body)
    d.check("setup: the author turn starts", code in (200, 201, 202), f"{code} {run}", fatal=True)
    if not run.get("run_id"):
        print(f"  author turn queued: {run.get('waiting_reason') or run.get('message')}", flush=True)
    return run.get("conversation_id") or conversation


def author_runs(pid):
    """Every run the author has had, oldest first, however it was started."""
    return [r for (r,) in d.ro("select id from runs where project_id=? and agent=? order by rowid",
                               (pid, AUTHOR))]


def author_busy(pid):
    """The author's live runs and the input waiting for one."""
    return d.ro("select id, status from runs where project_id=? and agent=? and status in "
                "('running', 'queued', 'starting') union all select id, state from "
                "inbound_queue_entries where project_id=? and agent=? and state='queued'",
                (pid, AUTHOR, pid, AUTHOR))


def reply(run_ids):
    """What the runs said: their text, and every ask_user question with its options."""
    said = []
    for run_id in run_ids:
        said += [c for (c,) in d.ro(
            "select content from agent_outputs where run_id=? and kind='text' order by sequence",
            (run_id,))]
        for text, options in d.ro("select question, options from questions where "
                                  "created_by_run_id=? order by created_at", (run_id,)):
            said.append(f"{text} {options}")
    return "\n".join(said)


def chosen(options):
    """The labels of the options that point at the project's own record (the label names it:
    a web-search option whose description mentions the project is not one)."""
    labels = [o["label"] for o in options if isinstance(o, dict) and o.get("label")]
    return ([x for x in labels if re.search(r"record|history|tally", x, re.I)]
            or [x for x in labels if re.search(r"project", x, re.I)
                and not re.search(r"web|search", x, re.I)])


def sources_question(options):
    """A question that offers the sources to judge the models by: the web and the project's record."""
    labels = " ".join(o.get("label", "") for o in options if isinstance(o, dict))
    return bool(re.search(r"web|search", labels, re.I)
                and re.search(r"record|history|tally|project", labels, re.I))


def models_question(text):
    """A question about which models, agents or builders to use (answered with the sources)."""
    return bool(re.search(r"model|judge|assign|builder|checker|roster|pick", text or "", re.I))


def journey_label(options):
    """The option that carries the author on, for a question about the journey (not the models)."""
    labels = [o["label"] for o in options if isinstance(o, dict) and o.get("label")]
    ok = [x for x in labels if not re.search(r"stop|fresh|cancel", x, re.I)]
    return next((x for x in ok if re.search(r"continue|yes|proceed|here", x, re.I)),
                (ok or labels or ["Continue."])[0])


def asks_for_sources(said):
    """The author's text asks, in a question sentence, which sources to judge the models by: naming
    both sources in that sentence, or asking about sources and listing them around it."""
    return bool(re.search(r"[^.?!\n]*(web|search)[^.?!\n]*(record|project'?s)[^.?!\n]*\?"
                          r"|[^.?!\n]*(record|project'?s)[^.?!\n]*(web|search)[^.?!\n]*\?",
                          said, re.I)
                or (re.search(r"[^.?!\n]*(sources?|judge)[^.?!\n]*\?", said, re.I)
                    and re.search(r"web|search", said, re.I)
                    and re.search(r"record|project'?s", said, re.I)))


def read_record_by_route():
    """An author that reads through its command equivalents shows only `Called PowerShell` in its
    outputs, so the route's own access line counts as the call. Only a Hub this drive started has
    a log here; on a reused one the tool name is the only signal."""
    log = d.TMP / "hub.log"
    return log.exists() and "/agent-actions/model-record HTTP/1.1\" 200" in log.read_text(
        encoding="utf-8", errors="replace")


def buildable(doc):
    """Requirements declared, and every task linked to one of them: without that a task has no
    evidence to wait for, and the build stalls on a 409 at its first completed task."""
    keys = {r.get("key") for r in doc.get("requirements") or [] if isinstance(r, dict)}
    ts = [t for t in doc.get("tasks") or [] if isinstance(t, dict)]
    return bool(keys) and len(ts) >= 2 and all(
        [r for r in t.get("requirements") or [] if isinstance(r, str)]
        and set(t["requirements"]) <= keys for t in ts)


def fire_job(base, job_id):
    """Fires a build's flow once and returns the answer: a refused firing is the caller's failure."""
    code, out = d.api("POST", f"{base}/jobs/{job_id}/run")
    print(f"  fired {job_id}: {code} {str(out)[:200]}", flush=True)
    return code, out


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
                "builder": builder, "checker": CHECKER,
                "depends_on": [] if key == "schema" else ["schema"]}
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
        "delivery": dict(FLOW_DELIVERY),
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

    answered = []
    sources_answered = []

    conversation = None

    def answer_questions():
        """Answers what the author has parked on (through the question's route, as the operator
        would). Returns whether there was anything to answer."""
        pending = open_questions(author_runs(pid))
        for qid, qtext, options, _multi in pending:
            # A question that offers the sources gets the project's record; any other
            # question about the models or the roster is answered in words; the journey's
            # 'how to proceed' gets its Continue option.
            if sources_question(options):
                labels = chosen(options)
                answer = ", ".join(labels) or ANSWER
                sources_answered.append(qid)
            elif models_question(qtext):
                labels = chosen(options)
                answer = ANSWER
            else:
                labels = [journey_label(options)]
                answer = labels[0]
            code, out = d.api("PATCH", f"{base}/questions/{qid}",
                              {"answer": answer, "labels": labels})
            d.check("setup: an author question is answered", code == 200, f"{code} {str(out)[:200]}")
            answered.append(qid)
        return bool(pending)

    def author_turn(message):
        """One author turn, in the one conversation: from the trigger until the author is idle,
        answering any ask_user on the way. Returns the runs it took, none if the input never got
        one; the path is re-read by id after, as the author may have renamed."""
        nonlocal path, conversation
        before = set(author_runs(pid))
        conversation = trigger(base, message, path, conversation)
        deadline = time.time() + TURN
        was_idle = False
        while time.time() < deadline:
            time.sleep(3)
            if answer_questions():
                deadline = time.time() + TURN
                was_idle = False
                continue
            # Twice running: a run that just ended can hand the queue to the next one.
            idle = not author_busy(pid)
            if idle and was_idle:
                break
            was_idle = idle
        d.check("setup: the author turn ends", was_idle, f"still busy: {author_busy(pid)}")
        path = current(base, doc_id)[0] or path
        return [r for r in author_runs(pid) if r not in before]

    def check_a1b(text, run_ids):
        marks = ",".join("?" * len(run_ids))
        said = json.dumps(d.ro(f"select content from agent_outputs where run_id in ({marks})",
                               tuple(run_ids))).lower()
        d.check("A1b the author was told the roster's models",
                "opus" in text.lower() or "opus" in said, text[:200])

    def step_of():
        return (d.ro("select step from spec_documents where id=?", (doc_id,)) or [(None,)])[0][0]

    # Walk the journey as the operator would, in one conversation: the request goes once, then
    # 'continue' to each step. The author is to ask how to judge the models at the tasks step
    # (FR-13); the answer is given only in reply to the ask. An author that has not asked by the
    # time it stands at the tasks step fails A1 by name, and is then told. The walk is bounded.
    said_all, asked, a1_done, told, message = [], False, False, False, REQUEST
    reached = False
    saw_tasks = False
    for _ in range(TURNS):
        step_before = step_of()
        run_ids = author_turn(message)
        saw_tasks = saw_tasks or step_of() in ("tasks", "build")
        said = reply(run_ids)
        said_all.append(said)
        (d.TMP / f"author-turn{len(said_all)}.txt").write_text(said, encoding="utf-8")
        text = "\n".join(said_all)
        turn_text = "\n".join(c for r in run_ids for (c,) in d.ro(
            "select content from agent_outputs where run_id=? and kind='text'", (r,)))
        # Asked only by an ask_user question that offered the sources, or a question sentence.
        asked = asked or bool(sources_answered) or asks_for_sources(turn_text)
        answered_by_route = bool(sources_answered)
        if not a1_done and (asked or step_before in ("tasks", "build")):
            a1_done = True
            d.check("A1 the author asks which sources to judge the models by", asked, text[-600:])
            check_a1b(text, author_runs(pid))
            told = answered_by_route
            message = ("Continue." if answered_by_route else f"{ANSWER} Then continue.")
            continue
        doc = payload_of(root, path)
        tasks_now = tasks_of(root, path)
        if step_of() == "build" and len(tasks_now) >= 2:
            if buildable(doc) and not told:
                # A buildable document reached without the ask: tell the author, and let it act
                # on the answer (A2), rather than leaving A2 to fail unprompted.
                told = True
                message = f"{ANSWER} Then record what you find in the document and resubmit it."
                continue
            if buildable(doc):
                reached = True
                break
            message = ("The document cannot be built yet: declare its requirements (each with an "
                       "acceptance criterion) and give every task `requirements` naming the keys "
                       "it implements. Resubmit it, keeping every builder, checker and reason.")
        elif step_of() in ("tasks", "build") and len(tasks_now) < 2:
            message = ("Submit the document with both tasks, each with builder, checker and a "
                       "reason for each.")
        elif not told and asks_for_sources(turn_text):
            told = True
            message = f"{ANSWER} Then continue."
        elif step_of() == step_before:
            message = PRESS_ON
        else:
            message = "Continue: take the document to the next step."
    d.check(f"A0b the author reached the tasks step within {TURNS} turns", saw_tasks,
            f"step={step_of()} turns={len(said_all)}")
    d.check(f"A0 the author reached the build step with a buildable document within {TURNS} turns",
            reached, f"step={step_of()} turns={len(said_all)}")
    if not a1_done:
        d.check("A1 the author asks which sources to judge the models by", asked,
                ("" if saw_tasks else "never reached the tasks step, where it is asked; ")
                + "\n".join(said_all)[-600:])
        check_a1b("\n".join(said_all), author_runs(pid))
    quoted = urllib.parse.quote(path)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    written = payload_of(root, path)
    (d.TMP / "document.json").write_text(json.dumps(written, indent=1, default=str), encoding="utf-8")
    run_ids = author_runs(pid)
    marks = ",".join("?" * len(run_ids))
    touched = d.ro(f"select content from agent_outputs where run_id in ({marks}) "
                   "and kind in ('tool_use','tool_call') ", tuple(run_ids)) or []
    blob = " ".join(c for (c,) in touched).lower()
    evidence = json.dumps(written.get("evidence"), default=str).lower()
    d.check("A2 the author read the per-model record (a tool call, with its figures in evidence)",
            (bool(re.search(r"model[_ -]?record|per[_ -]?model|work[_ -]?tally", blob))
             or read_record_by_route())
            and re.search(r"sample|n=|\b\d+ (\w+ )?(tasks?|turns?)\b", evidence) is not None,
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
    own = len(tasks) >= 2 and buildable(written)
    d.check("A7 the author's document is buildable: requirements declared, every task linked to one",
            own, json.dumps({"requirements": written.get("requirements"),
                             "task_requirements": [t.get("requirements") for t in tasks]},
                            default=str)[:500])
    fallback = []
    if not own:
        # The author did not get to a buildable document (on master it varies): seed one, with
        # picks and no reasons, so Build, the follow-up and Overview are driven and fail, if they
        # do, for their own reasons rather than all at once here.
        code, out = d.api("PUT", f"{base}/project/documents/{path}/content",
                          {"document": seeded()})
        fallback.append("seeded")
        print("NOTE: the author's document is not buildable; a seeded one stands in so the rest "
              "of the drive is seen. This run cannot pass (A9).")
        d.check("setup: the author's document did not stand; a seeded one is saved instead",
                code == 200, f"{code} {str(out)[:400]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        tasks = tasks_of(root, path)
        d.check("setup: the seeded document holds two tasks", len(tasks) == 2, fatal=True)
    state["tasks"] = tasks

    # The "Opus" of the roster is rebound to Haiku: every build turn is Haiku.
    d.api("PATCH", f"{base}/agents/{STRONG}", {"runner_id": haiku["id"]})
    d.api("PATCH", f"{base}/agents/{CHEAP}", {"runner_id": haiku["id"]})
    # Step C and the follow-up need a flow. The author may have written delivery none (or another
    # shape); the drive sets the flow itself, as a named setup step, before approval, so a missing
    # flow is never mistaken for a refused firing later.
    full = payload_of(root, path)
    delivery = full.get("delivery") or {}
    d.check("setup S1: the document recommends a flow run by an open agent",
            delivery.get("mode") == "flow" and delivery.get("agent") in (STRONG, CHEAP, CHECKER, AUTHOR),
            json.dumps(delivery, default=str)[:300])
    if delivery.get("mode") != "flow" or delivery.get("agent") not in (STRONG, CHEAP, CHECKER, AUTHOR):
        full.pop("hub", None)
        full["delivery"] = dict(FLOW_DELIVERY)
        code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": full})
        d.check("setup S2: the drive sets the flow delivery itself", code == 200,
                f"{code} {str(out)[:400]}", fatal=True)
    # Approval gaps go back to the author, as the operator would hand them, for a bounded number
    # of turns before A8 decides (a seeded stand-in has no author to hand them to).
    for attempt in range(3):
        quoted = urllib.parse.quote(path)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        approve = f"{base}/project/documents/phase?path={quoted}&to=approved"
        version = read.get("content_version")
        code, out = d.api("POST", approve, {"reason": "drive", "content_version": version})
        if code == 200 or fallback or attempt == 2:
            break
        author_turn("Approving the document was refused: "
                    f"{json.dumps(out, default=str)[:1500]}\nFix what it names (record the "
                    "journey's steps if the document already holds them) so it approves without "
                    "approve_anyway.")
    d.check("A8 the document approves on its own, without approve_anyway", code == 200,
            f"{code} {str(out)[:400]}")
    if code != 200:
        print(f"NOTE: approval was refused after the retries; the Hub's gaps: {str(out)[:600]}")
    if code != 200:
        fallback.append("forced")
        code, out = d.api("POST", approve, {"reason": "drive", "approve_anyway": True,
                                            "content_version": version})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    d.check("A9 the build is on the author's own document (not seeded, not forced)",
            not fallback, ",".join(fallback))

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
        try:
            page.get_by_role("button", name="Build…").first.click(timeout=30000)
        except Exception:  # noqa: BLE001 -- keep what the page showed, then fail as before
            page.screenshot(path=str(d.TMP / "no-build-button.png"))
            (d.TMP / "no-build-button.txt").write_text(
                f"{page.url}\n{page.inner_text('body')[:3000]}", encoding="utf-8")
            raise
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
    d.check("setup S3: Build was confirmed as a flow", body.get("driver") == "flow",
            json.dumps(body, default=str)[:300], fatal=True)
    d.check("B3 building as-is records exactly those picks",
            bool(build) and bool(tasks) and all((build.get("tasks") or {}).get(t["key"]) ==
                                {"builder": t.get("builder"), "checker": t.get("checker")}
                                for t in tasks), json.dumps(build, default=str)[:600])
    if not build:
        raise d.Stop("no running build")

    # A control: a task filed against the spec while its build runs joins that build, so the
    # follow-up's filing in D is known good and only the finished build is in question.
    reqs = [i for (i,) in d.ro("select identifier from spec_requirements where document_id=? "
                               "and state='active' order by identifier", (doc_id,))]
    code, control = d.as_agent(pid, CHECKER, "POST", "/tasks", {
        "title": "Add CONTROL.md", "spec_document": path, "requirement_ids": reqs[:1],
        "description": "Create CONTROL.md holding the single line `control`, then move this "
                       "task to completed. Change nothing else."})
    joined = code in (200, 201) and d.ro("select build_id from tasks where id=?",
                                         (control["id"],))[0][0] == state["build_id"]
    d.check("B4 a task filed against the spec while its build runs joins the build", joined,
            f"{code} {str(control)[:300]}")

    # ---- C: the build runs and finishes -------------------------------------------------
    ((job,),) = d.ro("select l.job_id from loops l join builds b on b.loop_id=l.id where b.id=?",
                     (state["build_id"],)) or [(None,)]
    d.check("setup S4: the build has a flow to fire", bool(job), f"job={job}", fatal=True)
    start = time.time()
    while time.time() - start < BUILD_LIMIT:
        code, out = fire_job(base, job)
        # "Every task ... is already being worked" and "<agent> is already running a turn" are 409s
        # that say nothing is wrong; any other refusal (for one, a completed task with no recorded
        # evidence) stops the drive, named.
        busy = code == 409 and ("already being worked" in str(out)
                                or "already running a turn" in str(out))
        d.check("C0 the build's flow accepts each firing", code in (200, 201, 202) or busy,
                f"{code} {str(out)[:300]}", fatal=True)
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
        "title": "Add FOLLOWUP.md", "spec_document": path, "requirement_ids": reqs[:1],
        "description": "Create FOLLOWUP.md holding the single line `follow-up`, then move this "
                       "task to completed. Change nothing else."})
    d.check("D0 the checker files a follow-up against the spec", code in (200, 201),
            f"{code} {str(filed)[:300]}", fatal=True)
    follow = filed["id"]
    linked = d.ro("select spec_document_id from tasks where id=?", (follow,))[0][0]
    d.check("D0b the follow-up is linked to the spec, as the control was",
            linked == doc_id, f"spec_document_id={linked}", fatal=True)
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
    # A pending task against the spec already reads `building` on master, so the build must also
    # be the running one for this to tell the two apart.
    d.check("D4 the spec stops reading as done: it shows building under a running build",
            shown_phase == "building" and bool(after) and after[0][1] == "running",
            f"display_phase={shown_phase} build={after[:1]}")
    new_job = (d.ro("select l.job_id from loops l join tasks t on t.loop_id=l.id where t.id=?",
                    (follow,)) or [(None,)])[0][0]
    started = False
    for _ in range(2):
        if new_job:
            fire_job(base, new_job)
            started = d.poll(lambda: d.ro("select 1 from runs where task_id=?", (follow,)), 90, 3)
        if started:
            break
    d.check("D5 a flow starts the follow-up within two firings, no other call", started,
            f"job={new_job}")

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
        title = str(payload_of(root, path).get("title") or "")
        d.check("E1 the warning names the spec, the task, the filer and 30 days",
                bool(text) and bool(title) and title.lower() in text.lower()
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
        fire_job(base, new_job)
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

# Observed 2026-11-01 on master (no implementation; run 21:18:12, artefacts drive1101-recommended-
# people/211812): 39 passed, 11 failed -- A1, A2, A4, B2, D1-D5, E1, E2. The author, kept in one
# conversation, reached the build step in 9 turns (A0) with a buildable document of its own, which
# approved without approve_anyway (A7-A9 hold, no seeding); it never asked which sources to judge by
# (A1), never read a record (A2) and gave no reasons (A4, B2). The finished build ignores the linked
# follow-up: no reopening, no assignee, the spec shows done, no flow starts it, no Overview warning,
# nothing to stop. B4 shows a task filed against the spec while its build runs does join it. What a
# master author writes varies run to run, so a run whose document is not buildable is seeded and
# fails A7-A9 as well, and a walk that runs out of turns fails A0 by name. One earlier run could not
# find the Build button within 30 s (a slow page load; the drive now keeps a screenshot then).
#
# Observed 2026-11-02 at ETCRB-3's implementation (run 05:06:47, artefacts .../050647): 48 passed, 8
# failed. The author reached the build step in 8 turns on its own document (A0, A0b, A7-A9), asked
# which sources in a question of its own (A1) and read the record through its command route, twice;
# that A2 failure is why the route's access line now counts. D1-D5, E1, E2 are ETCRB-4's. A forced run
# (a queued first trigger, a 2-turn budget) ended 28 passed, 18 failed with no crash: it named
# A0, went on on a seeded document and reached E3.
