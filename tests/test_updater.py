"""The launcher's updater (spec `agentweave-updates-itself`, task AWUI-3).

Each seam of `agentweave.updater` is driven here over real HTTP (a local index, a fake Hub), a real
SQLite file and a real lock file; pip, stopping and starting a Hub are injected. The end-to-end run
on a scratch install is the acceptance drive, scripts/drive/d1107_updates_itself.py.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from agentweave import cli, updater

_real_port_accepts = cli._hub_port_accepts

# --- a local index and a fake Hub ---------------------------------------------------------------


class _Server:
    """A loopback HTTP server answering from `routes` (path -> (status, content type, body));
    a route whose value is an exception class raises inside the handler (a 500 / dropped reply)."""

    def __init__(self, routes: Dict[str, Any]) -> None:
        self.routes = routes
        self.hits: List[str] = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                server.hits.append(self.path)
                route = server.routes.get(self.path.split("?")[0])
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if isinstance(route, type) and issubclass(route, BaseException):
                    raise route("the route raised")
                status, kind, body = route
                data = body if isinstance(body, bytes) else body.encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_a: Any) -> None:
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve():
    servers: List[_Server] = []

    def _make(routes: Dict[str, Any]) -> _Server:
        servers.append(_Server(routes))
        return servers[-1]

    yield _make
    for s in servers:
        s.close()


def _html(project: str, files: List[tuple]) -> tuple:
    links = "".join(
        f'<a href="/files/{n}#sha256=00"' + (' data-yanked=""' if y else "") + f">{n}</a>\n"
        for n, y in files
    )
    return 200, "text/html", f"<html><body>{links}</body></html>"


def _json(files: List[tuple]) -> tuple:
    body = {
        "meta": {"api-version": "1.0"},
        "files": [{"filename": n, "yanked": y} for n, y in files],
    }
    return 200, "application/vnd.pypi.simple.v1+json", json.dumps(body)


def _releases(stem: str) -> List[tuple]:
    return [
        (f"{stem}-2.1.0-py3-none-any.whl", False),
        (f"{stem}-2.1.1-py3-none-any.whl", False),
        (f"{stem}-2.1.1.tar.gz", False),
        (f"{stem}-2.1.2-py3-none-any.whl", True),  # yanked
        (f"{stem}-2.2.0rc1-py3-none-any.whl", False),  # a pre-release
    ]


def _index(serve, as_json: bool = False) -> _Server:
    make = (lambda p, f: _json(f)) if as_json else _html
    return serve(
        {
            "/simple/agentweave-ai/": make("agentweave-ai", _releases("agentweave_ai")),
            "/simple/agentweave-hub/": make("agentweave-hub", _releases("agentweave_hub")),
        }
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- versions ---------------------------------------------------------------------------------


def test_only_final_releases_parse_and_compare_as_pep_440():
    assert updater.parse_final("2.2.0rc1") is None
    assert updater.parse_final("2.2.0.dev3") is None
    assert updater.parse_final("0.0.0+dev") is None
    assert updater.parse_final("2.1") == updater.parse_final("2.1.0")
    assert updater.is_newer("2.1.1", "2.1.0")
    assert updater.is_newer("2.10.0", "2.9.9")
    assert updater.is_newer("2.1.0.post1", "2.1.0")
    assert not updater.is_newer("2.1.1", "2.1.1")
    assert not updater.is_newer("2.1.0", "2.1.1")
    assert not updater.is_newer(None, "2.1.0")
    # A dev build is not a release this updater replaces.
    assert not updater.is_newer("2.1.1", "0.0.0+dev")


# --- the check (FR-2) -------------------------------------------------------------------------


@pytest.mark.parametrize("as_json", [False, True])
def test_check_names_the_newest_final_release_not_the_pre_release_or_the_yanked(serve, as_json):
    index = _index(serve, as_json)
    assert updater.check_latest(f"http://127.0.0.1:{index.port}/simple/") == "2.1.1"


def test_check_asks_with_the_index_url_from_the_environment(serve, monkeypatch):
    index = _index(serve)
    monkeypatch.setenv(updater.INDEX_ENV, f"http://127.0.0.1:{index.port}/simple")
    assert updater.index_url() == f"http://127.0.0.1:{index.port}/simple/"
    assert updater.check_latest() == "2.1.1"
    assert "/simple/agentweave-ai/" in index.hits and "/simple/agentweave-hub/" in index.hits


def test_check_uses_pypi_when_no_index_is_named(monkeypatch):
    monkeypatch.delenv(updater.INDEX_ENV, raising=False)
    assert updater.index_url() == "https://pypi.org/simple/"


def test_check_offers_only_a_version_both_packages_have(serve):
    index = serve(
        {
            "/simple/agentweave-ai/": _html("", [("agentweave_ai-2.1.1-py3-none-any.whl", False)]),
            "/simple/agentweave-hub/": _html(
                "", [("agentweave_hub-2.1.0-py3-none-any.whl", False)]
            ),
        }
    )
    assert updater.check_latest(f"http://127.0.0.1:{index.port}/simple/") is None


def test_check_offline_ends_at_once_and_quietly():
    started = time.monotonic()
    assert updater.check_latest(f"http://127.0.0.1:{_free_port()}/simple/") is None
    assert time.monotonic() - started < 3.5


def test_check_against_a_silent_index_ends_within_its_three_seconds():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    held: List[socket.socket] = []
    threading.Thread(target=lambda: held.append(sock.accept()[0]), daemon=True).start()
    try:
        started = time.monotonic()
        assert updater.check_latest(f"http://127.0.0.1:{sock.getsockname()[1]}/simple/") is None
        assert time.monotonic() - started < updater.CHECK_SECONDS + 1.0
    finally:
        for conn in held:
            conn.close()
        sock.close()


def test_check_against_an_index_whose_route_raises_is_quiet(serve):
    index = serve({"/simple/agentweave-ai/": RuntimeError, "/simple/agentweave-hub/": RuntimeError})
    assert updater.check_latest(f"http://127.0.0.1:{index.port}/simple/") is None


def test_check_against_an_answer_that_is_not_an_index_is_quiet(serve):
    index = serve(
        {
            "/simple/agentweave-ai/": (200, "application/vnd.pypi.simple.v1+json", "{not json"),
            "/simple/agentweave-hub/": (500, "text/plain", "boom"),
        }
    )
    assert updater.check_latest(f"http://127.0.0.1:{index.port}/simple/") is None


def test_the_check_is_recorded_and_a_failed_one_leaves_what_was_known(serve, tmp_path):
    index = _index(serve)
    check = tmp_path / "app-window" / "update-check.json"
    url = f"http://127.0.0.1:{index.port}/simple/"
    assert updater.check_and_record(check, url=url) == "2.1.1"
    data = json.loads(check.read_text(encoding="utf-8"))
    assert data["latest"] == "2.1.1" and data["checked_at"].endswith("Z")
    assert updater.check_and_record(check, url=f"http://127.0.0.1:{_free_port()}/simple/") is None
    assert json.loads(check.read_text(encoding="utf-8")) == data


def test_while_running_the_index_is_asked_again_only_after_24_hours(tmp_path):
    check = tmp_path / "update-check.json"
    calls: List[str] = []

    def fetch(url: str, timeout: float):
        calls.append(url)
        stem = url.rstrip("/").rsplit("/", 1)[1].replace("-", "_")
        return _html("", [(f"{stem}-2.1.1-py3-none-any.whl", False)])[2].encode(), "text/html"

    updater.record_check(check, "2.1.0")
    assert updater.known_latest(check, url="http://x/simple/", fetch=fetch) == ("2.1.0", False)
    assert calls == []
    later = time.time() + updater.RECHECK_SECONDS + 60
    assert updater.known_latest(check, now=later, url="http://x/simple/", fetch=fetch) == (
        "2.1.1",
        True,
    )
    assert len(calls) == 2


# --- reading the Hub without a window (FR-1, FR-3) --------------------------------------------


def test_the_launcher_reads_the_version_from_health_without_a_window(serve):
    hub = serve(
        {
            "/health": (
                200,
                "application/json",
                json.dumps({"status": "ok", "version": "2.1.0", "install": "pip"}),
            )
        }
    )
    assert updater.hub_version(hub.port) == "2.1.0"


def test_an_older_hub_without_version_is_version_unknown_and_tolerated(serve):
    hub = serve(
        {"/health": (200, "application/json", json.dumps({"status": "ok", "runtime": "native"}))}
    )
    assert updater.hub_health(hub.port) == {"status": "ok", "runtime": "native"}
    assert updater.hub_version(hub.port) is None


def test_a_health_route_that_raises_or_no_hub_reads_as_no_version(serve):
    hub = serve({"/health": RuntimeError})
    assert updater.hub_version(hub.port) is None
    assert updater.hub_version(_free_port()) is None


# --- the setting (FR-11) ----------------------------------------------------------------------


def test_automatic_updating_is_on_by_default_and_remembered_off(tmp_path):
    setting = tmp_path / "app-window" / "update.json"
    assert updater.auto_update_on(setting) is True
    updater.set_auto_update(setting, False)
    assert json.loads(setting.read_text(encoding="utf-8")) == {"auto": False}
    assert updater.auto_update_on(setting) is False  # a later launch reads it again
    updater.set_auto_update(setting, True)
    assert updater.auto_update_on(setting) is True
    setting.write_text("not json", encoding="utf-8")
    assert updater.auto_update_on(setting) is True


# --- the launch decision ----------------------------------------------------------------------


def _facts(**kw: Any) -> updater.LaunchFacts:
    base = {"current": "2.1.0", "latest": "2.1.1", "kind": "pip", "auto": True, "hub": "absent"}
    base.update(kw)
    return updater.LaunchFacts(**base)


def test_a_launch_with_nothing_running_updates_first():
    decision = updater.decide_at_launch(_facts())
    assert (decision.action, decision.target) == ("update", "2.1.1")


def test_a_launch_on_an_idle_background_hub_updates_first():
    assert updater.decide_at_launch(_facts(hub="idle", hub_version="2.1.0")).action == "update"


@pytest.mark.parametrize(
    "facts, reason",
    [
        ({"kind": "editable"}, "not a pip-installed release"),
        ({"kind": "checkout"}, "not a pip-installed release"),
        ({"latest": None}, "no newer release"),
        ({"latest": "2.1.0"}, "no newer release"),
        ({"auto": False}, "automatic updating is off"),
        ({"hub": "busy", "hub_version": "2.1.0"}, "work is running"),
        ({"hub": "silent", "hub_version": "2.1.0"}, "did not answer the work check"),
        ({"hub": "idle", "hub_version": None}, "does not report its version"),
        ({"hub": "idle", "hub_version": "2.1.0", "window_open": True}, "window is already open"),
        ({"other_hubs": [8191]}, "port 8191"),
    ],
)
def test_every_reason_not_to_update_opens_as_things_are(facts, reason):
    decision = updater.decide_at_launch(_facts(**facts))
    assert decision.action == "open"
    assert reason in decision.reason


def test_the_work_answer_reads_idle_busy_or_silent():
    assert updater.work_state({"running": False, "turns": 0}) == "idle"
    assert updater.work_state({"running": True, "turns": 1}) == "busy"
    assert updater.work_state(None) == "silent"  # the route raised, or nothing answered
    assert updater.work_state({"detail": "error"}) == "silent"


# --- the lock (FR-10) -------------------------------------------------------------------------


def test_one_update_at_a_time_and_a_dead_holder_is_taken_over(tmp_path):
    path = tmp_path / "app-window" / "update.lock"
    first, second = updater.UpdateLock(path), updater.UpdateLock(path)
    assert first.acquire(8190)
    assert not second.acquire(8190)
    assert second.holder()["port"] == 8190
    first.release()
    assert second.holder() is None and not path.exists()
    path.write_text(json.dumps({"pid": 2**22 + 12345, "port": 8190}), encoding="utf-8")
    assert second.holder() is None  # its process has gone
    assert second.acquire(8191)
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    second.release()


def test_two_launches_at_once_take_the_lock_once(tmp_path):
    path = tmp_path / "update.lock"
    barrier = threading.Barrier(8)
    won: List[bool] = []

    def race() -> None:
        lock = updater.UpdateLock(path)
        barrier.wait()
        won.append(lock.acquire(8190))

    threads = [threading.Thread(target=race) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert won.count(True) == 1


# --- the apply sequence (FR-6, FR-7, FR-8, FR-10) ---------------------------------------------


def _db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path)) as c, c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
        c.execute("INSERT INTO projects VALUES ('p1', 'one'), ('p2', 'two')")
    return path


def _dump(path: Path) -> List[str]:
    with contextlib.closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as c:
        return list(c.iterdump())


class _Fake:
    """A Hub, pip and the other-Hub scan, recording the order things happen in."""

    def __init__(self, tmp_path: Path, **kw: Any) -> None:
        self.calls: List[str] = []
        self.running: Optional[str] = "2.1.0"
        self.installed = "2.1.0"
        self.db = _db(tmp_path / "data" / "agentweave.db")
        self.others: List[int] = kw.get("others", [])
        self.pip_fails = kw.get("pip_fails", False)
        self.migration_fails = kw.get("migration_fails", False)
        self.never_healthy = kw.get("never_healthy", False)
        self.lock = updater.UpdateLock(tmp_path / "app-window" / "update.lock")
        self.applier = updater.Applier(
            port=8190,
            current="2.1.0",
            target="2.1.1",
            db_path=self.db,
            backups_root=tmp_path / "update-backups",
            lock=self.lock,
            other_hubs=self.other_hubs,
            stop=self.stop,
            start=self.start,
            version=lambda: self.running,
            pip=self.pip,
            healthy_seconds=0.2,
            sleep=lambda s: time.sleep(0.01),
        )

    def other_hubs(self) -> List[int]:
        self.calls.append("others")
        return self.others

    def stop(self) -> Optional[str]:
        self.calls.append("stop")
        self.running = None
        return None

    def pip(self, version: str, reinstall: bool = False):
        self.calls.append(f"pip {version}{' reinstall' if reinstall else ''}")
        if self.pip_fails and not reinstall:
            return False, "ERROR: No matching distribution found for agentweave-hub==2.1.1"
        self.installed = version
        return True, ""

    def start(self) -> Optional[str]:
        self.calls.append(f"start {self.installed}")
        if self.installed == "2.1.1" and self.migration_fails:
            with contextlib.closing(sqlite3.connect(self.db)) as c, c:  # fails halfway
                c.execute("CREATE TABLE d1107_half_migrated (x INTEGER)")
                c.execute("INSERT INTO d1107_half_migrated VALUES (1)")
                c.execute("DELETE FROM projects WHERE id = 'p2'")
            return "exit code 1: Migration failed: boom"
        self.running = (
            None if (self.never_healthy and self.installed == "2.1.1") else self.installed
        )
        return None


def test_an_update_stops_copies_upgrades_starts_and_verifies_in_that_order(tmp_path):
    fake = _Fake(tmp_path)
    before = _dump(fake.db)
    result = updater.apply_update(fake.applier)
    assert result.state == "applied", result.detail
    assert fake.calls == ["others", "stop", "pip 2.1.1", "start 2.1.1"]
    assert result.backup is not None and result.backup.parent.parent == tmp_path / "update-backups"
    assert _dump(result.backup) == before  # a consistent copy, WAL and all
    assert not fake.lock.path.exists()  # released


def test_a_migration_that_fails_puts_the_old_version_and_the_database_back(tmp_path):
    fake = _Fake(tmp_path, migration_fails=True)
    before = _dump(fake.db)
    result = updater.apply_update(fake.applier)
    assert result.state == "failed"
    assert "Migration failed: boom" in result.detail and "2.1.0 was put back" in result.detail
    assert fake.calls == [
        "others",
        "stop",
        "pip 2.1.1",
        "start 2.1.1",
        "stop",
        "pip 2.1.0 reinstall",
        "start 2.1.0",
    ]
    assert _dump(fake.db) == before  # no half-migrated table, the deleted row back
    assert fake.running == "2.1.0"


def test_a_failed_upgrade_restores_without_asking(tmp_path):
    fake = _Fake(tmp_path, pip_fails=True)
    result = updater.apply_update(fake.applier)
    assert result.state == "failed"
    assert "No matching distribution" in result.detail
    assert fake.calls[-2:] == ["pip 2.1.0 reinstall", "start 2.1.0"]
    assert fake.running == "2.1.0"


def test_a_version_that_does_not_come_up_healthy_is_rolled_back(tmp_path):
    fake = _Fake(tmp_path, never_healthy=True)
    result = updater.apply_update(fake.applier)
    assert result.state == "failed"
    assert "did not report healthy" in result.detail
    assert fake.running == "2.1.0" and fake.calls[-1] == "start 2.1.0"


def test_another_hub_of_the_install_blocks_and_is_named_with_nothing_touched(tmp_path):
    fake = _Fake(tmp_path, others=[8191])
    before = _dump(fake.db)
    result = updater.apply_update(fake.applier)
    assert result.state == "blocked" and "port 8191" in result.detail
    assert fake.calls == ["others"]  # not stopped, not upgraded
    assert fake.running == "2.1.0" and _dump(fake.db) == before
    assert not (tmp_path / "update-backups").exists()


def test_a_second_update_while_one_runs_changes_nothing(tmp_path):
    fake = _Fake(tmp_path)
    holder = updater.UpdateLock(fake.lock.path)
    assert holder.acquire(8190)
    result = updater.apply_update(fake.applier)
    assert result.state == "blocked" and "already under way" in result.detail
    assert "stop" not in fake.calls and fake.running == "2.1.0"
    holder.release()


def test_unconfirmed_work_asks_first_and_an_unanswered_work_check_is_not_idle(tmp_path):
    fake = _Fake(tmp_path)
    busy = {"running": True, "turns": 1, "check_runs": 0, "landings": 0, "builds": 0}
    result = updater.apply_update(
        fake.applier, confirmed=False, work=lambda: busy, describe=lambda w: "1 agent turn"
    )
    assert (result.state, result.detail) == ("needs_confirm", "1 agent turn")
    result = updater.apply_update(fake.applier, confirmed=False, work=lambda: None)
    assert result.state == "needs_confirm"  # the work route raised: not idle (D3)
    assert fake.calls == []
    result = updater.apply_update(fake.applier, confirmed=False, work=lambda: {"running": False})
    assert result.state == "applied"


def test_only_the_newest_three_database_copies_are_kept(tmp_path):
    db = _db(tmp_path / "agentweave.db")
    root = tmp_path / "update-backups"
    for _ in range(5):
        updater.backup_database(db, root)
        time.sleep(0.002)
    assert len([p for p in root.iterdir() if p.is_dir()]) == 3


def test_no_database_yet_is_no_copy_and_a_restore_leaves_none(tmp_path):
    db = tmp_path / "agentweave.db"
    assert updater.backup_database(db, tmp_path / "b") is None
    _db(db)
    updater.restore_database(None, db)
    assert not db.exists()


def test_pip_runs_from_this_interpreter_pinned_to_the_version_on_the_named_index(monkeypatch):
    monkeypatch.setenv(updater.INDEX_ENV, "http://127.0.0.1:9/good/simple/")
    cmd = updater.pip_command("2.1.1")
    assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
    assert cmd[-2:] == ["agentweave-ai==2.1.1", "agentweave-hub==2.1.1"]
    assert cmd[cmd.index("--index-url") + 1] == "http://127.0.0.1:9/good/simple/"
    back = updater.pip_command("2.1.0", reinstall=True)
    assert "--force-reinstall" in back and "--no-deps" in back
    monkeypatch.delenv(updater.INDEX_ENV)
    assert "--index-url" not in updater.pip_command("2.1.1")


def test_install_kind_reads_direct_url(monkeypatch):
    class Dist:
        def __init__(self, raw: Optional[str]) -> None:
            self.raw = raw

        def read_text(self, name: str) -> Optional[str]:
            return self.raw

    import importlib.metadata as md

    for raw, kind in [
        (None, "pip"),
        (json.dumps({"url": "file:///c/x.whl", "archive_info": {}}), "pip"),
        (json.dumps({"url": "file:///c/repo", "dir_info": {"editable": True}}), "editable"),
        (json.dumps({"url": "file:///c/repo", "dir_info": {}}), "checkout"),
    ]:
        monkeypatch.setattr(md, "distribution", lambda _p, raw=raw: Dist(raw))
        assert updater.install_kind() == kind
        assert updater.installation_kind() == kind


# --- the launch path in cli.py ----------------------------------------------------------------


@pytest.fixture
def hub_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path / "hub")
    # These are the pip install's launches: no git checkout behind the Hub package (this suite
    # runs from one). A checkout's launch is tests/test_updater_checkout.py's.
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: None)
    (tmp_path / "hub").mkdir()
    return tmp_path / "hub"


def test_hub_only_starts_the_hub_with_no_window_and_no_project(monkeypatch):
    seen: Dict[str, Any] = {}

    def fake_start(**kw: Any) -> int:
        seen.update(kw)
        return 0

    monkeypatch.setattr(cli, "_hub_native_start", fake_start)
    assert cli.main(["--hub-only", "--port", "8190", "--profile", "d1107"]) == 0
    assert seen["app"] is False and seen["cwd"] is None
    assert (seen["port"], seen["profile"]) == (8190, "d1107")


def test_a_checkout_or_editable_launch_never_checks_or_updates(hub_dir, monkeypatch):
    monkeypatch.setattr(updater, "installation_kind", lambda: "editable")
    monkeypatch.setattr(
        updater, "check_latest", lambda **_k: pytest.fail("an editable install was checked")
    )
    assert cli._launch_update(8190, "d1107", None) is None


def test_a_launch_while_another_launch_updates_this_hub_leaves_the_window_to_it(
    hub_dir, monkeypatch
):
    monkeypatch.setattr(updater, "installation_kind", lambda: "pip")
    monkeypatch.setattr(
        updater, "check_latest", lambda **_k: pytest.fail("the second launch checked")
    )
    holder = cli._update_lock()
    assert holder.acquire(8190)
    try:
        assert cli._launch_update(8190, "d1107", None) == 0
    finally:
        holder.release()


def _launch_env(monkeypatch, latest: Optional[str], hub=("absent", None)) -> List[str]:
    opened: List[str] = []
    monkeypatch.setattr(updater, "installation_kind", lambda: "pip")
    monkeypatch.setattr(updater, "check_latest", lambda **_k: latest)
    monkeypatch.setattr(updater, "installed_version", lambda _p: "2.1.0")
    monkeypatch.setattr(cli, "_hub_launch_state", lambda _port: hub)
    monkeypatch.setattr(cli, "_hub_other_install_hubs", lambda _port: [])
    monkeypatch.setattr(cli, "_app_window_open_on", lambda _port: False)
    monkeypatch.setattr(
        cli, "_open_app_with_splash", lambda start, **_k: opened.append("splash") or 0
    )
    monkeypatch.setattr(
        updater, "apply_update", lambda a, **_k: pytest.fail("an update was applied")
    )
    return opened


@pytest.mark.parametrize(
    "latest, hub, auto",
    [
        (None, ("absent", None), True),  # offline: the launch goes on
        ("2.1.0", ("absent", None), True),  # already the newest: nothing changes
        ("2.1.1", ("absent", None), False),  # automatic updating off
        ("2.1.1", ("busy", "2.1.0"), True),  # work running
        ("2.1.1", ("silent", "2.1.0"), True),  # the work check did not answer
    ],
)
def test_a_launch_that_should_not_update_opens_as_things_are(
    hub_dir, monkeypatch, latest, hub, auto
):
    opened = _launch_env(monkeypatch, latest, hub)
    if not auto:
        updater.set_auto_update(cli._update_setting_file(), False)
    assert cli._launch_update(8190, "d1107", None) is None
    assert opened == []
    if latest:
        recorded = json.loads(cli._update_check_file().read_text(encoding="utf-8"))
        assert recorded["latest"] == latest


def test_a_launch_that_updates_does_it_behind_the_splash_holding_the_lock(hub_dir, monkeypatch):
    _launch_env(monkeypatch, "2.1.1")
    applied: List[Any] = []
    seen: Dict[str, Any] = {}

    def fake_apply(applier: updater.Applier, **_k: Any) -> updater.ApplyResult:
        applied.append(applier)
        assert applier.lock.held  # held for the whole update, against a second launch
        return updater.ApplyResult("applied", "Updated to 2.1.1.")

    def fake_splash(start, **kw: Any) -> int:
        seen.update(kw)
        assert cli._update_lock().holder() is not None
        url, failure = start()
        seen["url"], seen["failure"] = url, failure
        kw["after_shown"]()
        return 0

    monkeypatch.setattr(updater, "apply_update", fake_apply)
    monkeypatch.setattr(cli, "_open_app_with_splash", fake_splash)
    monkeypatch.setattr(updater, "hub_health", lambda _port, timeout=2.0: {"version": "2.1.1"})
    monkeypatch.setattr(
        cli, "_hub_resolve_launch_url", lambda port, cwd: f"http://127.0.0.1:{port}"
    )
    assert cli._launch_update(8190, "d1107", None) == 0
    assert [a.target for a in applied] == ["2.1.1"]
    assert seen["url"] == "http://127.0.0.1:8190" and seen["warm"] is False
    assert cli._update_lock().holder() is None  # released once the window was shown
    result = json.loads(cli._update_result_file(8190, "d1107").read_text(encoding="utf-8"))
    assert result["state"] == "applied"


def test_a_failed_update_at_launch_is_recorded_for_the_window_to_say(hub_dir, monkeypatch):
    _launch_env(monkeypatch, "2.1.1")
    monkeypatch.setattr(
        updater,
        "apply_update",
        lambda a, **_k: updater.ApplyResult("failed", "The update to 2.1.1 failed: boom."),
    )
    monkeypatch.setattr(cli, "_open_app_with_splash", lambda start, **kw: 0 if start()[0] else 1)
    monkeypatch.setattr(updater, "hub_health", lambda _port, timeout=2.0: {"version": "2.1.0"})
    monkeypatch.setattr(cli, "_hub_resolve_launch_url", lambda port, cwd: "http://x")
    assert cli._launch_update(8190, "d1107", None) == 0  # the restored version opens
    result = json.loads(cli._update_result_file(8190, "d1107").read_text(encoding="utf-8"))
    assert result == {
        "state": "failed",
        "detail": "The update to 2.1.1 failed: boom.",
        "at": result["at"],
    }


def test_the_hub_database_is_the_one_the_start_uses(hub_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli._hub_db_file("d1107") == hub_dir / "profiles" / "d1107" / "agentweave.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///C:/scratch/x.db")
    assert cli._hub_db_file("d1107") == Path("C:/scratch/x.db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://h/db")
    assert cli._hub_db_file("d1107") is None


def test_other_hubs_of_the_install_are_found_by_their_pid_files_and_health(
    hub_dir, monkeypatch, serve
):
    other = serve({"/health": (200, "application/json", '{"status": "ok", "version": "2.1.0"}')})
    (hub_dir / f"hub-otherhub2-{other.port}.pid").write_text(f"{os.getpid()}\n{other.port}")
    (hub_dir / "hub-otherhub1-8190.pid").write_text(f"{os.getpid()}\n8190")  # this window's own
    (hub_dir / f"hub-gone-{_free_port()}.pid").write_text("1\n1")  # a Hub that is not there
    monkeypatch.setattr(cli, "_process_image", lambda pid: sys.executable)
    assert cli._hub_other_install_hubs(8190) == [other.port]
    monkeypatch.setattr(cli, "_process_image", lambda pid: str(Path("/elsewhere/python.exe")))
    assert cli._hub_other_install_hubs(8190) == []  # another installation's Hub is not ours


def test_the_start_after_an_upgrade_runs_a_fresh_interpreter_and_says_why_it_failed(
    hub_dir, monkeypatch
):
    seen: Dict[str, Any] = {}

    def fake_run(command, **kw: Any):
        seen["command"] = command
        return subprocess.CompletedProcess(
            command, 1, stdout="Running database migrations...\n[ERROR] Migration failed: boom\n"
        )

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    why = cli._hub_start_for_update(8190, "d1107")
    assert why == "exit code 1: [ERROR] Migration failed: boom"
    assert seen["command"][:4] == [sys.executable, "-m", "agentweave", "--hub-only"]
    assert seen["command"][4:] == ["--port", "8190", "--profile", "d1107"]


def test_stopping_for_an_update_refuses_a_hub_this_launcher_did_not_start(
    hub_dir, serve, monkeypatch
):
    monkeypatch.setattr(cli, "_hub_port_accepts", _real_port_accepts)  # conftest stubs it
    hub = serve({"/health": (200, "application/json", '{"status": "ok"}')})
    why = cli._hub_stop_for_update(hub.port, "d1107")
    assert why and "not started by this launcher" in why
    assert cli._hub_stop_for_update(_free_port(), "d1107") is None  # nothing to stop


def test_parser_keeps_hub_only_out_of_the_help():
    parser = cli.create_parser()
    assert "--hub-only" not in parser.format_help()
    assert parser.parse_args(["--hub-only"]).hub_only is True
    assert isinstance(parser.parse_args([]), argparse.Namespace)
