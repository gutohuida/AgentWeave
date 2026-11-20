"""Acceptance drive for `profiles-threads-and-builds-everywhere` (spdoc-02cb5580092b), 2026-11-20.

Task `acceptance-drive` (PTBE-1): written before the build and failing on today's code at its own
assertions (the agent tree is there, the wrong entries are listed, the collapsed rail shows profile
icons), never at an import or a missing route. The `drive-run` task runs it green after the bundle
is refreshed. Not part of the project's checks.

The Hub. It starts its own Hub from this checkout's `hub/` on a fresh database, on a scratch port
(:8137; never :8000 or :8010, and it refuses to run if the port answers), and drives it through
`uiharness.Judge`, which refuses :8000 and :8010 too. A fresh database rather than the Terra replica
(`terra_replica.py --up`): compact-rail-marked asserts the collapsed rail holds exactly two projects,
which a copy of the operator's database cannot give. `--hub URL --key KEY --db PATH` drives an
already-running replica instead (the drive then adds its two projects to it, and the rail check
counts only them).

What it seeds, the way the Hub makes each one (rows written as the cited code writes them; no agent
has a runner and every job is off, so nothing can start a turn):

  project A
    - an operator thread with Architect: conversation origin `operator`, the operator's message as a
      delivered `operator` queue entry (agent_trigger.py:2841, :2988), a completed run;
    - a flow task run of Developer, its conversation with no operator message: origin `job`, a
      JobRun naming the conversation, a `job` entry carrying the task (scheduler.py:5785-5826), a
      completed run bound to the task;
    - a task started on assignment, the conversation whose origin is left at its default: origin
      `operator`, its briefing an `operator` entry carrying the task (assigned_task_start.py:182-208)
      -- written by the Hub, not by the operator, so it must not be listed either;
    - a review run of QA: origin `job`, a `job` entry with `review_task_id`, titled `Review ...`
      (review_on_completion.py:268, mender.py:353-370);
    - a mender run: agent `mender`, origin `mender`, titled `Mending: ...` (stalls.py:574-587);
    - a job firing of Developer: an AIJob (off), a JobRun, origin `job`, a `job` entry;
    - a peer message from Architect to Developer: a Message, a conversation origin `peer` bound to
      the sender's conversation, an `agent` entry (messages.py:97, :385-408);
    - a second job firing, of QA, that the operator replied in: as the first, plus a later
      delivered `operator` entry;
    - three builds over three approved documents: running (1 of 2 tasks approved), stopped by the
      operator with a task not approved, finished with every task approved.
  project B: one profile and one running build.

Recency, newest first: peer message, replied job firing, mender run, Architect thread, review run,
job firing, flow task run, task started on assignment. So a list that keeps every conversation in
recency order, today's, does not happen to read as the expected one.

Checks, printed in the `drive_baseline` shape
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
  acceptance-drive      project A expanded: no agent tree or recency view; threads are exactly the
                        replied job firing then the Architect thread, each labelled with its
                        profile; builds are exactly the stopped and the running build.
  builds-listed         the stopped build is listed before the running one, each named
                        "Build: <title>, <n> of <m> tasks done, <state>"; the running one offers no
                        dismiss; no link to all builds; choosing the stopped one opens its build
                        view.
  compact-rail-marked   collapsed: the two projects only, no profile icons; A carries
                        rail-compact-needs-A and its name says one build needs the operator; B
                        carries none.

Names relied on are those hub/ui/mock/README.md lists under "The sidebar's threads and builds".
Screenshots at 1440 and 900, dark and light, go to testbed/ui-judge/d1120-threads-builds/<HHMMSS>/.
Exits 1 if any check failed.

    py -3.11 scripts/drive/d1120_threads_builds_sidebar_browser.py
    py -3.11 scripts/drive/d1120_threads_builds_sidebar_browser.py --keep   # leave the Hub up
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from uiharness import Judge  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8137
STAMP = time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
ORDER = ["acceptance-drive", "builds-listed", "compact-rail-marked"]

HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
DB = pathlib.Path()
checks: dict[str, tuple[bool, bool, str]] = {}


class SetupError(Exception):
    """The scenario could not be built: the drive says nothing about the product."""


def record(key, ok, detail, reached=True):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)
    return ok


def need(ok, what, detail=""):
    if not ok:
        raise SetupError(f"{what}: {detail}")


# ── The Hub ─────────────────────────────────────────────────────────────────────────────────────


def _testbed():
    """`testbed/` of the main checkout: the Hub refuses a project nested in a task checkout."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, capture_output=True, text=True).stdout.strip()
    main = pathlib.Path(common).parent if common else REPO
    return main / "testbed"


TMP = _testbed() / "drive1120-threads-builds" / STAMP


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
        text = exc.read().decode()[:2000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except urllib.error.URLError as exc:
        return 0, str(exc)


def poll(fn, secs=15.0, every=0.25):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(every)
    return False


def start_hub():
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"refusing to run: something already answers on :{PORT}")
    TMP.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120, 0.5):
        proc.kill()
        sys.exit(f"the Hub did not come up; see {TMP / 'hub.log'}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


# ── Rows, as the Hub writes them ────────────────────────────────────────────────────────────────

NOW = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def at(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S.%f")


def insert(table, values):
    """Insert *values*, filling every NOT NULL column the schema gives no SQL default (the model's
    Python-side defaults: timestamps, counters, flags) the way the ORM would."""
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        values = dict(values)
        for _, name, kind, notnull, default, pk in con.execute(f"pragma table_info({table})"):
            if name in values or name == "sequence" or not notnull or default is not None or pk:
                continue
            upper = kind.upper()
            if "DATE" in upper or name.endswith("_at"):
                values[name] = at(0)
            elif "INT" in upper or "BOOL" in upper:
                values[name] = 0
            elif "JSON" in upper:
                values[name] = "{}"
            else:
                values[name] = ""
        values = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in values.items()}
        marks = ", ".join("?" * len(values))
        con.execute(f"insert into {table} ({', '.join(values)}) values ({marks})",
                    tuple(values.values()))
        con.commit()
    finally:
        con.close()


def fetch(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def uid(prefix):
    return f"{prefix}-{secrets.token_hex(6)}"


def conversation(pid, agent, origin, title, minutes_ago, created_minutes_ago=None, **extra):
    cid = uid("conv")
    created = at(created_minutes_ago if created_minutes_ago is not None else minutes_ago + 1)
    insert("conversations", {
        "id": cid, "project_id": pid, "agent": agent, "lifecycle": "open", "title": title,
        "title_set_by_operator": 0, "origin": origin, "lineage_id": cid, "own_worktree": 0,
        "created_at": created, "updated_at": at(minutes_ago), **extra,
    })
    return cid


def entry(pid, agent, cid, origin_type, content, minutes_ago, run_id, **extra):
    insert("inbound_queue_entries", {
        "id": uid("entry"), "project_id": pid, "agent": agent, "origin_type": origin_type,
        "content": content, "arrived_at": at(minutes_ago), "hop_depth": 0, "state": "delivered",
        "delivered_in_run_id": run_id, "delivered_at": at(minutes_ago), "conversation_id": cid,
        **extra,
    })


def run(pid, agent, cid, minutes_ago, task_id=None):
    rid = uid("run")
    insert("runs", {
        "id": rid, "project_id": pid, "agent": agent, "conversation_id": cid,
        "status": "completed", "task_id": task_id, "turn_depth": 0,
        "started_at": at(minutes_ago + 1), "ended_at": at(minutes_ago), "initiator": "operator",
    })
    return rid


def job(pid, agent, name):
    jid = uid("job")
    insert("ai_jobs", {"id": jid, "project_id": pid, "name": name, "agent": agent,
                       "message": "Look over the queue.", "cron": "0 3 1 1 *", "enabled": 0,
                       "session_mode": "new", "created_at": at(600), "source": "hub"})
    return jid


def job_firing(pid, agent, jid, title, minutes_ago, task_id=None, review_task_id=None):
    cid = conversation(pid, agent, "job", title, minutes_ago)
    insert("job_runs", {"id": uid("jobrun"), "job_id": jid, "project_id": pid,
                        "fired_at": at(minutes_ago + 1), "status": "completed",
                        "trigger": "scheduled", "conversation_id": cid})
    rid = run(pid, agent, cid, minutes_ago, task_id=task_id or review_task_id)
    entry(pid, agent, cid, "job", f"Firing of {title}.", minutes_ago + 1, rid, job_id=jid,
          task_id=task_id, review_task_id=review_task_id)
    return cid, rid


def task(pid, assignee, title, status, build_id=None, document_id=None, number=1):
    tid = uid("task")
    insert("tasks", {"id": tid, "project_id": pid, "title": title, "description": title,
                     "status": status, "priority": "medium", "assignee": assignee,
                     "build_id": build_id, "spec_document_id": document_id,
                     "created_at": at(500), "updated": at(400)})
    return tid


def build(pid, document_id, state, minutes_ago, **extra):
    bid = uid("build")
    insert("builds", {"id": bid, "project_id": pid, "document_id": document_id, "state": state,
                      "driver": "flow", "level": "reviewed", "builders": ["Developer"],
                      "reviewers": ["QA"], "landing": "main", "created_at": at(minutes_ago),
                      **extra})
    return bid


# ── The scenario ────────────────────────────────────────────────────────────────────────────────


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def open_project(name):
    root = TMP / name
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text(f"A scratch project for {name}.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": name})
    need(code in (200, 201), f"project {name} opens", f"{code} {project}")
    return project["id"]


def agent(pid, name):
    """A profile made through the route, on a Haiku runner, which is then unbound (as
    terra_replica.py makes its copy inert) so that nothing seeded can start a turn."""
    code, runners = api("GET", f"/projects/{pid}/runners")
    rows = runners if isinstance(runners, list) else (runners or {}).get("runners", [])
    runner = next((r for r in rows if r.get("name") == "Haiku"), None)
    if runner is None:
        code, runner = api("POST", f"/projects/{pid}/runners",
                           {"name": "Haiku", "cli": "claude", "model": HAIKU})
        need(code in (200, 201), "a runner", f"{code} {runner}")
    code, out = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner["id"]})
    need(code in (200, 201), f"profile {name}", f"{code} {out}")
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    con.execute("update agents set runner_id = null where project_id = ? and name = ?", (pid, name))
    con.commit()
    con.close()


def mender_agent(pid):
    if fetch("select 1 from agents where project_id = ? and name = 'mender'", (pid,)):
        return
    insert("agents", {"id": uid("agent"), "project_id": pid, "name": "mender",
                      "config": {"hub_role": "mender"}, "created_at": at(600)})


def document(pid, title):
    path = "spec/changes/" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") + "/spec.json"
    code, out = api("POST", f"/projects/{pid}/project/documents",
                    {"title": title, "kind": "change-spec", "path": path})
    need(code == 201, f"document {title}", f"{code} {out}")
    return out["id"]


def seed():
    a = open_project(f"threads-{STAMP}")
    b = open_project(f"quiet-{STAMP}")
    for name in ("Architect", "Developer", "QA"):
        agent(a, name)
    agent(b, "Scout")
    mender_agent(a)

    # Builds and their tasks.
    doc_run, doc_stop, doc_done = (document(a, t) for t in
                                   ("Running slice", "Stopped slice", "Finished slice"))
    running = build(a, doc_run, "running", 300)
    stopped = build(a, doc_stop, "stopped", 400, stop_reason="stopped by the operator",
                    stopped_at=at(200))
    finished = build(a, doc_done, "finished", 500, stopped_at=at(350))
    t_run1 = task(a, "Developer", "Write the list", "approved", running, doc_run)
    t_run2 = task(a, "Developer", "Wire the list", "in_progress", running, doc_run)
    task(a, "Developer", "Write the stop", "assigned", stopped, doc_stop)
    task(a, "Developer", "Write the other stop", "approved", stopped, doc_stop)
    task(a, "Developer", "Write the done", "approved", finished, doc_done)
    task(a, "Developer", "Write the other done", "approved", finished, doc_done)
    doc_b = document(b, "Quiet slice")
    running_b = build(b, doc_b, "running", 100)
    task(b, "Scout", "Look around", "in_progress", running_b, doc_b)
    task(b, "Scout", "Look again", "approved", running_b, doc_b)

    # Conversations, oldest first. Minutes ago: 90, 80, 70, 60, 50, 40, 30, 20.
    on_assign = conversation(a, "Developer", "operator", "Task T-9: Wire the list", 90,
                             task_id=t_run2)
    rid = run(a, "Developer", on_assign, 90, task_id=t_run2)
    entry(a, "Developer", on_assign, "operator", "Task T-9 is yours. Wire the list.", 91, rid,
          task_id=t_run2)

    flow_job = job(a, "Developer", "flow: Running slice")
    flow_run, _ = job_firing(a, "Developer", flow_job, "Task T-8: Write the list", 80,
                             task_id=t_run1)
    plain_job = job(a, "Developer", "Nightly tidy")
    firing, _ = job_firing(a, "Developer", plain_job, "Nightly tidy", 70)
    review, _ = job_firing(a, "QA", flow_job, "Review T-8: Write the list", 60,
                           review_task_id=t_run1)

    architect = conversation(a, "Architect", "operator", "Shape the sidebar", 50)
    rid = run(a, "Architect", architect, 50)
    entry(a, "Architect", architect, "operator", "Let's shape the sidebar.", 51, rid)

    mending = conversation(a, "mender", "mender", "Mending: Wire the list", 40)
    rid = run(a, "mender", mending, 40)
    entry(a, "mender", mending, "mender", "A stall on T-9.", 41, rid)

    qa_job = job(a, "QA", "Morning check")
    replied, _ = job_firing(a, "QA", qa_job, "Morning check", 31)
    rid = run(a, "QA", replied, 30)
    entry(a, "QA", replied, "operator", "Thanks -- also check the docs.", 30, rid)
    insert_touch = sqlite3.connect(DB.as_posix(), timeout=30)
    insert_touch.execute("update conversations set updated_at = ? where id = ?", (at(30), replied))
    insert_touch.commit()
    insert_touch.close()

    message_id = uid("msg")
    peer = conversation(a, "Developer", "peer", "Sidebar wording", 20,
                        bound_sender_conversation_id=architect)
    insert("messages", {"id": message_id, "project_id": a, "sender": "Architect",
                        "recipient": "Developer", "subject": "Sidebar wording",
                        "content": "Please use 'thread'.", "type": "message",
                        "timestamp": at(21), "read": 1, "conversation_id": architect})
    rid = run(a, "Developer", peer, 20)
    entry(a, "Developer", peer, "agent", "Please use 'thread'.", 21, rid,
          origin_agent="Architect", message_id=message_id)

    return {
        "a": a, "b": b,
        "threads": [replied, architect],  # newest first
        "profiles": {replied: "QA", architect: "Architect"},
        "not_threads": {"task started on assignment": on_assign, "flow task run": flow_run,
                        "job firing": firing, "review run": review, "mender run": mending,
                        "peer message": peer},
        "builds": {"running": running, "stopped": stopped, "finished": finished},
        "titles": {running: "Running slice", stopped: "Stopped slice", finished: "Finished slice"},
    }


def confirm_seed(s):
    """The routes the sidebar reads today see every seeded row: a check that then fails is about
    the sidebar, not about a row the Hub could not read."""
    code, out = api("GET", f"/projects/{s['a']}/conversations")
    need(code == 200, "GET conversations", f"{code} {out}")
    listed = {c["id"] for c in out["conversations"]}
    seeded = set(s["threads"]) | set(s["not_threads"].values())
    need(seeded <= listed, "every seeded conversation is listed by the route",
         f"missing {sorted(seeded - listed)}")
    code, out = api("GET", f"/projects/{s['a']}/project/builds")
    need(code == 200, "GET builds", f"{code} {out}")
    states = {b["id"]: (b["state"], b["tasks_done"], b["tasks_total"]) for b in out["builds"]}
    want = {s["builds"]["running"]: ("running", 1, 2), s["builds"]["stopped"]: ("stopped", 1, 2),
            s["builds"]["finished"]: ("finished", 2, 2)}
    need(all(states.get(k) == v for k, v in want.items()), "builds read back", f"{states}")


# ── The checks ──────────────────────────────────────────────────────────────────────────────────

ROW = 'button[data-slot="rail-row"]'


def wait_sidebar(page, pid):
    need(poll(lambda: page.locator(f'[data-testid="rail-project-{pid}"]').count() > 0, 30),
         "the sidebar shows the project", page.url)
    page.wait_for_timeout(1500)  # the per-project reads settle


def row_ids(page, scope, prefix):
    ids = page.locator(f'{scope} {ROW}[data-testid^="{prefix}"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    return [i[len(prefix):] for i in ids if not re.search(r"-(dismiss|edge|profile)$", i)]


def check_acceptance(page, s):
    a = s["a"]
    tree = {
        "agent rows": page.locator(f'[data-testid^="rail-agent-{a}-"]').count(),
        "agent expanders": page.locator(f'[data-testid^="agent-expander-{a}-"]').count(),
        "recency view": page.locator(f'[data-testid="rail-recency-{a}"]').count(),
        "tree/recency toggle": page.locator('[data-testid="rail-view-toggle"]').count(),
    }
    present = {k: v for k, v in tree.items() if v}
    body = page.locator(f'[data-testid="rail-threads-builds-{a}"]').count()
    threads = row_ids(page, f'[data-testid="rail-threads-{a}"]', "rail-thread-")
    builds = row_ids(page, f'[data-testid="rail-builds-{a}"]', "rail-build-")
    labels = {}
    for cid in s["threads"]:
        label = page.locator(f'[data-testid="rail-thread-{cid}-profile"]')
        labels[cid] = label.first.inner_text().strip() if label.count() else None
    want_builds = {s["builds"]["running"], s["builds"]["stopped"]}
    problems = []
    if present:
        problems.append(f"agent tree present ({', '.join(f'{k}={v}' for k, v in present.items())})")
    if not body:
        problems.append(f"no rail-threads-builds-{a}")
    if threads != s["threads"]:
        names = {v: k for k, v in s["not_threads"].items()}
        names.update({s["threads"][0]: "replied job firing", s["threads"][1]: "Architect thread"})
        problems.append("threads listed " + str([names.get(t, t) for t in threads])
                        + ", want ['replied job firing', 'Architect thread']")
    if labels != s["profiles"]:
        problems.append(f"profile labels {labels}, want {s['profiles']}")
    if set(builds) != want_builds or len(builds) != 2:
        problems.append(f"builds listed {builds}, want the running and the stopped build")
    return record("acceptance-drive", not problems, "; ".join(problems) or
                  "no agent tree; threads replied job firing then Architect, labelled; builds "
                  "stopped and running")


def check_builds(page, s, judge):
    a = s["a"]
    running, stopped = s["builds"]["running"], s["builds"]["stopped"]
    scope = f'[data-testid="rail-builds-{a}"]'
    order = row_ids(page, scope, "rail-build-")
    problems = []
    if order != [stopped, running]:
        problems.append(f"build rows {order}, want [stopped, running]")
    names = {
        stopped: "Build: Stopped slice, 1 of 2 tasks done, stopped, needs you",
        running: "Build: Running slice, 1 of 2 tasks done, running",
    }
    for name in names.values():
        found = page.get_by_role("button", name=name, exact=True).count()
        if found != 1:
            problems.append(f"no button named {name!r}")
    if page.locator(f'[data-testid="rail-build-dismiss-{running}"]').count():
        problems.append("the running build offers a dismiss")
    if not page.locator(f'[data-testid="rail-build-dismiss-{stopped}"]').count():
        problems.append("the stopped build offers no dismiss")
    sidebar = page.locator('[data-testid="sidebar"]')
    all_builds = sidebar.get_by_role("link", name=re.compile("all builds", re.I)).count() + \
        sidebar.get_by_role("button", name=re.compile("all builds", re.I)).count()
    if all_builds:
        problems.append("the sidebar links to all builds")
    if page.get_by_role("button", name=re.compile(r"^Build: Finished slice")).count():
        problems.append("the finished build is listed")
    target = page.get_by_role("button", name=names[stopped], exact=True)
    if target.count() == 1:
        target.click()
        opened = poll(lambda: page.locator(
            f'[data-testid="build-view"][data-build-id="{stopped}"]').count() > 0, 15)
        if not opened:
            problems.append(f"choosing the stopped build did not open its build view ({page.url})")
        else:
            judge.shot(page, "stopped_build_opened")
    else:
        problems.append("so the stopped build could not be chosen")
    return record("builds-listed", not problems, "; ".join(problems) or
                  "stopped before running, named with titles and states; no dismiss on running; "
                  "no all-builds link; the stopped one opens its build view")


def check_compact(page, s):
    a, b = s["a"], s["b"]
    toggle = page.locator('[data-testid="rail-collapse-toggle"]')
    need(toggle.count() == 1, "the collapse toggle", "not found")
    toggle.click()
    need(poll(lambda: page.locator('[data-testid="sidebar"][data-collapsed="true"]').count() == 1,
              10), "the sidebar collapses", "data-collapsed never true")
    page.wait_for_timeout(800)
    projects = page.locator('[data-testid^="rail-compact-project-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    ours = [p for p in projects if p.endswith((a, b))]
    profiles = page.locator('[data-testid^="rail-compact-agent-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))")
    problems = []
    if profiles:
        problems.append(f"{len(profiles)} profile icon(s) in the collapsed rail: {profiles}")
    if sorted(ours) != sorted([f"rail-compact-project-{a}", f"rail-compact-project-{b}"]):
        problems.append(f"project icons {projects}")
    if not ARGS.hub and len(projects) != 2:
        problems.append(f"{len(projects)} project icons, want 2")
    name_a = page.locator(f'[data-testid="rail-compact-project-{a}"]').get_attribute("aria-label")
    name_b = page.locator(f'[data-testid="rail-compact-project-{b}"]').get_attribute("aria-label")
    if not page.locator(f'[data-testid="rail-compact-needs-{a}"]').count():
        problems.append("project A carries no needs-you mark")
    if not re.search(r"\b1 build needs you\b", name_a or ""):
        problems.append(f"project A is named {name_a!r}, which does not say one build needs you")
    if page.locator(f'[data-testid="rail-compact-needs-{b}"]').count():
        problems.append("project B carries a needs-you mark")
    if name_b and re.search(r"needs? you", name_b):
        problems.append(f"project B is named {name_b!r}")
    return record("compact-rail-marked", not problems, "; ".join(problems) or
                  "projects only; A marked and named '1 build needs you'; B unmarked")


def drive(s):
    with Judge("d1120-threads-builds", hub=HUB, key=KEY) as judge:
        def at_sidebar(page):
            wait_sidebar(page, s["a"])

        judge.shots(s["a"], "sidebar", at_sidebar,
                    locator=lambda page: page.locator('[data-testid="sidebar"]'))
        page = judge.page(project=s["a"], mode="dark")
        wait_sidebar(page, s["a"])
        for key, fn in (("acceptance-drive", lambda: check_acceptance(page, s)),
                        ("builds-listed", lambda: check_builds(page, s, judge))):
            if ARGS.only and key not in ARGS.only:
                continue
            fn()
        if not ARGS.only or "compact-rail-marked" in ARGS.only:
            page = judge.page(project=s["a"], mode="dark")
            wait_sidebar(page, s["a"])
            check_compact(page, s)
            judge.shot(page, "collapsed_1440_dark")
            judge.set_mode(page, "light")
            judge.shot(page, "collapsed_1440_light")
        if judge.errors:
            print(f"note: {len(judge.errors)} console/page error(s) seen; listed below", flush=True)


def main():
    global HUB, KEY, DB, ARGS
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub")
    parser.add_argument("--key")
    parser.add_argument("--db")
    parser.add_argument("--keep", action="store_true", help="leave the scratch Hub running")
    parser.add_argument("--only", type=lambda v: v.split(","), default=None)
    ARGS = parser.parse_args()
    proc = None
    if ARGS.hub:
        HUB, KEY, DB = ARGS.hub.rstrip("/"), ARGS.key, pathlib.Path(ARGS.db)
        if HUB.endswith((":8000", ":8010")):
            sys.exit("this drive never drives :8000 or :8010")
        TMP.mkdir(parents=True, exist_ok=True)
    else:
        DB = TMP / "hub.db"
        proc = start_hub()
    try:
        s = seed()
        confirm_seed(s)
        print(f"seeded project A {s['a']} and B {s['b']}", flush=True)
        drive(s)
    except SetupError as exc:
        print(f"SETUP {exc}", flush=True)
        for key in ORDER:
            checks.setdefault(key, (False, False, f"not reached: {exc}"))
    finally:
        if proc is not None and not ARGS.keep:
            stop_hub(proc)
        elif proc is not None:
            print(f"Hub left up on {HUB} (key {KEY}); stop pid {proc.pid}")
    print()
    for key in ORDER:
        if ARGS.only and key not in ARGS.only:
            continue
        reached, failed, detail = checks.get(key, (False, False, "not reached"))
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    return 1 if any(failed or not reached for reached, failed, _ in checks.values()) else 0


ARGS = argparse.Namespace(hub=None, only=None)

if __name__ == "__main__":
    sys.exit(main())
