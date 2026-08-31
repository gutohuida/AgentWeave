"""DRIVE-2 part 1 -- does a LOOP's approved work reach the main branch, and does the
declaration decide it?

Task 8.5 of `a-loop-declares-whether-it-needs-evidence`, which is the only unticked item in that
change. Everything about the change is asserted by unit tests and NOTHING about it has been driven.
F124 was: approving a loop's task merges nothing, ever, for a structural reason -- a documentless
loop's task has no requirement any evidence could be recorded against, so `integration_targets` is
empty forever. This drive asks whether that is fixed *in the repository*, not in the Hub's account
of itself.

Three lanes, two of them on one agent turn each:

  LANE A (declaration OMITTED)   -- `create_loop` with `work_needs_evidence` left unset. The loop
                                    has no document and its task has no requirement link, so the
                                    branch tip governs. Approving must put the agent's file ON THE
                                    MAIN BRANCH.
  LANE A' (the retry button)     -- the main checkout is deliberately made dirty BEFORE approval,
                                    so the integration skips with `CHECKOUT_DIRTY`. Drives DRIVE-2
                                    item 4 for free: an unretryable skip must offer nothing, a
                                    dirty checkout must offer a button that works. Then the
                                    checkout is cleaned and the button is pressed for real.
  LANE B (declaration TRUE)      -- `create_loop` with `work_needs_evidence=True` on the same
                                    shape. Nothing may merge, and the reason must be the EVIDENCE
                                    one (`NOTHING_TO_MERGE`), never `NO_TASK_BRANCH` -- the two
                                    empty answers mean different things and the change exists
                                    partly to keep them apart.

Plus DRIVE-2 item 2, which costs no agent turn: the operator's route. `POST /jobs` must refuse
`work_needs_evidence` on a job that is not becoming a loop, and `PATCH /jobs/{id}` must refuse it
always, naming the create-a-new-loop remedy.

Ancestry is asked of the REPOSITORY (`git merge-base --is-ancestor`) and so is content
(`git show <main>:<file>`), never of the `TaskIntegration` row. A branch cut at dispatch and never
committed to has a tip that is already an ancestor of the main branch, so ancestry ALONE would pass
while nothing landed. The content check is the one that cannot be satisfied by doing nothing.

Real surface only. No row inserts. Haiku turns. LEAVES NO JOB ENABLED.

Run:  AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 -u t_drive2_loop_lands.py
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
OTHER = os.environ.get("AW_AGENT2") or "beta"
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
FILE_A = f"drive2_{RUN}_a.py"
FILE_B = f"drive2_{RUN}_b.py"

VERDICTS = []
ROOT = None
MAIN = None


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


def board():
    c, t = api("GET", f"/projects/{P}/tasks")
    return t if isinstance(t, list) else t.get("tasks", [])


def tasks_of(loop_row_id):
    """`Task.loop_id` is the *Loop* row's id, not the job's -- the two are different ids and
    matching on the job id would silently find nothing."""
    return [t for t in board() if t.get("loop_id") == loop_row_id]


def jobs():
    c, rows = api("GET", f"/projects/{P}/jobs")
    return rows if isinstance(rows, list) else []


def settle(rounds=30, gap=6, label=""):
    for i in range(rounds):
        time.sleep(gap)
        busy = [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]
        print(f"      t+{(i + 1) * gap:>3}s busy={busy} {label}")
        if i >= 1 and not busy:
            return
    print("      (did not settle)")


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
    """The file's content on the main branch, or None. This is THE question -- ancestry of a
    branch tip can be true while nothing landed, because the branch was cut from the main branch."""
    code, body, _ = git("show", f"{MAIN}:{name}")
    return body if code == 0 else None


def integrations(task_id):
    c, drawer = api("GET", f"/projects/{P}/tasks/{task_id}/integrations")
    rows = drawer.get("integrations", []) if isinstance(drawer, dict) else []
    return rows


def agent_output_text(name, limit=600):
    c, rows = api("GET", f"/projects/{P}/agents/{name}/output?limit={limit}")
    if not isinstance(rows, list):
        return ""
    out = []
    for r in rows:
        out.append(str(r.get("content") or ""))
        if r.get("payload"):
            out.append(json.dumps(r["payload"], default=str))
    return "\n".join(out)


def trigger(agent, message):
    return api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": agent, "message": message, "overrides": {"permission_mode": "workspace"}},
        timeout=40,
    )


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
    ros = agents()
    for name in (AUTHOR, OTHER):
        a = next((x for x in ros if x["name"] == name), None)
        if a is None or a.get("archived") or not a.get("runner_id"):
            sys.exit(f"agent {name!r} must exist, be open, and be bound to a runner")
    busy = [a["name"] for a in ros if a.get("status") not in ("idle", "offline", "error")]
    if busy:
        sys.exit(f"agents busy before the run: {busy}")
    live = [j for j in jobs() if j.get("enabled")]
    if live:
        sys.exit(f"jobs already enabled: {[j.get('id') for j in live]}")
    code, base_head, _ = git("rev-parse", MAIN)
    print(f"  [OK ] {ROOT}, main {MAIN!r} at {base_head[:12]}, tree clean")
    print(f"  [OK ] author {AUTHOR}, other {OTHER}, no job enabled, run tag {RUN}")
    return base_head


def ask_for_a_loop(agent, name, target_file, declaration):
    """One Haiku turn whose whole job is to call `create_loop`.

    Deliberately *not* created through `POST /jobs`: task 8.5 names `create_loop`, and the agent
    tool is the surface the new parameter was added to. What the operator's route does with the
    same field is section A, which costs no turn.
    """
    decl = (
        "Do NOT pass work_needs_evidence at all -- leave it unset."
        if declaration is None
        else f"Pass work_needs_evidence={declaration}."
    )
    msg = (
        f"Call the create_loop tool exactly once, then stop and say what it returned.\n"
        f"  name: {name}\n"
        f"  agent: {agent}\n"
        f'  message: "Work the task you have been given. Keep the edit minimal."\n'
        f"  cron: 0 4 1 1 *\n"
        f"  purpose: Grow the calculator by one function.\n"
        f"  stop_when_queue_empties: true\n"
        f"  {decl}\n"
        f"  initial_tasks: a single task, "
        f'{{"title": "Add power to {target_file}", "description": "Create a file called '
        f'{target_file} in your working directory containing exactly one function, '
        f"power(a, b), that returns a to the power of b. Change nothing else. Do not run "
        f'git."}}\n'
        f"Create nothing else. Do not create the file yourself. Do not create a task with "
        f"create_task."
    )
    c, t = trigger(agent, msg)
    print(f"  trigger {agent} -> {c}")
    if c != 200:
        print("      " + blob(t, 600))
    return c


def loop_named(name):
    return next((j for j in jobs() if j.get("name") == name), None)


def wait_for_job(name, seconds=180):
    for _ in range(seconds // 6):
        time.sleep(6)
        j = loop_named(name)
        if j:
            return j
        busy = [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]
        print(f"      waiting for {name}, busy={busy}")
    return None


def task_branch_tip(task_id):
    code, tip, _ = git("rev-parse", "--verify", f"refs/heads/agentweave/task/{task_id}")
    return tip if code == 0 else None


def wait_for_status(loop_row_id, wanted, seconds=420):
    """Wait for every task on the loop to reach *wanted* **and** for the turn to have ended.

    Those are not the same moment, and the difference is load-bearing on this route. `completed`
    is written by the agent's own `update_task` mid-turn; the agent's work is committed onto the
    task branch by the Hub's auto-snapshot at turn END. Between the two the branch tip is still
    the commit the branch was cut from -- so a reader that stopped at the status would measure a
    tip already an ancestor of the main branch and conclude nothing was built. Returns
    `(rows, tip_at_status, tip_after_turn)` so the drive can say what that window costs.
    """
    at_status = None
    for _ in range(seconds // 6):
        time.sleep(6)
        rows = tasks_of(loop_row_id)
        got = [(t["id"], t["status"]) for t in rows]
        busy = [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]
        print(f"      {got} busy={busy}")
        if rows and all(t["status"] in wanted for t in rows):
            if at_status is None:
                at_status = {t["id"]: task_branch_tip(t["id"]) for t in rows}
            if not busy:
                return rows, at_status, {t["id"]: task_branch_tip(t["id"]) for t in rows}
    rows = tasks_of(loop_row_id)
    return rows, at_status, {t["id"]: task_branch_tip(t["id"]) for t in rows}


def approve(task_id, label="operator lands the work"):
    """ONE request. This function used to be three, and the three are why the route exists.

    **What it cost before 2026-08-31** (F163, measured by this harness on its earlier runs, each
    refusal driven rather than assumed):

    1. `assignee -> null`. A loop's task is still assigned to the one agent that did it, and
       `completed -> under_review` answered **403** while it was: *"the move would claim its own
       author is reviewing it"*. A flow resolves a different reviewer and never meets this; a loop
       has no review leg, so the operator always did.
    2. `-> under_review`. `completed -> approved` answered **409** listing `rejected, under_review`
       as the only ways out of `completed`.
    3. `-> approved`, the transition that integrates.

    Three hand transitions, two of which existed only to satisfy the next one, and the product
    documented none of them. `POST /tasks/{id}/land` (group 6 of
    `approval-waits-for-the-turn-to-end`) composes exactly those three inside one transaction. The
    three still work and are still legal; this drive uses the one because the one is the claim.

    Asserted here rather than at the call sites, so every lane gets it: the single request answers
    200, and the task comes back `approved` with the author's hold released -- the two facts the
    three hops used to produce between them.
    """
    c, out = call(f"{label} (ONE request: POST /land)", "POST",
                  f"/projects/{P}/tasks/{task_id}/land", {}, expect=200, show=True, limit=700)
    if c == 200 and isinstance(out, dict):
        check(f"{label}: one action reached `approved`", out.get("status") == "approved",
              repr(out.get("status")))
        check(f"{label}: and released the author's hold in the same request",
              out.get("assignee") in (None, ""), repr(out.get("assignee")))
    return c, out


def main():
    base_head = preflight()
    created = []

    try:
        # ---------------------------------------------------------------- A
        head("A. The operator's route -- DRIVE-2 item 2, no agent turn")
        c, out = call(
            "POST /jobs with work_needs_evidence on a job that is not becoming a loop",
            "POST", f"/projects/{P}/jobs",
            {"name": f"d2-notaloop-{RUN}", "agent": AUTHOR, "message": "hello",
             "cron": "0 4 1 1 *", "work_needs_evidence": True},
            expect=400,
        )
        detail = out.get("detail") if isinstance(out, dict) else ""
        check("refused 400, and the sentence says how to make it a loop",
              c == 400 and "purpose or a stop" in str(detail), str(detail)[:120])
        check("nothing was left behind by the refusal",
              not any(j.get("name") == f"d2-notaloop-{RUN}" for j in jobs()))

        # ---------------------------------------------------------------- B
        head(f"B. LANE A -- {AUTHOR} creates a loop through `create_loop`, declaration OMITTED")
        name_a = f"d2-omitted-{RUN}"
        ask_for_a_loop(AUTHOR, name_a, FILE_A, None)
        job_a = wait_for_job(name_a)
        if job_a is None:
            note("the agent did not create the loop; falling back to the operator route so the "
                 "merge question is still answered, and recording that create_loop was not driven")
            c, job_a = call("operator creates the loop instead", "POST", f"/projects/{P}/jobs",
                            {"name": name_a, "agent": AUTHOR, "message": "Work the task you have "
                             "been given.", "cron": "0 4 1 1 *",
                             "purpose": "Grow the calculator by one function.",
                             "stop_when_queue_empties": True,
                             "initial_tasks": [{"title": f"Add power to {FILE_A}",
                                                "description": f"Create a file called {FILE_A} in "
                                                "your working directory containing exactly one "
                                                "function, power(a, b), returning a to the power "
                                                "of b. Change nothing else. Do not run git."}]},
                            expect=(200, 201), show=True)
            check("create_loop was driven", False, "the agent never called it")
        else:
            check("create_loop was driven -- the loop exists", True, job_a.get("id"))
        settle(rounds=8, label="(after loop creation)")
        job_a = loop_named(name_a) or job_a
        job_a_id = job_a.get("id")
        created.append(job_a_id)
        loop_a = (job_a.get("loop") or {}) if isinstance(job_a, dict) else {}
        c, summary = api("GET", f"/projects/{P}/jobs/{job_a_id}")
        loop_a = (summary.get("loop") or loop_a) if isinstance(summary, dict) else loop_a
        loop_a_id = loop_a.get("id")
        check("the job has a Loop row", bool(loop_a_id), repr(loop_a_id))
        wne = loop_a.get("work_needs_evidence", "MISSING")
        check("the omitted declaration is NULL on the row, not False",
              wne is None, repr(wne))

        c, out = call("PATCH the loop's declaration", "PATCH", f"/projects/{P}/jobs/{job_a_id}",
                      {"work_needs_evidence": True}, expect=400)
        detail = out.get("detail") if isinstance(out, dict) else ""
        check("PATCH refused, naming the create-a-new-loop remedy",
              c == 400 and "create a loop with the declaration" in str(detail), str(detail)[:140])
        c, summary = api("GET", f"/projects/{P}/jobs/{job_a_id}")
        check("the refused PATCH changed nothing",
              ((summary.get("loop") or {}).get("work_needs_evidence", 1)
               if isinstance(summary, dict) else 1) is None)

        # ---------------------------------------------------------------- C
        head("C. Fire it once by hand and let the task be worked")
        call("run job", "POST", f"/projects/{P}/jobs/{job_a_id}/run", {}, expect=200, show=True,
             limit=700)
        rows, tip_at_status, tip_after = wait_for_status(
            loop_a_id, ("completed", "under_review", "approved"))
        task_a = rows[0] if rows else {}
        t_a = task_a.get("id")
        check("the loop's task reached `completed` with nobody's hand on it",
              task_a.get("status") in ("completed", "under_review", "approved"),
              f"{t_a} {task_a.get('status')!r}")
        if not t_a:
            check("LANE A cannot continue -- no task", False)
            return
        early, late = (tip_at_status or {}).get(t_a), (tip_after or {}).get(t_a)
        note("branch tip the moment the task said `completed`", (early or "none")[:12])
        note("branch tip once the turn ended", (late or "none")[:12])
        note("THE WINDOW", "the tip was still the base commit while the task read `completed`"
             if early == base_head else "the two agreed")
        check("the Hub committed the agent's work onto the task's own branch",
              bool(late) and late != base_head, (late or "")[:12])
        check(f"{FILE_A} is NOT on {MAIN} yet", file_on_main(FILE_A) is None)

        # Group 5 of `approval-waits-for-the-turn-to-end` (F161/D21): a loop must not enter the
        # review arm at all. Before it, the loop's completed task was offered to the reviewer
        # selection, which a one-agent mode cannot staff -- so the work sat waiting for a reviewer
        # that could never be resolved. Checked here rather than in a lane of its own because this
        # is the exact population: one agent, one task, nobody else to ask.
        check("NO REVIEW STALL: the loop's task rests at `completed`, not `under_review`",
              task_a.get("status") == "completed", repr(task_a.get("status")))
        check("and the task is still held by its own author -- no reviewer was resolved onto it",
              task_a.get("assignee") == AUTHOR, repr(task_a.get("assignee")))
        check("and no second agent was pulled in to review it",
              statuses().get(OTHER) in ("idle", "offline"),
              f"{OTHER}={statuses().get(OTHER)!r}  all={statuses()}")

        # ---------------------------------------------------------------- D
        head("D. LANE A' -- dirty the operator's checkout, THEN approve (DRIVE-2 item 4)")
        with open(os.path.join(ROOT, "calc.py"), "a", encoding="utf-8") as fh:
            fh.write("\n# the operator was in the middle of something\n")
        code, dirty, _ = git("status", "--porcelain")
        check("the checkout is dirty on a TRACKED file", bool(dirty), dirty.replace("\n", " | "))
        c, out = approve(t_a)
        rows = integrations(t_a)
        print("      " + blob(rows, 1200).replace(chr(10), chr(10) + "      "))
        last = rows[-1] if rows else {}
        check("the integration was SKIPPED, not silently successful",
              last.get("outcome") == "skipped", repr(last.get("outcome")))
        check("the reason is the dirty checkout",
              "uncommitted changes" in str(last.get("reason")), str(last.get("reason"))[:120])
        check("and the row offers a retry",
              last.get("retryable") is True, repr(last.get("retryable")))
        check(f"{FILE_A} still did not reach {MAIN}", file_on_main(FILE_A) is None)

        head("E. Clean the checkout and press the button -- does it actually work?")
        git("checkout", "--", "calc.py")
        code, dirty, _ = git("status", "--porcelain")
        check("the checkout is clean again", not dirty, dirty)
        c, out = call("retry the integration", "POST",
                      f"/projects/{P}/tasks/{t_a}/integrations/retry", {}, expect=200, show=True,
                      limit=900)
        rows = integrations(t_a)
        last = rows[-1] if rows else {}
        check("the retry appended a fresh attempt rather than revising the skip",
              len(rows) >= 2, f"{len(rows)} rows")
        check("the retry MERGED", last.get("outcome") == "merged", repr(last.get("outcome")))
        body = file_on_main(FILE_A)
        check(f"THE POINT: {FILE_A} is on {MAIN} with the agent's function in it",
              body is not None and "def power" in body,
              "absent" if body is None else body.replace("\n", " / ")[:120])
        check("and its commit is an ancestor of the main branch",
              on_main(last.get("commit_sha")), str(last.get("commit_sha"))[:12])
        code, log, _ = git("log", "--oneline", "-6", MAIN)
        print(f"      --- {MAIN} now\n      " + log.replace(chr(10), chr(10) + "      "))

        # ---------------------------------------------------------------- F
        head(f"F. LANE B -- the same shape declaring `work_needs_evidence=True`")
        name_b = f"d2-declared-{RUN}"
        ask_for_a_loop(OTHER, name_b, FILE_B, "true")
        job_b = wait_for_job(name_b)
        if job_b is None:
            check("LANE B: create_loop with the declaration was driven", False,
                  "the agent never created it")
            return
        check("LANE B: create_loop carried the declaration through", True, job_b.get("id"))
        settle(rounds=8, label="(after loop creation)")
        job_b_id = job_b.get("id")
        created.append(job_b_id)
        c, summary = api("GET", f"/projects/{P}/jobs/{job_b_id}")
        loop_b = (summary.get("loop") or {}) if isinstance(summary, dict) else {}
        loop_b_id = loop_b.get("id")
        wne = loop_b.get("work_needs_evidence", "MISSING")
        check("the declaration reached the row as True", wne is True, repr(wne))

        call("run job", "POST", f"/projects/{P}/jobs/{job_b_id}/run", {}, expect=200)
        rows, _, tip_after_b = wait_for_status(
            loop_b_id, ("completed", "under_review", "approved"))
        task_b = rows[0] if rows else {}
        t_b = task_b.get("id")
        check("LANE B's task reached `completed`",
              task_b.get("status") in ("completed", "under_review", "approved"),
              f"{t_b} {task_b.get('status')!r}")
        if not t_b:
            return
        tip_b = (tip_after_b or {}).get(t_b)
        check("LANE B's work IS committed on its own branch -- the branch is not the question",
              bool(tip_b) and tip_b != base_head, (tip_b or "")[:12])
        before = file_on_main(FILE_B)
        c, out = approve(t_b)
        after = board()
        t = next((x for x in after if x["id"] == t_b), {})
        check("approval was NOT refused -- there is no evidence to be unaccepted",
              t.get("status") == "approved", repr(t.get("status")))
        rows = integrations(t_b)
        print("      " + blob(rows, 1200).replace(chr(10), chr(10) + "      "))
        last = rows[-1] if rows else {}
        check("nothing merged", last.get("outcome") != "merged", repr(last.get("outcome")))
        check("THE POINT: the reason is the EVIDENCE one, not the no-branch one",
              "nothing to merge" in str(last.get("reason")).lower()
              and "no branch of its own" not in str(last.get("reason")),
              str(last.get("reason"))[:140])
        check("an unretryable skip offers no button",
              last.get("retryable") is False, repr(last.get("retryable")))
        check(f"{FILE_B} did not reach {MAIN}", file_on_main(FILE_B) is None and before is None)

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
    main()
