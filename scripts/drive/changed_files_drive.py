"""Acceptance drive for "A check can run only the tests for what a task changed"
(spec/changes/a-check-can-run-only-the-tests-for-what-a-task-changed; FR-1 command-for-a-change,
FR-3 pre-review-only, FR-4 result-says, FR-5 judged-the-same). Written failing first (task CCROT-1):
it fails while the check settings cannot carry a command for a change.

Drives the trial Hub (:8010 by default, `--hub` for another; never :8000). Each run makes a scratch
under ~/Documents/aw-changed-files-<time>/ and removes it and its project at the end (`--keep`
leaves them). No agent turn is spent: tasks are on a disabled, documentless loop, the drive commits
each task's work to the task's own branch (`agentweave/task/<id>`) itself, as a builder would, and
moves the task to completed.

The testbed: modules a and b, test_a and test_b, and one pytest check with
  command              `python select_tests.py runs.jsonl`  the whole suite, report.xml
  command for a change `python select_tests.py runs.jsonl {changed_files}`  only the test files that name
                       a changed module (the project's own choice, FR-1)
  re-run command       `python rerun.py rerun.jsonl {tests}`
Every wrapper appends what it ran to a log outside the project: which command, the list file's
contents, and the test ids in report.xml afterwards.

Steps:
  settings  a command for a change without `{changed_files}` is refused; one with it saves and
            reads back unchanged (FR-7's seam)
  narrow    task 1 changes only a.py. Pre-review: the command for a change ran, the list file held
            exactly "a.py\\n", the report holds test_a's tests and none of test_b's (cc-ac1); the
            run shows the check as sized to the change, 1 file (rs-ac1). cc-ac2 (a rename lists
            both paths) is a Hub test.
  landing   task 1 approved: its landing batch ran the full command, the report holds test_a's and
            test_b's tests (pr-ac1), and the command for a change did not run again (pr-ac2's
            landing half; the main-run and re-run halves are Hub tests)
  broken    task 2 breaks test_a. Pre-review: the failing test is named from the report, confirmed
            by the re-run command, and the task is sent back naming it (js-ac1)

    py -3.11 scripts/drive/changed_files_drive.py
    py -3.11 scripts/drive/changed_files_drive.py --keep

Start the trial Hub from the checkout under test (`.claude/reference/hubs.md`). Exit 1 when any check
fails or the drive itself breaks.
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
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-changed-files-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-4-5-20251001"  # the loop's agent never takes a turn; a runner is required
GIT_ID = ["-c", "user.name=cfdrive", "-c", "user.email=cfdrive@drive"]
#: The check settings' field for the command for a change (FR-7).
CHANGE_FIELD = "change_command"
CHECK_NAME = "pytest"

MODULE_A = "def double(x):\n    return x * 2\n"
MODULE_B = "def triple(x):\n    return x * 3\n"
TEST_A = (
    "from a import double\n\n\ndef test_double():\n    assert double(2) == 4\n\n\n"
    "def test_double_zero():\n    assert double(0) == 0\n"
)
TEST_B = "from b import triple\n\n\ndef test_triple():\n    assert triple(2) == 6\n"

#: `select_tests.py <log> [<list file>]`: runs pytest on every test file (or, given a list, on the test
#: files that name a changed module), writes report.xml, and appends {mode, list, tests} to the log.
SELECT = r"""import json, pathlib, re, subprocess, sys
import xml.etree.ElementTree as ET

log, listing = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
files = sorted(str(p) for p in pathlib.Path(".").glob("test_*.py"))
body = None
if listing:
    body = pathlib.Path(listing).read_text(encoding="utf-8")
    changed = {pathlib.PurePosixPath(x.strip()).stem for x in body.splitlines() if x.strip()}
    files = [f for f in files
             if any(re.search(r"\b" + m + r"\b", pathlib.Path(f).read_text("utf-8")) for m in changed)]
code = 0
if files:
    code = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=report.xml", *files]).returncode
else:
    pathlib.Path("report.xml").write_text('<testsuites><testsuite tests="0"/></testsuites>')
tests = [c.get("classname") + "::" + c.get("name") for c in ET.parse("report.xml").iter("testcase")]
with open(log, "a", encoding="utf-8") as out:
    out.write(json.dumps({"mode": "changed" if listing else "full", "list": body, "tests": tests}) + "\n")
sys.exit(code)
"""
#: `rerun.py <log> <classname::name>...`: re-runs those tests by name, as the Hub's confirmation does.
RERUN = r"""import json, subprocess, sys
log, ids = sys.argv[1], sys.argv[2:]
with open(log, "a", encoding="utf-8") as out:
    out.write(json.dumps({"ids": ids}) + "\n")
names = " or ".join(i.split("::", 1)[1] for i in ids)
sys.exit(subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=report.xml", "-k", names]).returncode)
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
    def force(func, target, _exc):  # noqa: ANN001 -- git marks objects read-only on Windows
        os.chmod(target, 0o700)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=force)


class Project:
    def __init__(self, hub: Hub, root: pathlib.Path) -> None:
        self.hub, self.root = hub, root
        self.id = hub.call("POST", "/projects/open", {"path": str(root)})["id"]
        note(f"project {self.id} at {root}")
        runner = hub.call(
            "POST",
            f"/projects/{self.id}/runners",
            {"name": "claude haiku (cfdrive)", "cli": "claude", "model": HAIKU},
        )
        hub.call("POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]})
        hub.call(
            "POST",
            f"/projects/{self.id}/jobs",
            {"name": "cfdrive", "agent": "builder", "message": "work", "cron": "0 0 1 1 *",
             "enabled": False, "purpose": "cfdrive", "work_needs_evidence": False},
        )
        jobs = hub.call("GET", f"/projects/{self.id}/jobs")
        self.loop = next(j.get("loop_id") or (j.get("loop") or {}).get("id") for j in jobs)
        if not self.loop:
            raise RuntimeError(f"the drive's job has no loop: {json.dumps(jobs)[:400]}")

    def apply_checks(self, checks: list) -> tuple[int, object]:
        settings = self.hub.call("GET", f"/projects/{self.id}/settings")
        settings.update({"main_branch": "master", "checks": checks})
        return self.hub.request("PUT", f"/projects/{self.id}/settings", settings)

    def task_with_work(self, title: str, files: dict) -> str:
        """A task whose work is *files* committed on its own branch, moved to completed."""
        task = self.hub.call(
            "POST",
            f"/projects/{self.id}/tasks",
            {"title": title, "description": "cfdrive", "loop_id": self.loop},
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
            code, res = self.hub.request("PATCH", f"/projects/{self.id}/tasks/{task}", {"status": status})
            if code >= 300:
                note(f"moving the task to {status} -> {code}: {json.dumps(res)[:300]}")
        return task

    def wait_run(self, task: str, minutes: float) -> dict:
        """The task's latest finished check run, asking for one if completing it started none."""
        deadline, asked, started = time.time() + minutes * 60, False, time.time()
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


def read_log(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def result_named(run: dict, name: str) -> dict:
    return next((r for r in run.get("results") or [] if r.get("name") == name), {})


def show(result: dict) -> None:
    note("result: " + json.dumps({k: v for k, v in result.items() if k != "output_tail"})[:700])


def wait_for(predicate, minutes: float) -> bool:  # noqa: ANN001
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(5)
    return predicate()


def sized_to_change(result: dict) -> tuple[bool, str]:
    """FR-4: the result records it was sized to the change and with how many files. The field names
    are the build's; read the plausible spellings so the drive fails on the fact, not on a name."""
    flag = next((result[k] for k in ("sized_to_change", "narrowed", "for_change") if k in result), None)
    count = next(
        (result[k] for k in ("changed_file_count", "changed_files_count", "changed_count", "changed_files")
         if k in result),
        None,
    )
    if isinstance(count, list):
        count = len(count)
    return bool(flag) and count == 1, f"sized={flag!r} files={count!r}"


def drive(hub: Hub, keep: bool) -> None:
    root, logs = SCRATCH / "project", SCRATCH / "logs"
    root.mkdir()
    logs.mkdir()
    files = {"a.py": MODULE_A, "b.py": MODULE_B, "test_a.py": TEST_A, "test_b.py": TEST_B,
             "select_tests.py": SELECT, "rerun.py": RERUN,
             ".gitignore": "report.xml\n__pycache__/\n.pytest_cache/\n"}
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "modules a and b and their tests")
    py = pathlib.PurePath(sys.executable).as_posix()
    runs_path, rerun_path = logs / "runs.jsonl", logs / "rerun.jsonl"
    runs_log, rerun_log = runs_path.as_posix(), rerun_path.as_posix()
    pytest_check = {
        "name": CHECK_NAME,
        "command": f'"{py}" select_tests.py {runs_log}',
        CHANGE_FIELD: f'"{py}" select_tests.py {runs_log} {{changed_files}}',
        "timeout_seconds": 300,
        "report_path": "report.xml",
        "rerun_command": f'"{py}" rerun.py {rerun_log} {{tests}}',
        "phase": "both",
    }
    project = None
    try:
        project = Project(hub, root)
        bad = dict(pytest_check, **{CHANGE_FIELD: f'"{py}" select_tests.py {runs_log}'})
        code, res = project.apply_checks([bad])
        check("settings: a command for a change without {changed_files} is refused",
              400 <= code < 500 and "changed_files" in json.dumps(res), f"HTTP {code} {json.dumps(res)[:200]}")
        code, res = project.apply_checks([pytest_check])
        saved = (res.get("checks") or [{}])[0] if code < 300 and isinstance(res, dict) else {}
        if not check("settings: the command for a change saves and reads back unchanged",
                     code < 300 and saved.get(CHANGE_FIELD) == pytest_check[CHANGE_FIELD],
                     f"HTTP {code} {json.dumps(res)[:300]}"):
            raise RuntimeError("the check settings cannot carry a command for a change yet")

        # narrow: task 1 changes only a.py
        task1 = project.task_with_work("Change a only", {"a.py": MODULE_A + "\n# changed\n"})
        run = project.wait_run(task1, minutes=5)
        result = result_named(run, CHECK_NAME)
        show(result)
        entries = read_log(runs_path)
        changed = [e for e in entries if e["mode"] == "changed"]
        check("narrow: the pre-review run passed", run["state"] == "passed", f"state {run['state']}")
        check("narrow: the command for a change ran once, the list file held exactly a.py",
              len(changed) == 1 and changed[0]["list"] == "a.py\n",
              f"entries {[(e['mode'], e['list']) for e in entries]}")
        check("narrow: the report holds test_a's tests and none of test_b's (cc-ac1)",
              bool(changed) and {t.split("::")[0] for t in changed[0]["tests"]} == {"test_a"}
              and len(changed[0]["tests"]) == 2,
              f"tests {changed[0]['tests'] if changed else None}")
        ok, detail = sized_to_change(result)
        check("narrow: the run shows the check as sized to the change, 1 file (rs-ac1)", ok, detail)

        # landing: approve task 1; its batch runs the full command
        before = len(read_log(runs_path))
        code, res = hub.request("PATCH", f"/projects/{project.id}/tasks/{task1}", {"status": "approved"})
        note(f"approve -> HTTP {code}" + (f" {json.dumps(res)[:200]}" if code >= 300 else ""))
        wait_for(lambda: any(e["mode"] == "full" for e in read_log(runs_path)[before:]), 10)
        later = read_log(runs_path)[before:]
        full = [e for e in later if e["mode"] == "full"]
        check("landing: the batch ran the full command, its report holds test_a's and test_b's tests (pr-ac1)",
              bool(full) and {t.split("::")[0] for t in full[0]["tests"]} == {"test_a", "test_b"},
              f"entries {[(e['mode'], e['tests']) for e in later]}")
        check("landing: the command for a change did not run again (pr-ac2, landing half)",
              not any(e["mode"] == "changed" for e in later))

        # broken: task 2 breaks test_a
        before = len(read_log(rerun_path))
        task2 = project.task_with_work("Break a", {"a.py": "def double(x):\n    return x + 3\n"})
        run = project.wait_run(task2, minutes=5)
        result = result_named(run, CHECK_NAME)
        show(result)
        named = [t.get("id") if isinstance(t, dict) else t for t in result.get("failed_tests") or []]
        check("broken: the run failed, naming test_a's failing test from the report",
              run["state"] == "failed" and bool(named) and all(n.startswith("test_a::") for n in named)
              and "test_a::test_double" in named, f"state {run['state']} named {named}")
        confirmed = result.get("confirmed") or {}
        reruns = read_log(rerun_path)[before:]
        check("broken: the re-run command confirmed it",
              bool(reruns) and all(set(r["ids"]) <= set(named) for r in reruns)
              and confirmed.get("how") == "tests",
              f"confirmed {json.dumps(confirmed)[:200]} reruns {reruns}")
        task = hub.call("GET", f"/projects/{project.id}/tasks/{task2}")
        check("broken: the task was sent back naming the test (js-ac1)",
              task.get("status") == "revision_needed" and "test_double" in json.dumps(task),
              f"status {task.get('status')}")
    except Exception as exc:  # a broken drive is a failure, never a pass
        check("the drive ran to the end", False, repr(exc)[:600])
    finally:
        if keep:
            note(f"kept {SCRATCH}" + (f" and project {project.id}" if project else ""))
        else:
            if project:
                try:
                    project.remove()
                except Exception as exc:  # noqa: BLE001 -- clean up regardless
                    note(f"could not remove {project.id}: {exc!r}")
            rmtree(SCRATCH)


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
    drive(hub, args.keep)
    print("FAILED: " + ", ".join(failures) if failures else "ALL PASS", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
