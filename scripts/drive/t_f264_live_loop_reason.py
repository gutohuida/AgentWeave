"""F264, SECOND PASS — driving the live path row 17 could only mirror.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_f264_live_loop_reason.py
    AW_HUB=... AW_KEY=... py -3.11 t_f264_live_loop_reason.py --teardown

F264 was filed on 2026-09-01 from `t_sweep_row17_messages.py` leg 8 and **labelled honestly as
mirrored, not driven**: the SQL of `_pending_loop_request`'s message branch (`scheduler.py:415`)
was replayed read-only against the fixture's own rows, because reaching the branch for real needs a
loop whose `created_by_run_id` resolves to an agent — that is, a loop created *by an agent* through
`create_loop` — which that harness never built. What was measured was that the query as written
selects across projects. What was **not** measured was a live loop actually printing another
project's message to the operator.

This harness builds exactly that situation and reads what the product says:

* two projects with the **same two agent names**, `boss` and `worker` — names are project-scoped
  and repeat freely, which is the whole premise;
* a real `claude-haiku-4-5` turn as `boss` in the victim project calling `create_loop` with
  `agent="worker"` and `stop_when_queue_empties=True`, so `loop.created_by_run_id` is a real run
  and `job.agent` is the other name;
* then — after every turn, never before one — one unread `worker -> boss` message in **each**
  project, the victim's sent first and the foreign one second, so the foreign row is the newest
  candidate by `timestamp desc`;
* the loop's queue drained by the operator, then fired by hand through `POST /jobs/{id}/run`, which
  reaches `_loop_stop_reason` -> `QUEUE_DRAINED_REASON` -> the `loop_queue_exhausted` event whose
  payload carries `pending_request`.

Then it asks the two questions a mirror cannot answer: **which project's message did the product
choose**, and **can an operator read it** — through `GET /loops/{id}` and through the Logs screen,
which renders raw event data (`LogLine.tsx:132`) and, per F252, is shipped.

**Building the precondition found a second defect, which is why leg 2 has two halves.** The natural
call — `create_loop(..., initial_tasks=[...])`, exactly as the tool's own docstring advertises — is
refused 403 for an agent creating a loop for anybody but itself, because D8 collapses "the loop's
creator" into `AIJob.agent`, the agent the loop *triggers*. The refusal arrives after the job and
the loop have already been committed, so the caller is told the Hub rejected `POST /jobs` while an
enabled loop it does not know about is left behind — one whose `stop_when_queue_empties` can never
fire, because "empty" means drained and this queue never filled. Leg 2a drives that; leg 2b then
makes the same call without the seed, which is what the rest of the harness needs.

**Re-runnable on the state it leaves.** Every row this harness writes carries the run tag, the
reason is asserted against *this* run's own foreign subject rather than a constant, and no count is
absolute. The loop ends itself (`end_loop` disables the job), and `--teardown` deletes both
fixtures.
"""

import glob
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
KEY = os.environ.get("AW_KEY", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-f264")
DIR2 = DIR + "-foreign"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME2 = os.path.basename(DIR2.rstrip("\\/"))
BOSS, WORKER = "boss", "worker"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_ASSETS = os.path.join(ROOT, "hub", "hub", "static", "ui", "assets")
UI_SRC = os.path.join(ROOT, "hub", "ui", "src")

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


# ---------------------------------------------------------------------------- fixture


def git(path, *args):
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path, label):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row17_messages.py`, itself from row 16 and row 15, and not decoration: a
    project whose repository has no commits cannot run a turn — `git worktree add ... HEAD` fails
    with "invalid reference: HEAD" and `POST /agent/trigger` answers an honest 200 with
    `run_id: null`.
    """
    os.makedirs(path, exist_ok=True)
    if git(path, "rev-parse", "--git-dir").returncode != 0:
        git(path, "init")
    if git(path, "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write(label + " fixture\n")
        git(path, "add", "README.md")
        git(path, "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a turn can run")


def ensure_project(path, name):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path, name)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    _, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST", f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    # `lifecycle=all` for the same reason row 17 needed it: the default listing hides archived
    # rows, and a setup helper that reads the default listing cannot see what an earlier run left.
    _, body = api("GET", f"/projects/{project}/agents?lifecycle=all")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {str(body)[:300]}")


def teardown():
    for name in (NAME, NAME2):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR2):
        if os.path.isdir(path):
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME)
P2 = ensure_project(DIR2, NAME2)
RUNNER = ensure_runner(P)
RUNNER2 = ensure_runner(P2)
for _a in (BOSS, WORKER):
    ensure_agent(P, _a, RUNNER)
    ensure_agent(P2, _a, RUNNER2)
A = f"/projects/{P}"
A2 = f"/projects/{P2}"
print(f"fixture: victim {NAME}={P}  foreign {NAME2}={P2}  tag={TAG}")


# ---------------------------------------------------------------------------- helpers


def db_rows(sql, args=()):
    """Read the Hub's database read-only. Observation only; the Hub owns this file."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def send(project_path, sender, recipient, subject, content):
    return api(
        "POST",
        f"{project_path}/messages",
        {"from": sender, "to": recipient, "subject": subject, "content": content},
    )


def bundle_files():
    return sorted(glob.glob(os.path.join(UI_ASSETS, "*.js")))


def in_bundle(needle):
    for path in bundle_files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            if needle in fh.read():
                return os.path.basename(path)
    return None


def src_refs(symbol):
    """Every file under hub/ui/src that names *symbol*, tests excluded."""
    hits = []
    for path in glob.glob(os.path.join(UI_SRC, "**", "*.ts*"), recursive=True):
        rel = os.path.relpath(path, UI_SRC).replace("\\", "/")
        if "__tests__" in rel:
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            if re.search(re.escape(symbol), fh.read()):
                hits.append(rel)
    return hits


def trigger(project_path, agent, message):
    code, body = api(
        "POST", f"{project_path}/agent/trigger", {"agent": agent, "message": message}, timeout=90
    )
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = (body or {}).get("run_id") or (body or {}).get("id")
    return (run_id, "started") if run_id else (None, f"no run: {json.dumps(body)[:200]}")


def wait_run(run_id, wait=420):
    deadline = time.time() + wait
    while time.time() < deadline:
        rows = db_rows("SELECT id, status FROM runs WHERE id = ?", (run_id,))
        if rows and rows[0]["status"] not in ("running", "queued", "starting"):
            return rows[0]["status"]
        time.sleep(5)
    return "timeout"


def busy_runs(project):
    return db_rows(
        "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND status IN "
        "('running','queued','starting')",
        (project,),
    )[0]["c"]


def wait_idle(project, wait=300):
    """No turn in flight in *project*.

    Not a nicety. A turn started by a firing outlives the request that started it, and a live
    agent writes real rows — on the fourth and sixth runs of this harness the orphan loop's own
    worker turn sent `boss` a genuine message *after* the fixtures were seeded, which made that
    message the newest candidate and correctly flipped the measurement below. Anything this
    harness asserts about "the newest row" has to be seeded with the roster idle.
    """
    deadline = time.time() + wait
    while time.time() < deadline and busy_runs(project):
        time.sleep(5)
    return busy_runs(project)


# ---------------------------------------------------------------------------- LEG 0

leg(0, "preflight — the Hub under test is the one this checkout describes")

code, _probe = api("GET", "/projects")
ok("the Hub on this port answers an authenticated read", code == 200, str(code))
BASE_PROJECTS = project_count()
note("projects before this run", BASE_PROJECTS)

mine = db_rows("SELECT id, name FROM projects WHERE id = ?", (P,))
ok("the database read here is the one the Hub on this port serves",
   bool(mine) and mine[0]["name"] == NAME, f"{DB} -> {mine}")

# The claim under test is about a query in scheduler.py; if the running process predates the file
# on disk, nothing measured here says anything about this checkout.
sched = os.path.getmtime(os.path.join(ROOT, "hub", "hub", "scheduler.py"))
note("scheduler.py mtime", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sched)))


# ---------------------------------------------------------------------------- LEG 1

leg(1, "a loop created BY AN AGENT — the precondition, and what the natural call does")

# `create_loop` is gated: an agent-originated job needs the project's own allowance
# (`_require_agent_job_allowance`, jobs.py:31). The operator grants it here, as an operator would.
code, qs = api("GET", f"{A}/queue/settings")
ok("the queue settings read", code == 200, f"{code} {str(qs)[:200]}")
body = dict(qs or {})
body["allow_agent_jobs"] = True
code, qs2 = api("PATCH", f"{A}/queue/settings", body)
ok("the operator grants the agent-jobs allowance", code == 200 and qs2.get("allow_agent_jobs") is True,
   f"{code} {str(qs2)[:200]}")

CRON = "7 4 1 1 *"  # 04:07 on 1 January: far enough away that nothing fires behind this harness


def create_loop_turn(name, seed_title=None):
    """One real turn in which `boss` calls `create_loop` for `worker`, and nothing else."""
    lines = [
        "Do exactly one thing, then stop.",
        "",
        "Call the create_loop tool once with exactly these arguments:",
        f'  name: "{name}"',
        f'  agent: "{WORKER}"',
        '  message: "Work the queue."',
        f'  cron: "{CRON}"',
        '  purpose: "Drive the loop stall reason."',
        "  stop_when_queue_empties: true",
    ]
    if seed_title is not None:
        lines.append(f'  initial_tasks: [{{"title": "{seed_title}"}}]')
    lines += [
        "",
        "Call no other tool. Do not send a message to anyone. Do not create tasks separately. "
        "When create_loop returns or fails, end the turn immediately.",
    ]
    run_id, why = trigger(A, BOSS, "\n".join(lines))
    if run_id is None:
        return None, why
    return run_id, wait_run(run_id)


def loop_rows(name):
    return db_rows(
        "SELECT l.id, l.job_id, l.created_by_run_id, l.stop_when_queue_empties, l.ending_state, "
        "j.agent, j.cron, j.enabled, j.archived_at "
        "FROM loops l JOIN ai_jobs j ON j.id = l.job_id WHERE l.project_id = ? AND j.name = ?",
        (P, name),
    )


# ---- 2a. The call as an agent would naturally write it: seed the queue in the same call. -------
#
# `create_loop`'s own docstring advertises `initial_tasks`, and `jobs.py:697` states in a comment
# that the loop-authorship gate "is satisfied for free" here. It is not: D8 collapses "the loop's
# creator" into `AIJob.agent`, which is the agent the loop *triggers* — so an agent creating a loop
# for somebody else is not the creator of the loop it just created.
SEEDED_NAME = f"f264-seeded-{TAG}"
SEED_TITLE = f"f264 seed {TAG}"
jobs_before = db_rows("SELECT COUNT(*) c FROM ai_jobs WHERE project_id = ?", (P,))[0]["c"]
SEED_RUN, seed_status = create_loop_turn(SEEDED_NAME, seed_title=SEED_TITLE)
ok("a real turn started for the creating agent", SEED_RUN is not None, str(seed_status))
note("seeding run / status", f"{SEED_RUN} / {seed_status}")

# The Hub's own words, recorded by the runner as the tool's result — not the agent's prose about it.
errs = db_rows(
    "SELECT payload FROM agent_outputs WHERE run_id = ? AND kind = 'tool_result' "
    "AND payload LIKE '%create_loop%'",
    (SEED_RUN or "",),
)
err_text = " ".join(e["payload"] or "" for e in errs)
refused = "403" in err_text and "creator" in err_text
ok("the Hub REFUSED the agent's create_loop because of its initial_tasks", refused,
   err_text[:400] or "no tool_result recorded")
note("what the agent was told", re.sub(r"\\n", " ", err_text)[:260])

seeded = loop_rows(SEEDED_NAME)
ok("...and yet the job and loop it refused exist anyway (F54's rule breached)",
   len(seeded) == 1, f"{len(seeded)} rows")
if seeded:
    S = seeded[0]
    note("orphaned loop / job", f"{S['id']} / {S['job_id']}")
    stasks = db_rows("SELECT COUNT(*) c FROM tasks WHERE loop_id = ?", (S["id"],))[0]["c"]
    ok("the queue the call was refused for is empty", stasks == 0, str(stasks))
    ok("the orphan is left ENABLED, so it fires on its cron with nothing to do",
       bool(S["enabled"]), repr(S["enabled"]))
    ok("its stop condition can never fire: 'empty' means drained, and this one never filled",
       bool(S["stop_when_queue_empties"]) and stasks == 0,
       f"swqe={S['stop_when_queue_empties']} ever={stasks}")
    jobs_after = db_rows("SELECT COUNT(*) c FROM ai_jobs WHERE project_id = ?", (P,))[0]["c"]
    ok("the refusal added a job row", jobs_after == jobs_before + 1, f"{jobs_before} -> {jobs_after}")
    ok("the scheduler took it: a next firing is already stamped",
       bool(db_rows("SELECT next_run FROM ai_jobs WHERE id = ?", (S["job_id"],))[0]["next_run"]),
       str(db_rows("SELECT next_run FROM ai_jobs WHERE id = ?", (S["job_id"],))))

    # And what that firing does, driven rather than argued: `_loop_stop_reason` returns None for a
    # queue that never filled, so the stop condition does not catch it and a real turn starts on
    # an empty queue. One firing is enough to show the shape; the cron would repeat it.
    worker_runs_before = db_rows(
        "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, WORKER)
    )[0]["c"]
    c, b = api("POST", f"{A}/jobs/{S['job_id']}/run", None, timeout=300)
    note("firing the loop the Hub said it had refused", f"{c} {str(b)[:160]}")
    ok("that firing is NOT skipped — the stop condition cannot see a queue that never filled",
       c in (200, 201), f"{c} {str(b)[:200]}")
    worker_runs_after = db_rows(
        "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, WORKER)
    )[0]["c"]
    ok("...and it spends a real agent turn on a loop with nothing in its queue",
       worker_runs_after == worker_runs_before + 1, f"{worker_runs_before} -> {worker_runs_after}")

    # Leave nothing running: the operator's only way to stop a loop the product says was never made.
    api("PATCH", f"{A}/jobs/{S['job_id']}", {"enabled": False})
    api("POST", f"{A}/jobs/{S['job_id']}/archive")

# ---- 2b. The same call without the seed — the precondition F264's live path actually needs. ----
LOOP_NAME = f"f264-{TAG}"
RUN_ID, run_status = create_loop_turn(LOOP_NAME)
ok("a second real turn started", RUN_ID is not None, str(run_status))
note("run id / status", f"{RUN_ID} / {run_status}")
if RUN_ID is None:
    print("\ncannot continue without a run; stopping")
    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    sys.exit(1)

loops = loop_rows(LOOP_NAME)
ok("the agent's create_loop call produced a loop", len(loops) == 1, f"{len(loops)} rows: {loops}")
if not loops:
    print("\nthe live path needs an agent-created loop; stopping")
    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    sys.exit(1)
L = loops[0]
LOOP, JOB = L["id"], L["job_id"]
note("loop / job", f"{LOOP} / {JOB}")
ok("the loop records the creating RUN, which is what the message branch resolves",
   L["created_by_run_id"] == RUN_ID, f"{L['created_by_run_id']!r} != {RUN_ID!r}")
ok("the loop's job runs as the OTHER agent name", L["agent"] == WORKER, repr(L["agent"]))
ok("the loop stops when its queue empties", bool(L["stop_when_queue_empties"]), repr(L["stop_when_queue_empties"]))
ok("the creating run resolves to the creating agent (creator_agent = boss)",
   bool(db_rows("SELECT agent FROM runs WHERE id = ?", (RUN_ID,)))
   and db_rows("SELECT agent FROM runs WHERE id = ?", (RUN_ID,))[0]["agent"] == BOSS,
   str(db_rows("SELECT agent FROM runs WHERE id = ?", (RUN_ID,))))
note("cron the agent set", L["cron"])


# ---------------------------------------------------------------------------- LEG 2

leg(2, "the two candidate messages — same names, two projects, the foreign one newest")

# **Seeded after every real turn, deliberately.** This block used to run first, and on the fourth
# run the orphan loop's own firing (leg 1) spent a turn in which `worker` sent `boss` a genuine
# "Loop stall diagnosis" message — newer than both fixtures, in the victim's own project — and the
# measurement below correctly flipped. The defect is "whichever is newest anywhere", so the
# harness has to own which row is newest, and no agent turn may run between here and the firing.

ok("no turn is in flight before the candidates are seeded", wait_idle(P) == 0,
   f"{busy_runs(P)} runs still going")

VICTIM_SUBJ = f"victim-own {TAG}"
FOREIGN_SUBJ = f"FOREIGN-PROJECT {TAG}"

code, m1 = send(A, WORKER, BOSS, VICTIM_SUBJ, f"the victim project's own worker->boss mail {TAG}")
ok("the victim project's own worker->boss message is created", code == 201, f"{code} {str(m1)[:200]}")
M_VICTIM = (m1 or {}).get("id") if isinstance(m1, dict) else None

time.sleep(1.5)  # so `timestamp desc` has something unambiguous to order by

code, m2 = send(A2, WORKER, BOSS, FOREIGN_SUBJ, f"another project's private mail {TAG}")
ok("the foreign project's worker->boss message is created", code == 201, f"{code} {str(m2)[:200]}")
M_FOREIGN = (m2 or {}).get("id") if isinstance(m2, dict) else None
note("victim message / foreign message", f"{M_VICTIM} / {M_FOREIGN}")

pair = db_rows(
    "SELECT id, project_id, subject, read, timestamp FROM messages WHERE id IN (?, ?) "
    "ORDER BY timestamp",
    (M_VICTIM or "", M_FOREIGN or ""),
)
ok("both rows exist, one per project", len(pair) == 2 and pair[0]["project_id"] != pair[1]["project_id"],
   str(pair))
ok("neither is marked read (F259: nothing in the product ever marks one)",
   all(r["read"] in (0, False) for r in pair), str([r["read"] for r in pair]))
ok("the FOREIGN message is the newer of the two", bool(pair) and pair[-1]["id"] == M_FOREIGN,
   f"newest is {pair[-1]['id'] if pair else None}")

# The candidate set the unfiltered query sees, instance-wide, before the loop exists.
cands = db_rows(
    "SELECT id, project_id, subject FROM messages WHERE sender = ? AND recipient = ? AND read = 0 "
    "ORDER BY timestamp DESC",
    (WORKER, BOSS),
)
note("unread worker->boss messages instance-wide", f"{len(cands)} in {len({c['project_id'] for c in cands})} projects")
ok("the newest candidate instance-wide is this run's FOREIGN message",
   bool(cands) and cands[0]["id"] == M_FOREIGN, str(cands[:2]))


# ---------------------------------------------------------------------------- LEG 3

leg(3, "the operator seeds the queue — the caller D8 exempts — then drains it")

# The operator is exempt from `_authorize_loop_task_creation`, so this is the only way this loop's
# queue can be filled at all: its own creator is not its "creator" by D8's definition.
code, seeded_task = api("POST", f"{A}/tasks", {"title": f"f264 seed {TAG}", "loop_id": LOOP})
ok("the operator can put a task in the loop's queue", code in (200, 201),
   f"{code} {str(seeded_task)[:200]}")

code, qtasks = api("GET", f"{A}/tasks?loop_id={LOOP}")
queued = qtasks if isinstance(qtasks, list) else []
ok("the loop's queue now has a task", len(queued) >= 1, f"{code} {str(qtasks)[:200]}")
for t in queued:
    c, b = api("PATCH", f"{A}/tasks/{t['id']}", {"status": "rejected"})
    note(f"PATCH {t['id']} -> rejected", f"{c} {str(b)[:120]}")

open_now = db_rows(
    "SELECT COUNT(*) c FROM tasks WHERE loop_id = ? AND status NOT IN ('approved','rejected')",
    (LOOP,),
)[0]["c"]
ever = db_rows("SELECT COUNT(*) c FROM tasks WHERE loop_id = ?", (LOOP,))[0]["c"]
ok("the queue is drained, not never-filled (both halves of _loop_stop_reason)",
   open_now == 0 and ever >= 1, f"open={open_now} ever={ever}")


# ---------------------------------------------------------------------------- LEG 4

leg(4, "fire it — and read the reason the product gives the operator")

# A firing whose agent is already busy is skipped for a different reason and emits no exhaustion
# event at all — measured on the fourth run, where leg 1's orphan turn was still finishing. Wait
# for the roster to be idle before firing, or the measurement below races the fixture.
ok("no run is in flight in the fixture when the loop is fired", wait_idle(P) == 0,
   f"{busy_runs(P)} runs still going")

ev_before = db_rows(
    "SELECT COUNT(*) c FROM event_logs WHERE project_id = ? AND event_type = 'loop_queue_exhausted'",
    (P,),
)[0]["c"]
code, fired = api("POST", f"{A}/jobs/{JOB}/run", None, timeout=300)
note("POST /jobs/{id}/run", f"{code} {str(fired)[:200]}")
# The firing is answered as a refusal — and it is also the moment the loop ends for good
# (`end_loop` sets `ending_state`, disables the job and removes it from the scheduler). The
# response says only what the queue is; leg 7 measures the state it left behind.
ok("a manual fire on a drained loop is answered 409", code == 409, f"{code} {str(fired)[:200]}")
ok("...and the refusal text does not say the loop has now ended",
   not re.search(r"end|stopp|disabl", str(fired), re.I), str(fired)[:200])

evs = db_rows(
    "SELECT id, project_id, agent, data, timestamp FROM event_logs "
    "WHERE project_id = ? AND event_type = 'loop_queue_exhausted' ORDER BY timestamp DESC",
    (P,),
)
ok("the firing emitted a loop_queue_exhausted event", len(evs) == ev_before + 1,
   f"{ev_before} -> {len(evs)}")
mine_ev = next((e for e in evs if json.loads(e["data"] or "{}").get("loop_id") == LOOP), None)
ok("...for THIS loop", mine_ev is not None, str(evs[:1])[:200])
if mine_ev is None:
    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    sys.exit(1)

payload = json.loads(mine_ev["data"] or "{}")
pending = payload.get("pending_request")
note("pending_request", json.dumps(pending, default=str)[:400])
ok("the event carries a pending_request rather than null", isinstance(pending, dict),
   repr(pending))
if not isinstance(pending, dict):
    print("\nthe message branch did not fire; nothing further to measure")
    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    sys.exit(1)

ok("its kind is 'message' — the branch F264 is about", pending.get("kind") == "message",
   repr(pending.get("kind")))
ok("its addressee is the loop's creator", pending.get("to") == BOSS, repr(pending.get("to")))

# THE MEASUREMENT. Filed as mirrored on 2026-09-01; this is the live answer.
ok("THE REASON THE OPERATOR IS SHOWN IS THE FOREIGN PROJECT'S MESSAGE",
   pending.get("reason") == FOREIGN_SUBJ,
   f"reason={pending.get('reason')!r} foreign={FOREIGN_SUBJ!r} victim={VICTIM_SUBJ!r}")
ok("...and is NOT the victim project's own candidate",
   pending.get("reason") != VICTIM_SUBJ, repr(pending.get("reason")))


# ---------------------------------------------------------------------------- LEG 5

leg(5, "provenance — the row the reason came out of, and what a project filter would have said")

src = db_rows(
    "SELECT id, project_id, sender, recipient, read FROM messages WHERE subject = ?",
    (pending.get("reason") or "",),
)
ok("the reason text is a real message row", len(src) == 1, str(src))
if src:
    ok("that row belongs to the OTHER project",
       src[0]["project_id"] == P2, f"{src[0]['project_id']} (victim is {P})")
    ok("it is not the run's own project", src[0]["project_id"] != P, src[0]["project_id"])

scoped = db_rows(
    "SELECT id, subject FROM messages WHERE project_id = ? AND sender = ? AND recipient = ? "
    "AND read = 0 ORDER BY timestamp DESC LIMIT 1",
    (P, WORKER, BOSS),
)
note("what a project-scoped query would have returned", str(scoped))
ok("the correct answer existed and differs from the one printed",
   bool(scoped) and scoped[0]["subject"] == VICTIM_SUBJ and scoped[0]["subject"] != pending.get("reason"),
   f"scoped={scoped} printed={pending.get('reason')!r}")

# F259's half: the `read` predicate is not what bounds the candidate set.
unread_all = db_rows(
    "SELECT COUNT(*) c FROM messages WHERE sender = ? AND recipient = ? AND read = 0",
    (WORKER, BOSS),
)[0]["c"]
read_all = db_rows(
    "SELECT COUNT(*) c FROM messages WHERE sender = ? AND recipient = ? AND read = 1",
    (WORKER, BOSS),
)[0]["c"]
note("worker->boss messages instance-wide", f"{unread_all} unread / {read_all} read")
ok("the read predicate excludes nothing, so the candidate set is every such message ever sent",
   read_all == 0, f"{read_all} read rows exist")


# ---------------------------------------------------------------------------- LEG 6

leg(6, "reachability — can an operator actually read the leaked text?")

code, detail = api("GET", f"{A}/loops/{LOOP}")
ok("the loop detail route answers", code == 200, f"{code} {str(detail)[:200]}")
det_events = (detail or {}).get("events") or []
det_hit = next(
    (e for e in det_events if (e.get("data") or {}).get("pending_request")), None
)
ok("GET /loops/{id} hands the whole payload to the caller, foreign text included",
   det_hit is not None
   and ((det_hit.get("data") or {}).get("pending_request") or {}).get("reason") == FOREIGN_SUBJ,
   json.dumps(det_hit, default=str)[:300] if det_hit else "no event carried one")

code, logs = api("GET", f"{A}/logs?event_type=loop_queue_exhausted&limit=500")
rows = logs if isinstance(logs, list) else (logs or {}).get("logs") or []
log_hit = next(
    (r for r in rows
     if r.get("event_type") == "loop_queue_exhausted"
     and ((r.get("data") or {}).get("pending_request") or {}).get("reason") == FOREIGN_SUBJ),
    None,
)
ok("the Logs route — the one the shipped Logs screen reads — serves it too",
   log_hit is not None, f"{code}, {len(rows)} rows")
note("LogLine renders raw data on expand", "hub/ui/src/components/logs/LogLine.tsx:132")

# And the two places that could have *explained* it instead.
refs = src_refs("pending_request")
ok("no shipped component reads pending_request at all", not refs, str(refs))
ev_summary = os.path.join(UI_SRC, "lib", "eventSummary.ts")
with open(ev_summary, encoding="utf-8") as fh:
    summary_src = fh.read()
m = re.search(r"case 'loop_queue_exhausted':\s*\n\s*return ([^\n]+)", summary_src)
note("the timeline's whole sentence for this event", m.group(1) if m else "not found")
ok("the timeline summary drops the reason entirely",
   bool(m) and "pending_request" not in m.group(1), m.group(1) if m else "not found")
ok("the served bundle contains no reader either", in_bundle("pending_request") is None,
   str(in_bundle("pending_request")))


# ---------------------------------------------------------------------------- LEG 7

leg(7, "cleanliness — the loop ended itself, and nothing is left running")

job_now = db_rows("SELECT enabled, archived_at FROM ai_jobs WHERE id = ?", (JOB,))
ok("the ended loop's job was disabled by end_loop", bool(job_now) and not job_now[0]["enabled"],
   str(job_now))
enabled_anywhere = db_rows("SELECT COUNT(*) c FROM ai_jobs WHERE enabled = 1")[0]["c"]
ok("no job is left enabled anywhere on the instance", enabled_anywhere == 0, str(enabled_anywhere))
loop_row = db_rows("SELECT ending_state, stop_reason FROM loops WHERE id = ?", (LOOP,))
note("loop ending", str(loop_row))
ok("...and the loop records why it ended",
   bool(loop_row) and loop_row[0]["stop_reason"] == "loop queue is empty", str(loop_row))

# Put the allowance back the way a fresh project has it.
body["allow_agent_jobs"] = False
code, _ = api("PATCH", f"{A}/queue/settings", body)
ok("the agent-jobs allowance is revoked again", code == 200, str(code))
note("projects now", project_count())

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
if FAIL:
    print("failed:")
    for f in FAIL:
        print("  - " + f)
