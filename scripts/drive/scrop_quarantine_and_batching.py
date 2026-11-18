"""Acceptance drive for "The slow checks run once per landing, not once per task, and flaky tests are
quarantined" (spec/changes/the-slow-checks-run-once-per-landing-not-once-per-task-and-flaky-tests-
are-quarantined, FR-1 enters-on-a-flip, FR-2 quarantined-failure-excused, FR-3 no-confirmation-
rerun, FR-7 leaves-after-passes, FR-10 fix-task-on-entry, FR-12 landing-checks-run-once). Written
failing first (SCROP-1): on the pre-build code no test is ever quarantined, so a flaky test's failure
is always re-run to confirm it and nothing names it quarantined.

Drives a trial Hub on :8010 (never :8000). `--start-hub` starts one from THIS checkout's source on
`--port` (8010 by default) with a scratch database of its own, and stops it at the end; without it
the drive uses the Hub already answering at `--hub`. Every run makes its own scratch under
~/Documents/aw-scrop-<time>/ and removes it and its projects at the end (`--keep` leaves them).

The scratch project has one agent, `builder` (Haiku; never started), and two checks behind
`gate.py`, the same pytest with `--junitxml` (xunit2: no file per test, so FR-6 never voids an
excuse here) and a re-run command: `pytest` at phase `review` and `pytest-landing` at phase
`landing`, which first sleeps `--landing-seconds` (240 by default). That sleep stands in for this
project's own landing-only `hub-tests` (about 27 minutes): FR-12 is about a landing check slower
than the spread of the approvals, and a check that ends in seconds lands each approval alone,
whatever the queue does. Each invocation is logged to `<scratch>/runs.jsonl` with its commit and
arguments, so a confirmation re-run (`--rerun ...`) is visible beside the route's own record of it.

The seeded test `test_quar::test_quar` (Q) passes unless the tree holds `arm-q.txt`. When it does,
it reads `<scratch>/q-mode`: a number N fails it and counts down (1 is a flip on today's code: the
first attempt fails and the confirmation re-run passes), `always` fails it every time. Only the
runner task R's work adds `arm-q.txt`, so main and the batching tasks never fail Q.

R is one hand-made task, on no loop, flow or build. Before each of its runs the drive commits a new
file to R's branch -- a pass is reused for an identical tree, and a reused pass records no history
-- and starts the run with the operator's `POST /projects/{id}/tasks/{task}/checks/run`.

Steps (one numbered run of R each, `R<n>`):
  enters     R1 flips Q, R2..R19 pass it, R20 flips it: 20 runs, 2 flips, rate 0.1. PASS needs Q
             absent from the quarantine list after R19 and present after R20, for check `pytest`,
             with its time of entry (ac-enters).
  fix        on entry, the quarantine entry names an open fix task that names Q, and exactly one
             open task names Q. The known-failing list files none before: a pre-review flip whose
             xunit2 report names no file counts as the task's own (`touched_tests`), so R1's and
             R20's runs fail and Q is never listed. The "already has one" half of ac-fix-task is
             Q's re-entry at R29, while its first fix task is still open.
  excused    R21 fails Q once. PASS needs R21 passed, still in review, its `pytest` result naming
             Q in `quarantined_tests` (ac-excused-passes), and neither `confirmed` nor `flaky` on
             that result and no `--rerun` invocation logged for it (ac-no-rerun).
  leaves     with the exit number set to 3: R22, R23 pass, R24 fails Q, R25..R27 pass. PASS needs Q
             still quarantined after R24 and after R26, and gone after R27 (ac-leaves); its fix task
             then has a note naming quarantine and is still open (ac-fix-task).
  no-reentry R28 fails Q outright (`always`), its rate still above 0.05. PASS needs Q not
             quarantined after R28, and quarantined after R29 flips it again, with still exactly one
             open fix task naming Q (ac-no-reentry-without-flip, ac-fix-task).
  batching   five tasks B1..B5, each a new file, their pre-review runs passed, approved one every
             60 s (four minutes). PASS needs every one landed, `pytest-landing` executed (not
             skipped, not reused) at most twice over every task_check_runs row, and each B with a
             pre-review run whose `pytest` result passed (ac-batching).

The quarantine contract this drive assumes of the build is the constants below: `QUARANTINE_ROUTE`
and its entry fields (shaped as the known-failing list's entries), the result field
`EXCUSED_FIELD`, and the settings key `EXIT_SETTING`. Where the build names them otherwise, the
run-the-drive task changes these constants and says so.

Ends with one baseline line per criterion the drive covers,
  check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <first failing assertion>
which is what the drive task's `drive_baseline` evidence carries. Exit 1 when any check fails.

    py -3.11 scripts/drive/scrop_quarantine_and_batching.py --start-hub
    py -3.11 scripts/drive/scrop_quarantine_and_batching.py --hub http://127.0.0.1:8010 --keep
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[2]
TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-scrop-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-5-5"
GIT_ID = ["-c", "user.name=scrop", "-c", "user.email=scrop@drive"]
#: How often the Hub looks at main (`project_checks.WATCH_SECONDS`).
WATCH_SECONDS = 30
CHECK = "pytest"
LANDING_CHECK = "pytest-landing"
Q = "test_quar::test_quar"
SETTLED = ("landed", "sent_back", "not_landed")
CLOSED = ("approved", "rejected")
#: The project's quarantined tests (FR-11's list), answering `{"quarantined": [entry, ...]}`.
QUARANTINE_ROUTE = "/checks/quarantine"
QUARANTINE_LIST = "quarantined"
#: An entry's fields, as `known_failing.entry_view` names its own.
ENTRY_CHECK, ENTRY_TEST, ENTRY_AT, ENTRY_FIX = "check", "test", "entered_at", "fix_task"
#: On a check's result: the failing tests quarantine excused (FR-2). SCROP-4: the build names them
#: under `quarantine.tests`, each a quarantine snapshot with a `test` (`quarantine.RESULT_KEY`), not
#: as a flat `quarantined_tests` list of ids as SCROP-1 assumed.
EXCUSED_FIELD = "quarantine"


def excused_tests(result: dict) -> list[str]:
    """The test ids a check's result names as excused by quarantine."""
    record = result.get(EXCUSED_FIELD) if isinstance(result.get(EXCUSED_FIELD), dict) else {}
    return [str(t.get("test")) for t in record.get("tests") or [] if isinstance(t, dict)]


#: The project settings (FR-9): consecutive passes to leave.
EXIT_SETTING = "quarantine_exit_passes"
EXIT_PASSES = 3

GATE = r"""import json, pathlib, shutil, subprocess, sys, time
log, args = pathlib.Path(sys.argv[1]), sys.argv[2:]
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
began = time.time()
if args[:1] == ["landing"]:
    time.sleep(float(args[1]))
    args = args[2:]
targets = []
if args[:1] == ["--rerun"]:
    for t in args[1:]:
        mod, name = t.split("::", 1)
        targets.append(mod.replace(".", "/") + ".py::" + name)
run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                      "--junitxml=report.xml", *targets])
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"head": head, "args": sys.argv[2:], "began": began, "ran": time.time(),
                        "exit": run.returncode}) + "\n")
sys.exit(run.returncode)
"""
PASSING = "def test_one():\n    assert 1 + 1 == 2\n\n\ndef test_two():\n    assert 2 * 2 == 4\n"
QUAR = (
    "import pathlib\n\nMODE = pathlib.Path({mode!r})\n\n\n"
    "def test_quar():\n"
    "    if not pathlib.Path('arm-q.txt').exists():\n"
    "        return\n"
    "    mode = MODE.read_text().strip() if MODE.exists() else '0'\n"
    "    if mode == 'always':\n"
    "        raise AssertionError('quar: fails outright')\n"
    "    left = int(mode or 0)\n"
    "    if left > 0:\n"
    "        MODE.write_text(str(left - 1))\n"
    "    assert left <= 0, f'quar: {{left}} failure(s) left'\n"
)

failures: list[str] = []
#: Criterion -> whether the drive got as far as asserting it.
reached: dict[str, bool] = {
    "ac-enters": False,
    "ac-excused-passes": False,
    "ac-no-rerun": False,
    "ac-leaves": False,
    "ac-no-reentry-without-flip": False,
    "ac-fix-task": False,
    "ac-batching": False,
}
#: Criterion -> its first failing assertion.
first_failure: dict[str, str] = {}


def check(name: str, ok: bool, detail: str = "", criterion: str | None = None) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
    if criterion:
        reached[criterion] = True
    if not ok:
        failures.append(name)
        if criterion:
            first_failure.setdefault(criterion, f"{name} -- {detail}"[:400])
    return ok


def note(text: str) -> None:
    print(f"       {text}", flush=True)


# --- the Hub -----------------------------------------------------------------------------------


class Hub:
    def __init__(self, url: str, key: str) -> None:
        if url.rstrip("/").endswith(":8000"):
            raise SystemExit(":8000 is the operator's real instance. Never drive it.")
        self.url, self.key = url.rstrip("/"), key

    def request(self, method: str, path: str, body: object = None) -> tuple[int, object]:
        req = urllib.request.Request(self.url + "/api/v1" + path, method=method)
        req.add_header("Authorization", f"Bearer {self.key}")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=120) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(), exc.code
        except urllib.error.URLError as exc:
            return 0, str(exc)
        try:
            return status, json.loads(raw or b"null")
        except ValueError:
            return status, raw.decode("utf-8", "replace")

    def call(self, method: str, path: str, body: object = None) -> object:
        status, res = self.request(method, path, body)
        if status >= 300 or status == 0:
            raise RuntimeError(f"{method} {path} -> {status}: {json.dumps(res)[:800]}")
        return res


def hub_key(url: str) -> str:
    if os.environ.get("AW_KEY"):
        return os.environ["AW_KEY"]
    if url.rstrip("/").endswith(":8010") and TRIAL_KEY.exists():
        return TRIAL_KEY.read_text(encoding="utf-8").strip()
    with urllib.request.urlopen(url.rstrip("/") + "/api/v1/setup/token", timeout=10) as r:
        return json.loads(r.read())["api_key"]


def start_hub(port: int, home: pathlib.Path, key: str) -> subprocess.Popen:
    """A Hub from this checkout's source, on a scratch database. Nothing of the shell's own Hub
    reaches it: a drive run inside an agent turn inherits that turn's HUB_URL and credential."""
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(home / 'hub.db').as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = key
    log = open(home / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "hub.main:app",
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ],
        cwd=str(REPO / "hub"),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    hub = Hub(f"http://127.0.0.1:{port}", key)
    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"the Hub exited ({proc.returncode}); see {home / 'hub.log'}")
        if hub.request("GET", "/projects")[0] == 200:
            return proc
        time.sleep(1)
    stop_hub(proc)
    raise SystemExit(f"the Hub did not come up; see {home / 'hub.log'}")


def stop_hub(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


# --- scratch -----------------------------------------------------------------------------------


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *GIT_ID, *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {done.stderr.strip()[:500]}")
    return done.stdout.strip()


def rmtree(path: pathlib.Path) -> None:
    """Git marks objects read-only on Windows: clear the bit and retry."""

    def force(func, target, _exc):  # noqa: ANN001
        os.chmod(target, 0o700)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=force)
    if path.exists():
        print(f"  !! {path} still exists after removal")


def wait_for(what: str, test, minutes: float):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        found = test()
        if found:
            return found
        time.sleep(2)
    note(f"timed out waiting for {what}")
    return None


def as_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class Project:
    """A scratch project on the Hub with one agent, `builder`; removed after."""

    def __init__(self, hub: Hub, root: pathlib.Path) -> None:
        self.hub, self.root = hub, root
        self.id = hub.call("POST", "/projects/open", {"path": str(root)})["id"]
        note(f"project {self.id} at {root}")
        runner = hub.call(
            "POST",
            f"/projects/{self.id}/runners",
            {"name": "claude haiku (scrop)", "cli": "claude", "model": HAIKU},
        )
        hub.call(
            "POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]}
        )

    def settings(self) -> dict:
        return self.hub.call("GET", f"/projects/{self.id}/settings")

    def put_settings(self, changes: dict) -> tuple[int, object]:
        settings = self.settings()
        settings.update(changes)
        return self.hub.request("PUT", f"/projects/{self.id}/settings", settings)

    def new_task(self, title: str) -> str:
        """A hand-made task assigned to `builder`, created `pending`, so nothing starts a turn."""
        return self.hub.call(
            "POST",
            f"/projects/{self.id}/tasks",
            {"title": title, "description": "scrop drive", "assignee": "builder"},
        )["id"]

    def move(self, task: str, *statuses: str) -> None:
        for status in statuses:
            code, res = self.hub.request(
                "PATCH", f"/projects/{self.id}/tasks/{task}", {"status": status}
            )
            if code >= 300:
                note(f"moving {task} to {status} -> {code}: {json.dumps(res)[:300]}")

    def task(self, task: str) -> dict:
        return self.hub.call("GET", f"/projects/{self.id}/tasks/{task}")

    def tasks(self) -> list[dict]:
        return self.hub.call("GET", f"/projects/{self.id}/tasks?limit=1000").get("tasks") or []

    def landing(self, task: str) -> dict:
        view = self.hub.call("GET", f"/projects/{self.id}/tasks/{task}/checks")
        return view.get("landing") or {}

    def approve(self, task: str) -> None:
        """The operator's approval: into review first (`completed` has no edge to `approved`)."""
        if self.task(task).get("status") != "under_review":
            self.move(task, "under_review")
        self.move(task, "approved")

    def query(self, sql: str) -> list[dict]:
        """Rows of the dashboard query route as dicts; raises with the route's refusal."""
        code, res = self.hub.request("POST", f"/projects/{self.id}/dashboards/query", {"sql": sql})
        if code >= 300:
            raise RuntimeError(f"query refused ({code}): {json.dumps(res)[:400]}")
        return [dict(zip(res["columns"], row, strict=True)) for row in res["rows"]]

    def runs_of(self, task: str) -> list[dict]:
        rows = self.query(
            "select id, state, started_at, ended_at, merged_sha, results from task_check_runs "
            f"where task_id = '{task}' order by started_at"
        )
        for row in rows:
            row["results"] = as_json(row["results"]) or []
        return rows

    def run_row(self, run_id: str) -> dict:
        rows = self.query(
            "select id, state, started_at, ended_at, merged_sha, results from task_check_runs "
            f"where id = '{run_id}'"
        )
        if not rows:
            return {}
        rows[0]["results"] = as_json(rows[0]["results"]) or []
        return rows[0]

    def quarantined(self) -> tuple[list[dict] | None, str]:
        """The quarantine list, or `None` and why it could not be read."""
        code, res = self.hub.request("GET", f"/projects/{self.id}{QUARANTINE_ROUTE}")
        if code != 200 or not isinstance(res, dict):
            return None, f"GET {QUARANTINE_ROUTE} -> {code}: {json.dumps(res)[:200]}"
        return list(res.get(QUARANTINE_LIST) or []), ""

    def q_history(self) -> dict:
        rows = self.query(
            "select count(*) as runs, sum(outcome = 'flipped') as flips, "
            "sum(outcome = 'failed') as failed from test_history "
            f"where check_name = '{CHECK}' and test_id = '{Q}'"
        )
        return rows[0] if rows else {}

    def remove(self) -> None:
        self.hub.request("POST", f"/projects/{self.id}/agent/builder/stop", {})
        code, res = self.hub.request("DELETE", f"/projects/{self.id}")
        note(f"removed project {self.id}: HTTP {code}" + ("" if code < 300 else f" {res}"))


def result_of(row: dict, name: str) -> dict:
    for result in row.get("results") or []:
        if isinstance(result, dict) and result.get("name") == name:
            return result
    return {}


def runs_logged(log: pathlib.Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


class Runner:
    """The task R whose runs drive Q's history: one new commit and one pre-review run per call."""

    def __init__(self, project: Project, mode: pathlib.Path, log: pathlib.Path) -> None:
        self.project, self.mode, self.log = project, mode, log
        self.id = project.new_task("Runs the quarantined test")
        branch = f"agentweave/task/{self.id}"
        git(project.root, "branch", branch, git(project.root, "rev-parse", "HEAD"))
        self.work = project.root.parent / f"work-{self.id}"
        git(project.root, "worktree", "add", "-q", str(self.work), branch)
        (self.work / "arm-q.txt").write_text("arms test_quar\n", encoding="utf-8", newline="\n")
        git(self.work, "add", "arm-q.txt")
        git(self.work, "commit", "-qm", "arm test_quar")
        self.n = 0

    def run(self, mode: str) -> dict:
        """R<n+1> with Q's mode *mode*; its ended task_check_runs row (results parsed)."""
        self.n += 1
        label = f"R{self.n}"
        self.mode.write_text(mode, encoding="utf-8")
        rel = f"run-{self.n:02d}.txt"
        (self.work / rel).write_text(f"{label}\n", encoding="utf-8", newline="\n")
        git(self.work, "add", rel)
        git(self.work, "commit", "-qm", label)
        before = {r["id"] for r in self.project.runs_of(self.id)}
        status = self.project.task(self.id).get("status")
        if status not in ("completed", "under_review"):
            if status != "in_progress":
                self.project.move(self.id, "in_progress")
            self.project.move(self.id, "completed")  # which starts a run of its own
        # The previous run's row reads ended a moment before its job is done, and `checks/run`
        # answers `running` and starts nothing meanwhile: ask until a new row exists.
        deadline = time.time() + 120
        while not [x for x in self.project.runs_of(self.id) if x["id"] not in before]:
            if time.time() > deadline:
                raise RuntimeError(f"{label}: no run started (R {status})")
            asked = self.project.hub.call(
                "POST", f"/projects/{self.project.id}/tasks/{self.id}/checks/run", {}
            )
            if asked.get("run_id"):
                break
            time.sleep(2)
        row = wait_for(
            f"{label} to end",
            lambda: next(
                (
                    r
                    for r in self.project.runs_of(self.id)
                    if r["id"] not in before and r["state"] not in (None, "running", "queued")
                ),
                None,
            ),
            minutes=5,
        )
        if not row:
            seen = [(x["id"], x["state"]) for x in self.project.runs_of(self.id)]
            raise RuntimeError(
                f"{label} ({mode}) did not end: R {self.project.task(self.id).get('status')}"
                f", its runs {seen}"
            )
        res = result_of(row, CHECK)
        note(
            f"{label} mode={mode}: run {row['id']} {row['state']}; Q history {self.project.q_history()}"
            f"; result keys {sorted(res)}"
        )
        return row

    def reruns(self, row: dict) -> list[dict]:
        """The `--rerun` invocations gate.py logged on *row*'s merged commit."""
        return [
            r
            for r in runs_logged(self.log)
            if r["head"] == row.get("merged_sha") and "--rerun" in r["args"]
        ]

    def close(self) -> None:
        try:
            git(self.project.root, "worktree", "remove", "--force", str(self.work))
        except RuntimeError as exc:
            note(f"could not remove {self.work}: {exc}")


def q_entry(project: Project) -> tuple[dict | None, str]:
    listed, why = project.quarantined()
    if listed is None:
        return None, why
    for entry in listed:
        if entry.get(ENTRY_TEST) == Q and entry.get(ENTRY_CHECK) == CHECK:
            return entry, ""
    return None, f"listed: {json.dumps(listed)[:300]}"


def open_fix_tasks(project: Project, runner: str) -> list[dict]:
    """Open tasks other than R naming Q in their title or description."""
    return [
        t
        for t in project.tasks()
        if t["id"] != runner
        and t.get("status") not in CLOSED
        and Q in f"{t.get('title') or ''}\n{t.get('description') or ''}"
    ]


# --- the drive ---------------------------------------------------------------------------------


def drive(hub: Hub, keep: list, landing_seconds: int) -> None:
    root = SCRATCH / "project"
    root.mkdir(parents=True)
    log = SCRATCH / "runs.jsonl"
    mode = SCRATCH / "q-mode"
    (root / "gate.py").write_text(GATE, encoding="utf-8", newline="\n")
    (root / "test_ok.py").write_text(PASSING, encoding="utf-8", newline="\n")
    (root / "test_quar.py").write_text(
        QUAR.format(mode=mode.as_posix()), encoding="utf-8", newline="\n"
    )
    (root / ".gitignore").write_text("report.xml\n__pycache__/\n", encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "passing tests, the seeded test, and the gated check")
    project = Project(hub, root)
    keep.append(project)
    py = pathlib.Path(sys.executable).as_posix()
    gate = f'"{py}" gate.py {log.as_posix()}'
    checks = [
        {
            "name": name,
            "command": command,
            "timeout_seconds": 900,
            "report_path": "report.xml",
            "rerun_command": f"{command} --rerun {{tests}}",
            "phase": phase,
        }
        for name, command, phase in (
            (CHECK, gate, "review"),
            (LANDING_CHECK, f"{gate} landing {landing_seconds}", "landing"),
        )
    ]
    code, res = project.put_settings({"main_branch": "master", "checks": checks})
    if code >= 300:
        raise RuntimeError(f"saving the checks -> {code}: {res}")
    # The exit number apart, so a Hub that refuses the key still saves the checks.
    code, res = project.put_settings({EXIT_SETTING: EXIT_PASSES})
    exit_set = project.settings().get(EXIT_SETTING)
    note(f"PUT {EXIT_SETTING}={EXIT_PASSES} -> {code}; read back {exit_set!r}")
    time.sleep(WATCH_SECONDS + 10)  # the Hub's first look at main only records its tip

    r = Runner(project, mode, log)
    try:
        quarantine_steps(project, r, exit_set)
    finally:
        r.close()
    batching(project, landing_seconds)


def quarantine_steps(project: Project, r: Runner, exit_set: object) -> None:
    # enters: R1 flips, R2..R19 pass, R20 flips.
    row = r.run("1")
    check(
        "enters: premise -- R1 recorded Q flipped",
        project.q_history() == {"runs": 1, "flips": 1, "failed": 0},
        json.dumps(project.q_history()),
        "ac-enters",
    )
    for _ in range(18):
        row = r.run("0")
    hist = project.q_history()
    check(
        "enters: premise -- 19 runs of Q, 1 flipped",
        hist.get("runs") == 19 and hist.get("flips") == 1,
        json.dumps(hist),
        "ac-enters",
    )
    entry, why = q_entry(project)
    check(
        "enters: Q is not quarantined at 19 runs (no flake rate yet)",
        entry is None and not why.startswith("GET"),
        why or json.dumps(entry),
        "ac-enters",
    )
    row = r.run("1")
    hist = project.q_history()
    check(
        "enters: premise -- R20 recorded Q's second flip (20 runs, 2 flips, rate 0.1)",
        hist.get("runs") == 20 and hist.get("flips") == 2,
        json.dumps(hist),
        "ac-enters",
    )
    entry, why = q_entry(project)
    check(
        f"enters: Q is quarantined for {CHECK}, with the time it entered",
        bool(entry and entry.get(ENTRY_AT)),
        why or json.dumps(entry),
        "ac-enters",
    )

    # fix: one open fix task, the entry's own.
    fixes = open_fix_tasks(project, r.id)
    fix_id = ((entry or {}).get(ENTRY_FIX) or {}).get("id")
    check(
        "fix: exactly one open task names Q",
        len(fixes) == 1,
        json.dumps([(t["id"], t.get("title")) for t in fixes])[:400],
        "ac-fix-task",
    )
    check(
        "fix: Q's quarantine entry names that open fix task",
        bool(fix_id) and fix_id in {t["id"] for t in fixes},
        f"entry fix task {fix_id!r}; open {[t['id'] for t in fixes]}",
        "ac-fix-task",
    )
    notes_before = json.dumps(project.task(fix_id).get("notes")) if fix_id else ""

    # excused: R21 fails Q, which is quarantined.
    row = r.run("1")
    res = result_of(row, CHECK)
    status = project.task(r.id).get("status")
    check(
        "excused: R21's run passed and R is still in review",
        row["state"] == "passed" and status in ("completed", "under_review"),
        f"run {row['state']}; task {status}",
        "ac-excused-passes",
    )
    check(
        f"excused: R21's {CHECK} result names Q in {EXCUSED_FIELD}",
        Q in excused_tests(res),
        json.dumps({k: res.get(k) for k in (EXCUSED_FIELD, "failed_tests", "flaky_tests")}),
        "ac-excused-passes",
    )
    reruns = r.reruns(row)
    check(
        "no-rerun: R21's result made no confirmation re-run (no `confirmed`, no `flaky`)",
        not res.get("confirmed") and not res.get("flaky"),
        json.dumps({k: res.get(k) for k in ("confirmed", "flaky")})[:400],
        "ac-no-rerun",
    )
    check(
        "no-rerun: gate.py logged no --rerun invocation on R21's commit",
        not reruns,
        json.dumps(reruns)[:400],
        "ac-no-rerun",
    )

    # leaves: exit 3; pass, pass, fail, pass, pass, pass.
    check(
        f"leaves: premise -- the project's {EXIT_SETTING} reads {EXIT_PASSES}",
        exit_set == EXIT_PASSES,
        f"read back {exit_set!r}",
        "ac-leaves",
    )
    r.run("0")
    r.run("0")
    r.run("1")
    entry, why = q_entry(project)
    check(
        "leaves: Q is still quarantined after pass, pass, fail (R22-R24)",
        entry is not None,
        why or json.dumps(entry),
        "ac-leaves",
    )
    r.run("0")
    r.run("0")
    entry, why = q_entry(project)
    check(
        "leaves: Q is still quarantined after two passes that follow the fail (R26)",
        entry is not None,
        why or json.dumps(entry),
        "ac-leaves",
    )
    r.run("0")
    listed, why = project.quarantined()
    entry, _ = q_entry(project)
    check(
        "leaves: Q left quarantine after the third pass that follows the fail (R27)",
        listed is not None and entry is None,
        why or json.dumps(entry),
        "ac-leaves",
    )
    fix = project.task(fix_id) if fix_id else {}
    notes_after = json.dumps(fix.get("notes"))
    check(
        "fix: on leaving, the fix task gained a note naming quarantine and is still open",
        bool(fix)
        and fix.get("status") not in CLOSED
        and notes_after != notes_before
        and "quarantin" in notes_after.lower(),
        f"status {fix.get('status')!r}; notes {notes_after[-300:]}",
        "ac-fix-task",
    )

    # no-reentry: R28 fails Q outright; R29 flips it.
    r.run("always")
    hist = project.q_history()
    rate = (hist.get("flips") or 0) / (hist.get("runs") or 1)
    check(
        "no-reentry: premise -- Q's rate is still above 0.05 after its outright failure",
        rate > 0.05,
        json.dumps({**hist, "rate": round(rate, 4)}),
        "ac-no-reentry-without-flip",
    )
    listed, why = project.quarantined()
    entry, _ = q_entry(project)
    check(
        "no-reentry: the outright failure (R28) did not put Q back in quarantine",
        listed is not None and entry is None,
        why or json.dumps(entry),
        "ac-no-reentry-without-flip",
    )
    status = project.task(r.id).get("status")
    if status not in ("completed", "under_review"):
        note(f"R is {status} after R28: stopping builder; R29 completes it again")
        project.hub.request("POST", f"/projects/{project.id}/agent/builder/stop", {})
    flips = project.q_history().get("flips") or 0
    r.run("1")
    check(
        "no-reentry: premise -- R29 recorded a new flip of Q",
        (project.q_history().get("flips") or 0) == flips + 1,
        json.dumps(project.q_history()),
        "ac-no-reentry-without-flip",
    )
    entry, why = q_entry(project)
    check(
        "no-reentry: the new flip (R29) put Q back in quarantine",
        entry is not None,
        why or json.dumps(entry),
        "ac-no-reentry-without-flip",
    )
    fixes = open_fix_tasks(project, r.id)
    again = ((entry or {}).get(ENTRY_FIX) or {}).get("id")
    check(
        "fix: re-entry filed no second fix task; the entry names the same open one",
        len(fixes) == 1 and bool(fix_id) and again == fix_id,
        f"open {[t['id'] for t in fixes]}; entry {again!r}; first {fix_id!r}",
        "ac-fix-task",
    )


def batching(project: Project, landing_seconds: int) -> None:
    tasks = []
    base = git(project.root, "rev-parse", "HEAD")
    for n in range(1, 6):
        task = project.new_task(f"Batch task B{n}")
        branch = f"agentweave/task/{task}"
        git(project.root, "branch", branch, base)
        work = project.root.parent / f"work-{task}"
        git(project.root, "worktree", "add", "-q", str(work), branch)
        try:
            (work / f"b{n}.txt").write_text(f"B{n}\n", encoding="utf-8", newline="\n")
            git(work, "add", f"b{n}.txt")
            git(work, "commit", "-qm", f"B{n}")
        finally:
            git(project.root, "worktree", "remove", "--force", str(work))
        project.move(task, "in_progress", "completed")
        tasks.append(task)

    def passed_pre_review(task: str) -> bool:
        return any(
            row["state"] == "passed" and result_of(row, CHECK).get("exit_code") == 0
            for row in project.runs_of(task)
        )

    ready = wait_for(
        "every B's pre-review run to pass",
        lambda: all(passed_pre_review(t) for t in tasks),
        minutes=10,
    )
    if not check(
        "batching: premise -- B1..B5 each have a passing pre-review run",
        bool(ready),
        json.dumps({t: [r["state"] for r in project.runs_of(t)] for t in tasks}),
        "ac-batching",
    ):
        return
    for i, task in enumerate(tasks):
        if i:
            time.sleep(60)
        project.approve(task)
        note(f"approved B{i + 1} {task} at {time.strftime('%H:%M:%S')}")
    views = wait_for(
        "every B to settle",
        lambda: (lambda v: v if all(x.get("state") in SETTLED for x in v) else None)(
            [project.landing(t) for t in tasks]
        ),
        minutes=10 + 3 * landing_seconds / 60,
    ) or [project.landing(t) for t in tasks]
    check(
        "batching: premise -- B1..B5 all landed",
        all(v.get("state") == "landed" for v in views),
        json.dumps([v.get("state") for v in views]),
        "ac-batching",
    )
    rows = project.query("select id, task_id, results from task_check_runs")
    executed = []
    for row in rows:
        result = result_of({"results": as_json(row["results"]) or []}, LANDING_CHECK)
        if result and not result.get("skipped") and not result.get("reused_from"):
            executed.append(row["id"])
    batches = project.query("select id, state, check_run_id from landing_batches")
    note(f"landing batches {json.dumps(batches)[:600]}")
    check(
        f"batching: {LANDING_CHECK} executed at most twice across landing all five",
        len(executed) <= 2,
        f"executed in {len(executed)} run(s): {executed}",
        "ac-batching",
    )
    check(
        f"batching: each B has a pre-review result for {CHECK}",
        all(passed_pre_review(t) for t in tasks),
        "",
        "ac-batching",
    )


def baseline() -> None:
    """One line per criterion the drive covers, as the `drive_baseline` evidence reads them."""
    for key, got_there in reached.items():
        failed = key in first_failure
        print(
            f"check {key}: reached={'yes' if got_there else 'no'} "
            f"failed_at_assertion={'yes' if got_there and failed else 'no'} -- "
            + (first_failure.get(key) or "all assertions passed"),
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hub", default="http://127.0.0.1:8010")
    parser.add_argument(
        "--start-hub",
        action="store_true",
        help="start a Hub from this checkout on --port with a scratch database",
    )
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument(
        "--landing-seconds", type=int, default=240, help="how long the landing-only check takes"
    )
    parser.add_argument("--keep", action="store_true", help="leave the scratch and its projects")
    args = parser.parse_args()
    if args.port == 8000:
        raise SystemExit(":8000 is the operator's real instance. Never drive it.")
    SCRATCH.mkdir(parents=True)
    print(f"scratch {SCRATCH}", flush=True)
    proc = None
    if args.start_hub:
        key = "aw_live_" + secrets.token_hex(16)
        url = f"http://127.0.0.1:{args.port}"
        if Hub(url, key).request("GET", "/projects")[0] != 0:
            raise SystemExit(f"something already answers on {url}: stop it or drop --start-hub")
        proc = start_hub(args.port, SCRATCH, key)
        hub = Hub(url, key)
        print(f"started a Hub from {REPO} on {url} (database {SCRATCH / 'hub.db'})", flush=True)
    else:
        hub = Hub(args.hub, hub_key(args.hub))
        try:
            urllib.request.urlopen(hub.url + "/health", timeout=10).read()
        except OSError as exc:
            raise SystemExit(f"no Hub at {args.hub}: {exc}") from exc
        print(f"Hub {args.hub}", flush=True)
    projects: list[Project] = []
    try:
        try:
            drive(hub, projects, args.landing_seconds)
        except Exception as exc:  # a broken drive is a failure, never a pass
            check("the drive ran to the end", False, repr(exc)[:600])
    finally:
        for project in projects:
            if args.keep:
                note(f"kept project {project.id}")
                continue
            try:
                project.remove()
            except Exception as exc:  # noqa: BLE001 -- clean up regardless
                note(f"could not remove {project.id}: {exc!r}")
        if proc is not None:
            stop_hub(proc)
        if args.keep:
            note(f"kept {SCRATCH}")
        else:
            time.sleep(2)
            rmtree(SCRATCH)
    print("FAILED: " + ", ".join(failures) if failures else "ALL PASS", flush=True)
    baseline()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
