"""Acceptance drive for "A development checkout updates the same way"
(spec/changes/a-development-checkout-updates-the-same-way).

Written failing first (task DCUSW-1), against the CONTRACT in the document's design:
  * GET /health gains, for a checkout Hub, `commit` (40-hex HEAD read once at Hub start) and
    `branch` (the checked-out branch, null when detached);
  * the window bridge's `update_status()` gains `kind` ("checkout"), `commit`, `branch`,
    `master_tip`, `behind` (int), `dirty` (repo-relative paths), and `message`; `available` is
    false off master;
  * `set_auto_update(on, kind)`, kind "checkout" writing `auto_checkout` (default false) into
    HUB_DIR/app-window/update.json beside the pip key `auto`;
  * `apply_update(confirmed)` -> {"state": "needs_confirm" | "applied" | "failed" | "blocked"}:
    needs_confirm also for a dirty tree (its detail naming the files), failed for a failed
    rehearsal (old Hub untouched) and for a restored failed start, blocked when the previous
    commit cannot be prepared (before anything is stopped);
  * HUB_DIR/update-backups/<stamp>/ (the database copy) and HUB_DIR/previous-commit/<sha>.

What it builds, all of it scratch and its own:
  * per step, a clone of THIS checkout under %TEMP%\\agentweave-d1107co\\<run>\\clones\\<step>,
    on a branch `master` at this checkout's HEAD, with a bare remote of its own as `origin`;
    the drive then commits to the clone's master as a merge would (a harmless file; a migration
    that raises; a lifespan that raises, so the Hub passes migrations and will not start);
  * a virtual environment (cached in %TEMP%\\agentweave-d1107co\\venv for its dependencies) with
    the step's clone installed editable (`pip install -e <clone>/hub -e <clone>`), which is how a
    checkout runs the Hub: the code served is the clone's working tree;
  * a scratch home: USERPROFILE points at it, so HUB_DIR (profiles, .env, update.json, backups,
    previous-commit) is the drive's own, never the operator's ~/.agentweave/hub; CLAUDE_CONFIG_DIR
    keeps the real ~/.claude so Haiku turns can sign in. Scratch ports 8192-8193 by default; never
    :8000 or :8010, which are only listed (netstat), never called.

"A Hub behind, nothing running" is a Hub of the clone started with `--hub-only` (what an update
starts: detached, no window) before the drive commits to master: once the commit lands, the
checkout's code is newer than the code that Hub runs. The app is then launched as the shortcut
launches it (`_resolve_shortcut_target()` of the scratch install, plus --profile/--port). The page
is read through WebView2's DevTools port and the bridge is called from the page, as the page does.
Real agent turns run on Haiku where work must be running (a turn that sleeps in a shell).

Steps, each named after the criterion it checks (`--only` takes these names):
  reports-commit  c-reports-commit        /health commit and branch == the clone's; App settings too
  knows-behind    c-knows-behind          two local commits + one pushed only to the remote:
                                          behind 2, no fetch; .git unreadable: nothing, no error
  auto-off        c-auto-default-off      setting at default: Hub left on its commit, Update shown;
                                          set_auto_update(true, "checkout") holds across a launch
  idle            c-launch-restarts-idle  auto_checkout on, idle Hub behind: window on the new
                                          commit, no console window of the app's
  busy            c-never-interrupts      a Haiku turn running, auto on, a launch: same pid, same
                                          turn; apply_update(false) needs_confirm naming the turn
  rehearsal       c-rehearsal             a commit whose migration raises: same pid, same database,
                                          the failure shown
  previous        c-previous-not-ready    HUB_DIR/previous-commit unwritable: blocked, same pid/db
  apply-reload    c-apply-reload          maximized window, a turn run and ended, Update: same
                                          window, maximized, new commit, same projects and runs
  failed-start    c-failed-start          a commit whose Hub will not start: previous commit running
                                          on the database copy, the failure shown
  dirty           c-dirty                 dirty master and a feature-branch clone, auto on: no
                                          restart at launch; dirty prompt names the file, confirmed
                                          restarts leaving it; feature branch shown, no update
  own-hub         c-own-hub               two Hubs of one clone, one updated: the other's pid,
                                          health and running turn untouched

Assumptions about details the CONTRACT leaves open (named once so the build can move them):
  UPDATE_BUTTON -- data-testid="update-button" (else: a button whose words say Update and name a
                   commit count, "commit", "master" or a number).
  set_auto_update takes (on, kind) positionally, kind "checkout".
  "Unwritable previous-commit location" is HUB_DIR/previous-commit made a plain file, so nothing
  can be created beneath it (an ACL deny is not reliable against the owner on Windows).
  "Repository unreadable" is the clone's .git denied to the current user (icacls), restored after.

Ends with one baseline line per criterion,
  check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <first failing assertion>
which is what the drive task's `drive_baseline` evidence carries.

Restores on exit what a scratch launch rewrites outside the scratch home: the `agentweave:` link
registration (HKCU) and the Start-menu shortcut. Kills every process it started, and every process
running from the scratch venv.

  py -3.11 scripts/drive/d1107_updates_a_checkout.py
  py -3.11 scripts/drive/d1107_updates_a_checkout.py --only reports-commit,knows-behind
  py -3.11 scripts/drive/d1107_updates_a_checkout.py --port 8192 --fresh-venv
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
import d1105_own_app as d  # noqa: E402
import d1107_updates_itself as u  # noqa: E402
import d1108_windows_notifications as w  # noqa: E402

user32 = u.user32
note, wait_for = d.note, d.wait_for

FORBIDDEN_PORTS = {8000, 8010}
NO_WINDOW = 0x08000000
SW_MAXIMIZE = 3
RUN = time.strftime("%H%M%S")
BASE = pathlib.Path(tempfile.gettempdir()) / "agentweave-d1107co"
SCRATCH = BASE / RUN
VENV = BASE / "venv"
HOME = SCRATCH / "home"
HUB_DIR = HOME / ".agentweave" / "hub"
PROFILE_PREFIX = "d1107co"
UPDATE_BUTTON = '[data-testid="update-button"]'
APPLY_LIMIT = (
    420.0  # prepare previous + rehearse + stop + start + 120 s health + restore, with room
)
SETTING_TEXT = "Restart onto master automatically when I open AgentWeave"
DIRTY_FILE = "d1107co-uncommitted.txt"
NO_INDEX = u.refusing_url()
# A line saying the update failed; the page's own "failed merges" counter is not that.
UPDATE_FAILED = re.compile(
    r"[^\n]{0,80}(updat|migrat|restart|start)[^\n]{0,80}fail[^\n]{0,120}"
    r"|[^\n]{0,80}fail[^\n]{0,80}(updat|migrat|restart|start)[^\n]{0,80}",
    re.I,
)
FEATURE = "d1107co-feature"

# The helpers of the updates-itself drive read their module's globals at call time: point them at
# this drive's scratch folder, home and venv, so nothing of that drive's (or the operator's) is used.
u.BASE, u.SCRATCH, u.VENV = BASE, SCRATCH, VENV
u.VENV_PY = VENV / "Scripts" / "python.exe"
u.HOME, u.HUB_DIR, u.APPDATA_LINK = HOME, HUB_DIR, HOME / "AppData"
VENV_PY = u.VENV_PY
sh, kill_tree = u.sh, u.kill_tree


# --- criteria ----------------------------------------------------------------------------------

CRITS = {
    c.key: c
    for c in (
        u.Criterion("c-reports-commit", "FR-1"),
        u.Criterion("c-knows-behind", "FR-2"),
        u.Criterion("c-auto-default-off", "FR-10"),
        u.Criterion("c-launch-restarts-idle", "FR-3"),
        u.Criterion("c-never-interrupts", "FR-4"),
        u.Criterion("c-rehearsal", "FR-5"),
        u.Criterion("c-previous-not-ready", "FR-11"),
        u.Criterion("c-apply-reload", "FR-6"),
        u.Criterion("c-failed-start", "FR-7"),
        u.Criterion("c-dirty", "FR-8"),
        u.Criterion("c-own-hub", "FR-9"),
    )
}


# --- the environment ---------------------------------------------------------------------------


_base_env = u.clean_env


def clean_env() -> dict:
    env = _base_env()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(name, None)
    return env


u.clean_env = clean_env  # u.pip, u.App.env and friends use it


def git(repo: pathlib.Path, *args, check: bool = True) -> str:
    done = subprocess.run(
        ["git", *map(str, args)],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=clean_env(),
        creationflags=NO_WINDOW,
    )
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(map(str, args))} in {repo}: {done.stderr.strip()}")
    return done.stdout.strip()


# --- the scratch clone -------------------------------------------------------------------------


class Clone:
    """A clone of this checkout on `master`, with a bare remote of its own as `origin`."""

    def __init__(self, name: str):
        self.path = SCRATCH / "clones" / name
        self.remote = SCRATCH / "remotes" / f"{name}.git"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.remote.parent.mkdir(parents=True, exist_ok=True)
        git(SCRATCH, "clone", "--quiet", ROOT, self.path)
        git(self.path, "checkout", "--quiet", "-B", "master")
        git(self.path, "config", "user.email", "d1107co@example.invalid")
        git(self.path, "config", "user.name", "d1107co")
        git(self.path, "config", "core.autocrlf", "false")
        git(SCRATCH, "clone", "--quiet", "--bare", self.path, self.remote)
        git(self.path, "remote", "set-url", "origin", self.remote)
        git(self.path, "fetch", "--quiet", "origin")  # the drive's own, before any Hub runs
        git(self.path, "branch", "--quiet", "-u", "origin/master", "master")
        note(f"clone {name}: {self.head()[:12]} at {self.path}")

    def head(self) -> str:
        return git(self.path, "rev-parse", "HEAD")

    def tip(self, ref: str = "refs/heads/master") -> str:
        return git(self.path, "rev-parse", ref)

    def branch(self) -> str:
        return git(self.path, "rev-parse", "--abbrev-ref", "HEAD")

    def commit(self, files: dict[str, str], message: str) -> str:
        for rel, text in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            git(self.path, "add", rel)
        git(self.path, "commit", "--quiet", "-m", message)
        return self.head()

    def harmless(self, n: int) -> str:
        return self.commit(
            {f"d1107co/commit-{n}.txt": f"commit {n} of the checkout drive\n"},
            f"d1107co: harmless commit {n}",
        )


def migration_head(clone: Clone) -> str:
    versions = clone.path / "hub" / "hub" / "migrations" / "versions"
    revisions, downs = set(), set()
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision\s*=\s*["\']([^"\']+)', text, re.M)
        down = re.search(r'^down_revision\s*=\s*["\']([^"\']+)', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            downs.add(down.group(1))
    heads = sorted(revisions - downs)
    if len(heads) != 1:
        raise SystemExit(f"cannot place the failing migration: heads {heads}")
    return heads[0]


def commit_failing_migration(clone: Clone) -> str:
    text = u.FAILING_MIGRATION.format(head=migration_head(clone))
    return clone.commit(
        {"hub/hub/migrations/versions/9999_d1107_fails.py": text},
        "d1107co: a migration made to fail",
    )


LIFESPAN = "async def lifespan(app: FastAPI):\n"


def commit_hub_that_will_not_start(clone: Clone) -> str:
    """Migrations pass (nothing new to run) and `hub.main` imports, but the app's lifespan raises,
    so uvicorn never serves /health."""
    main = clone.path / "hub" / "hub" / "main.py"
    text = main.read_text(encoding="utf-8")
    if LIFESPAN not in text:
        raise SystemExit("cannot place the failing start: no `async def lifespan` in hub/main.py")
    text = text.replace(
        LIFESPAN,
        LIFESPAN + '    raise RuntimeError("d1107co: this Hub is made not to start")\n',
        1,
    )
    return clone.commit({"hub/hub/main.py": text}, "d1107co: a Hub that will not start")


# --- the venv ----------------------------------------------------------------------------------


def ensure_venv(fresh: bool) -> None:
    marker = VENV / ".d1107co-ready"
    if fresh:
        u.remove_venv()
    if marker.exists() and VENV_PY.exists():
        u.sweep_pip_leftovers()
        return
    u.remove_venv()
    done = sh(["py", "-3.11", "-m", "venv", VENV], timeout=300, env=clean_env())
    if done.returncode != 0:
        raise SystemExit(f"venv: {done.stderr}")
    u.pip("install", "-U", "pip", "setuptools>=77", "wheel")


def install_clone(clone: Clone) -> None:
    """The scratch install runs `clone`'s working tree (editable, both packages)."""
    marker = VENV / ".d1107co-ready"
    if not marker.exists():
        u.pip(
            "install",
            "-c",
            ROOT / "constraints-dev.txt",
            "-e",
            clone.path / "hub",
            "-e",
            clone.path,
            "pywebview>=5.0",
        )
        marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        return
    u.pip(
        "install",
        "--no-deps",
        "--no-build-isolation",
        "-e",
        clone.path / "hub",
        "-e",
        clone.path,
    )


def served_from() -> str:
    done = sh(
        [VENV_PY, "-c", "import hub, os; print(os.path.dirname(os.path.abspath(hub.__file__)))"],
        timeout=60,
        env=clean_env(),
        cwd=HUB_DIR,
    )
    return done.stdout.strip()


# --- the scratch app ---------------------------------------------------------------------------


class App(u.App):
    """One scratch Hub of the clone the venv runs, on one port and profile."""

    def __init__(self, port: int, profile: str, cwd: pathlib.Path, cdp: int, clone: Clone):
        super().__init__(port, profile, cwd, cdp)
        self.clone = clone

    def env(self, index_url: str = "") -> dict:
        # The pip slice's release check is pointed at a port nothing listens on, so no step can
        # reach PyPI: on an editable install its apply_update still ran a pip install of the
        # newest release (F1182, seen on this drive's first run).
        return super().env(NO_INDEX)

    def open_app(self, timeout: float = 120) -> int | None:
        return self.open("", timeout)

    def launch_app(self) -> subprocess.Popen:
        return self.launch("")

    def start_headless(self) -> str:
        """Start this port's Hub with no window (`--hub-only`); '' when it answers.

        Run from the project folder, as a launch is, and never from HUB_DIR: `agentweave` loads
        `./.env` into its environment first, and HUB_DIR/.env names the FIRST profile's
        DATABASE_URL, which then wins over --profile (F1181, seen on this drive's first run)."""
        done = sh(
            [
                VENV_PY,
                "-m",
                "agentweave",
                "--hub-only",
                "--port",
                self.port,
                "--profile",
                self.profile,
            ],
            timeout=300,
            env=self.env(),
            cwd=self.cwd,
        )
        if not self.wait_healthy(60):
            tail = (done.stdout + done.stderr).strip()[-400:]
            return f"exit {done.returncode}: {tail}"
        return ""

    def commit(self) -> str | None:
        return (self.health() or {}).get("commit")

    def update_button(self) -> str | None:
        return self.page_try(
            f"""(() => {{
  const words = e => [e.innerText, e.getAttribute('aria-label'), e.title].filter(Boolean).join(' ');
  const b = document.querySelector('{UPDATE_BUTTON}')
    || [...document.querySelectorAll('button')].find(e => /\\bupdate\\b/i.test(words(e))
         && /(commit|master|behind|\\d)/i.test(words(e)));
  return b ? words(b).trim() : null;
}})()""",
            None,
        )

    def status(self) -> tuple[dict, str]:
        value, why = u.bridge_try(self, "update_status")
        return (value if isinstance(value, dict) else {}), why


def update_file() -> pathlib.Path:
    return HUB_DIR / "app-window" / "update.json"


def set_settings(values: dict | None) -> None:
    """update.json as App settings writes it; None removes it (every setting at its default)."""
    path = update_file()
    if values is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values), encoding="utf-8")


def settings_file() -> dict:
    try:
        return json.loads(update_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def forget_check() -> None:
    (HUB_DIR / "app-window" / "update-check.json").unlink(missing_ok=True)


def message_text(status: dict) -> str:
    message = status.get("message")
    if isinstance(message, dict):
        return f"{message.get('state', '')}: {message.get('detail', '')}"
    return str(message or "")


def newest_copy(before: list[pathlib.Path]) -> pathlib.Path | None:
    for folder in reversed([p for p in u.backups() if p not in before]):
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix == ".db":
                return f
    return None


def flat(text: str | None, n: int = 300) -> str:
    return re.sub(r"\s+", " ", text or "")[:n]


def serves_own_db(app: App) -> tuple[bool, str]:
    """Does the Hub on the app's port serve its own profile's database? Its project ids, read
    through the API, against the profile file's (F1181: a restart from HUB_DIR opened another's)."""
    code, projects = app.api("GET", "/projects")
    rows = projects if isinstance(projects, list) else (projects or {}).get("projects", [])
    served = {p.get("id") for p in rows if isinstance(p, dict)}
    on_file = u.ids(app, "projects")
    return (
        bool(on_file) and served == on_file,
        f"API {sorted(served)} ({code}), file {sorted(on_file)}",
    )


def start_turn(app: App, seconds: int) -> tuple[str | None, str]:
    """A real Haiku turn that stays in progress for about `seconds` (d1105's, with its length)."""
    code, projects = app.api("GET", "/projects")
    rows = projects if isinstance(projects, list) else (projects or {}).get("projects", [])
    project = next(
        (
            p
            for p in rows
            if pathlib.Path(p.get("path") or p.get("working_directory") or "").resolve()
            == app.cwd.resolve()
        ),
        None,
    )
    if project is None:
        code, project = app.api(
            "POST", "/projects/open", {"path": str(app.cwd), "name": app.cwd.name}
        )
    if not isinstance(project, dict) or "id" not in project:
        return None, f"no project for {app.cwd}: {code} {str(project)[:300]}"
    a = f"/projects/{project['id']}"
    app.api("PATCH", a, {"main_branch": "main"})
    _, runner = app.api(
        "POST", f"{a}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
    )
    if not isinstance(runner, dict) or "id" not in runner:
        return None, f"runner: {runner}"
    app.api("POST", f"{a}/agents", {"name": "worker", "runner_id": runner["id"]})
    code, run = app.api(
        "POST",
        f"{a}/agent/trigger",
        {
            "agent": "worker",
            "session_mode": "new",
            "message": "Run this shell command and wait for it to finish: "
            f"powershell -NoProfile -Command Start-Sleep -Seconds {seconds} . "
            "Then reply with the word done.",
        },
    )
    if not isinstance(run, dict):
        return None, f"trigger: {code} {run}"
    if run.get("run_id"):
        return run["run_id"], ""
    entry = run.get("queue_entry_id")
    if entry:
        delivered = wait_for(
            lambda: (
                app.db("select delivered_in_run_id from inbound_queue_entries where id=?", (entry,))
                or [[None]]
            )[0][0],
            60,
            1.0,
        )
        if delivered:
            return delivered, ""
    return None, f"trigger: {code} {json.dumps(run)[:600]}"


def running_turn(app: App, seconds: int) -> tuple[str | None, str]:
    run_id, why = start_turn(app, seconds)
    if run_id and wait_for(lambda: d.run_status(app, run_id) == "running", 90, 1.0):
        return run_id, ""
    return None, why or f"{run_id} {run_id and d.run_status(app, run_id)}"


def profile(step: str) -> str:
    return f"{PROFILE_PREFIX}{RUN}{step}"


class Ctx:
    def __init__(self, ports, cdps):
        self.ports, self.cdps = ports, cdps

    def app(self, step: str, clone: Clone, which: int = 0) -> App:
        name = f"{step}{which}" if which else step
        return App(self.ports[which], profile(name), u.project_dir(name), self.cdps[which], clone)


def prepare(c: u.Criterion, name: str) -> Clone | None:
    """A fresh clone of this checkout, installed as the scratch install's code."""
    try:
        clone = Clone(name)
        install_clone(clone)
    except Exception as exc:
        c.need("a scratch clone is made and installed", False, f"{type(exc).__name__}: {exc}")
        return None
    where = served_from()
    if not c.need(
        "the scratch install serves the clone's working tree",
        pathlib.Path(where or ".").resolve() == (clone.path / "hub" / "hub").resolve(),
        where,
    ):
        return None
    return clone


def behind_headless(c: u.Criterion, app: App, commits: int = 1) -> tuple[str, list[int]] | None:
    """A Hub of the clone running with nothing to do, then `commits` harmless commits on master.
    Returns (the commit the Hub started from, its pid)."""
    why = app.start_headless()
    if not c.need("a Hub of the clone runs (started headless, no window)", not why, why):
        return None
    old = app.clone.head()
    for n in range(commits):
        app.clone.harmless(n + 1)
    pids = app.hub_pids()
    if not c.need(
        f"the clone's master is {commits} commit(s) past the Hub's start",
        git(app.clone.path, "rev-list", "--count", f"{old}..master") == str(commits),
        f"Hub started at {old[:12]}, master {app.clone.tip()[:12]}",
    ):
        return None
    c.need("the Hub runs as one process", len(pids) == 1, str(pids))
    return old, pids


# --- steps -------------------------------------------------------------------------------------


def step_reports_commit(ctx: Ctx) -> None:
    c = CRITS["c-reports-commit"]
    set_settings(None)
    clone = prepare(c, "reports")
    if clone is None:
        return
    app = ctx.app("reports", clone)
    try:
        hwnd = app.open_app()
        if not c.need("the app's window opens", hwnd is not None):
            return
        if not c.need(
            "its Hub answers and the page loads", app.wait_healthy() and app.page_ready()
        ):
            return
        health = app.health() or {}
        note(f"/health: {health}")
        head, branch = clone.head(), clone.branch()
        c.check(
            "GET /health `commit` is the clone's HEAD",
            health.get("commit") == head,
            f"commit {health.get('commit')!r}, HEAD {head}",
        )
        c.check(
            "GET /health `branch` is the clone's branch (master)",
            health.get("branch") == branch == "master",
            f"branch {health.get('branch')!r}, clone {branch!r}",
        )
        text = app.settings_text() or ""
        c.check(
            "App settings names the commit (at least its first 7 characters) and the branch",
            head[:7] in text and "master" in text,
            flat(text),
        )
        note(f"/health install: {health.get('install')!r} (CONTRACT: 'checkout')")
    finally:
        app.cleanup()


def step_knows_behind(ctx: Ctx) -> None:
    c = CRITS["c-knows-behind"]
    set_settings(None)
    clone = prepare(c, "behind")
    if clone is None:
        return
    app = ctx.app("behind", clone)
    denied = False
    try:
        why = app.start_headless()
        if not c.need("a Hub of the clone runs", not why, why):
            return
        old = clone.head()
        clone.harmless(1)
        clone.harmless(2)
        git(clone.path, "push", "--quiet", "origin", "master")
        tracking = clone.tip("refs/remotes/origin/master")
        worker = SCRATCH / "clones" / "behind-upstream"
        git(SCRATCH, "clone", "--quiet", clone.remote, worker)
        git(worker, "config", "user.email", "d1107co@example.invalid")
        git(worker, "config", "user.name", "d1107co")
        (worker / "d1107co").mkdir(exist_ok=True)
        (worker / "d1107co" / "commit-3.txt").write_text("only on the remote\n", encoding="utf-8")
        git(worker, "add", "d1107co/commit-3.txt")
        git(worker, "commit", "--quiet", "-m", "d1107co: a commit only the remote holds")
        git(worker, "push", "--quiet", "origin", "master")
        remote_tip = git(clone.remote, "rev-parse", "refs/heads/master")
        master = clone.tip()
        if not c.need(
            "master is 2 past the Hub, the remote 3 past it, the clone not fetched",
            git(clone.path, "rev-list", "--count", f"{old}..master") == "2"
            and git(clone.remote, "rev-list", "--count", f"{old}..master") == "3"
            and tracking == master,
            f"Hub {old[:12]}, master {master[:12]}, origin/master {tracking[:12]},"
            f" remote {remote_tip[:12]}",
        ):
            return
        forget_check()
        hwnd = app.open_app()
        if not c.need(
            "the app opens on that Hub",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        wait_for(lambda: app.update_button(), 15, 1.0)
        status, why = app.status()
        note(f"update_status(): {status or why}")
        c.check(
            "update_status says 2 commits behind (not 3)",
            status.get("behind") == 2,
            why or f"behind {status.get('behind')!r}",
        )
        c.check(
            "update_status names the Hub's commit and the local master tip",
            status.get("commit") == old and status.get("master_tip") == master,
            f"commit {status.get('commit')!r}, master_tip {status.get('master_tip')!r}",
        )
        button = app.update_button()
        c.check(
            "the Update button is shown and says how many (2)",
            bool(button) and bool(re.search(r"\b2\b", button)),
            repr(button),
        )
        c.check(
            "no fetch ran: origin/master in the clone is unchanged, master is unchanged",
            clone.tip("refs/remotes/origin/master") == tracking and clone.tip() == master,
            f"origin/master {clone.tip('refs/remotes/origin/master')[:12]}, master {clone.tip()[:12]}",
        )
        app.cleanup()

        # The repository unreadable: the clone's .git denied to this user.
        user = os.environ.get("USERNAME") or os.getlogin()
        done = sh(["icacls", clone.path / ".git", "/deny", f"{user}:(OI)(CI)(RX)"], timeout=60)
        denied = done.returncode == 0
        probe = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=clone.path,
            capture_output=True,
            text=True,
            env=clean_env(),
            creationflags=NO_WINDOW,
        )
        if not c.need(
            "the clone's git directory is unreadable (git rev-parse fails)",
            denied and probe.returncode != 0,
            f"icacls {done.returncode} {done.stdout.strip()[-120:]}; git {probe.returncode}",
        ):
            return
        forget_check()
        hwnd = app.open_app()
        c.check(
            "unreadable: the app still opens",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        )
        status, why = app.status()
        note(f"update_status() with .git unreadable: {status or why}")
        c.check(
            "unreadable: update_status answers (no error raised through the bridge)",
            not why and bool(status),
            why or repr(status),
        )
        c.check(
            "unreadable: it reports nothing (not available, no behind count)",
            not status.get("available") and not status.get("behind"),
            f"available {status.get('available')!r}, behind {status.get('behind')!r}",
        )
        c.check(
            "unreadable: no Update button", app.update_button() is None, repr(app.update_button())
        )
        shown = app.body_text() + "\n" + message_text(status)
        error = re.search(r"[^\n]{0,60}(git|repositor)[^\n]{0,60}(fail|error|denied)", shown, re.I)
        c.check("unreadable: no error is shown", error is None, error.group(0) if error else "")
    finally:
        app.cleanup()
        if denied:
            user = os.environ.get("USERNAME") or os.getlogin()
            sh(["icacls", clone.path / ".git", "/remove:d", user], timeout=60)


def step_auto_off(ctx: Ctx) -> None:
    c = CRITS["c-auto-default-off"]
    set_settings(None)
    clone = prepare(c, "autooff")
    if clone is None:
        return
    app = ctx.app("autooff", clone)
    try:
        found = behind_headless(c, app)
        if found is None:
            return
        old, pids = found
        forget_check()
        hwnd = app.open_app()
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        status, why = app.status()
        note(f"update_status(): {status or why}")
        c.check(
            "the checkout setting is off by default (update_status auto_checkout false)",
            status.get("auto_checkout") is False,
            why or f"auto_checkout {status.get('auto_checkout')!r}",
        )
        c.check(
            "the launch left the Hub on its old commit (same pid, GET /health commit)",
            app.hub_pids() == pids and app.commit() == old,
            f"{pids} -> {app.hub_pids()}, commit {app.commit()!r} (old {old[:12]})",
        )
        wait_for(lambda: app.update_button(), 15, 1.0)
        button = app.update_button()
        c.check("the Update button is shown", bool(button), repr(button))
        text = app.settings_text() or ""
        c.check(f"App settings offers '{SETTING_TEXT}'", SETTING_TEXT in text, flat(text))
        done, why = u.bridge_try(app, "set_auto_update", True, "checkout")
        c.check(
            "set_auto_update(true, 'checkout') through the window",
            not why and done is not False,
            why or repr(done),
        )
        saved = settings_file()
        c.check(
            "update.json records auto_checkout true, and the pip key `auto` is not what changed",
            saved.get("auto_checkout") is True and saved.get("auto", True) is True,
            repr(saved),
        )
        app.cleanup()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need("a further launch opens", hwnd is not None and app.wait_healthy()):
            return
        app.page_ready()
        status, why = app.status()
        c.check(
            "after a further launch the setting is still on (update_status, update.json)",
            status.get("auto_checkout") is True and settings_file().get("auto_checkout") is True,
            why or f"auto_checkout {status.get('auto_checkout')!r}, file {settings_file()!r}",
        )
    finally:
        app.cleanup()


def step_idle(ctx: Ctx) -> None:
    c = CRITS["c-launch-restarts-idle"]
    set_settings({"auto_checkout": True})
    clone = prepare(c, "idle")
    if clone is None:
        return
    app = ctx.app("idle", clone)
    try:
        found = behind_headless(c, app)
        if found is None:
            return
        old, pids = found
        new = clone.tip()
        forget_check()
        watch = d.ConsoleWatch(lambda: app.pids).start()
        try:
            hwnd = app.open_app(APPLY_LIMIT)
            # The window appears at once on the splash while the restart runs behind it, with
            # the old Hub still answering: the app's page loads only once the launch is done.
            healthy = hwnd is not None and app.page_ready(APPLY_LIMIT) and app.wait_healthy()
            at_open = app.commit()
            time.sleep(3.0)
        finally:
            watch.stop()
        if not c.need("the launch opens a window", hwnd is not None):
            return
        c.check(
            "the window opens on the new commit (GET /health when it appears)",
            healthy and at_open == new,
            f"commit {at_open!r}, master {new[:12]}, old {old[:12]}",
        )
        c.check(
            "the Hub was restarted (a new pid)",
            app.hub_pids() != pids,
            f"{pids} -> {app.hub_pids()}",
        )
        c.check(
            "no console or terminal window of the app's was created",
            not watch.ours,
            str(list(watch.ours.values())) if watch.ours else "",
        )
        if watch.others:
            note(f"unattributed terminal windows (not counted): {list(watch.others.values())}")
    finally:
        app.cleanup()


def step_busy(ctx: Ctx) -> None:
    c = CRITS["c-never-interrupts"]
    set_settings({"auto_checkout": True})
    clone = prepare(c, "busy")
    if clone is None:
        return
    app = ctx.app("busy", clone)
    try:
        why = app.start_headless()
        if not c.need("a Hub of the clone runs", not why, why):
            return
        old = clone.head()
        run_id, why = running_turn(app, 240)
        if not c.need("a real Haiku turn is in progress", bool(run_id), why):
            return
        clone.harmless(1)
        pids = app.hub_pids()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        c.check(
            "after the launch the Hub pid is unchanged",
            app.hub_pids() == pids and bool(pids),
            f"{pids} -> {app.hub_pids()}",
        )
        c.check(
            "after the launch the turn is unchanged (running)",
            d.run_status(app, run_id) == "running",
            d.run_status(app, run_id),
        )
        c.check("the Hub still reports its old commit", app.commit() == old, repr(app.commit()))
        wait_for(lambda: app.update_button(), 15, 1.0)
        button = app.update_button()
        c.check("the Update button is shown", bool(button), repr(button))
        answer, why = u.bridge_try(app, "apply_update", False)
        note(f"apply_update(false) with a turn running: {answer if answer is not None else why}")
        answer = answer if isinstance(answer, dict) else {}
        c.check(
            "pressed, it asks first (state needs_confirm)",
            answer.get("state") == "needs_confirm",
            why or repr(answer),
        )
        c.check(
            "the prompt names the running turn ('1 agent turn')",
            bool(re.search(r"\b1 agent turn\b", answer.get("detail") or "")),
            repr(answer.get("detail")),
        )
        time.sleep(5.0)  # the operator cancels
        c.check(
            "after cancel: same Hub pid, old commit, the turn running",
            app.hub_pids() == pids
            and app.commit() == old
            and d.run_status(app, run_id) == "running",
            f"{app.hub_pids()} {app.commit()!r} {d.run_status(app, run_id)}",
        )
    finally:
        app.cleanup()


def dump_parts(path: pathlib.Path) -> dict:
    """`u.stable_dump`'s parts, each by name, so a moved checksum says what moved."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    queries = {
        "schema": "select name, sql from sqlite_master where type in ('table','index') order by name",
        "revision": "select * from alembic_version",
        "projects": "select id from projects order by id",
        "agents": "select id from agents order by id",
        "runners": "select id from runners order by id",
    }
    try:
        parts = {}
        for name, query in queries.items():
            try:
                parts[name] = connection.execute(query).fetchall()
            except sqlite3.Error:
                parts[name] = None
        return parts
    finally:
        connection.close()


def settled_dump(app: App, limit: float = 60.0) -> str:
    """`u.stable_dump` once two readings 5 s apart agree (or after `limit`)."""
    deadline = time.monotonic() + limit
    last = u.stable_dump(app.db_path)
    while time.monotonic() < deadline:
        time.sleep(5.0)
        now = u.stable_dump(app.db_path)
        if now == last:
            return now
        note(f"database still settling: {last[:12]} -> {now[:12]}")
        last = now
    return last


def step_rehearsal(ctx: Ctx) -> None:
    c = CRITS["c-rehearsal"]
    set_settings(None)
    clone = prepare(c, "rehearsal")
    if clone is None:
        return
    app = ctx.app("rehearsal", clone)
    try:
        why = app.start_headless()
        if not c.need("a Hub of the clone runs", not why, why):
            return
        old = clone.head()
        commit_failing_migration(clone)
        pids = app.hub_pids()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        # A just-opened window's Hub may still be writing its first rows (QA, DCUSW-4: the
        # checksum moved under an apply that changed nothing): measure from a settled database.
        before = settled_dump(app)
        parts_before = dump_parts(app.db_path)
        answer, why = u.bridge_try(app, "apply_update", True, timeout=APPLY_LIMIT)
        note(f"apply_update(true): {answer if answer is not None else why}")
        if answer is None or why:  # the page reloaded under the call: read what it recorded
            app.page_ready()
            status, _ = app.status()
            answer = status.get("message") if isinstance(status.get("message"), dict) else {}
        answer = answer if isinstance(answer, dict) else {}
        c.check(
            "the answer is failed, naming the migration",
            answer.get("state") == "failed"
            and bool(re.search(r"migrat", answer.get("detail") or "", re.I)),
            repr(answer),
        )
        c.check(
            "the old Hub is still running with the same pid",
            app.hub_pids() == pids and app.commit() == old,
            f"{pids} -> {app.hub_pids()}, commit {app.commit()!r}",
        )
        parts_after = dump_parts(app.db_path)
        c.check(
            "the database checksum is unchanged (schema, revision, projects, agents, runners)",
            u.stable_dump(app.db_path) == before,
            f"{before[:12]} -> {u.stable_dump(app.db_path)[:12]}; changed: "
            + ", ".join(k for k in parts_after if parts_after[k] != parts_before.get(k)),
        )
        c.check(
            "no trace of the failed migration's table",
            not u.has_table(app.db_path, "d1107_half_migrated"),
        )
        app.page_ready()
        status, _ = app.status()
        shown = message_text(status) + "\n" + app.body_text()
        found = UPDATE_FAILED.search(shown)
        c.check(
            "the window shows the failure", bool(found), found.group(0) if found else flat(shown)
        )
    finally:
        app.cleanup()


def step_previous(ctx: Ctx) -> None:
    c = CRITS["c-previous-not-ready"]
    set_settings(None)
    clone = prepare(c, "previous")
    if clone is None:
        return
    app = ctx.app("previous", clone)
    blocker = HUB_DIR / "previous-commit"
    try:
        found = behind_headless(c, app)
        if found is None:
            return
        old, pids = found
        if blocker.is_dir():
            shutil.rmtree(blocker, onerror=u._writable_then)
        blocker.write_text(
            "d1107co: a file where the previous-commit folder goes\n", encoding="utf-8"
        )
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        before = u.stable_dump(app.db_path)
        answer, why = u.bridge_try(app, "apply_update", True, timeout=APPLY_LIMIT)
        note(f"apply_update(true): {answer if answer is not None else why}")
        answer = answer if isinstance(answer, dict) else {}
        c.check(
            "the answer is 'blocked' with the reason",
            answer.get("state") == "blocked" and bool((answer.get("detail") or "").strip()),
            why or repr(answer),
        )
        c.check(
            "the Hub pid is unchanged and it is on its old commit",
            app.hub_pids() == pids and app.commit() == old,
            f"{pids} -> {app.hub_pids()}, commit {app.commit()!r}",
        )
        c.check(
            "the database is unchanged",
            u.stable_dump(app.db_path) == before,
            f"{before[:12]} -> {u.stable_dump(app.db_path)[:12]}",
        )
    finally:
        app.cleanup()
        if blocker.is_file():
            blocker.unlink()


def step_apply_reload(ctx: Ctx) -> None:
    c = CRITS["c-apply-reload"]
    set_settings(None)
    clone = prepare(c, "applyreload")
    if clone is None:
        return
    app = ctx.app("applyreload", clone)
    try:
        found = behind_headless(c, app)
        if found is None:
            return
        old, pids = found
        new = clone.tip()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        time.sleep(2.0)
        c.need("the window is maximized", bool(user32.IsZoomed(hwnd)))
        run_id, why = running_turn(app, 20)
        if not c.need("a real Haiku turn is in progress", bool(run_id), why):
            return
        ended = wait_for(
            lambda: d.run_status(app, run_id) not in ("running", "pending", "queued"), 300, 3.0
        )
        if not c.need("the work ends", bool(ended), d.run_status(app, run_id)):
            return
        wait_for(lambda: app.update_button(), 15, 1.0)
        button = app.update_button()
        c.check("the Update button is shown", bool(button), repr(button))
        projects, runs = u.ids(app, "projects"), u.ids(app, "runs")
        zoomed, where = bool(user32.IsZoomed(hwnd)), u.rect(hwnd)
        launcher = sorted(app.pids)
        why = app.fire("apply_update", False)
        c.check("pressed with nothing running, the update starts", not why, why)
        c.check(
            "the Hub reports the new commit",
            bool(wait_for(lambda: app.commit() == new, APPLY_LIMIT, 2.0)),
            f"commit {app.commit()!r}, master {new[:12]}",
        )
        c.check(
            "the Hub was restarted (a new pid)",
            app.hub_pids() != pids,
            f"{pids} -> {app.hub_pids()}",
        )
        c.check(
            "the same window is open (same handle, same launcher)",
            bool(user32.IsWindow(hwnd)) and sorted(app.pids) == launcher,
        )
        own, detail = serves_own_db(app)
        c.check("the restarted Hub serves this profile's database", own, detail)
        c.check("the page loads again", app.page_ready())
        c.check("the window is still maximized", bool(user32.IsZoomed(hwnd)) and zoomed)
        c.check(
            "the window has the same size and place",
            u.rect(hwnd) == where,
            f"{where} -> {u.rect(hwnd)}",
        )
        geometry = HUB_DIR / "app-window" / f"window-{app.port}.json"
        note(f"geometry file: {geometry.read_text('utf-8') if geometry.exists() else 'absent'}")
        c.check(
            "the projects and history that were there still are",
            bool(projects) and projects <= u.ids(app, "projects") and runs <= u.ids(app, "runs"),
            f"projects {len(projects)} -> {len(u.ids(app, 'projects'))},"
            f" runs {len(runs)} -> {len(u.ids(app, 'runs'))}",
        )
        # Removed after the new commit answers healthy, which is what the steps above waited
        # for: a whole tree takes seconds to delete, so give the apply time to finish.
        leftover = HUB_DIR / "previous-commit" / old[:12]
        c.check(
            "the previous-commit worktree is removed after the healthy start",
            bool(d.wait_for(lambda: not leftover.exists(), 120, 2.0)),
            str(leftover),
        )
    finally:
        app.cleanup()


def step_failed_start(ctx: Ctx) -> None:
    c = CRITS["c-failed-start"]
    set_settings(None)
    clone = prepare(c, "failedstart")
    if clone is None:
        return
    app = ctx.app("failedstart", clone)
    try:
        why = app.start_headless()
        if not c.need("a Hub of the clone runs", not why, why):
            return
        old = clone.head()
        commit_hub_that_will_not_start(clone)
        pids = app.hub_pids()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        copies = u.backups()
        why = app.fire("apply_update", True)
        c.check("the update starts (apply_update(true))", not why, why)
        moved = wait_for(lambda: app.hub_pids() != pids, 120, 1.0)
        note(f"the Hub process changed: {bool(moved)} ({pids} -> {app.hub_pids()})")
        stated = {"text": "", "answer": None}

        def failure_stated() -> bool:
            if app.commit() != old:
                return False
            answer = app.page_try("window.__d1107", None, timeout=5)
            stated["answer"] = answer
            status, _ = app.status()
            text = message_text(status) + "\n" + app.body_text()
            found = UPDATE_FAILED.search(text)
            stated["text"] = found.group(0) if found else ""
            return bool(found) and bool(moved or app.hub_pids() != pids)

        wait_for(failure_stated, APPLY_LIMIT, 3.0)
        note(f"apply_update's answer: {stated['answer']!r}")
        c.check(
            "the new commit was tried: the Hub was stopped and started again (a new pid)",
            bool(moved) or app.hub_pids() != pids,
            f"{pids} -> {app.hub_pids()}",
        )
        c.check(
            "the previous commit's Hub is running again (GET /health commit)",
            app.commit() == old,
            f"commit {app.commit()!r}, old {old[:12]}",
        )
        copy = newest_copy(copies)
        c.check("a copy of the database was taken before the stop", copy is not None, str(copy))
        c.check(
            "the database equals that copy",
            copy is not None and u.stable_dump(app.db_path) == u.stable_dump(copy),
            f"live {u.stable_dump(app.db_path)[:12]}, copy {u.stable_dump(copy)[:12] if copy else None}",
        )
        own, detail = serves_own_db(app)
        c.check("the previous commit's Hub serves this profile's database", own, detail)
        c.check("the window says the update failed", bool(stated["text"]), stated["text"])
    finally:
        app.cleanup()


def step_dirty(ctx: Ctx) -> None:
    c = CRITS["c-dirty"]
    set_settings({"auto_checkout": True})
    clone = prepare(c, "dirty")
    if clone is None:
        return
    app = ctx.app("dirty", clone)
    try:
        found = behind_headless(c, app)
        if found is None:
            return
        old, pids = found
        new = clone.tip()
        dirty = clone.path / DIRTY_FILE
        dirty.write_text("d1107co: an uncommitted file\n", encoding="utf-8")
        content = dirty.read_bytes()
        forget_check()
        hwnd = app.open_app(APPLY_LIMIT)
        if not c.need(
            "dirty: the launch opens a window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        c.check(
            "dirty: no restart at launch (same pid)",
            app.hub_pids() == pids,
            f"{pids} -> {app.hub_pids()}",
        )
        c.check(
            "dirty: the Hub still reports its old commit",
            app.commit() == old,
            f"commit {app.commit()!r}, old {old[:12]}",
        )
        status, why = app.status()
        note(f"dirty update_status(): {status or why}")
        c.check(
            "dirty: update_status lists the uncommitted file",
            DIRTY_FILE in (status.get("dirty") or []),
            why or repr(status.get("dirty")),
        )
        wait_for(lambda: app.update_button(), 15, 1.0)
        c.check(
            "dirty: the Update button is offered",
            bool(app.update_button()),
            repr(app.update_button()),
        )
        answer, why = u.bridge_try(app, "apply_update", False)
        note(f"dirty apply_update(false): {answer if answer is not None else why}")
        answer = answer if isinstance(answer, dict) else {}
        c.check(
            "dirty: unconfirmed, it asks first, naming the uncommitted file",
            answer.get("state") == "needs_confirm" and DIRTY_FILE in (answer.get("detail") or ""),
            why or repr(answer),
        )
        c.check(
            "dirty: unconfirmed, nothing restarted",
            app.hub_pids() == pids,
            f"{pids} -> {app.hub_pids()}",
        )
        why = app.fire("apply_update", True)
        c.check("dirty: confirmed, the update starts", not why, why)
        c.check(
            "dirty: confirmed, the Hub restarts onto master",
            bool(wait_for(lambda: app.commit() == new, APPLY_LIMIT, 2.0)),
            f"commit {app.commit()!r}, master {new[:12]}",
        )
        c.check(
            "dirty: the uncommitted file is untouched",
            dirty.exists() and dirty.read_bytes() == content,
        )
        app.cleanup()

        # A second clone, on a feature branch, with master ahead of it.
        feature = prepare(c, "feature")
        if feature is None:
            return
        git(feature.path, "branch", "--quiet", FEATURE)
        feature.harmless(1)
        git(feature.path, "checkout", "--quiet", FEATURE)
        other = ctx.app("feature", feature)
        try:
            why = other.start_headless()
            if not c.need("feature: a Hub of the feature-branch clone runs", not why, why):
                return
            pids = other.hub_pids()
            c.need(
                "feature: master is ahead of the branch the Hub runs",
                git(feature.path, "rev-list", "--count", f"{FEATURE}..master") == "1",
            )
            forget_check()
            hwnd = other.open_app(APPLY_LIMIT)
            if not c.need(
                "feature: the launch opens a window",
                hwnd is not None and other.wait_healthy() and other.page_ready(),
            ):
                return
            c.check(
                "feature: no restart at launch (same pid)",
                other.hub_pids() == pids,
                f"{pids} -> {other.hub_pids()}",
            )
            health = other.health() or {}
            c.check(
                "feature: GET /health names the branch",
                health.get("branch") == FEATURE,
                repr(health.get("branch")),
            )
            status, why = other.status()
            c.check(
                "feature: update_status offers nothing (available false) and names the branch",
                status.get("available") is False and status.get("branch") == FEATURE,
                why or f"available {status.get('available')!r}, branch {status.get('branch')!r}",
            )
            text = other.settings_text() or ""
            c.check("feature: App settings shows the branch", FEATURE in text, flat(text))
            c.check(
                "feature: no Update button",
                other.update_button() is None,
                repr(other.update_button()),
            )
        finally:
            other.cleanup()
    finally:
        app.cleanup()


def step_own_hub(ctx: Ctx) -> None:
    c = CRITS["c-own-hub"]
    set_settings(None)
    clone = prepare(c, "ownhub")
    if clone is None:
        return
    one, other = ctx.app("ownhub", clone, 0), ctx.app("ownhub", clone, 1)
    try:
        why_one, why_other = one.start_headless(), other.start_headless()
        if not c.need(
            "two Hubs of the clone run on two ports",
            not why_one and not why_other,
            f"{why_one} {why_other}",
        ):
            return
        old = clone.head()
        run_id, why = running_turn(other, 300)
        if not c.need(f"a real Haiku turn runs on :{other.port}", bool(run_id), why):
            return
        clone.harmless(1)
        new = clone.tip()
        hub = other.hub_pids()
        forget_check()
        hwnd = one.open_app(APPLY_LIMIT)
        if not c.need(
            f"a window opens on :{one.port}",
            hwnd is not None and one.wait_healthy() and one.page_ready(),
        ):
            return
        why = one.fire("apply_update", True)
        c.check(f"the update of :{one.port} starts", not why, why)
        c.check(
            f":{one.port} is updated onto the new commit",
            bool(wait_for(lambda: one.commit() == new, APPLY_LIMIT, 2.0)),
            f"commit {one.commit()!r}, answer {one.page_try('window.__d1107', None)!r}",
        )
        c.check(
            f"the other Hub (:{other.port}) has the same pid",
            other.hub_pids() == hub and bool(hub),
            f"{hub} -> {other.hub_pids()}",
        )
        health = other.health() or {}
        c.check(
            "the other Hub answers /health, still on its own commit",
            bool(health) and health.get("commit") == old,
            json.dumps(health)[:300],
        )
        c.check(
            "the other Hub's turn is still running",
            d.run_status(other, run_id) == "running",
            d.run_status(other, run_id),
        )
    finally:
        one.cleanup()
        other.cleanup()


STEPS = {
    "reports-commit": step_reports_commit,
    "knows-behind": step_knows_behind,
    "auto-off": step_auto_off,
    "idle": step_idle,
    "busy": step_busy,
    "rehearsal": step_rehearsal,
    "previous": step_previous,
    "apply-reload": step_apply_reload,
    "failed-start": step_failed_start,
    "dirty": step_dirty,
    "own-hub": step_own_hub,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8192, help="first of two scratch ports")
    parser.add_argument("--cdp", type=int, default=9348, help="first of two DevTools ports")
    parser.add_argument("--only", default="", help="comma-separated steps: " + ",".join(STEPS))
    parser.add_argument("--fresh-venv", action="store_true", help="rebuild the cached venv")
    opts = parser.parse_args()
    ports, cdps = [opts.port, opts.port + 1], [opts.cdp, opts.cdp + 1]
    if FORBIDDEN_PORTS & set(ports):
        raise SystemExit(f"refusing ports {ports}: :8000 and :8010 are never driven")
    busy = [p for p in ports + cdps if not d.port_free(p)]
    if busy:
        raise SystemExit(f"port(s) {busy} already in use; pick another --port/--cdp")
    chosen = [s for s in opts.only.split(",") if s] or list(STEPS)
    unknown = set(chosen) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown step(s) {sorted(unknown)}; steps are {list(STEPS)}")

    bystanders = d.bystanders()
    note(f":8000/:8010 listeners before: {bystanders}")
    link, shortcut = w.SavedLink(), u.SavedShortcut()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    u.make_home()
    try:
        ensure_venv(opts.fresh_venv)
        ctx = Ctx(ports, cdps)
        for name in chosen:
            print(f"\n=== {name}", flush=True)
            try:
                STEPS[name](ctx)
            except Exception as exc:  # a step that breaks is reported, and the next one runs
                d.check(f"{name}: the step ran to its end", False, f"{type(exc).__name__}: {exc}")
    finally:
        u.kill_venv_processes()
        link.restore()
        shortcut.restore()
        if u.unlink_home():
            shutil.rmtree(SCRATCH, onerror=u._writable_then)
        else:
            note(
                f"left {SCRATCH} in place: its AppData junction could not be removed (never rmtree it)"
            )
    d.check(
        ":8000 and :8010 are served by the same processes as before",
        d.bystanders() == bystanders,
        f"{bystanders} -> {d.bystanders()}",
    )

    print("\nBASELINE")
    for criterion in CRITS.values():
        print(criterion.line())
    failures = d.failures
    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    for name in failures:
        print(f"  - {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
