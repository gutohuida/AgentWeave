"""Acceptance drive for `a-tester-drives-the-built-product-and-keeps-the-spec-true` (tester-amends
slice), 2026-10-09.

The slice's `drive` criterion (spdoc-622cf1b3b011 on :8010). Starts its own Hub on :8102 with a fresh
database (never :8000 or :8010), opens a project whose calc.py adds wrongly when the first number is
negative (a planted bug), with two Haiku agents: alice builds, tess tests. The approved flow document
says `python calc.py -2 3` prints 1; its one task asks only for a README usage line. Checks, in order:

  1. the agent amend route exists (401 without a run credential, not 404/405) -- spends no turn;
  2. approval creates the flow, with delivery.tester tess;
  3. alice's firing completes the README task;
  4. the next firing queues its review to tess (the named tester goes first);
  5. tess's test turn records an add_task amendment, author tess, with its run, not reviewed;
  6. the added task is pending on the flow's board;
  7. a later firing gives it to alice and some branch's calc.py prints 1 for -2 3;
  8. a change_criterion amendment from a run testing a task of the document is applied, and with
     accepted evidence at the new digest the requirement reads `amendment_unreviewed`;
  9. the operator marks the amendments reviewed and the requirement reads `verified`.

Check 8 uses a run the drive starts for the purpose (a Run row plus its delivered review entry in
the scratch database, as the Hub tests do), not a Haiku turn choosing to relax a criterion.

The contract it fixes for the build: agent routes `POST /agent-actions/spec/documents/amend`
`{path, op, requirement?, criterion?, task?, change?, reason, how_to_check}` and
`POST /agent-actions/spec/documents/cannot-satisfy`; operator routes
`GET /projects/{id}/project/documents/amendments?path=` -> `{"amendments": [{id, op, target, reason,
how_to_check, author, run_id, reviewed, created_at}]}` and
`POST /projects/{id}/project/documents/amendments/review?path=` `{ids?}`; `delivery.tester`;
coverage state `amendment_unreviewed`.

Fails on today's Hub at check 1. Stops at the first failure. Spends Haiku turns from check 3 on.

    py -3.11 scripts/drive/d1013_tester_amends.py
"""

import pathlib
import secrets
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8102
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1013-tester-amends" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

DOC = "spec/changes/calc-usage/spec.json"
BUGGY = '''import sys


def add(a, b):
    if a < 0:
        return b - a
    return a + b


if __name__ == "__main__":
    print(add(int(sys.argv[1]), int(sys.argv[2])))
'''
AGENTS = ("alice", "tess")


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Calc usage",
        "summary": "Document how to run calc.py.",
        "problem": "README.md does not say how to run calc.py.",
        "scope": {"in_scope": ["README usage line"], "non_goals": ["New operations"]},
        "requirements": [{"key": "adds", "modal": "MUST", "rationale": None, "party": None,
                          "statement": "python calc.py A B MUST print the sum of the integers A and B."}],
        "acceptance_criteria": [{
            "key": "negative", "requirement": "adds", "given": "the project checked out",
            "when": "python calc.py -2 3 is run", "then": "it prints 1",
            "how_to_check": "python calc.py -2 3", "checked_by": "agent"}],
        "tasks": [{"key": "usage", "title": "README usage line",
                   "description": "Add one line to README.md: Usage: python calc.py A B. Change nothing else.",
                   "requirements": ["adds"], "depends_on": [], "files": ["README.md"],
                   "from": None, "reviewer": None}],
        "algorithms": [], "design": "One line.", "evidence": {"checked": ["calc.py exists"], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "flow", "agent": "alice", "tester": "tess", "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "0 3 1 1 *"},
    }


def wait_idle(pid, secs=600):
    """Until no run of the project is running and no entry is queued or in delivery."""
    end = time.time() + secs
    time.sleep(3)
    while time.time() < end:
        running = d.ro("select count(*) from runs where project_id=? and status='running'", (pid,))[0][0]
        if not running:
            return True
        time.sleep(5)
    return False


def fire(base, job_id, pid):
    code, out = d.api("POST", f"{base}/jobs/{job_id}/run")
    print("  run", code, str(out)[:200], flush=True)
    wait_idle(pid)


def status(task_id):
    rows = d.ro("select status, assignee from tasks where id=?", (task_id,))
    return rows[0] if rows else (None, None)


def amendments(base):
    code, out = d.api("GET", f"{base}/project/documents/amendments?path={urllib.parse.quote(DOC)}")
    return out.get("amendments", []) if code == 200 and isinstance(out, dict) else []


def coverage_state(base, identifier):
    code, out = d.api("GET", f"{base}/project/spec/coverage?document={urllib.parse.quote(DOC)}")
    rows = out.get("requirements", []) if isinstance(out, dict) else []
    row = next((r for r in rows if r.get("identifier") == identifier), {})
    return row.get("state"), out if not row else row


def tester_run(pid, task_id):
    """A running tess run whose delivered entry is a review of `task_id` (the Hub tests' pattern)."""
    sys.path.insert(0, str(d.REPO / "hub"))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.agent_auth import hash_run_token
    from hub.db.models import InboundQueueEntry, Run

    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-d1013-" + secrets.token_hex(4)
    engine = create_engine(f"sqlite:///{d.DB.as_posix()}")
    with Session(engine) as session:
        session.add(Run(id=run_id, project_id=pid, agent="tess", status="running", turn_depth=0,
                        capability_token_hash=hash_run_token(token)))
        session.add(InboundQueueEntry(
            id="entry-" + run_id, project_id=pid, agent="tess", origin_type="operator",
            content="test the task", hop_depth=0, state="delivered", review_task_id=task_id,
            delivered_in_run_id=run_id))
        session.commit()
    engine.dispose()
    return run_id, token


def agent_api(token, method, path, body=None):
    saved = d.KEY
    d.KEY = token
    try:
        return d.api(method, path, body)
    finally:
        d.KEY = saved


def drive():
    # 1: the route exists. Without a credential an existing agent route answers 401.
    code, out = agent_api("", "POST", "/agent-actions/spec/documents/amend", {"path": DOC})
    d.check("1 the agent amend route exists", code == 401, f"{code} {str(out)[:200]}")

    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# calc\n\nA tiny adder.\n", encoding="utf-8")
    (root / "calc.py").write_text(BUGGY, encoding="utf-8")
    d.git(root, "add", "README.md", "calc.py")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "calc"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    for name in AGENTS:
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        assert code in (200, 201), (name, code, out)

    quoted = urllib.parse.quote(DOC)
    code, out = d.api("POST", f"{base}/project/documents", {"title": "Calc usage", "kind": "change-spec",
                                                           "path": DOC})
    assert code == 201, (code, out)
    code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    assert code == 200, (code, out)
    identifier = out["identifiers"]["adds"]
    d.api("POST", f"{base}/project/documents/journey?path={quoted}",
          {"size": "small", "step": "delivery", "reason": "drive setup"})
    d.api("POST", f"{base}/project/documents/close-exploration?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/propose?path={quoted}")
    assert code == 200 and out.get("proposed"), (code, out)
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True})
    flow = ((out if isinstance(out, dict) else {}).get("approval_outcome") or {}).get("flow") or {}
    job_id = flow.get("job_id")
    d.check("2 approval creates the flow", code == 200 and bool(job_id), f"{code} flow={flow}")
    (usage,) = out["tasks_created"][:1]
    try:
        # 3: alice builds.
        for _ in range(3):
            fire(base, job_id, pid)
            if status(usage)[0] in ("completed", "under_review", "approved"):
                break
        d.check("3 alice completes the README task", status(usage)[0] in ("completed", "under_review"),
                str(status(usage)))
        # 4: the review goes to the named tester.
        if status(usage)[0] == "completed":
            d.api("POST", f"{base}/jobs/{job_id}/run")
            time.sleep(3)
        entries = d.ro("select agent from inbound_queue_entries where review_task_id=? order by sequence",
                       (usage,))
        d.check("4 the review is queued to the tester tess", [a for (a,) in entries][:1] == ["tess"],
                str(entries))
        wait_idle(pid)
        # 5: the tester found the bug by driving and added a task.
        listed = amendments(base)
        added = [a for a in listed if a.get("op") == "add_task"]
        first = added[0] if added else {}
        d.check("5 tess's test turn records an add_task amendment, by tess, with its run, not reviewed",
                bool(first) and first.get("author") == "tess" and first.get("run_id")
                and first.get("reviewed") is False, f"amendments={listed}")
        # 6: the task is on the flow's board.
        loop_id = d.ro("select loop_id from tasks where id=?", (usage,))[0][0]
        fresh = d.ro("select id, status from tasks where loop_id=? and id<>? order by created_at",
                     (loop_id, usage))
        d.check("6 the added task is pending on the flow's board", bool(fresh)
                and fresh[0][1] in ("pending", "assigned", "in_progress"), str(fresh))
        fix = fresh[0][0]
        # 7: the implementer fixes it.
        for _ in range(4):
            if status(fix)[0] in ("completed", "under_review", "approved"):
                break
            fire(base, job_id, pid)
        fixed = []
        branches = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"],
                                  cwd=root, capture_output=True, text=True).stdout.split()
        for branch in branches:
            source = subprocess.run(["git", "show", f"{branch}:calc.py"], cwd=root,
                                    capture_output=True, text=True).stdout
            if not source:
                continue
            scratch = d.TMP / f"calc_{branch.replace('/', '_')}.py"
            scratch.write_text(source, encoding="utf-8")
            ran = subprocess.run([sys.executable, str(scratch), "-2", "3"], capture_output=True, text=True)
            if ran.stdout.strip() == "1":
                fixed.append(branch)
        d.check("7 alice takes the added task and a branch's calc.py prints 1 for -2 3",
                status(fix)[0] in ("completed", "under_review", "approved") and bool(fixed),
                f"{status(fix)} fixed on {fixed} of {branches}")
        # 8: a relaxing amendment cannot count as passing until reviewed.
        _, token = tester_run(pid, fix)
        code, out = agent_api(token, "POST", "/agent-actions/spec/documents/amend", {
            "path": DOC, "op": "change_criterion", "criterion": "negative",
            "change": {"then": "it prints a number"},
            "reason": "drive: a relaxed criterion", "how_to_check": "python calc.py -2 3"})
        assert code in (200, 201), (code, out)
        code, ev = d.api("POST", f"{base}/project/spec/evidence", {
            "identifier": identifier, "summary": "python calc.py -2 3 prints 1 on the fix branch",
            "kind": "test_result", "locator": "calc.py", "document": DOC})
        assert code == 201, (code, ev)
        code, out = d.api("POST", f"{base}/project/spec/evidence/{ev['id']}/decision",
                          {"decision": "accepted", "reason": "drive"})
        assert code == 200, (code, out)
        state, detail = coverage_state(base, identifier)
        d.check("8 accepted evidence with a not-reviewed relaxing amendment reads amendment_unreviewed",
                state == "amendment_unreviewed", f"{state} {str(detail)[:300]}")
        # 9: reviewed, the evidence counts.
        code, out = d.api("POST", f"{base}/project/documents/amendments/review?path={quoted}", {})
        state, detail = coverage_state(base, identifier)
        d.check("9 once the operator marks them reviewed the requirement is verified",
                code == 200 and state == "verified" and all(a.get("reviewed") for a in amendments(base)),
                f"{code} {state} {str(detail)[:300]}")
    finally:
        d.api("PATCH", f"{base}/jobs/{job_id}", {"enabled": False})
        d.api("POST", f"{base}/jobs/{job_id}/archive")


d.drive = drive

if __name__ == "__main__":
    d.main()
