"""Acceptance drive for "Checks report which tests failed, in any language"
(spec/changes/checks-report-which-tests-failed-in-any-language, FR-2 drive-node-project and
FR-9 repo-per-test). Written failing first (task CRWTF-1).

Drives the trial Hub (:8010 by default, `--hub` for another; never :8000). Every run creates its
own scratch, named for the run, under ~/Documents/aw-d1105-checks-<time>/, and removes it and the
projects it opened at the end, pass or fail (`--keep` leaves them for a look).

No agent turn is spent. Each task is on a disabled, documentless loop whose work merges its branch
tip (`work_needs_evidence: false`), so the drive commits the task's work to the task's own branch
(`agentweave/task/<id>`) itself, as a builder would, and the operator moves the task to completed.

Steps:

  node  (FR-2 drive-node-project) -- a Node project whose only check runs Node's built-in test
        runner with `--test-reporter=junit` to report.xml, with report path `report.xml` and a
        re-run command `node rerun.js <log> {tests}`. rerun.js appends the ids it was given to a
        log outside the project, turns each `classname::name` into `--test-name-pattern`, and runs
        the same reporter. The task's work breaks one of two tests. PASS needs: the run failed;
        its result names exactly `test::adds two numbers`; its confirmation re-ran that test alone
        (`how: tests`, `tests: [id]`); and the re-run command was run, every time, with only that
        id. Before the build the settings route refuses the two fields; the drive then saves the
        check without them so the run still happens, and its result names no test.

  repo  (FR-9 repo-per-test) -- a clone of this checkout opened as a project, with the check
        settings the build delivers (DELIVERED, below) applied exactly. The task adds one failing
        Hub test inside a test class, and lists it in the sweep set so `sweep` meets it before
        review even where `hub-tests` runs only at landing. PASS needs: the settings read back
        as delivered; the failing check names exactly that test; and its confirmation re-ran that test alone. Skipped, with
        a message, until DELIVERED exists (the repo-settings task delivers it). It runs the
        delivered checks for real, so it takes as long as hub-tests does (10-20 minutes).

    py -3.11 scripts/drive/d1105_checks_report_tests.py               # both steps
    py -3.11 scripts/drive/d1105_checks_report_tests.py --only node   # or --only repo
    py -3.11 scripts/drive/d1105_checks_report_tests.py --keep        # leave the scratch

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

ROOT = pathlib.Path(__file__).resolve().parents[2]
#: The check settings the build delivers for this repository, as the operator pastes them into the
#: check settings: a JSON list of checks, or an object whose `checks` is one (FR-9).
DELIVERED = ROOT / "scripts" / "checks" / "check_settings.json"
TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
SCRATCH = pathlib.Path.home() / "Documents" / f"aw-d1105-checks-{time.strftime('%H%M%S')}"
HAIKU = "claude-haiku-4-5-20251001"  # the loop's agent never takes a turn; a runner is required
GIT_ID = ["-c", "user.name=d1105", "-c", "user.email=d1105@drive"]

NODE_TEST = """const test = require('node:test');
const assert = require('node:assert');
const { add } = require('./calc');

test('adds two numbers', () => {
  assert.strictEqual(add(2, 3), 5);
});

test('adds zero', () => {
  assert.strictEqual(add(0, 0), 0);
});
"""
NODE_CALC = "exports.add = (a, b) => a + b;\n"
NODE_BROKEN = "exports.add = (a, b) => a - b;\n"  # 'adds zero' still passes: 0 - 0 = 0
#: The project's re-run wrapper: the Hub passes it `classname::name` ids as separate arguments;
#: Node selects tests by name, so the wrapper drops the classname. Its first argument is the log.
NODE_RERUN = r"""const fs = require('fs');
const { spawnSync } = require('child_process');
const [log, ...ids] = process.argv.slice(2);
fs.appendFileSync(log, JSON.stringify({ cwd: process.cwd(), ids }) + '\n');
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = ids.map((id) => '--test-name-pattern=^' + escape(id.slice(id.indexOf('::') + 2)) + '$');
const args = ['--test', '--test-reporter=junit', '--test-reporter-destination=report.xml', ...patterns];
const run = spawnSync(process.execPath, args, { stdio: 'inherit' });
process.exit(run.status === null ? 1 : run.status);
"""
NODE_ID = "test::adds two numbers"

REPO_TEST_FILE = "hub/tests/test_d1105_drive_fails_on_purpose.py"
SWEEP_SET = "scripts/checks/sweep_tests.txt"
REPO_TEST = '''"""Added by scripts/drive/d1105_checks_report_tests.py on a scratch clone; never on main."""


class TestD1105Drive:
    def test_fails_on_purpose(self):
        assert 1 + 1 == 3

    def test_passes(self):
        assert 1 + 1 == 2
'''
#: The id's tail whatever the rootdir pytest's report is relative to: `<module>.<class>::<name>`.
REPO_ID_TAIL = "test_d1105_drive_fails_on_purpose.TestD1105Drive::test_fails_on_purpose"

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
            {"name": "claude haiku (d1105)", "cli": "claude", "model": HAIKU},
        )
        hub.call("POST", f"/projects/{self.id}/agents", {"name": "builder", "runner_id": runner["id"]})
        # Disabled: it never fires. It gives the task a source whose approval merges the branch tip,
        # so the task's own branch is what its checks run on.
        hub.call(
            "POST",
            f"/projects/{self.id}/jobs",
            {"name": "d1105 drive", "agent": "builder", "message": "work", "cron": "0 0 1 1 *",
             "enabled": False, "purpose": "d1105 drive", "work_needs_evidence": False},
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
            {"title": title, "description": "d1105 drive", "loop_id": self.loop},
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
            code, res = self.hub.request("PATCH", f"/projects/{self.id}/tasks/{task}", {"status": status})
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


# --- node (FR-2) -------------------------------------------------------------------------------


def node_step(hub: Hub, keep: list) -> None:
    if shutil.which("node") is None:
        check("node: Node is installed", False, "node is not on PATH")
        return
    root = SCRATCH / "node" / "project"
    root.mkdir(parents=True)
    log = (SCRATCH / "node" / "rerun-log.jsonl").as_posix()
    for rel, text in {"calc.js": NODE_CALC, "calc.test.js": NODE_TEST, "rerun.js": NODE_RERUN,
                      ".gitignore": "report.xml\n"}.items():
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "calc and its tests")
    project = Project(hub, root)
    keep.append(project)
    check_settings = {
        "name": "node-tests",
        "command": "node --test --test-reporter=junit --test-reporter-destination=report.xml",
        "timeout_seconds": 300,
        "report_path": "report.xml",
        "rerun_command": f"node rerun.js {log} {{tests}}",
    }
    code, res = project.apply_checks([check_settings], "master")
    saved = res.get("checks", [{}])[0] if code < 300 and isinstance(res, dict) else {}
    accepted = check(
        "node: the settings save a report path and a re-run command",
        code < 300 and saved.get("report_path") == "report.xml"
        and saved.get("rerun_command") == check_settings["rerun_command"],
        f"HTTP {code} {json.dumps(res)[:300] if code >= 300 else json.dumps(saved)[:300]}",
    )
    if not accepted:
        note("saving the check without them, so the run still happens (the before-the-build case)")
        bare = {k: v for k, v in check_settings.items() if k not in ("report_path", "rerun_command")}
        code, res = project.apply_checks([bare], "master")
        if code >= 300:
            raise RuntimeError(f"saving the bare check -> {code}: {res}")

    task = project.task_with_work("Make add subtract", {"calc.js": NODE_BROKEN})
    run = project.wait_run(task, minutes=5)
    result = result_named(run, "node-tests")
    show(result)
    check("node: the run failed", run["state"] == "failed", f"state {run['state']} {run.get('error') or ''}")
    ids = test_ids(result)
    check("node: the result names exactly the failing test", ids == [NODE_ID], f"named {ids}")
    confirmed = result.get("confirmed") or {}
    check(
        "node: the confirmation re-ran that test alone",
        confirmed.get("how") == "tests" and list(confirmed.get("tests") or []) == [NODE_ID],
        f"confirmed {json.dumps(confirmed)[:300]}",
    )
    lines = pathlib.Path(log).read_text(encoding="utf-8").splitlines() if pathlib.Path(log).exists() else []
    calls = [json.loads(line)["ids"] for line in lines if line.strip()]
    note(f"re-run command calls: {calls}")
    check(
        "node: the re-run command ran, with only that id each time",
        bool(calls) and all(c == [NODE_ID] for c in calls),
        f"{len(calls)} call(s)",
    )


# --- repo (FR-9) -------------------------------------------------------------------------------


def delivered_checks(path: pathlib.Path) -> list | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["checks"] if isinstance(data, dict) else data


def repo_step(hub: Hub, keep: list, delivered: pathlib.Path) -> None:
    checks = delivered_checks(delivered)
    if checks is None:
        print(
            f"[SKIP] repo: no delivered check settings at {delivered} -- the "
            "repo-settings task delivers them; until it lands this step cannot run",
            flush=True,
        )
        return
    root = SCRATCH / "repo" / "project"
    root.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(root)], check=True)
    branch = git(root, "branch", "--show-current")
    project = Project(hub, root)
    keep.append(project)
    code, res = project.apply_checks(checks, branch)
    saved = res.get("checks") if code < 300 and isinstance(res, dict) else None
    as_delivered = saved is not None and len(saved) == len(checks) and all(
        all(s.get(k) == v for k, v in c.items()) for s, c in zip(saved, checks)
    )
    check(
        "repo: the delivered settings are what was applied",
        as_delivered,
        f"HTTP {code} {json.dumps(res)[:400] if not as_delivered else ''}",
    )
    if saved is None:
        return
    # Listed in the sweep set too, so `sweep` (before review) meets it whatever phase `hub-tests`
    # runs in: the operator's runs only at landing, which a task's own run never reaches.
    sweep_set = (root / SWEEP_SET).read_text(encoding="utf-8").rstrip("\n") + "\n"
    task = project.task_with_work(
        "Add a failing Hub test",
        {REPO_TEST_FILE: REPO_TEST, SWEEP_SET: sweep_set + REPO_TEST_FILE + "\n"},
    )
    run = project.wait_run(task, minutes=60)
    note(f"run {run['id']}: {run['state']} {run.get('error') or ''}")
    failing = [r for r in run.get("results") or [] if r.get("exit_code") not in (0, None)
               or r.get("confirmed")]
    check("repo: a check failed", run["state"] == "failed" and bool(failing),
          f"state {run['state']}, results {[r.get('name') for r in run.get('results') or []]}")
    for result in failing:
        show(result)
        ids = test_ids(result)
        name = result.get("name")
        check(
            f"repo: {name} names exactly the failing test in the class",
            len(ids) == 1 and ids[0].endswith(REPO_ID_TAIL),
            f"named {ids}",
        )
        confirmed = result.get("confirmed") or {}
        check(
            f"repo: {name}'s confirmation re-ran that test alone",
            confirmed.get("how") == "tests" and list(confirmed.get("tests") or []) == ids[:1],
            f"confirmed {json.dumps(confirmed)[:300]}",
        )


# --- main --------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hub", default="http://127.0.0.1:8010")
    parser.add_argument("--only", choices=("node", "repo"))
    parser.add_argument("--keep", action="store_true", help="leave the scratch and its projects")
    parser.add_argument("--delivered", type=pathlib.Path, default=DELIVERED,
                        help="the repo step's check settings (default: the delivered file)")
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
        steps = (("node", node_step), ("repo", lambda h, k: repo_step(h, k, args.delivered)))
        for name, step in steps:
            if args.only in (None, name):
                try:
                    step(hub, projects)
                except Exception as exc:  # a broken step is a failure, never a pass
                    check(f"{name}: the step ran to the end", False, repr(exc)[:600])
    finally:
        if args.keep:
            note(f"kept {SCRATCH} and projects {[p.id for p in projects]}")
        else:
            for project in projects:
                try:
                    project.remove()
                except Exception as exc:  # noqa: BLE001 -- clean up the rest regardless
                    note(f"could not remove {project.id}: {exc!r}")
            rmtree(SCRATCH)
    print("FAILED: " + ", ".join(failures) if failures else "ALL PASS", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
