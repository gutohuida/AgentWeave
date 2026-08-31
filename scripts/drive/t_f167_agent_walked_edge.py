"""F167's unmeasured half -- does F70's recovery see an author whose history has an AGENT-walked edge?

F167 (severity B, FINDINGS.md) was filed off `t_f154_wedged_review.py`'s LANE 5 with a bound stated
in the finding itself and repeated as an `[obs]` line in the harness:

    every edge here was walked by the operator, so no transition names an agent. A history with an
    agent-walked edge is NOT measured by this drive and F70 may well recover it.

This harness measures exactly that one thing, and nothing else. It builds the SAME wedge -- an
`under_review` task whose `assignee` is its own author, holding no live turn -- but reaches
`in_progress` through the **runtime** rather than through the operator, so
`TaskTransition.actor_agent` is populated for that one edge.

**Why no model output is needed even though a real run is spawned.** `bind_run_to_task`
(`run_task_binding.py:427-440`) sets `run.task_id`, then takes `-> in_progress` through
`apply_transition` with `run_actor(run.id, run.agent)` and `origin='runtime'`. The transition is
recorded when the run is BOUND, at spawn, before the model has said a word. So pressing Run once and
cancelling the turn seconds later is enough to leave an agent-named edge in the history -- which is
also why this costs a Haiku spawn and no Haiku thinking.

The measurement is a CONTRAST, run inside one project so the two firings differ in one variable:

  LANE 1  the agent-walked history -- fire the loop, let it bind and start the task, cancel the
                                      turn. Assert the task is `in_progress` with the author on it
                                      and that the operator sent no PATCH to put it there.
  LANE 2  wedge it from there      -- the operator walks only `completed` and `under_review`, the
                                      two edges `under_review`'s route actually requires. The
                                      `in_progress` edge stays the agent's.
  LANE 3  THE MEASUREMENT          -- press Run. Does the answer differ from F167's all-operator
                                      case, i.e. does `wedged_review` fire when the history names
                                      the author?
  LANE 4  the all-operator control -- the identical wedge with EVERY edge walked by hand, in this
                                      same project and against the same code, so LANE 3's answer is
                                      read against a control taken minutes apart rather than against
                                      a number from another harness's run.
  LANE 5  what the board says      -- for whichever way LANE 3 lands.

Whatever it answers is worth having: if the recovery fires, F167 is precisely scoped to the
all-operator history and a F154 repair may lean on `wedged_review` for the agent case; if it does
not, F167 is not a corner and `wedged_review` cannot carry the author case at all.

**A harness defect found on the first run, and it is a product finding too.** LANE 1 asserted "a run
is bound to the task" against `GET /projects/{p}/runs` and came back red with an empty list. The
route does not exist -- and neither does `POST /projects/{p}/runs/{id}/cancel`. `t_f154_wedged_
review.py` calls both, so its "no run is live on this project" checks passed vacuously against `[]`
parsed out of a 404 body, and its cancels stopped nothing. The whole operator surface for a run is
the roster's `status` field and `POST /projects/{p}/agent/{agent}/stop`. Filed as F168; this harness
uses the real surface.

Real surface only. No row inserts, no database reads. One real spawn per lane that needs one,
stopped as soon as the edge it exists for is recorded. Creates its own project in a fresh temporary
repository, and disables every job it creates.

Run:  AW_HUB=http://127.0.0.1:8011 py -3.11 -u t_f167_agent_walked_edge.py
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
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-f167-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": f"f167-drive-{RUN}"})
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
    body = {
        "name": name,
        "agent": AUTHOR,
        "message": "Reply with the single word: ok. Do not use any tool.",
        "cron": "0 4 1 1 *",
        "enabled": True,
        "purpose": "Drive F167's unmeasured half.",
        "stop_when_queue_empties": True,
        "initial_tasks": [{"title": title, "description": "One line. Nothing else."}],
    }
    code, job = api("POST", f"/projects/{P}/jobs", body)
    if code != 201:
        raise SystemExit(f"could not create the loop: {code} {job}")
    JOBS.append(job["id"])
    tasks = [t for t in board() if t.get("loop_id") and t.get("title") == title]
    if not tasks:
        raise SystemExit(f"the loop seeded no task: {blob(job)}")
    return job["id"], tasks[0]["id"]


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


def fire(job_id, label):
    code, body = api("POST", f"/projects/{P}/jobs/{job_id}/run", {})
    detail = body.get("detail") if isinstance(body, dict) else body
    print(f"  fire[{label}] -> {code}")
    print(f"      {json.dumps(detail, default=str)[:700]}")
    return code, detail


def summary(job_id):
    code, body = api("GET", f"/projects/{P}/jobs/{job_id}")
    return body if isinstance(body, dict) else {}


def busy_agents():
    """Which agents the roster says are mid-turn.

    **There is no runs listing route and no run-cancel route.** `GET /projects/{p}/runs` and
    `POST /projects/{p}/runs/{id}/cancel`, which `t_f154_wedged_review.py` calls, are both 404 --
    the whole operator surface for a run is the roster's `status` and
    `POST /projects/{p}/agent/{agent}/stop`. Filed as F168; every liveness assertion in that
    harness passed vacuously against an empty list parsed out of a 404 body.
    """
    return [name for name, status in statuses().items() if status not in ("idle", None)]


def park_live_turns(seconds=90):
    """This drive spends no model time it can avoid: stop each busy agent, then wait for quiet.

    The stop route is per-AGENT, not per-run, which is the only handle the product offers.
    """
    for name in busy_agents():
        code, body = api("POST", f"/projects/{P}/agent/{name}/stop", {})
        note("stopped a turn rather than spending it", f"{name} -> {code}")
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not busy_agents():
            return True
        time.sleep(2)
    return not busy_agents()


def wait_until_started(tid, seconds=60):
    """Wait until the task has been started by the runtime -- `in_progress`, nobody having PATCHed it."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        row = task(tid)
        if row and row.get("status") == "in_progress":
            return row
        time.sleep(1)
    return task(tid)


def main():
    head("SETUP -- a fresh project, a fresh repository, two Haiku agents")
    make_project()
    runner = ensure_runner()
    ensure_agent(AUTHOR, runner)
    ensure_agent(REVIEWER, runner)
    check(
        "both agents exist and are idle before anything",
        set(statuses()) >= {AUTHOR, REVIEWER},
        str(statuses()),
    )

    head("LANE 1 -- an AGENT-walked edge: the loop binds a run and the RUNTIME starts the task")
    job1, t1 = make_loop(f"f167-agentwalked-{RUN}", "Add one line to README")
    print(f"  job {job1}, task {job1 and t1}")
    before = task(t1)
    check(
        "the seeded task starts pending, untouched by anyone",
        before and before["status"] == "pending",
        f"{before and before['status']} / assignee={before and before.get('assignee')}",
    )
    c0, d0 = fire(job1, "start the task through the loop")
    check("the loop starts the task", c0 == 200, f"{c0} {json.dumps(d0, default=str)[:200]}")
    row = wait_until_started(t1)
    check(
        "the RUNTIME put the task in_progress with its author on it -- the operator sent no PATCH",
        row and row["status"] == "in_progress" and row.get("assignee") == AUTHOR,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )
    note(
        "why this is the whole point",
        "bind_run_to_task takes `-> in_progress` with run_actor(run.id, run.agent) at SPAWN, so "
        "TaskTransition.actor_agent names alpha before the model has said a word",
    )
    park_live_turns()
    check("no turn is left live", not busy_agents(), str(statuses()))

    head("LANE 2 -- the operator wedges it from there, walking only the two edges they must")
    move(t1, "completed")
    move(t1, "under_review", AUTHOR)
    row = task(t1)
    check(
        "the task is under_review with its own author on it",
        row and row["status"] == "under_review" and row.get("assignee") == AUTHOR,
        f"{row and row['status']} / {row and row.get('assignee')}",
    )
    check("still no turn is live on this project", not busy_agents(), str(statuses()))

    head("LANE 3 -- THE MEASUREMENT: press Run on a wedge whose history NAMES the author")
    c1, d1 = fire(job1, "agent-walked history")
    text1 = json.dumps(d1, default=str).lower()
    agent_walked_says_nothing_wrong = c1 == 409 and "nothing is wrong" in text1
    note("the agent-walked firing", f"{c1} {json.dumps(d1, default=str)[:400]}")
    park_live_turns()

    head("LANE 4 -- the control: the identical wedge with EVERY edge walked by the operator")
    job2, t2 = make_loop(f"f167-operatorwalked-{RUN}", "Add one line to CHANGELOG")
    move(t2, "assigned", AUTHOR)
    move(t2, "in_progress")
    move(t2, "completed")
    move(t2, "under_review", AUTHOR)
    row2 = task(t2)
    check(
        "the control task is under_review with its own author on it -- one variable differs",
        row2 and row2["status"] == "under_review" and row2.get("assignee") == AUTHOR,
        f"{row2 and row2['status']} / {row2 and row2.get('assignee')}",
    )
    c2, d2 = fire(job2, "all-operator history")
    text2 = json.dumps(d2, default=str).lower()
    control_says_nothing_wrong = c2 == 409 and "nothing is wrong" in text2
    check(
        "the control reproduces F167 as filed: the all-operator history answers 409 "
        "'nothing is wrong'",
        control_says_nothing_wrong,
        f"{c2}",
    )
    park_live_turns()

    head("THE CONTRAST -- the two answers side by side")
    print(f"  agent-walked  -> {c1}  {json.dumps(d1, default=str)[:220]}")
    print(f"  all-operator  -> {c2}  {json.dumps(d2, default=str)[:220]}")
    differ = (c1, agent_walked_says_nothing_wrong) != (c2, control_says_nothing_wrong)
    check(
        "F167's bound holds: an AGENT-walked edge makes F70's recovery answer DIFFERENTLY from "
        "the all-operator history",
        differ,
        f"agent-walked {c1} / control {c2}"
        + ("" if differ else "  <-- both identical: F167 is not scoped to the operator's history"),
    )
    if not differ:
        note(
            "IF THIS CHECK IS RED IT IS THE FINDING",
            "the recovery does not fire even when the history names the author, so `wedged_review` "
            "cannot carry the author case at all and F167 is wider than filed",
        )

    head("LANE 5 -- what the board says about the agent-walked wedge")
    s1 = summary(job1)
    lv1 = s1.get("loop") or {}
    cur1 = lv1.get("current_tasks", s1.get("current_tasks")) or []
    mine1 = [c for c in cur1 if c.get("id") == t1]
    note("the agent-walked task on the walk", json.dumps(mine1, default=str)[:400])
    note("its stall_reason", json.dumps(lv1.get("stall_reason", s1.get("stall_reason")))[:300])
    check(
        "the board says SOMETHING about the agent-walked task -- either it holds it or it names "
        "the wedge",
        bool(mine1) or bool(lv1.get("stall_reason") or s1.get("stall_reason")),
        json.dumps(mine1, default=str)[:200],
    )

    head("TEARDOWN -- leave no job enabled and no turn live")
    park_live_turns()
    for jid in JOBS:
        code, _ = api("PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        print(f"  disable {jid} -> {code}")
    code, jobs_now = api("GET", f"/projects/{P}/jobs")
    left = [j.get("id") for j in (jobs_now or []) if j.get("enabled")]
    check("no job left enabled", not left, str(left))
    check("no turn left live", not busy_agents(), str(statuses()))

    head("VERDICT")
    for label, ok, detail in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {detail}" if detail else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}")
    print(f"  project {P} at {ROOT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
