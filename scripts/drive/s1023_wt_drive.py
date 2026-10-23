"""2026-10-23 day sweep: Worktrees & integration, scratch Hub (hub-up wt1023 8160). Phases:

  setup    project ~/Documents/aw-wt1023 (greet.py + test), haiku runner, alpha + beta, two checks,
           T1 (alpha) and T2 (beta) that both rewrite greet.py's one line, N (nothing), I (alpha, held)
  work     alpha's turn on T1 and beta's on T2, in parallel; both commit on their task branches
  checks   checks per task, and F985 (checks/run on a task with no commit)
  preview  integration-preview for T1 and T2
  dirty    dirty the project's checkout, approve T2 -> skipped "uncommitted changes" (retryable)
  land1    clean the checkout, approve T1 -> merged; preview T2 again (now conflicts)
  retry    retry T2 -> merge fails (conflict); integrations listed
  fix      operator resolves on T2's own branch (merge master in, keep beta's line), retry -> merged
  skip     F917: approve N (nothing to merge), retry anyway
  iso      F242: flip alpha's isolation (read_only) while it holds I -> 409
  state    every task as the list returns it, master log, worktree list

  py -3.11 scripts/drive/s1023_wt_drive.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-s1023-wt.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1023_wt_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
HAIKU = "claude-haiku-4-5-20251001"


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


def git(*args, cwd=None):
    r = subprocess.run(["git", "-C", cwd or S["DIR"], *args], capture_output=True, text=True,
                       encoding="utf-8")
    return (r.stdout + r.stderr).strip()


def brief(t):
    keys = ("id", "title", "status", "assignee", "latest_integration", "blocked_reason")
    return {k: t.get(k) for k in keys if t.get(k) is not None}


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


def walk(key, *statuses):
    out = None
    for to in statuses:
        st, res = api("PATCH", f"~/tasks/{S[key]}", {"status": to})
        say(f"{key} -> {to}: {st}", brief(res) if st == 200 else res)
        out = (st, res)
    return out


def phase_setup():
    d = e2e.PROJECTS / "aw-wt1023"
    d.mkdir(parents=True, exist_ok=True)
    (d / "greet.py").write_text('def greet(name):\n    return "Hello, " + name\n', encoding="utf-8")
    (d / "test_greet.py").write_text(
        "from greet import greet\n\n\ndef test_greet():\n    assert greet('x').endswith('x')\n", encoding="utf-8")
    S["P"] = e2e.cmd_setup("aw-wt1023")
    S["DIR"] = str(d)
    save()
    st, proj = api("GET", "~")
    say("project", (st, {k: proj.get(k) for k in ("id", "main_branch", "path")} if isinstance(proj, dict) else proj))
    st, rn = api("POST", "~/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    say("runner", (st, rn.get("id")))
    for name in ("alpha", "beta"):
        st, out = api("POST", "~/agents", {"name": name, "runner_id": rn["id"]})
        say(f"agent {name}", (st, out.get("name") if isinstance(out, dict) else out))
    checks = [{"name": "tests", "command": "py -3.11 -m pytest -q", "timeout_seconds": 60},
              {"name": "status", "command": "git status --short", "timeout_seconds": 10}]
    st, out = api("PUT", "~/settings", {"checks": checks})
    say("checks", (st, out.get("checks") if isinstance(out, dict) else out))
    for key, title, who in (("T1", "T1: greet says Hi", "alpha"), ("T2", "T2: greet says Hey", "beta"),
                            ("N", "N: nothing to merge", "alpha"), ("I", "I: held by alpha", "alpha")):
        st, t = api("POST", "~/tasks", {"title": title, "assignee": who})
        say(f"create {key}", (st, brief(t) if st == 201 else t))
        S[key] = t["id"]
    save()
    say("ids", S)


MSG = ("Work on your task. In greet.py change the line `return \"Hello, \" + name` to "
       "`return \"{word}, \" + name`. Change nothing else. Run `py -3.11 -m pytest -q`, then commit greet.py "
       "with git (`git add greet.py` then `git commit -m \"greet says {word}\"`). Finally move your task to "
       "completed with the AgentWeave update_task tool.")


def phase_work():
    results = {}

    def go(agent, key, word):
        res = trigger(agent, MSG.format(word=word), S[key])
        rid = res.get("run_id")
        results[key] = (rid, wait_run(rid) if rid else None)

    threads = [threading.Thread(target=go, args=a) for a in (("alpha", "T1", "Hi"), ("beta", "T2", "Hey"))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    say("runs", results)
    S["runs"] = results
    save()
    for k in ("T1", "T2"):
        say(k, brief(task(k)))
    say("worktrees", git("worktree", "list"))
    say("branches", git("branch", "-a", "-v"))
    say("run rows", ro("select id, agent, status, task_id, workspace_dir from runs order by started_at"))


def phase_checks():
    for k in ("T1", "T2"):
        st, out = api("GET", f"~/tasks/{S[k]}/checks")
        say(f"{k} checks", (st, out))
    st, out = api("POST", f"~/tasks/{S['I']}/checks/run")
    say("F985 checks/run on I (no commit)", (st, out))
    st, out = api("GET", f"~/tasks/{S['I']}/checks")
    say("I checks after", (st, out))


def phase_preview():
    for k in ("T1", "T2"):
        st, out = api("GET", f"~/tasks/{S[k]}/integration-preview")
        say(f"{k} preview", (st, out))


def phase_dirty():
    readme = pathlib.Path(S["DIR"]) / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "operator scratch line\n", encoding="utf-8")
    say("status", git("status", "--short"))
    st, out = api("GET", f"~/tasks/{S['T2']}/integration-preview")
    say("T2 preview dirty", (st, out.get("reason") if isinstance(out, dict) else out))
    st, out = api("POST", f"~/tasks/{S['T2']}/land", {})
    say("land T2", (st, brief(out) if st == 200 else out))
    st, out = api("GET", f"~/tasks/{S['T2']}/integrations")
    say("T2 integrations", (st, out))


def phase_land1():
    say("restore", git("checkout", "--", "README.md"))
    say("status", git("status", "--short"))
    st, out = api("POST", f"~/tasks/{S['T1']}/land", {})
    say("land T1", (st, brief(out) if st == 200 else out))
    st, out = api("GET", f"~/tasks/{S['T1']}/integrations")
    say("T1 integrations", (st, out))
    say("master", git("log", "--oneline", "-5", "master"))
    st, out = api("GET", f"~/tasks/{S['T2']}/integration-preview")
    say("T2 preview after T1", (st, out))


def phase_retry():
    st, out = api("POST", f"~/tasks/{S['T2']}/integrations/retry")
    say("retry T2", (st, out))
    say("status after", git("status", "--short"))
    say("master", git("log", "--oneline", "-5", "master"))
    say("T2", brief(task("T2")))


def phase_fix():
    wt = ro("select workspace_dir from runs where task_id=? order by started_at desc limit 1", (S["T2"],))
    path = wt[0]["workspace_dir"] if wt else None
    say("T2 checkout", path)
    if path and pathlib.Path(path).exists():
        say("merge master in", git("-c", "user.name=op", "-c", "user.email=op@x", "merge", "master", cwd=path))
        say("checkout --ours", git("checkout", "--ours", "greet.py", cwd=path))
        say("add", git("add", "greet.py", cwd=path))
        say("commit", git("-c", "user.name=op", "-c", "user.email=op@x", "commit", "--no-edit", cwd=path))
        say("branch log", git("log", "--oneline", "-4", cwd=path))
    st, out = api("GET", f"~/tasks/{S['T2']}/integration-preview")
    say("T2 preview after fix", (st, out))
    if "--retry" in sys.argv:
        st, out = api("POST", f"~/tasks/{S['T2']}/integrations/retry")
        say("retry T2 after fix", (st, out))
    say("master", git("log", "--oneline", "-6", "master"))
    say("greet.py on master", git("show", "master:greet.py"))
    say("T2", brief(task("T2")))


def phase_skip():
    walk("N", "in_progress", "completed", "under_review", "approved")
    st, res = api("GET", f"~/tasks/{S['N']}/integrations")
    say("N integrations", (st, res))
    st, res = api("POST", f"~/tasks/{S['N']}/integrations/retry")
    say("F917 retry N anyway", (st, res))


def phase_iso():
    st, res = api("PATCH", "~/agents/alpha", {"config": {"read_only": True}})
    say("flip alpha to read_only while holding I", (st, res))
    st, res = api("GET", "~/agents/alpha")
    say("alpha config after", (st, res.get("config") if isinstance(res, dict) else res))


def phase_t3():
    """Gate vs preview: alpha's T3 turn rewrites the line, then the operator moves master under it."""
    st, t = api("POST", "~/tasks", {"title": "T3: greet says Yo", "assignee": "alpha"})
    S["T3"] = t["id"]
    save()
    res = trigger("alpha", MSG.format(word="Yo").replace('"Hello, "', '"Hey, "'), S["T3"])
    rid = res.get("run_id")
    say("run", (rid, wait_run(rid) if rid else None))
    say("T3", brief(task("T3")))
    say("branches", git("branch", "-v"))


def phase_gate():
    p = pathlib.Path(S["DIR"]) / "greet.py"
    p.write_text('def greet(name):\n    return "Howdy, " + name\n', encoding="utf-8")
    say("operator commit", git("-c", "user.name=op", "-c", "user.email=op@x", "commit", "-am", "operator: Howdy"))
    st, out = api("GET", f"~/tasks/{S['T3']}/integration-preview")
    say("T3 preview", (st, out))
    st, out = api("POST", f"~/tasks/{S['T3']}/land", {})
    say("T3 land", (st, out))
    st, out = api("PATCH", f"~/tasks/{S['T3']}", {"status": "under_review", "assignee": None})
    say("T3 -> under_review (unassigned)", (st, brief(out) if st == 200 else out))
    st, out = api("PATCH", f"~/tasks/{S['T3']}", {"status": "approved"})
    say("T3 -> approved", (st, out))
    say("T3 integrations", api("GET", f"~/tasks/{S['T3']}/integrations"))
    say("T3", brief(task("T3")))
    say("master", git("log", "--oneline", "-3", "master"))


def phase_resolve():
    """Send T3 back; alpha resolves the conflict on its own branch; Land it."""
    st, out = api("PATCH", f"~/tasks/{S['T3']}", {"status": "revision_needed", "assignee": "alpha",
                                                     "notes": "greet.py conflicts with master (operator: Howdy). Merge master in, keep Yo."})
    say("T3 -> revision_needed", (st, brief(out) if st == 200 else out))
    msg = ("Your task was sent back: greet.py conflicts with the master branch. In your checkout run "
           "`git merge master`, resolve greet.py so the line reads `return \"Yo, \" + name`, then "
           "`git add greet.py` and `git commit --no-edit`. Run `py -3.11 -m pytest -q`. Then move your task "
           "to completed with the AgentWeave update_task tool.")
    res = trigger("alpha", msg, S["T3"])
    rid = res.get("run_id")
    say("run", (rid, wait_run(rid) if rid else None))
    say("T3", brief(task("T3")))
    say("branch", git("log", "--oneline", "-4", f"agentweave/task/{S['T3']}"))
    st, out = api("GET", f"~/tasks/{S['T3']}/integration-preview")
    say("T3 preview", (st, out.get("reason") if isinstance(out, dict) else out))
    time.sleep(5)
    st, out = api("GET", f"~/tasks/{S['T3']}/checks")
    say("T3 checks", (st, [(r["state"], r["target_shas"], r["error"]) for r in out.get("runs", [])] if isinstance(out, dict) else out))
    st, out = api("POST", f"~/tasks/{S['T3']}/land", {})
    say("T3 land", (st, brief(out) if st == 200 else out))
    say("master", git("log", "--oneline", "-4", "master"))
    say("greet.py on master", git("show", "master:greet.py"))


NOHOWDY = "py -3.11 -c \"import sys; sys.exit(3 if 'Howdy' in open('greet.py').read() else 0)\""


def phase_checkfail():
    """A check that fails on the work: completion runs it, Land is refused naming it, override lands."""
    checks = [{"name": "tests", "command": "py -3.11 -m pytest -q", "timeout_seconds": 60},
              {"name": "nohowdy", "command": NOHOWDY, "timeout_seconds": 20}]
    st, out = api("PUT", "~/settings", {"checks": checks})
    say("checks", (st, [c["name"] for c in out.get("checks", [])] if isinstance(out, dict) else out))
    st, t = api("POST", "~/tasks", {"title": "T4: greet says Howdy", "assignee": "beta"})
    S["T4"] = t["id"]
    save()
    res = trigger("beta", MSG.format(word="Howdy").replace('"Hello, "', '"Yo, "'), S["T4"])
    rid = res.get("run_id")
    say("run", (rid, wait_run(rid) if rid else None))
    say("T4", brief(task("T4")))
    for _ in range(20):
        st, out = api("GET", f"~/tasks/{S['T4']}/checks")
        if out.get("runs") and not out.get("running"):
            break
        time.sleep(2)
    say("T4 checks", (st, [(r["state"], [(x["name"], x["exit_code"]) for x in r["results"]], r["error"]) for r in out.get("runs", [])]))
    st, out = api("POST", f"~/tasks/{S['T4']}/land", {})
    say("T4 land", (st, out))
    st, out = api("POST", f"~/tasks/{S['T4']}/land", {"override_checks_reason": "   "})
    say("T4 land blank override", (st, out))
    st, out = api("POST", f"~/tasks/{S['T4']}/land", {"override_checks_reason": "Howdy is wanted this once"})
    say("T4 land override", (st, brief(out) if st == 200 else out))
    say("master", git("log", "--oneline", "-3", "master"))
    say("greet.py on master", git("show", "master:greet.py"))


NOBAD = "py -3.11 -c \"import os, sys; sys.exit(4 if os.path.exists('bad.txt') else 0)\""


def phase_bypass():
    """An approved, merged task whose branch gains a commit: retry merges it with no check and no review."""
    checks = [{"name": "tests", "command": "py -3.11 -m pytest -q", "timeout_seconds": 60},
              {"name": "nobad", "command": NOBAD, "timeout_seconds": 20}]
    st, out = api("PUT", "~/settings", {"checks": checks})
    say("checks", (st, [c["name"] for c in out.get("checks", [])] if isinstance(out, dict) else out))
    branch = f"agentweave/task/{S['T1']}"
    tmp = pathlib.Path(os.environ.get("TEMP", "C:/Windows/Temp")) / "wt1023bypass"
    say("worktree add", git("worktree", "add", "-q", str(tmp), branch))
    (tmp / "bad.txt").write_text("this file fails the nobad check\n", encoding="utf-8")
    say("commit", git("add", "bad.txt", cwd=str(tmp)) + git("-c", "user.name=op", "-c", "user.email=op@x",
                                                             "commit", "-qm", "bad.txt after approval", cwd=str(tmp)))
    say("worktree remove", git("worktree", "remove", str(tmp)))
    say("T1 before", brief(task("T1")))
    st, out = api("GET", f"~/tasks/{S['T1']}/integration-preview")
    say("T1 preview", (st, out.get("reason") if isinstance(out, dict) else out))
    st, out = api("POST", f"~/tasks/{S['T1']}/integrations/retry")
    say("retry T1", (st, [(r["outcome"], (r["commit_sha"] or "")[:8], r["retryable"]) for r in out.get("integrations", [])]
                      if isinstance(out, dict) and "integrations" in out else out))
    say("master", git("log", "--oneline", "-3", "master"))
    say("bad.txt on master", git("show", "master:bad.txt"))
    time.sleep(3)
    st, out = api("GET", f"~/tasks/{S['T1']}/checks")
    say("T1 checks", (st, [(r["state"], [t[:8] for t in r["target_shas"]], [(x["name"], x["exit_code"]) for x in r["results"]]) for r in out.get("runs", [])]))
    say("T1 transitions", ro("select from_status, to_status, actor_kind, override_reason from task_transitions where task_id=? order by sequence", (S["T1"],)))


def phase_fault():
    """What each integration route answers with the project's .git moved aside (always restored)."""
    g = pathlib.Path(S["DIR"]) / ".git"
    off = pathlib.Path(S["DIR"]) / ".git.off"
    g.rename(off)
    try:
        for label, method, path in (
            ("preview T4", "GET", f"~/tasks/{S['T4']}/integration-preview"),
            ("checks T4", "GET", f"~/tasks/{S['T4']}/checks"),
            ("checks/run T4", "POST", f"~/tasks/{S['T4']}/checks/run"),
            ("retry T4", "POST", f"~/tasks/{S['T4']}/integrations/retry"),
            ("retry N", "POST", f"~/tasks/{S['N']}/integrations/retry"),
            ("worktrees", "GET", "~/worktrees"),
            ("land I", "POST", f"~/tasks/{S['I']}/land"),
        ):
            st, out = api(method, path, {} if method == "POST" else None)
            if isinstance(out, dict) and "integrations" in out:
                out = [(r["outcome"], r["reason"][:160], r["retryable"]) for r in out["integrations"]][-1:]
            say(label, (st, out))
    finally:
        off.rename(g)
    say("restored", g.is_dir())


def phase_iwork():
    """alpha commits work on I and completes it, so I holds unmerged work (F916), then flip checks."""
    res = trigger("alpha", "Work on your task: create a file extra.py containing `X = 1`, then `git add extra.py` and "
                  "`git commit -m \"add extra\"`. Then move your task to completed with the AgentWeave update_task tool.",
                  S["I"])
    rid = res.get("run_id")
    say("run", (rid, wait_run(rid) if rid else None))
    say("I", brief(task("I")))
    say("branch", git("log", "--oneline", "-2", f"agentweave/task/{S['I']}"))


def phase_iso2():
    """After I is gone: the flip with nothing held goes through, and back."""
    for flag in (True, None):
        st, res = api("PATCH", "~/agents/alpha", {"config": {"read_only": flag}})
        say(f"flip alpha read_only={flag}", (st, res.get("config") if isinstance(res, dict) else res))
        say("worktree view", api("GET", "~/agents/alpha/workspace"))


def phase_traces():
    """F997: every check_run / task_integration trace, its aw.command spans and which are errors."""
    st, out = api("GET", "~/traces?limit=200")
    rows = out if isinstance(out, list) else out.get("traces", [])
    kinds = {}
    for r in rows:
        kinds[r.get("kind") or r.get("name")] = kinds.get(r.get("kind") or r.get("name"), 0) + 1
    say("trace kinds", (st, kinds))
    want = sys.argv[2].split(",") if len(sys.argv) > 2 else ["check_run", "task_integration"]
    for r in rows:
        label = r.get("name")
        if not any(w in str(label) for w in want):
            continue
        st, tr = api("GET", f"~/traces/{r['trace_id']}")
        spans = tr.get("spans", []) if isinstance(tr, dict) else []
        cmds = [s for s in spans if s.get("operation") == "aw.command"]
        errs = [s for s in cmds if s.get("status") == "error"]
        say(f"trace {r['trace_id']} {label} {r.get('started_at')}", f"{len(spans)} spans, {len(cmds)} aw.command, {len(errs)} error")
        for s in errs:
            a = s.get("attributes") or {}
            argv = a.get("aw.command.argv") or a.get("process.command_args") or a.get("aw.command") or ""
            print("    ERR", str(argv)[:160], "|", a.get("aw.command.exit_code") or a.get("process.exit.code"),
                  "|", (s.get("status_message") or "")[:120])


def phase_state():
    st, tasks = api("GET", "~/tasks")
    for t in tasks["tasks"]:
        say(t["id"], brief(t))
    say("master", git("log", "--oneline", "--graph", "-10", "master"))
    say("worktrees", git("worktree", "list"))


if __name__ == "__main__":
    globals()["phase_" + sys.argv[1]]()
