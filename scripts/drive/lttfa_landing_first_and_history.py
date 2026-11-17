"""Acceptance drive for "Landing time and test flakiness are measured"
(spec/changes/landing-time-and-test-flakiness-are-measured, FR-3 landing-goes-first, FR-5
test-history-recorded, FR-8 landing-dashboard; FR-7's batch record is read on the way). Written
failing first (LTTFA-1): on the pre-build code check slots are served in arrival order, no per-test
history is kept, landing batches record no wait or run count, and no project has the dashboard.

Drives a trial Hub on :8010 (never :8000). `--start-hub` starts one from THIS checkout's source on
`--port` (8010 by default) with a scratch database of its own, and stops it at the end; without it
the drive uses the Hub already answering at `--hub`. Every run makes its own scratch under
~/Documents/aw-lttfa-<time>/ and removes it and its projects at the end (`--keep` leaves them).

The scratch project has one agent, `builder` (Haiku; never started), and two checks behind
`gate.py`: `pytest` at phase `review` and `pytest-landing` at phase `landing`, the same pytest with
`--junitxml` (pytest's default xunit2 family, which names no file per test) and a re-run command.
Two checks, not one at `both`: the batch's tree equals L's pre-review tree, and one check would
reuse that pass and run nothing at landing. Before pytest runs, `gate.py` waits while a gate file
`<scratch>/gates/<name>` exists for any `hold-<name>.txt` in the checkout, so a task whose work adds
`hold-h1.txt` holds its check slot until the drive deletes `gates/h1`. Each invocation's report is
copied to `<scratch>/reports/` and logged to `<scratch>/runs.jsonl` with the commit it ran on.

Tasks are made by hand, on no loop, flow or build; the drive commits each task's work on its own
branch, moves it to completed, starts its pre-review run with the operator's
`POST /projects/{id}/tasks/{task}/checks/run`, and approves it as the operator.

Concurrency. FR-10's setting does not exist on the pre-build code; the Hub runs
`--slots` (default 2, today's `MAX_CONCURRENT_RUNS`) check runs at once. The drive fills every slot
with a holder, so freeing one holder is the spec's "concurrency 1 with the slot held": one slot
frees and two runs wait for it.

Steps:
  order    L (adds hold-l.txt) has its pre-review run pass while nothing is held, then the holders
           H1..Hn take every slot. W (adds hold-w.txt and a test that always fails) has its
           pre-review run queued; then L is approved and its landing batch's run queues. H1 is
           released. PASS needs task_check_runs.slot_at of the batch's run (landing_batches.
           check_run_id) earlier than W's run's (ac-landing-jumps-queue).
  history  W's pre-review run named 3 passing tests and 1 failing one in an xunit2 report. PASS
           needs 4 rows of test_history for the run (check_run_id), whose test_id set equals the
           report's `classname::name` ids, whose outcome is passed/failed as the report says, and
           whose file is empty or null (ac-history-xunit2).
  flip     test_flaky fails once in L's tree (a counter outside the project, armed to 1 after L's
           pre-review run) and passes on its confirmation. PASS needs L to land and the
           test_history row of `test_flaky::test_flaky` for the batch's run to read outcome
           'flipped', phase 'landing' (ac-flip-recorded).
  batch    the batch's landing_batches row carries ready_at, slot_at, checks_ended_at,
           check_runs >= 2 and outcome 'landed' (FR-7, read on the way; not a baseline check).
  dash     on this project and on a second, empty project made after it, GET .../dashboards
           lists 'Landing time and flaky tests', and GET .../dashboards/{id}/run returns every
           panel with error null (ac-dashboard-every-project).

The table and column names above are this drive's contract with the build (`HISTORY` and
`BATCH_FIELDS` below), read through the dashboard query route `POST /projects/{id}/dashboards/query`.
Where the build names them otherwise, the run-the-drive task changes these constants and says so.

Ends with one baseline line per criterion the drive covers,
  check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <first failing assertion>
which is what the drive task's `drive_baseline` evidence carries. Exit 1 when any check fails.

    py -3.11 scripts/drive/lttfa_landing_first_and_history.py --start-hub
    py -3.11 scripts/drive/lttfa_landing_first_and_history.py --hub http://127.0.0.1:8010 --keep
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
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[2]
TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-lttfa-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-5-5"
GIT_ID = ["-c", "user.name=lttfa", "-c", "user.email=lttfa@drive"]
#: How often the Hub looks at main (`project_checks.WATCH_SECONDS`).
WATCH_SECONDS = 30
CHECK = "pytest"
LANDING_CHECK = "pytest-landing"
FLAKY_ID = "test_flaky::test_flaky"
DASHBOARD = "Landing time and flaky tests"
SETTLED = ("landed", "sent_back", "not_landed")
#: The per-test history (FR-5): table and the columns the drive reads.
HISTORY = "test_history"
HISTORY_COLUMNS = (
    "check_name",
    "test_id",
    "file",
    "outcome",
    "check_run_id",
    "phase",
    "commit_sha",
    "recorded_at",
)
#: The batch's landing record (FR-7), on `landing_batches`.
BATCH_FIELDS = ("ready_at", "slot_at", "checks_ended_at", "check_runs", "outcome")

GATE = r"""import json, pathlib, shutil, subprocess, sys, time
log, gates, args = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3:]
if args[:1] == ["landing"]:
    args = args[1:]
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
holds = sorted(p.name[len("hold-"):-len(".txt")] for p in pathlib.Path(".").glob("hold-*.txt"))
began = time.time()
while any((gates / name).exists() for name in holds):
    time.sleep(0.5)
targets = []
if args[:1] == ["--rerun"]:
    for t in args[1:]:
        mod, name = t.split("::", 1)
        targets.append(mod.replace(".", "/") + ".py::" + name)
run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                      "--junitxml=report.xml", *targets])
reports = log.parent / "reports"
reports.mkdir(exist_ok=True)
copy = reports / f"{head[:12]}-{time.time_ns()}.xml"
if pathlib.Path("report.xml").exists():
    shutil.copy("report.xml", copy)
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"head": head, "args": args, "holds": holds, "began": began,
                        "ran": time.time(), "exit": run.returncode, "report": str(copy)}) + "\n")
sys.exit(run.returncode)
"""
PASSING = "def test_one():\n    assert 1 + 1 == 2\n\n\ndef test_two():\n    assert 2 * 2 == 4\n"
# Fails, in L's tree only, while the counter outside the project is above zero, spending one.
FLAKY = (
    "import pathlib\n\nCOUNTER = pathlib.Path({counter!r})\n\n\n"
    "def test_flaky():\n"
    "    if not pathlib.Path('hold-l.txt').exists():\n"
    "        return\n"
    "    left = int(COUNTER.read_text()) if COUNTER.exists() else 0\n"
    "    if left > 0:\n"
    "        COUNTER.write_text(str(left - 1))\n"
    "    assert left <= 0, f'flaky: {{left}} failure(s) left on the counter'\n"
)
BROKEN = "def test_broken():\n    assert 1 + 1 == 3, 'this task breaks a test'\n"

failures: list[str] = []
#: Criterion -> whether the drive got as far as asserting it.
reached: dict[str, bool] = {
    "ac-landing-jumps-queue": False,
    "ac-history-xunit2": False,
    "ac-flip-recorded": False,
    "ac-dashboard-every-project": False,
}
#: Criterion -> its first failing assertion.
first_failure: dict[str, str] = {}


def check(name: str, ok: bool, detail: str = "", criterion: str | None = None) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
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


class Project:
    """A scratch project on the Hub with one agent, `builder`; removed after."""

    def __init__(self, hub: Hub, root: pathlib.Path) -> None:
        self.hub, self.root = hub, root
        self.id = hub.call("POST", "/projects/open", {"path": str(root)})["id"]
        note(f"project {self.id} at {root}")
        runner = hub.call(
            "POST",
            f"/projects/{self.id}/runners",
            {"name": "claude haiku (lttfa)", "cli": "claude", "model": HAIKU},
        )
        hub.call(
            "POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]}
        )

    def apply_checks(self, checks: list, main_branch: str) -> tuple[int, object]:
        settings = self.hub.call("GET", f"/projects/{self.id}/settings")
        settings.update({"main_branch": main_branch, "checks": checks})
        return self.hub.request("PUT", f"/projects/{self.id}/settings", settings)

    def task_with_work(self, title: str, files: dict) -> str:
        """A hand-made task assigned to `builder`, its work *files* committed on its own branch,
        moved to completed. Created `pending`, so nothing starts a turn for it."""
        task = self.hub.call(
            "POST",
            f"/projects/{self.id}/tasks",
            {"title": title, "description": "lttfa drive", "assignee": "builder"},
        )["id"]
        base = git(self.root, "rev-parse", "HEAD")
        branch = f"agentweave/task/{task}"
        git(self.root, "branch", branch, base)
        work = self.root.parent / f"work-{task}"
        git(self.root, "worktree", "add", "-q", str(work), branch)
        try:
            for rel, text in files.items():
                (work / rel).write_text(text, encoding="utf-8", newline="\n")
                git(work, "add", rel)
            git(work, "commit", "-qm", title)
        finally:
            git(self.root, "worktree", "remove", "--force", str(work))
        for status in ("in_progress", "completed"):
            code, res = self.hub.request(
                "PATCH", f"/projects/{self.id}/tasks/{task}", {"status": status}
            )
            if code >= 300:
                note(f"moving {task} to {status} -> {code}: {json.dumps(res)[:300]}")
        return task

    def pre_review_run(self, task: str) -> str | None:
        """The task's pre-review run. Moving it to completed already started one, and `checks/run`
        then answers `run_id` null (one is executing): read that one from task_check_runs."""
        res = self.hub.call("POST", f"/projects/{self.id}/tasks/{task}/checks/run", {})
        if res.get("run_id"):
            return res["run_id"]
        # The completion's run writes its row only once its merged commit is built.
        rows = wait_for(
            f"{task}'s pre-review run row",
            lambda: self.query(
                f"select id from task_check_runs where task_id = '{task}' "
                "order by started_at desc limit 1"
            ),
            minutes=1,
        )
        return rows[0]["id"] if rows else None

    def task(self, task: str) -> dict:
        return self.hub.call("GET", f"/projects/{self.id}/tasks/{task}")

    def landing(self, task: str) -> dict:
        view = self.hub.call("GET", f"/projects/{self.id}/tasks/{task}/checks")
        return view.get("landing") or {}

    def approve(self, task: str) -> None:
        """The operator's approval: into review first (`completed` has no edge to `approved`)."""
        if self.task(task).get("status") != "under_review":
            code, res = self.hub.request(
                "PATCH", f"/projects/{self.id}/tasks/{task}", {"status": "under_review"}
            )
            if code >= 300:
                note(f"moving {task} to under_review -> {code}: {json.dumps(res)[:300]}")
        code, res = self.hub.request(
            "PATCH", f"/projects/{self.id}/tasks/{task}", {"status": "approved"}
        )
        if code >= 300:
            note(f"moving {task} to approved -> {code}: {json.dumps(res)[:300]}")

    def query(self, sql: str) -> list[dict]:
        """Rows of the dashboard query route as dicts; raises with the route's refusal."""
        code, res = self.hub.request("POST", f"/projects/{self.id}/dashboards/query", {"sql": sql})
        if code >= 300:
            raise RuntimeError(f"query refused ({code}): {json.dumps(res)[:400]}")
        return [dict(zip(res["columns"], row, strict=True)) for row in res["rows"]]

    def run_row(self, run_id: str) -> dict:
        rows = self.query(
            "select id, state, started_at, slot_at, ended_at, merged_sha from task_check_runs "
            f"where id = '{run_id}'"
        )
        return rows[0] if rows else {}

    def remove(self) -> None:
        code, res = self.hub.request("POST", f"/projects/{self.id}/agent/builder/stop", {})
        code, res = self.hub.request("DELETE", f"/projects/{self.id}")
        note(f"removed project {self.id}: HTTP {code}" + ("" if code < 300 else f" {res}"))


def wait_for(what: str, test, minutes: float):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        found = test()
        if found:
            return found
        time.sleep(3)
    note(f"timed out waiting for {what}")
    return None


def runs_logged(log: pathlib.Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def report_cases(path: str) -> dict[str, str]:
    """A JUnit report's testcases as `classname::name` -> passed|failed (the Hub's id, FR-2)."""
    cases = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        test = f"{case.get('classname') or ''}::{case.get('name') or ''}"
        bad = any(child.tag in ("failure", "error") for child in case)
        cases[test] = "failed" if bad else "passed"
    return cases


def history(project: Project, run_id: str) -> list[dict]:
    return project.query(
        f"select {', '.join(HISTORY_COLUMNS)} from {HISTORY} where check_run_id = '{run_id}'"
    )


# --- the drive ---------------------------------------------------------------------------------


def drive(hub: Hub, keep: list, slots: int) -> None:
    root = SCRATCH / "project"
    root.mkdir(parents=True)
    gates = SCRATCH / "gates"
    gates.mkdir()
    log = SCRATCH / "runs.jsonl"
    counter = SCRATCH / "flaky-count"
    (root / "gate.py").write_text(GATE, encoding="utf-8", newline="\n")
    (root / "test_ok.py").write_text(PASSING, encoding="utf-8", newline="\n")
    (root / "test_flaky.py").write_text(
        FLAKY.format(counter=counter.as_posix()), encoding="utf-8", newline="\n"
    )
    (root / ".gitignore").write_text("report.xml\n__pycache__/\n", encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "passing tests, a flaky one, and the gated check")
    project = Project(hub, root)
    keep.append(project)
    py = pathlib.Path(sys.executable).as_posix()
    gate = f'"{py}" gate.py {log.as_posix()} {gates.as_posix()}'
    code, res = project.apply_checks(
        [
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
                (LANDING_CHECK, f"{gate} landing", "landing"),
            )
        ],
        "master",
    )
    if code >= 300:
        raise RuntimeError(f"saving the check -> {code}: {res}")
    time.sleep(WATCH_SECONDS + 10)  # the Hub's first look at main only records its tip

    # L's own pre-review run passes now, while nothing is held, so its approval waits on nothing.
    land = project.task_with_work("Lands past a flaky test", {"hold-l.txt": "l\n"})
    first = project.pre_review_run(land)
    note(f"L {land}: pre-review run {first}")
    if not first:
        raise RuntimeError("no pre-review run started for the task")
    done = wait_for(
        "L's pre-review run to end",
        lambda: (lambda r: r if r.get("state") not in (None, "running") else None)(
            project.run_row(first or "")
        ),
        minutes=5,
    )
    note(f"L's pre-review run: {done}")
    counter.write_text("1", encoding="utf-8")  # L's landing run fails test_flaky once

    # The holders take every slot.
    holders = []
    for n in range(1, slots + 1):
        (gates / f"h{n}").write_text("held", encoding="utf-8")
        task = project.task_with_work(f"Holds slot {n}", {f"hold-h{n}.txt": "h\n"})
        holders.append((n, task, project.pre_review_run(task)))
    for n, task, run in holders:
        note(f"H{n} {task}: run {run}")
        if not run:
            raise RuntimeError("no pre-review run started for the task")
    held = wait_for(
        "every holder to hold a slot",
        lambda: all(project.run_row(run or "").get("slot_at") for _, _, run in holders),
        minutes=5,
    )
    if not check(
        "order: premise -- every check slot is held",
        bool(held),
        json.dumps([project.run_row(run or "") for _, _, run in holders])[:600],
        "ac-landing-jumps-queue",
    ):
        return

    # W's pre-review run waits first; then L's landing run waits behind it.
    wait = project.task_with_work(
        "Breaks a test (waits for review)", {"hold-w.txt": "w\n", "test_broken.py": BROKEN}
    )
    w_run = project.pre_review_run(wait)
    note(f"W {wait}: pre-review run {w_run}")
    if not w_run:
        raise RuntimeError("no pre-review run started for the task")
    time.sleep(3)
    project.approve(land)
    batch_id = wait_for(
        "L's landing batch",
        lambda: (project.landing(land).get("batch") or {}).get("id"),
        minutes=5,
    )
    l_run = None
    if batch_id:
        l_run = wait_for(
            "the batch's check run to wait for a slot",
            lambda: (
                project.query(f"select check_run_id from landing_batches where id = '{batch_id}'")
                or [{}]
            )[0].get("check_run_id"),
            minutes=3,
        )
    note(f"L's batch {batch_id}: run {l_run}")
    w_row, l_row = project.run_row(w_run or ""), project.run_row(l_run or "")
    note(f"before the slot frees: W {w_row}; L {l_row}")
    queued = bool(w_row and l_row) and not w_row.get("slot_at") and not l_row.get("slot_at")
    if not check(
        "order: premise -- the pre-review run and then the landing run wait, neither has a slot",
        queued and w_row["started_at"] < l_row["started_at"],
        f"W {w_row}; L {l_row}",
        "ac-landing-jumps-queue",
    ):
        return
    reached["ac-landing-jumps-queue"] = True
    (gates / "h1").unlink()  # one slot frees
    wait_for(
        "both waiting runs to get a slot",
        lambda: project.run_row(w_run).get("slot_at") and project.run_row(l_run).get("slot_at"),
        minutes=10,
    )
    w_row, l_row = project.run_row(w_run), project.run_row(l_run)
    note(f"after: W slot_at {w_row.get('slot_at')}; L slot_at {l_row.get('slot_at')}")
    check(
        "order: the landing run got the freed slot before the pre-review run that waited first",
        bool(l_row.get("slot_at"))
        and (not w_row.get("slot_at") or l_row["slot_at"] < w_row["slot_at"]),
        f"task_check_runs.slot_at landing {l_row.get('slot_at')} vs pre-review "
        f"{w_row.get('slot_at')}",
        "ac-landing-jumps-queue",
    )
    for path in gates.iterdir():  # every holder goes; the rest need no slot contest
        path.unlink()

    # history: W's run, 3 passes and 1 failure in an xunit2 report.
    wait_for(
        "W's run to end",
        lambda: project.run_row(w_run).get("state") not in (None, "running"),
        minutes=10,
    )
    w_row = project.run_row(w_run)
    full = [
        r
        for r in runs_logged(log)
        if r["head"] == (w_row.get("merged_sha") or "-") and not r["args"]
    ]
    expected = report_cases(full[0]["report"]) if full else {}
    note(f"W's run {w_row.get('state')}; its report: {expected}")
    reached["ac-history-xunit2"] = True
    check(
        "history: premise -- W's report names 3 passes and 1 failure",
        sorted(expected.values()) == ["failed", "passed", "passed", "passed"],
        json.dumps(expected),
        "ac-history-xunit2",
    )
    try:
        rows = history(project, w_run)
    except RuntimeError as exc:
        rows = []
        check("history: test_history is readable for W's run", False, str(exc), "ac-history-xunit2")
    else:
        got = {r["test_id"]: r["outcome"] for r in rows}
        check(
            "history: 4 rows with the report's ids and outcomes",
            len(rows) == 4 and got == expected,
            f"rows {json.dumps(rows)[:500]}",
            "ac-history-xunit2",
        )
        check(
            "history: file is empty on every row (xunit2 names none)",
            bool(rows) and all(not r["file"] for r in rows),
            json.dumps([r["file"] for r in rows]),
            "ac-history-xunit2",
        )
        check(
            "history: each row names its check, phase 'review', the run's commit and a time",
            bool(rows)
            and all(
                r["check_name"] == CHECK
                and r["phase"] == "review"
                and r["commit_sha"] == w_row.get("merged_sha")
                and r["recorded_at"]
                for r in rows
            ),
            json.dumps(rows[:1]),
            "ac-history-xunit2",
        )

    # flip: L's landing run failed test_flaky once and passed it on the confirmation.
    view = wait_for(
        "L's landing to settle",
        lambda: (lambda v: v if v.get("state") in SETTLED else None)(project.landing(land)),
        minutes=15,
    ) or project.landing(land)
    note(
        f"L's landing {view.get('state')}; counter left "
        f"{counter.read_text(encoding='utf-8') if counter.exists() else '?'}"
    )
    reached["ac-flip-recorded"] = True
    check(
        "flip: premise -- L landed past its flaky test",
        view.get("state") == "landed" and counter.read_text(encoding="utf-8") == "0",
        json.dumps({k: view.get(k) for k in ("state", "reason")})[:400],
        "ac-flip-recorded",
    )
    try:
        rows = history(project, l_run)
    except RuntimeError as exc:
        check(
            "flip: test_history is readable for the batch's run",
            False,
            str(exc),
            "ac-flip-recorded",
        )
    else:
        flaky = [r for r in rows if r["test_id"] == FLAKY_ID]
        check(
            f"flip: {FLAKY_ID}'s row for the batch's run is 'flipped', {LANDING_CHECK}, 'landing'",
            len(flaky) == 1
            and flaky[0]["outcome"] == "flipped"
            and flaky[0]["check_name"] == LANDING_CHECK
            and flaky[0]["phase"] == "landing",
            f"rows {json.dumps(rows)[:500]}",
            "ac-flip-recorded",
        )

    # batch: the landing record, read on the way (FR-7).
    try:
        batch = project.query(
            f"select {', '.join(BATCH_FIELDS)} from landing_batches where id = '{batch_id}'"
        )
    except RuntimeError as exc:
        check("batch: the landing record is readable", False, str(exc))
    else:
        rec = batch[0] if batch else {}
        check(
            "batch: ready, slot and end times, 2+ check runs, outcome landed",
            bool(rec.get("ready_at") and rec.get("slot_at") and rec.get("checks_ended_at"))
            and (rec.get("check_runs") or 0) >= 2
            and rec.get("outcome") == "landed",
            json.dumps(rec),
        )

    # dash: this project, with history, and a new empty one.
    empty_root = SCRATCH / "empty"
    empty_root.mkdir()
    (empty_root / "README.md").write_text("empty\n", encoding="utf-8")
    git(empty_root, "init", "-q", "-b", "master")
    git(empty_root, "add", "-A")
    git(empty_root, "commit", "-qm", "empty")
    empty = Project(hub, empty_root)
    keep.append(empty)
    reached["ac-dashboard-every-project"] = True
    for which, p in (("with history", project), ("new and empty", empty)):
        listed = hub.call("GET", f"/projects/{p.id}/dashboards").get("dashboards") or []
        named = [d for d in listed if d.get("name") == DASHBOARD]
        if not check(
            f"dash: the project {which} has '{DASHBOARD}'",
            len(named) == 1,
            f"dashboards {[d.get('name') for d in listed]}",
            "ac-dashboard-every-project",
        ):
            continue
        ran = hub.call("GET", f"/projects/{p.id}/dashboards/{named[0]['id']}/run")
        panels = ran.get("panels") or []
        errors = [(x.get("title"), x.get("error")) for x in panels if x.get("error")]
        check(
            f"dash: every panel runs without an error on the project {which}",
            bool(panels) and not errors,
            f"{len(panels)} panels; errors {json.dumps(errors)[:400]}",
            "ac-dashboard-every-project",
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
        "--slots", type=int, default=2, help="the Hub's check concurrency: holders to fill it"
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
            drive(hub, projects, args.slots)
        except Exception as exc:  # a broken drive is a failure, never a pass
            check("the drive ran to the end", False, repr(exc)[:600])
    finally:
        for path in (SCRATCH / "gates").glob("*"):
            path.unlink()  # free any holder still waiting
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
