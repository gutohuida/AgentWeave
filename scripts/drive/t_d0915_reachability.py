"""DRIVE 2026-09-15 -- a task nothing will move holds nobody (openspec change, tasks 5.2-5.4c).

The change (`4b59ee0`) makes the free-agent pool ask whether anything will ever move an assigned
task before letting it hold its assignee: a task holds its agent only while its loop has not ended
and is not archived, or while a turn within the hop budget is queued for that agent naming it.
LoopEngine's board is the population it exists for -- the Architect handed `dev` and `dev_2` tasks
through `create_task` with an assignee and no loop, and from then on every flow firing answered
"could not staff this step" for a review both of them were idle enough to do (F352).

Unit tests cover the predicate through `decide_firing`. This drives it through the real routes with
real Haiku turns, because what a test cannot show is the product: that a flow's review is actually
staffed and actually run by an agent the old rule would have called busy.

Phase AUTHOR (one flow per lane, each with a one-task document, so no firing can staff two lanes'
reviews at once). Only `alpha` exists, so `alpha` authors every task in a real turn, recording
evidence that names a commit. The review arm refuses a task with no such evidence (`scheduler.py`,
`review_target`), and an operator-walked completion names no author, which would put `alpha` itself
on the ladder -- so the author has to be a real agent turn, not a PATCH.

Phase LANES. `beta` and `gamma` are created, and given work outside every loop through
`POST /tasks` with an assignee and no `loop_id` -- the Architect's route.

  5.2   LoopEngine's shape: fire flow 1. The review is staffed (`beta`, first in name order) and a
        real Haiku turn runs it. No `review_unstaffed` is recorded for the task.
  5.3   Control: `beta` and `gamma` are given tasks in a second LIVE loop. Fire flow 2: unstaffed,
        with today's rung-3 sentence.
  5.4   Pause that loop: still unstaffed. End it (`PATCH /jobs/{id}` with a stop reason): staffed.
        Archived: a third loop holds them again; fire flow 3 (unstaffed, the control), then archive
        its job through `POST /jobs/{id}/archive` WITHOUT stopping it, confirm `ending_state` is
        null on `GET /loops/{id}`, fire again: staffed.
  5.4b  RETIRED 2026-09-22 (its precondition was F258). Was: a peer message to `beta` naming its out-of-loop task, through `POST /messages` with a
        `task_id` and no run, queues at hop_budget + 1. Fire flow 4: `beta` is still staffed.
  5.4c  An empty plain loop on `alpha`. While `alpha` runs a real turn, press Run: 409 naming
        `alpha`, and no new entry on `alpha`'s queue.

Real surface only. No row inserts. Every runner binds Haiku. Disables every job it creates.

Run (from scripts/drive):
  AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> AW_PHASE=author py -3.11 -u t_d0915_reachability.py
  AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> AW_PHASE=lanes  py -3.11 -u t_d0915_reachability.py
State between phases: $AW_STATE (default: a JSON file beside the system temp directory).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api, task_rows  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"  # the id the catalog declares; the bare name is refused
AUTHOR, B, C = "alpha", "beta", "gamma"
LANES = ("staffed", "control", "archived", "budget")
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0")
PHASE = os.environ.get("AW_PHASE", "author")
STATE = os.environ.get("AW_STATE") or os.path.join(tempfile.gettempdir(), "d0915_state.json")
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
FAR_CRON = "0 4 1 1 *"

VERDICTS = []
S = {}


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    print(f"  [obs] {label}" + (f" -- {detail}" if detail else ""))


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def blob(x, limit=900):
    return json.dumps(x, default=str)[:limit]


def save():
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump(S, handle, indent=1)


def load():
    global S
    with open(STATE, encoding="utf-8") as handle:
        S = json.load(handle)
    aw.P = S["P"]


def P():  # noqa: N802 -- reads like the constant it replaces in aw.py
    return S["P"]


def call(label, method, path, body=None, expect=(200, 201)):
    code, out = api(method, path, body)
    ok = code in expect
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED ' + blob(out, 600)}")
    if not ok:
        raise SystemExit(f"{label} failed")
    return out


def git(root, *args):
    p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {p.stderr or p.stdout}")
    return (p.stdout or "").strip()


# --- reads --------------------------------------------------------------------------------------


def statuses():
    code, body = api("GET", f"/projects/{P()}/agents")
    return {a["name"]: a.get("status") for a in (body if isinstance(body, list) else [])}


def tasks():
    code, body = api("GET", f"/projects/{P()}/tasks?limit=500")
    return task_rows(body)


def task(tid):
    return next((t for t in tasks() if t["id"] == tid), None)


def evidence(tid):
    code, ev = api("GET", f"/projects/{P()}/project/spec/evidence")
    rows = ev.get("evidence", []) if isinstance(ev, dict) else []
    return [e for e in rows if e.get("task_id") == tid]


def unstaffed_events(tid):
    code, rows = api("GET", f"/projects/{P()}/logs?event_type=review_unstaffed&limit=500")
    rows = rows if isinstance(rows, list) else []
    return [r for r in rows if (r.get("data") or {}).get("task_id") == tid]


def queue(agent):
    code, rows = api("GET", f"/projects/{P()}/queue/{agent}")
    return rows if isinstance(rows, list) else []


def loop_row(loop_id):
    code, body = api("GET", f"/projects/{P()}/loops/{loop_id}")
    return body if isinstance(body, dict) else {}


def settle(label, rounds=60, gap=5, tids=()):
    """Wait until no agent is running. Prints each tick so a slow turn is visible in the log."""
    for i in range(rounds):
        time.sleep(gap)
        busy = {n: s for n, s in statuses().items() if s not in ("idle", "offline", "error", None)}
        rows = [(t["id"][-6:], t["status"], t.get("assignee")) for t in tasks() if t["id"] in tids]
        print(f"      [{label}] t+{(i + 1) * gap:>3}s busy={busy} {rows}")
        if i >= 1 and not busy:
            return True
    print(f"      [{label}] did not settle")
    return False


def running_any(*names):
    now = statuses()
    return any(now.get(n) == "running" for n in names)


def live_holdings(agent):
    """The agent's open tasks that sit in a loop that has not ended and is not archived."""
    out = []
    for t in tasks():
        if t.get("assignee") != agent or t["status"] in ("approved", "rejected", "cancelled"):
            continue
        if t.get("loop_id"):
            lr = loop_row(t["loop_id"])
            if lr.get("ending_state") is None and not lr.get("archived_at"):
                out.append((t["id"], t["status"], t["loop_id"]))
    return out


def wait_for(pred, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.5)
    print(f"      timed out waiting for {what}")
    return False


# --- writes -------------------------------------------------------------------------------------


def fire(job_id, label):
    """Press Run. Enables the job first -- Run refuses a disabled job, and every phase ends by
    disabling everything it created -- and only this job, so a paused holding loop stays paused."""
    code, body = api("GET", f"/projects/{P()}/jobs/{job_id}")
    if isinstance(body, dict) and not body.get("enabled"):
        call(f"enable {job_id}", "PATCH", f"/projects/{P()}/jobs/{job_id}", {"enabled": True})
    code, body = api("POST", f"/projects/{P()}/jobs/{job_id}/run", {})
    detail = body.get("detail") if isinstance(body, dict) and "detail" in body else body
    print(f"  fire[{label}] -> {code}  {blob(detail, 700)}")
    return code, detail


def make_agent(name, runner):
    call(f"agent {name}", "POST", f"/projects/{P()}/agents", {"name": name, "runner_id": runner})


def one_task_document(lane):
    target = f"d0915_{lane}.txt"
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": f"{target} exists",
        "summary": f"One file, so the {lane} lane has exactly one piece of work to review.",
        "problem": f"{target} does not exist.",
        "scope": {"in_scope": [target], "non_goals": ["anything else"]},
        "requirements": [
            {
                "key": "file",
                "statement": f"The project SHALL contain {target} holding the line {lane}.",
                "modal": "SHALL",
                "rationale": "A drive needs one reviewable change.",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "file-exists",
                "requirement": "file",
                "given": "the project after the change",
                "when": f"{target} is read",
                "then": f"it holds the single line {lane}",
            }
        ],
        "tasks": [
            {
                "key": "write-file",
                "title": f"Create {target}",
                "description": f"Create {target} in your working directory containing exactly the "
                f"line `{lane}`. Change nothing else.",
                "requirements": ["file"],
            }
        ],
    }
    base = f"/projects/{P()}/project"
    doc = call(
        f"[{lane}] create document", "POST", f"{base}/documents", {"title": payload["title"]}
    )
    q = urllib.parse.quote(doc["path"], safe="")
    call(f"[{lane}] content", "PUT", f"{base}/documents/{q}/content", {"document": payload})
    call(
        f"[{lane}] close exploration",
        "POST",
        f"{base}/documents/close-exploration?path={q}",
        {"reason": "drive 0915"},
    )
    call(f"[{lane}] propose", "POST", f"{base}/documents/propose?path={q}", {"reason": "drive"})
    return doc.get("id"), q


def make_flow(lane, doc_id):
    job = call(
        f"[{lane}] flow",
        "POST",
        f"/projects/{P()}/jobs",
        {
            "name": f"d0915-{lane}-{RUN}",
            "agent": AUTHOR,
            "message": "Work the task you have been given. Keep the edit minimal.",
            "cron": FAR_CRON,
            "purpose": f"Get the {lane} lane's one file written and reviewed.",
            "spec_document_id": doc_id,
            "stop_when_queue_empties": True,
            "enabled": True,
        },
    )
    loop_id = (job.get("loop") or {}).get("id")
    if not loop_id:
        raise SystemExit(f"[{lane}] the flow opted into no loop: {blob(job)}")
    S.setdefault("jobs", []).append(job["id"])
    return job["id"], loop_id


def holding_loop(label):
    """A plain live loop holding one task for `beta` and one for `gamma` -- the control's variable."""
    job = call(
        f"[{label}] plain loop",
        "POST",
        f"/projects/{P()}/jobs",
        {
            "name": f"d0915-{label}-{RUN}",
            "agent": AUTHOR,
            "message": "Do the next thing on the queue.",
            "cron": FAR_CRON,
            "purpose": f"Hold {B} and {C} inside a live loop ({label}).",
            "enabled": True,
            "initial_tasks": [
                {"title": f"{label}: {B}'s loop task", "description": "Held for the drive."},
                {"title": f"{label}: {C}'s loop task", "description": "Held for the drive."},
            ],
        },
    )
    S.setdefault("jobs", []).append(job["id"])
    loop_id = (job.get("loop") or {}).get("id")
    mine = [t for t in tasks() if t.get("loop_id") == loop_id]
    for t, who in zip(sorted(mine, key=lambda r: r["title"]), (B, C), strict=True):
        call(
            f"[{label}] {t['id']} -> {who}",
            "PATCH",
            f"/projects/{P()}/tasks/{t['id']}",
            {"status": "assigned", "assignee": who},
        )
    save()
    return job["id"], loop_id


# --- phases -------------------------------------------------------------------------------------


def phase_author():
    head("5.1 SETUP -- a fresh project and repository, one Haiku runner, only the author exists")
    root = tempfile.mkdtemp(prefix="aw-d0915-")
    git(root, "init", "-q")
    git(root, "config", "user.email", "drive@example.com")
    git(root, "config", "user.name", "Drive")
    git(root, "checkout", "-q", "-b", "main")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "base")
    created = call("open project", "POST", "/projects/open", {"path": root, "name": f"d0915-{RUN}"})
    S.update(P=created["id"], root=root, jobs=[], lanes={})
    aw.P = S["P"]
    if P() in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P()}")
    call("main branch", "PUT", f"/projects/{P()}/settings", {"main_branch": "main"})
    runner = call(
        "runner",
        "POST",
        f"/projects/{P()}/runners",
        {"name": "haiku", "cli": "claude", "model": HAIKU},
    )
    S["runner"] = runner["id"]
    make_agent(AUTHOR, runner["id"])
    roster = statuses()
    check("the roster is exactly the author", set(roster) == {AUTHOR}, str(roster))
    print(f"  project {P()} at {root}")
    save()

    head("AUTHOR -- one flow per lane; the author works each task in a real Haiku turn")
    for lane in LANES:
        doc_id, q = one_task_document(lane)
        job_id, loop_id = make_flow(lane, doc_id)
        call(
            f"[{lane}] approve",
            "POST",
            f"/projects/{P()}/project/documents/phase?path={q}&to=approved",
            {"reason": "drive 0915"},
        )
        time.sleep(1)
        mine = [t for t in tasks() if t.get("loop_id") == loop_id]
        check(
            f"[{lane}] approval put one task on the flow's queue", len(mine) == 1, str(mine)[:200]
        )
        S["lanes"][lane] = {"job": job_id, "loop": loop_id, "task": mine[0]["id"]}
        save()

    for lane in LANES:
        lane_s = S["lanes"][lane]
        code, _ = fire(lane_s["job"], f"{lane}: author works")
        check(f"[{lane}] the author's firing started", code == 200, str(code))
        settle(lane, tids=(lane_s["task"],))
        row = task(lane_s["task"])
        ev = evidence(lane_s["task"])
        shas = [(e.get("footprint") or {}).get("commit_sha") for e in ev]
        check(
            f"[{lane}] {AUTHOR} completed the task",
            row["status"] == "completed" and row.get("assignee") == AUTHOR,
            f"{row['status']} / {row.get('assignee')}",
        )
        check(f"[{lane}] evidence names a commit", any(shas), str(shas))
    save()


def lane_staffed():
    head("5.2 THE LOOPENGINE SHAPE -- beta and gamma hold work outside every loop")
    # Created only now, after every lane's task is authored, so neither can have worked one.
    make_agent(B, S["runner"])
    make_agent(C, S["runner"])
    roster = statuses()
    check(
        "the roster is the author and the two bookmark holders, all idle",
        roster == {AUTHOR: "idle", B: "idle", C: "idle"},
        str(roster),
    )
    t_b = call(
        f"{B}'s bookmark",
        "POST",
        f"/projects/{P()}/tasks",
        {"title": f"{B}: a task given outside every loop", "assignee": B, "status": "assigned"},
    )
    call(
        f"{B}'s bookmark -> in_progress",
        "PATCH",
        f"/projects/{P()}/tasks/{t_b['id']}",
        {"status": "in_progress"},
    )
    t_c = call(
        f"{C}'s bookmark",
        "POST",
        f"/projects/{P()}/tasks",
        {"title": f"{C}: a task given outside every loop", "assignee": C},
    )
    S["bookmarks"] = {B: t_b["id"], C: t_c["id"]}
    save()
    rows = {t["id"]: t for t in tasks()}
    check(
        "both bookmarks are live, assigned, and in no loop",
        rows[t_b["id"]]["status"] == "in_progress"
        and rows[t_c["id"]]["status"] == "pending"
        and rows[t_c["id"]].get("assignee") == C
        and not rows[t_b["id"]].get("loop_id")
        and not rows[t_c["id"]].get("loop_id"),
        blob(
            [
                (rows[i]["status"], rows[i].get("assignee"), rows[i].get("loop_id"))
                for i in (t_b["id"], t_c["id"])
            ]
        ),
    )
    code, agents_now = api("GET", f"/projects/{P()}/agents")
    counts = {a["name"]: a.get("active_task_count") for a in agents_now}
    check(
        "the roster still counts each bookmark (3.6, live)",
        counts.get(B) == 1 and counts.get(C) == 1,
        str(counts),
    )

    lane = S["lanes"]["staffed"]
    code, detail = fire(lane["job"], "5.2 review")
    check("5.2: the flow firing answers 200", code == 200, f"{code} {blob(detail, 300)}")
    started = wait_for(lambda: statuses().get(B) == "running", 90, f"{B} to start")
    row = task(lane["task"])
    check(
        f"5.2: the review is staffed with {B}",
        row["status"] == "under_review" and row.get("assignee") == B,
        f"{row['status']} / {row.get('assignee')}",
    )
    check(f"5.2: {B}'s real Haiku turn started", started, str(statuses()))
    settle("5.2 review", tids=(lane["task"],))
    row = task(lane["task"])
    note("5.2: where the reviewer left the task", f"{row['status']} / {row.get('assignee')}")
    ev = unstaffed_events(lane["task"])
    check("5.2: no review_unstaffed is recorded for the task", not ev, blob(ev, 400))
    rows = {t["id"]: t for t in tasks()}
    note(
        "bookmarks after the review",
        blob({i: (rows[i]["status"], rows[i].get("assignee")) for i in S["bookmarks"].values()}),
    )


def free_reviewers():
    """End every lane flow whose task a reviewer still holds.

    A reviewer that returns `revision_needed` keeps the assignee until the next firing hands the
    revision back to the author, and that task sits in a live loop, so it holds the reviewer --
    correctly, under this change. The lanes below each need `beta` and `gamma` holding nothing but
    what the lane stages, so a finished lane's flow is ended (the operator's stop) rather than
    fired again, which would spend another author turn on a newline.
    """
    for name, lane in S["lanes"].items():
        row = task(lane["task"])
        reviewer_holds = (
            row and row.get("assignee") in (B, C) and row["status"] not in ("approved", "rejected")
        )
        if reviewer_holds and loop_row(lane["loop"]).get("ending_state") is None:
            call(
                f"end the {name} flow ({row['status']} held by {row['assignee']})",
                "PATCH",
                f"/projects/{P()}/jobs/{lane['job']}",
                {"stop_reason": "drive 0915: lane finished"},
            )
    for who in (B, C):
        held = live_holdings(who)
        check(f"{who} holds nothing in a live loop before the lane", not held, str(held))


def lane_control_paused_ended():
    head("5.3 CONTROL -- the same people, now holding tasks in a second LIVE loop")
    free_reviewers()
    job2, loop2 = holding_loop("control-loop")
    lane = S["lanes"]["control"]
    code, detail = fire(lane["job"], "5.3 control")
    row = task(lane["task"])
    ev = unstaffed_events(lane["task"])
    reason = (ev[-1].get("data") or {}).get("reason") if ev else None
    check(
        "5.3: the review is unstaffed -- the task stays completed, with no reviewer",
        row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{row['status']} / {row.get('assignee')}",
    )
    check("5.3: a review_unstaffed is recorded", bool(ev), blob(ev, 300))
    check(
        "5.3: with today's rung-3 sentence",
        bool(reason) and "could not staff this step" in reason,
        str(reason),
    )
    note("5.3: the firing's answer", f"{code} {blob(detail, 400)}")

    head("5.4 PAUSED -- disable the holding loop's job: its tasks still hold (design D2)")
    call("pause the holding loop", "PATCH", f"/projects/{P()}/jobs/{job2}", {"enabled": False})
    code, detail = fire(lane["job"], "5.4 paused")
    row = task(lane["task"])
    check(
        "5.4 paused: still unstaffed",
        row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{row['status']} / {row.get('assignee')}  fire={code} {blob(detail, 300)}",
    )
    summary = api("GET", f"/projects/{P()}/jobs/{lane['job']}")[1]
    note(
        "5.4 paused: the flow's stall_reason",
        blob((summary.get("loop") or {}).get("stall_reason") or summary.get("stall_reason"), 400),
    )

    head("5.4 ENDED -- stop the holding loop: its tasks hold nobody")
    call(
        "end the holding loop",
        "PATCH",
        f"/projects/{P()}/jobs/{job2}",
        {"stop_reason": "drive 0915: ended to free its agents"},
    )
    check(
        "5.4 ended: the loop has an ending_state",
        bool(loop_row(loop2).get("ending_state")),
        str(loop_row(loop2).get("ending_state")),
    )
    code, detail = fire(lane["job"], "5.4 ended")
    wait_for(lambda: running_any(B, C), 90, "a reviewer to start")
    row = task(lane["task"])
    check(
        "5.4 ended: the review is staffed with a bookmark holder",
        code == 200 and row["status"] == "under_review" and row.get("assignee") in (B, C),
        f"{code} {row['status']} / {row.get('assignee')}",
    )
    settle("5.4 ended review", tids=(lane["task"],))
    row = task(lane["task"])
    note("5.4 ended: where the reviewer left the task", f"{row['status']} / {row.get('assignee')}")


def lane_archived():
    head("5.4 ARCHIVED -- a third loop holds them; archive its job WITHOUT stopping it")
    free_reviewers()
    job3, loop3 = holding_loop("archive-loop")
    lane = S["lanes"]["archived"]
    code, detail = fire(lane["job"], "archived: control first")
    row = task(lane["task"])
    check(
        "archived: while that loop is live, the review is unstaffed (the control)",
        row["status"] == "completed" and row.get("assignee") == AUTHOR,
        f"{code} {row['status']} / {row.get('assignee')}",
    )
    call("archive the holding job", "POST", f"/projects/{P()}/jobs/{job3}/archive", {})
    lr = loop_row(loop3)
    check(
        "archived: GET /loops/{id} -- archived, and ending_state is still null",
        lr.get("archived_at") and lr.get("ending_state") is None,
        f"archived_at={lr.get('archived_at')} ending_state={lr.get('ending_state')}",
    )
    code, detail = fire(lane["job"], "archived: after")
    wait_for(lambda: running_any(B, C), 90, "a reviewer to start")
    row = task(lane["task"])
    check(
        "archived: the review is staffed with a bookmark holder",
        code == 200 and row["status"] == "under_review" and row.get("assignee") in (B, C),
        f"{code} {row['status']} / {row.get('assignee')}",
    )
    settle("archived review", tids=(lane["task"],))


def lane_budget():
    head("5.4b PAST THE HOP BUDGET -- retired 2026-09-22")
    # This leg built its precondition from F258: a runless `POST /messages` was born at
    # hop_budget + 1, so one call put an entry past the budget. F258 is repaired -- that send is
    # now the operator's, at depth 0, and would start a turn for `beta` rather than hold one -- and
    # F261's repair refuses a runless `from` naming an agent. A past-budget entry can now only come
    # from a real chain of agent turns, which this harness does not build. Reported as skipped, not
    # passed: the question "does input past the budget hold anybody?" is still open here.
    note(
        "5.4b SKIPPED",
        "its precondition was F258's defect; a past-budget entry now needs a real agent chain",
    )


def lane_busy_empty():
    head("5.4c A BUSY AGENT'S EMPTY LOOP (D8) -- Run pressed while alpha's real turn runs")
    job = call(
        "empty plain loop",
        "POST",
        f"/projects/{P()}/jobs",
        {
            "name": f"d0915-empty-{RUN}",
            "agent": AUTHOR,
            "message": "Fill this loop's queue.",
            "cron": FAR_CRON,
            "purpose": "An empty loop whose agent is mid-turn.",
            "enabled": True,
        },
    )
    S["jobs"].append(job["id"])
    save()
    mine = [t for t in tasks() if t.get("loop_id") == (job.get("loop") or {}).get("id")]
    check("5.4c: the loop holds no task", not mine, str(mine)[:200])
    before = {e["id"] for e in queue(AUTHOR)}
    call(
        f"trigger {AUTHOR}",
        "POST",
        f"/projects/{P()}/agent/trigger",
        {
            "agent": AUTHOR,
            "message": "List every file in your working directory, including hidden ones, and "
            "write a one-paragraph summary of each. Use your tools; do not guess.",
        },
        expect=(200, 201, 202),
    )
    running = wait_for(lambda: statuses().get(AUTHOR) == "running", 90, f"{AUTHOR} to start")
    check(f"5.4c: {AUTHOR} is running a real turn", running, str(statuses()))
    code, detail = fire(job["id"], "5.4c while busy")
    still = statuses().get(AUTHOR)
    text = json.dumps(detail, default=str)
    check(f"5.4c: {AUTHOR} was still running when Run answered", still == "running", str(still))
    check(
        f"5.4c: 409 naming {AUTHOR}, 'Nothing was started', not 'no other agent is free'",
        code == 409
        and AUTHOR in text
        and "Nothing was started" in text
        and "no other agent is free" not in text,
        f"{code} {text[:400]}",
    )
    new = [e for e in queue(AUTHOR) if e["id"] not in before]
    job_entries = [e for e in new if e.get("job_id") == job["id"] or "job" in str(e.get("kind"))]
    note("5.4c: entries added to alpha's queue since the trigger", blob(new, 700))
    check("5.4c: no job entry was queued for the busy agent", not job_entries, blob(job_entries))
    settle("5.4c trigger turn")


def teardown():
    head("5.5 TEARDOWN -- leave no job enabled")
    code, jobs = api("GET", f"/projects/{P()}/jobs?include_archived=true")
    for j in jobs if isinstance(jobs, list) else []:
        if j.get("enabled"):
            c, _ = api("PATCH", f"/projects/{P()}/jobs/{j['id']}", {"enabled": False})
            print(f"  disable {j['id']} -> {c}")
    code, jobs = api("GET", f"/projects/{P()}/jobs?include_archived=true")
    left = [j.get("id") for j in (jobs if isinstance(jobs, list) else []) if j.get("enabled")]
    check("5.5: no job left enabled", not left, str(left))


def main():
    try:
        if PHASE == "author":
            phase_author()
        else:
            load()
            steps = {
                "staffed": lane_staffed,
                "control": lane_control_paused_ended,
                "archived": lane_archived,
                "budget": lane_budget,
                "busy": lane_busy_empty,
            }
            wanted = os.environ.get("AW_LANES", ",".join(steps)).split(",")
            for name in wanted:
                steps[name]()
    finally:
        if S.get("P"):
            teardown()
    head("VERDICT")
    for label, ok, detail in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {detail}" if detail else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}   project {S.get('P')} state {STATE}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
