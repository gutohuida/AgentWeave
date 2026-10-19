"""Sweep 2026-10-19: Tasks x Flows & review x Worktrees & integration, real Haiku turns.

A two-task flow (builder works, rev reviews) on a small library, with a project check configured,
so a task's story carries runs, transitions, a review, a send-back and check runs. Phases are
functions, run one at a time:

  py -3.11 scripts/drive/s1019_tasks.py setup | fire [n] | status | story <task> | ...
"""

import json
import sys
import time

from s1019_tasks_lib import B, D, S, api, q, ro, runs, save, say, settle, spec_tasks, task, texts, transitions

PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "calc clamps correctly and gains sub",
    "summary": "Fix clamp() to honour its upper bound, and add sub().",
    "problem": "clamp ignores hi; there is no subtraction helper.",
    "scope": {"in_scope": ["calc/ops.py", "calc/registry.py", "tests/"], "non_goals": ["Other helpers"]},
    "requirements": [
        {"key": "clamp", "modal": "MUST", "statement": "calc.ops.clamp(x, lo, hi) MUST return lo when x < lo, hi when x > hi, else x.",
         "rationale": "It ignores hi today."},
        {"key": "sub", "modal": "MUST", "statement": "calc.ops MUST provide sub(a, b) returning a - b, listed in calc.registry.PUBLIC.",
         "rationale": "Symmetry with add."},
    ],
    "acceptance_criteria": [
        {"key": "a-clamp", "requirement": "clamp", "given": "x=15, lo=0, hi=10", "when": "clamp is called",
         "then": "it returns 10", "checked_by": "agent"},
        {"key": "a-sub", "requirement": "sub", "given": "a=7, b=3", "when": "sub is called", "then": "it returns 4",
         "checked_by": "agent"},
    ],
    "tasks": [
        {"key": "t-clamp", "title": "Fix clamp upper bound",
         "description": "Fix clamp in calc/ops.py so it honours hi. Add tests/test_clamp.py covering below, inside and above the range. Commit your work.",
         "requirements": ["clamp"], "files": ["calc/ops.py", "tests/test_clamp.py"]},
        {"key": "t-sub", "title": "Add sub()",
         "description": "Add sub(a, b) at the END of calc/ops.py, append \"sub\" as the LAST entry of calc/registry.py PUBLIC, add tests/test_sub.py. Commit your work.",
         "requirements": ["sub"], "files": ["calc/ops.py", "calc/registry.py", "tests/test_sub.py"]},
    ],
    "algorithms": [],
    "design": "Two small independent edits to one module.",
    "evidence": {"checked": ["calc/ops.py clamp ignores hi"], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
    "delivery": {"mode": "flow", "agent": "builder", "reviewer": "rev", "tester": False,
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"},
}


def setup():
    st, cur = api("GET", f"{B}/settings")
    cur["checks"] = [{"name": "tests", "command": "py -3.11 -m pytest -q tests", "timeout_seconds": 300}]
    say("settings", api("PUT", f"{B}/settings", cur))
    code, doc = api("POST", f"{D}/documents", {"title": PAYLOAD["title"], "kind": "change-spec"})
    say("create", (code, doc))
    S["doc"] = doc["path"]
    save()
    path = q(doc["path"])
    say("write", api("PUT", f"{D}/documents/{path}/content", {"document": PAYLOAD}))
    say("close", api("POST", f"{D}/documents/close-exploration?path={path}"))
    say("propose", api("POST", f"{D}/documents/propose?path={path}"))
    code, res = api("POST", f"{D}/documents/phase?path={path}&to=approved", {"reason": "tasks sweep"})
    say("approve", (code, res))
    if code >= 300:
        say("approve anyway", api("POST", f"{D}/documents/phase?path={path}&to=approved",
                                  {"reason": "tasks sweep", "approve_anyway": True}))
    time.sleep(3)
    jobs = api("GET", f"{B}/jobs")[1]
    say("jobs", jobs)
    for j in jobs:
        S["job"] = j["id"]
        S["loop"] = (j.get("loop") or {}).get("id")
    S["tasks"] = {t["title"]: t["id"] for t in spec_tasks()}
    save()
    status()


def status():
    say("runs", runs())
    for t in spec_tasks():
        print("  task", t["id"], t["title"][:30], t["status"], t.get("assignee"), t.get("dependency_state"))
    for j in api("GET", f"{B}/jobs")[1]:
        print("  job", j["id"], j["name"][:40], j.get("enabled"), j.get("run_count"))
    for a in ("builder", "rev"):
        qs = [(e["id"], e["state"], e.get("review_task_id"), e.get("task_id"), e.get("waiting_reason"),
               e.get("abandoned_reason")) for e in api("GET", f"{B}/queue/{a}")[1] if e["state"] in ("queued", "withdrawn")]
        if qs:
            print("  queue", a, qs)


def fire(n="1"):
    for i in range(int(n)):
        before = {r["id"] for r in ro("select id from runs")}
        code, res = api("POST", f"{B}/jobs/{S['job']}/run")
        say(f"fire {i}", (code, res))
        time.sleep(8)
        settle()
        new = [r for r in runs(10) if r["id"] not in before]
        for r in new:
            tx = texts(r["id"])
            say(f"run {r['id']} {r['agent']} {r['status']} task={r['task_id']}", tx[-1][:600] if tx else "")
        status()


def wait():
    settle()
    status()


def story(tid):
    st, out = api("GET", f"{B}/tasks/{tid}/story")
    print(st, out["task"], out["summary"])
    for e in out["events"]:
        e = dict(e)
        ev, rv, at = e.pop("evidence", None), e.pop("reviews", None), (e.get("at") or "")[11:23]
        if e["kind"] == "transition":
            print(" ", at, "T", e["from"], "->", e["to"], e["actor_kind"], e["actor"], e["origin"], e["run_id"])
        elif e["kind"] == "run":
            print(" ", at, "RUN", e["id"], e["agent"], e["status"], e["conversation_id"], e["duration_seconds"])
        elif e["kind"] == "evidence":
            print(" ", at, "EV", e["id"], ev["requirement"]["identifier"], ev["review_state"],
                  ev.get("commit") or ev.get("commit_sha"), [(r["decision"], r["actor"], r["at"][11:19]) for r in rv])
        else:
            print(" ", at, e["kind"].upper(), json.dumps(e, ensure_ascii=False)[:400])


def hist(tid):
    st, out = api("GET", f"{B}/tasks/{tid}/transitions")
    print(st, json.dumps(out, indent=1, ensure_ascii=False)[:6000])
    for r in transitions(tid):
        print("  db", r)


def trigger(agent, message, **extra):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": "workspace"}}
    body.update(extra)
    return api("POST", f"{B}/agent/trigger", body)


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        r = ro("select status from runs where id=?", (run_id,))
        if r and r[0]["status"] not in ("running", "queued", "starting", "pending"):
            return r[0]["status"]
        time.sleep(4)
    return "still-running"


def div():
    """A second documentless task, left completed, for a pre-existing check failure on screen."""
    code, t = api("POST", f"{B}/tasks", {"title": "Add div()", "assignee": "builder",
                                         "description": "Add div(a, b) returning a / b at the END of calc/ops.py, "
                                         "and tests/test_div.py asserting div(8, 2) == 4. Commit your work, then "
                                         "set this task to completed."})
    S["div"] = t["id"]
    save()
    code, r = trigger("builder", "Work your task: add div() as described, commit, and complete the task.",
                      task_id=t["id"])
    say("trigger", (code, r))
    say("run", wait_run(r["run_id"]))
    time.sleep(15)
    say("task", {k: task(t["id"]).get(k) for k in ("status", "assignee")})
    say("checks", api("GET", f"{B}/tasks/{t['id']}/checks")[1])


def mul():
    """A documentless task worked by a real turn: checks run at the run's end (branch tip)."""
    code, t = api("POST", f"{B}/tasks", {"title": "Add mul()", "assignee": "builder",
                                         "description": "Add mul(a, b) returning a * b at the END of calc/ops.py, "
                                         "and tests/test_mul.py asserting mul(3, 4) == 12. Commit your work, then "
                                         "set this task to completed."})
    say("create", (code, {k: t.get(k) for k in ("id", "status", "assignee")} if code < 300 else t))
    S["mul"] = t["id"]
    save()
    code, r = trigger("builder", "Work your task: add mul() as described, commit, and complete the task.",
                      task_id=t["id"])
    say("trigger", (code, r))
    st = wait_run(r["run_id"])
    tx = texts(r["run_id"])
    say(f"run {st}", tx[-1][:500] if tx else "")
    time.sleep(15)
    say("task", {k: task(t["id"]).get(k) for k in ("status", "assignee")})
    say("checks", api("GET", f"{B}/tasks/{t['id']}/checks")[1])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
