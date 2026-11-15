"""Acceptance drive for `spec-page-remembers-readable-task-threads-retrospective-after-landing`
(RSRTT-1), 2026-11-15: the seven acceptance criteria that only a running Hub and a browser can
answer, written failing first, before RSRTT-2 (retrospective after landing), RSRTT-3 (remembered
spec) and RSRTT-4 (readable threads) are built. A later task runs it green and fixes only the drive.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8021
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), listening on 127.0.0.1, and refuses a port
something already answers on. Never :8000 or :8010. Real agent turns bind Haiku.

The scenario, in a throwaway git repository on `main`. A Haiku runner, agents Builder and Checker,
the build retrospective job on with automatic firing, and one landing-phase check on the project: a
project with a check lands in batches after a gather window (`landing_queue.BATCH_GATHER_SECONDS`),
which is what makes a landing stay `queued` after its approval commits. Without a check a landing
lands at once and "approved but not landed" could not be seen.

  R  "Retro waits"  two tasks t1 and t2 (no dependency: a document whose first task every other waits
                    on has an acceptance drive the Hub will not approve without a baseline), built as a flow at Reviewed. Builder really works each, and
                    the operator approves each (`POST /tasks/{id}/land`). t1 lands (a real landing
                    row reaching `landed`); t2's is still queued when its approval commits.
  S  "Thread graph" ten tasks, nothing worked: `a` with three dependants f1 f2 f3, and a prerequisite
                    in each other state with one dependant (pp pending, pi in_progress, pr rejected),
                    `a` approved. The tasks are moved by the operator's own PATCHes, so every state
                    is a real transition.

The checks (R first, because it takes the real turns; the browser checks use R and S):
  ac-retro-waits   t1 landed, t2 approved and its landing still open: no manager_job_fired event for
                   the retrospective job in the settle window; when t2's landing lands, exactly one.
  ac-reopen        the operator opens S from the list, the app is closed (a persistent browser
                   profile) and reopened on a bare ?project=<id>&tab=spec: S is shown.
  ac-url           S remembered, a link naming R opened: R is shown; then a bare Spec tab: R again.
  ac-list          S open, one click on the list control, the list is shown; the Spec tab left and
                   reopened bare: S is shown, not the list.
  ac-fanout        S in build order: the three edges leaving `a` share no segment (sampled along the
                   paths) and their vertical runs are at least 8px apart. Screenshot.
  ac-colour        S in build order: each edge leaving a prerequisite carries `data-state` naming that
                   prerequisite's state (done / waiting / in-progress / rejected), the four differ,
                   and the legend names the ones present. Screenshot.

The page contract the drive probes (RSRTT-3 and RSRTT-4 may rename these and the drive's fixing task
then follows them, not the behaviour):
  * a document is shown when `[data-testid=spec-document-header]` is visible and holds its title;
    the list is shown when no header is visible and `aside.aw-sp-list` is;
  * the list control is `[data-testid=spec-list-control]`, else the existing "Close document" button
    (`spec-document-close`), else a button named "All documents" / "Documents" / "List";
  * a thread is `svg.aw-sp-threads path.aw-sp-thread`; its prerequisite is the knot
    (`circle.aw-sp-knot`) at the path's start, whose `data-status` is that task's status;
  * a thread's state is its `data-state`: done | waiting | in-progress | rejected (the words
    approved / pending / in_progress are read as their state);
  * the legend is `[data-testid=spec-thread-legend]`, its text naming the states shown.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/rsrtt-drive/<HHMMSS>/.

    py -3.11 scripts/drive/rsrtt_acceptance_drive.py                  # own Hub on :8021
    py -3.11 scripts/drive/rsrtt_acceptance_drive.py --only ac-fanout,ac-colour
    py -3.11 scripts/drive/rsrtt_acceptance_drive.py --self-test      # the drive's own logic, no Hub
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import secrets
import socket
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
STAMP = time.strftime("%H%M%S")
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8021)
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-rsrtt" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
KEY = "aw_live_" + secrets.token_hex(16)
HAIKU = "claude-haiku-5-5"
JOB = "build-retrospective"
BUILDER, CHECKER = "Builder", "Checker"
DOC_R, TITLE_R = "spec/changes/retro-waits/spec.json", "Retro waits"
DOC_S, TITLE_S = "spec/changes/thread-graph/spec.json", "Thread graph"
TURN_WAIT = 10 * 60
LANDING_WAIT = 6 * 60
RETRO_WAIT = 5 * 60
SETTLE = 15
# A landing check this slow keeps a landing open longer than a retrospective takes to write.
CHECK_SECONDS = 75
DONE = ("completed", "under_review")
MIN_RUN_GAP = 8.0
ORDER = ["ac-retro-waits", "ac-reopen", "ac-url", "ac-list", "ac-fanout", "ac-colour"]
SPARE = ("Spare", "spec/changes/spare/spec.json")
# What each task of S is for, and the state its dependants' thread must show.
S_TASKS = [
    ("a", []), ("f1", ["a"]), ("f2", ["a"]), ("f3", ["a"]),
    ("pp", []), ("qp", ["pp"]), ("pi", []), ("qi", ["pi"]), ("pr", []), ("qr", ["pr"]),
]
S_STATES = {"a": "approved", "pp": "pending", "pi": "in_progress", "pr": "rejected"}
EXPECT_STATE = {"approved": "done", "pending": "waiting", "in_progress": "in-progress",
                "rejected": "rejected"}

checks = {}  # key -> (reached, failed, detail)


class Setup(Exception):
    """Something the drive depends on could not be arranged."""


def record(key, reached, ok, detail):
    checks[key] = (reached, reached and not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- pure logic (self-tested)


def thread_state(raw):
    """A thread's state word, normalised, or None. The page words it `data-state`."""
    word = (raw or "").strip().lower().replace("_", "-")
    return {"done": "done", "approved": "done", "waiting": "waiting", "pending": "waiting",
            "blocked": "waiting", "assigned": "waiting", "in-progress": "in-progress",
            "rejected": "rejected"}.get(word)


def legend_states(text):
    """The states a legend's text names."""
    low = (text or "").lower().replace("_", " ")
    found = set()
    for state, pattern in (("done", r"\b(done|approved)\b"), ("waiting", r"\b(waiting|pending|blocked)\b"),
                           ("in-progress", r"\bin[ -]progress\b"), ("rejected", r"\brejected\b")):
        if re.search(pattern, low):
            found.add(state)
    return found


def sharing(a, b, tolerance=0.75, allowed=2):
    """Two sampled paths (lists of (x, y)) share a segment: more than `allowed` of a's samples lie
    within `tolerance` px of one of b's. Paths may cross or touch at a knot; they may not run on."""
    near = sum(1 for (x, y) in a if any(math.hypot(x - u, y - v) <= tolerance for (u, v) in b))
    return near > allowed


def vertical_run_x(samples, tolerance=0.6):
    """The x of a path's longest vertical stretch: the longest run of consecutive samples whose x stays
    within `tolerance` of the run's first, as its mean x. None for fewer than two samples."""
    best, current = [], []
    for point in samples:
        if current and abs(point[0] - current[0][0]) > tolerance:
            current = []
        current.append(point)
        if len(current) > len(best):
            best = list(current)
    if len(best) < 2:
        return None
    return sum(p[0] for p in best) / len(best)


def fanout_verdict(paths):
    """`(ok, detail)` for the threads leaving one task: pairwise unshared, runs >= MIN_RUN_GAP apart."""
    if len(paths) != 3:
        return False, f"{len(paths)} threads leave the task, wanted 3"
    shared = [(i, j) for i in range(3) for j in range(i + 1, 3) if sharing(paths[i], paths[j])]
    runs = sorted(x for x in (vertical_run_x(p) for p in paths) if x is not None)
    gaps = [round(b - a, 1) for a, b in zip(runs, runs[1:])]
    ok = not shared and len(runs) == 3 and all(g >= MIN_RUN_GAP for g in gaps)
    return ok, (f"threads sharing a segment: {shared or 'none'}; vertical runs at x="
                f"{[round(r, 1) for r in runs]}, gaps {gaps} (need >= {MIN_RUN_GAP:g}px)")


def colour_verdict(edges, legend):
    """`(ok, detail)`: `edges` is [(prerequisite status, thread state word)], one per prerequisite state."""
    seen = {status: thread_state(word) for status, word in edges}
    wrong = {s: (seen.get(s), want) for s, want in EXPECT_STATE.items() if seen.get(s) != want}
    distinct = len({v for v in seen.values() if v}) == len(EXPECT_STATE)
    listed = legend_states(legend)
    missing = sorted(set(EXPECT_STATE.values()) - listed)
    ok = not wrong and distinct and not missing
    return ok, (f"thread states by prerequisite {seen}; wrong {wrong or 'none'}; legend names "
                f"{sorted(listed) or 'nothing'}" + (f", missing {missing}" if missing else ""))


def count_firings(events, since_ids=()):
    """Retrospective firings among manager_job_fired events, the ones in `since_ids` excluded."""
    return [e for e in events if e.get("job") in (JOB, None) and e.get("id") not in since_ids]


def self_test():
    straight = [(10 + 0.0, float(y)) for y in range(0, 100, 2)]
    shifted = [(22.0, float(y)) for y in range(0, 100, 2)]
    wide = [(34.0, float(y)) for y in range(0, 100, 2)]
    near = [(26.0, float(y)) for y in range(0, 100, 2)]
    piled = [(24.0, float(y)) for y in range(0, 100, 2)]
    cases = [
        (thread_state("approved"), "done"), (thread_state("In_Progress"), "in-progress"),
        (thread_state("pending"), "waiting"), (thread_state(None), None),
        (legend_states("Done · Waiting · In progress · Rejected"),
         {"done", "waiting", "in-progress", "rejected"}),
        (legend_states("approved, in_progress"), {"done", "in-progress"}),
        (sharing(straight, straight), True), (sharing(straight, shifted), False),
        (vertical_run_x(shifted), 22.0),
        (vertical_run_x([(0, 0), (5, 3), (10, 9)]), None),
        (fanout_verdict([straight, shifted, wide])[0], True),
        (fanout_verdict([straight, shifted, near])[0], False),   # 4px apart
        (fanout_verdict([piled, piled, piled])[0], False),        # one lane, drawn three times
        (fanout_verdict([straight, shifted])[0], False),
        (colour_verdict([("approved", "done"), ("pending", "waiting"), ("in_progress", "in-progress"),
                         ("rejected", "rejected")], "done waiting in progress rejected")[0], True),
        (colour_verdict([("approved", None), ("pending", None), ("in_progress", None),
                         ("rejected", None)], "")[0], False),
        (colour_verdict([("approved", "done"), ("pending", "done"), ("in_progress", "in-progress"),
                         ("rejected", "rejected")], "done in progress rejected")[0], False),
        (len(count_firings([{"id": "e1", "job": JOB}, {"id": "e2", "job": JOB}], {"e1"})), 1),
        (ORDER[-1], "ac-colour"),
        (len(S_TASKS), 10),
        (all(d in {k for k, _ in S_TASKS} for _, deps in S_TASKS for d in deps), True),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- the Hub


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


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def rw(sql, args=()):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs, every=2.0):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(every)
    return bool(fn())


def port_answers():
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def start_hub(log_path):
    DB.parent.mkdir(parents=True, exist_ok=True)
    # The drive may run inside an agent turn on another Hub: its HUB_URL, credential and tool-server
    # bin would reach this Hub's agents, whose tool calls would then go to that other Hub.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print(f"stopped the Hub on :{PORT}", flush=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def hold(pid, agent):
    """A running run of *agent*, so the flow hands it nothing; the operator is then the approver."""
    run_id = "run-rsrtt-" + secrets.token_hex(4)
    token = "aw_run_" + secrets.token_urlsafe(24)
    rw("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
       "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
       (run_id, pid, agent, _now(), hashlib.sha256(token.encode("utf-8")).hexdigest()))
    return run_id


def release(run_id):
    rw("update runs set status='completed', ended_at=? where id=?", (_now(), run_id))


def task_payload(key, title, depends_on, requirement, real):
    text = (f"Create the file {key}.txt at the repository root holding the single line `{key}`. "
            "Change nothing else. Record evidence for the requirement with record_evidence, then "
            "complete the task.") if real else f"Held for the drive's thread graph ({key})."
    return {"key": key, "title": title, "description": text, "requirements": [requirement],
            "files": [f"{key}.txt"], "depends_on": depends_on}


def document_payload(title, tasks, real):
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}, a document for the RSRTT drive.", "problem": "The drive needs one.",
        "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]},
        "requirements": [{"key": "r1", "modal": "MUST", "statement": "The repository MUST say so."}],
        "acceptance_criteria": [{"key": "says-so", "requirement": "r1", "given": "the repository",
                                 "when": "it is read", "then": "it says so", "how_to_check": "read it",
                                 "checked_by": "agent"}],
        "tasks": [task_payload(k, f"Task {k}", deps, "r1", real) for k, deps in tasks],
        "delivery": {"mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *",  # once a year: the drive fires the flow itself
                     "reasons": {"mode": "The drive.", "agent": "The default builder."}},
    }


def make_document(base, path, title, tasks, real):
    quoted = urllib.parse.quote(path)
    code, out = api("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec", "path": path})
    if code != 201:
        raise Setup(f"create {path}: {code} {str(out)[:300]}")
    code, out = api("PUT", f"{base}/project/documents/{path}/content",
                    {"document": document_payload(title, tasks, real)})
    if code != 200:
        raise Setup(f"save {path}: {code} {str(out)[:600]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    if code != 200:
        raise Setup(f"approve {path}: {code} {str(out)[:600]}")
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
                     "landing": "main"})
    if code != 200:
        raise Setup(f"build {path}: {code} {str(out)[:800]}")
    (doc_id,) = ro("select id from spec_documents where path=?", (path,))[0]
    tasks_by_key = {k: (t, loop) for t, loop, k in ro(
        "select id, loop_id, spec_task_key from tasks where spec_document_id=?", (doc_id,))}
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    return tasks_by_key, build_id


def status_of(task_id):
    return ro("select status from tasks where id=?", (task_id,))[0][0]


def live_runs(pid):
    return ro("select id from runs where project_id=? and status in ('running', 'queued', 'starting') "
              "and id not like 'run-rsrtt-%'", (pid,))


def work(base, pid, job_id, task_id, label):
    """Fire the flow until a real turn finishes *task_id*, re-firing only while nothing runs."""
    end = time.time() + TURN_WAIT
    while time.time() < end and status_of(task_id) not in DONE:
        if not live_runs(pid):
            code, out = api("POST", f"{base}/jobs/{job_id}/run")
            print(f"  fired {job_id} for {label}: {code} {str(out)[:120]}", flush=True)
        time.sleep(20)
    if status_of(task_id) not in DONE:
        raise Setup(f"{label}: no real turn finished the task in {TURN_WAIT}s ({status_of(task_id)})")
    poll(lambda: not live_runs(pid), 180)


def approve(base, task_id, label):
    code, rows = api("GET", f"{base}/project/spec/evidence?review_state=awaiting")
    rows = rows.get("evidence", []) if code == 200 and isinstance(rows, dict) else []
    for row in rows:
        api("POST", f"{base}/project/spec/evidence/{row['id']}/decision",
            {"decision": "accepted", "reason": "the drive's operator"})
    code, out = api("POST", f"{base}/tasks/{task_id}/land")
    if code != 200 or status_of(task_id) != "approved":
        raise Setup(f"{label}: the operator's approval: {code} {status_of(task_id)} {str(out)[:300]}")


def landing_state(task_id):
    rows = ro("select state from task_landings where task_id=? order by order_key desc, id desc limit 1",
              (task_id,))
    return rows[0][0] if rows else None


def firings(base):
    code, out = api("GET", f"{base}/manager/activity?job={JOB}")
    return out.get("firings", []) if code == 200 and isinstance(out, dict) else []


# --------------------------------------------------------------------------- the Hub part


def arrange(state):
    root = SCRATCH / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A throwaway project for the RSRTT drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"rsrtt-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"the project opens: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(pid=pid, base=base)
    # One landing-phase check: with one the Hub lands in batches after a gather window, so an
    # approved task's landing is still open when its approval commits.
    code, out = api("PUT", f"{base}/settings", {"main_branch": "main", "checks": [
        {"name": "slow", "phase": "landing",
         "command": f'"{sys.executable}" -c "import time; time.sleep({CHECK_SECONDS})"'}]})
    if code != 200:
        raise Setup(f"the project's main branch and landing check: {code} {str(out)[:300]}")
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"the Haiku runner: {code} {haiku}")
    for name in (BUILDER, CHECKER):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": haiku["id"], "model": HAIKU, "mode": "automatic"})
    if code != 200:
        raise Setup(f"the retrospective job on: {code} {str(out)[:300]}")
    # A third document, so a bare Spec tab never has a sole document to open for want of a choice.
    code, out = api("POST", f"{base}/project/documents",
                    {"title": SPARE[0], "kind": "change-spec", "path": SPARE[1]})
    if code != 201:
        raise Setup(f"the spare document: {code} {str(out)[:300]}")
    state["hold"] = hold(pid, CHECKER)
    print(f"project {pid} at {root}", flush=True)


def check_retro_waits(state):
    key, base, pid = "ac-retro-waits", state["base"], state["pid"]
    tasks, state["build_r"] = make_document(
        base, DOC_R, TITLE_R, [("t1", []), ("t2", [])], real=True)
    (t1, loop), (t2, _) = tasks["t1"], tasks["t2"]
    (job_id,) = ro("select job_id from loops where id=?", (loop,))[0]
    state["tasks_r"] = {"t1": t1, "t2": t2}
    work(base, pid, job_id, t1, "t1")
    approve(base, t1, "t1")
    if not poll(lambda: landing_state(t1) == "landed", LANDING_WAIT, every=3):
        raise Setup(f"t1's landing did not reach landed in {LANDING_WAIT}s (is {landing_state(t1)})")
    work(base, pid, job_id, t2, "t2")
    approve(base, t2, "t2")
    print(f"  t2 approved; its landing is {landing_state(t2)}", flush=True)
    if landing_state(t2) == "landed":
        raise Setup("t2's landing was already landed when its approval returned; no window to look in")
    if not poll(lambda: landing_state(t2) == "landed", LANDING_WAIT, every=3):
        record(key, True, False, f"t1 landed; t2 approved; its landing never landed (is {landing_state(t2)})")
        return
    # A firing is recorded when it ends, so "none had fired" is read off the landing: any firing
    # event stamped before t2's landing ended began at the approval, which the document must wait out.
    (landed_at,) = ro("select coalesce(ended_at, updated_at) from task_landings where task_id=? and "
                      "state='landed' order by order_key desc limit 1", (t2,))[0]
    early = ro("select timestamp from event_logs where project_id=? and event_type='manager_job_fired' "
               "and data like ? and timestamp < ?", (pid, f"%{DOC_R}%", landed_at))
    poll(lambda: len(firings(base)) >= 1, RETRO_WAIT, every=5)
    time.sleep(SETTLE)
    total = firings(base)
    record(key, True, not early and len(total) == 1,
           f"t1 landed; t2 approved with its landing open until {landed_at}: {len(early)} retrospective "
           f"firing(s) recorded before it landed; {len(total)} in all once it had")


# --------------------------------------------------------------------------- S: the thread graph


def arrange_graph(state):
    base = state["base"]
    tasks, state["build_s"] = make_document(base, DOC_S, TITLE_S, S_TASKS, real=False)
    state["tasks_s"] = {k: t for k, (t, _) in tasks.items()}
    ids = state["tasks_s"]
    walk = {
        "in_progress": ["in_progress"],
        "rejected": ["rejected"],
        "approved": ["in_progress", "completed", "under_review", "approved"],
    }
    for key, final in S_STATES.items():
        for step in walk.get(final, []):
            code, out = api("PATCH", f"{base}/tasks/{ids[key]}", {"status": step, "notes": "the drive"})
            if code != 200:
                raise Setup(f"{key} -> {step}: {code} {str(out)[:400]}")
    got = {k: status_of(ids[k]) for k in S_STATES}
    if got != S_STATES:
        raise Setup(f"the graph's states are {got}, wanted {S_STATES}")
    print(f"  graph states {got}", flush=True)


# --------------------------------------------------------------------------- the browser part


def new_context(play, profile):
    context = play.chromium.launch_persistent_context(
        str(profile), viewport={"width": 1440, "height": 940})
    # The operator's session is the tab's (sessionStorage, gone with the app) and the selected
    # project is remembered; what the app remembers beyond that is what the checks look for.
    context.add_init_script(
        f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));"
        "if (!localStorage.getItem('agentweave-selected-project')) "
        f"localStorage.setItem('agentweave-selected-project', {PID[0]!r});")
    return context


PID = [""]
TITLES = {"B": TITLE_S, "D": TITLE_R}
PATHS = {TITLE_S: DOC_S, TITLE_R: DOC_R, SPARE[0]: SPARE[1]}
OUT = [pathlib.Path(".")]


def spec_url(pid, document=None):
    url = f"{HUB}/?project={pid}&tab=spec"
    return url + (f"&document={urllib.parse.quote(document, safe='')}" if document else "")


def settle(page):
    page.wait_for_timeout(2500)


def header_text(page):
    header = page.get_by_test_id("spec-document-header")
    return header.first.inner_text() if header.count() and header.first.is_visible() else ""


def doc_shown(page, title):
    return title in header_text(page)


def list_shown(page):
    return not header_text(page) and page.locator("aside.aw-sp-list").count() > 0


def what_is_shown(page):
    if header_text(page):
        named = [t for t in (TITLE_S, TITLE_R, "Spare") if t in header_text(page)]
        return f"document {named[0] if named else header_text(page).splitlines()[0][:60]!r}"
    return "the list" if list_shown(page) else "neither a document nor the list"


def shot(page, name):
    OUT[0].mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT[0] / f"{name}.png"), full_page=True)


def open_from_list(page, title):
    row = page.locator("aside.aw-sp-list").get_by_text(title, exact=False).first
    row.wait_for(timeout=20000)
    row.click()
    settle(page)
    return doc_shown(page, title)


def list_control(page):
    for locator in (page.get_by_test_id("spec-list-control"), page.get_by_test_id("spec-document-close"),
                    page.get_by_role("button", name=re.compile(r"^(all documents|documents|list)$", re.I))):
        if locator.count():
            return locator.first
    return None


def browser_checks(state, only):
    from playwright.sync_api import sync_playwright

    pid = state["pid"]
    PID[0] = pid
    profile = SCRATCH / "browser-profile"
    with sync_playwright() as play:
        # What a bare Spec tab opens with nothing remembered. Master opens the newest document, so a
        # check that remembered that one would pass without remembering anything: B and D are chosen
        # among the documents it does not open.
        probe = new_context(play, SCRATCH / "browser-probe")
        try:
            page = probe.new_page()
            page.goto(spec_url(pid), wait_until="domcontentloaded")
            settle(page)
            default = what_is_shown(page)
        finally:
            probe.close()
        titles = [t for t in (TITLE_S, TITLE_R, SPARE[0]) if f"document {t!r}" != default]
        TITLES["B"], TITLES["D"] = titles[0], titles[1]
        print(f"  a fresh bare Spec tab shows {default}; B is {TITLES['B']!r}, D is {TITLES['D']!r}", flush=True)
        context = new_context(play, profile)
        page = context.new_page()
        page.goto(spec_url(pid), wait_until="domcontentloaded")
        settle(page)
        opened = False
        try:
            opened = open_from_list(page, TITLES["B"])
        except Exception as exc:  # noqa: BLE001 -- reported below, as the check's reach
            print(f"  could not open {TITLES['B']} from the list: {exc}", flush=True)
        context.close()   # the app is closed
        if not only or "ac-reopen" in only:
            guarded("ac-reopen", check_reopen, play, profile, pid, opened)
        if not only or "ac-url" in only:
            guarded("ac-url", check_url, play, profile, pid)
        if not only or "ac-list" in only:
            guarded("ac-list", check_list, play, profile, pid)
        if not only or {"ac-fanout", "ac-colour"} & only:
            context = new_context(play, profile)
            page = context.new_page()
            try:
                page.goto(spec_url(pid, DOC_S), wait_until="domcontentloaded")
                settle(page)
                for key, fn in (("ac-fanout", check_fanout), ("ac-colour", check_colour)):
                    if not only or key in only:
                        guarded(key, fn, page, state)
            finally:
                context.close()


def guarded(key, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 -- a probe that could not run is "not reached"
        checks[key] = (False, False, f"{type(exc).__name__}: {str(exc)[:240]}")
        print(f"FAIL {key} -- not reached: {exc}", flush=True)


def check_reopen(play, profile, pid, opened):
    if not opened:
        checks["ac-reopen"] = (False, False, f"could not open {TITLES['B']} from the list to remember it")
        return
    context = new_context(play, profile)   # the app, reopened
    try:
        page = context.new_page()
        page.goto(spec_url(pid), wait_until="domcontentloaded")
        settle(page)
        shot(page, "reopen")
        record("ac-reopen", True, doc_shown(page, TITLES["B"]),
               f"opened {TITLES['B']}, closed and reopened the app on a bare Spec tab: {what_is_shown(page)}")
    finally:
        context.close()


def check_url(play, profile, pid):
    context = new_context(play, profile)
    try:
        page = context.new_page()
        page.goto(spec_url(pid, PATHS[TITLES["B"]]), wait_until="domcontentloaded")
        settle(page)
        page.goto(spec_url(pid, PATHS[TITLES["D"]]), wait_until="domcontentloaded")
        settle(page)
        via_link = doc_shown(page, TITLES["D"])
        page.goto(spec_url(pid), wait_until="domcontentloaded")
        settle(page)
        later = doc_shown(page, TITLES["D"])
        shot(page, "url")
        record("ac-url", True, via_link and later,
               f"{TITLES['B']} remembered, a link naming {TITLES['D']}: shown={via_link}; a bare Spec tab "
               f"after: {what_is_shown(page)}")
    finally:
        context.close()


def check_list(play, profile, pid):
    context = new_context(play, profile)
    try:
        page = context.new_page()
        page.goto(spec_url(pid, PATHS[TITLES["B"]]), wait_until="domcontentloaded")
        settle(page)
        control = list_control(page)
        if control is None:
            shot(page, "list")
            record("ac-list", True, False,
                   f"{TITLES['B']} is open and the page has no list control to click ({what_is_shown(page)})")
            return
        control.click()
        settle(page)
        listed = list_shown(page)
        page.goto(f"{HUB}/?project={pid}&tab=thread", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.goto(spec_url(pid), wait_until="domcontentloaded")
        settle(page)
        back = doc_shown(page, TITLES["B"])
        shot(page, "list")
        record("ac-list", True, listed and back,
               f"one click on the list control: list shown={listed}; Spec tab left and reopened: "
               f"{what_is_shown(page)}")
    finally:
        context.close()


SAMPLE_JS = """() => {
  const svg = document.querySelector('svg.aw-sp-threads');
  if (!svg) return null;
  const knots = [...svg.querySelectorAll('circle.aw-sp-knot')].map(c => ({
    x: +c.getAttribute('cx'), y: +c.getAttribute('cy'), status: c.getAttribute('data-status')}));
  const edges = [...svg.querySelectorAll('path.aw-sp-thread')].map(p => {
    const n = 60, len = p.getTotalLength(), s = [];
    for (let i = 0; i <= n; i++) { const q = p.getPointAtLength(len * i / n); s.push([q.x, q.y]); }
    return {samples: s, state: p.getAttribute('data-state'), done: p.getAttribute('data-done'),
            klass: p.getAttribute('class')};
  });
  const legend = document.querySelector('[data-testid=spec-thread-legend]');
  return {knots, edges, legend: legend ? legend.innerText : null};
}"""


def graph(page):
    """Threads and knots as drawn, or why not."""
    page.get_by_role("radio", name=re.compile(r"build order", re.I)).first.click(timeout=3000) \
        if page.get_by_role("radio", name=re.compile(r"build order", re.I)).count() else None
    page.wait_for_timeout(1200)
    data = page.evaluate(SAMPLE_JS)
    if data is None:
        raise RuntimeError("no thread graph on the document (the tasks in build order)")
    return data


def edges_from(data, status):
    """The edges whose start sits on a knot of a task in `status`, as sample lists with their state."""
    out = []
    for edge in data["edges"]:
        x0, y0 = edge["samples"][0]
        knot = next((k for k in data["knots"] if abs(k["x"] - x0) < 0.6 and abs(k["y"] - y0) < 0.6), None)
        if knot and knot["status"] == status:
            out.append(edge)
    return out


def check_fanout(page, state):
    data = graph(page)
    shot(page, "fanout")
    leaving = edges_from(data, "approved")   # `a`'s three dependants, `a` being the approved task
    ok, detail = fanout_verdict([e["samples"] for e in leaving])
    record("ac-fanout", True, ok, detail)


def check_colour(page, state):
    data = graph(page)
    shot(page, "colour")
    edges = []
    for status in EXPECT_STATE:
        found = edges_from(data, status)
        edges.append((status, (found[0].get("state") or found[0].get("done")) if found else None))
    ok, detail = colour_verdict(edges, data["legend"])
    record("ac-colour", True, ok, detail + ("" if data["legend"] is not None else "; no legend on the page"))


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys to run (iteration)")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if str(PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code "
                 "(F1121). Pick another AW_DRIVE_PORT; this drive does not reuse a Hub.")
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    OUT[0] = REPO / "testbed" / "rsrtt-drive" / STAMP
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    state, setup_error = {}, None
    try:
        arrange(state)
        if not only or "ac-retro-waits" in only:
            try:
                check_retro_waits(state)
            except Setup as exc:
                checks["ac-retro-waits"] = (False, False, f"setup: {exc}")
                print(f"SETUP ac-retro-waits: {exc}", flush=True)
        if not only or only - {"ac-retro-waits"}:
            arrange_graph(state)
            browser_checks(state, only)
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        if state.get("hold"):
            release(state["hold"])
        for build in (state.get("build_r"), state.get("build_s")):
            if build and state.get("base"):
                api("POST", f"{state['base']}/project/builds/{build}/stop")
        stop_hub(proc)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        if only and key not in only:
            continue
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT[0]}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
