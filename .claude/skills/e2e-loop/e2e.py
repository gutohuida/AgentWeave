"""Drive AgentWeave from outside the UI, the way an operator does.

The harness behind the `e2e-loop` skill — read `SKILL.md` beside this file for the method; this
is only the mechanism. Everything goes through the Hub's real HTTP surface with real credentials.
**Nothing is simulated: if a step has no API, that is a finding, not something to work around.**
The only database access is read-only (`mode=ro`) — rows are evidence, never a way in.

It drives a Hub it started itself, on its own profile and port. Never :8000 (the operator's real
instance). The current Hub is remembered in ~/.agentweave/e2e-current.json so each command —
every shell call is a fresh process — finds it without re-exporting anything.

Usage (always `py -3.11`, never bare `python`):
    hub-up <profile> <port>                        start a Hub from source on a fresh profile
    hub-down                                       stop the Hub hub-up started (by its exact PID)
    setup <project-name>                           git repo under ~/Documents, opened as a project
    agent <project> <name> <charter-substr|-> <cli> [model]
    doc-new <project> [title]
    turn <project> <agent> <message> [--doc PATH] [--task ID] [--perm MODE] [--fresh]
    watch <run-id> [minutes]
    answer <project> <agent> [choice]
    close|propose <project> <path>
    phase <project> <path> <to> [reason] [--anyway]  --anyway approves over approval_warnings
    tasks <project>
    task-set <project> <task-id> <status>
    api <METHOD> <path> [json-body | @file]        any route; prints status and body, never raises.
                                                   @file sends the file's raw bytes (PDF/PNG/JPEG/...)
    manager <project> [<job-key> on|off [runner-id|-] [model]]   list or set the Hub's own model jobs
    vault <project> map | read <entry-id> | contradictions | reports | settings
    vault <project> add <name> <type> <text|@file> [--private] [--dated YYYY-MM-DD]
    vault <project> file <path> [type] [--private] [--dated YYYY-MM-DD]
    ro "<sql>"                                     read-only query against the Hub's database
    state <project>
    clean <project>                                archive jobs, disable manager jobs, delete the
                                                   project, remove its dir and its private vault
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = pathlib.Path.home()
# AW_E2E_STATE lets parallel sweeps each keep their own Hub record.
STATE = pathlib.Path(os.environ.get("AW_E2E_STATE") or HOME / ".agentweave" / "e2e-current.json")
PROFILES = HOME / ".agentweave" / "hub" / "profiles"
#: The checkout the Hub runs from. Override with AW_REPO_ROOT.
REPO = pathlib.Path(os.environ.get("AW_REPO_ROOT") or HOME / "Documents" / "projects" / "AgentWeave")
#: Test projects live here — never inside the repository.
PROJECTS = pathlib.Path(os.environ.get("AW_E2E_ROOT") or HOME / "Documents")
PY311 = os.environ.get("AW_PY311") or str(
    HOME / "AppData" / "Local" / "Programs" / "Python" / "Python311" / "python.exe"
)


def _state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def hub():
    url = os.environ.get("AW_HUB") or _state().get("hub")
    if not url:
        raise SystemExit("No Hub. Run `hub-up <profile> <port>` or set AW_HUB.")
    if url.rstrip("/").endswith(":8000"):
        raise SystemExit(":8000 is the operator's real instance. Never drive it.")
    return url.rstrip("/")


def db():
    path = os.environ.get("AW_HUB_DB") or _state().get("db")
    if not path:
        raise SystemExit("No database path. Run `hub-up` or set AW_HUB_DB.")
    return path


_KEY = None


def key():
    """AW_KEY if set, else the loopback-only /setup/token — how a fresh profile hands one out."""
    global _KEY
    if _KEY is None:
        _KEY = os.environ.get("AW_KEY")
        if not _KEY:
            with urllib.request.urlopen(hub() + "/api/v1/setup/token", timeout=10) as r:
                _KEY = json.loads(r.read())["api_key"]
    return _KEY


def request(method, path, body=None, timeout=60, raw=None, content_type=None):
    """Returns (status, parsed body). Never raises on an HTTP error: a refusal is a result."""
    # Git Bash rewrites a `/projects/...` argument into `C:/Program Files/Git/projects/...`.
    # Undo it rather than send a path the Hub was never asked for.
    mangled = re.match(r"^[A-Za-z]:/.*?/Git(/.*)$", path)
    if mangled:
        path = mangled.group(1)
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/api/") and path != "/health":
        path = "/api/v1" + path
    req = urllib.request.Request(hub() + path, method=method)
    req.add_header("Authorization", f"Bearer {key()}")
    data = None
    if raw is not None:
        data = raw
        req.add_header("Content-Type", content_type or "application/octet-stream")
    elif body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def call(method, path, body=None):
    """Like `request`, but a non-2xx is fatal to the step — use it for setup, not for probes."""
    status, parsed = request(method, path, body)
    if status >= 300:
        print(f"  !! {method} {path} -> {status}: {json.dumps(parsed)[:600]}")
        raise RuntimeError(f"{status}: {parsed}")
    return parsed


def ro():
    c = sqlite3.connect(f"file:{db()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


# ---------------------------------------------------------------------------
# Hub lifecycle


def cmd_hub_up(profile, port):
    if str(port) in ("8000", "8010"):
        raise SystemExit("8000 is the operator's and 8010 is the trial Hub. Pick a free port.")
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=1).close()
    except OSError:
        pass
    else:
        raise SystemExit(
            f"Something already listens on :{port}. Its /health would answer for a Hub this "
            "command did not start; pick another port or stop it first."
        )
    path = PROFILES / profile / "agentweave.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # A forward-slash C:/ path. A /c/Users form silently creates a stray database elsewhere.
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(path).replace("\\", "/")
    log = pathlib.Path(os.environ.get("TEMP", str(HOME))) / f"agentweave-hub-{port}.log"
    flags = 0
    if os.name == "nt":
        # Detached and out of the caller's job object, so the Hub outlives this shell call.
        flags = 0x00000008 | 0x00000200 | 0x01000000
    cmd = [PY311, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", str(port)]
    with open(log, "ab") as out:
        try:
            proc = subprocess.Popen(
                cmd, cwd=REPO / "hub", env=env, stdout=out, stderr=out, creationflags=flags
            )
        except OSError:
            proc = subprocess.Popen(
                cmd, cwd=REPO / "hub", env=env, stdout=out, stderr=out,
                creationflags=flags & ~0x01000000,
            )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                health = json.loads(r.read())
                break
        except (OSError, ValueError):
            time.sleep(1)
    else:
        raise SystemExit(f"Hub did not come up; read {log}")
    STATE.write_text(
        json.dumps({"hub": url, "db": str(path), "pid": proc.pid, "port": port, "log": str(log)}),
        encoding="utf-8",
    )
    print("HUB=" + url)
    print("DB=" + str(path))
    print("PID=" + str(proc.pid), "LOG=" + str(log))
    print("health:", health)
    if health.get("ui_stale"):
        print("  !! ui_stale: the served dashboard is older than hub/ui/src — UI findings are void")


def cmd_hub_down():
    st = _state()
    pid = st.get("pid")
    if not pid:
        raise SystemExit("No Hub recorded by hub-up.")
    # Kill this exact PID and its children. Never a blanket python kill: :8000 is python too.
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print("stopped", pid, "on", st.get("hub"))


# ---------------------------------------------------------------------------
# Setup


def cmd_setup(name):
    d = PROJECTS / name
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "README.md").exists():
        (d / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    if not (d / ".git").is_dir():
        for args in (
            ["init", "-q", "-b", "master"],
            ["add", "-A"],
            ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        ):
            subprocess.run(["git", "-C", str(d), *args])
    project = call("POST", "/projects/open", {"path": str(d)})["id"]
    print("PROJECT=" + project)
    print("DIR=" + str(d))
    return project


def cmd_agent(project, name, charter_sub, cli, model=None):
    """Find-or-create a runner, then create the agent through the operator route."""
    runners = call("GET", f"/projects/{project}/runners")
    match = [r for r in runners if r["cli"] == cli and (model is None or r.get("model") == model)]
    runner = match[0] if match else call(
        "POST",
        f"/projects/{project}/runners",
        {"name": f"{cli} {model or 'default'} (e2e)", "cli": cli, "model": model},
    )
    charter = None
    if charter_sub != "-":
        charters = call("GET", f"/projects/{project}/charters")
        charter = next((c for c in charters if charter_sub.lower() in c["name"].lower()), None)
    body = {"name": name, "runner_id": runner["id"]}
    if charter:
        body["charter_id"] = charter["id"]
    status, res = request("POST", f"/projects/{project}/agents", body)
    if status == 409:
        patch = {"runner_id": runner["id"]}
        if charter:
            patch["charter_id"] = charter["id"]
        call("PATCH", f"/projects/{project}/agents/{name}", patch)
    elif status >= 300:
        raise SystemExit(f"agent create -> {status}: {res}")
    print(
        f"agent {name}: runner={runner['name']} ({runner['cli']}/{runner.get('model')}) "
        f"charter={charter['name'] if charter else None}"
    )


def cmd_doc_new(project, title=""):
    doc = call("POST", f"/projects/{project}/project/documents", {"title": title} if title else {})
    print("DOC=" + doc["path"])
    print("  title:", repr(doc.get("title")), "phase:", doc.get("phase"))
    return doc["path"]


# ---------------------------------------------------------------------------
# Turns


def latest_conversation(project, agent):
    row = ro().execute(
        # Open ones only: the trigger refuses an archived conversation with 409. `sequence`, not
        # `created_at`: two conversations created in one Windows clock tick tie on the timestamp.
        "select id from conversations where project_id=? and agent=? and lifecycle='open' "
        "order by sequence desc limit 1",
        (project, agent),
    ).fetchone()
    return row["id"] if row else None


def cmd_turn(project, agent, message, doc=None, task=None, fresh=False, perm=None):
    body = {"agent": agent, "message": message}
    if perm:
        body["overrides"] = {"permission_mode": perm}
    if doc:
        body["spec_document"] = doc
    if task:
        body["task_id"] = task
    if not fresh:
        conversation = latest_conversation(project, agent)
        if conversation:
            body["conversation_id"] = conversation
    status, res = request("POST", f"/projects/{project}/agent/trigger", body)
    print(f"HTTP {status}")
    if status >= 300:
        print(json.dumps(res, indent=2)[:1500])
        return None
    print("RUN=" + str(res.get("run_id")))
    print("  status:", res.get("status"), res.get("waiting_reason") or "")
    return res.get("run_id")


def wait_for(run_id, minutes=15):
    deadline = time.time() + float(minutes) * 60
    while time.time() < deadline:
        st = ro().execute("select status from runs where id=?", (run_id,)).fetchone()
        if st and st["status"] not in ("running", "queued", "starting", "pending"):
            return st["status"]
        time.sleep(6)
    return "still-running"


def dump_turn(run_id, tools=True):
    c = ro()
    st = c.execute("select status, error, agent from runs where id=?", (run_id,)).fetchone()
    if not st:
        print("no such run", run_id)
        return
    print(f"\n=== {run_id} [{st['agent']}] :: {st['status']}", end="")
    print(f" :: {st['error']}" if st["error"] else "", "===")
    # `sequence` restarts every run, so order by timestamp first.
    for row in c.execute(
        "select kind, content from agent_outputs where run_id=? order by timestamp, sequence, id",
        (run_id,),
    ):
        body = (row["content"] or "").strip()
        if row["kind"] == "text":
            print(f"\n[TEXT]\n{body}")
        elif tools:
            print(f"[{row['kind']}] {body[:300]}")


def cmd_watch(run_id, minutes=15):
    print("status:", wait_for(run_id, minutes))
    dump_turn(run_id)


def cmd_answer(project, agent, choice=None):
    rows = call("GET", f"/projects/{project}/questions?answered=false")
    pending = [q for q in rows if q["from_agent"] == agent and not q.get("declined")]
    for q in sorted(pending, key=lambda x: x.get("batch_index") or 0):
        labels = [o["label"] for o in (q.get("options") or [])]
        pick = choice or (labels[0] if labels else "You decide")
        call(
            "PATCH",
            f"/projects/{project}/questions/{q['id']}",
            {"answer": pick, "labels": [pick] if labels else []},
        )
        print(f"  answered: {q['question'][:80]} -> {pick}")
    print("answered:", len(pending))


# ---------------------------------------------------------------------------
# Spec phase control


def _doc_route(project, action, path, extra=""):
    return (
        f"/projects/{project}/project/documents/{action}"
        f"?path={urllib.parse.quote(path)}{extra}"
    )


def cmd_close(project, path):
    print(json.dumps(request("POST", _doc_route(project, "close-exploration", path)), indent=2))


def cmd_propose(project, path):
    print(json.dumps(request("POST", _doc_route(project, "propose", path)), indent=2)[:2500])


def cmd_phase(project, path, to, reason="", anyway=False):
    body = {"reason": reason}
    if anyway:
        # Approval answers 409 `approval_warnings` listing the gaps; this is the operator's
        # "Approve anyway". A document written in one PUT always warns steps_skipped (F574).
        body["approve_anyway"] = True
    res = request("POST", _doc_route(project, "phase", path, f"&to={to}"), body)
    print(json.dumps(res, indent=2)[:1500])


# ---------------------------------------------------------------------------
# Tasks, probes and state


def cmd_tasks(project):
    page = call("GET", f"/projects/{project}/tasks?limit=500")
    rows = page["tasks"] if isinstance(page, dict) else page
    if isinstance(page, dict) and page.get("has_more"):
        print(f"  (showing {len(rows)} of {page.get('total')})")
    if not rows:
        print("(no tasks)")
    for t in rows:
        print(f"  {t['id']}  {t['status']:<15} {t.get('assignee') or '-':<12} {t['title'][:60]}")
    return rows


def cmd_task_set(project, task_id, status_value):
    status, res = request("PATCH", f"/projects/{project}/tasks/{task_id}", {"status": status_value})
    print(f"HTTP {status}:", res.get("status") if isinstance(res, dict) and status < 300 else res)


MEDIA = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".json": "application/json",  # a JSON body too large to quote on the command line
}


def _raw(arg):
    """`@file` -> (bytes, media type); None for an inline JSON argument. A `.json` file goes as
    `application/json`, so the Hub parses it as a body rather than refusing raw bytes (422)."""
    if not (arg and arg.startswith("@")):
        return None
    f = pathlib.Path(arg[1:])
    return f.read_bytes(), MEDIA.get(f.suffix.lower(), "application/octet-stream")


def cmd_api(method, path, body=None):
    raw = _raw(body)
    if raw:
        status, res = request(method.upper(), path, raw=raw[0], content_type=raw[1])
    else:
        status, res = request(method.upper(), path, json.loads(body) if body else None)
    print(f"HTTP {status}")
    print(json.dumps(res, indent=2, ensure_ascii=False)[:6000])


def cmd_ro(sql):
    for row in ro().execute(sql):
        print(dict(row))


def cmd_state(project):
    c = ro()
    print("--- documents ---")
    for r in c.execute(
        "select path, title, phase from spec_documents where project_id=?", (project,)
    ):
        print(f"  {r['phase']:<10} {r['path']}  ({(r['title'] or '')[:50]})")
    print("--- document events ---")
    for r in c.execute(
        "select kind, actor_kind, actor, created_at from spec_document_events "
        "where project_id=? order by created_at",
        (project,),
    ):
        print(f"  {str(r['created_at'])[:19]}  {r['kind']:<10} {r['actor_kind']}/{r['actor']}")
    print("--- runs ---")
    for r in c.execute(
        "select id, agent, status, error from runs where project_id=? order by started_at",
        (project,),
    ):
        print(f"  {r['id']}  {r['agent']:<12} {r['status']}  {(r['error'] or '')[:60]}")
    print("--- jobs (enabled ones cost money) ---")
    for j in call("GET", f"/projects/{project}/jobs?include_archived=true"):
        print(f"  {j['id']}  enabled={j.get('enabled')}  archived={j.get('archived_at') is not None}")
    print("--- manager jobs (enabled ones cost money on every upload, proposal and turn) ---")
    status, jobs = request("GET", f"/projects/{project}/manager/jobs")
    for j in _job_list(jobs) if status < 300 else []:
        print(f"  {j.get('key'):<20} enabled={j.get('enabled')}  runner={j.get('runner_id')}")
    print("--- tasks ---")
    cmd_tasks(project)


# ---------------------------------------------------------------------------
# The Hub's own model work (manager jobs) and the knowledge vault


def _job_list(jobs):
    if isinstance(jobs, dict):
        return jobs.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def cmd_manager(project, key=None, onoff=None, runner="-", model=None):
    """No key: list. Otherwise PATCH /manager/jobs/{key} and print whatever it answers. The vault
    jobs need a runner of their own; conversation-titles borrows the conversation agent's."""
    if key is None:
        for j in _job_list(call("GET", f"/projects/{project}/manager/jobs")):
            print(
                f"  {j.get('key'):<20} enabled={j.get('enabled')}  runner={j.get('runner_id')}"
                f"  model={j.get('model')}"
            )
        return
    body = {"enabled": onoff == "on"}
    if runner and runner != "-":
        body["runner_id"] = runner
    if model:
        body["model"] = model
    status, res = request("PATCH", f"/projects/{project}/manager/jobs/{key}", body)
    print(f"HTTP {status}")
    print(json.dumps(res, indent=2, ensure_ascii=False)[:1500])


def _flags(args, *names):
    """Pull `--private` and `--<name> value` flags out of an argument list."""
    rest, out, i = [], {}, 0
    while i < len(args):
        flag = args[i][2:] if args[i].startswith("--") else None
        if flag == "private":
            out["private"], i = True, i + 1
        elif flag in names:
            out[flag], i = args[i + 1], i + 2
        else:
            rest.append(args[i])
            i += 1
    return rest, out


def cmd_vault(project, sub, *args):
    base = f"/projects/{project}/vault"
    args, opts = _flags(list(args), "dated")
    visibility = "private" if opts.get("private") else None
    if sub == "map":
        for e in call("GET", base + "/map").get("entries", []):
            marks = " ".join(k for k in ("disputed", "presumed") if e.get(k))
            if e.get("superseded_by"):
                marks += f" superseded_by={e['superseded_by']}"
            if e.get("available") is False:
                # No holder: a file this Hub has not read yet (or could not), not another machine.
                marks += f" held-by={e['holder']}" if e.get("holder") else " text-not-yet-read"
            name = e.get("name") or (e.get("claim") or e.get("opening") or "")[:60]
            print(
                f"  {e['id']:<18} {e['kind']:<6} {e.get('type') or '':<10} "
                f"{e.get('visibility') or '':<8} fetches={e.get('fetches', 0):<3} {name} {marks}"
            )
        return
    if sub in ("contradictions", "reports", "settings"):
        status, res = request("GET", f"{base}/{sub}")
    elif sub == "read":
        status, res = request("GET", f"{base}/entries/{args[0]}")
    elif sub == "add":
        name, type_, text = args[0], args[1], args[2]
        if text.startswith("@"):
            text = pathlib.Path(text[1:]).read_text(encoding="utf-8")
        body = {"name": name, "type": type_, "content": text}
        if visibility:
            body["visibility"] = visibility
        if opts.get("dated"):
            body["dated"] = opts["dated"]
        status, res = request("POST", base + "/sources", body)
    elif sub == "file":
        f = pathlib.Path(args[0])
        query = {"name": f.name, "type": args[1] if len(args) > 1 else "document"}
        if visibility:
            query["visibility"] = visibility
        if opts.get("dated"):
            query["dated"] = opts["dated"]
        status, res = request(
            "POST",
            base + "/files?" + urllib.parse.urlencode(query),
            raw=f.read_bytes(),
            content_type=MEDIA.get(f.suffix.lower(), "application/octet-stream"),
        )
    else:
        raise SystemExit(f"unknown vault subcommand {sub!r}; see the usage")
    print(f"HTTP {status}")
    print(json.dumps(res, indent=2, ensure_ascii=False)[:6000])


def _rmtree(path):
    """Git marks .git/objects read-only on Windows; clear the bit and retry, and say so honestly
    when the tree survives rather than printing "removed" over it."""

    def force(func, target, _exc):
        os.chmod(target, 0o700)
        func(target)

    if not os.path.exists(path):
        return
    try:
        shutil.rmtree(path, onerror=force)
    except OSError as exc:
        print(f"  !! could not remove {path}: {exc}")
        return
    if os.path.exists(path):
        print(f"  !! {path} still exists after rmtree")


def cmd_clean(project):
    """Archive every job first (a live cron keeps spending), then delete through the API."""
    status, proj = request("GET", f"/projects/{project}")
    directory = proj.get("working_directory") if isinstance(proj, dict) else None
    for j in call("GET", f"/projects/{project}/jobs"):
        s, _ = request("POST", f"/projects/{project}/jobs/{j['id']}/archive")
        print(f"  archived job {j['id']}: HTTP {s}")
    s, vs = request("GET", f"/projects/{project}/vault/settings")
    private = vs.get("effective_private_location") if s < 300 and isinstance(vs, dict) else None
    s, jobs = request("GET", f"/projects/{project}/manager/jobs")
    for j in _job_list(jobs) if s < 300 else []:
        if j.get("enabled"):
            s2, _ = request(
                "PATCH", f"/projects/{project}/manager/jobs/{j['key']}", {"enabled": False}
            )
            print(f"  disabled manager job {j['key']}: HTTP {s2}")
    s, res = request("DELETE", f"/projects/{project}")
    print(f"  DELETE project: HTTP {s} {res if s >= 300 else ''}")
    # Strictly beneath PROJECTS: a project opened on ~/Documents itself (F685) must not take it.
    if directory and pathlib.Path(directory).resolve() in (PROJECTS.resolve(), *PROJECTS.resolve().parents):
        print(f"  left {directory} in place: it is {PROJECTS} or above it")
    elif directory and pathlib.Path(directory).resolve().is_relative_to(PROJECTS.resolve()):
        _rmtree(directory)
    elif directory:
        print(f"  left {directory} in place: not under {PROJECTS}")
    # F592: deleting a project leaves its private vault behind. Say so, then remove it -- only
    # inside the Hub's own vaults directory, never a custom location the drive chose.
    vaults = HOME / ".agentweave" / "hub" / "vaults"
    if private and pathlib.Path(private).exists():
        if pathlib.Path(private).resolve().is_relative_to(vaults.resolve()) and pathlib.Path(private).resolve() != vaults.resolve():
            print(f"  F592: the Hub left {private} behind; removing it")
            _rmtree(private)
        else:
            print(f"  !! private vault left at {private} (custom location; remove it yourself)")
    print("removed", project)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(0)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "phase":
        cmd_phase(*[a for a in args if a != "--anyway"], anyway="--anyway" in args)
    elif cmd == "turn":
        opts = {"doc": None, "task": None, "perm": None}
        rest, fresh, i = [], False, 0
        while i < len(args):
            flag = args[i].lstrip("-")
            if args[i].startswith("--") and flag in opts:
                opts[flag] = args[i + 1]
                i += 2
            elif args[i] == "--fresh":
                fresh, i = True, i + 1
            else:
                rest.append(args[i])
                i += 1
        cmd_turn(rest[0], rest[1], rest[2], fresh=fresh, **opts)
    else:
        table = {
            "hub-up": cmd_hub_up, "hub-down": cmd_hub_down, "setup": cmd_setup,
            "agent": cmd_agent, "doc-new": cmd_doc_new, "watch": cmd_watch,
            "answer": cmd_answer, "close": cmd_close, "propose": cmd_propose,
            "tasks": cmd_tasks, "task-set": cmd_task_set,
            "api": cmd_api, "ro": cmd_ro, "state": cmd_state, "clean": cmd_clean,
            "manager": cmd_manager, "vault": cmd_vault,
        }
        if cmd not in table:
            print(__doc__)
            raise SystemExit(1)
        table[cmd](*args)
