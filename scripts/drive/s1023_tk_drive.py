"""2026-10-23 day sweep, Tasks row, scratch Hub (hub-up tk1023 8162). Phases:

  setup    project aw-tk1023 (calc package + test + tools/agent_probe.py), haiku runner, alpha + beta,
           tasks: K (prereq of L and M), W (story subject), X (alpha's, in progress), Bown (beta's probe task)
  workk    alpha's turn on K: code, commit, complete (unmerged work for the delete)
  workw    alpha's turn on W: code, commit, complete
  revise   operator under_review -> revision_needed with notes
  workw2   alpha's second turn on W after the revision
  approve  operator under_review -> approved (merge)
  probe    beta's turn: runs tools/agent_probe.py (agent-plane PATCH probes with its own run credential),
           then task_history W and list_tasks via its tools
  bulk     create 105 tasks through the operator route; GET /tasks total / has_more
  story    GET /tasks/W/story vs /transitions vs DB task_transitions and runs
  illegal  operator illegal moves; route returns
  delete   DELETE K (prereq of L, M, with unmerged work): events task_deleted / task_checkout_kept, branch
  state    every task as the list returns it

  py -3.11 scripts/drive/s1023_tk_drive.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-s1023-tk.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1023_tk_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
HAIKU = "claude-haiku-4-5-20251001"

PROBE = r'''"""Agent-plane probes, run by an agent inside its own turn (uses AW_RUN_TOKEN / HUB_URL)."""
import json
import os
import pathlib
import urllib.error
import urllib.request

HUB = os.environ["HUB_URL"].rstrip("/") + "/api/v1/agent-actions"
TOKEN = os.environ["AW_RUN_TOKEN"]
OUT = []


def call(method, path, body=None):
    req = urllib.request.Request(HUB + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def note(label, st, res):
    OUT.append({"label": label, "status": st, "body": res})
    print(label, st, json.dumps(res)[:400])


ids = {}
off = 0
while True:
    st, page = call("GET", f"/tasks?limit=20&offset={off}")
    for t in page.get("tasks", []):
        ids[t["title"].split(":")[0]] = t["id"]
    if not page.get("has_more"):
        break
    off += 20


def brief(key):
    st, t = call("GET", f"/tasks/{ids[key]}")
    return {k: t.get(k) for k in ("title", "status", "assignee", "priority", "description", "notes")}


own, other, done = ids["Bown"], ids["X"], ids["W"]
note("before own", 200, brief("Bown"))
note("rename own", *call("PATCH", f"/tasks/{own}", {"title": "Bown: renamed by beta"}))
note("priority own", *call("PATCH", f"/tasks/{own}", {"priority": "critical"}))
note("description own", *call("PATCH", f"/tasks/{own}", {"description": "beta rewrote this"}))
note("assignee own", *call("PATCH", f"/tasks/{own}", {"assignee": "alpha"}))
note("unassign own", *call("PATCH", f"/tasks/{own}", {"assignee": None}))
note("status+title own", *call("PATCH", f"/tasks/{own}", {"status": "completed", "title": "Bown: x"}))
note("after refusals own", 200, brief("Bown"))
note("finish alpha's X", *call("PATCH", f"/tasks/{other}", {"status": "completed"}))
note("notes on alpha's X", *call("PATCH", f"/tasks/{other}", {"notes": "beta was here"}))
note("after X", 200, brief("X"))
note("illegal own -> approved from in_progress", *call("PATCH", f"/tasks/{own}", {"status": "approved"}))
note("own -> completed", *call("PATCH", f"/tasks/{own}", {"status": "completed"}))
note("own -> under_review", *call("PATCH", f"/tasks/{own}", {"status": "under_review"}))
note("own -> approved (self-approve)", *call("PATCH", f"/tasks/{own}", {"status": "approved"}))
note("after self-approve own", 200, brief("Bown"))
note("approved W -> pending", *call("PATCH", f"/tasks/{done}", {"status": "pending"}))
note("blocked own", *call("PATCH", f"/tasks/{own}", {"status": "blocked"}))
note("unknown status", *call("PATCH", f"/tasks/{own}", {"status": "finished"}))
note("history W", *call("GET", f"/tasks/{done}/transitions"))
st, big = call("GET", "/tasks?limit=1000")
note("list 1000", st, {k: v for k, v in big.items() if k != "tasks"} if isinstance(big, dict) else big)
note("list 1000 has tasks", st, len(big.get("tasks", [])) if isinstance(big, dict) else None)
note("unknown task", *call("PATCH", "/tasks/task-nope", {"status": "completed"}))
pathlib.Path(os.path.expanduser("~/.agentweave/s1023_tk_probe.json")).write_text(json.dumps(OUT, indent=1))
print("PROBE DONE", len(OUT))
'''


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None):
    if path.startswith("~"):
        path = f"/projects/{S['P']}" + path[1:]
    return e2e.request(method, path, body)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:3000]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def git(*args):
    r = subprocess.run(["git", "-C", S["DIR"], *args], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout + r.stderr).strip()


def brief(t):
    keys = ("id", "title", "status", "assignee", "priority", "dependency_state", "notes", "latest_integration")
    out = {k: t.get(k) for k in keys if t.get(k) is not None}
    out["pre"] = [(p["title"], p["status"]) for p in t.get("prerequisites") or []]
    return out


def task(key):
    return api("GET", f"~/tasks/{S[key]}")[1]


def trigger(agent, message, task_id=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if task_id:
        body["task_id"] = task_id
    st, res = api("POST", "~/agent/trigger", body)
    say(f"trigger {agent} -> {st}", {k: res.get(k) for k in ("run_id", "status", "waiting_reason", "detail")})
    return res


def wait_run(run_id, secs=900):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(4)
    return "still-running"


def walk(key, *statuses, notes=None):
    for to in statuses:
        body = {"status": to}
        if notes and to in ("revision_needed", "rejected"):
            body["notes"] = notes
        st, res = api("PATCH", f"~/tasks/{S[key]}", body)
        say(f"{key} -> {to}: {st}", brief(res) if st == 200 else res)


def phase_setup():
    d = pathlib.Path(e2e.PROJECTS) / "aw-tk1023"
    (d / "calc").mkdir(parents=True, exist_ok=True)
    (d / "tests").mkdir(exist_ok=True)
    (d / "tools").mkdir(exist_ok=True)
    (d / "calc" / "__init__.py").write_text("", encoding="utf-8")
    (d / "calc" / "ops.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (d / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (d / "tests" / "test_ops.py").write_text(
        "from calc.ops import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    (d / "tools" / "agent_probe.py").write_text(PROBE, encoding="utf-8")
    S["P"] = e2e.cmd_setup("aw-tk1023")
    S["DIR"] = str(d)
    save()
    st, rn = api("POST", "~/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    say("runner", (st, rn.get("id")))
    for name in ("alpha", "beta"):
        st, out = api("POST", "~/agents", {"name": name, "runner_id": rn["id"]})
        say(f"agent {name}", (st, out.get("name") if isinstance(out, dict) else out))
    specs = [
        ("K", "K: add sub() to calc/ops.py", "alpha", []),
        ("L", "L: use sub() in a report", None, ["K"]),
        ("M", "M: document sub()", None, ["K"]),
        ("W", "W: add mul() to calc/ops.py", "alpha", []),
        ("X", "X: alpha's work in progress", "alpha", []),
        ("Bown", "Bown: beta's probe task", "beta", []),
    ]
    for key, title, who, deps in specs:
        body = {"title": title, "description": f"Task {key}.", "depends_on": [S[k] for k in deps]}
        if who:
            body["assignee"] = who
        st, t = api("POST", "~/tasks", body)
        say(f"create {key}", (st, brief(t) if st == 201 else t))
        S[key] = t["id"]
    save()
    walk("X", "in_progress")
    walk("Bown", "in_progress")
    say("ids", S)


def _work(key, msg):
    res = trigger("alpha", msg, S[key])
    rid = res.get("run_id")
    say("run", wait_run(rid))
    S.setdefault("runs", {}).setdefault(key, []).append(rid)
    save()
    say(key, brief(task(key)))
    say("branches", git("branch", "-a"))


def phase_workk():
    _work("K", "Work on your task K. In calc/ops.py add `def sub(a, b): return a - b`. Commit the change with git "
               "(message 'add sub'). Then move your task to completed with update_task. Do nothing else.")


def phase_workw():
    _work("W", "Work on your task W. In calc/ops.py add `def mul(a, b): return a * b`. Commit the change with git "
               "(message 'add mul'). Then move your task to completed with update_task. Do nothing else.")


def phase_revise():
    walk("W", "under_review")
    walk("W", "revision_needed", notes="Add a test for mul() in tests/test_ops.py asserting mul(2, 3) == 6.")


def phase_workw2():
    _work("W", "Your task W came back with revision_needed; read its notes. Add `test_mul` in tests/test_ops.py "
               "asserting mul(2, 3) == 6 (import mul), commit with git, then move the task to completed. Do nothing else.")


def phase_approve():
    st, res = api("POST", f"~/tasks/{S['W']}/land", {})
    say("land W", (st, brief(res) if st == 200 else res))
    st, res = api("GET", f"~/tasks/{S['W']}/integrations")
    say("W integrations", (st, res))
    say("master", git("log", "--oneline", "-5", "master"))


def phase_probe():
    msg = ("Run exactly this one command from your workspace and nothing else: `py -3.11 tools/agent_probe.py`. "
           "Then call the AgentWeave tool task_history for task " + S["W"] + " and the tool list_tasks with "
           "limit 1000, and report in your reply, briefly, what each answered (status codes and refusals). "
           "Do not change any task yourself.")
    res = trigger("beta", msg, S["Bown"])
    rid = res.get("run_id")
    say("run", wait_run(rid))
    S["run_probe"] = rid
    save()
    p = pathlib.Path(os.path.expanduser("~/.agentweave/s1023_tk_probe.json"))
    if p.exists():
        for row in json.loads(p.read_text()):
            say(row["label"], (row["status"], row["body"]))
    else:
        say("probe file", "absent")


def phase_bulk():
    for i in range(105):
        st, _ = api("POST", "~/tasks", {"title": f"Z{i:03d}: bulk"})
        if st != 201:
            say("bulk create", (i, st, _))
            break
    st, res = api("GET", "~/tasks")
    say("GET /tasks", (st, len(res.get("tasks", [])), res.get("total"), res.get("has_more")))
    st, res = api("GET", "~/tasks?limit=1000")
    say("GET /tasks?limit=1000", (st, len(res.get("tasks", [])), res.get("total"), res.get("has_more")))
    st, res = api("GET", "~/tasks?limit=1001")
    say("GET /tasks?limit=1001", (st, res))
    st, res = api("GET", "~/tasks/board")
    say("board keys", (st, list(res.keys()) if isinstance(res, dict) else res))


def phase_story():
    key = sys.argv[2] if len(sys.argv) > 2 else "W"
    st, story = api("GET", f"~/tasks/{S[key]}/story")
    say("story", (st, story))
    st, tr = api("GET", f"~/tasks/{S[key]}/transitions")
    say("transitions", (st, tr))
    say("db transitions", ro("select from_status, to_status, actor_kind, actor_agent, origin, run_id, created_at "
                             "from task_transitions where task_id=? order by created_at", (S[key],)))
    say("db runs", ro("select id, agent, status, task_id, conversation_id, started_at, ended_at from runs "
                      "where task_id=? order by started_at", (S[key],)))


def phase_illegal():
    for key, to in (("L", "approved"), ("L", "under_review"), ("L", "in_progress"), ("W", "in_progress"),
                    ("W", "bogus")):
        st, res = api("PATCH", f"~/tasks/{S[key]}", {"status": to})
        say(f"{key} -> {to}", (st, res if st != 200 else brief(res)))
    st, res = api("PATCH", f"~/tasks/{S['L']}", {"title": "   "})
    say("blank title", (st, res))
    st, res = api("PATCH", f"~/tasks/{S['L']}", {"title": "x" * 600})
    say("600-char title", (st, res if st != 200 else len(res.get("title", ""))))
    st, res = api("PATCH", f"~/tasks/{S['L']}", {"assignee": "nobody-here"})
    say("unknown assignee", (st, res))
    st, res = api("PATCH", f"~/tasks/{S['L']}", {"priority": "urgent"})
    say("bad priority", (st, res))
    st, res = api("PATCH", f"~/tasks/{S['L']}", {"priority": "high"})
    say("priority-only (assignee kept?)", (st, brief(res) if st == 200 else res))
    st, res = api("GET", "~/tasks/transitions/allowed")
    say("allowed", (st, res))


def phase_delete():
    key = sys.argv[2] if len(sys.argv) > 2 else "K"
    say("before", brief(task(key)))
    say("branches before", git("branch", "-a"))
    say("worktrees before", git("worktree", "list"))
    st, res = api("DELETE", f"~/tasks/{S[key]}")
    say("DELETE", (st, res))
    say("events", ro("select event_type, data, severity, timestamp from event_logs where event_type in "
                     "('task_deleted','task_checkout_kept') order by timestamp desc limit 4"))
    say("branches after", git("branch", "-a"))
    say("worktrees after", git("worktree", "list"))
    for k in ("L", "M"):
        if k in S:
            say(k, brief(task(k)))


DOC = "spec/changes/calc-div/spec.json"


def phase_spec():
    reqs = [{"key": "div", "statement": "calc.ops MUST offer div(a, b) returning a / b.", "modal": "MUST"}]
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": "Calc division",
        "scope": {"in_scope": ["calc package"], "non_goals": ["complex numbers"]},
        "requirements": reqs,
        "acceptance_criteria": [{"key": "c-div", "requirement": "div", "given": "6, 3", "when": "div(6, 3)",
                                 "then": "2.0", "how_to_check": "py -3.11 -m pytest -q"}],
        "tasks": [{"key": "t-div", "title": "R: add div()", "description": "Add div() to calc/ops.py.",
                   "requirements": ["div"], "files": ["calc/ops.py"]}],
        "delivery": {"mode": "none"},
    }
    st, out = api("POST", "~/project/documents", {"path": DOC, "title": "Calc division"})
    say("doc create", (st, out.get("path") if isinstance(out, dict) else out))
    st, out = api("PUT", f"~/project/documents/{DOC}/content", {"document": doc})
    say("doc write", st)
    for step in ("close-exploration", "propose"):
        st, out = api("POST", f"~/project/documents/{step}?path={DOC}")
        say(step, (st, {k: out.get(k) for k in ("phase", "blocking")} if isinstance(out, dict) else out))
    st, out = api("POST", f"~/project/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
    say("approve anyway", (st, out.get("phase") if isinstance(out, dict) else out))
    st, tasks = api("GET", "~/tasks?limit=1000")
    for t in tasks["tasks"]:
        if t.get("spec_task_key") == "t-div":
            S["R"] = t["id"]
    save()
    api("PATCH", f"~/tasks/{S['R']}", {"assignee": "alpha"})
    say("R", brief(task("R")))


def phase_workr():
    _work("R", "Work on your task. In calc/ops.py add `def div(a, b): return a / b`. Commit it with git. Then record "
               "evidence for requirement FR-1 with the AgentWeave record_evidence tool naming your commit, and move "
               "your task to completed. Do nothing else.")
    say("evidence", ro("select * from requirement_evidence"))


def phase_delrun():
    res = trigger("alpha", "Work on your task X: run `py -3.11 -m pytest -q` and then move task X to completed.", S["X"])
    rid = res.get("run_id")
    time.sleep(4)
    say("run status", ro("select status from runs where id=?", (rid,)))
    st, out = api("DELETE", f"~/tasks/{S['X']}")
    say("DELETE X mid-run", (st, out))
    say("run", wait_run(rid))
    say("X after", api("GET", f"~/tasks/{S['X']}"))


def phase_stall():
    st, t = api("POST", "~/tasks", {"title": "S: say OK and stop", "assignee": "beta",
                                    "description": "Reply with the single word OK. Change nothing, update no task."})
    S["S"] = t["id"]
    save()
    res = trigger("beta", "Reply with the single word OK. Do not call any tool and do not change any task.", S["S"])
    say("run", wait_run(res.get("run_id")))
    say("S after the turn", {**brief(task("S")), "div": task("S").get("has_open_divergence")})
    st, res = api("PATCH", f"~/tasks/{S['S']}", {"status": "blocked", "blocked_reason": "Which currency should OK use?"})
    say("block S", (st, brief(res) if st == 200 else res))
    say("S", {**brief(task("S")), "div": task("S").get("has_open_divergence")})


def phase_state():
    st, tasks = api("GET", "~/tasks?limit=20")
    for t in tasks["tasks"]:
        say(t["id"], brief(t))


if __name__ == "__main__":
    globals()["phase_" + sys.argv[1]]()
