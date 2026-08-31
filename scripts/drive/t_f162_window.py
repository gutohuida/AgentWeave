"""F162 -- approve INSIDE the window and read what the integration records.

F162 was measured twice during DRIVE-2, at 6-second granularity: a loop's task reads `completed`
(written by the agent's own `update_task`, mid-turn) while the tip of `agentweave/task/<id>` is
still the commit the branch was cut from. The Hub commits the agent's work onto that branch by an
auto-snapshot at turn END, which is a later moment.

The WINDOW is measured. The CONSEQUENCE is not -- it was read from the code, which is the half this
repository's own discipline says gets you. The claim under test:

    an approval inside the window resolves the BASE commit as the merge target, `integrate_task`
    finds it already reachable from the main branch, records ALREADY_INTEGRATED, and `is_retryable`
    deliberately classifies that skip as NOT retryable -- so the work is stranded with the task at
    `approved`, the file on a branch nobody will merge, and no button on screen.

Three outcomes are all worth having and this drive prints which one happened:

  REPRODUCED   -- the three transitions land while the agent is still mid-turn, the integration
                  skips as already-integrated with no retry, and the file never reaches the main
                  branch. F162 becomes a defect with a repro.
  GUARDED      -- some transition is REFUSED while a run is live. F162 downgrades, and the drive
                  says exactly which request refused and with what sentence.
  NARROWER     -- the tip has already moved by the time the task reads `completed` at 1s
                  granularity. F162's window is narrower than 6s sampling suggested, and the drive
                  says how narrow.

Method: one loop, declaration OMITTED (so the branch tip governs the merge -- LANE A of DRIVE-2,
already proven to land), fired by hand, then a TIGHT 1-second poll of `GET /tasks` and the git
ref, and the moment the task reads `completed` the three transitions F163 documents are fired
back to back with no settle in between.

Ancestry and content are asked of the REPOSITORY, never of the `TaskIntegration` row.

Real surface only. No row inserts. Haiku turns. LEAVES NO JOB ENABLED.

Run:  AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 -u t_f162_window.py
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or ""
AUTHOR = os.environ.get("AW_AGENT") or "alpha"
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
FILE_A = f"f162_{RUN}.py"

VERDICTS = []
ROOT = None
MAIN = None
TIMELINE = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    print(f"  [obs] {label}" + (f" -- {detail}" if detail else ""))


def stamp(what, detail=""):
    TIMELINE.append((time.monotonic(), what, detail))
    print(f"  [t+{TIMELINE[-1][0] - T0:7.2f}s] {what} {detail}")


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def blob(x, limit=1200):
    return json.dumps(x, indent=1, default=str)[:limit]


def call(label, method, path, body=None, expect=None, show=False, limit=900):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED'}")
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message") or detail
    if isinstance(detail, str):
        print(f"      refusal: {detail[:400]}")
    elif show or not ok:
        print("      " + blob(out, limit).replace(chr(10), chr(10) + "      "))
    return code, out


def agents():
    c, rows = api("GET", f"/projects/{P}/agents")
    return rows if isinstance(rows, list) else []


def statuses():
    return {a["name"]: a["status"] for a in agents()}


def busy_names():
    return [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]


def board():
    c, t = api("GET", f"/projects/{P}/tasks")
    return t if isinstance(t, list) else t.get("tasks", [])


def tasks_of(loop_row_id):
    return [t for t in board() if t.get("loop_id") == loop_row_id]


def jobs():
    c, rows = api("GET", f"/projects/{P}/jobs")
    return rows if isinstance(rows, list) else []


def git(*args):
    r = subprocess.run(
        ["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def on_main(sha):
    if not sha:
        return False
    code, _, _ = git("merge-base", "--is-ancestor", sha, MAIN)
    return code == 0


def file_on_main(name):
    code, body, _ = git("show", f"{MAIN}:{name}")
    return body if code == 0 else None


def task_branch_tip(task_id):
    code, tip, _ = git("rev-parse", "--verify", f"refs/heads/agentweave/task/{task_id}")
    return tip if code == 0 else None


def integrations(task_id):
    c, drawer = api("GET", f"/projects/{P}/tasks/{task_id}/integrations")
    return drawer.get("integrations", []) if isinstance(drawer, dict) else []


def trigger(agent, message):
    return api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": agent, "message": message, "overrides": {"permission_mode": "workspace"}},
        timeout=40,
    )


def settle(rounds=40, gap=6, label=""):
    for i in range(rounds):
        time.sleep(gap)
        busy = busy_names()
        print(f"      t+{(i + 1) * gap:>3}s busy={busy} {label}")
        if i >= 1 and not busy:
            return True
    print("      (did not settle)")
    return False


def preflight():
    global ROOT, MAIN
    head("PRE. Preconditions -- asserted, never assumed")
    if not P:
        sys.exit("set AW_PROJECT")
    if P in ("proj-5e960453", "proj-18e5d4e0"):
        sys.exit("refusing to drive against a forbidden project")
    c, rows = api("GET", "/projects")
    row = next((x for x in (rows or []) if x.get("id") == P), None) if isinstance(rows, list) else None
    if row is None:
        sys.exit(f"project {P} not found")
    ROOT = row["working_directory"]
    c, settings = api("GET", f"/projects/{P}/settings")
    MAIN = settings.get("main_branch") if isinstance(settings, dict) else None
    if not MAIN:
        sys.exit("no main branch chosen -- the pass condition is unreachable")
    if not settings.get("allow_agent_jobs"):
        sys.exit("allow_agent_jobs is off -- `create_loop` would be refused before it is reached")
    code, out, _ = git("status", "--porcelain")
    if code != 0:
        sys.exit(f"{ROOT} is not a git repository")
    if out:
        sys.exit(f"{ROOT} is dirty before the drive:\n{out}")
    a = next((x for x in agents() if x["name"] == AUTHOR), None)
    if a is None or a.get("archived") or not a.get("runner_id"):
        sys.exit(f"agent {AUTHOR!r} must exist, be open, and be bound to a runner")
    if busy_names():
        sys.exit(f"agents busy before the run: {busy_names()}")
    live = [j for j in jobs() if j.get("enabled")]
    if live:
        sys.exit(f"jobs already enabled: {[j.get('id') for j in live]}")
    code, base_head, _ = git("rev-parse", MAIN)
    print(f"  [OK ] {ROOT}, main {MAIN!r} at {base_head[:12]}, tree clean")
    print(f"  [OK ] author {AUTHOR}, no job enabled, run tag {RUN}, target {FILE_A}")
    return base_head


def make_loop(name):
    """Ask the author for a loop through `create_loop`, declaration OMITTED.

    Same route DRIVE-2 LANE A drove, because that is the one already proven to land work: with no
    document and no requirement link, `merge_targets` resolves the BRANCH TIP, which is precisely
    the thing F162 says is stale inside the window. Falls back to the operator's route if the turn
    does not produce a loop, because the window is the question here, not `create_loop`.
    """
    msg = (
        f"Call the create_loop tool exactly once, then stop and say what it returned.\n"
        f"  name: {name}\n"
        f"  agent: {AUTHOR}\n"
        f'  message: "Work the task you have been given. Keep the edit minimal."\n'
        f"  cron: 0 4 1 1 *\n"
        f"  purpose: Grow the calculator by one function.\n"
        f"  stop_when_queue_empties: true\n"
        f"  Do NOT pass work_needs_evidence at all -- leave it unset.\n"
        f"  initial_tasks: a single task, "
        f'{{"title": "Add cube to {FILE_A}", "description": "Create a file called '
        f"{FILE_A} in your working directory containing exactly one function, cube(a), that "
        f'returns a cubed. Change nothing else. Do not run git."}}\n'
        f"Create nothing else. Do not create the file yourself. Do not create a task with "
        f"create_task."
    )
    c, t = trigger(AUTHOR, msg)
    print(f"  trigger {AUTHOR} -> {c}")
    for _ in range(30):
        time.sleep(6)
        j = next((x for x in jobs() if x.get("name") == name), None)
        if j:
            check("create_loop was driven -- the loop exists", True, j.get("id"))
            return j
        print(f"      waiting for {name}, busy={busy_names()}")
    note("the agent did not create the loop; falling back to the operator route so the window "
         "question is still answered")
    c, j = call("operator creates the loop instead", "POST", f"/projects/{P}/jobs",
                {"name": name, "agent": AUTHOR,
                 "message": "Work the task you have been given. Keep the edit minimal.",
                 "cron": "0 4 1 1 *",
                 "purpose": "Grow the calculator by one function.",
                 "stop_when_queue_empties": True,
                 "initial_tasks": [{"title": f"Add cube to {FILE_A}",
                                    "description": f"Create a file called {FILE_A} in your "
                                    "working directory containing exactly one function, cube(a), "
                                    "that returns a cubed. Change nothing else. Do not run git."}]},
                expect=(200, 201))
    return j if isinstance(j, dict) else None


def main():
    global T0
    T0 = time.monotonic()
    base_head = preflight()
    created = []
    outcome = "UNDECIDED"

    try:
        head("A. One loop, declaration OMITTED, fired by hand")
        name = f"f162-{RUN}"
        job = make_loop(name)
        if not job:
            check("a loop exists to drive", False)
            return
        job_id = job.get("id")
        created.append(job_id)
        settle(rounds=8, label="(after loop creation)")
        c, summary = api("GET", f"/projects/{P}/jobs/{job_id}")
        loop = (summary.get("loop") or {}) if isinstance(summary, dict) else {}
        loop_id = loop.get("id")
        check("the job has a Loop row", bool(loop_id), repr(loop_id))
        check("the omitted declaration is NULL on the row",
              loop.get("work_needs_evidence", "MISSING") is None,
              repr(loop.get("work_needs_evidence", "MISSING")))

        call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, expect=200)
        stamp("job fired")

        # -------------------------------------------------------------- B
        head("B. TIGHT 1-second poll -- catch the instant the task reads `completed`")
        t_a = None
        tip_at_completed = None
        busy_at_completed = None
        deadline = time.monotonic() + 480
        last_print = 0.0
        while time.monotonic() < deadline:
            rows = tasks_of(loop_id)
            if rows:
                row = rows[0]
                t_a = row["id"]
                st = row.get("status")
                if st in ("completed", "under_review", "approved"):
                    tip_at_completed = task_branch_tip(t_a)
                    busy_at_completed = busy_names()
                    stamp("task reads " + repr(st),
                          f"tip={(tip_at_completed or 'none')[:12]} busy={busy_at_completed}")
                    break
                if time.monotonic() - last_print > 10:
                    last_print = time.monotonic()
                    print(f"      {t_a} {st!r} busy={busy_names()}")
            time.sleep(1.0)

        if not t_a or tip_at_completed is None and not busy_at_completed:
            check("the loop's task reached `completed` inside the deadline", False, repr(t_a))
            return
        check("the loop's task reached `completed` with nobody's hand on it", True, t_a)

        tip_is_stale = tip_at_completed == base_head or tip_at_completed is None
        agent_still_running = bool(busy_at_completed)
        note("base commit", base_head[:12])
        note("tip at the instant the task read `completed`", (tip_at_completed or "none")[:12])
        note("agent status at that instant", str(busy_at_completed))

        # -------------------------------------------------------------- C
        head("C. The three transitions, back to back, WITH NO SETTLE -- inside the window")
        hops = []
        c1, o1 = call("1/3 assignee -> null", "PATCH", f"/projects/{P}/tasks/{t_a}",
                      {"assignee": None})
        hops.append(("assignee -> null", c1, o1))
        stamp("hop 1 done", str(c1))
        c2, o2 = call("2/3 -> under_review", "PATCH", f"/projects/{P}/tasks/{t_a}",
                      {"status": "under_review"})
        hops.append(("-> under_review", c2, o2))
        stamp("hop 2 done", str(c2))
        c3, o3 = call("3/3 -> approved", "PATCH", f"/projects/{P}/tasks/{t_a}",
                      {"status": "approved"}, show=True, limit=800)
        hops.append(("-> approved", c3, o3))
        stamp("hop 3 done", str(c3))
        tip_after_approval = task_branch_tip(t_a)
        busy_after_approval = busy_names()
        note("tip immediately after the approval", (tip_after_approval or "none")[:12])
        note("agent status immediately after the approval", str(busy_after_approval))

        approved = c3 == 200
        refused = [(what, code, (out.get("detail") if isinstance(out, dict) else out))
                   for what, code, out in hops if code not in (200, 201)]

        rows_i = integrations(t_a)
        print("      --- integrations recorded at approval time")
        print("      " + blob(rows_i, 1400).replace(chr(10), chr(10) + "      "))
        last = rows_i[-1] if rows_i else {}

        # -------------------------------------------------------------- D
        head("D. Which of the three outcomes happened?")
        if refused and not approved:
            outcome = "GUARDED"
            what, code, detail = refused[-1]
            check("F162 DOWNGRADES: the product refused a transition inside the window",
                  True, f"{what} -> {code}: {str(detail)[:200]}")
            note("the guard is at", f"{what} answering {code}")
        elif not tip_is_stale:
            outcome = "NARROWER"
            check("F162 NARROWS: the tip had already moved when the task read `completed`",
                  True, f"tip {(tip_at_completed or '')[:12]} != base {base_head[:12]}")
            note("at 1s granularity the window did not contain the read; "
                 "the 6s measurement straddled the snapshot", "")
        else:
            check("the approval landed inside the window -- task is `approved`", approved,
                  f"hop3={c3}")
            note("nothing was refused; the product let approval run against a stale tip", "")
            stale_target = (last.get("commit_sha") or "")
            check("the integration did NOT merge",
                  last.get("outcome") != "merged", repr(last.get("outcome")))
            check("and the target it resolved was the BASE commit, not the agent's work",
                  stale_target[:12] == base_head[:12] or last.get("outcome") == "skipped",
                  f"target={stale_target[:12]} base={base_head[:12]}")
            check("the skip reason names already-integrated / nothing to merge",
                  any(k in str(last.get("reason")).lower()
                      for k in ("already", "nothing to merge", "ancestor")),
                  str(last.get("reason"))[:180])
            check("THE STRAND: the skip offers NO retry button",
                  last.get("retryable") is False, repr(last.get("retryable")))
            outcome = "REPRODUCED"

        # -------------------------------------------------------------- E
        head("E. Let the turn end, then read the repository -- did the work land at all?")
        settle(rounds=40, label="(waiting for the turn to end)")
        tip_final = task_branch_tip(t_a)
        note("tip once the turn ended", (tip_final or "none")[:12])
        window_moved = bool(tip_final) and tip_final != tip_at_completed
        note("did the snapshot arrive after the approval?", str(window_moved))
        body = file_on_main(FILE_A)
        rows_i = integrations(t_a)
        print("      --- integrations after the turn ended")
        print("      " + blob(rows_i, 1400).replace(chr(10), chr(10) + "      "))
        last = rows_i[-1] if rows_i else {}
        after = next((x for x in board() if x["id"] == t_a), {})
        note("the task's final status", repr(after.get("status")))
        code, log, _ = git("log", "--oneline", "-6", MAIN)
        print(f"      --- {MAIN} now\n      " + log.replace(chr(10), chr(10) + "      "))

        if outcome == "REPRODUCED":
            check("THE CONSEQUENCE: the agent's work is on its branch and NOT on the main branch",
                  bool(tip_final) and tip_final != base_head and body is None,
                  f"branch tip {(tip_final or '')[:12]}, {FILE_A} on {MAIN}: "
                  f"{'absent' if body is None else 'present'}")
            check("and the task is parked at `approved` with nothing left to press",
                  after.get("status") == "approved" and last.get("retryable") is not True,
                  f"{after.get('status')!r} retryable={last.get('retryable')!r}")
        elif outcome == "GUARDED":
            check("after the turn ends the ordinary approval still lands the work",
                  True, "checked below")
            c, _ = call("retry the three hops after the turn ended (1/3)", "PATCH",
                        f"/projects/{P}/tasks/{t_a}", {"assignee": None})
            call("retry (2/3)", "PATCH", f"/projects/{P}/tasks/{t_a}",
                 {"status": "under_review"})
            call("retry (3/3)", "PATCH", f"/projects/{P}/tasks/{t_a}",
                 {"status": "approved"}, show=True, limit=600)
            time.sleep(2)
            body = file_on_main(FILE_A)
            rows_i = integrations(t_a)
            last = rows_i[-1] if rows_i else {}
            check("outside the window the same three hops merge the work",
                  body is not None and "def cube" in body,
                  "absent" if body is None else body.replace("\n", " / ")[:120])
        else:  # NARROWER
            check("the work reached the main branch as usual",
                  body is not None and "def cube" in body,
                  "absent" if body is None else body.replace("\n", " / ")[:120])

        head("F. The window, measured at 1s")
        for at, what, detail in TIMELINE:
            print(f"  t+{at - T0:7.2f}s  {what} {detail}")
        print(f"\n  OUTCOME: {outcome}")

    finally:
        head("Z. LEAVE NO JOB ENABLED")
        for jid in created:
            call(f"disable {jid}", "PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        for j in jobs():
            if j.get("enabled"):
                call(f"disable stray {j.get('id')}", "PATCH", f"/projects/{P}/jobs/{j['id']}",
                     {"enabled": False})
        print(f"  agents: {statuses()}")
        code, dirty, _ = git("status", "--porcelain")
        print(f"  checkout dirty: {dirty!r}")
        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held      OUTCOME: {outcome}")


def lane_wide():
    """LANE 2 -- how WIDE is the window? Nobody has measured that; only that it is open.

    Lane 1 caught it and reproduced the consequence, but there the agent's *last* act was
    `update_task`, so the snapshot followed within a second. That is the narrow end. The window is
    not a fixed race: it runs from `update_task(completed)` to the END OF THE TURN, so its width is
    whatever the agent chooses to do next -- which the product does not constrain at all.

    This lane asks for an ordinary multi-step turn: build the thing, mark it done, then keep
    working. No approval is attempted; the tip is simply polled every second from the moment the
    task reads `completed` until it moves. The number that comes out is the window's width, and it
    is the difference between "a race a human could not hit" and "a window an operator sits in".
    """
    global T0
    T0 = time.monotonic()
    base_head = preflight()
    created = []
    try:
        head("LANE 2. An ordinary multi-step turn -- mark the task done, then keep working")
        name = f"f162w-{RUN}"
        w1, w2 = f"f162w_{RUN}_a.py", f"f162w_{RUN}_b.py"
        c, job = call(
            "create the loop (operator route -- `create_loop` was already driven in lane 1)",
            "POST", f"/projects/{P}/jobs",
            {"name": name, "agent": AUTHOR,
             "message": "Work the task you have been given, in the order it gives the steps.",
             "cron": "0 4 1 1 *", "purpose": "Grow the calculator by one function.",
             "stop_when_queue_empties": True,
             "initial_tasks": [{
                 "title": f"Add cube to {w1}, then tidy up",
                 "description":
                     f"Do these three steps IN THIS ORDER and do not reorder them.\n"
                     f"  1. Create a file called {w1} in your working directory containing "
                     f"exactly one function, cube(a), that returns a cubed.\n"
                     f"  2. Call the update_task tool to set this task's status to completed.\n"
                     f"  3. THEN, after step 2 and not before, create a second file called {w2} "
                     f"containing a module docstring that explains what {w1} is for, and then "
                     f"read both files back and say what they contain.\n"
                     f"Do not run git."}]},
            expect=(200, 201))
        if not isinstance(job, dict) or not job.get("id"):
            check("the loop was created", False, blob(job, 400))
            return
        job_id = job["id"]
        created.append(job_id)
        c, summary = api("GET", f"/projects/{P}/jobs/{job_id}")
        loop_id = ((summary.get("loop") or {}) if isinstance(summary, dict) else {}).get("id")
        check("the job has a Loop row", bool(loop_id), repr(loop_id))

        call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, expect=200)
        stamp("job fired")

        t_a = None
        completed_at = None
        deadline = time.monotonic() + 480
        last_print = 0.0
        while time.monotonic() < deadline:
            rows = tasks_of(loop_id)
            if rows:
                t_a = rows[0]["id"]
                st = rows[0].get("status")
                if st in ("completed", "under_review", "approved"):
                    completed_at = time.monotonic()
                    stamp("task reads " + repr(st),
                          f"tip={(task_branch_tip(t_a) or 'none')[:12]} busy={busy_names()}")
                    break
                if time.monotonic() - last_print > 15:
                    last_print = time.monotonic()
                    print(f"      {t_a} {st!r} busy={busy_names()}")
            time.sleep(1.0)
        if completed_at is None:
            check("the task reached `completed` inside the deadline", False, repr(t_a))
            return

        tip0 = task_branch_tip(t_a)
        check("the tip is STILL the base commit at the moment the task reads `completed`",
              tip0 == base_head, f"{(tip0 or 'none')[:12]} vs base {base_head[:12]}")

        head("Poll the tip every second until it moves -- this IS the window")
        width = None
        while time.monotonic() - completed_at < 480:
            tip = task_branch_tip(t_a)
            if tip and tip != tip0:
                width = time.monotonic() - completed_at
                stamp("the snapshot arrived", f"tip {tip[:12]}")
                break
            if not busy_names():
                width = time.monotonic() - completed_at
                stamp("the turn ended without the tip moving", f"tip {(tip or 'none')[:12]}")
                break
            time.sleep(1.0)
        if width is None:
            check("the window closed inside the deadline", False)
            return
        note("THE WIDTH OF THE WINDOW", f"{width:.1f} seconds, with the task readable as "
             f"`completed` and approvable for every one of them")
        check("the window is wide enough for an operator to sit in it (>= 10s)", width >= 10,
              f"{width:.1f}s")

        head("Approve normally, outside the window, so the fixture is left landing its work")
        settle(rounds=40, label="(waiting for the turn to end)")
        call("1/3 assignee -> null", "PATCH", f"/projects/{P}/tasks/{t_a}", {"assignee": None})
        call("2/3 -> under_review", "PATCH", f"/projects/{P}/tasks/{t_a}",
             {"status": "under_review"})
        call("3/3 -> approved", "PATCH", f"/projects/{P}/tasks/{t_a}", {"status": "approved"})
        time.sleep(2)
        body = file_on_main(w1)
        rows_i = integrations(t_a)
        print("      " + blob(rows_i, 900).replace(chr(10), chr(10) + "      "))
        check("outside the window the same three hops DO land the work",
              body is not None and "def cube" in body,
              "absent" if body is None else body.replace("\n", " / ")[:120])

        head("The window, measured at 1s")
        for at, what, detail in TIMELINE:
            print(f"  t+{at - T0:7.2f}s  {what} {detail}")
    finally:
        head("Z. LEAVE NO JOB ENABLED")
        for jid in created:
            call(f"disable {jid}", "PATCH", f"/projects/{P}/jobs/{jid}", {"enabled": False})
        for j in jobs():
            if j.get("enabled"):
                call(f"disable stray {j.get('id')}", "PATCH", f"/projects/{P}/jobs/{j['id']}",
                     {"enabled": False})
        print(f"  agents: {statuses()}")
        code, dirty, _ = git("status", "--porcelain")
        print(f"  checkout dirty: {dirty!r}")
        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    (lane_wide if os.environ.get("AW_WIDE") else main)()
