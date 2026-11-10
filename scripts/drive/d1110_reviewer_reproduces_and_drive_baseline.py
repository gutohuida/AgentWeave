"""Acceptance drive for `evidence-review-sends-work-back-only-for-what-is-wrong-with-it`, 2026-11-10.

The change's first task (spdoc-90c4b16a5d3e, task `drive`), written before the build. It covers two
acceptance criteria on a scratch project with real Haiku turns:

  ac-reanchor-lands (FR-1)  A flow task's FR-1 evidence is recorded at commit A. The drive then
                            moves the task branch to B: a fix commit, then a merge of main (the
                            checker is held busy by a seeded run until then, because a finished
                            task's review is handed out at once). The
                            task's reviewer accepts the evidence with its own reproduction at B
                            and approves.
      R1  the accepted evidence's footprint names B
      R2  the landed work (main) includes B's changes: the fix line, and B is an ancestor of main

  ac-bad-baseline (FR-7)    A two-task document whose first task is its acceptance drive. The
                            drive's builder records a `drive_baseline` evidence row listing one
                            check that stopped at a 404 (`c-unreached`) and one that passed on the
                            pre-build code (`c-vacuous`). The drive's reviewer reviews it; the flow
                            is fired once more afterwards, so a dependent that could start, would.
      K1  the drive task went to revision_needed
      K2  the send-back names both checks (task notes or the evidence's rejection reason)
      K3  the dependent task has not started (never handed out, not in progress)

Each covered check is reported as reached or not, and as passed or failed at its own assertion, in
a per-check baseline printed at the end: a check whose setup did not happen (a turn that did not
complete, a branch that could not be staged) reads `not reached`, never `failed`.

The baseline evidence's shape is a convention this drive fixes for the build to enforce: one line per
check, `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`.

Scratch Hub: the trial Hub on AW_DRIVE_PORT (default 8010), reused when one answers there and
otherwise started from this checkout's `hub/` on AW_DRIVE_DB (default: the trial profile's
database). Never :8000. The flows' cron fires once a year; the drive fires them itself. About
six Haiku turns, 15-30 minutes.

    py -3.11 scripts/drive/d1110_reviewer_reproduces_and_drive_baseline.py
"""

import subprocess
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1110-reviewer-reproduces" / d.STAMP
NOTE_DOC = "spec/changes/note-file/spec.json"
DRIVE_DOC = "spec/changes/greeting/spec.json"
B1, R1, B2, R2 = "NoteBuilder", "NoteChecker", "DriveBuilder", "DriveChecker"
FIX_LINE = "fixed after the evidence was recorded"
UNREACHED, VACUOUS = "c-unreached", "c-vacuous"
BASELINE = (
    "drive baseline on the pre-build code:\n"
    f"check {UNREACHED}: reached=no failed_at_assertion=no -- stopped at setup: "
    "POST /api/v1/greetings answered 404 before its assertion ran\n"
    f"check {VACUOUS}: reached=yes failed_at_assertion=no -- passed on the pre-build code"
)
YEARLY = "0 0 1 1 *"
FIRINGS = 3

# The per-check baseline: key -> {"criterion", "reached", "passed", "detail"}.
baseline = {}


def covered(key, criterion, reached, ok=False, detail=""):
    """One covered check. Not reached is reported as such and never counted as its assertion."""
    baseline[key] = {"criterion": criterion, "reached": bool(reached),
                     "passed": bool(reached and ok), "detail": detail}
    if reached:
        d.check(f"{criterion} {key}", ok, detail)
    else:
        d.check(f"{criterion} {key} (not reached)", False, detail)


def note_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Note file",
        "summary": "One file.", "problem": "There is no note.",
        "scope": {"in_scope": ["NOTE.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "note", "modal": "MUST", "statement": "NOTE.md MUST exist."}],
        "acceptance_criteria": [{
            "key": "exists", "requirement": "note", "given": "the repository", "when": "read",
            "then": "NOTE.md starts with the line note", "how_to_check": "cat NOTE.md",
            "checked_by": "agent"}],
        "tasks": [{
            "key": "t1", "title": "Write the note", "requirements": ["note"], "files": ["NOTE.md"],
            "builder": B1, "checker": R1,
            "description": (
                "Create NOTE.md at the repository root holding the single line `note`. Commit it "
                "yourself: `git add NOTE.md` then `git commit -m note`. Then call record_evidence "
                f"for FR-1 (document {NOTE_DOC}) with command `cat NOTE.md`, its output, and "
                "covers `full`. Then move this task to completed. Change nothing else.\n\n"
                "To the reviewer: the task branch may have moved after the evidence was recorded "
                "(a fix and a merge of main). Run `cat NOTE.md` on the current checkout; where it "
                "still starts with `note`, accept the evidence with your own reproduction at the "
                "current commit rather than sending the task back to have it recorded again."),
        }],
        "delivery": {"mode": "flow", "agent": B1, "checker": R1, "stop_when_queue_empties": True,
                     "cron": YEARLY, "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def drive_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Greeting",
        "summary": "A greeting route.", "problem": "There is no greeting.",
        "scope": {"in_scope": ["greet.py"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "greet", "modal": "MUST",
                          "statement": "POST /api/v1/greetings MUST answer 201 with a greeting."}],
        "acceptance_criteria": [{
            "key": "greets", "requirement": "greet", "given": "the service",
            "when": "POST /api/v1/greetings is called", "then": "it answers 201 with a greeting",
            "how_to_check": "acceptance drive", "checked_by": "agent"}],
        "tasks": [{
            "key": "drive", "title": "Acceptance drive", "requirements": ["greet"],
            "files": ["drive_check.py"], "builder": B2, "checker": R2,
            "description": (
                "This task is the document's acceptance drive. Create drive_check.py at the "
                "repository root holding the single line `print('drive')`, and commit it: "
                "`git add drive_check.py` then `git commit -m drive`. Then call record_evidence "
                f"for FR-1 (document {DRIVE_DOC}) with kind `drive_baseline`, command "
                "`python drive_check.py`, covers `full`, summary `per-check baseline of the "
                "acceptance drive on the pre-build code`, and output exactly these three lines:\n\n"
                + BASELINE + "\n\nThen move this task to completed. Change nothing else."),
        }, {
            "key": "build", "title": "Build the greeting", "requirements": ["greet"],
            "files": ["greet.py"], "depends_on": ["drive"], "builder": B2, "checker": R2,
            "description": "Create greet.py with a function greet() returning 'hello'.",
        }],
        "delivery": {"mode": "flow", "agent": B2, "checker": R2, "stop_when_queue_empties": True,
                     "cron": YEARLY, "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def open_doc(base, pid, path, title, payload, builder, checker):
    quoted = urllib.parse.quote(path)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": title, "kind": "change-spec", "path": path})
    d.check(f"setup: {title} created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": payload})
    d.check(f"setup: {title} saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check(f"setup: {title} approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builder": builder,
                       "checker": checker, "landing": "main"})
    d.check(f"setup: {title} built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = d.ro("select t.id, t.spec_task_key, t.loop_id from tasks t join spec_documents s "
                "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, path))
    tasks = {key: tid for tid, key, _ in rows}
    loop = rows[0][2]
    job = d.ro("select job_id from loops where id=?", (loop,))[0][0]
    return {"build": build_id, "tasks": tasks, "loop": loop, "job": job}


def status_of(task):
    return d.ro("select status, assignee from tasks where id=?", (task,))[0]


def evidence(task):
    return d.ro("select e.id, e.kind, e.review_state, f.commit_sha, e.actor from requirement_evidence e "
                "left join evidence_footprints f on f.evidence_id=e.id where e.task_id=? "
                "order by e.produced_at", (task,))


def send_back_words(base, task):
    """What a send-back said: the task's notes once it went to revision_needed, and the reasons
    on decisions that did not accept. An approval's notes that mention a check name are not one
    (observed on master: the approving reviewer listed both checks while approving)."""
    moves = [to for (to,) in d.ro("select to_status from task_transitions where task_id=?", (task,))]
    _, card = d.api("GET", f"{base}/tasks/{task}")
    notes = str((card or {}).get("notes") or "") if "revision_needed" in moves else ""
    return " ".join([notes, *[r for (r,) in d.ro(
        "select r.reason from evidence_reviews r join requirement_evidence e on e.id=r.evidence_id "
        "where e.task_id=? and r.decision <> 'accepted'", (task,))]])


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def fire_and_wait(base, pid, *jobs):
    for job in jobs:
        d.fire(base, job)
    d.wait_idle(pid)


def drive(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1110-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state["base"] = base
    d.api("PATCH", base, {"main_branch": "main"})
    code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    for name in (B1, R1, B2, R2):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    note = open_doc(base, pid, NOTE_DOC, "Note file", note_payload(), B1, R1)
    drv = open_doc(base, pid, DRIVE_DOC, "Greeting", drive_payload(), B2, R2)
    state["builds"] = [note["build"], drv["build"]]
    t1, dt, dep = note["tasks"]["t1"], drv["tasks"]["drive"], drv["tasks"]["build"]
    print(f"project {pid} root {root}\n  note t1 {t1} job {note['job']}\n"
          f"  drive {dt} dependent {dep} job {drv['job']}", flush=True)

    # 1. Both flows fire. A finished task's review is handed out at once, so the note's checker is
    # held busy (a seeded running run) until t1's branch has moved; the drive's flow runs on
    # through its builder, its reviewer and whatever that review lets start.
    hold_run, _ = d.hold(pid, R1)
    state["held"] = hold_run
    for _ in range(FIRINGS):
        fire_and_wait(base, pid, note["job"], drv["job"])
        if status_of(t1)[0] == "completed" and d.handouts(dt, review=True):
            break
    print(f"  after building: t1 {status_of(t1)} {evidence(t1)}\n"
          f"                  drive {status_of(dt)} {evidence(dt)}", flush=True)

    note_ev = [e for e in evidence(t1) if e[2] == "awaiting" and e[3]]
    note_ready = status_of(t1)[0] in ("completed", "under_review") and bool(note_ev)
    d.check("setup: t1 completed with awaiting evidence at a commit, not yet reviewed", note_ready,
            f"{status_of(t1)} {evidence(t1)}")
    drive_ready = any(e[1] == "drive_baseline" for e in evidence(dt))
    d.check("setup: the drive task recorded a drive_baseline row", drive_ready,
            f"{status_of(dt)} {evidence(dt)}")

    # 2. Move t1's branch past the evidence's commit A: a fix, then a merge of main.
    staged_b = None
    if note_ready:
        commit_a = note_ev[-1][3]
        worktree = root / ".agentweave" / "tasks" / t1
        try:
            (root / "OTHER.md").write_text("main moved on\n", encoding="utf-8")
            d.git(root, "add", "OTHER.md")
            d.git(root, "commit", "-q", "-m", "main moves on")
            with open(worktree / "NOTE.md", "a", encoding="utf-8") as fh:
                fh.write(FIX_LINE + "\n")
            d.git(worktree, "add", "NOTE.md")
            d.git(worktree, "commit", "-q", "-m", "fix after the evidence")
            d.git(worktree, "merge", "--no-ff", "--no-edit", "main")
            staged_b = git_out(worktree, "rev-parse", "HEAD")
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"  could not stage B: {exc}", flush=True)
        d.check("setup: t1's branch moved from A to B", bool(staged_b) and staged_b != commit_a,
                f"A {commit_a} B {staged_b}")

    # 3. The note's checker is let go and reviews at B; the drive's flow fires once more, so a
    # dependent that could start now is handed out.
    d.release(hold_run)
    state.pop("held", None)
    for _ in range(FIRINGS):
        fire_and_wait(base, pid, note["job"], drv["job"])
        if d.handouts(t1, review=True) and status_of(t1)[0] not in ("completed", "under_review"):
            break
    reviewed_note = bool(d.handouts(t1, review=True))
    reviewed_drive = bool(d.handouts(dt, review=True))
    d.fire(base, drv["job"])
    time.sleep(20)
    print(f"  after review: t1 {status_of(t1)} {evidence(t1)}\n"
          f"                drive {status_of(dt)} {evidence(dt)}\n"
          f"                dependent {status_of(dep)} handouts {d.handouts(dep, review=False)}",
          flush=True)

    # ac-reanchor-lands
    reach = note_ready and bool(staged_b) and reviewed_note
    accepted = [e for e in evidence(t1) if e[2] == "accepted"]
    # Accepted at B by the review itself: a send-back and a builder's re-recording is the
    # paperwork round this criterion removes, not a way to satisfy it.
    moves = [to for (to,) in d.ro("select to_status from task_transitions where task_id=? "
                                  "order by sequence", (t1,))]
    covered("R1", "ac-reanchor-lands", reach,
            any(e[3] == staged_b for e in accepted) and "revision_needed" not in moves,
            f"B {staged_b}; accepted footprints {[e[3] for e in accepted]}; t1 {status_of(t1)}; "
            f"moves {moves}")
    landed = ""
    if reach:
        d.poll(lambda: FIX_LINE in git_out(root, "show", "main:NOTE.md"), 120, every=5)
        landed = git_out(root, "show", "main:NOTE.md")
    ancestor = bool(staged_b) and subprocess.run(
        ["git", "merge-base", "--is-ancestor", staged_b, "main"], cwd=root).returncode == 0
    integrations = d.ro("select commit_sha, outcome, reason from task_integrations where task_id=?",
                        (t1,))
    covered("R2", "ac-reanchor-lands", reach, FIX_LINE in landed and ancestor,
            f"main:NOTE.md {landed!r}; B ancestor of main {ancestor}; integrations {integrations}")

    # ac-bad-baseline
    reach = drive_ready and reviewed_drive
    covered("K1", "ac-bad-baseline", reach, status_of(dt)[0] == "revision_needed",
            f"drive {status_of(dt)}")
    said = send_back_words(base, dt)
    covered("K2", "ac-bad-baseline", reach, UNREACHED in said and VACUOUS in said,
            said[:600] or "no send-back said anything")
    covered("K3", "ac-bad-baseline", reach,
            not d.handouts(dep, review=False) and status_of(dep)[0] not in ("in_progress", "completed"),
            f"dependent {status_of(dep)} handouts {d.handouts(dep, review=False)}")


def tidy(state):
    if state.get("held"):
        d.release(state["held"])
    base = state.get("base")
    for build in state.get("builds") or []:
        if base and build:
            code, _ = d.api("POST", f"{base}/project/builds/{build}/stop")
            print(f"stopped build {build}: {code}")


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
            tidy(state)
        finally:
            d.stop_hub(proc)
    print("\nper-check baseline:")
    for key in ("R1", "R2", "K1", "K2", "K3"):
        row = baseline.get(key)
        if row is None:
            print(f"check {key}: reached=no failed_at_assertion=no -- setup stopped before it")
            continue
        failed = row["reached"] and not row["passed"]
        print(f"check {key} ({row['criterion']}): reached={'yes' if row['reached'] else 'no'} "
              f"failed_at_assertion={'yes' if failed else 'no'} -- {row['detail'][:300]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on master f68059f, 2026-11-10, three runs (artefacts drive1110-reviewer-reproduces/211422,
# 212120, 213230). Every covered check is reached and fails at its own assertion:
#   R1  the note's checker sent t1 back once its branch had moved past A (revision_needed, evidence
#       held); the builder then took a whole turn, rewrote NOTE.md and re-recorded, so no accepted
#       footprint ever named B.
#   R2  what landed was that rework commit: main:NOTE.md reads `note`, without B's fix line, although
#       B is an ancestor of it.
#   K1  DriveChecker (Haiku) approved the baseline listing c-unreached (404) and c-vacuous (passed), in
#       all three runs.
#   K2  no send-back named either check. In 213230 the approving notes named both while approving, and
#       the first form of K2 passed on that: it now counts only a send-back's words.
#   K3  the dependent task was built and reviewed (under_review, then approved).
# The first run had no hold on the note's checker and reviewed t1 before B could be staged; the hold
# was added for that. R1's "never sent back" half ran in 213230. K2's send-back-only rule was added
# after 213230 and evaluated against its rows (no revision_needed move, no non-accepting decision),
# not re-run.
