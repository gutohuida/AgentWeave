"""The checkout half of the launcher's updater (spec `a-development-checkout-updates-the-same-way`,
task DCUSW-4).

Each seam runs against a real git repository made in a temporary folder (with a bare remote, a
real `git worktree`), a real SQLite file and a real lock file; stopping and starting a Hub are
injected. The bridge and the Hub-process helpers of `cli.py` are driven with the updater's real
functions. The end-to-end run on a scratch clone is the acceptance drive,
scripts/drive/d1107_updates_a_checkout.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from agentweave import cli, updater

# --- a repository ------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return done.stdout.strip()


def _commit(repo: Path, name: str, text: str = "x\n") -> str:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Made once: git calls are slow on a busy Windows machine, a folder copy is not."""
    base = tmp_path_factory.mktemp("template")
    root = base / "checkout"
    root.mkdir()
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    _commit(root, "hub/hub/main.py", "app = None\n")
    _commit(root, "hub/ui/src/main.tsx", "export {}\n")
    _git(base, "clone", "-q", "--bare", str(root), str(base / "remote.git"))
    _git(root, "remote", "add", "origin", "../remote.git")  # relative: the copy keeps it
    _git(root, "fetch", "-q", "origin")
    _git(root, "branch", "-q", "-u", "origin/master", "master")
    return base


@pytest.fixture
def repo(_template: Path, tmp_path: Path) -> Path:
    """A checkout on master shaped like this one (`hub/hub/main.py`, `hub/ui/src`), with a bare
    remote as `origin` (`tmp_path/remote.git`) and master tracking it."""
    import shutil

    for name in ("checkout", "remote.git"):
        shutil.copytree(_template / name, tmp_path / name)
    return tmp_path / "checkout"


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


# --- finding the checkout ------------------------------------------------------------------------


def test_checkout_root_is_the_folder_holding_hub_ui_src_and_git(repo: Path, tmp_path: Path):
    assert updater.checkout_root(repo / "hub" / "hub") == repo.resolve()
    installed = tmp_path / "site-packages" / "hub"
    installed.mkdir(parents=True)
    (installed / "main.py").write_text("", encoding="utf-8")
    assert updater.checkout_root(installed) is None  # a pip install: no hub/ui/src, no .git


# --- FR-2: behind, local master only ---------------------------------------------------------------


def test_behind_counts_local_master_not_the_remote_and_fetches_nothing(repo: Path, tmp_path: Path):
    hub = _head(repo)
    _commit(repo, "one.txt")
    _commit(repo, "two.txt")
    _git(repo, "push", "-q", "origin", "master")
    tracking = _git(repo, "rev-parse", "refs/remotes/origin/master")
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    _git(other, "config", "user.email", "t@example.invalid")
    _git(other, "config", "user.name", "t")
    _commit(other, "three.txt")
    _git(other, "push", "-q", "origin", "master")

    state = updater.read_checkout(repo, hub)

    assert state is not None
    assert state.behind == 2  # not 3: the remote's third commit was never fetched
    assert state.master_tip == _head(repo) and state.commit == hub
    assert state.branch == "master" and state.on_master and state.available
    assert _git(repo, "rev-parse", "refs/remotes/origin/master") == tracking  # no fetch ran


def test_a_hub_on_master_s_tip_is_not_behind(repo: Path):
    state = updater.read_checkout(repo, _head(repo))
    assert state is not None and state.behind == 0 and not state.available


def test_dirty_lists_uncommitted_paths_with_renames(repo: Path):
    (repo / "notes.txt").write_text("mine\n", encoding="utf-8")
    (repo / "hub" / "hub" / "main.py").write_text("app = 1\n", encoding="utf-8")
    _git(repo, "mv", "hub/ui/src/main.tsx", "hub/ui/src/moved.tsx")
    state = updater.read_checkout(repo, _head(repo))
    assert state is not None
    assert sorted(state.dirty) == ["hub/hub/main.py", "hub/ui/src/moved.tsx", "notes.txt"]


def test_off_master_and_detached_are_never_available(repo: Path):
    hub = _head(repo)
    _git(repo, "checkout", "-q", "-b", "feature")
    _git(repo, "branch", "-q", "-f", "master", hub)
    _commit(repo, "on-feature.txt")
    _git(repo, "checkout", "-q", "master")
    _commit(repo, "on-master.txt")
    _git(repo, "checkout", "-q", "feature")
    state = updater.read_checkout(repo, hub)
    assert state is not None and state.branch == "feature" and state.behind == 1
    assert not state.available
    assert "branch feature" in (updater.checkout_summary(state) or "")
    _git(repo, "checkout", "-q", "--detach")
    state = updater.read_checkout(repo, hub)
    assert state is not None and state.branch is None and not state.available


def test_an_unreadable_repository_answers_none_quietly(repo: Path, tmp_path: Path):
    assert updater.read_checkout(tmp_path / "not-a-repo", _head(repo)) is None
    assert updater.read_checkout(repo, "0" * 40) is None  # a commit the repository lacks
    assert updater.read_checkout(repo, None) is None
    assert updater.read_checkout(repo, "not-a-sha") is None


@pytest.mark.parametrize("failing", ["symbolic-ref", "rev-parse", "rev-list", "status"])
def test_any_git_call_that_fails_ends_quietly(repo: Path, failing: str):
    hub = _head(repo)
    _commit(repo, "one.txt")

    def git(root: Path, *args: str, **kw: Any) -> updater.GitResult:
        if args[0] == failing:
            return 128, "", "fatal: unable to read"
        return updater.git_call(root, *args, **kw)

    assert updater.read_checkout(repo, hub, git) is None


def test_git_that_cannot_run_is_an_answer_not_an_exception(monkeypatch, repo: Path):
    def boom(*a: Any, **kw: Any) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(updater.subprocess, "run", boom)
    code, _, err = updater.git_call(repo, "status")
    assert code == -1 and "git" in err
    assert updater.read_checkout(repo, "a" * 40) is None


def test_the_watch_reads_once_then_at_most_hourly_or_for_another_commit(repo: Path):
    now = [0.0]
    reads: List[str] = []

    def read(root: Path, commit: Optional[str]) -> Optional[updater.CheckoutState]:
        reads.append(commit or "")
        return updater.CheckoutState(commit or "", "master", "b" * 40, 1, [])

    watch = updater.CheckoutWatch(clock=lambda: now[0])
    watch.state(repo, "a" * 40, read)
    now[0] = 3599
    watch.state(repo, "a" * 40, read)
    assert len(reads) == 1
    watch.state(repo, "c" * 40, read)  # the Hub restarted onto another commit
    assert len(reads) == 2
    now[0] = 3599 + 3600
    watch.state(repo, "c" * 40, read)
    assert len(reads) == 3
    watch.forget()
    watch.state(repo, "c" * 40, read)
    assert len(reads) == 4
    assert watch.state(repo, None, read) is None and len(reads) == 4


# --- FR-10: the checkout's own switch ---------------------------------------------------------------


def test_auto_checkout_is_off_by_default_and_kept_apart_from_pip_s(tmp_path: Path):
    setting = tmp_path / "update.json"
    assert updater.auto_checkout_on(setting) is False
    assert updater.auto_update_on(setting) is True
    updater.set_auto_update(setting, True, "checkout")
    assert json.loads(setting.read_text(encoding="utf-8")) == {"auto_checkout": True}
    assert updater.auto_update_on(setting) is True
    updater.set_auto_update(setting, False)  # the pip switch keeps the checkout's
    assert json.loads(setting.read_text(encoding="utf-8")) == {
        "auto_checkout": True,
        "auto": False,
    }
    assert updater.auto_checkout_on(setting) is True


# --- FR-3, FR-4, FR-8, FR-10: the launch decision ---------------------------------------------------


def _state(**over: Any) -> updater.CheckoutState:
    values: Dict[str, Any] = {
        "commit": "a" * 40,
        "branch": "master",
        "master_tip": "b" * 40,
        "behind": 1,
        "dirty": [],
    }
    values.update(over)
    return updater.CheckoutState(**values)


@pytest.mark.parametrize(
    "facts, reason",
    [
        (updater.CheckoutLaunchFacts(_state(), auto=False, hub="idle"), "automatically is off"),
        (updater.CheckoutLaunchFacts(_state(), auto=True, hub="busy"), "work is running"),
        (updater.CheckoutLaunchFacts(_state(), auto=True, hub="silent"), "work check"),
        (
            updater.CheckoutLaunchFacts(_state(dirty=["x.txt"]), auto=True, hub="idle"),
            "uncommitted",
        ),
        (
            updater.CheckoutLaunchFacts(_state(branch="feature"), auto=True, hub="idle"),
            "feature",
        ),
        (updater.CheckoutLaunchFacts(_state(behind=0), auto=True, hub="idle"), "tip of master"),
        (updater.CheckoutLaunchFacts(None, auto=True, hub="idle"), "could not be read"),
        (updater.CheckoutLaunchFacts(_state(), auto=True, hub="absent"), "no Hub runs"),
        (
            updater.CheckoutLaunchFacts(_state(), auto=True, hub="idle", window_open=True),
            "window is already open",
        ),
    ],
)
def test_a_launch_opens_as_it_is_for_every_reason_not_to_restart(facts, reason):
    decision = updater.decide_checkout_at_launch(facts)
    assert decision.action == "open" and reason in decision.reason


def test_a_launch_restarts_an_idle_hub_behind_on_a_clean_master_with_the_switch_on():
    decision = updater.decide_checkout_at_launch(
        updater.CheckoutLaunchFacts(_state(), auto=True, hub="idle")
    )
    assert decision.action == "update" and decision.target == "b" * 40


# --- FR-11: the previous commit ----------------------------------------------------------------------


def test_the_previous_commit_is_prepared_as_a_worktree_and_reused(repo: Path, tmp_path: Path):
    hub = _head(repo)
    _commit(repo, "new.txt")
    previous = tmp_path / "hubdir" / "previous-commit"
    target, why = updater.prepare_previous(repo, hub, previous)
    assert why is None and target == previous / hub[:12]
    assert (target / "hub" / "hub" / "main.py").is_file() and not (target / "new.txt").exists()
    again, why = updater.prepare_previous(repo, hub, previous)
    assert why is None and again == target
    updater.remove_previous(repo, target)
    assert not target.exists()
    assert str(target).replace("\\", "/") not in _git(repo, "worktree", "list")


def test_leftovers_are_cleared_before_a_failure_is_believed(repo: Path, tmp_path: Path):
    hub = _head(repo)
    previous = tmp_path / "previous-commit"
    target, _ = updater.prepare_previous(repo, hub, previous)
    assert target is not None
    import shutil

    shutil.rmtree(target)  # registered but missing
    target, why = updater.prepare_previous(repo, hub, previous)
    assert why is None and target is not None and target.is_dir()
    updater.remove_previous(repo, target)
    (previous / hub[:12]).mkdir(parents=True)  # a plain leftover folder
    (previous / hub[:12] / "junk.txt").write_text("x", encoding="utf-8")
    target, why = updater.prepare_previous(repo, hub, previous)
    assert why is None and target is not None and (target / "hub" / "hub" / "main.py").is_file()


def test_a_deep_hub_dir_and_a_long_tracked_path_still_make_the_previous_commit(
    repo: Path, tmp_path: Path
):
    # QA's drive (DCUSW-4): under a deep HUB_DIR, git refused a tracked path past Windows' 260
    # characters ("Filename too long") and every apply was blocked. The blob is added by plumbing,
    # so this test does not itself need to write a long path into the source checkout.
    long_dir = "/".join(["a-rather-long-folder-name-like-the-archive-has"] * 3)
    long_path = f"{long_dir}/specs/some-capability-with-a-long-name/spec.md"
    blob = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
        input="x\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{long_path}")
    _git(repo, "commit", "-q", "-m", "a long tracked path")
    hub = _head(repo)
    previous = tmp_path / ("deep-hub-dir-" + "x" * 60) / ".agentweave" / "hub" / "previous-commit"
    assert len(str(previous)) + 1 + 12 + 1 + len(long_path) > 260
    target, why = updater.prepare_previous(repo, hub, previous)
    assert why is None and target is not None
    assert target == previous / hub[:12]
    full = os.path.normpath(str(target / long_path))
    assert os.path.exists("\\\\?\\" + full if os.name == "nt" else full)
    updater.remove_previous(repo, target)
    assert not target.exists()


def test_an_unwritable_previous_location_is_a_reason(repo: Path, tmp_path: Path):
    previous = tmp_path / "previous-commit"
    previous.write_text("a file where the folder goes", encoding="utf-8")
    target, why = updater.prepare_previous(repo, _head(repo), previous)
    assert target is None and why


# --- applying ---------------------------------------------------------------------------------------


def _make_db(path: Path, rows: int = 3) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("create table projects (id text primary key)")
    conn.executemany("insert into projects values (?)", [(f"p{i}",) for i in range(rows)])
    conn.commit()
    conn.close()


def _checksum(path: Path) -> str:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    return hashlib.sha256(dump.encode()).hexdigest()


class _Hub:
    """A pretend Hub on one port: which commit it runs, and every stop and start asked of it."""

    def __init__(self, commit: str, new: str, db: Path) -> None:
        self.commit: Optional[str] = commit
        self.old = commit
        self.new = new
        self.db = db
        self.calls: List[str] = []
        self.start_fails: Optional[str] = None
        self.started_previous: Optional[Path] = None
        self.db_at_previous_start: Optional[str] = None

    def stop(self) -> Optional[str]:
        self.calls.append("stop")
        self.commit = None
        return None

    def start(self) -> Optional[str]:
        self.calls.append("start")
        if self.start_fails:
            return self.start_fails
        # what the new code's Hub does at start: migrate the real database
        conn = sqlite3.connect(str(self.db))
        conn.execute("create table if not exists migrated (id integer)")
        conn.commit()
        conn.close()
        self.commit = self.new
        return None

    def start_previous(self, worktree: Path) -> Optional[str]:
        self.calls.append("start_previous")
        self.started_previous = worktree
        self.db_at_previous_start = _checksum(self.db)
        # The folder is named by the commit's first 12 characters (`updater.previous_folder`).
        self.commit = self.old if self.old and self.old.startswith(worktree.name) else worktree.name
        return None


def _applier(repo: Path, tmp_path: Path, hub: _Hub, **over: Any) -> updater.CheckoutApplier:
    rehearsed: List[Path] = []

    def rehearse(copy: Path) -> Any:
        rehearsed.append(copy)
        return True, "ok"

    values: Dict[str, Any] = {
        "port": 8173,
        "root": repo,
        "db_path": hub.db,
        "backups_root": tmp_path / "hubdir" / "update-backups",
        "previous_root": tmp_path / "hubdir" / "previous-commit",
        "lock": updater.UpdateLock(tmp_path / "hubdir" / "app-window" / "update.lock"),
        "hub_commit": lambda: hub.commit,
        "stop": hub.stop,
        "start": hub.start,
        "start_previous": hub.start_previous,
        "rehearse": rehearse,
        "healthy_seconds": 0.5,
        "sleep": lambda _s: None,
    }
    values.update(over)
    applier = updater.CheckoutApplier(**values)
    applier.rehearsed = rehearsed  # type: ignore[attr-defined]
    return applier


@pytest.fixture
def behind(repo: Path, tmp_path: Path):
    """A Hub running the checkout's HEAD, then one commit on master: (repo, hub)."""
    old = _head(repo)
    new = _commit(repo, "new.txt")
    db = tmp_path / "agentweave.db"
    _make_db(db)
    return repo, _Hub(old, new, db)


def test_apply_restarts_onto_master_and_drops_the_previous_worktree(behind, tmp_path: Path):
    repo, hub = behind
    a = _applier(repo, tmp_path, hub)
    result = updater.apply_checkout_update(a, confirmed=False, work=lambda: {"running": False})
    assert result.state == "applied", result.detail
    assert hub.commit == hub.new and hub.calls == ["stop", "start"]
    assert a.rehearsed and a.rehearsed[0].name == "rehearsal.db"  # type: ignore[attr-defined]
    assert result.backup is not None and result.backup.name == "agentweave.db"
    assert not (
        updater.previous_folder(a.previous_root, _git(repo, "rev-parse", "HEAD~1"))
    ).exists()
    assert not a.lock.path.exists()


def test_work_running_asks_first_and_touches_nothing(behind, tmp_path: Path):
    repo, hub = behind
    a = _applier(repo, tmp_path, hub)
    result = updater.apply_checkout_update(
        a,
        confirmed=False,
        work=lambda: {"running": True, "turns": 1},
        describe=lambda w: "1 agent turn is running",
    )
    assert result.state == "needs_confirm" and "1 agent turn" in result.detail
    assert hub.calls == [] and not a.previous_root.exists()
    silent = updater.apply_checkout_update(a, confirmed=False, work=lambda: None)
    assert silent.state == "needs_confirm" and hub.calls == []


def test_a_dirty_tree_asks_naming_the_files_then_restarts_leaving_them(behind, tmp_path: Path):
    repo, hub = behind
    (repo / "mine.txt").write_text("uncommitted\n", encoding="utf-8")
    a = _applier(repo, tmp_path, hub)
    asked = updater.apply_checkout_update(a, confirmed=False, work=lambda: {"running": False})
    assert asked.state == "needs_confirm" and "mine.txt" in asked.detail
    assert hub.calls == []
    done = updater.apply_checkout_update(a, confirmed=True)
    assert done.state == "applied", done.detail
    assert (repo / "mine.txt").read_text(encoding="utf-8") == "uncommitted\n"


def test_off_master_is_blocked_before_anything(behind, tmp_path: Path):
    repo, hub = behind
    _git(repo, "checkout", "-q", "-b", "feature")
    result = updater.apply_checkout_update(_applier(repo, tmp_path, hub), confirmed=True)
    assert result.state == "blocked" and "feature" in result.detail and hub.calls == []


def test_a_hub_that_does_not_say_its_commit_is_not_updated(behind, tmp_path: Path):
    repo, hub = behind
    hub.commit = None
    result = updater.apply_checkout_update(_applier(repo, tmp_path, hub), confirmed=True)
    assert result.state == "blocked" and hub.calls == []


def test_previous_commit_not_ready_is_blocked_with_the_hub_and_database_untouched(
    behind, tmp_path: Path
):
    repo, hub = behind
    a = _applier(repo, tmp_path, hub)
    a.previous_root.parent.mkdir(parents=True, exist_ok=True)
    a.previous_root.write_text("not a folder", encoding="utf-8")
    before = _checksum(hub.db)
    result = updater.apply_checkout_update(a, confirmed=True)
    assert result.state == "blocked" and "nothing was stopped" in result.detail
    assert hub.calls == [] and hub.commit != hub.new and _checksum(hub.db) == before
    assert not a.rehearsed  # type: ignore[attr-defined]


def test_a_failed_rehearsal_leaves_the_hub_and_database_untouched(behind, tmp_path: Path):
    repo, hub = behind
    a = _applier(
        repo, tmp_path, hub, rehearse=lambda copy: (False, "Traceback\nRuntimeError: boom")
    )
    before = _checksum(hub.db)
    result = updater.apply_checkout_update(a, confirmed=True)
    assert result.state == "failed"
    assert "migrations failed" in result.detail and "boom" in result.detail
    assert hub.calls == [] and _checksum(hub.db) == before
    assert not (
        updater.previous_folder(a.previous_root, _git(repo, "rev-parse", "HEAD~1"))
    ).exists()


def test_a_start_that_fails_restores_the_database_then_starts_the_previous_commit(
    behind, tmp_path: Path
):
    repo, hub = behind
    old = hub.commit
    hub.start_fails = "exit code 1: lifespan raised"
    a = _applier(repo, tmp_path, hub)
    before = _checksum(hub.db)
    result = updater.apply_checkout_update(a, confirmed=True)
    assert result.state == "failed"
    assert "restart onto master failed" in result.detail and "lifespan raised" in result.detail
    assert hub.calls == ["stop", "start", "stop", "start_previous"]
    assert (
        hub.started_previous == updater.previous_folder(a.previous_root, old) and hub.commit == old
    )
    assert hub.db_at_previous_start == before  # restored before the previous Hub started
    assert result.backup is not None and _checksum(result.backup) == before
    assert (
        updater.previous_folder(a.previous_root, old) / "hub" / "hub" / "main.py"
    ).is_file()  # kept: it runs there


def test_a_hub_that_never_reports_healthy_is_restored_too(behind, tmp_path: Path):
    repo, hub = behind
    old = hub.commit

    def start() -> Optional[str]:
        hub.calls.append("start")
        conn = sqlite3.connect(str(hub.db))
        conn.execute("create table half_migrated (id integer)")
        conn.commit()
        conn.close()
        hub.commit = None  # started, never answers
        return None

    a = _applier(repo, tmp_path, hub, start=start)
    before = _checksum(hub.db)
    result = updater.apply_checkout_update(a, confirmed=True)
    assert result.state == "failed" and "did not report healthy" in result.detail
    assert hub.commit == old and _checksum(hub.db) == before


def test_an_update_already_under_way_is_blocked(behind, tmp_path: Path):
    repo, hub = behind
    a = _applier(repo, tmp_path, hub)
    a.lock.path.parent.mkdir(parents=True, exist_ok=True)
    a.lock.path.write_text(json.dumps({"pid": os.getpid(), "port": 9}), encoding="utf-8")
    result = updater.apply_checkout_update(a, confirmed=True)
    assert result.state == "blocked" and "port 9" in result.detail and hub.calls == []


# --- cli: the Hub processes ---------------------------------------------------------------------------


def test_the_rehearsal_runs_the_checkout_s_code_on_the_copy(tmp_path: Path):
    """`_hub_rehearse_migrations` imports `hub` from the checkout's `hub/` and points
    DATABASE_URL at the copy; a migration that raises is a failure with its message."""
    root = tmp_path / "co"
    pkg = root / "hub" / "hub"
    (pkg / "migrations" / "versions").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    seen = tmp_path / "seen.txt"
    env_py = pkg / "migrations" / "env.py"
    env_py.write_text(
        "import os, hub\n"
        f"open({str(seen)!r}, 'w').write(os.environ['DATABASE_URL'] + '|' + hub.__file__)\n",
        encoding="utf-8",
    )
    copy = tmp_path / "rehearsal.db"
    ok, output = cli._hub_rehearse_migrations(root, copy)
    assert ok, output
    url, imported = seen.read_text(encoding="utf-8").split("|")
    assert url == f"sqlite+aiosqlite:///{copy.as_posix()}"
    assert Path(imported).resolve() == (pkg / "__init__.py").resolve()
    env_py.write_text("raise RuntimeError('d1107 migration made to fail')\n", encoding="utf-8")
    ok, output = cli._hub_rehearse_migrations(root, copy)
    assert not ok and "d1107 migration made to fail" in output


def test_the_restart_names_the_profile_s_database_outright(monkeypatch, tmp_path: Path):
    """F1181: run from HUB_DIR, `agentweave` would load HUB_DIR/.env's DATABASE_URL (the first
    profile's) over --profile; the restart passes the profile's own."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path / "hub")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    seen: Dict[str, Any] = {}

    def run(cmd: List[str], **kw: Any) -> Any:
        seen.update(kw)
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli._hub_start_for_update(8174, "other") is None
    expected = (cli._hub_profile_data_dir("other") / "agentweave.db").as_posix()
    assert seen["env"]["DATABASE_URL"] == f"sqlite+aiosqlite:///{expected}"
    assert seen["cmd"][-2:] == ["--profile", "other"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_the_previous_commit_starts_from_its_worktree_not_the_install(monkeypatch, tmp_path: Path):
    """`_hub_start_previous` runs uvicorn with the worktree's `hub/` as its working directory, so
    the worktree's `hub.main` is what serves (testbed/previous_commit_spike.md)."""
    pytest.importorskip("uvicorn")
    worktree = tmp_path / "previous-commit" / ("c" * 40)
    pkg = worktree / "hub" / "hub"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "main.py").write_text(
        "import json, os\n"
        "async def app(scope, receive, send):\n"
        "    if scope['type'] != 'http':\n"
        "        return\n"
        "    body = json.dumps({'status': 'ok', 'commit': 'c' * 40, 'from': __file__,\n"
        "                       'db': os.environ.get('DATABASE_URL')}).encode()\n"
        "    await send({'type': 'http.response.start', 'status': 200,\n"
        "                'headers': [(b'content-type', b'application/json')]})\n"
        "    await send({'type': 'http.response.body', 'body': body})\n",
        encoding="utf-8",
    )
    hub_dir = tmp_path / "hubdir"
    hub_dir.mkdir()
    monkeypatch.setattr(cli, "HUB_DIR", hub_dir)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    port = _free_port()
    pid = None
    try:
        assert cli._hub_start_previous(port, "prev", worktree) is None
        pid = int(cli._hub_pid_file(port, "prev").read_text(encoding="utf-8").split()[0])
        body = updater.hub_health(port) or {}
        assert body.get("commit") == "c" * 40
        assert Path(body["from"]).resolve() == (pkg / "main.py").resolve()
        expected = (cli._hub_profile_data_dir("prev") / "agentweave.db").as_posix()
        assert body["db"] == f"sqlite+aiosqlite:///{expected}"
    finally:
        if pid:
            cli._hub_kill_pid(pid)


# --- cli: the window's bridge -----------------------------------------------------------------------


class _Window:
    def __init__(self) -> None:
        self.js: List[str] = []

    def evaluate_js(self, code: str) -> None:
        self.js.append(code)


@pytest.fixture
def bridge_env(monkeypatch, behind, tmp_path: Path):
    repo, hub = behind
    hub_dir = tmp_path / "hubdir"
    monkeypatch.setattr(cli, "HUB_DIR", hub_dir)
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: repo)
    monkeypatch.setattr(
        updater,
        "hub_health",
        lambda port, timeout=2.0: (
            {"status": "ok", "commit": hub.commit, "branch": "master"} if hub.commit else None
        ),
    )
    monkeypatch.setattr(cli, "_hub_work_running", lambda port: {"running": False})
    applied: List[Any] = []

    def checkout_applier(port: int, profile: str, root: Path) -> updater.CheckoutApplier:
        a = _applier(root, tmp_path, hub)
        applied.append(a)
        return a

    monkeypatch.setattr(cli, "_checkout_applier", checkout_applier)

    def no_pip(*a: Any, **kw: Any) -> None:
        raise AssertionError("a checkout never reaches pip")

    monkeypatch.setattr(updater, "known_latest", no_pip)
    monkeypatch.setattr(updater, "apply_update", no_pip)
    bridge = cli._AppWindowApi(cli._AppWindowCloser(8175))
    bridge._window = _Window()
    return bridge, repo, hub, applied


def test_status_of_a_checkout_names_commit_branch_tip_behind_and_dirty(bridge_env):
    bridge, repo, hub, _ = bridge_env
    (repo / "mine.txt").write_text("x", encoding="utf-8")
    status = bridge.update_status()
    assert status["kind"] == "checkout"
    assert status["commit"] == hub.commit and status["branch"] == "master"
    assert status["master_tip"] == hub.new and status["behind"] == 1
    assert status["dirty"] == ["mine.txt"]
    assert status["available"] is True and status["applicable"] is True
    assert status["auto_checkout"] is False
    assert "1 commit ahead" in status["summary"]


def test_status_of_an_unreadable_checkout_offers_nothing_and_raises_nothing(
    bridge_env, monkeypatch, tmp_path: Path
):
    bridge, _, _, _ = bridge_env
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: tmp_path / "gone")
    status = bridge.update_status()
    assert status["kind"] == "checkout"
    assert status["available"] is False and not status["behind"] and status["summary"] is None


def test_the_switch_is_saved_per_kind(bridge_env, tmp_path: Path):
    bridge, _, _, _ = bridge_env
    assert bridge.set_auto_update(True, "checkout") is True
    assert bridge.update_status()["auto_checkout"] is True
    saved = json.loads((tmp_path / "hubdir" / "app-window" / "update.json").read_text("utf-8"))
    assert saved == {"auto_checkout": True}


def test_apply_from_the_window_restarts_onto_master_and_reloads(bridge_env):
    bridge, _, hub, applied = bridge_env
    bridge.update_status()
    answer = bridge.apply_update(False)
    assert answer["state"] == "applied", answer
    assert hub.commit == hub.new and len(applied) == 1
    assert bridge._window.js == ["window.location.reload()"]
    assert bridge.update_status()["behind"] == 0  # read again for the new commit


def test_apply_with_a_dirty_tree_asks_without_reloading(bridge_env):
    bridge, repo, hub, _ = bridge_env
    (repo / "mine.txt").write_text("x", encoding="utf-8")
    answer = bridge.apply_update(False)
    assert answer["state"] == "needs_confirm" and "mine.txt" in answer["detail"]
    assert bridge._window.js == [] and hub.calls == []


def test_an_editable_install_outside_a_checkout_is_never_pip_installed(monkeypatch, tmp_path):
    """F1182: the bridge refused nothing, and ran pip over an editable install."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: None)
    monkeypatch.setattr(updater, "installation_kind", lambda: "editable")

    def no_pip(*a: Any, **kw: Any) -> None:
        raise AssertionError("pip must not run")

    monkeypatch.setattr(updater, "apply_update", no_pip)
    bridge = cli._AppWindowApi(cli._AppWindowCloser(8176))
    bridge._window = _Window()
    answer = bridge.apply_update(True)
    assert answer["state"] == "blocked" and bridge._window.js == []


def test_a_pip_release_equal_to_the_installed_one_is_not_applied(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: None)
    monkeypatch.setattr(updater, "installation_kind", lambda: "pip")
    monkeypatch.setattr(updater, "installed_version", lambda name: "2.2.0")
    monkeypatch.setattr(updater, "known_latest", lambda path: ("2.2.0", False))

    def no_pip(*a: Any, **kw: Any) -> None:
        raise AssertionError("pip must not run")

    monkeypatch.setattr(updater, "apply_update", no_pip)
    bridge = cli._AppWindowApi(cli._AppWindowCloser(8177))
    bridge._window = _Window()
    assert bridge.apply_update(True)["state"] == "failed"


# --- cli: the launch -------------------------------------------------------------------------------


@pytest.fixture
def launch_env(monkeypatch, behind, tmp_path: Path):
    repo, hub = behind
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path / "hubdir")
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: repo)
    monkeypatch.setattr(cli, "_hub_launch_state", lambda port: ("idle", None))
    monkeypatch.setattr(cli, "_hub_commit", lambda port: hub.commit)
    monkeypatch.setattr(cli, "_app_window_open_on", lambda port: False)
    ran: List[str] = []

    def launch_apply(port, profile, cwd, lock, run, intro):
        ran.append(intro)
        return run().state

    monkeypatch.setattr(cli, "_launch_apply", launch_apply)
    monkeypatch.setattr(
        cli, "_checkout_applier", lambda port, profile, root: _applier(root, tmp_path, hub)
    )
    return repo, hub, ran


def test_a_launch_with_the_switch_at_its_default_leaves_the_hub_alone(launch_env):
    _, hub, ran = launch_env
    assert cli._launch_update(8178, "p", None) is None
    assert ran == [] and hub.calls == []


def test_a_launch_with_the_switch_on_restarts_an_idle_hub_onto_master(launch_env):
    _, hub, ran = launch_env
    updater.set_auto_update(cli._update_setting_file(), True, "checkout")
    assert cli._launch_update(8178, "p", None) == "applied"
    assert len(ran) == 1 and hub.commit == hub.new


def test_a_launch_never_restarts_a_busy_or_dirty_checkout(launch_env, monkeypatch):
    repo, hub, ran = launch_env
    updater.set_auto_update(cli._update_setting_file(), True, "checkout")
    monkeypatch.setattr(cli, "_hub_launch_state", lambda port: ("busy", None))
    assert cli._launch_update(8178, "p", None) is None
    monkeypatch.setattr(cli, "_hub_launch_state", lambda port: ("silent", None))
    assert cli._launch_update(8178, "p", None) is None
    monkeypatch.setattr(cli, "_hub_launch_state", lambda port: ("idle", None))
    (repo / "mine.txt").write_text("x", encoding="utf-8")
    assert cli._launch_update(8178, "p", None) is None
    assert ran == [] and hub.calls == []


def test_a_launch_never_asks_pip_for_a_checkout(launch_env, monkeypatch):
    def no_pip(*a: Any, **kw: Any) -> None:
        raise AssertionError("a checkout launch never checks PyPI")

    monkeypatch.setattr(updater, "check_and_record", no_pip)
    assert cli._launch_update(8178, "p", None) is None


@pytest.fixture(autouse=True)
def _no_real_hub_dir(monkeypatch, tmp_path: Path):
    """Nothing here writes to the real Hub folder, whatever a test forgets to point elsewhere."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path / "default-hubdir")
