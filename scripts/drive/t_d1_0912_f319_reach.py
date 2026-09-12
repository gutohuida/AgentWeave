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

The proof is read from the drive database (`tasks`, `task_transitions`, `runs`,
`inbound_queue_entries`, `requirement_evidence`), read-only, not from a response alone.

    AW_HUB=http://127.0.0.1:8016 AW_KEY=... AW_PROJECT=proj-... AW_DB=<path> \
        py -3.11 scripts/drive/t_d1_0912_f319_reach.py [B|A|C ...]

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
LEGS = set(a.upper() for a in sys.argv[1:]) or {"B", "A", "C"}

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
        "select id, status, task_id, started_at, ended_at from runs where project_id=? and agent=? "
        "order by started_at",
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
        {"document": payload("d0912", ["fr-1", "fr-2", "fr-3", "fr-4"])},
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


def show_state(tid, agent):
    note("task", task_row(tid))
    note("transitions", json.dumps(transitions(tid)))
    note(f"runs of {agent}", json.dumps(runs_of(agent)))
    note(f"queue of {agent}", json.dumps(entries_of(agent)))


REV, REV2, REV3, AUTH = f"rev{TAG}", f"revb{TAG}", f"revc{TAG}", f"auth{TAG}"
ensure_agents([REV, REV2, REV3, AUTH])
DOC, IDS = make_document()
note("document", DOC)
note("identifiers", IDS)
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
    before = transitions(tb1)
    c, b = dispatch_review(REV, tb1)
    note("POST /agent/trigger", f"{c} {str(b)[:500]}")
    ok("the operator is refused (not told it is queued)", c in (403, 409), str(c))
    after = task_row(tb1)
    new = transitions(tb1)[len(before) :]
    show_state(tb1, REV)
    ok(
        "F319(b) REACHED: the refused dispatch left the task staffed",
        after["assignee"] == REV,
        repr(after),
    )
    ok(
        "F319(b) REACHED: ... and moved it to under_review with a transition row",
        after["status"] == "under_review" and any(t["to_status"] == "under_review" for t in new),
        json.dumps(new),
    )
    ok("... with no run for the reviewer", not runs_of(REV), json.dumps(runs_of(REV)))
    c, b = dispatch_review(REV, tb1)
    note("second dispatch of the same reviewer", f"{c} {str(b)[:300]}")
    c, b = dispatch_review(REV3, tb1)
    note("dispatching a DIFFERENT reviewer to the stranded task", f"{c} {str(b)[:300]}")

    leg("B2: the reviewer's review-checkout path is a plain directory")
    tb2, ev = completed_task(f"B2 {TAG}", IDS["fr-3"], DOC, HEAD)
    obstruct = ROOT / ".agentweave" / "reviews" / REV2
    obstruct.mkdir(parents=True, exist_ok=True)
    (obstruct / "leftover.txt").write_text("not a worktree\n")
    before = transitions(tb2)
    c, b = dispatch_review(REV2, tb2)
    note("POST /agent/trigger", f"{c} {str(b)[:500]}")
    ok("the operator is refused", c in (403, 409), str(c))
    after = task_row(tb2)
    new = transitions(tb2)[len(before) :]
    show_state(tb2, REV2)
    ok(
        "F319(b) REACHED (B2): the task is left under_review, held by the refused reviewer",
        after == {"status": "under_review", "assignee": REV2},
        repr(after),
    )
    ok("... with a transition row and no run", bool(new) and not runs_of(REV2), json.dumps(new))

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
                "Do exactly these three steps and nothing else. 1) Run the shell command `sleep 60` "
                "and wait for it to finish. 2) Call the tool mcp__agentweave__record_evidence with "
                f"identifier='{IDS['fr-2']}', document='{DOC}', task_id='{ta}', "
                "kind='manual_observation', locator='README.md', summary='README exists'. "
                "3) Reply with the single word done. Do not call update_task."
            ),
        },
        timeout=90,
    )
    note("trigger the author-to-be", f"{c} {str(b)[:200]}")
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
    c, b = dispatch_review(AUTH, ta)
    note("dispatch the same agent to review, while it runs", f"{c} {str(b)[:400]}")
    ok("the route accepts it (queued behind the running turn)", c == 200, str(c))
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
        ok(
            "F319(a) REACHED: the refused reviewer now holds the completed task",
            after == {"status": "completed", "assignee": AUTH},
            repr(after),
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
