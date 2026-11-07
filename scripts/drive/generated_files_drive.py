"""Acceptance drive for `generated-files-are-rebuilt-when-work-lands-instead-of-sending-it-back`.

The change's `drive` task (GFARW-1, spdoc-ce4fd0e56b1a), written before the build of the rest, for
FR-3's ac-drive: two tasks branched from the same commit, one editing a.txt and one editing b.txt,
each committing its own rebuilt gen.txt, land one after the other; neither is sent back, and main's
gen.txt equals what `python gen.py` produces on main's a.txt and b.txt. On master before the build
it fails at the second task's landing, which is sent back merge-needed: the two gen.txt clash.

It starts its own Hub from this checkout on a free port (never :8000 or :8010) with a throwaway
database and bootstrap key, and its PATH carries a stub `claude` in place of the real one: it answers
`--version`, so agents can be created, and fails every turn before it touches anything, so the
drive's own hand is the only builder and no model is billed. The builder's part (edit, regenerate,
commit) is done in task worktrees the drive cuts itself at the same main commit, on the branch the
Hub would use (`agentweave/task/<id>`); the Hub accepts a registered worktree on that branch as the
task's checkout (`worktrees.ensure_task_worktree`).

The contract it drives (the change's design):
  - project setting `generated_files: {"paths": ["gen.txt"], "command": "python gen.py",
    "timeout_seconds": 60}`, through PUT /projects/{id}/settings beside `checks`;
  - each task: completed -> under_review -> approved, with the operator's evidence (accepted on
    arrival) recorded at the task's commit first, since a flow's approval lands only work backed by
    accepted evidence;
  - a landing that rebuilt generated files writes a merge commit whose message ends
    ` (generated files rebuilt)`, and its landing record carries `regenerated`.

    py -3.11 scripts/drive/generated_files_drive.py

Exit 0 when every check passes. AW_DRIVE_KEEP=1 leaves the Hub running and its files in place.
"""

import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%Y%m%d-%H%M%S")
TMP = pathlib.Path(tempfile.gettempdir()) / "drive-generated-files" / STAMP
DB = TMP / "hub" / "agentweave.db"
KEY = "aw_live_" + secrets.token_hex(16)
FORBIDDEN_PORTS = {8000, 8010}
BUILDER, CHECKER = "Builder", "Checker"
HAIKU = "haiku"
DOC = "spec/changes/generated-drive/spec.json"
TITLE = "Generated files drive"
SUFFIX = " (generated files rebuilt)"
LAND_WAIT = 10 * 60
results = []
PORT = 0
HUB = ""

# The fixture's generator. gen.txt is one line naming both inputs, so two tasks that each change
# one input and regenerate it change the same line of gen.txt: their source changes merge cleanly
# and their generated output conflicts, the case the change is about.
GEN_PY = '''import hashlib
import pathlib

a = pathlib.Path("a.txt").read_text(encoding="utf-8").strip()
b = pathlib.Path("b.txt").read_text(encoding="utf-8").strip()
digest = hashlib.sha256((a + "|" + b).encode("utf-8")).hexdigest()[:12]
pathlib.Path("gen.txt").write_text(f"a={a} b={b} sha={digest}\\n", encoding="utf-8")
'''


class Stop(Exception):  # noqa: N818 -- the drive's own stop signal, as in its siblings
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return 0, str(exc)


def git(cwd, *args, check_rc=True):
    out = subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=drive",
                          *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check_rc and out.returncode:
        raise RuntimeError(f"git {' '.join(args)} -> {out.returncode}: {out.stderr.strip()}")
    return out.stdout.strip()


def poll(fn, secs, every=2.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- not there yet
            pass
        time.sleep(every)
    return None


def free_port():
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


def python_command():
    """`python gen.py` as the design states it, when a `python` is on PATH; else this interpreter."""
    return "python gen.py" if shutil.which("python") else f'"{sys.executable}" gen.py'


def start_hub():
    global PORT, HUB
    PORT = free_port()
    HUB = f"http://127.0.0.1:{PORT}"
    DB.parent.mkdir(parents=True)
    # The drive may run inside an agent turn on another Hub: its HUB_URL, credential and tool-server
    # bin would reach this Hub's agents, whose tool calls would then go to that other Hub.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    stub = TMP / "stub-claude"
    stub.mkdir()
    (stub / "claude.cmd").write_text(
        '@echo off\nif "%~1"=="--version" (echo 0.0.0 drive stub& exit /b 0)\n'
        "echo the drive's stub claude runs no turn 1>&2\nexit /b 1\n", encoding="utf-8")
    keep = [d for d in env.get("PATH", "").split(os.pathsep)
            if d and "tool-server" not in d.replace("\\", "/") and not shutil.which("claude", path=d)]
    env["PATH"] = os.pathsep.join([str(stub), *keep])
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log_path = TMP / "hub.log"
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 180):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def expected_gen(root, ref):
    """What `gen.py` produces on *ref*'s a.txt and b.txt, run in a scratch directory."""
    scratch = TMP / f"expect-{secrets.token_hex(3)}"
    scratch.mkdir()
    for name in ("gen.py", "a.txt", "b.txt"):
        (scratch / name).write_text(git(root, "show", f"{ref}:{name}") + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "-I", "gen.py"], cwd=scratch, check=True)
    return (scratch / "gen.txt").read_text(encoding="utf-8").strip()


def seed(root):
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    (root / "gen.py").write_text(GEN_PY, encoding="utf-8")
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "b.txt").write_text("beta\n", encoding="utf-8")
    subprocess.run([sys.executable, "-I", "gen.py"], cwd=root, check=True)
    git(root, "add", ".gitignore", "gen.py", "a.txt", "b.txt", "gen.txt")
    git(root, "commit", "-q", "-m", "seed: gen.txt is generated from a.txt and b.txt")
    return git(root, "rev-parse", "HEAD")


def payload():
    def task(key, req, source):
        return {"key": key, "title": f"Change {source}", "requirements": [req],
                "files": [source, "gen.txt"],
                "description": f"Change {source}, run `python gen.py`, commit both.",
                "builder": BUILDER, "reviewer": CHECKER}

    return {
        "schema_version": 1, "kind": "change-spec", "title": TITLE,
        "summary": "Two inputs of one generated file change in parallel.",
        "problem": "Drive the generated-files rebuild at landing.",
        "scope": {"in_scope": ["a.txt", "b.txt", "gen.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": k, "modal": "MUST", "statement": f"{k}.txt MUST change."}
                         for k in ("a", "b")],
        "acceptance_criteria": [{"key": f"has-{k}", "requirement": k, "given": "the repository",
                                 "when": "read", "then": f"{k}.txt changed",
                                 "how_to_check": f"cat {k}.txt", "checked_by": "agent"}
                                for k in ("a", "b")],
        "tasks": [task("ta", "a", "a.txt"), task("tb", "b", "b.txt")],
        "delivery": {"mode": "flow", "agent": BUILDER, "builders": [BUILDER], "level": "reviewed",
                     "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
                     "reasons": {"mode": "Two tasks.", "agent": "Default."}},
    }


def worktree(root, task_id, base):
    """The task's checkout at *base*, on the branch the Hub uses; or the one the Hub cut already."""
    path = root / ".agentweave" / "tasks" / task_id
    branch = f"agentweave/task/{task_id}"
    if not path.exists():
        try:
            git(root, "worktree", "add", "-q", "-b", branch, str(path), base)
        except RuntimeError:
            # The Hub provisioned it first (a turn the flow started, failed by the stub).
            if not poll(lambda: (path / "gen.py").exists(), 60):
                raise
    return path


def landing(base, task_id):
    _, out = api("GET", f"{base}/tasks/{task_id}/checks")
    return (out or {}).get("landing") or {} if isinstance(out, dict) else {}


def task_row(base, task_id):
    return api("GET", f"{base}/tasks/{task_id}")[1] or {}


def approve(base, key, task_id):
    """completed -> under_review -> approved, as the operator, waiting out the stub's failed turns."""
    api("PATCH", f"{base}/tasks/{task_id}", {"status": "under_review"})

    def unfinished(out):
        detail = out.get("detail") if isinstance(out, dict) else None
        return isinstance(detail, dict) and bool(detail.get("unfinished"))

    end = time.time() + 240
    code, out = api("PATCH", f"{base}/tasks/{task_id}", {"status": "approved"})
    while code == 409 and unfinished(out) and time.time() < end:
        time.sleep(5)
        code, out = api("PATCH", f"{base}/tasks/{task_id}", {"status": "approved"})
    detail = out.get("detail") if isinstance(out, dict) else None
    unmergeable = [e.get("paths") for e in (detail or {}).get("unmergeable") or []] if isinstance(
        detail, dict) else []
    # On master before the build, the approval gate (requirement_gate._check_mergeable) refuses the
    # second task because its evidenced commit conflicts with main in gen.txt; a reviewer then has
    # only the merge-needed send-back left. The build must get past this gate as well.
    check(f"{key}: approved (the approval gate does not refuse a generated-only conflict)",
          code == 200, f"{code}; unmergeable paths {unmergeable}; {str(out)[:400]}")
    return code == 200


def settle(base, key, task_id):
    """Wait until the task's work landed or the task was sent back; say which."""
    def done():
        row = task_row(base, task_id)
        land = landing(base, task_id)
        if land.get("state") == "landed":
            return ("landed", row, land)
        if row.get("status") in ("revision_needed", "rejected") or land.get("state") in (
                "sent_back", "not_landed"):
            return ("sent_back", row, land)
        return None

    out = poll(done, LAND_WAIT, 5)
    if out is None:
        row, land = task_row(base, task_id), landing(base, task_id)
        return "timeout", row, land
    return out


def drive(state):
    root = TMP / "proj"
    seed_sha = seed(root)
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"gendrive-{STAMP}"})
    check("setup: the fixture project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state["base"] = base
    api("PATCH", base, {"main_branch": "main"})
    code, out = api("PUT", f"{base}/settings", {"allow_agent_jobs": True})
    check("setup: agent jobs allowed", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    generated = {"paths": ["gen.txt"], "command": python_command(), "timeout_seconds": 60}
    code, out = api("PUT", f"{base}/settings", {"generated_files": generated})
    saved = out.get("generated_files") if isinstance(out, dict) else None
    check("setup: the operator declares gen.txt generated, rebuilt by `python gen.py`",
          code == 200 and (saved or {}).get("paths") == ["gen.txt"], f"{code} {str(out)[:400]}")
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    check("setup: a runner", code in (200, 201), f"{code} {runner}", fatal=True)
    for name in (BUILDER, CHECKER):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": TITLE, "kind": "change-spec", "path": DOC})
    check("setup: document created", code == 201, f"{code} {out}", fatal=True)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    check("setup: document saved", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    minted = (out or {}).get("identifiers") or {}
    ids = {"ta": minted.get("a"), "tb": minted.get("b")}
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True,
                     "content_version": read.get("content_version")})
    check("setup: document approved", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builders": [BUILDER],
                     "landing": "main"})
    check("setup: built, landing on main", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    state["build_id"] = build_id
    _, tasks = api("GET", f"{base}/tasks?limit=200")
    rows = tasks["tasks"] if isinstance(tasks, dict) else tasks
    tasks = {t["spec_task_key"]: t["id"] for t in rows if t.get("build_id") == build_id}
    check("setup: the build carries ta and tb", set(tasks) == {"ta", "tb"}, str(sorted(tasks)),
          fatal=True)
    print(f"project {pid} root {root} tasks {tasks}", flush=True)

    # The builders' part: both branches cut from the same main commit, each changing one input and
    # committing its own rebuilt gen.txt.
    heads = {}
    for key, source, word in (("ta", "a.txt", "apple"), ("tb", "b.txt", "banana")):
        wt = worktree(root, tasks[key], seed_sha)
        check(f"{key}: its checkout starts at the seed commit",
              git(wt, "rev-parse", "HEAD") == seed_sha, git(wt, "log", "--oneline", "-3"),
              fatal=True)
        (wt / source).write_text(f"{word}\n", encoding="utf-8")
        subprocess.run([sys.executable, "-I", "gen.py"], cwd=wt, check=True)

        def commit(wt=wt, source=source, key=key):
            # The Hub may be running git in the same worktree; its index.lock refuses ours.
            try:
                git(wt, "add", source, "gen.txt")
                git(wt, "commit", "-q", "-m", f"drive: {key} changes {source}, gen.txt rebuilt")
                return True
            except RuntimeError as exc:
                if "index.lock" not in str(exc):
                    raise
                return False

        check(f"{key}: {source} and its rebuilt gen.txt committed", poll(commit, 120, 3),
              fatal=True)
        heads[key] = git(wt, "rev-parse", "HEAD")
    clash = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", heads["ta"],
                            heads["tb"]], cwd=root, capture_output=True, text=True)
    # --name-only: the tree on the first line, then each conflicted path, then a blank line.
    conflicted = set(clash.stdout.split("\n\n")[0].splitlines()[1:])
    check("fixture: the two branches conflict in gen.txt alone",
          clash.returncode == 1 and conflicted == {"gen.txt"}, clash.stdout.strip()[:300],
          fatal=True)

    for key in ("ta", "tb"):
        # The flow may not have claimed it yet: walk it to completed as the builder's turn would.
        status = task_row(base, tasks[key]).get("status")
        if status == "pending":
            api("PATCH", f"{base}/tasks/{tasks[key]}", {"status": "assigned", "assignee": BUILDER})
            status = task_row(base, tasks[key]).get("status")
        if status == "assigned":
            api("PATCH", f"{base}/tasks/{tasks[key]}", {"status": "in_progress"})
        code, out = api("PATCH", f"{base}/tasks/{tasks[key]}", {"status": "completed"})
        check(f"{key}: completed", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        code, out = api("POST", f"{base}/project/spec/evidence",
                        {"identifier": ids[key], "document": DOC, "task_id": tasks[key],
                         "kind": "manual_observation", "commit": heads[key], "covers": "full",
                         "summary": f"drive: {key} changed its input and rebuilt gen.txt"})
        check(f"{key}: evidence recorded and accepted at {heads[key][:8]}",
              code == 201 and (out or {}).get("review_state") == "accepted",
              f"{code} {str(out)[:300]}", fatal=True)

    # Land one after the other: the first lands cleanly, the second meets the gen.txt conflict.
    outcomes = {}
    for key in ("ta", "tb"):
        if not approve(base, key, tasks[key]):
            outcomes[key] = "refused"
            continue
        outcome, row, land = settle(base, key, tasks[key])
        outcomes[key] = outcome
        check(f"{key}: lands and is not sent back", outcome == "landed",
              f"{outcome}; status {row.get('status')}; landing {json.dumps(land)[:600]}; "
              f"notes {str(row.get('notes'))[:600]}")
        if outcome == "landed":
            regenerated = land.get("regenerated")
            if key == "tb":
                check("tb: its landing record names the rebuilt gen.txt and a duration",
                      isinstance(regenerated, dict) and "gen.txt" in (regenerated.get("paths") or [])
                      and isinstance(regenerated.get("seconds"), (int, float)),
                      f"regenerated {regenerated}")

    main = git(root, "rev-parse", "main")
    on_main = git(root, "show", "main:gen.txt")
    expected = expected_gen(root, "main")
    check("main: a.txt and b.txt carry both tasks' changes",
          git(root, "show", "main:a.txt") == "apple" and git(root, "show", "main:b.txt") == "banana",
          f"a={git(root, 'show', 'main:a.txt')!r} b={git(root, 'show', 'main:b.txt')!r}")
    check("main: gen.txt equals what `python gen.py` produces on main's a.txt and b.txt",
          on_main == expected, f"main {main[:8]} gen.txt {on_main!r}; expected {expected!r}")
    log = git(root, "log", "--format=%s", f"{seed_sha}..main")
    check(f"main: a merge commit's message ends {SUFFIX!r}",
          any(line.endswith(SUFFIX) for line in log.splitlines()), log[:600])
    check("neither task was sent back", all(o == "landed" for o in outcomes.values()), str(outcomes))


def main():
    proc = start_hub()
    state = {}
    try:
        drive(state)
    except Stop:
        pass
    finally:
        if not os.environ.get("AW_DRIVE_KEEP"):
            if state.get("build_id"):
                api("POST", f"{state['base']}/project/builds/{state['build_id']}/stop")
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
