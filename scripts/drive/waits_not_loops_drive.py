"""Acceptance drive for `a-task-that-cannot-move-waits-instead-of-being-rebuilt-and-re-reviewed`.

Criterion `drive-replays-tsbvd-5` of FR-2 (spdoc-2a6345a91b5d, task `write-acceptance-drive`),
written before the build. It replays the TSBVD-5 situation: a fix found while a task is being
built is filed as something that task must wait for, and the task must wait instead of being
rebuilt and re-reviewed.

It starts its own Hub from this checkout's `hub/` on a port it reserves (an OS-chosen free one,
never :8000 or :8010), with a fresh database under `testbed/waits-not-loops/<stamp>/`, and a
bootstrap key of its own. A project of two Haiku agents -- Developer (builder) and QA (checker)
-- and an approved one-requirement change built as a flow at Reviewed. Task W is the drive-like
task. The one scripted step: when W is `in_progress` the drive files fix task F, naming W as
waiting for it, with the credential of a run of QA bound to W (the checker's review run;
`hold`). Everything else is the flow's real agents: F is built, reviewed and approved by
Developer and QA, and W is handed back to Developer when F is approved.

The drive then samples once a second -- W as the Hub returns it, W's moves to revision_needed,
builder runs started on W since the filing, F's status, and whether W's branch holds F's commit
-- until W is next completed after F's approval, and judges the samples (`judge`):

  J1  while F is unapproved, every sample has W `blocked` with a reason naming F
  J2  W records zero moves to revision_needed from the filing on
  J3  no builder run starts on W while F is unapproved
  J4  within 60 s of F's approval W is assigned to its builder
  J5  when W is next completed, its branch contains F's approved commit

Not reached is not failed: a check the run never got to is reported `reached=no`, and still
fails the drive. If the Hub cannot start the drive exits 2 with the reason (the run is then to end
with report_cannot_satisfy, not a retry or a send-back).

The filing call's field naming W (`FILING_FIELD`) is the one thing this drive guesses at: the
change has not built it. The build's first task reads it from here and changes it if it names the
field differently. On the code before the build, the field is ignored, W gets no prerequisite
and J1 fails.

    py -3.11 scripts/drive/waits_not_loops_drive.py              # about 10-30 min, Haiku turns
    py -3.11 scripts/drive/waits_not_loops_drive.py --self-test  # no Hub, no model

Exit 0 only if every check holds; each sample is printed. `--self-test` judges the recorded
samples in `fixtures/waits_not_loops_samples.json` -- records as the Hub returned them in a real
run of this drive -- and variants of them, and exits 0 when `judge` tells them apart.
"""

import copy
import datetime
import hashlib
import json
import os
import pathlib
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
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "waits_not_loops_samples.json"
STAMP = time.strftime("%Y%m%d-%H%M%S")
TESTBED = REPO / "testbed" / "waits-not-loops" / STAMP
DB = TESTBED / "agentweave.db"
# Outside the checkout: the Hub refuses to register a project nested in a task checkout.
PROJECT_ROOT = pathlib.Path(tempfile.gettempdir()) / "waits-not-loops" / STAMP / "proj"
KEY = "aw_live_" + secrets.token_hex(16)
FORBIDDEN_PORTS = {8000, 8010}
HAIKU = "claude-haiku-5-5"
DEV, QA = "Developer", "QA"
DOC = "spec/changes/waits-not-loops/spec.json"
REQ = "says-w"
REQ_ID = "FR-1"  # what the Hub mints for the document's one requirement
YEARLY = "0 0 1 1 *"
FILING_FIELD = "precedes"  # create_task: the existing tasks the new one must be done before
FIRE_EVERY = 20
START_WAIT = 20 * 60
FIX_WAIT = 40 * 60
RELEASE_WITHIN = 60
SECOND_WAIT = 30 * 60
CHECKS = ("J1", "J2", "J3", "J4", "J5")
HUB = ""
PORT = 0
results = []


class Stop(Exception):  # noqa: N818 -- the drive's own stop signal, as in its siblings
    """A step the rest of the drive depends on failed."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


# ---------------------------------------------------------------------------------------------
# The judgement: pure, over sample records. Each sample is
#   {"t": seconds since the filing, "task": <GET /tasks/W as returned>, "fix_status": str,
#    "revision_moves": int, "builder_runs": int, "contains_fix": bool}
# `revision_moves` counts W's transitions to revision_needed since the filing; `builder_runs`
# counts runs of W's builder bound to W started since the filing; `contains_fix` is whether W's
# branch holds F's tip at that second.
# ---------------------------------------------------------------------------------------------


def judge(samples):
    """{check: (reached, passed, detail)} for J1..J5 over the samples, in time order."""
    out = {}
    open_ = [s for s in samples if s["fix_status"] != "approved"]
    approved = [s for s in samples if s["fix_status"] == "approved"]
    fix_id = samples[0].get("fix_id") if samples else None

    bad = [s for s in open_ if not (
        s["task"].get("status") == "blocked"
        and fix_id and fix_id in (s["task"].get("blocked_reason") or ""))]
    out["J1"] = (bool(open_), bool(open_) and not bad, "every unapproved-fix sample has W blocked naming F" if not bad
                 else f"{len(bad)} of {len(open_)} samples not blocked on F, first at t="
                      f"{bad[0]['t']}s: {bad[0]['task'].get('status')!r} "
                      f"{bad[0]['task'].get('blocked_reason')!r}")

    moves = max((s["revision_moves"] for s in samples), default=0)
    out["J2"] = (bool(samples), bool(samples) and moves == 0, f"moves to revision_needed since the filing: {moves}")

    runs = max((s["builder_runs"] for s in open_), default=0)
    out["J3"] = (bool(open_), bool(open_) and runs == 0,
                 f"builder runs started on W while F was unapproved: {runs}")

    if not approved:
        out["J4"] = (False, False, "F was never approved in the samples")
    else:
        t0 = approved[0]["t"]
        window = [s for s in approved if s["t"] - t0 <= RELEASE_WITHIN]
        # A release is an assignment that follows a wait: W was blocked before it.
        was_blocked = False
        hit = []
        for s in samples:
            if s["task"].get("status") == "blocked":
                was_blocked = True
            elif (was_blocked and s in window and s["task"].get("status") == "assigned"
                  and s["task"].get("assignee") == DEV):
                hit.append(s)
        out["J4"] = (True, bool(hit), (f"assigned to {DEV} at +{hit[0]['t'] - t0:.0f}s" if hit else
                     f"not assigned to {DEV} within {RELEASE_WITHIN}s of approval; statuses "
                     f"{sorted({s['task'].get('status') for s in window})}"))

    # W's next completion after the filing, whenever it comes: on the code before the build it
    # comes without F's commit, which is what this check exists to catch.
    done = [s for s in samples if s["task"].get("status") in ("completed", "under_review",
                                                               "approved")]
    out["J5"] = (bool(done), bool(done) and done[0]["contains_fix"],
                 ("W's branch holds F's commit when W is next completed" if done and
                  done[0]["contains_fix"] else "W's branch lacks F's commit when W is next "
                  "completed" if done else "W was not completed again"))
    return out


def self_test():
    """`judge` on the recorded samples of a real run, and on variants that must differ."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    samples = data["samples"]
    print(f"recorded run {data['recorded_from']} ({len(samples)} samples)")
    real = judge(samples)
    for key in CHECKS:
        print(f"  recorded {key}: {real[key]}")
    ok = True

    def expect(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(("PASS " if good else "FAIL ") + name + ("" if good else f" -- got {got}, want {want}"))

    expect("the recorded run is judged as the real run was", data["expected"],
           {k: bool(v[1]) for k, v in real.items()})
    # Variants made by editing the recorded samples: fields the Hub returned stay as returned,
    # only the verdict-bearing ones are set, and F is made approved from 60% of the way through.
    fix_id = samples[0]["fix_id"]
    cut = max(1, int(len(samples) * 0.6))
    good = copy.deepcopy(samples)
    for i, s in enumerate(good):
        s["revision_moves"] = s["builder_runs"] = 0
        if i < cut:
            s["fix_status"] = "pending"
            s["task"]["status"] = "blocked"
            s["task"]["blocked_reason"] = f"waiting for {fix_id}"
        else:
            s["fix_status"] = "approved"
            s["task"]["status"] = "assigned"
            s["task"]["assignee"] = DEV
            s["task"]["blocked_reason"] = None
            s["t"] = s["t"] + 0.0
    good[-1]["task"]["status"] = "completed"
    good[-1]["contains_fix"] = True
    verdict = judge(good)
    expect("a waiting-then-released run passes every check", [verdict[k][1] for k in CHECKS],
           [True] * 5)
    loop = copy.deepcopy(good)
    loop[0]["task"]["status"] = "revision_needed"
    for s in loop:
        s["revision_moves"] = 1
    expect("a send-back is caught (J1, J2)", [judge(loop)[k][1] for k in ("J1", "J2")],
           [False, False])
    rebuilt = copy.deepcopy(good)
    rebuilt[0]["builder_runs"] = 1
    expect("a builder run while F is open is caught (J3)", judge(rebuilt)["J3"][1], False)
    late = copy.deepcopy(good)
    for s in late:
        if s["fix_status"] == "approved":
            s["task"]["status"] = "blocked"
    expect("a release that never comes is caught (J4)", judge(late)["J4"][1], False)
    stale = copy.deepcopy(good)
    stale[-1]["contains_fix"] = False
    expect("a branch without F's commit is caught (J5)", judge(stale)["J5"][1], False)
    unstopped = copy.deepcopy(good)
    unstopped[1]["task"]["status"] = "under_review"
    unstopped[1]["task"]["blocked_reason"] = None
    expect("a task that is not stopped is caught (J1)", judge(unstopped)["J1"][1], False)
    expect("no samples is not a pass", all(not v[1] for v in judge([]).values()), True)
    print("self-test: " + ("ok" if ok else "FAILED"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------
# The drive
# ---------------------------------------------------------------------------------------------


def api(method, path, body=None, timeout=60, key=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"},
        method=method)
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


def git(root, *args):
    out = subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=drive",
                          *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return out.returncode, out.stdout.strip()


def poll(fn, secs, every=1.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- a row not yet written
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


def start_hub():
    global PORT, HUB
    PORT = free_port()
    HUB = f"http://127.0.0.1:{PORT}"
    TESTBED.mkdir(parents=True)
    # The drive may run inside an agent turn on another Hub: hand this one none of its
    # HUB_URL, credentials or tool-server bin, or its agents' tool calls would go there.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TESTBED / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120):
        proc.kill()
        print(f"the throwaway Hub did not come up on :{PORT}; see {TESTBED / 'hub.log'}")
        sys.exit(2)
    print(f"started a throwaway Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    if proc is not None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def hold(pid, agent, task_id):
    """A running run of `agent` bound to `task_id`, as the Hub's tests seed one, and its
    credential: the checker's review run on the task, which a spawned turn alone has otherwise."""
    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-wnl-" + secrets.token_hex(4)
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(
            "insert into runs (id, project_id, agent, task_id, status, started_at, initiator, "
            "turn_depth, capability_token_hash) values (?, ?, ?, ?, 'running', ?, 'operator', 0, ?)",
            (run_id, pid, agent, task_id, _now(),
             hashlib.sha256(token.encode("utf-8")).hexdigest()))
        con.commit()
    finally:
        con.close()
    return run_id, token


def release(run_id):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute("update runs set status='completed', ended_at=? where id=?", (_now(), run_id))
        con.commit()
    finally:
        con.close()


DESCRIPTION = (
    "Goal: w.txt at the repository root holds the single line `w`, and the fix for it is in: "
    "f.txt at the repository root holds `f` (another task adds f.txt; it lands on main when done). "
    "How this task is worked (follow it exactly; it is a drive):\n"
    "- Builder (Developer): first `git merge main` so any f.txt that has landed is here. Create "
    "w.txt holding `w`, `git add w.txt`, `git commit -m w`. Then run "
    f"`cat w.txt`, call record_evidence for requirement `{REQ_ID}` (document {DOC}) with this task's "
    "id, that command, its output and covers `full`, and move the task to completed. If this task "
    "is now waiting on another task, do nothing more.\n"
    "- Reviewer: run `cat w.txt` and `cat f.txt`. Where f.txt is missing from this task's branch, "
    "the fix is not in: do not approve; move this task to revision_needed with reason_class "
    "`defect` and the note `f.txt is missing`, and decide no evidence. Where w.txt reads `w` and "
    "f.txt reads `f`, accept the evidence with your own reproduction at the current commit and "
    "approve the task."
)
FIX_DESCRIPTION = (
    "Goal: f.txt at the repository root holds the single line `f`.\n"
    "- Builder: create f.txt holding `f`, `git add f.txt`, `git commit -m f`. Then run `cat f.txt`, "
    f"call record_evidence for requirement `{REQ_ID}` (document {DOC}) with this task's id, that "
    "command, its output and covers `partial`, and move the task to completed.\n"
    "- Reviewer: run `cat f.txt`; where it reads `f`, accept the evidence with your own "
    "reproduction at the current commit and approve the task."
)


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Waits not loops",
        "summary": "The repository says w.", "problem": "The repository has no w.txt.",
        "scope": {"in_scope": ["w.txt", "f.txt (the fix W waits for, added by a task filed during the build)"], "non_goals": ["Anything else"]},
        "requirements": [{"key": REQ, "modal": "MUST",
                          "statement": "The repository MUST hold w.txt reading w, and f.txt reading f (the fix a task filed during the build adds)."}],
        "acceptance_criteria": [{
            "key": "says-w-ac", "requirement": REQ, "given": "the repository",
            "when": "w.txt is read", "then": "it reads w", "how_to_check": "cat w.txt",
            "checked_by": "agent"}],
        "tasks": [{"key": "w", "title": "Add w.txt", "description": DESCRIPTION,
                   "requirements": [REQ], "files": ["w.txt"], "builder": DEV, "checker": QA}],
        "delivery": {"mode": "flow", "agent": DEV, "checker": QA, "stop_when_queue_empties": True,
                     "cron": YEARLY, "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def runs_busy(pid):
    return ro("select id, agent from runs where project_id=? and status in "
              "('running', 'queued', 'starting') and id not like 'run-wnl-%'", (pid,))


class Sampler:
    def __init__(self, base, pid, job, w, branch_of):
        self.base, self.pid, self.job, self.w, self.branch_of = base, pid, job, w, branch_of
        self.fix = None
        self.t0 = None
        self.samples = []
        self.last_fire = 0.0

    def fire(self):
        if time.time() - self.last_fire >= FIRE_EVERY:
            self.last_fire = time.time()
            api("POST", f"{self.base}/jobs/{self.job}/run")

    def tick(self):
        self.fire()
        _, task = api("GET", f"{self.base}/tasks/{self.w}")
        if not isinstance(task, dict):
            task = {"status": f"unreadable: {task}"}
        fix_status = ro("select status from tasks where id=?", (self.fix,))[0][0]
        moves = ro("select count(*) from task_transitions where task_id=? and "
                   "to_status='revision_needed' and created_at >= ?", (self.w, self.since))[0][0]
        runs = ro("select count(*) from runs where task_id=? and agent=? and started_at >= ? and "
                  "id not like 'run-wnl-%'", (self.w, DEV, self.since))[0][0]
        contains = self.contains_fix()
        sample = {"t": round(time.time() - self.t0, 1), "fix_id": self.fix, "task": task,
                  "fix_status": fix_status, "revision_moves": moves, "builder_runs": runs,
                  "contains_fix": contains}
        self.samples.append(sample)
        print(f"  t={sample['t']:>6}s W {task.get('status')} assignee {task.get('assignee')} "
              f"blocked_reason {task.get('blocked_reason')!r} | F {fix_status} | "
              f"revision moves {moves} builder runs {runs} contains F {contains}", flush=True)
        return sample

    def contains_fix(self):
        fix_branch, w_branch = self.branch_of(self.fix), self.branch_of(self.w)
        code, tip = git(PROJECT_ROOT, "rev-parse", "--verify", "-q", fix_branch)
        if code or not w_branch:
            return False
        code, _ = git(PROJECT_ROOT, "merge-base", "--is-ancestor", tip, w_branch)
        return code == 0


def drive(state):
    PROJECT_ROOT.mkdir(parents=True)
    git(PROJECT_ROOT, "init", "-q", "-b", "main")
    (PROJECT_ROOT / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (PROJECT_ROOT / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    git(PROJECT_ROOT, "add", ".")
    git(PROJECT_ROOT, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(PROJECT_ROOT),
                                                   "name": f"wnl-{STAMP}"})
    check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state["base"] = base
    api("PATCH", base, {"main_branch": "main"})
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude",
                                                   "model": HAIKU})
    check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    for name in (DEV, QA):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": "Waits not loops", "kind": "change-spec", "path": DOC})
    check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    check("setup: the document is saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    # The confirmation is an agent-plane call; the held run is a QA run bound to no task.
    run_id, token = hold(pid, QA, None)
    try:
        code, out = api("POST", "/agent-actions/spec/documents/confirm-criteria", {
            "path": DOC, "confirmations": [{"criterion": "says-w-ac", "kind": "new"}]}, key=token)
    finally:
        release(run_id)
    check("setup: the criterion is confirmed", code == 200, f"{code} {str(out)[:400]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True,
                     "content_version": read.get("content_version")})
    check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builder": DEV, "checker": QA,
                     "landing": "main"})
    check("setup: the document is built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    state["build"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    rows = ro("select t.id, t.loop_id from tasks t join spec_documents s on t.spec_document_id = "
              "s.id where s.project_id = ? and s.path = ?", (pid, DOC))
    check("setup: task W materialised", len(rows) == 1, f"{rows}", fatal=True)
    w, loop = rows[0]
    job = ro("select job_id from loops where id = ?", (loop,))[0][0]
    print(f"project {pid} root {PROJECT_ROOT}\n  W {w} job {job}", flush=True)

    def branch_of(task_id):
        return f"agentweave/task/{task_id}"

    sampler = Sampler(base, pid, job, w, branch_of)

    def started():
        sampler.fire()
        return ro("select status from tasks where id=?", (w,))[0][0] == "in_progress"

    check("setup: W reaches in_progress", bool(poll(started, START_WAIT, every=2.0)), fatal=True)

    # The one scripted step: the checker's review run files F, naming W as waiting for it.
    run_id, token = hold(pid, QA, w)
    sampler.since = _now()
    body = {"title": "Add f.txt", "description": FIX_DESCRIPTION, "assignee": DEV, "builder": DEV,
            "checker": QA, "spec_document": DOC, "requirement_ids": [REQ_ID]}
    try:
        code, fix = api("POST", "/agent-actions/tasks", {**body, FILING_FIELD: [w]}, key=token)
        print(f"  filed F as run {run_id} (QA, bound to {w}): {code} {str(fix)[:300]}", flush=True)
        if not check("the checker's run can file F as something W waits for",
                     code in (200, 201), f"{code} {str(fix)[:300]}"):
            # Not a reason to stop: file F plainly so the flow runs, and let the samples show
            # what happens to W.
            code, fix = api("POST", "/agent-actions/tasks", body, key=token)
            print(f"  filed F without waiting: {code} {str(fix)[:200]}", flush=True)
    finally:
        release(run_id)
    check("setup: F exists", code in (200, 201), f"{code} {str(fix)[:300]}", fatal=True)
    sampler.fix = fix["id"]
    sampler.t0 = time.time()
    state["samples"] = sampler.samples

    # Sample every second until W is next completed after F's approval, or the waits run out.
    deadline = time.time() + FIX_WAIT + SECOND_WAIT
    approved_at = None
    while time.time() < deadline:
        s = sampler.tick()
        if s["fix_status"] == "approved" and approved_at is None:
            approved_at = time.time()
        if approved_at and s["task"].get("status") in ("completed", "under_review", "approved"):
            break
        if approved_at and time.time() - approved_at > SECOND_WAIT:
            break
        if approved_at is None and time.time() - sampler.t0 > FIX_WAIT:
            break
        time.sleep(1)


def save_samples(samples, expected=None):
    path = TESTBED / "samples.json"
    path.write_text(json.dumps({"recorded_from": f"waits_not_loops_drive {STAMP}",
                                "samples": samples, "expected": expected}, indent=1),
                    encoding="utf-8")
    print(f"samples written to {path}")


def tidy(state):
    base, build = state.get("base"), state.get("build")
    if base and build:
        code, _ = api("POST", f"{base}/project/builds/{build}/stop")
        print(f"stopped build {build}: {code}")


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    proc = start_hub()
    state = {}
    started = time.time()
    try:
        drive(state)
    except Stop:
        pass
    finally:
        try:
            tidy(state)
        finally:
            stop_hub(proc)
    samples = state.get("samples") or []
    verdict = judge(samples)
    save_samples(samples, {k: bool(v[1]) for k, v in verdict.items()})
    print(f"\nper-check result ({int(time.time() - started)}s):")
    for key in CHECKS:
        reached, passed, detail = verdict[key]
        results.append((key, passed))
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if reached and not passed else 'no'} -- {detail[:600]}")
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TESTBED})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
