"""Acceptance drive for `fold-duplicate-agents-into-one-profile-with-their-history-kept`, 2026-11-20.

The change's first task (spdoc-70f63e0ae27e, task `acceptance-drive`), written before the build. It
covers criterion `drive-fold-a-roster` (FR-9, with FR-3's pool merge and FR-12's addressing
refusal) on a fresh scratch project on the trial Hub, spending no agent turn:

  setup  runners Haiku and Sonnet; agents Developer (Haiku), DeveloperOpus (Sonnet), QA and QA2
         (Haiku), Developer and QA holding the evidence-acceptance grant; an approved one-requirement
         document; a task DeveloperOpus claimed, recorded evidence for and completed, so it waits
         for review; an enabled job (cron once a year) whose agent is QA2; seeded finished runs of
         all four agents, and a saved dashboard counting those runs by agent name, run once.
  fold   the operator opens the fold preview and folds DeveloperOpus into Developer and QA2 into
         QA, through the routes the agent settings' "Fold into..." dialog calls.

Then the checks, every one after the fold:

  F1  the preview (GET /agents/{name}/fold?into=) answers 200 with can_fold true, for both folds
  F2  the fold (POST /agents/{name}/fold) answers 200 naming folded_into, for both folds
  PL  Developer's pool holds the Haiku and the Sonnet runner, Haiku still its default (FR-3)
  PK  GET /agents (the list every picker reads) leaves DeveloperOpus and QA2 out, and GET
      /agents?lifecycle=all shows each folded_into its profile
  JB  the job's agent is now QA
  EV  Developer, deciding DeveloperOpus's evidence, is refused naming its profile (FR-9)
  RV  Developer, taking the task into review and approving it, is refused naming its profile, and
      the task is not approved (FR-9)
  QA  QA takes it into review, accepts its evidence and approves it: the task ends approved by QA
  MS  send_message from QA to DeveloperOpus is refused 409 agent_folded naming Developer (FR-12)
  DB  the saved dashboard returns the same rows as before the fold
  GP  a query grouping the seeded runs by coalesce(agents.folded_into, runs.agent) returns one
      Developer and one QA row, summing their folded agents' runs

Agent-plane calls are made as each agent through a seeded running run with its own credential
(`initiator` autonomous, id `run-d1119-...`), as `d1029`'s drive does; autonomous so that the
task's moves keep the map's edges and author checks (`is_free_mover`), as a flow's turns do. While
an agent is addressed (DeveloperOpus building, DeveloperOpus messaged) it holds such a run, so
today's code queues rather than launches a turn; the drive withdraws what it queued before
releasing the run.

The contract the drive assumes, from the design's Contract section, kept in one place for the
builders to meet or adjust (`fold_preview`, `fold`, `names_profile`):
  - GET /projects/{pid}/agents/{name}/fold?into={profile} -> 200 {"can_fold", "refusals", ...};
  - POST /projects/{pid}/agents/{name}/fold {"into"} -> 200 {"folded_into", "profile": {"pool"}};
  - agent reads carry `folded_into`; a folded agent is out of lifecycle=open;
  - addressing a folded name answers 409 detail {"code": "agent_folded", "folded_into"};
  - an independence refusal of a profile's run names the profile and the folded author: its text
    holds both "Developer" as the profile and "DeveloperOpus" as the name the work was done under
    (`names_profile`); RV judges the independence refusals (403) alone, since a move the lifecycle
    then refuses (409, e.g. completed -> approved once under_review was refused) is not one.

Each check is reported as reached or not, and as passed or failed at its own assertion, in the
per-check baseline printed at the end (`check <key>: reached=<yes|no> failed_at_assertion=<yes|no>
-- <detail>`). A check whose setup did not happen reads `not reached`, never `failed`. The fold
failing does not stop the drive: every later check runs on the unfolded roster, which is how each
fails at its own assertion on pre-build code.

Scratch Hub: the trial Hub on AW_DRIVE_PORT (default 8010), reused when one answers there and
otherwise started from this checkout's `hub/` on AW_DRIVE_DB (default: the trial profile's
database). Never :8000. Under a minute; no agent turn.

    py -3.11 scripts/drive/d1119_fold_roster.py
"""

import datetime
import hashlib
import json
import secrets
import sqlite3
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1119-fold-roster" / d.STAMP
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
DOC = "spec/changes/fold-work/spec.json"
DEV, DEV_OPUS, QA, QA2 = "Developer", "DeveloperOpus", "QA", "QA2"
FOLDS = ((DEV_OPUS, DEV), (QA2, QA))
YEARLY = "0 0 1 1 *"
# Seeded finished runs per agent, for the dashboard and the per-profile query.
SEEDED = {DEV: 1, DEV_OPUS: 2, QA: 1, QA2: 3}
SEED_PREFIX = "run-d1119-seed-"
DASHBOARD_SQL = (f"select agent, count(*) as runs from runs where id like '{SEED_PREFIX}%' "
                 "group by agent order by agent")
PROFILE_SQL = (f"select coalesce(a.folded_into, r.agent) as profile, count(*) as runs "
               f"from runs r join agents a on a.name = r.agent where r.id like '{SEED_PREFIX}%' "
               "group by profile order by profile")
CHECKS = ("F1", "F2", "PL", "PK", "JB", "EV", "RV", "QA", "MS", "DB", "GP")

baseline = {}


def covered(key, reached, ok=False, detail=""):
    """One covered check. Not reached is reported as such and never counted as its assertion."""
    baseline[key] = {"reached": bool(reached), "passed": bool(reached and ok), "detail": detail}
    name = f"drive-fold-a-roster {key}"
    d.check(name if reached else f"{name} (not reached)", bool(reached and ok), detail)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _write(sql, args=()):
    con = sqlite3.connect(d.DB.as_posix(), timeout=30)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


class Run:
    """A running run of `agent` with its own credential, as the Hub tests seed one: the agent
    reads as busy while it lives, and agent-plane calls through it act as that agent."""

    def __init__(self, pid, agent):
        self.pid, self.agent = pid, agent
        self.token = "aw_run_" + secrets.token_urlsafe(24)
        self.id = "run-d1119-" + secrets.token_hex(4)
        _write("insert into runs (id, project_id, agent, status, started_at, initiator, "
               "turn_depth, capability_token_hash) values (?, ?, ?, 'running', ?, 'autonomous', "
               "0, ?)", (self.id, pid, agent, _now(),
                         hashlib.sha256(self.token.encode("utf-8")).hexdigest()))

    def call(self, method, path, body=None):
        return d.api(method, "/agent-actions" + path, body, key=self.token)

    def end(self):
        # What today's code queued for this agent while it was busy is withdrawn first, so its
        # release launches no turn.
        _write("update inbound_queue_entries set state='withdrawn', withdrawn_at=? where "
               "project_id=? and agent=? and delivered_at is null and withdrawn_at is null",
               (_now(), self.pid, self.agent))
        _write("update runs set status='completed', ended_at=? where id=?", (_now(), self.id))


def as_agent(pid, agent, method, path, body=None):
    run = Run(pid, agent)
    try:
        return run.call(method, path, body)
    finally:
        run.end()


def seed_runs(pid):
    for agent, count in SEEDED.items():
        for _ in range(count):
            _write("insert into runs (id, project_id, agent, status, started_at, ended_at, "
                   "initiator, turn_depth) values (?, ?, ?, 'completed', ?, ?, 'autonomous', 0)",
                   (SEED_PREFIX + secrets.token_hex(4), pid, agent, _now(), _now()))


def agents(base, lifecycle="open"):
    code, out = d.api("GET", f"{base}/agents?lifecycle={lifecycle}")
    rows = out if isinstance(out, list) else (out or {}).get("agents") or []
    return {r.get("name"): r for r in rows if isinstance(r, dict)}


def fold_preview(base, name, into):
    return d.api("GET", f"{base}/agents/{name}/fold?into={urllib.parse.quote(into)}")


def fold(base, name, into):
    return d.api("POST", f"{base}/agents/{name}/fold", {"into": into})


def refused(code, out):
    return code is not None and 400 <= code < 500


def names_profile(out):
    """An independence refusal naming the profile and the folded name the work was done under."""
    text = json.dumps(out)
    return DEV_OPUS in text and DEV in text.replace(DEV_OPUS, "")


def independence_refused(code):
    """An independence refusal is a 403; a 409 is the lifecycle refusing an edge, not a verdict."""
    return code == 403


def short(value, n=300):
    return json.dumps(value)[:n] if not isinstance(value, str) else value[:n]


def task_row(task_id):
    return d.ro("select status, assignee from tasks where id=?", (task_id,))[0]


def approved_by(task_id):
    rows = d.ro("select actor_agent, to_status from task_transitions where task_id=? "
                "order by created_at", (task_id,))
    return [agent for agent, to in rows if to == "approved"]


def setup(state):
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"d1119f-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(pid=pid, base=base, root=root)
    d.api("PATCH", base, {"main_branch": "main"})
    runners = {}
    for label, model in (("Haiku", HAIKU), ("Sonnet", SONNET)):
        code, out = d.api("POST", f"{base}/runners", {"name": label, "cli": "claude", "model": model})
        d.check(f"setup: a {label} runner", code in (200, 201), f"{code} {out}", fatal=True)
        runners[label] = out["id"]
    state["runners"] = runners
    for name, runner in ((DEV, "Haiku"), (DEV_OPUS, "Sonnet"), (QA, "Haiku"), (QA2, "Haiku")):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runners[runner]})
        d.check(f"setup: agent {name} on {runner}", code in (200, 201), f"{code} {out}", fatal=True)
    for name in (DEV, QA):
        code, out = d.api("PATCH", f"{base}/agents/{name}", {"can_accept_evidence": True})
        d.check(f"setup: {name} may decide evidence", code == 200, f"{code} {short(out)}",
                fatal=True)

    # An approved one-requirement document, so the task's evidence has a requirement.
    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": "Fold work", "kind": "change-spec", "path": DOC})
    d.check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    document = {
        "schema_version": 1, "kind": "change-spec", "title": "Fold work",
        "summary": "One file.", "problem": "There is no file.",
        "scope": {"in_scope": ["work.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "work", "modal": "MUST",
                          "statement": "The repository MUST hold work.txt."}],
        "acceptance_criteria": [{
            "key": "work-exists", "requirement": "work", "given": "the repository",
            "when": "work.txt is read", "then": "it holds one line",
            "how_to_check": "cat work.txt", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Add work.txt", "requirements": ["work"],
                   "files": ["work.txt"], "description": "Add work.txt."}],
        "delivery": {"mode": "none", "reasons": {"mode": "The drive files its own task."}},
    }
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": document})
    d.check("setup: the document is saved", code == 200, f"{code} {short(out, 600)}", fatal=True)
    code, out = as_agent(pid, QA, "POST", "/spec/documents/confirm-criteria", {
        "path": DOC, "confirmations": [{"criterion": "work-exists", "kind": "new"}]})
    d.check("setup: the criterion is confirmed", code == 200, f"{code} {short(out, 400)}")
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": (read or {}).get("content_version")})
    d.check("setup: the document is approved", code == 200, f"{code} {short(out, 600)}", fatal=True)
    identifier = d.ro("select r.identifier from spec_requirements r join spec_documents s on "
                      "r.document_id = s.id where s.project_id=? and s.path=?", (pid, DOC))[0][0]

    # DeveloperOpus files, builds and completes the task, recording evidence, in one held run.
    work = Run(pid, DEV_OPUS)
    try:
        code, task = work.call("POST", "/tasks", {
            "title": "Add work.txt", "description": "Add work.txt.", "assignee": DEV_OPUS,
            "builder": DEV_OPUS, "spec_document": DOC, "requirement_ids": [identifier]})
        d.check("setup: DeveloperOpus files the task", code == 201, f"{code} {short(task, 600)}",
                fatal=True)
        task_id = task["id"]
        state["task"] = task_id
        code, out = work.call("PATCH", f"/tasks/{task_id}", {"status": "in_progress"})
        d.check("setup: DeveloperOpus claims it", code == 200, f"{code} {short(out, 600)}",
                fatal=True)
        (root / "work.txt").write_text("work\n", encoding="utf-8")
        code, evidence = work.call("POST", "/spec/evidence", {
            "identifier": identifier, "document": DOC, "task_id": task_id,
            "summary": "work.txt holds one line", "command": "cat work.txt", "output": "work",
            "covers": "full"})
        d.check("setup: DeveloperOpus records evidence", code in (200, 201),
                f"{code} {short(evidence, 600)}", fatal=True)
        state["evidence"] = evidence["id"]
        code, out = work.call("PATCH", f"/tasks/{task_id}", {"status": "completed"})
        d.check("setup: DeveloperOpus completes it", code == 200, f"{code} {short(out, 800)}",
                fatal=True)
    finally:
        work.end()
    status = task_row(task_id)[0]
    review_state = d.ro("select review_state from requirement_evidence where id=?",
                        (state["evidence"],))[0][0]
    d.check("setup: the task waits for review with its evidence awaiting",
            status == "completed" and review_state == "awaiting",
            f"task {status}, evidence {review_state}", fatal=True)

    code, job = d.api("POST", f"{base}/jobs", {
        "name": "qa2-sweep", "agent": QA2, "message": "Sweep.", "cron": YEARLY, "enabled": True})
    d.check("setup: an enabled job whose agent is QA2", code == 201 and job.get("enabled"),
            f"{code} {short(job)}", fatal=True)
    state["job"] = job["id"]

    seed_runs(pid)
    code, dash = d.api("POST", f"{base}/dashboards", {
        "name": "Runs by agent", "description": "How many runs each agent name has.",
        "panels": [{"title": "Runs by agent", "query": DASHBOARD_SQL, "kind": "bar"}]})
    d.check("setup: a dashboard counting runs by agent name", code == 201,
            f"{code} {short(dash)}", fatal=True)
    state["dashboard"] = dash.get("id") or (dash.get("dashboard") or {}).get("id")
    code, before = d.api("GET", f"{base}/dashboards/{state['dashboard']}/run")
    state["dashboard_before"] = [p.get("rows") for p in (before or {}).get("panels") or []]
    d.check("setup: the dashboard runs", code == 200 and state["dashboard_before"] != [None],
            f"{code} rows {state['dashboard_before']}", fatal=True)
    print(f"project {pid} root {root}\n  task {task_id} evidence {state['evidence']} "
          f"job {state['job']} dashboard {state['dashboard']} runners {runners}", flush=True)


def drive(state):
    setup(state)
    pid, base, task_id = state["pid"], state["base"], state["task"]
    runners = state["runners"]

    # The fold, as the dialog does it: the preview, then the confirm.
    previews, folds = [], []
    for name, into in FOLDS:
        code, out = fold_preview(base, name, into)
        previews.append((name, into, code, out))
        code2, out2 = fold(base, name, into)
        folds.append((name, into, code2, out2))
    covered("F1", True, all(c == 200 and (o or {}).get("can_fold") is True
                            for _, _, c, o in previews),
            "; ".join(f"preview {n}->{i}: {c} {short(o, 160)}" for n, i, c, o in previews))
    covered("F2", True, all(c == 200 and (o or {}).get("folded_into") == i
                            for _, i, c, o in folds),
            "; ".join(f"fold {n}->{i}: {c} {short(o, 160)}" for n, i, c, o in folds))

    # PL: Developer's pool holds both runners, Haiku its default.
    pool = (agents(base, "all").get(DEV) or {}).get("pool") or []
    got = sorted((e.get("runner_id"), bool(e.get("default"))) for e in pool)
    want = sorted([(runners["Haiku"], True), (runners["Sonnet"], False)])
    covered("PL", True, got == want, f"Developer's pool {short(pool, 400)}; want {want}")

    # PK: out of the pickers' list, folded_into on the full list.
    open_names = sorted(agents(base, "open"))
    every = agents(base, "all")
    marks = {n: (every.get(n) or {}).get("folded_into", "<no field>") for n, _ in FOLDS}
    covered("PK", True,
            DEV_OPUS not in open_names and QA2 not in open_names
            and marks == {DEV_OPUS: DEV, QA2: QA},
            f"open agents {open_names}; folded_into {marks}")

    # JB: the job names QA.
    code, job = d.api("GET", f"{base}/jobs/{state['job']}")
    covered("JB", code == 200, (job or {}).get("agent") == QA,
            f"{code} job agent {(job or {}).get('agent')!r}, enabled {(job or {}).get('enabled')}")

    # EV: Developer deciding DeveloperOpus's evidence is refused naming its profile.
    code, out = as_agent(pid, DEV, "POST", f"/spec/evidence/{state['evidence']}/decision", {
        "decision": "accepted", "reason": "The drive: Developer decides DeveloperOpus's evidence."})
    review_state = d.ro("select review_state from requirement_evidence where id=?",
                        (state["evidence"],))[0][0]
    covered("EV", True, refused(code, out) and names_profile(out) and review_state == "awaiting",
            f"{code} {short(out, 400)}; evidence now {review_state}")

    # RV: Developer taking the task into review and approving it is refused naming its profile.
    review = Run(pid, DEV)
    try:
        moves = []
        for to in ("under_review", "approved"):
            code, out = review.call("PATCH", f"/tasks/{task_id}", {
                "status": to, "notes": "The drive: Developer reviews DeveloperOpus's task."})
            moves.append((to, code, out))
    finally:
        review.end()
    status = task_row(task_id)[0]
    # Only the independence refusals are judged: with under_review refused, the approve that
    # follows meets the lifecycle's 409 (completed -> approved), which names no profile.
    refusals = [(to, c, o) for to, c, o in moves if independence_refused(c)]
    covered("RV", True,
            bool(refusals) and all(names_profile(o) for _, _, o in refusals)
            and all(refused(c, o) for _, c, o in moves)
            and status == "completed" and DEV not in approved_by(task_id),
            "; ".join(f"{to}: {c} {short(o, 220)}" for to, c, o in moves)
            + f"; task now {status}")

    # QA: QA's review goes through and approves the task.
    review = Run(pid, QA)
    try:
        steps = []
        code, out = review.call("PATCH", f"/tasks/{task_id}", {
            "status": "under_review", "notes": "The drive: QA reviews it."})
        steps.append(("under_review", code, out))
        code, out = review.call("PATCH", f"/tasks/{task_id}", {
            "status": "approved", "notes": "The drive: work.txt holds one line."})
        steps.append(("approved", code, out))
    finally:
        review.end()
    status, holder = task_row(task_id)
    by = approved_by(task_id)
    covered("QA", True, status == "approved" and by == [QA],
            "; ".join(f"{to}: {c} {short(o, 220)}" for to, c, o in steps)
            + f"; task now {status} (assignee {holder}), approved by {by}")

    # MS: a message to DeveloperOpus is refused naming Developer. DeveloperOpus is held busy, so
    # a message today's code accepts queues instead of launching a turn.
    held = Run(pid, DEV_OPUS)
    try:
        code, out = as_agent(pid, QA, "POST", "/messages", {
            "recipient": DEV_OPUS, "subject": "Drive", "content": "The drive: are you there?",
            "type": "message"})
    finally:
        held.end()
    detail = (out or {}).get("detail") if isinstance(out, dict) else None
    covered("MS", True,
            code == 409 and isinstance(detail, dict) and detail.get("code") == "agent_folded"
            and detail.get("folded_into") == DEV and DEV in str(detail.get("message")),
            f"{code} {short(out, 400)}")

    # DB: the saved dashboard returns the same rows as before.
    code, after = d.api("GET", f"{base}/dashboards/{state['dashboard']}/run")
    rows_after = [p.get("rows") for p in (after or {}).get("panels") or []]
    folded_now = all((agents(base, "all").get(n) or {}).get("folded_into") == i for n, i in FOLDS)
    covered("DB", True, code == 200 and rows_after == state["dashboard_before"] and folded_now,
            f"{code} before {state['dashboard_before']} after {rows_after}; "
            f"both folds recorded {folded_now}")

    # GP: grouping by profile sums the folded agents into their profiles.
    code, out = d.api("POST", f"{base}/dashboards/query", {"sql": PROFILE_SQL})
    rows = (out or {}).get("rows") if isinstance(out, dict) else None
    want = [[DEV, SEEDED[DEV] + SEEDED[DEV_OPUS]], [QA, SEEDED[QA] + SEEDED[QA2]]]
    covered("GP", True, code == 200 and [list(r) for r in rows or []] == want,
            f"{code} rows {rows!r} want {want}; {short(out, 300) if code != 200 else ''}")


def tidy(state):
    base, job = state.get("base"), state.get("job")
    if base and job:
        code, _ = d.api("PATCH", f"{base}/jobs/{job}", {"enabled": False})
        print(f"disabled job {job}: {code}")


def main():
    proc = d.start_hub()
    state = {}
    d.TMP.mkdir(parents=True, exist_ok=True)
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
              f"failed_at_assertion={'yes' if failed else 'no'} -- {row['detail'][:400]}")
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on pre-build code (branch agentweave/task/task-25ac322a4e64 at 90a6df0, migration head
# 0187), 2026-11-20, run 001746 (3 s, no agent turn). The Hub already on :8010 answered 500 to
# every POST /projects/open, so the run used a Hub started from this checkout on a fresh database:
#   AW_DRIVE_PORT=8019 AW_DRIVE_DB=<temp>/drive1119-fold-roster/fresh-001746.db
# Every setup step passed and every check is reached and fails at its own assertion:
#   F1/F2  GET and POST /agents/{name}/fold are 404 for both folds.
#   PL     Developer's pool is Haiku alone; the Sonnet entry did not join it.
#   PK     the open list still offers DeveloperOpus and QA2; no agent row carries folded_into.
#   JB     the job's agent is still QA2.
#   EV     Developer's decision on DeveloperOpus's evidence was accepted (200, now accepted).
#   RV     Developer took DeveloperOpus's task into review and approved it (200, 200): the hole.
#   QA     QA could not review it: already approved by Developer.
#   MS     send_message from QA to DeveloperOpus was accepted (201); queued while held, withdrawn.
#   DB     the dashboard's rows are unchanged, but neither fold is recorded.
#   GP     the per-profile query fails: no such column a.folded_into.
