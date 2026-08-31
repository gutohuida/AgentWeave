"""F154 -- a review that ended without a verdict, and every operator surface saying nothing is wrong.

F154 (severity A, FINDINGS.md) was found by accident: a reviewer spent its whole turn in a
`ToolSearch` loop, reached a verdict in its own prose and never called `update_task`. The task sat
at `under_review` with that reviewer's name on it, both agents idle, and the loop answered

    409  "Every task on this loop's queue is already being worked. Nothing was started, and
          nothing is wrong -- the next firing picks up whatever finishes."

An accident is not a reproduction. This harness builds the same row **deterministically and with no
agent turn at all**, because the flaky reviewer was never the cause -- the cause is that
`decide_firing`'s `WITH_REVIEWER` branch (`scheduler.py:1313-1361`) records the task as `in_flight`
on the strength of `task.assignee` alone, and never consults `held`, the per-task
"is a turn actually running on this" answer it computed three lines earlier and which the
ordinary-work arm next door does consult (`scheduler.py:1383-1386`).

So the population is: an `under_review` task whose assignee is a non-author, holding no running
turn. An operator reaches it by hand through the only route the lifecycle offers them, and a
reviewer reaches it by ending a turn without a verdict. Neither needs a model.

Four lanes, none of which spends a turn:

  LANE 1  the wedge exists          -- one loop, one task, driven by hand to `under_review` with a
                                       non-author reviewer. No run has ever been live on this
                                       project. Assert the roster agrees: both agents idle.
  LANE 2  what the firing says      -- press Run. Record the status and the exact sentence, twice,
                                       minutes apart in the original and back-to-back here. The
                                       finding is 409 + "nothing is wrong".
  LANE 3  what every other surface  -- the job summary's `stall_reason`, the walk's `current_tasks`
          says                         and its `agent_capacity`, the queue counts, and the task row
                                       itself. F154's claim is that not one of them names the wedge.
                                       This lane measures that claim surface by surface rather than
                                       asserting it.
  LANE 4  the cure, and its price   -- `under_review`'s three exits are the operator's. Take one
                                       (`revision_needed`) and show the loop moves again. That is
                                       the finding's sting: the rescue is cheap and the operator is
                                       never told they need it.

Then LANE 5 runs the same wedge with the AUTHOR in `assignee` instead of a reviewer -- one variable
changed. It was written expecting a CONTRAST: F70's recovery should fire, set `wedged_review`, carry
the row to the ladder and answer differently. **It does not**, and the measurement is worth more
than the expectation was. The recovery asks `assignee in agents_that_worked(task)`, and
`agents_that_worked` reads `TaskTransition.actor_agent`, which is NULL for every edge an operator
walked by hand. A task whose whole history is the operator's names no agent, so the author is not
recognised as the author and the identical 409 comes back. Filed as F167.

Real surface only. No row inserts. NO agent turns, so no model is bound. Creates its own project in
a fresh temporary repository, and disables every job it creates.

Run:  AW_HUB=http://127.0.0.1:8011 py -3.11 -u t_f154_wedged_review.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
AUTHOR = "alpha"
REVIEWER = "beta"
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0")

ROOT = None
P = ""
JOBS = []
VERDICTS = []
NOTES = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    NOTES.append((label, detail))
    print(f"  [obs] {label}" + (f" -- {detail}" if detail else ""))


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def blob(x, limit=1400):
    return json.dumps(x, indent=1, default=str)[:limit]


def git(*args):
    p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def must(*args):
    code, out, err = git(*args)
    if code != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {err or out}")
    return out


def make_project():
    """A real repository first, then `open` -- `create` refuses a directory that exists."""
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-f154-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": f"f154-drive-{RUN}"})
    if code not in (200, 201):
        raise SystemExit(f"could not open the project: {code} {created}")
    P = created["id"]
    aw.P = P
    if P in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P}")
    code, saved = api("PUT", f"/projects/{P}/settings", {"main_branch": "main"})
    if code != 200:
        raise SystemExit(f"could not set the main branch: {code} {saved}")
    print(f"  project {P} at {ROOT}")


def ensure_runner():
    code, body = api("GET", f"/projects/{P}/runners")
    for r in body if isinstance(body, list) else []:
        if r.get("model") == HAIKU:
            return r["id"]
    code, body = api(
        "POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU}
    )
    if code >= 300:
        raise SystemExit(f"no runner: {code} {body}")
    return body["id"]


def ensure_agent(name, runner):
    code, body = api("POST", f"/projects/{P}/agents", {"name": name, "runner_id": runner})
    if code >= 300:
        code, body = api("PATCH", f"/projects/{P}/agents/{name}", {"runner_id": runner})
        if code >= 300:
            raise SystemExit(f"no agent {name}: {code} {body}")


def agents():
    code, body = api("GET", f"/projects/{P}/agents")
    return body if isinstance(body, list) else []


def statuses():
    return {a["name"]: a.get("status") for a in agents()}


def make_loop(name, title):
    """A loop with one task on its queue, created in the one call that creates the loop.

    `enabled` must be true or `POST /jobs/{id}/run` refuses with "Job is disabled" before the
    scheduler is ever reached -- so the cron is a date that will not arrive during the drive, and
    the job is disabled again in TEARDOWN.
    """
    body = {
        "name": name,
        "agent": AUTHOR,
        "message": "Work the task you have been given.",
        "cron": "0 4 1 1 *",
        "enabled": True,
        "purpose": "Drive F154.",
        "stop_when_queue_empties": True,
        "initial_tasks": [{"title": title, "description": "One line. Nothing else."}],
    }
    code, job = api("POST", f"/projects/{P}/jobs", body)
    if code != 201:
        raise SystemExit(f"could not create the loop: {code} {job}")
    JOBS.append(job["id"])
    code, summary = api("GET", f"/projects/{P}/jobs/{job['id']}")
    loop_row = (summary.get("loop") or {}).get("id") if isinstance(summary, dict) else None
    tasks = [t for t in board() if t.get("loop_id") and t.get("title") == title]
    if not tasks:
        raise SystemExit(f"the loop seeded no task: {blob(summary)}")
    return job["id"], loop_row, tasks[0]["id"]


def board():
    code, body = api("GET", f"/projects/{P}/tasks")
    if isinstance(body, dict):
        body = body.get("tasks") or body.get("items") or []
    return body if isinstance(body, list) else []


def task(tid):
    return next((t for t in board() if t["id"] == tid), None)


def move(tid, status, assignee=None, expect=200):
    payload = {"status": status}
    if assignee is not None:
        payload["assignee"] = assignee
    code, body = api("PATCH", f"/projects/{P}/tasks/{tid}", payload)
    ok = code == expect
    print(
        f"  {'    ' if ok else 'BAD '}-> {status}"
        + (f" ({assignee})" if assignee else "")
        + f"  [{code}]"
    )
    if not ok:
        print("      " + blob(body, 700))
        raise SystemExit(f"could not move the task to {status}")
    return body


def wedge(tid, assignee):
    """Drive a task by hand to `under_review` with *assignee* holding it. No turn is ever run."""
    move(tid, "assigned", AUTHOR)
    move(tid, "in_progress")
    move(tid, "completed")
    move(tid, "under_review", assignee)


def fire(job_id, label):
    code, body = api("POST", f"/projects/{P}/jobs/{job_id}/run", {})
    detail = body.get("detail") if isinstance(body, dict) else body
    print(f"  fire[{label}] -> {code}")
    print(f"      {json.dumps(detail, default=str)[:600]}")
    return code, detail


def summary(job_id):
    code, body = api("GET", f"/projects/{P}/jobs/{job_id}")
    return body if isinstance(body, dict) else {}


def live_runs():
    """Every run this project has that has not ended. The whole finding rests on this being empty."""
    code, body = api("GET", f"/projects/{P}/runs")
    rows = body if isinstance(body, list) else (body or {}).get("runs") or []
    return [r for r in rows if r.get("status") in ("running", "queued", "starting", "pending")]


def main():
    head("SETUP -- a fresh project, a fresh repository, two Haiku agents, no turn ever run")
    make_project()
    runner = ensure_runner()
    ensure_agent(AUTHOR, runner)
    ensure_agent(REVIEWER, runner)
    roster = statuses()
    check(
        "both agents exist and are idle before anything",
        roster.get(AUTHOR) in ("idle", None) and roster.get(REVIEWER) in ("idle", None),
        str(roster),
    )

    head("LANE 1 -- build the wedge by hand: under_review, a non-author reviewer, no live turn")
    job1, loop1, t1 = make_loop(f"f154-wedge-{RUN}", "Add one line to README")
    print(f"  job {job1}, loop {loop1}, task {t1}")
    wedge(t1, REVIEWER)
    row = task(t1)
    check(
        "the task is under_review with the reviewer on it",
        row and row["status"] == "under_review" and row.get("assignee") == REVIEWER,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )
    check("no run is live on this project", not live_runs(), str(live_runs())[:200])
    roster = statuses()
    check(
        "the roster says both agents are idle",
        roster.get(AUTHOR) in ("idle", None) and roster.get(REVIEWER) in ("idle", None),
        str(roster),
    )

    head("LANE 2 -- press Run, twice. What does the loop say about a review nobody is doing?")
    c1, d1 = fire(job1, "first")
    time.sleep(2)
    c2, d2 = fire(job1, "second")
    text1 = json.dumps(d1, default=str).lower()
    reproduced = c1 == 409 and "nothing is wrong" in text1
    check(
        "F154 REPRODUCED: the firing answers 409 'nothing is wrong'",
        reproduced,
        f"{c1}",
    )
    check("and it says the same thing on a second press", c2 == c1, f"{c2}")
    check(
        "no run started either time, so the sentence's promise cannot come true",
        not live_runs(),
        str(live_runs())[:200],
    )

    head("LANE 3 -- surface by surface: does ANYTHING name the wedge?")
    s = summary(job1)
    loop_view = s.get("loop") or {}
    stall = loop_view.get("stall_reason", s.get("stall_reason"))
    current = loop_view.get("current_tasks", s.get("current_tasks")) or []
    queue = loop_view.get("queue", s.get("queue"))
    note("job summary stall_reason", json.dumps(stall, default=str))
    note("job summary queue", json.dumps(queue, default=str))
    note("job summary current_tasks", json.dumps(current, default=str)[:600])
    check(
        "stall_reason is null for a queue that will never move again",
        stall in (None, "", "null"),
        json.dumps(stall, default=str),
    )
    mine = [c for c in current if c.get("id") == t1]
    check(
        "the walk still lists the task as current, with the idle reviewer named",
        bool(mine) and mine[0].get("agent") == REVIEWER,
        json.dumps(mine, default=str)[:300],
    )
    if mine:
        note(
            "agent_capacity for an agent the roster calls idle", str(mine[0].get("agent_capacity"))
        )
        check(
            "agent_capacity reads 'held' for an idle agent",
            mine[0].get("agent_capacity") == "held",
            str(mine[0].get("agent_capacity")),
        )
    row = task(t1)
    note("the task row itself", json.dumps({k: row.get(k) for k in ("status", "assignee")}))
    surfaces_that_name_it = []
    if stall:
        surfaces_that_name_it.append("stall_reason")
    if isinstance(d1, str) and t1 in d1:
        surfaces_that_name_it.append("the 409")
    check(
        "NOT ONE operator surface names the task or says the review is unattended",
        not surfaces_that_name_it,
        str(surfaces_that_name_it),
    )

    head("LANE 4 -- the cure is one transition, and the operator is never told they need it")
    move(t1, "revision_needed")
    c3, d3 = fire(job1, "after the operator's rescue")
    check(
        "once rescued by hand the loop moves again",
        c3 == 200,
        f"{c3} {json.dumps(d3, default=str)[:200]}",
    )
    if c3 == 200:
        # A selection means a turn was started. Park it: this drive spends no model time, and a
        # live turn left behind would poison LANE 5's reading of the roster.
        note("the rescue started a turn -- the drive stops it rather than spending it")
        for r in live_runs():
            api("POST", f"/projects/{P}/runs/{r['id']}/cancel", {})
        time.sleep(3)

    head("LANE 5 -- one variable changed: the AUTHOR in `assignee` instead of a reviewer")
    # Written expecting F70's recovery to fire here and answer differently. It does not, and the
    # reason is worth more than the expectation was: `wedged_review` asks
    # `assignee in agents_that_worked(task)`, and `agents_that_worked` reads `TaskTransition.
    # actor_agent` -- which is NULL for every edge an operator walked by hand
    # (`task_transition_service.py:199-224`, whose own docstring says so). A task whose whole
    # history is the operator's names no agent, so the author is not recognised as the author and
    # the branch takes the `in_flight` arm again. That is F142's measured case -- "an operator who
    # moved a stuck task to under_review by hand" -- reachable through the very fallback that was
    # added to close it. Filed as F167.
    job2, loop2, t2 = make_loop(f"f154-author-{RUN}", "Add one line to CHANGELOG")
    wedge(t2, AUTHOR)
    row2 = task(t2)
    check(
        "the second task is under_review with its own author on it",
        row2 and row2["status"] == "under_review" and row2.get("assignee") == AUTHOR,
        f"{row2 and row2['status']} / {row2 and row2.get('assignee')}",
    )
    c4, d4 = fire(job2, "author wedged")
    note("the author-wedged firing", f"{c4} {json.dumps(d4, default=str)[:300]}")
    check(
        "F167: the AUTHOR-wedged row answers 409 'nothing is wrong' too -- F70's recovery "
        "cannot see an author whose history is the operator's",
        c4 == 409 and "nothing is wrong" in json.dumps(d4, default=str).lower(),
        f"{c4}",
    )
    s2 = summary(job2)
    lv2 = s2.get("loop") or {}
    cur2 = lv2.get("current_tasks", s2.get("current_tasks")) or []
    mine2 = [c for c in cur2 if c.get("id") == t2]
    check(
        "and the board names the AUTHOR as the agent holding the review",
        bool(mine2) and mine2[0].get("agent") == AUTHOR,
        json.dumps(mine2, default=str)[:300],
    )
    note(
        "the bound on this measurement",
        "every edge here was walked by the operator, so no transition names an agent. A history "
        "with an agent-walked edge is NOT measured by this drive and F70 may well recover it.",
    )
    for r in live_runs():
        api("POST", f"/projects/{P}/runs/{r['id']}/cancel", {})

    head("TEARDOWN -- leave no job enabled")
    time.sleep(2)
    for jid in JOBS:
        code, _ = api("PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        print(f"  disable {jid} -> {code}")
    code, jobs_now = api("GET", f"/projects/{P}/jobs")
    left = [j.get("id") for j in (jobs_now or []) if j.get("enabled")]
    check("no job left enabled", not left, str(left))

    head("VERDICT")
    for label, ok, detail in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {detail}" if detail else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}")
    print(f"  project {P} at {ROOT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
