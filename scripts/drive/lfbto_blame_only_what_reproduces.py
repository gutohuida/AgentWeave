"""Acceptance drive for "A landing failure is blamed on a task only when it reproduces there"
(spec/changes/a-landing-failure-is-blamed-on-a-task-only-when-it-reproduces-there, FR-1
blame-needs-reproduction, criterion ac-drive; FR-5 and FR-7 are read on the way). Written failing
first (LFBTO-1): on the pre-build code a flaky test sends a clean task back by elimination, and a
real landing send-back carries no proof and restarts nobody.

Drives a trial Hub on :8010 (never :8000). `--start-hub` starts one from THIS checkout's source on
`--port` (8010 by default) with a scratch database of its own, and stops it at the end; without it
the drive uses the Hub already answering at `--hub`. Every run makes its own scratch under
~/Documents/aw-lfbto-<time>/ and removes it and its project at the end (`--keep` leaves them).

The scratch project has one agent, `builder` (Haiku), and one check: pytest with `--junitxml`,
behind `runcheck.py`, at the landing phase only, so a task's completion runs nothing and only a
landing batch runs the tests. Tasks are made by hand, on no loop, flow or build, assigned to
`builder`; the drive commits each task's work to the task's own branch itself (a loopless task with
no requirement merges its branch tip) and moves it to completed, then approves it as the operator.
No agent turn is spent until the Hub starts one.

The flaky test. main carries `test_flaky.py`, which fails while a counter file outside the project
(`<scratch>/flaky-count`) is above zero, decrementing it each time. The drive arms it to 2 just
before the first batch: the batch's full run fails it and the flake re-run on the same tree fails
it again, so the failure stands as confirmed; every later run passes it. It reproduces on no
prefix: it is nobody's.

Steps:
  batch    CLEAN_A adds a.txt, CLEAN_B adds b.txt, both approved together (one batch).
           PASS needs: both land; neither is sent back; neither is in revision_needed.
  breaks   once the batch has settled, BREAKS adds `test_broken.py` (a test that always fails) and
           is approved alone. PASS needs: it is sent back (revision_needed, landing sent_back);
           the send-back's note carries its proof -- the batch's base commit and the prefix commit
           both named, the re-run command, the failing test id, and at least two exit codes;
           and a turn of its author `builder` is queued bound to the task after the send-back,
           with no operator action. The author's turn is stopped as soon as it is seen.

Ends with one baseline line per criterion the drive covers,
  check ac-drive: reached=<yes|no> failed_at_assertion=<yes|no> -- <first failing assertion>
which is what the drive task's `drive_baseline` evidence carries. Exit 1 when any check fails.

    py -3.11 scripts/drive/lfbto_blame_only_what_reproduces.py --start-hub
    py -3.11 scripts/drive/lfbto_blame_only_what_reproduces.py --hub http://127.0.0.1:8010 --keep
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[2]
TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-lfbto-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-5-5"
GIT_ID = ["-c", "user.name=lfbto", "-c", "user.email=lfbto@drive"]
#: How often the Hub looks at main (`project_checks.WATCH_SECONDS`).
WATCH_SECONDS = 30
#: How long the oldest queued landing waits for others (`landing_queue.BATCH_GATHER_SECONDS`).
GATHER_SECONDS = 60
FLAKY_ID = "test_flaky::test_flaky"
BROKEN_ID = "test_broken::test_broken"
SETTLED = ("landed", "sent_back", "not_landed")

RUNCHECK = r"""import json, os, subprocess, sys, time
log, args = sys.argv[1], sys.argv[2:]
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({"head": head, "cwd": os.getcwd(), "args": args, "t": time.time()}) + "\n")
targets = []
if args[:1] == ["--rerun"]:
    for t in args[1:]:
        mod, name = t.split("::", 1)
        targets.append(mod.replace(".", "/") + ".py::" + name)
run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                      "--junitxml=report.xml", *targets])
sys.exit(run.returncode)
"""
PASSING = "def test_ok():\n    assert 1 + 1 == 2\n"
# Fails while the counter outside the project is above zero, spending one each time.
FLAKY = (
    "import pathlib\n\nCOUNTER = pathlib.Path({counter!r})\n\n\n"
    "def test_flaky():\n"
    "    left = int(COUNTER.read_text()) if COUNTER.exists() else 0\n"
    "    if left > 0:\n"
    "        COUNTER.write_text(str(left - 1))\n"
    "    assert left <= 0, f'flaky: {{left}} failure(s) left on the counter'\n"
)
BROKEN = "def test_broken():\n    assert 1 + 1 == 3, 'this task breaks a test'\n"

failures: list[str] = []
reached: dict[str, bool] = {"ac-drive": False}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)
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
            {"name": "claude haiku (lfbto)", "cli": "claude", "model": HAIKU},
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
        moved to completed. Created `pending` (not `assigned`), so nothing starts a turn for it."""
        task = self.hub.call(
            "POST",
            f"/projects/{self.id}/tasks",
            {"title": title, "description": "lfbto drive", "assignee": "builder"},
        )["id"]
        base = git(self.root, "rev-parse", "HEAD")
        branch = f"agentweave/task/{task}"
        git(self.root, "branch", branch, base)
        work = self.root.parent / f"work-{task}"
        git(self.root, "worktree", "add", "-q", str(work), branch)
        try:
            for rel, text in files.items():
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
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

    def queue(self, agent: str) -> list:
        code, res = self.hub.request("GET", f"/projects/{self.id}/queue/{agent}")
        return res if code == 200 and isinstance(res, list) else []

    def stop(self, agent: str) -> None:
        code, res = self.hub.request("POST", f"/projects/{self.id}/agent/{agent}/stop", {})
        note(f"stopped {agent}'s turn: HTTP {code}" + ("" if code < 300 else f" {res}"))

    def remove(self) -> None:
        self.stop("builder")
        code, res = self.hub.request("DELETE", f"/projects/{self.id}")
        note(f"removed project {self.id}: HTTP {code}" + ("" if code < 300 else f" {res}"))


def wait_for(what: str, test, minutes: float):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        found = test()
        if found:
            return found
        time.sleep(5)
    note(f"timed out waiting for {what}")
    return None


def runs_logged(log: pathlib.Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def narrowing(db: pathlib.Path | None, batch_id: str | None) -> object:
    """The batch's narrowing log, read-only from the scratch Hub's database where the drive knows it
    (no route serves it); `None` otherwise."""
    if db is None or not batch_id or not db.exists():
        return None
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select narrowing from landing_batches where id=?", (batch_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        return f"unreadable: {exc}"
    finally:
        con.close()
    return json.loads(row[0]) if row and row[0] else None


def brief(view: dict) -> str:
    batch = view.get("batch") or {}
    return json.dumps(
        {
            "state": view.get("state"),
            "batch": batch.get("id"),
            "batch_state": batch.get("state"),
            "reason": (view.get("reason") or "")[:300],
        }
    )


# --- the drive ---------------------------------------------------------------------------------


def drive(hub: Hub, keep: list, db: pathlib.Path | None) -> None:
    root = SCRATCH / "project"
    root.mkdir(parents=True)
    log = SCRATCH / "runs.jsonl"
    counter = SCRATCH / "flaky-count"
    (root / "runcheck.py").write_text(RUNCHECK, encoding="utf-8", newline="\n")
    (root / "test_ok.py").write_text(PASSING, encoding="utf-8", newline="\n")
    (root / "test_flaky.py").write_text(
        FLAKY.format(counter=counter.as_posix()), encoding="utf-8", newline="\n"
    )
    (root / ".gitignore").write_text("report.xml\n__pycache__/\n", encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "passing tests, a flaky one, and the check wrapper")
    project = Project(hub, root)
    keep.append(project)
    py = pathlib.Path(sys.executable).as_posix()
    code, res = project.apply_checks(
        [
            {
                "name": "pytest",
                "command": f'"{py}" runcheck.py {log.as_posix()}',
                "timeout_seconds": 300,
                "report_path": "report.xml",
                "rerun_command": f'"{py}" runcheck.py {log.as_posix()} --rerun {{tests}}',
                "phase": "landing",
            }
        ],
        "master",
    )
    if code >= 300:
        raise RuntimeError(f"saving the check -> {code}: {res}")
    # The Hub's first look at main only records its tip; let it look before anything lands.
    time.sleep(WATCH_SECONDS + 10)

    # batch: two clean tasks land together past a flaky failure that reproduces on no prefix.
    clean_a = project.task_with_work("Clean work A", {"a.txt": "a\n"})
    clean_b = project.task_with_work("Clean work B", {"b.txt": "b\n"})
    for t in (clean_a, clean_b):
        note(f"{t}: {project.task(t).get('status')} before approval")
    counter.write_text("2", encoding="utf-8")  # armed now: no run before the batch spends it
    seen = len(runs_logged(log))
    reached["ac-drive"] = True
    for t in (clean_a, clean_b):
        project.approve(t)
    views: dict = {}

    def batch_settled() -> bool:
        views.update({t: project.landing(t) for t in (clean_a, clean_b)})
        return all(v.get("state") in SETTLED for v in views.values())

    wait_for("the first batch to settle", batch_settled, minutes=20)
    for t, v in views.items():
        note(f"{t} landing: {brief(v)}")
    batch_ids = {(v.get("batch") or {}).get("id") for v in views.values()}
    note(
        f"runs logged in the batch: {len(runs_logged(log)) - seen}; counter left "
        f"{counter.read_text(encoding='utf-8') if counter.exists() else '?'}"
    )
    for batch_id in sorted(b for b in batch_ids if b):
        note(f"narrowing of {batch_id}: {json.dumps(narrowing(db, batch_id))[:900]}")
    # A landing records the batch that landed it, which a partial land makes a new one: what says
    # they were checked together is a batch whose tasks are both.
    together = [
        v["batch"]["id"]
        for v in views.values()
        if {clean_a, clean_b} <= set((v.get("batch") or {}).get("task_ids") or [])
    ]
    check(
        "batch: the two clean tasks were checked in one batch",
        bool(together),
        f"batches {sorted(map(str, batch_ids))}, holding both: {together}",
    )
    for t, label in ((clean_a, "A"), (clean_b, "B")):
        status = project.task(t).get("status")
        check(
            f"batch: clean task {label} landed, not sent back by a flaky test",
            views[t].get("state") == "landed" and status != "revision_needed",
            f"landing {views[t].get('state')}, task {status}",
        )

    # breaks: a task that really breaks a test is sent back with proof, and its author restarts.
    broken = project.task_with_work("Adds a test that always fails", {"test_broken.py": BROKEN})
    project.approve(broken)
    view = wait_for(
        "the breaking task's landing to settle",
        lambda: (lambda v: v if v.get("state") in SETTLED else None)(project.landing(broken)),
        minutes=20,
    ) or project.landing(broken)
    sent_back_at = time.time()
    task = project.task(broken)
    note(f"{broken} landing: {brief(view)}")
    batch = view.get("batch") or {}
    note(f"narrowing of {batch.get('id')}: {json.dumps(narrowing(db, batch.get('id')))[:900]}")
    check(
        "breaks: the task that breaks a test is sent back",
        view.get("state") == "sent_back" and task.get("status") == "revision_needed",
        f"landing {view.get('state')}, task {task.get('status')}",
    )
    proof = "\n".join(str(x or "") for x in (view.get("reason"), task.get("notes")))
    base, prefix = batch.get("base_sha") or "", batch.get("merged_sha") or ""
    missing = [
        what
        for what, ok in (
            (f"the base commit {base[:12]}", bool(base) and base[:7] in proof),
            (f"the prefix commit {prefix[:12]}", bool(prefix) and prefix[:7] in proof),
            ("the re-run command", "runcheck.py" in proof and "--rerun" in proof),
            (f"the failing test {BROKEN_ID}", "test_broken" in proof),
            (
                "two exit codes",
                len(re.findall(r"exit(?: code|_code)?[ =:]*-?\d+", proof, re.I)) >= 2,
            ),
        )
        if not ok
    ]
    check(
        "breaks: the send-back's note carries its proof (both probes, exit codes, the test)",
        view.get("state") == "sent_back" and not missing,
        ("missing " + "; ".join(missing) + f" -- note: {proof[:500]!r}") if missing else "",
    )
    entry = wait_for(
        "a turn of the author bound to the task",
        lambda: next((e for e in project.queue("builder") if e.get("task_id") == broken), None),
        minutes=3,
    )
    if entry is not None:
        project.stop("builder")
    check(
        "breaks: the author's turn on the task is queued, with no operator action",
        entry is not None,
        (
            f"entry {json.dumps(entry)[:300]}"
            if entry
            else f"no queue entry for builder bound to {broken} within 3 minutes of the send-back "
            f"(task {project.task(broken).get('status')}, waited {int(time.time() - sent_back_at)} s)"
        ),
    )


def baseline() -> None:
    """One line per criterion the drive covers, as the `drive_baseline` evidence reads them."""
    first = failures[0] if failures else ""
    print(
        f"check ac-drive: reached={'yes' if reached['ac-drive'] else 'no'} "
        f"failed_at_assertion={'yes' if reached['ac-drive'] and failures else 'no'} -- "
        + (first or "all assertions passed"),
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
    parser.add_argument("--keep", action="store_true", help="leave the scratch and its project")
    args = parser.parse_args()
    if args.port == 8000:
        raise SystemExit(":8000 is the operator's real instance. Never drive it.")
    SCRATCH.mkdir(parents=True)
    print(f"scratch {SCRATCH}", flush=True)
    proc, db = None, None
    if args.start_hub:
        key = "aw_live_" + secrets.token_hex(16)
        url = f"http://127.0.0.1:{args.port}"
        if Hub(url, key).request("GET", "/projects")[0] != 0:
            raise SystemExit(f"something already answers on {url}: stop it or drop --start-hub")
        proc, db = start_hub(args.port, SCRATCH, key), SCRATCH / "hub.db"
        hub = Hub(url, key)
        print(f"started a Hub from {REPO} on {url} (database {db})", flush=True)
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
            drive(hub, projects, db)
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
