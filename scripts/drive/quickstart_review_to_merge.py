"""Acceptance drive for `a-hand-started-task-reaches-review-and-merge` (HSTRR, spdoc-cf43204735ff),
2026-11-13. FR-5 `ac-drive`: written, and recorded failing on master, before the build (HSTRR-1).

The quickstart (docs/getting-started/quickstart.md) as a first-time operator follows it, with nothing
else done by hand:

  1  hub        its own Hub from this checkout's source on --port, its database under
                <tmp>/aw-quickstart-review/<profile>/ (never :8000, never the trial :8010); HUB_URL and
                every AW_* are stripped from its environment, so its agents cannot call the shell's Hub
  2  project    a fresh git project on `main` (greet.py with `greet(name)`, a test, a README), opened
  3  agents     planner (Spec Author), builder (Developer), reviewer (Code Reviewer), all Haiku, made
                the way the Add agent dialog makes them (provider + model + charter)
  4  ask        the planner is asked, in its conversation, for a one-function change and its task; its
                questions are answered as an operator would; it gets up to --planner-turns turns
  5  check      Check on the document (moves nothing), then Approve with the version read, and
                Approve anyway over the gaps if the Hub lists any; the tasks land on the board
  6  start      the builder is started on the first task from the card: the trigger the card's
                "Start builder on this" posts (`task_id`, `Work on task <id>: <title>`)
  7  wait       nothing more from the operator. Questions are still answered (the quickstart says an
                agent asks and waits), but no task is moved, no review is triggered, nothing is landed.
                The wait ends when the task is approved, or when nothing has moved for --stall-minutes
                (no run active in the project and the task's status unchanged), or at --timeout-minutes

PASS only if, at the end:
  a  the task is `approved`
  b  the move to `approved` was made by an agent's run, and that agent is not the builder (not the
     operator: "Land it" is the operator's move and is never pressed here)
  c  the task has evidence, none of it left awaiting, and at least one piece accepted
  d  the accepted evidence's commit is on `main`, and `main` moved past the seed commit

It prints PASS/FAIL per check, then the task's status, its transitions, its evidence and
`git log --oneline main`. Exit 0 on PASS, 1 on FAIL. On master (before the build) it is expected to
FAIL at `a`: the builder completes the task and nothing starts a review (the stall ends the wait).

    py -3.11 scripts/drive/quickstart_review_to_merge.py --profile hstrr --port 8131
    ... --model claude-haiku-5-5 --stall-minutes 6 --timeout-minutes 45 --planner-turns 4
"""

import argparse
import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
FORBIDDEN_PORTS = (8000, 8010)
PLANNER, BUILDER, REVIEWER = "planner", "builder", "reviewer"
CHARTERS = {PLANNER: "Spec Author", BUILDER: "Developer", REVIEWER: "Code Reviewer"}
ACTIVE_RUN = ("running", "queued", "starting")

GREET_PY = 'def greet(name):\n    return "Hello, " + name\n'
TEST_PY = (
    "from greet import greet\n\n\n"
    "def test_greet():\n"
    '    assert greet("Ada") == "Hello, Ada"\n'
)
README = "A tiny greeting library. Run the tests with `python -m pytest -q`.\n"
ASK = (
    "One small change for this greeting library: add a function `farewell(name)` to greet.py that "
    'returns "Goodbye, <name>", with a test beside the existing one. Please author a short change '
    "specification with one requirement and its scenario, then exactly one task for the builder. "
    "This is a fix-sized change: size it as a fix, and carry the document through its steps to its "
    "task in this conversation without waiting for me between steps."
)
CONTINUE = (
    "Carry on: finish the change specification through to its single task for the builder, "
    "advancing the steps yourself. I will check and approve it when you are done."
)

HUB = ""
KEY = "aw_live_" + secrets.token_hex(16)
DB = pathlib.Path()
results = []


class DriveStopError(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise DriveStopError(name)
    return bool(ok)


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except urllib.error.URLError as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
        cwd=root, capture_output=True, text=True,
    )


def poll(fn, secs):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- the Hub still starting
            pass
        time.sleep(0.5)
    return False


def start_hub(port, home):
    # Nothing of the shell's own Hub may reach this one: a drive started inside an agent turn
    # inherits that turn's HUB_URL (the operator's :8000) and run credential, and the Hub prefers
    # its own HUB_URL over the address it observes when telling a run where to call back.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(home / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120):
        stop_hub(proc)
        sys.exit(f"hub did not come up; see {home / 'hub.log'}")
    return proc


def stop_hub(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


# ------------------------------------------------------------------ the operator's answers

def answer_questions(base, answered):
    """Answer every open question as an operator following the quickstart would: take the option
    that keeps the change small and moving, else the first one."""
    _, pending = api("GET", f"{base}/questions?answered=false")
    for question in pending if isinstance(pending, list) else []:
        if question["id"] in answered:
            continue
        answered.add(question["id"])
        labels = [o.get("label", "") for o in question.get("options") or [] if isinstance(o, dict)]
        prefer = ("fix", "small", "yes", "continue", "proceed", "approve", "advance", "go ahead")
        pick = next((lb for p in prefer for lb in labels if p in lb.lower()), labels[0] if labels else "")
        answer = pick or "Keep it minimal: just farewell(name) and its test. Carry on without asking."
        print(f"  asked {question.get('agent')}: {question.get('question', '')[:160]!r} -> {answer!r}",
              flush=True)
        api("PATCH", f"{base}/questions/{question['id']}",
            {"answer": answer, "labels": [pick] if pick else []})


def active_runs(pid):
    marks = ",".join("?" * len(ACTIVE_RUN))
    return ro(f"select id, agent, task_id, status from runs where project_id=? and status in ({marks})",
              (pid, *ACTIVE_RUN))


def wait_for_run(base, pid, run_id, minutes, answered):
    end = time.time() + minutes * 60
    while time.time() < end:
        answer_questions(base, answered)
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0][0] not in ACTIVE_RUN:
            print(f"  run {run_id} {rows[0][0]}", flush=True)
            return rows[0][0]
        time.sleep(5)
    return "timeout"


# ------------------------------------------------------------------ the planner's document

def find_tasks(node):
    """The declared tasks in a spec.json, wherever the payload keeps them."""
    if isinstance(node, dict):
        tasks = node.get("tasks")
        if isinstance(tasks, list) and tasks and all(isinstance(t, dict) for t in tasks):
            return tasks
        for value in node.values():
            found = find_tasks(value)
            if found:
                return found
    return []


def planner_document(base, root):
    _, rows = api("GET", f"{base}/project/documents")
    rows = rows if isinstance(rows, list) else (rows or {}).get("documents", [])
    changes = [r for r in rows if r.get("kind") == "change-spec" and r.get("phase") == "exploring"]
    if not changes:
        return None, []
    doc = changes[-1]
    file = root / doc["path"]
    tasks = find_tasks(json.loads(file.read_text(encoding="utf-8"))) if file.is_file() else []
    return doc, tasks


# ------------------------------------------------------------------ the drive

def drive(args, home):
    root = home / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "greet.py").write_text(GREET_PY, encoding="utf-8")
    (root / "test_greet.py").write_text(TEST_PY, encoding="utf-8")
    (root / "README.md").write_text(README, encoding="utf-8")
    git(root, "add", "greet.py", "test_greet.py", "README.md")
    git(root, "commit", "-q", "-m", "Initial greeting library")
    seed = git(root, "rev-parse", "HEAD").stdout.strip()

    # 2-3: the project and its three agents.
    code, project = api("POST", "/projects/open", {"path": str(root), "name": "quickstart-review"})
    check("2 the project opens", code in (200, 201), f"{code} {str(project)[:300]}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    _, charters = api("GET", f"{base}/charters")
    by_name = {c["name"]: c["id"] for c in charters if isinstance(c, dict)} if isinstance(charters, list) else {}
    for name, charter in CHARTERS.items():
        body = {"name": name, "provider": "claude", "model": args.model}
        if charter in by_name:
            body["charter_id"] = by_name[charter]
        code, out = api("POST", f"{base}/agents", body)
        check(f"3 agent {name} ({charter}, {args.model})", code in (200, 201) and charter in by_name,
              f"{code} {str(out)[:200]}", fatal=True)

    # 4: ask the planner.
    answered = set()
    conversation = None
    doc, tasks = None, []
    for turn in range(1, args.planner_turns + 1):
        body = {"agent": PLANNER, "message": ASK if turn == 1 else CONTINUE}
        if conversation:
            body["conversation_id"] = conversation
        code, run = api("POST", f"{base}/agent/trigger", body)
        check(f"4.{turn} the planner's turn starts", code in (200, 202) and run.get("run_id"),
              f"{code} {str(run)[:300]}", fatal=True)
        conversation = run.get("conversation_id") or conversation
        wait_for_run(base, pid, run["run_id"], args.turn_minutes, answered)
        doc, tasks = planner_document(base, root)
        print(f"  after turn {turn}: document={doc and doc.get('path')} step={doc and doc.get('step')} "
              f"tasks={len(tasks)}", flush=True)
        if doc and tasks:
            break
    check("4 the planner wrote a change document with a task", bool(doc and tasks),
          f"document={doc and doc.get('path')} tasks={len(tasks)}", fatal=True)
    path = doc["path"]
    quoted = urllib.parse.quote(path)

    # 5: Check, then Approve (anyway, over the gaps it lists).
    code, checked = api("POST", f"{base}/project/documents/check?path={quoted}")
    check("5a Check answers and moves nothing", code == 200 and isinstance(checked, dict),
          f"{code} {str(checked)[:300]}", fatal=True)
    print(f"  check: ready={checked.get('ready')} blocking={len(checked.get('blocking') or [])} "
          f"warnings={len(checked.get('warnings') or [])}", flush=True)
    version = checked.get("content_version")
    approve = {"reason": "quickstart drive", "content_version": version}
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved", approve)
    if code == 409:
        print(f"  approval listed gaps: {str(out)[:400]}", flush=True)
        code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                        {**approve, "approve_anyway": True})
    check("5b Approve (anyway) approves the document", code == 200 and out.get("phase") == "approved",
          f"{code} {str(out)[:400]}", fatal=True)

    _, listed = api("GET", f"{base}/tasks?limit=1000")
    board = [t for t in (listed or {}).get("tasks", []) if t.get("spec_document_id") == doc.get("id")]
    ready = [t for t in board if not t.get("prerequisites")] or board
    check("5c approval put the document's tasks on the board", bool(board),
          f"{[(t.get('readable_id'), t.get('status')) for t in board]}", fatal=True)
    task = ready[0]
    task_id = task["id"]

    # 6: "Start builder on this", as the card posts it.
    code, run = api("POST", f"{base}/agent/trigger", {
        "agent": BUILDER, "message": f"Work on task {task_id}: {task.get('title', '')}",
        "task_id": task_id,
    })
    check("6 the card starts the builder on the task", code in (200, 202) and run.get("run_id"),
          f"{code} {str(run)[:300]}", fatal=True)

    # 7: wait, doing nothing but answer questions.
    started = time.time()
    last_status, last_change = None, time.time()
    seen = []
    while time.time() - started < args.timeout_minutes * 60:
        answer_questions(base, answered)
        _, now = api("GET", f"{base}/tasks/{task_id}")
        status = (now or {}).get("status") if isinstance(now, dict) else None
        running = active_runs(pid)
        if status != last_status:
            print(f"  [{int(time.time() - started):>5}s] task {status} "
                  f"(stage {now.get('stage')}: {now.get('stage_detail')}) "
                  f"runs={[(r[1], r[2] == task_id) for r in running]}", flush=True)
            seen.append(status)
            last_status, last_change = status, time.time()
        if running:
            last_change = time.time()
        if status in ("approved", "rejected"):
            break
        if time.time() - last_change > args.stall_minutes * 60:
            print(f"  nothing moved for {args.stall_minutes} min with the task {status} and no run "
                  f"active: the wait ends (stage {now.get('stage')}: {now.get('stage_detail')}, "
                  f"waiting_on {now.get('waiting_on')})", flush=True)
            break
        time.sleep(15)
    report(base, root, task_id, seed)


def report(base, root, task_id, seed):
    _, task = api("GET", f"{base}/tasks/{task_id}")
    _, history = api("GET", f"{base}/tasks/{task_id}/transitions")
    _, ev = api("GET", f"{base}/project/spec/evidence")
    transitions = (history or {}).get("transitions", []) if isinstance(history, dict) else []
    evidence = [e for e in (ev or {}).get("evidence", []) if e.get("task_id") == task_id]
    builder_moves = [t for t in transitions if t.get("to_status") == "completed"]
    author = builder_moves[-1].get("actor_agent") if builder_moves else BUILDER
    approvals = [t for t in transitions if t.get("to_status") == "approved"]
    approval = approvals[-1] if approvals else {}
    main_log = git(root, "log", "--oneline", "main").stdout.strip()

    print("\n--- the task", flush=True)
    print(f"  {task.get('readable_id')} {task_id}: {task.get('status')} "
          f"(stage {task.get('stage')}: {task.get('stage_detail')})")
    print("--- transitions")
    for t in transitions:
        print(f"  {t.get('from_status')} -> {t.get('to_status')}  by {t.get('actor_kind')}"
              f"/{t.get('actor_agent')} origin={t.get('origin')}")
    print("--- evidence")
    for e in evidence:
        requirement = e.get("requirement")
        if isinstance(requirement, dict):
            requirement = requirement.get("identifier")
        print(f"  {e.get('id')} {requirement} {e.get('review_state')} commit={e.get('commit')} "
              f"by {(e.get('actor') or e.get('author_record'))}")
    print("--- git log --oneline main")
    print("  " + main_log.replace("\n", "\n  "))
    print()

    check("a the task ends approved", task.get("status") == "approved", f"status={task.get('status')}")
    check("b approved by a reviewing agent, not the builder and not the operator",
          bool(approval) and approval.get("actor_kind") != "operator"
          and approval.get("actor_agent") not in (None, "", author),
          f"approval by {approval.get('actor_kind')}/{approval.get('actor_agent')}, builder={author}"
          if approval else "no move to approved")
    accepted = [e for e in evidence if e.get("review_state") == "accepted"]
    awaiting = [e for e in evidence if e.get("review_state") == "awaiting"]
    check("c its evidence is accepted, none left awaiting", bool(accepted) and not awaiting,
          f"accepted={len(accepted)} awaiting={len(awaiting)} total={len(evidence)}")
    commits = {e.get("commit") for e in accepted if e.get("commit")}
    on_main = bool(commits) and all(
        git(root, "merge-base", "--is-ancestor", c, "main").returncode == 0 for c in commits)
    head = git(root, "rev-parse", "main").stdout.strip()
    check("d its commit is on main, and main moved past the seed", on_main and head != seed,
          f"evidence commits={sorted(commits)} main={head[:12]} seed={seed[:12]}")


def main():
    global HUB, DB
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="hstrr", help="names this drive's scratch Hub home")
    parser.add_argument("--port", type=int, default=8131)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--planner-turns", type=int, default=4)
    parser.add_argument("--turn-minutes", type=int, default=15)
    parser.add_argument("--stall-minutes", type=int, default=6)
    parser.add_argument("--timeout-minutes", type=int, default=45)
    args = parser.parse_args()
    if args.port in FORBIDDEN_PORTS:
        sys.exit(f"port {args.port} is a real Hub's (8000 the operator's, 8010 the trial); pick another")

    # Outside this checkout: the Hub refuses to open a project nested in a task checkout.
    home = (pathlib.Path(tempfile.gettempdir()) / "aw-quickstart-review" / args.profile
            / time.strftime("%Y%m%d-%H%M%S"))
    home.mkdir(parents=True)
    HUB = f"http://127.0.0.1:{args.port}"
    DB = home / "hub.db"
    print(f"hub {HUB}, home {home}", flush=True)
    proc = start_hub(args.port, home)
    try:
        drive(args, home)
    except DriveStopError:
        pass
    finally:
        stop_hub(proc)
    failed = [name for name, ok in results if not ok]
    print("\nFAIL: " + "; ".join(failed) if failed else "\nPASS", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
