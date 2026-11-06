"""Acceptance drive for "Failures already known are on a list, not re-argued"
(spec/changes/failures-already-known-are-on-a-list-not-re-argued, FR-4 removed-when-passing,
FR-6 owner-not-started, FR-7 gates-consult-the-list; ac-drive). Written failing first (FAKAL-1):
on master there is no list, so the seeded failure never reaches it and the drive fails there.

Drives the trial Hub (:8010 by default, `--hub` for another; never :8000). Every run creates its
own scratch, named for the run, under ~/Documents/aw-d1106-list-<time>/, and removes it and the
project it opened at the end, pass or fail (`--keep` leaves them for a look).

No agent turn is spent. Tasks sit on a disabled, documentless loop whose work merges its branch
tip, so the drive commits each task's work to the task's own branch itself and moves the task to
completed, then approves it as the operator.

The project's one check is pytest with `--junitxml`, behind `runcheck.py`, which logs the commit
and directory of every run it makes to a file outside the project. A run on a checkout of main is
one whose commit is main's tip, which no merged candidate or task branch ever is.

Steps, in order:

  seed     main gets an outside commit (not landed by the Hub) adding `test_listed`, which fails.
           The Hub's one full run on that commit lists it as failing on main (FR-3).
           PASS needs the entry on the list, with a fix task.
  owner    FR-5/FR-6: the fix task (the entry was found on main) is unassigned, is on no loop, flow
           or build, and has no run after a minute with a loop firing in the project.
  land     two tasks: CLEAN adds marker.txt, NEW adds `test_new`, which fails only while marker.txt
           exists, so each passes its own completion run and the batch's run fails it. Both are
           approved together. PASS needs: CLEAN lands past the listed test; NEW is sent
           back (its own failure); no check run used a checkout of main; no landing was ever held.
  removed  FR-4: an outside commit fixes `test_listed`; the Hub's run on that commit passes it;
           the entry comes off the list while its fix task stays open.

The list's route is read as `GET /projects/<id>/known-failing` (an object with `entries`, or a
list), each entry carrying `test_id` (or `test`), `kind` and `fix_task_id` (or `owner_task_id`);
LIST_ROUTE and the field names in `entry_*` below are the one place to change if the build names
them differently.

    py -3.11 scripts/drive/d1106_known_failing_list.py
    py -3.11 scripts/drive/d1106_known_failing_list.py --keep   # leave the scratch

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
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-d1106-list-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-4-5-20251001"  # the loop's agent never takes a turn; a runner is required
GIT_ID = ["-c", "user.name=d1106", "-c", "user.email=d1106@drive"]
LIST_ROUTE = "/projects/{pid}/known-failing"
LISTED_ID = "test_listed::test_listed"
NEW_ID = "test_new::test_new"

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
FAILING = "def test_{n}():\n    assert 1 + 1 == 3\n"
# The new failure only exists once the two tasks are merged: CLEAN adds marker.txt, NEW adds a test
# that fails while marker.txt exists. Each task's own completion run passes; the batch's run fails.
CONFLICT = (
    "import pathlib\n\n\ndef test_new():\n"
    "    assert not (pathlib.Path(__file__).parent / 'marker.txt').exists()\n"
)
FIXED = "def test_listed():\n    assert 1 + 1 == 2\n"

failures: list[str] = []


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
    """A scratch project on the Hub: opened, given an agent and a branch-tip loop, removed after."""

    def __init__(self, hub: Hub, root: pathlib.Path) -> None:
        self.hub, self.root = hub, root
        self.id = hub.call("POST", "/projects/open", {"path": str(root)})["id"]
        note(f"project {self.id} at {root}")
        runner = hub.call(
            "POST",
            f"/projects/{self.id}/runners",
            {"name": "claude haiku (d1106)", "cli": "claude", "model": HAIKU},
        )
        hub.call(
            "POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]}
        )
        # Disabled: it never fires. It gives the task a source whose approval merges the branch tip,
        # so the task's own branch is what its checks run on.
        hub.call(
            "POST",
            f"/projects/{self.id}/jobs",
            {
                "name": "d1106 drive",
                "agent": "builder",
                "message": "work",
                "cron": "0 0 1 1 *",
                "enabled": False,
                "purpose": "d1106 drive",
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
            {"title": title, "description": "d1106 drive", "loop_id": self.loop},
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


def test_ids(result: dict) -> list[str]:
    """The failing test ids a check result names, whether recorded as ids or as {id, file}."""
    named = result.get("failed_tests") or []
    return [t.get("id") if isinstance(t, dict) else t for t in named]


def result_named(run: dict, name: str) -> dict:
    return next((r for r in run.get("results") or [] if r.get("name") == name), {})


def show(result: dict) -> None:
    brief = {k: v for k, v in result.items() if k != "output_tail"}
    note("result: " + json.dumps(brief)[:900])


# --- the list ----------------------------------------------------------------------------------


def entry_test(entry: dict) -> str:
    return entry.get("test_id") or entry.get("test") or ""


def entry_task(entry: dict) -> str:
    return entry.get("fix_task_id") or entry.get("owner_task_id") or ""


def read_list(project: "Project") -> list[dict]:
    status, res = project.hub.request("GET", LIST_ROUTE.format(pid=project.id))
    if status >= 300:
        return []
    return res.get("entries", []) if isinstance(res, dict) else res or []


def is_listed(entry: dict) -> bool:
    return entry_test(entry) == LISTED_ID or entry_test(entry).endswith("test_listed")


def wait_for(what: str, test, minutes: float):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        found = test()
        if found:
            return found
        time.sleep(5)
    note(f"timed out waiting for {what}")
    return None


def commit_to_main(root: pathlib.Path, files: dict, message: str) -> str:
    """An outside commit: made by the drive, never landed by the Hub."""
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
        git(root, "add", rel)
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def runs_logged(log: pathlib.Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def approve(project: "Project", task: str) -> None:
    code, res = project.hub.request(
        "PATCH", f"/projects/{project.id}/tasks/{task}", {"status": "approved"}
    )
    if code >= 300:
        note(f"approving {task} -> {code}: {json.dumps(res)[:300]}")


def landing_of(project: "Project", task: str) -> dict:
    view = project.hub.call("GET", f"/projects/{project.id}/tasks/{task}/checks")
    return view.get("landing") or {}


# --- the drive ---------------------------------------------------------------------------------


def drive(hub: "Hub", keep: list) -> None:
    root = SCRATCH / "project"
    root.mkdir(parents=True)
    log = SCRATCH / "runs.jsonl"
    (root / "runcheck.py").write_text(RUNCHECK, encoding="utf-8", newline="\n")
    (root / "test_ok.py").write_text(PASSING, encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text("report.xml\n__pycache__/\n", encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a passing test and the check wrapper")
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
            }
        ],
        "master",
    )
    if code >= 300:
        raise RuntimeError(f"saving the check -> {code}: {res}")

    # seed: an outside commit puts a failing test on main
    commit_to_main(root, {"test_listed.py": FAILING.format(n="listed")}, "add a failing test")
    entry = wait_for(
        "the seeded failure on the list",
        lambda: next((e for e in read_list(project) if is_listed(e)), None),
        minutes=10,
    )
    check(
        "seed: the outside commit's failure is on the list",
        entry is not None,
        f"list {read_list(project)}",
    )
    if entry is None:
        return
    check(
        "seed: it is listed as failing on main",
        "main" in str(entry.get("kind")),
        f"kind {entry.get('kind')}",
    )
    main_tip = git(root, "rev-parse", "master")
    seen_before = len(runs_logged(log))

    # owner: the entry was found by a run on main, so its fix task is unassigned (FR-5), is on no
    # loop, flow or build, and no run starts on it while a loop fires in the project (FR-6)
    fix = entry_task(entry)
    check("owner: the entry names a fix task", bool(fix), f"entry {entry}")
    if fix:
        hub.call(
            "POST",
            f"/projects/{project.id}/jobs",
            {
                "name": "d1106 firing",
                "agent": "builder",
                "message": "work",
                "cron": "* * * * *",
                "enabled": True,
                "purpose": "d1106 drive: a loop that fires during the minute",
                "stop_at": "2099-01-01T00:00:00Z",
            },
        )
        time.sleep(75)
        for job in hub.call("GET", f"/projects/{project.id}/jobs"):
            if job.get("name") == "d1106 firing":  # done with it: it must not fire later
                hub.request("POST", f"/projects/{project.id}/jobs/{job['id']}/archive")
        task = hub.call("GET", f"/projects/{project.id}/tasks/{fix}")
        story = hub.call("GET", f"/projects/{project.id}/tasks/{fix}/story")
        check(
            "owner: a fix task for a main-found entry is unassigned",
            not task.get("assignee"),
            f"assignee {task.get('assignee')}",
        )
        check(
            "owner: it is on no loop, flow or build",
            not (task.get("loop_id") or task.get("build_id") or task.get("spec_document_id")),
            f"loop {task.get('loop_id')} build {task.get('build_id')}",
        )
        check(
            "owner: it is not started and no run exists for it",
            task.get("status") in ("pending", "assigned")
            and task.get("assignee_status") != "running"
            and (story.get("summary") or {}).get("runs") == 0,
            f"status {task.get('status')} / {task.get('assignee_status')}, "
            f"runs {(story.get('summary') or {}).get('runs')}",
        )

    # land: the clean task goes past the listed test; the one adding a failure goes back
    clean = project.task_with_work("Clean work", {"marker.txt": "present\n"})
    bad = project.task_with_work("Adds a test that fails beside it", {"test_new.py": CONFLICT})
    for t in (clean, bad):
        run = project.wait_run(t, minutes=5)
        check(
            f"land: {t}'s own completion run passes (the failure needs the merge)",
            run.get("state") == "passed",
            f"state {run.get('state')}",
        )
    tips: dict[str, float] = {main_tip: 0.0}  # every main tip seen, when first seen
    for t in (clean, bad):
        approve(project, t)
    held = False

    def settled() -> bool:
        nonlocal held
        tips.setdefault(git(root, "rev-parse", "master"), time.time())
        states = [landing_of(project, t).get("state") for t in (clean, bad)]
        held = held or "held" in states
        return held or all(s in ("landed", "sent_back", "not_landed") for s in states)

    wait_for("both landings to settle", settled, minutes=15)
    views = {t: landing_of(project, t) for t in (clean, bad)}
    note("landings: " + json.dumps({t: v.get("state") for t, v in views.items()}))
    check(
        "land: the clean task landed past the listed test",
        views[clean].get("state") == "landed",
        json.dumps({k: views[clean].get(k) for k in ("state", "reason")}),
    )
    check(
        "land: the task that adds a failure was sent back",
        views[bad].get("state") == "sent_back",
        json.dumps({k: views[bad].get(k) for k in ("state", "reason")}),
    )
    bad_task = hub.call("GET", f"/projects/{project.id}/tasks/{bad}")
    check(
        "land: the task that adds a failure is back with its author",
        bad_task.get("status") == "revision_needed",
        f"status {bad_task.get('status')}",
    )
    check("land: no landing was held", not held)
    after = runs_logged(log)[seen_before:]
    on_main = [r for r in after if r["head"] in tips and tips[r["head"]] < r["t"]]
    check(
        "land: no check run used a checkout of main",
        not on_main,
        f"{len(on_main)} of {len(after)} runs on a main tip seen before the run ({len(tips)} tips)",
    )

    # removed: the test passes again on main
    commit_to_main(root, {"test_listed.py": FIXED}, "fix the listed test")
    gone = wait_for(
        "the entry to come off the list",
        lambda: not any(is_listed(e) for e in read_list(project)),
        minutes=10,
    )
    check("removed: the entry came off once the test passed on main", bool(gone))
    if fix:
        task = hub.call("GET", f"/projects/{project.id}/tasks/{fix}")
        check(
            "removed: its fix task is still open",
            task.get("status") not in ("approved", "rejected"),
            f"status {task.get('status')}",
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
