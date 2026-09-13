"""D-1 2026-09-12: F319's unverified reach, live, through real routes only.

F319 (night window, 2026-09-12) was measured at unit level: `trigger_agent_directly` stages a review
with `enter_selected_task` -- which writes `task.assignee` and travels `-> under_review` -- and then
may refuse. `turn_scheduler` catches that `TriggerAgentError` and commits **the same session** to
record `waiting_reason` (`turn_scheduler.py:349`), so whatever the staging wrote is committed with
it. Two questions were left unverified, and this file asks them of a live Hub:

  (b) **After staging.** `prepare_review_turn` raises `ReviewTurnRefused` *after*
      `enter_selected_task` succeeded (`agent_trigger.py:847-858`). The operator route's own
      pre-check, `commit_for_task_review`, reads the database only. Three of `prepare_review_turn`'s
      refusals read the *repository* -- the commit is gone, the project is not a git repository, the
      reviewer's checkout path is obstructed -- so none of them is asked before the task is staged.
        B1  the evidence's commit is pruned from the repository after it was recorded
        B2  the reviewer's review-checkout path is a plain directory, not a registered worktree
  (a) **The entry guard, with no drift.** The route asks `review_dispatch_refusal` when the entry is
      *queued*; the dispatch asks the entry guard when the entry is *delivered*. An entry that waits
      behind a running turn is delivered later, and an agent can become the evidence author in
      between. Leg A queues a review for an agent while that agent's own (Haiku) turn is running and
      about to record evidence for the same task.
  C   4.5, live: a task whose only evidence is operator-kind reaches a real review turn.
  F   F320 (added 2026-09-13, a-refused-review-leaves-nothing-behind 5.1): a review H queued for X
      behind X's own running turn is refused at every delivery, and a plain message M waits behind
      it in another conversation. The pass that gives H up either stops (the defect: M queued at 0
      attempts, no run) or goes on and delivers M.

AW_EXPECT selects what is asserted (a-refused-review-leaves-nothing-behind 5.1):
  prefix (default)  the defect is REACHED -- the refused dispatch left the task staffed, D9 refuses
                    a second reviewer as "already under review", and F stops after giving up on H.
  fixed             every leg's task row and transition count equal a snapshot taken immediately
                    before the dispatch, no refused reviewer has a run, D9 does not refuse a second
                    reviewer as "already under review", and F delivers M in the pass that gives H up.

The proof is read from the drive database (`tasks`, `task_transitions`, `runs`,
`inbound_queue_entries`, `requirement_evidence`), read-only, not from a response alone.

    AW_HUB=http://127.0.0.1:8016 AW_KEY=... AW_PROJECT=proj-... AW_DB=<path> \
        AW_EXPECT=prefix|fixed py -3.11 scripts/drive/t_d1_0912_f319_reach.py [B|A|F|C ...]

Real surface only. No row inserts. Haiku turns. LEAVES NO JOB ENABLED (it creates none).
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0", "proj-d85a82bf4216") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project.")
    sys.exit(1)
DB = os.environ["AW_DB"]
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
A = f"/projects/{P}/project"
LEGS = {a.upper() for a in sys.argv[1:]} or {"B", "A", "F", "C"}
EXPECT = os.environ.get("AW_EXPECT", "prefix")
if EXPECT not in ("prefix", "fixed"):
    raise SystemExit(f"AW_EXPECT must be prefix or fixed, not {EXPECT!r}")
FIXED = EXPECT == "fixed"
GUARD_WORDS = "recorded evidence for this task"

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail else ""))
    return bool(cond)


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(title):
    print(f"\n=== {title}")


def rows(sql, *args):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def task_row(tid):
    return rows("select status, assignee from tasks where id=?", tid)[0]


def transitions(tid):
    return rows(
        "select sequence, from_status, to_status, actor_kind, actor_agent, origin "
        "from task_transitions where task_id=? order by sequence",
        tid,
    )


def runs_of(agent):
    return rows(
        "select id, status, task_id, conversation_id, started_at, ended_at from runs "
        "where project_id=? and agent=? order by started_at",
        P,
        agent,
    )


def entries_of(agent):
    return rows(
        "select id, state, review_task_id, waiting_reason, delivery_attempts, withdrawn_at "
        "from inbound_queue_entries where project_id=? and agent=? order by sequence",
        P,
        agent,
    )


c, projrow = api("GET", f"/projects/{P}")
ROOT = pathlib.Path(projrow["working_directory"])


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {args} failed: {r.stderr}")
    return r.stdout.strip(), r.returncode


# --- fixture: a runner, the agents, one approved document with three requirements ---------------


def ensure_agents(names):
    c, runners = api("GET", f"/projects/{P}/runners")
    runner = next((r for r in (runners or []) if r.get("model") == HAIKU), None)
    if runner is None:
        c, runner = api(
            "POST",
            f"/projects/{P}/runners",
            {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU},
        )
        assert c in (200, 201), (c, runner)
    for name in names:
        c, b = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner["id"]})
        if c not in (200, 201, 409):
            raise SystemExit(f"agent {name}: {c} {b}")
        api(
            "PATCH",
            f"/projects/{P}/agents/{name}",
            {"default_permission_mode": "bypassPermissions"},
        )


def payload(title, keys):
    return {
        "schema_version": 1,
        "kind": "change-spec",
        "title": title,
        "summary": "A driven fixture document for D-1 2026-09-12, complete enough to approve.",
        "problem": "F319's reach cannot be driven without requirements that evidence can name.",
        "scope": {"in_scope": ["Review dispatch"], "non_goals": ["Anything real"]},
        "requirements": [
            {
                "key": k,
                "statement": f"The subject MUST satisfy condition {k} exactly as stated here.",
                "modal": "MUST",
                "rationale": f"Condition {k} is silent when violated, so it needs stating.",
            }
            for k in keys
        ],
        "acceptance_criteria": [
            {
                "key": f"ac-{k}",
                "requirement": k,
                "given": "a fixture project",
                "when": f"condition {k} is exercised",
                "then": f"the behaviour matches {k}",
            }
            for k in keys
        ],
        "tasks": [
            {
                "key": f"t-{k}",
                "title": f"Satisfy condition {k}",
                "description": f"Implement condition {k}, covering ac-{k} with a named test.",
                "requirements": [k],
                "reviewer": "critic",
            }
            for k in keys
        ],
        "design": "Each condition is local to its own function.",
        "evidence": {"checked": ["Nothing, fixture"], "limits": ["Describes no software"]},
        "lifecycle": "Deleted with the fixture.",
        "open_questions": [],
    }


def make_document():
    path = f"spec/changes/d0912-{TAG}/spec.html"
    c, b = api("POST", f"{A}/documents", {"path": path, "title": f"d0912 {TAG}"})
    assert c == 201, (c, b)
    c, b = api(
        "PUT",
        f"{A}/documents/{path}/content",
        {"document": payload("d0912", ["fr-1", "fr-2", "fr-3", "fr-4", "fr-5"])},
    )
    assert c in (200, 201), (c, str(b)[:300])
    ids = b.get("identifiers") or {}
    c, _ = api("POST", f"{A}/documents/close-exploration?path={path}")
    assert c == 200, c
    c, b = api("POST", f"{A}/documents/propose?path={path}")
    assert c == 200 and not b.get("blocking"), (c, str(b)[:300])
    c, _ = api("POST", f"{A}/documents/phase?path={path}&to=approved", {"reason": ""})
    assert c == 200, c
    return path, ids


def completed_task(title, identifier, doc, locator):
    """A task the OPERATOR walks to `completed`, carrying one operator evidence row at *locator*."""
    c, t = api(
        "POST",
        f"/projects/{P}/tasks",
        {"title": title, "description": title, "requirements": [identifier]},
    )
    assert c in (200, 201), (c, t)
    tid = t["id"]
    c, ev = api(
        "POST",
        f"{A}/spec/evidence",
        {
            "identifier": identifier,
            "document": doc,
            "task_id": tid,
            "kind": "manual_observation",
            "locator": locator,
            "summary": f"operator observed {title}",
        },
    )
    assert c == 201, (c, str(ev)[:300])
    for to in ("in_progress", "completed"):
        c, b = api("PATCH", f"/projects/{P}/tasks/{tid}", {"status": to})
        assert c == 200, (to, c, str(b)[:300])
    return tid, ev


def dispatch_review(agent, tid):
    return api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": agent,
            "review_task_id": tid,
            "message": f"Review task {tid}. Reply with one sentence and call no tool.",
        },
        timeout=90,
    )


def wait_idle(agent, limit=420):
    t0 = time.time()
    while time.time() - t0 < limit:
        if not any(r["status"] == "running" for r in runs_of(agent)):
            return True
        time.sleep(5)
    return False


def entry(eid):
    return rows(
        "select id, state, conversation_id, delivery_attempts, waiting_reason, abandoned_reason, "
        "delivered_in_run_id, withdrawn_at from inbound_queue_entries where id=?",
        eid,
    )[0]


def events(event_type, agent):
    return rows(
        "select id, data from event_logs where project_id=? and event_type=? and agent=?",
        P,
        event_type,
        agent,
    )


def snapshot(tid):
    """What the fixed tree must leave untouched: the task row, and how many transitions it has."""
    return task_row(tid), len(transitions(tid))


def continue_conversation(conv):
    return api("POST", f"/projects/{P}/conversations/{conv}/continue", timeout=90)


def wait_attempts(eid, at_least, limit=60):
    t0 = time.time()
    while time.time() - t0 < limit:
        e = entry(eid)
        if e["delivery_attempts"] >= at_least or e["state"] != "queued":
            return e
        time.sleep(2)
    return entry(eid)


def detail(body):
    return body.get("detail") if isinstance(body, dict) else body


def untouched(label, tid, before, reviewer):
    """AW_EXPECT=fixed: the refused dispatch left the task exactly as it found it."""
    now = snapshot(tid)
    ok(
        f"{label}: task row and transition count equal the before-dispatch snapshot",
        now == before,
        f"before={before!r} now={now!r}",
    )
    ok(
        f"{label}: the refused reviewer has no run",
        not runs_of(reviewer),
        json.dumps(runs_of(reviewer)),
    )


def show_state(tid, agent):
    note("task", task_row(tid))
    note("transitions", json.dumps(transitions(tid)))
    note(f"runs of {agent}", json.dumps(runs_of(agent)))
    note(f"queue of {agent}", json.dumps(entries_of(agent)))


REV, REV2, REV3, AUTH = f"rev{TAG}", f"revb{TAG}", f"revc{TAG}", f"auth{TAG}"
AUTHF = f"authf{TAG}"
note("AW_EXPECT", EXPECT)
ensure_agents([REV, REV2, REV3, AUTH, AUTHF])
DOC, IDS = make_document()
note("document", DOC)
note("identifiers", IDS)
# The long first step of legs A and F. It was `sleep 60` until 2026-09-13, when Claude Code 2.1.269
# answered every standalone `sleep 60` / `Start-Sleep -Seconds 60` with "Blocked: standalone sleep"
# and the agent gave up on the turn -- so it never became the author, and leg A never reached its
# precondition. A committed script that takes a minute is a real command, as a slow test run is.
if not (ROOT / "slow_step.py").exists():
    (ROOT / "slow_step.py").write_text(
        'import time\n\ntime.sleep(60)\nprint("slow step finished")\n', encoding="utf-8"
    )
    git("add", "slow_step.py")
    git("commit", "-q", "-m", "slow_step.py: a step that takes a minute")
SLOW_STEP = (
    "1) Run the command `python slow_step.py` in your workspace and wait for it to finish; it "
    "takes about a minute and prints 'slow step finished'. "
)
HEAD, _ = git("rev-parse", "HEAD")
note("fixture HEAD", HEAD)

# ================================================================================================
if "B" in LEGS:
    leg("B1: the evidence's commit is pruned after it was recorded; a non-author is dispatched")
    git("checkout", "-q", "-b", f"gone-{TAG}")
    git("commit", "-q", "--allow-empty", "-m", f"d0912 {TAG} a commit that will be pruned")
    GONE, _ = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    tb1, ev = completed_task(f"B1 {TAG}", IDS["fr-1"], DOC, GONE)
    ok(
        "operator evidence is footprinted at the side commit",
        (ev.get("footprint") or {}).get("commit_sha") == GONE,
        str(ev.get("footprint"))[:200],
    )
    git("branch", "-q", "-D", f"gone-{TAG}")
    git("reflog", "expire", "--expire=now", "--all")
    git("gc", "-q", "--prune=now")
    _, rc = git("cat-file", "-e", GONE, check=False)
    ok("the commit is gone from the repository", rc != 0, f"cat-file rc={rc}")
    c, b = api("GET", f"/projects/{P}/tasks/{tb1}")
    note("before dispatch", task_row(tb1))
    snap = snapshot(tb1)
    before = transitions(tb1)
    c, b = dispatch_review(REV, tb1)
    note("POST /agent/trigger", f"{c} {str(b)[:500]}")
    note("B1 route sentence (5.3: unchanged by the fix)", detail(b))
    ok("the operator is refused (not told it is queued)", c in (403, 409), str(c))
    after = task_row(tb1)
    new = transitions(tb1)[len(before) :]
    show_state(tb1, REV)
    if FIXED:
        untouched("B1", tb1, snap, REV)
    else:
        ok(
            "F319(b) REACHED: the refused dispatch left the task staffed",
            after["assignee"] == REV,
            repr(after),
        )
        ok(
            "F319(b) REACHED: ... and moved it to under_review with a transition row",
            after["status"] == "under_review"
            and any(t["to_status"] == "under_review" for t in new),
            json.dumps(new),
        )
        ok("... with no run for the reviewer", not runs_of(REV), json.dumps(runs_of(REV)))
    c, b = dispatch_review(REV, tb1)
    note("second dispatch of the same reviewer", f"{c} {str(b)[:300]}")
    c, b = dispatch_review(REV3, tb1)
    note("dispatching a DIFFERENT reviewer to the task", f"{c} {str(b)[:300]}")
    said_held = "already under review" in str(detail(b))
    if FIXED:
        ok(
            "D9: the second reviewer is NOT refused as 'already under review'",
            not said_held,
            f"{c} {detail(b)}",
        )
        untouched("B1 after both further dispatches", tb1, snap, REV3)
    else:
        ok(
            "D9 REACHED: the second reviewer is refused as 'already under review'",
            said_held,
            f"{c} {detail(b)}",
        )

    leg("B2: the reviewer's review-checkout path is a plain directory")
    tb2, ev = completed_task(f"B2 {TAG}", IDS["fr-3"], DOC, HEAD)
    obstruct = ROOT / ".agentweave" / "reviews" / REV2
    obstruct.mkdir(parents=True, exist_ok=True)
    (obstruct / "leftover.txt").write_text("not a worktree\n")
    snap = snapshot(tb2)
    before = transitions(tb2)
    c, b = dispatch_review(REV2, tb2)
    note("POST /agent/trigger", f"{c} {str(b)[:500]}")
    note("B2 route sentence (5.3: unchanged by the fix)", detail(b))
    ok("the operator is refused", c in (403, 409), str(c))
    after = task_row(tb2)
    new = transitions(tb2)[len(before) :]
    show_state(tb2, REV2)
    if FIXED:
        untouched("B2", tb2, snap, REV2)
    else:
        ok(
            "F319(b) REACHED (B2): the task is left under_review, held by the refused reviewer",
            after == {"status": "under_review", "assignee": REV2},
            repr(after),
        )
        ok(
            "... with a transition row and no run",
            bool(new) and not runs_of(REV2),
            json.dumps(new),
        )

# ================================================================================================
if "A" in LEGS:
    leg("A: a review queued behind the agent's own running turn, which then records evidence")
    ta, _ = completed_task(f"A {TAG}", IDS["fr-2"], DOC, HEAD)
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AUTH,
            "message": (
                "Do exactly these three steps and nothing else. "
                + SLOW_STEP
                + "2) Call the tool mcp__agentweave__record_evidence with "
                f"identifier='{IDS['fr-2']}', document='{DOC}', task_id='{ta}', "
                "kind='manual_observation', locator='README.md', summary='README exists'. "
                "3) Reply with the single word done. Do not call update_task."
            ),
        },
        timeout=90,
    )
    note("trigger the author-to-be", f"{c} {str(b)[:200]}")
    ok("its own turn started, not queued behind another", b.get("status") == "running", str(b))
    t0 = time.time()
    while time.time() - t0 < 60 and not any(r["status"] == "running" for r in runs_of(AUTH)):
        time.sleep(1)
    ok(
        "its turn is running",
        any(r["status"] == "running" for r in runs_of(AUTH)),
        json.dumps(runs_of(AUTH)),
    )
    authors_now = rows(
        "select actor from requirement_evidence where task_id=? and actor_kind='agent'", ta
    )
    ok(
        "... and it has not recorded evidence yet, so the route has nothing to refuse",
        not authors_now,
        json.dumps(authors_now),
    )
    snap = snapshot(ta)
    c, b = dispatch_review(AUTH, ta)
    note("dispatch the same agent to review, while it runs", f"{c} {str(b)[:400]}")
    ok("the route accepts it (queued behind the running turn)", c == 200, str(c))
    a_entry = b.get("queue_entry_id") if isinstance(b, dict) else None
    a_conv = b.get("conversation_id") if isinstance(b, dict) else None
    ok("wait for the running turn to end", wait_idle(AUTH))
    time.sleep(10)
    ev_rows = rows(
        "select id, actor_kind, actor, review_state from requirement_evidence where task_id=?", ta
    )
    note("evidence on the task", json.dumps(ev_rows))
    became_author = any(r["actor_kind"] == "agent" and r["actor"] == AUTH for r in ev_rows)
    ok("the agent did record evidence for the task during that turn (Haiku acted)", became_author)
    show_state(ta, AUTH)
    after = task_row(ta)
    if became_author:
        ok(
            "4.6 live: its awaiting evidence refused it the review (no second run)",
            len(runs_of(AUTH)) == 1,
            json.dumps(runs_of(AUTH)),
        )
        if FIXED:
            ok(
                "A: task row and transition count equal the before-dispatch snapshot",
                snapshot(ta) == snap,
                f"before={snap!r} now={snapshot(ta)!r}",
            )
        else:
            ok(
                "F319(a) REACHED: the refused reviewer now holds the completed task",
                after == {"status": "completed", "assignee": AUTH},
                repr(after),
            )
    # Drive A's entry to the delivery limit through the operator's own route, so that it is
    # settled before leg F starts: every run end re-drains every agent with something queued.
    passes = []
    if a_entry:
        e = wait_attempts(a_entry, 1)
        passes.append(
            (
                "run-end re-drain",
                e["delivery_attempts"],
                e["state"],
                e["waiting_reason"],
                snapshot(ta),
            )
        )
        for n in (1, 2):
            if entry(a_entry)["state"] != "queued":
                break
            c, b = continue_conversation(a_conv)
            note(f"A continue {n}", f"{c} {json.dumps(b)[:300]}")
            e = entry(a_entry)
            passes.append(
                (
                    f"continue {n}",
                    e["delivery_attempts"],
                    e["state"],
                    e["waiting_reason"],
                    snapshot(ta),
                )
            )
        for p_ in passes:
            note("A pass", json.dumps(p_, default=str))
        e = entry(a_entry)
        note("A's entry at the end", json.dumps(e, default=str))
        abandoned = events("queue_entry_abandoned", AUTH)
        note("queue_entry_abandoned rows for the author", len(abandoned))
        if FIXED and became_author:
            ok(
                "A: the guard's sentence is the entry's waiting_reason on every queued pass",
                all(GUARD_WORDS in (p_[3] or "") for p_ in passes if p_[2] == "queued"),
                json.dumps([p_[3] for p_ in passes]),
            )
            ok(
                "A: after attempt 3 the entry is given up, with a queue_entry_abandoned row",
                e["state"] == "withdrawn"
                and e["delivery_attempts"] == 3
                and GUARD_WORDS in (e["abandoned_reason"] or "")
                and len(abandoned) >= 1,
                json.dumps(e, default=str),
            )
            ok(
                "A: the task equals its before-dispatch snapshot after every pass",
                all(p_[4] == snap for p_ in passes),
                json.dumps([p_[4] for p_ in passes]),
            )
        elif became_author:
            ok(
                "(prefix) giving up on the entry did not release the task",
                task_row(ta) == {"status": "completed", "assignee": AUTH},
                repr(task_row(ta)),
            )

# ================================================================================================
if "F" in LEGS:
    leg("F: F320 -- the pass that gives up a refused head, with a plain message waiting behind it")
    # Every run end re-drains the whole project, so F starts only once nothing else is live: on
    # 2026-09-13 a leg-A review that ended without a verdict restaffed its task to X, and X's
    # "running turn" in F was that restaff, not F's own.
    t0 = time.time()
    while time.time() - t0 < 420 and rows(
        "select id from runs where project_id=? and status='running'", P
    ):
        time.sleep(5)
    busy = rows("select agent, id from runs where project_id=? and status='running'", P)
    queued_now = rows(
        "select agent, id from inbound_queue_entries where project_id=? and state='queued'", P
    )
    note("entries queued project-wide before F", json.dumps(queued_now))
    ok("nothing is running in the project before F", not busy, json.dumps(busy))
    tf, _ = completed_task(f"F {TAG}", IDS["fr-5"], DOC, HEAD)
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AUTHF,
            "message": (
                "Do exactly these three steps and nothing else. "
                + SLOW_STEP
                + "2) Call the tool mcp__agentweave__record_evidence with "
                f"identifier='{IDS['fr-5']}', document='{DOC}', task_id='{tf}', "
                "kind='manual_observation', locator='README.md', summary='README exists'. "
                "3) Reply with the single word done. Do not call update_task."
            ),
        },
        timeout=90,
    )
    note("1. trigger X's turn", f"{c} {str(b)[:200]}")
    ok("X's own turn started, not queued behind another", b.get("status") == "running", str(b))
    t0 = time.time()
    while time.time() - t0 < 60 and not any(r["status"] == "running" for r in runs_of(AUTHF)):
        time.sleep(1)
    ok("X's turn is running", any(r["status"] == "running" for r in runs_of(AUTHF)))
    snap = snapshot(tf)
    c, h = dispatch_review(AUTHF, tf)
    note("2. dispatch H, a review of TF naming X", f"{c} {str(h)[:300]}")
    ok("H is answered 200 queued", c == 200 and h.get("status") == "queued", f"{c} {h}")
    c, m = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AUTHF, "message": "Reply with the single word pong. Call no tool."},
        timeout=90,
    )
    note("3. trigger M, plain, in a new conversation", f"{c} {str(m)[:300]}")
    ok("M is answered 200 queued", c == 200 and m.get("status") == "queued", f"{c} {m}")
    H, HC = h.get("queue_entry_id"), h.get("conversation_id")
    M, MC = m.get("queue_entry_id"), m.get("conversation_id")
    ok("H and M are in different conversations", HC != MC, f"{HC} {MC}")
    ok("4. wait for X's turn to end", wait_idle(AUTHF))
    e = wait_attempts(H, 1)
    became_author = any(
        r["actor_kind"] == "agent" and r["actor"] == AUTHF
        for r in rows("select actor_kind, actor from requirement_evidence where task_id=?", tf)
    )
    ok("X recorded evidence for TF during its turn (Haiku acted)", became_author)
    note("H after the run-end re-drain", json.dumps(e, default=str))
    note("M after the run-end re-drain", json.dumps(entry(M), default=str))
    gave_up_by = None
    for n in (1, 2, 3):
        if entry(H)["state"] != "queued":
            break
        m_before = entry(M)
        c, r = continue_conversation(HC)
        he, me = entry(H), entry(M)
        note(f"5. continue {n} on H's conversation", f"{c} {json.dumps(r)}")
        note(f"   H after continue {n}", json.dumps(he, default=str))
        note(f"   M after continue {n}", json.dumps(me, default=str))
        if he["state"] != "queued" and gave_up_by is None:
            gave_up_by = (n, r, m_before, me)
    time.sleep(15)
    he, me = entry(H), entry(M)
    note("6. H at the end", json.dumps(he, default=str))
    note("6. M at the end", json.dumps(me, default=str))
    note(f"runs of {AUTHF}", json.dumps(runs_of(AUTHF)))
    note("TF", repr(snapshot(tf)))
    ok(
        "H is given up (withdrawn at 3 attempts)",
        he["state"] == "withdrawn" and he["delivery_attempts"] == 3,
        json.dumps(he, default=str),
    )
    ok("H was given up by an operator continue", gave_up_by is not None, repr(gave_up_by))
    if FIXED:
        n, r, m_before, _ = gave_up_by or (None, {}, {}, {})
        note("the continue whose pass gave H up", n)
        ok(
            "F: M was still queued at 0 attempts before that pass",
            m_before.get("state") == "queued" and m_before.get("delivery_attempts") == 0,
            json.dumps(m_before, default=str),
        )
        ok(
            "F: that same pass started M's conversation",
            (r or {}).get("started_conversation_id") == MC,
            json.dumps(r),
        )
        ok(
            "F: M is delivered, into a real run",
            me["state"] == "delivered"
            and me["delivered_in_run_id"] in [x["id"] for x in runs_of(AUTHF)],
            json.dumps(me, default=str),
        )
        ok(
            "F: TF equals its before-dispatch snapshot",
            snapshot(tf) == snap,
            f"before={snap!r} now={snapshot(tf)!r}",
        )
        ok("M's turn ends", wait_idle(AUTHF))
    else:
        ok(
            "F320 REACHED: M is still queued at 0 attempts",
            me["state"] == "queued" and me["delivery_attempts"] == 0,
            json.dumps(me, default=str),
        )
        ok(
            "F320 REACHED: ... with no run for M",
            me["delivered_in_run_id"] is None
            and not [x for x in runs_of(AUTHF) if x["conversation_id"] == MC],
            json.dumps(runs_of(AUTHF)),
        )
        ok(
            "(prefix) the refused review H left TF staffed by X",
            task_row(tf) == {"status": "completed", "assignee": AUTHF},
            f"before={snap!r} now={snapshot(tf)!r}",
        )

# ================================================================================================
if "C" in LEGS:
    leg(
        "C: 4.5 live -- operator-kind evidence only, every agent eligible, a real review turn starts"
    )
    tc, _ = completed_task(f"C {TAG}", IDS["fr-4"], DOC, HEAD)
    c, b = dispatch_review(REV3, tc)
    note("POST /agent/trigger", f"{c} {str(b)[:300]}")
    ok("the review is dispatched", c == 200, str(c))
    ok("the review turn ends", wait_idle(REV3))
    show_state(tc, REV3)
    runs = [r for r in runs_of(REV3) if r["task_id"] == tc]
    ok("a real run bound to the task", bool(runs), json.dumps(runs_of(REV3)))
    ok(
        "the task entered under_review held by the reviewer",
        any(t["to_status"] == "under_review" for t in transitions(tc)),
        json.dumps(transitions(tc)),
    )

print(f"\n{len(PASS)} ok, {len(FAIL)} fail")
for f in FAIL:
    print("  FAIL:", f)
