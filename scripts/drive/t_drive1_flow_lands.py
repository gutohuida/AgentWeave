"""DRIVE-1 -- does a flow's approved work actually reach the main branch?

The point of the whole `the-flow-lands-its-work` run. Changes A
(`a-flow-briefing-names-its-contract`), B (`a-review-a-flow-cannot-staff-is-named`) and C
(`approval-refuses-unaccepted-evidence`) are all implemented and all three are UNDRIVEN. The flow
suite cannot prove C -- it configures no main branch -- so only this can.

Two lanes on one document, deliberately, because the interesting question is not whether the happy
path works but what the two halves of C do to a live flow:

  LANE CLEAN (`modulo`)  -- the operator accepts the evidence BEFORE the review firing. The
                            reviewer's `approved` should succeed and the commit should land on the
                            project's main branch at that moment.
  LANE STALL (`power`)   -- the evidence is left `awaiting`. The reviewer's `approved` should be
                            REFUSED by C's gate. Three things no unit test can answer are measured
                            there: does the refusal's sentence reach the agent as prose rather than
                            as a dict repr (F152 driven, not unit-tested); does the agent do
                            anything sensible with it or retry; and is the stall legible to an
                            operator on the board rather than only correct in the API.

Then the operator accepts the stalled lane's evidence and the drive asks whether the flow itself
recovers, or whether a person has to finish it by hand.

Pass condition, DRIVEN not asserted: both tasks reach `approved` AND both commits are reachable
from the project's main branch, with a following firing finding nothing to re-do.

Real surface only. No row inserts. Haiku turns. LEAVES NO JOB ENABLED.

Run:  AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... py -3.11 -u t_drive1_flow_lands.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

P = os.environ.get("AW_PROJECT") or ""
AGENT = os.environ.get("AW_AGENT") or "alpha"
RUN = os.environ.get("AW_RUN") or time.strftime("%H%M%S")
TARGET = f"drive1_{RUN}.py"
BASE = f"/projects/{P}/project"

VERDICTS = []
ROOT = None  # the project's working directory, filled by preflight


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    """Recorded but not scored -- an observation the drive exists to make, with no pass/fail."""
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


def mine():
    return [t for t in board() if TARGET in (t.get("title") or "")]


def by_key(word):
    """The one task whose title names *word* -- `power` or `modulo`."""
    return next((t for t in mine() if word in (t.get("title") or "")), {})


def settle(rounds=45, gap=6):
    for i in range(rounds):
        time.sleep(gap)
        busy = [n for n, s in statuses().items() if s not in ("idle", "offline", "error")]
        rows = [(t["title"].split()[1], t["status"], t.get("assignee")) for t in mine()]
        print(f"      t+{(i + 1) * gap:>3}s busy={busy} mine={rows}")
        if i >= 2 and not busy:
            return
    print("      (did not settle)")


def evidence_rows(task_id=None):
    c, ev = api("GET", f"/projects/{P}/project/spec/evidence")
    rows = ev.get("evidence", []) if isinstance(ev, dict) else []
    if task_id is None:
        return rows
    return [e for e in rows if e.get("task_id") == task_id]


def git(*args):
    r = subprocess.run(
        ["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def on_main(sha, main_branch):
    """Is *sha* an ancestor of the project's main branch, asked of the repository itself?

    The Hub's own `TaskIntegration` row is the Hub's account of what it did; this is the only
    check that answers the question the run's purpose is written in -- *did the work reach the
    main branch* -- without taking the Hub's word for it.
    """
    if not sha:
        return False
    code, _, _ = git("merge-base", "--is-ancestor", sha, main_branch)
    return code == 0


def agent_output_text(name, limit=1000):
    """Everything the turn emitted -- `content` AND `payload`.

    A tool RESULT is where a refusal actually lands, and it is carried in `payload`, not in the
    assistant's own text. Reading only `content` would answer "the agent never saw it" for a
    refusal sitting one field over, which is exactly the shape of mistake this drive exists to
    avoid making.
    """
    c, rows = api("GET", f"/projects/{P}/agents/{name}/output?limit={limit}")
    if not isinstance(rows, list):
        return ""
    out = []
    for r in rows:
        out.append(str(r.get("content") or ""))
        if r.get("payload"):
            out.append(json.dumps(r["payload"], default=str))
    return "\n".join(out)


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": f"{TARGET} grows a power and a modulo",
    "summary": "Two independent additions, so a flow has two things to work in parallel, two "
    "things to review, and two commits that have to reach the main branch.",
    "problem": f"{TARGET} does not exist and the project has no exponent or remainder.",
    "scope": {"in_scope": [TARGET], "non_goals": ["tests", "packaging"]},
    "requirements": [
        {
            "key": "power",
            "statement": f"{TARGET} SHALL offer a power(a, b) returning a raised to b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing exponentiation.",
        },
        {
            "key": "modulo",
            "statement": f"{TARGET} SHALL offer a modulo(a, b) returning the remainder of a / b.",
            "modal": "SHALL",
            "rationale": "The calculator is missing remainder.",
        },
    ],
    "acceptance_criteria": [
        {
            "key": "power-works",
            "requirement": "power",
            "given": f"{TARGET} after the change",
            "when": "power(2, 3) is called",
            "then": "it returns 8",
        },
        {
            "key": "modulo-works",
            "requirement": "modulo",
            "given": f"{TARGET} after the change",
            "when": "modulo(7, 3) is called",
            "then": "it returns 1",
        },
    ],
    "tasks": [
        {
            "key": "add-power",
            "title": f"Add power to {TARGET}",
            "description": f"Create or append to {TARGET} in your working directory a function "
            "power(a, b) returning a ** b. Change nothing else. Do not run git.",
            "requirements": ["power"],
        },
        {
            "key": "add-modulo",
            "title": f"Add modulo to {TARGET}",
            "description": f"Create or append to {TARGET} in your working directory a function "
            "modulo(a, b) returning a % b. Change nothing else. Do not run git.",
            "requirements": ["modulo"],
        },
    ],
    "design": "Two one-line functions, independent of each other.",
    "lifecycle": "One-off change.",
}


def preflight():
    global ROOT
    head("PRE. Preconditions -- asserted, never assumed")
    if not P:
        sys.exit("set AW_PROJECT")
    c, rows = api("GET", "/projects")
    row = next((x for x in (rows or []) if x.get("id") == P), None) if isinstance(rows, list) else None
    if row is None:
        sys.exit(f"project {P} not found")
    if P in ("proj-5e960453", "proj-18e5d4e0"):
        sys.exit("refusing to drive against a forbidden project")
    ROOT = row["working_directory"]
    c, settings = api("GET", f"/projects/{P}/settings")
    main_branch = settings.get("main_branch") if isinstance(settings, dict) else None
    if not main_branch:
        sys.exit("this project has no main branch chosen -- nothing can ever merge, so the "
                 "pass condition is unreachable and a green run would mean nothing")
    code, out, _ = git("status", "--porcelain")
    if code != 0:
        sys.exit(f"{ROOT} is not a git repository -- there is no main branch to land on")
    if out:
        sys.exit(f"{ROOT} has uncommitted changes before the drive:\n{out}")
    ros = agents()
    author = next((a for a in ros if a["name"] == AGENT), None)
    if author is None or author.get("archived") or not author.get("runner_id"):
        sys.exit(f"agent {AGENT!r} must exist, be open, and be bound to a runner")
    busy = [a["name"] for a in ros if a.get("status") not in ("idle", "offline", "error")]
    if busy:
        sys.exit(f"agents busy before the run: {busy}")
    pool = [a["name"] for a in ros
            if a["name"] != AGENT and not a.get("archived") and a.get("runner_id")]
    if not pool:
        sys.exit("no second bound agent -- no non-author reviewer can ever resolve")
    c, jobs = api("GET", f"/projects/{P}/jobs")
    live = [j for j in (jobs if isinstance(jobs, list) else []) if j.get("enabled")]
    if live:
        sys.exit(f"jobs already enabled: {[j.get('id') for j in live]}")
    if mine():
        sys.exit(f"tasks matching {TARGET} already exist -- pick a different AW_RUN")
    code, base_head, _ = git("rev-parse", main_branch)
    print(f"  [OK ] {ROOT}")
    print(f"  [OK ] main branch {main_branch!r} at {base_head[:12]}, tree clean")
    print(f"  [OK ] author {AGENT}, reviewer pool {pool}, no job enabled, run tag {RUN}")
    return main_branch, base_head, pool


def main():
    main_branch, base_head, pool = preflight()

    head("A. An approved document with two independent tasks")
    c, doc = call("create document", "POST", f"{BASE}/documents",
                  {"title": PAYLOAD["title"]}, expect=(200, 201))
    path = doc["path"]
    doc_id = doc.get("id")
    q = urllib.parse.quote(path, safe="")
    call("write content", "PUT", f"{BASE}/documents/{q}/content",
         {"document": PAYLOAD}, expect=(200, 201))
    call("close exploration", "POST", f"{BASE}/documents/close-exploration?path={q}",
         {"reason": "drive 1"}, expect=(200, 201))
    call("propose", "POST", f"{BASE}/documents/propose?path={q}", {"reason": "drive 1"},
         expect=(200, 201))

    head("B. The flow, created BEFORE approval so materialised tasks land in its queue")
    c, job = call("create flow", "POST", f"/projects/{P}/jobs", {
        "name": f"drive1-{RUN}",
        "agent": AGENT,
        "message": "Work the task you have been given. Keep the edit minimal.",
        "cron": "0 4 * * *",
        "purpose": f"Get both tasks in {TARGET} done, reviewed, and landed.",
        "spec_document_id": doc_id,
        "stop_when_queue_empties": True,
        "enabled": True,
    }, expect=(200, 201))
    if c >= 300:
        return
    job_id = job["id"]
    loop_id = (job.get("loop") or {}).get("id")
    check("the job opted into a loop", bool(loop_id), str(loop_id))
    if not loop_id:
        return

    try:
        head("C. Approve the document -- two tasks into this loop's queue")
        call("approve", "POST", f"{BASE}/documents/phase?path={q}&to=approved",
             {"reason": "drive 1"}, expect=(200, 201))
        time.sleep(2)
        rows = mine()
        check("approval materialised exactly two tasks", len(rows) == 2,
              str([(r["id"], r["title"]) for r in rows]))
        if len(rows) != 2:
            return
        check("...both into this loop's queue",
              all(r.get("loop_id") == loop_id for r in rows),
              str([r.get("loop_id") for r in rows]))
        t_power = by_key("power")["id"]
        t_mod = by_key("modulo")["id"]
        print(f"      power={t_power}  modulo={t_mod}")

        head("D. Firing 1 -- both tasks worked, and does each REACH `completed` on its own?")
        # Change A's whole claim. Before it, the briefing never named `update_task`, both tasks sat
        # in `in_progress` forever, and every later firing re-briefed the same agents for finished
        # work. `completed` reached without an operator touching anything is that fix driven.
        call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, expect=(200, 201))
        settle()
        rows = mine()
        print(f"      {[(t['title'].split()[1], t['status'], t.get('assignee')) for t in rows]}")
        authors = {t["id"]: t.get("assignee") for t in rows}
        check("both tasks were staffed", all(authors.values()), str(authors))
        check("A driven: both tasks reached `completed` with no operator transition",
              all(t["status"] == "completed" for t in rows),
              str([(t["title"].split()[1], t["status"]) for t in rows]))

        head("D2. Did each task record evidence naming a commit?")
        # The briefing asks for it (`_briefing_evidence_lines`). Whether an agent actually does it
        # is the thing change D exists to settle and this drive can only measure.
        ev_state = {}
        for word, tid in (("power", t_power), ("modulo", t_mod)):
            rows_ev = evidence_rows(tid)
            shas = [(e["id"], e.get("status"), (e.get("footprint") or {}).get("commit_sha"))
                    for e in rows_ev]
            ev_state[word] = rows_ev
            print(f"      {word}: {shas}")
            check(f"{word} recorded evidence naming a commit",
                  any((e.get("footprint") or {}).get("commit_sha") for e in rows_ev),
                  str(shas))
        if not (ev_state["power"] and ev_state["modulo"]):
            note("without evidence on both tasks the two lanes below cannot be told apart")

        head("E. LANE CLEAN -- the operator accepts `modulo`'s evidence before the review")
        for e in ev_state["modulo"]:
            call(f"accept {e['id']}", "POST",
                 f"/projects/{P}/project/spec/evidence/{e['id']}/decision",
                 {"decision": "accepted", "reason": "drive 1, clean lane"}, expect=(200, 201))
        note("LANE STALL: `power`'s evidence is deliberately left awaiting",
             str([(e["id"], e.get("status")) for e in ev_state["power"]]))

        head("F. Firing 2 -- is the finished work offered to NON-author reviewers?")
        c, b = call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {},
                    expect=(200, 201), show=True, limit=1600)
        settle()
        rows = mine()
        print(f"      {[(t['title'].split()[1], t['status'], t.get('assignee')) for t in rows]}")
        reviewers = {t["id"]: t.get("assignee") for t in rows}
        for word, tid in (("power", t_power), ("modulo", t_mod)):
            check(f"{word}'s reviewer is not its author",
                  reviewers.get(tid) and reviewers[tid] != authors.get(tid),
                  f"{authors.get(tid)} -> {reviewers.get(tid)}")

        head("G. LANE CLEAN -- did `modulo` reach `approved`, and did its commit LAND?")
        t = by_key("modulo")
        check("modulo reached `approved` with nobody's hand on it",
              t.get("status") == "approved", repr(t.get("status")))
        c, drawer = api("GET", f"/projects/{P}/tasks/{t_mod}/integrations")
        print("      " + blob(drawer, 1400).replace(chr(10), chr(10) + "      "))
        mod_sha = (ev_state["modulo"][0].get("footprint") or {}).get("commit_sha") \
            if ev_state["modulo"] else None
        git("fetch", "--all", "--quiet")
        check("THE POINT: modulo's commit is reachable from the main branch",
              on_main(mod_sha, main_branch), f"{(mod_sha or '')[:12]} in {main_branch}")

        head("H. LANE STALL -- was `power`'s approval refused, and what did the agent see?")
        t = by_key("power")
        check("power did NOT reach `approved` while its evidence sits unaccepted",
              t.get("status") != "approved", repr(t.get("status")))
        text = agent_output_text(reviewers.get(t_power) or "")
        marker = "This task's work has been recorded and nobody has judged it"
        seen = marker in text
        check("F152 driven: the refusal's SENTENCE reached the agent's turn",
              seen, "found" if seen else f"not in {len(text)} chars of output")
        if seen:
            i = text.index(marker)
            excerpt = text[max(0, i - 200): i + 500]
            print("      --- what the agent actually read")
            print("      " + excerpt.replace(chr(10), chr(10) + "      "))
            check("...as prose, not as a dict repr",
                  "'code':" not in excerpt and "'blocking':" not in excerpt
                  and "gate_unsatisfied'," not in excerpt,
                  excerpt[:160].replace(chr(10), " | "))
        else:
            print("      --- last 2000 chars of the reviewer's output, for the record")
            print("      " + text[-2000:].replace(chr(10), chr(10) + "      "))

        head("H2. Is the stall LEGIBLE to an operator, or only correct in the API?")
        c, drawer = api("GET", f"/projects/{P}/tasks/{t_power}/integration-preview")
        print("      integration drawer: " + blob(drawer, 900).replace(chr(10), chr(10) + "      "))
        c, loop = api("GET", f"/projects/{P}/loops/{loop_id}")
        print("      loop: " + blob(loop, 1600).replace(chr(10), chr(10) + "      "))
        c, hist = api("GET", f"/projects/{P}/jobs/{job_id}/history")
        print("      history: " + blob(hist, 1600).replace(chr(10), chr(10) + "      "))

        head("I. The operator accepts `power`'s evidence -- does the work land now?")
        for e in ev_state["power"]:
            call(f"accept {e['id']}", "POST",
                 f"/projects/{P}/project/spec/evidence/{e['id']}/decision",
                 {"decision": "accepted", "reason": "drive 1, stall lane"}, expect=(200, 201))
        pow_sha = (ev_state["power"][0].get("footprint") or {}).get("commit_sha") \
            if ev_state["power"] else None
        landed_on_acceptance = on_main(pow_sha, main_branch)
        note("did acceptance alone land it?", str(landed_on_acceptance))
        note("(it should not: acceptance integrates tasks already at `approved`, and this one "
             "was refused before it got there -- so somebody still has to approve it)")

        head("I2. Does the FLOW finish it, or does a person have to?")
        before = by_key("power").get("status")
        c, b = call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, show=True,
                    limit=1400)
        settle()
        after = by_key("power")
        note(f"power {before} -> {after.get('status')}", repr(after.get("assignee")))
        if after.get("status") != "approved":
            note("the flow did not finish it; the operator approves by hand, which is the "
                 "route the refusal's own sentence points at")
            call("operator approves power", "PATCH", f"/projects/{P}/tasks/{t_power}",
                 {"status": "approved"}, expect=200, show=True, limit=900)
            after = by_key("power")

        head("J. THE PASS CONDITION -- two tasks approved, two commits on the main branch")
        git("fetch", "--all", "--quiet")
        rows = mine()
        check("both tasks are `approved`",
              all(t["status"] == "approved" for t in rows),
              str([(t["title"].split()[1], t["status"]) for t in rows]))
        for word, sha in (("power", pow_sha), ("modulo", mod_sha)):
            check(f"THE POINT: {word}'s commit is on {main_branch}", on_main(sha, main_branch),
                  (sha or "no sha")[:12])
        code, log, _ = git("log", "--oneline", "-12", main_branch)
        print(f"      --- {main_branch} now")
        print("      " + log.replace(chr(10), chr(10) + "      "))
        code, files, _ = git("ls-tree", "--name-only", main_branch)
        print(f"      files on {main_branch}: {files.split()}")
        code, body, _ = git("show", f"{main_branch}:{TARGET}")
        if code == 0:
            print(f"      --- {TARGET} on {main_branch}")
            print("      " + body.replace(chr(10), chr(10) + "      "))
        check(f"both functions are in {TARGET} on {main_branch}",
              code == 0 and "def power" in body and "def modulo" in body,
              f"exit {code}")

        head("K. A following firing finds nothing to re-do")
        c, b = call("run job", "POST", f"/projects/{P}/jobs/{job_id}/run", {}, show=True,
                    limit=1400)
        settle(rounds=6)
        rows = mine()
        check("nothing moved out of `approved`",
              all(t["status"] == "approved" for t in rows),
              str([(t["title"].split()[1], t["status"]) for t in rows]))
        check("no agent was left mid-turn by that firing",
              not [n for n, s in statuses().items() if s not in ("idle", "offline", "error")],
              str(statuses()))
    finally:
        head("Z. LEAVE NO JOB ENABLED")
        call("disable", "PATCH", f"/projects/{P}/jobs/{job_id}", {"enabled": False})
        call("archive", "POST", f"/projects/{P}/jobs/{job_id}/archive", {})
        call("jobs now", "GET", f"/projects/{P}/jobs", expect=200, show=True, limit=400)
        print(f"      agents: {statuses()}")
        head("VERDICTS")
        bad = [v for v in VERDICTS if not v[1]]
        for label, ok, detail in VERDICTS:
            print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
        print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
