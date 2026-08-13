"""Drive AgentWeave from outside the UI, the way an operator does.

The harness behind the `e2e-loop` skill — read `SKILL.md` beside this file for the method; this
is only the mechanism. It is a test *instrument*, not part of the product, and nothing in the
product imports it.

Everything goes through the Hub's real HTTP surface with real credentials. **Nothing is
simulated: if a step has no API, that is a finding, not something to work around.** The first run
of this harness found ten defects that 1693 passing unit tests could not, because all of them
lived between two features rather than inside one.

Test projects are created outside the repository. A project at the repo root would give this
repository an AgentWeave session, which `CLAUDE.md` forbids.

Usage:
    python e2e.py setup <project-name>
    python e2e.py agent <project> <name> <charter-substring> <cli> [model]
    python e2e.py doc-new <project> [title]
    python e2e.py turn <project> <agent> <message> [--doc PATH] [--task TASK_ID]
    python e2e.py watch <run-id> [minutes]
    python e2e.py answer <project> <agent> [choice]
    python e2e.py state <project>
    python e2e.py close|propose <project> <path>
    python e2e.py phase <project> <path> <to>
    python e2e.py tasks <project>
    python e2e.py task-set <project> <task-id> <status>
    python e2e.py clean <project>
"""

from __future__ import annotations

import json
import urllib.parse
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The repository root, derived from this file's location rather than written down, so the
# harness moves with the skill instead of pinning one machine.
ROOT = os.environ.get("AW_REPO_ROOT") or str(pathlib.Path(__file__).resolve().parents[3])
DB = os.environ.get("AW_HUB_DB") or os.path.join(ROOT, "hub", "data", "agentweave.db")
BASE = os.environ.get("AW_HUB_URL", "http://127.0.0.1:8010")

#: Where test projects are created. Never inside the repository — a project at the repo root
#: would give this repo an AgentWeave session, which CLAUDE.md forbids.
PROJECTS = os.environ.get("AW_E2E_ROOT") or str(pathlib.Path.home() / "Documents")
KEY = (
    re.search(r"AW_BOOTSTRAP_API_KEY=(.+)", open(os.path.join(ROOT, "hub", ".env")).read())
    .group(1)
    .strip()
)


def call(method, path, body=None, token=None, quiet=False):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", f"Bearer {token or KEY}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        if not quiet:
            print(f"  !! {method} {path} -> {exc.code}: {payload[:400]}")
        raise RuntimeError(f"{exc.code}: {payload}") from exc


def unwrap(result):
    return result["value"] if isinstance(result, dict) and "value" in result else result


def ro():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


# ---------------------------------------------------------------------------
# Setup


def cmd_setup(name):
    d = os.path.join(PROJECTS, name)
    os.makedirs(d, exist_ok=True)
    if not os.path.exists(os.path.join(d, "README.md")):
        open(os.path.join(d, "README.md"), "w").write(f"# {name}\n")
    if not os.path.isdir(os.path.join(d, ".git")):
        for cmd in ("init -q", "add -A", "-c user.name=t -c user.email=t@t commit -q -m init"):
            subprocess.run(f'git -C "{d}" {cmd}', shell=True)
    project = call("POST", "/api/v1/projects/open", {"path": d})["id"]
    print("PROJECT=" + project)
    print("DIR=" + d)
    return project


def cmd_agent(project, name, charter_sub, cli, model=None):
    runners = unwrap(call("GET", f"/api/v1/projects/{project}/runners"))
    match = [r for r in runners if r["cli"] == cli and (model is None or r.get("model") == model)]
    if not match:
        created = call(
            "POST",
            f"/api/v1/projects/{project}/runners",
            {"name": f"{cli} {model or 'default'} (e2e)", "cli": cli, "model": model},
        )
        match = [created]
    runner = match[0]

    charters = unwrap(call("GET", f"/api/v1/projects/{project}/charters"))
    charter = next((c for c in charters if charter_sub.lower() in c["name"].lower()), None)

    try:
        call(
            "POST",
            f"/api/v1/projects/{project}/agents/register",
            {"name": name, "contact_mode": "poll"},
            quiet=True,
        )
    except RuntimeError:
        pass
    patch = {"runner_id": runner["id"]}
    if charter:
        patch["charter_id"] = charter["id"]
    call("PATCH", f"/api/v1/projects/{project}/agents/{name}", patch)
    print(
        f"agent {name}: runner={runner['name']} ({runner['cli']}/{runner.get('model')}) "
        f"charter={charter['name'] if charter else None}"
    )


def cmd_doc_new(project, title=""):
    body = {"title": title} if title else {}
    doc = call("POST", f"/api/v1/projects/{project}/project/documents", body)
    print("DOC=" + doc["path"])
    print("  title:", repr(doc["title"]), "phase:", doc["phase"])
    return doc["path"]


# ---------------------------------------------------------------------------
# Turns


def latest_conversation(project, agent):
    row = (
        ro()
        .execute(
            "select id from conversations where project_id=? and agent=? "
            "order by created_at desc limit 1",
            (project, agent),
        )
        .fetchone()
    )
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
    res = call("POST", f"/api/v1/projects/{project}/agent/trigger", body)
    print("RUN=" + str(res.get("run_id")))
    print("  status:", res["status"], res.get("waiting_reason") or "")
    return res.get("run_id")


def wait_for(run_id, minutes=15):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        st = ro().execute("select status from runs where id=?", (run_id,)).fetchone()
        if st and st["status"] != "running":
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
    for row in c.execute(
        "select kind, content from agent_outputs where run_id=? order by sequence", (run_id,)
    ):
        body = (row["content"] or "").strip()
        if row["kind"] == "text":
            print(f"\n[TEXT]\n{body}")
        elif tools:
            print(f"[{row['kind']}] {body[:200]}")


def cmd_watch(run_id, minutes=15):
    print("status:", wait_for(run_id, float(minutes)))
    dump_turn(run_id)


def cmd_answer(project, agent, choice=None):
    rows = call("GET", f"/api/v1/projects/{project}/questions?answered=false")
    pending = [q for q in rows if q["from_agent"] == agent and not q.get("declined")]
    for q in sorted(pending, key=lambda x: x.get("batch_index") or 0):
        labels = [o["label"] for o in (q.get("options") or [])]
        pick = choice or (labels[0] if labels else "You decide")
        call(
            "PATCH",
            f"/api/v1/projects/{project}/questions/{q['id']}",
            {"answer": pick, "labels": [pick] if labels else []},
        )
        print(f"  answered: {q['question'][:80]} -> {pick}")
    print("answered:", len(pending))
    return len(pending)


# ---------------------------------------------------------------------------
# Spec phase control


def cmd_close(project, path):
    print(
        call(
            "POST",
            f"/api/v1/projects/{project}/project/documents/close-exploration"
            f"?path={urllib.parse.quote(path)}",
        )
    )


def cmd_propose(project, path):
    res = call(
        "POST",
        f"/api/v1/projects/{project}/project/documents/propose?path={urllib.parse.quote(path)}",
    )
    print(json.dumps(res, indent=2)[:2000])


def cmd_phase(project, path, to, reason=""):
    res = call(
        "POST",
        f"/api/v1/projects/{project}/project/documents/phase"
        f"?path={urllib.parse.quote(path)}&to={to}",
        {"reason": reason},
    )
    print(json.dumps(res, indent=2)[:800])


# ---------------------------------------------------------------------------
# Tasks and state


def cmd_tasks(project):
    rows = unwrap(call("GET", f"/api/v1/projects/{project}/tasks"))
    if not rows:
        print("(no tasks)")
    for t in rows:
        print(
            f"  {t['id']}  {t['status']:<15} {t.get('assignee') or '-':<12} {t['title'][:60]}"
        )
    return rows


def cmd_task_set(project, task_id, status_value, **extra):
    body = {"status": status_value}
    body.update(extra)
    res = call("PATCH", f"/api/v1/projects/{project}/tasks/{task_id}", body)
    print(f"  {task_id} -> {res['status']}")


def cmd_state(project):
    c = ro()
    print("--- documents ---")
    for r in c.execute(
        "select path, title, phase, explore_closed_at from spec_documents where project_id=?",
        (project,),
    ):
        print(f"  {r['phase']:<10} {r['path']}  ({r['title'][:50]})")
    print("--- document events ---")
    for r in c.execute(
        "select kind, actor_kind, actor, created_at from spec_document_events "
        "where project_id=? order by created_at",
        (project,),
    ):
        print(f"  {r['created_at'][:19]}  {r['kind']:<10} {r['actor_kind']}/{r['actor']}")
    print("--- runs ---")
    for r in c.execute(
        "select id, agent, status, error from runs where project_id=? order by started_at",
        (project,),
    ):
        print(f"  {r['id']}  {r['agent']:<12} {r['status']}  {(r['error'] or '')[:60]}")
    print("--- tasks ---")
    try:
        cmd_tasks(project)
    except RuntimeError:
        pass


def cmd_clean(project):
    c = sqlite3.connect(DB)
    d = c.execute("select working_directory from projects where id=?", (project,)).fetchone()
    for t in [r[0] for r in c.execute("select name from sqlite_master where type='table'")]:
        cols = [r[1] for r in c.execute(f'pragma table_info("{t}")')]
        if "project_id" in cols:
            c.execute(f'delete from "{t}" where project_id=?', (project,))
    c.execute("delete from projects where id=?", (project,))
    c.commit()
    if d:
        shutil.rmtree(d[0], ignore_errors=True)
    print("removed", project)


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(0)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "setup":
        cmd_setup(*args)
    elif cmd == "agent":
        cmd_agent(*args)
    elif cmd == "doc-new":
        cmd_doc_new(*args)
    elif cmd == "turn":
        doc = task = perm = None
        rest = []
        i = 0
        while i < len(args):
            if args[i] == "--doc":
                doc = args[i + 1]
                i += 2
            elif args[i] == "--task":
                task = args[i + 1]
                i += 2
            elif args[i] == "--perm":
                perm = args[i + 1]
                i += 2
            elif args[i] == "--fresh":
                rest.append("fresh")
                i += 1
            else:
                rest.append(args[i])
                i += 1
        fresh = "fresh" in rest
        rest = [r for r in rest if r != "fresh"]
        cmd_turn(rest[0], rest[1], rest[2], doc=doc, task=task, fresh=fresh, perm=perm)
    elif cmd == "watch":
        cmd_watch(*args)
    elif cmd == "answer":
        cmd_answer(*args)
    elif cmd == "close":
        cmd_close(*args)
    elif cmd == "propose":
        cmd_propose(*args)
    elif cmd == "phase":
        cmd_phase(*args)
    elif cmd == "tasks":
        cmd_tasks(*args)
    elif cmd == "task-set":
        cmd_task_set(*args)
    elif cmd == "state":
        cmd_state(*args)
    elif cmd == "clean":
        cmd_clean(*args)
    else:
        print(__doc__)
