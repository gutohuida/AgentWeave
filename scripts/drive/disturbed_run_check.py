"""Acceptance drive for "A disturbed check run is not a pile of flaky tests"
(spec/changes/a-disturbed-check-run-is-not-a-pile-of-flaky-tests, FR-1 disturbed-run; ac-drive).
Written failing first (DCRNP-1): on master a run that fails 5 named tests which all pass on the
rerun lists 5 flaky entries and files 5 fix tasks, so the task-count assertion fails there.

Drives the trial Hub (:8010 by default, `--hub` for another; never :8000). Every run makes its own
scratch under ~/Documents/aw-disturbed-<time>/ and removes it and its project at the end, pass or
fail (`--keep` leaves them for a look). No agent turn is spent.

The project's one check is `runcheck.py`, which writes a JUnit report. Run whole, it fails 5 named
tests (a marker file in the scratch, outside the project, records that it has been run). Run as the
rerun command (`--rerun <ids>`), every test passes. A task with one committed file is completed so
its checks run, then the drive reads, as the operator would:

  disturbed  the task's check run reads disturbed (a `disturbed` field anywhere in the run's result)
  list       the known-failing list gained no entry
  logs       the project's Logs hold exactly one disturbed event (event_type containing "disturbed")
  tasks      the ledger holds no fix task (every task but the drive's own)

Each assertion is reported on its own, so a run that fails one still shows the others. The
disturbed event's type is matched by substring (EVENT_WORD) and the list route is read as
`GET /projects/<id>/checks/known-failing` (an object with `entries`, or a list): change
those two constants if the build names them differently.

    py -3.11 scripts/drive/disturbed_run_check.py
    py -3.11 scripts/drive/disturbed_run_check.py --keep   # leave the scratch

Start the trial Hub from the checkout under test (`.claude/reference/hubs.md`). Exit 1 when any
check fails or the drive itself breaks.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-disturbed-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-4-5-20251001"  # the loop's agent never takes a turn; a runner is required
GIT_ID = ["-c", "user.name=disturbed", "-c", "user.email=disturbed@drive"]
LIST_ROUTE = "/projects/{pid}/checks/known-failing"
EVENT_WORD = "disturbed"
FAILING_TESTS = 5

RUNCHECK = r"""import json, sys, time
marker, args = sys.argv[1], sys.argv[2:]
names = ["test_alpha", "test_bravo", "test_charlie", "test_delta", "test_echo"]
rerun = args[:1] == ["--rerun"]
with open(marker, "a", encoding="utf-8") as f:
    f.write(json.dumps({"rerun": rerun, "args": args, "t": time.time()}) + "\n")
cases = []
for name in names:
    if rerun:
        cases.append(f'<testcase classname="suite_busy" file="tests/test_busy.py" name="{name}"/>')
    else:
        cases.append(
            f'<testcase classname="suite_busy" file="tests/test_busy.py" name="{name}">'
            f'<failure message="git timed out in {name}">TimeoutError in {name}</failure></testcase>'
        )
failures = 0 if rerun else len(names)
with open("report.xml", "w", encoding="utf-8") as f:
    f.write(
        f'<testsuites><testsuite name="suite_busy" tests="{len(names)}" failures="{failures}">'
        + "".join(cases)
        + "</testsuite></testsuites>"
    )
sys.exit(1 if failures else 0)
"""

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)
    return ok


def note(text: str) -> None:
    print(f"       {text}", flush=True)


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
        try:
            return status, json.loads(raw or b"null")
        except ValueError:
            return status, raw.decode("utf-8", "replace")

    def call(self, method: str, path: str, body: object = None) -> object:
        status, res = self.request(method, path, body)
        if status >= 300:
            raise RuntimeError(f"{method} {path} -> {status}: {json.dumps(res)[:800]}")
        return res


def hub_key(url: str) -> str:
    if os.environ.get("AW_KEY"):
        return os.environ["AW_KEY"]
    if url.rstrip("/").endswith(":8010") and TRIAL_KEY.exists():
        return TRIAL_KEY.read_text(encoding="utf-8").strip()
    with urllib.request.urlopen(url.rstrip("/") + "/api/v1/setup/token", timeout=10) as r:
        return json.loads(r.read())["api_key"]


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
    """A scratch project on the Hub: opened, given an agent and a branch-tip loop, removed after."""

    def __init__(self, hub: Hub, root: pathlib.Path) -> None:
        self.hub, self.root = hub, root
        self.id = hub.call("POST", "/projects/open", {"path": str(root)})["id"]
        note(f"project {self.id} at {root}")
        runner = hub.call(
            "POST",
            f"/projects/{self.id}/runners",
            {"name": "claude haiku (disturbed)", "cli": "claude", "model": HAIKU},
        )
        hub.call(
            "POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]}
        )
        # Disabled: it never fires. It gives the task a source whose approval merges the branch tip.
        hub.call(
            "POST",
            f"/projects/{self.id}/jobs",
            {
                "name": "disturbed drive",
                "agent": "builder",
                "message": "work",
                "cron": "0 0 1 1 *",
                "enabled": False,
                "purpose": "disturbed drive",
                "work_needs_evidence": False,
            },
        )
        jobs = hub.call("GET", f"/projects/{self.id}/jobs")
        self.loop = next(j.get("loop_id") or (j.get("loop") or {}).get("id") for j in jobs)
        if not self.loop:
            raise RuntimeError(f"the drive's job has no loop: {json.dumps(jobs)[:400]}")

    def apply_checks(self, checks: list, main_branch: str) -> tuple[int, object]:
        settings = self.hub.call("GET", f"/projects/{self.id}/settings")
        settings.update({"main_branch": main_branch, "checks": checks})
        return self.hub.request("PUT", f"/projects/{self.id}/settings", settings)

    def task_with_work(self, title: str, files: dict) -> str:
        """A task whose work is *files* committed on its own branch, moved to completed."""
        task = self.hub.call(
            "POST",
            f"/projects/{self.id}/tasks",
            {"title": title, "description": "disturbed drive", "loop_id": self.loop},
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
                note(f"moving the task to {status} -> {code}: {json.dumps(res)[:300]}")
        return task

    def wait_run(self, task: str, minutes: float) -> dict:
        """The task's latest finished check run, asking for one if completing it started none."""
        deadline, asked = time.time() + minutes * 60, False
        started = time.time()
        while time.time() < deadline:
            view = self.hub.call("GET", f"/projects/{self.id}/tasks/{task}/checks")
            runs = view.get("runs") or []
            if runs and runs[0]["state"] not in ("running", "queued", "pending"):
                return runs[0]
            if not runs and not asked and time.time() - started > 20:
                note("completing the task started no run: asking for one")
                self.hub.request("POST", f"/projects/{self.id}/tasks/{task}/checks/run")
                asked = True
            time.sleep(5)
        raise RuntimeError(f"no finished check run for {task} within {minutes} minutes")

    def remove(self) -> None:
        for job in self.hub.call("GET", f"/projects/{self.id}/jobs"):
            self.hub.request("POST", f"/projects/{self.id}/jobs/{job['id']}/archive")
        code, res = self.hub.request("DELETE", f"/projects/{self.id}")
        note(f"removed project {self.id}: HTTP {code}" + ("" if code < 300 else f" {res}"))


def read_list(project: Project) -> list[dict]:
    status, res = project.hub.request("GET", LIST_ROUTE.format(pid=project.id))
    if status >= 300:
        return []
    return res.get("entries", []) if isinstance(res, dict) else res or []


def read_tasks(project: Project) -> list[dict]:
    res = project.hub.call("GET", f"/projects/{project.id}/tasks")
    return res.get("tasks", []) if isinstance(res, dict) else res or []


def read_logs(project: Project) -> list[dict]:
    status, res = project.hub.request("GET", f"/projects/{project.id}/logs?limit=500")
    return res if status < 300 and isinstance(res, list) else []


def mentions(value: object, word: str) -> bool:
    """Whether *word* is a key, or a truthy-valued key, anywhere in *value* (a run's result)."""
    if isinstance(value, dict):
        return any(
            (word in str(k).lower() and bool(v)) or mentions(v, word) for k, v in value.items()
        )
    if isinstance(value, list):
        return any(mentions(v, word) for v in value)
    return isinstance(value, str) and value.strip().lower() == word


def drive(hub: Hub, keep: list) -> None:
    root = SCRATCH / "project"
    root.mkdir(parents=True)
    marker = SCRATCH / "runs.jsonl"
    (root / "runcheck.py").write_text(RUNCHECK, encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text("report.xml\n__pycache__/\n", encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the check wrapper")
    project = Project(hub, root)
    keep.append(project)
    py = pathlib.Path(sys.executable).as_posix()
    code, res = project.apply_checks(
        [
            {
                "name": "busy",
                "command": f'"{py}" runcheck.py {marker.as_posix()}',
                "timeout_seconds": 120,
                "report_path": "report.xml",
                "rerun_command": f'"{py}" runcheck.py {marker.as_posix()} --rerun {{tests}}',
            }
        ],
        "master",
    )
    if code >= 300:
        raise RuntimeError(f"saving the check -> {code}: {res}")
    before_tasks = {t["id"] for t in read_tasks(project)}

    task = project.task_with_work("add a file", {"note.txt": "work\n"})
    run = project.wait_run(task, minutes=6)
    note("run: " + json.dumps(run)[:1200])
    # the rerun is made inside the run; give the Hub a moment to write its list entries and tasks
    time.sleep(10)
    calls = [json.loads(x) for x in marker.read_text(encoding="utf-8").splitlines() if x.strip()]
    reruns = [c for c in calls if c["rerun"]]
    check(
        "the check ran whole, then reran the failed tests",
        bool(calls) and bool(reruns),
        f"{len(calls)} calls, {len(reruns)} reruns",
    )

    # disturbed: the task's check run reads disturbed
    check("disturbed: the task's check run reads disturbed", mentions(run, EVENT_WORD))

    # list: no known-failing entry
    entries = read_list(project)
    check("list: the known-failing list gained no entry", not entries, f"{len(entries)} entries")

    # logs: one disturbed event
    events = [e for e in read_logs(project) if EVENT_WORD in str(e.get("event_type", "")).lower()]
    check("logs: the Logs hold one disturbed event", len(events) == 1, f"{len(events)} events")

    # tasks: no fix task
    after = read_tasks(project)
    extra = [t for t in after if t["id"] not in before_tasks and t["id"] != task]
    check(
        "tasks: no fix task is created",
        not extra,
        f"{len(extra)} new tasks: {[t.get('title') for t in extra][:6]}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hub", default="http://127.0.0.1:8010")
    parser.add_argument("--keep", action="store_true", help="leave the scratch and its project")
    args = parser.parse_args()
    hub = Hub(args.hub, hub_key(args.hub))
    try:
        urllib.request.urlopen(hub.url + "/health", timeout=10).read()
    except OSError as exc:
        raise SystemExit(f"no Hub at {args.hub}: {exc}") from exc
    print(f"Hub {args.hub}; scratch {SCRATCH}", flush=True)
    SCRATCH.mkdir(parents=True)
    projects: list[Project] = []
    try:
        try:
            drive(hub, projects)
        except Exception as exc:  # a broken drive is a failure, never a pass
            check("the drive ran to the end", False, repr(exc)[:600])
    finally:
        if args.keep:
            note(f"kept {SCRATCH} and projects {[p.id for p in projects]}")
        else:
            for project in projects:
                try:
                    project.remove()
                except Exception as exc:  # noqa: BLE001 -- clean up regardless
                    note(f"could not remove {project.id}: {exc!r}")
            rmtree(SCRATCH)
    print("FAILED: " + ", ".join(failures) if failures else "ALL PASS", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
