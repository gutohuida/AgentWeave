"""Acceptance drive for `a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, 2026-11-21.

The change's first task (spdoc-a9382cf4b71e, task `acceptance-drive`), written before the build. It
covers criterion `acceptance-drive-two-profile-flow` (FR-3) and, once `builder-only-completes`
lands, FR-5's "no 'completed' transition by QA". It takes the F1199 replication (fresh Hub :8032,
profile f1199repro: a plain reply from Developer landing in QA's task-bound thread, and QA completing
the task from there) to a whole flow: a fresh Hub, two Haiku profiles -- Developer (builder) and QA
(checker), the shape onboarding recommends -- and an approved one-task change built as a flow at
Reviewed, landing on main. The task's description has Developer build it and then ask QA, by a
message naming the task, to record its evidence and complete it, so a QA thread completes the task
and records evidence for it, as QA did in the 11-21 drive. When QA's completion is refused (the
builder-only guard), QA tells Developer and Developer completes it: QA's thread has still recorded
the evidence, which excludes it from the review as much as completing does.

Setup (fatal, not a criterion check): a QA thread completed the task or recorded evidence for it,
outside any review -- the condition the rest needs; its lineages are the "authoring" lineages.

Checks, each reached or not and passed or failed at its own assertion:

  R1  a review of the task is queued for QA into a conversation whose lineage is none of those
  V1  a verdict on the task (approved, revision_needed or rejected) is given by a QA run in that
      fresh lineage
  S1  no `review_unstaffed` stall is opened for the task
  G1  no transition of the task to `completed` was made by a QA run (FR-5; red until the
      builder-only guard lands, by design)

Hub: AW_HUB, AW_KEY and AW_DB name an already-running fresh drive Hub (its URL, its bootstrap key,
its database file). Without them the drive starts one itself from this checkout's `hub/` on
AW_DRIVE_PORT (default 8033) with a new database under the drive's temp directory, and stops it at
the end. Never the trial Hub's database, never :8000. The flow's cron fires once a year; the drive
fires it itself. About four to six Haiku turns, 10-30 minutes.

    py -3.11 scripts/drive/d1121_f1199_two_profile_flow.py
"""

import os
import pathlib
import secrets
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1121-two-profile-flow" / d.STAMP
if os.environ.get("AW_HUB"):
    d.HUB = os.environ["AW_HUB"].rstrip("/")
    d.KEY = os.environ["AW_KEY"]
    d.DB = pathlib.Path(os.environ["AW_DB"])
    OWN_HUB = False
else:
    d.PORT = int(os.environ.get("AW_DRIVE_PORT") or 8033)
    d.HUB = f"http://127.0.0.1:{d.PORT}"
    d.KEY = "aw_live_" + secrets.token_hex(16)
    d.DB = d.TMP / "agentweave.db"
    OWN_HUB = True

HAIKU = "claude-haiku-5-5"
DOC = "spec/changes/hello-two-profiles/spec.json"
DEV, QA = "Developer", "QA"
REQ = "hello"
YEARLY = "0 0 1 1 *"
FIRINGS = 6
CHECKS = ("R1", "V1", "S1", "G1")
VERDICTS = ("approved", "revision_needed", "rejected")

baseline = {}


def covered(key, reached, ok=False, detail=""):
    baseline[key] = {"reached": bool(reached), "passed": bool(reached and ok), "detail": detail}
    name = f"acceptance-drive-two-profile-flow {key}"
    d.check(name if reached else f"{name} (not reached)", bool(reached and ok), detail)


DESCRIPTION = (
    "Goal: hello.txt at the repository root holds the single line `hello`.\n\n"
    "How this task is worked (follow it exactly; it is a drive of who may do what):\n"
    "- Builder (Developer): create hello.txt holding `hello`, then `git add hello.txt` and "
    "`git commit -m hello`. Do NOT call record_evidence and do NOT move the task to completed. "
    "Instead call send_message to QA, passing this task's id as task_id, asking QA to record the "
    "evidence for requirement `hello` and then move this task to completed. Then end your turn. "
    "If you have already sent that message, do nothing more unless QA tells you its completion "
    "was refused: then call record_evidence yourself (command `cat hello.txt`, its output, covers "
    "`full`) and move the task to completed.\n"
    "- QA, when Developer asks you to (a message, not a review): run `cat hello.txt` (the file is "
    "on this task's branch if it is not in your directory: `git show <that branch>:hello.txt`), "
    f"call record_evidence for requirement `hello` (document {DOC}) with this task's id, that "
    "command, its output and covers `full`, then call update_task to move this task to completed. "
    "If that move is refused, call send_message to Developer saying the completion was refused "
    "and Developer should complete it.\n"
    "- Reviewer (a review turn of this task): run `cat hello.txt`; where it reads `hello`, accept "
    "the evidence with your own reproduction at the current commit and approve the task."
)


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Hello, two profiles",
        "summary": "The repository says hello.", "problem": "The repository has no hello.txt.",
        "scope": {"in_scope": ["hello.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": REQ, "modal": "MUST",
                          "statement": "The repository MUST hold hello.txt reading hello."}],
        "acceptance_criteria": [{
            "key": "says-hello", "requirement": REQ, "given": "the repository",
            "when": "hello.txt is read", "then": "it reads hello",
            "how_to_check": "cat hello.txt", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Add hello.txt", "description": DESCRIPTION,
                   "requirements": [REQ], "files": ["hello.txt"],
                   "builder": DEV, "checker": QA}],
        "delivery": {"mode": "flow", "agent": DEV, "checker": QA,
                     "stop_when_queue_empties": True, "cron": YEARLY,
                     "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def lineage_of_run(run_id):
    rows = d.ro("select coalesce(c.lineage_id, c.id) from runs r join conversations c "
                "on c.id = r.conversation_id where r.id = ?", (run_id,))
    return rows[0][0] if rows else None


def lineage_of_conversation(conversation_id):
    rows = d.ro("select coalesce(lineage_id, id) from conversations where id = ?",
                (conversation_id,))
    return rows[0][0] if rows else None


def authoring(task_id):
    """QA's runs that completed the task or recorded evidence, outside a review: run -> what."""
    facts = {}
    for (run,) in d.ro("select run_id from task_transitions where task_id = ? and "
                       "actor_agent = ? and to_status = 'completed'", (task_id, QA)):
        facts.setdefault(run, set()).add("completed")
    for (run,) in d.ro("select run_id from requirement_evidence where actor = ? and "
                       "(task_id = ? or task_id is null)", (QA, task_id)):
        facts.setdefault(run, set()).add("recorded evidence")
    reviews = {r for (r,) in d.ro("select delivered_in_run_id from inbound_queue_entries "
                                  "where review_task_id = ? and delivered_in_run_id is not null",
                                  (task_id,))}
    return {run: what for run, what in facts.items() if run not in reviews}


def review_entries(task_id):
    """QA review entries for the task: (entry id, state, conversation lineage, run)."""
    out = []
    for eid, state, conv, run in d.ro(
            "select id, state, conversation_id, delivered_in_run_id from inbound_queue_entries "
            "where review_task_id = ? and agent = ? order by sequence", (task_id, QA)):
        lineage = lineage_of_conversation(conv) if conv else None
        if lineage is None and run:
            lineage = lineage_of_run(run)
        out.append((eid, state, lineage, run))
    return out


def unstaffed(task_id):
    return d.ro("select id, reason, outcome from stalls where cause = 'review_unstaffed' and "
                "task_id = ?", (task_id,))


def drive(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1121-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state["base"] = base
    d.api("PATCH", base, {"main_branch": "main"})
    code, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude",
                                                     "model": HAIKU})
    d.check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    for name in (DEV, QA):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Hello, two profiles", "kind": "change-spec", "path": DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    d.check("setup: the document is saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = d.as_agent(pid, QA, "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": "says-hello", "kind": "new"}]})
    d.check("setup: the criterion is confirmed", code == 200, f"{code} {str(out)[:400]}")
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builder": DEV, "checker": QA,
                       "landing": "main"})
    d.check("setup: the document is built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    state["build"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = d.ro("select t.id, t.loop_id from tasks t join spec_documents s on "
                "t.spec_document_id = s.id where s.project_id = ? and s.path = ?", (pid, DOC))
    d.check("setup: the task materialised", len(rows) == 1, f"{rows}", fatal=True)
    task, loop = rows[0]
    job = d.ro("select job_id from loops where id = ?", (loop,))[0][0]
    print(f"project {pid} root {root}\n  task {task} job {job}", flush=True)

    for _ in range(FIRINGS):
        d.fire(base, job)
        d.wait_idle(pid)
        status = d.ro("select status from tasks where id = ?", (task,))[0][0]
        stalls = unstaffed(task)
        print(f"  after firing: task {status}; review_unstaffed stalls {stalls}", flush=True)
        if status in VERDICTS or (stalls and authoring(task)):
            break

    facts = authoring(task)
    lineages = {run: lineage_of_run(run) for run in facts}
    d.check("setup: a QA thread completed the task or recorded evidence, outside a review",
            bool(facts),
            "QA runs outside a review that worked the task: "
            + (", ".join(f"{run} ({', '.join(sorted(what))}; lineage {lineages[run]})"
                         for run, what in facts.items()) or "none"), fatal=True)
    reached = True
    authored = set(lineages.values())
    # A fact with no lineage excludes the whole agent (design D1), so no thread can be "fresh".
    named_only = None in authored

    entries = review_entries(task)
    fresh = [e for e in entries if e[2] is not None and e[2] not in authored]
    covered("R1", reached, bool(fresh) and not named_only,
            f"QA review entries (id, state, lineage, run): {entries}; authoring lineages "
            f"{sorted(map(str, authored))}")

    verdicts = d.ro("select to_status, run_id, actor_agent from task_transitions where "
                    "task_id = ? and to_status in ('approved', 'revision_needed', 'rejected') "
                    "order by sequence", (task,))
    fresh_lineages = {e[2] for e in fresh}
    by_fresh = [v for v in verdicts if v[2] == QA and v[1] and lineage_of_run(v[1]) in fresh_lineages]
    covered("V1", reached, bool(by_fresh),
            f"verdicts (to, run, agent): {verdicts}; by a fresh QA thread: {by_fresh}")

    stalls = unstaffed(task)
    covered("S1", reached, not stalls, f"review_unstaffed stalls for the task: {stalls}")

    completions = d.ro("select t.run_id, t.actor_agent, r.agent from task_transitions t left join "
                       "runs r on r.id = t.run_id where t.task_id = ? and "
                       "t.to_status = 'completed' order by t.sequence", (task,))
    by_qa = [c for c in completions if QA in (c[1], c[2])]
    covered("G1", bool(completions), not by_qa,
            f"completions (run, actor, run agent): {completions}; by QA: {by_qa}")


def tidy(state):
    base, build = state.get("base"), state.get("build")
    if base and build:
        code, _ = d.api("POST", f"{base}/project/builds/{build}/stop")
        print(f"stopped build {build}: {code}")


def main():
    d.TMP.mkdir(parents=True, exist_ok=True)
    proc = None
    if OWN_HUB:
        if d.api("GET", "/projects")[0] != 0:
            sys.exit(f"something already answers on :{d.PORT}; name it with AW_HUB/AW_KEY/AW_DB "
                     "or choose another AW_DRIVE_PORT")
        proc = d.start_hub()
    print(f"Hub {d.HUB} database {d.DB}", flush=True)
    state = {}
    started = time.time()
    try:
        drive(state)
    except d.Stop:
        pass
    finally:
        try:
            tidy(state)
        finally:
            d.stop_hub(proc)
    print(f"\nper-check baseline ({int(time.time() - started)}s):")
    for key in CHECKS:
        row = baseline.get(key)
        if row is None:
            print(f"check {key}: reached=no failed_at_assertion=no -- setup stopped before it")
            continue
        failed = row["reached"] and not row["passed"]
        print(f"check {key}: reached={'yes' if row['reached'] else 'no'} "
              f"failed_at_assertion={'yes' if failed else 'no'} -- {row['detail'][:600]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Re-run with A0 made a fatal setup step: run 150428 (own Hub :8037, 98 s, exit 1), same outcome
# (QA run-d6d8f90d0342 completed + recorded evidence; review_unstaffed stall-9d72572858d3).
# Observed on pre-build code (branch agentweave/task/task-09dd80eb9515 at 96fa0c8, master's line),
# 2026-11-21, run 144918 (artefacts drive1121-two-profile-flow/144918, own Hub :8033 on a new
# database, 37 s, one firing). Exit 1. Developer built hello.txt and messaged QA naming the task;
# QA's message turn (run-41eff2389112, lineage conv-b510758a57a4) recorded the evidence and moved
# the task to completed. The flow then opened review_unstaffed stall-33766b552a0d: "this task names
# 'QA' as its reviewer, and that agent is the one that completed this task. Naming a different
# reviewer, or reviewing it yourself, is the way forward -- the flow will not substitute somebody
# else for a named reviewer." -- the 11-21 deadlock (stall-442d07c7b549), replicated by a flow.
#   setup passes: QA's thread completed the task and recorded evidence outside a review.
#   R1  fails: no review entry was queued for QA at all.
#   V1  fails: no verdict.
#   S1  fails: the review_unstaffed stall above.
#   G1  fails: QA made the task's only 'completed' transition (red until builder-only-completes).
