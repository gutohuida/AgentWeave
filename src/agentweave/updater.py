"""The launcher's updater: is a newer AgentWeave published, and applying it safely.

Spec `agentweave-updates-itself` (design D1, D4, CONTRACT). The launcher does the checking and
the applying, never the Hub, because a Hub cannot replace the package it runs from. Stdlib only,
like the rest of the CLI.

Seams, each injectable so a test drives it without pip, a Hub or a network:
  * `check_latest()`  -- the newest final, unyanked release on the index (PyPI unless
    `AW_UPDATE_INDEX_URL` names a PEP 503 simple index), quiet on any failure (FR-2);
  * `decide_at_launch()` -- a pure function from what a launch found to "update" or "open"
    (FR-3, FR-4, FR-8, FR-9, FR-10, FR-11);
  * `apply_update()`  -- stop, copy the database, pip, start, verify; on any failure after the
    copy, put the previous version and the database back and start that (FR-6, FR-7), all under
    `update.lock`, one update at a time (FR-10).

Files, under the Hub folder (HUB_DIR): `app-window/update-check.json`, `app-window/update.json`,
`app-window/update.lock`, and `update-backups/<UTC stamp>/agentweave.db`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

#: The packages an update moves together; `agentweave-ai` requires the same `agentweave-hub`.
PACKAGES = ("agentweave-ai", "agentweave-hub")
PYPI_SIMPLE = "https://pypi.org/simple/"
INDEX_ENV = "AW_UPDATE_INDEX_URL"
#: FR-2: a source that does not answer within this many seconds ends the check, silently.
CHECK_SECONDS = 3.0
#: FR-2: while the app runs, the check is repeated at most this often.
RECHECK_SECONDS = 24 * 60 * 60
#: FR-7: the new version must report healthy within this long, or the old one is put back.
HEALTHY_SECONDS = 120.0
#: How many database copies are kept (CONTRACT: newest three).
BACKUPS_KEPT = 3
PIP_SECONDS = 600

_FINAL = re.compile(r"^\d+(?:\.\d+)*(?:\.post\d+)?$")


# --- versions ---------------------------------------------------------------------------------


def parse_final(version: str) -> Optional[Tuple[Tuple[int, ...], int]]:
    """`2.1.1` -> ((2, 1, 1), 0); a pre-release, dev or local version -> None (never offered).

    A post-release sorts after its release (`2.1.1.post1` -> ((2, 1, 1), 1)). Trailing zeros are
    dropped so `2.1` and `2.1.0` compare equal, as PEP 440 says."""
    text = (version or "").strip().lower().lstrip("v")
    if not _FINAL.match(text):
        return None
    release, _, post = text.partition(".post")
    parts = [int(p) for p in release.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts), int(post) if post else 0


def is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    """Is `candidate` a final release newer than `current`? An unparseable current (a dev build,
    `0.0.0+dev`) is never upgraded over: it is not a release this updater knows how to replace."""
    a, b = parse_final(candidate or ""), parse_final(current or "")
    return a is not None and b is not None and a > b


def installed_version(package: str) -> Optional[str]:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package)
    except PackageNotFoundError:
        return None


def install_kind(package: str = "agentweave-hub") -> str:
    """`pip`, `editable` or `checkout`: the launcher's own read of what the Hub's /health says
    (hub/hub/version.py `install_kind`), so it needs no Hub to answer (FR-9)."""
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        dist = distribution(package)
    except PackageNotFoundError:
        return "checkout"
    raw = dist.read_text("direct_url.json")
    if not raw:
        return "pip"
    try:
        info = json.loads(raw)
    except ValueError:
        return "checkout"
    if (info.get("dir_info") or {}).get("editable"):
        return "editable"
    if "archive_info" in info:
        return "pip"
    return "checkout" if "url" in info else "pip"


def installation_kind() -> str:
    """The install as a whole: `pip` only when both packages are pip-installed releases."""
    kinds = [install_kind(p) for p in PACKAGES]
    for kind in ("checkout", "editable"):
        if kind in kinds:
            return kind
    return "pip"


# --- the check (FR-2) -------------------------------------------------------------------------


def index_url() -> str:
    base = os.environ.get(INDEX_ENV) or PYPI_SIMPLE
    return base if base.endswith("/") else base + "/"


def _release_versions(page: bytes, content_type: str, project: str) -> List[str]:
    """Final, unyanked versions listed on a PEP 691 (JSON) or PEP 503 (HTML) project page."""
    filenames: List[str] = []
    if "json" in content_type:
        data = json.loads(page.decode("utf-8"))
        for entry in data.get("files") or []:
            if entry.get("yanked"):
                continue
            filenames.append(str(entry.get("filename") or ""))
    else:
        html = page.decode("utf-8", errors="replace")
        for attrs, text in re.findall(r"<a\b([^>]*)>([^<]*)</a>", html, flags=re.I):
            if re.search(r"\bdata-yanked\b", attrs, flags=re.I):
                continue
            filenames.append(text.strip())
    stem = re.sub(r"[-_.]+", "_", project).lower()
    versions = []
    for name in filenames:
        lowered = name.lower()
        if lowered.endswith(".whl"):
            parts = name.split("-")
            if len(parts) >= 5 and re.sub(r"[-_.]+", "_", parts[0]).lower() == stem:
                versions.append(parts[1])
            continue
        for suffix in (".tar.gz", ".zip"):
            if lowered.endswith(suffix):
                base = name[: -len(suffix)]
                head, _, ver = base.rpartition("-")
                if re.sub(r"[-_.]+", "_", head).lower() == stem:
                    versions.append(ver)
    return [v for v in versions if parse_final(v) is not None]


def check_latest(
    url: Optional[str] = None,
    timeout: float = CHECK_SECONDS,
    fetch: Optional[Callable[[str, float], Tuple[bytes, str]]] = None,
) -> Optional[str]:
    """The newest final release published for both packages, or None when it could not be had.

    Never raises and never waits past `timeout` in all (FR-2): offline, a silent index, an answer
    that is not an index -- each is None, and the launch goes on with what is installed."""
    base = url or index_url()
    fetch = fetch or _fetch
    deadline = time.monotonic() + timeout
    common: Optional[set] = None
    try:
        for project in PACKAGES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            page, kind = fetch(f"{base}{project}/", remaining)
            found = set(_release_versions(page, kind, project))
            common = found if common is None else common & found
    except Exception:
        return None
    if not common:
        return None
    return max(common, key=lambda v: parse_final(v) or ((), 0))


def _fetch(url: str, timeout: float) -> Tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json, text/html;q=0.1",
            "User-Agent": "agentweave-updater",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - index URL
        return resp.read(), resp.headers.get("Content-Type", "")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_check(check_file: Path, latest: Optional[str]) -> None:
    write_json(check_file, {"checked_at": _now_iso(), "latest": latest})


def check_and_record(check_file: Path, **kwargs: Any) -> Optional[str]:
    """`check_latest()`, and when it answered, `update-check.json` records it. A failed check
    leaves the file as it was: what was last learned is still what is known."""
    latest = check_latest(**kwargs)
    if latest is not None:
        with contextlib.suppress(OSError):
            record_check(check_file, latest)
    return latest


def known_latest(
    check_file: Path, now: Optional[float] = None, **kwargs: Any
) -> Tuple[Optional[str], bool]:
    """While the app runs: what `update-check.json` knows, checked again only once it is 24 h old
    (FR-2). Returns (latest, fresh) -- `fresh` when this call asked the index."""
    data = read_json(check_file)
    checked = data.get("checked_at")
    age: Optional[float] = None
    if isinstance(checked, str):
        with contextlib.suppress(ValueError):
            stamp = datetime.strptime(checked, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = (now if now is not None else time.time()) - stamp.timestamp()
    if age is not None and 0 <= age < RECHECK_SECONDS:
        latest = data.get("latest")
        return (latest if isinstance(latest, str) else None), False
    latest = check_and_record(check_file, **kwargs)
    if latest is None:
        cached = data.get("latest")
        return (cached if isinstance(cached, str) else None), True
    return latest, True


# --- the setting (FR-11) ----------------------------------------------------------------------


def auto_update_on(setting_file: Path) -> bool:
    """'Update automatically when I open AgentWeave': absent or unreadable is on (the default)."""
    value = read_json(setting_file).get("auto", True)
    return value is not False


def set_auto_update(setting_file: Path, on: bool) -> bool:
    write_json(setting_file, {"auto": bool(on)})
    return bool(on)


# --- reading a Hub without a window (FR-1, FR-3) ----------------------------------------------


def hub_health(port: int, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """The Hub's GET /health body, or None when nothing (or nothing that is a Hub) answers."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - loopback
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as resp:
            if resp.status != 200:
                return None
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def hub_version(port: int, timeout: float = 2.0) -> Optional[str]:
    """The `version` the Hub on `port` reports. None for no Hub, and for an older Hub whose
    /health has no `version` (CONTRACT: version unknown -- never updated automatically)."""
    body = hub_health(port, timeout)
    version = (body or {}).get("version")
    return version if isinstance(version, str) and version else None


# --- the lock (FR-10) -------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == 259  # STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class UpdateLock:
    """`update.lock`: one update at a time, instance-wide, because every Hub of the install runs
    from the same package files. Created exclusively; a lock whose holder has exited is stale and
    taken over. Records who holds it (`pid`, `port`, `since`) so a second launch can tell an
    update for its own port from one for another."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.held = False

    def holder(self) -> Optional[Dict[str, Any]]:
        """Who holds the lock now, or None when nobody alive does."""
        data = read_json(self.path)
        if not self.path.exists():
            return None
        pid = data.get("pid")
        if isinstance(pid, int) and _pid_alive(pid):
            return data
        if not data:  # being written this instant, or unreadable: young means being written
            with contextlib.suppress(OSError):
                if time.time() - self.path.stat().st_mtime < 5:
                    return {"pid": None, "port": None}
        return None

    def acquire(self, port: Optional[int] = None) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self.holder() is not None:
                    return False
                with contextlib.suppress(OSError):
                    self.path.unlink()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "port": port, "since": _now_iso()}, handle)
            self.held = True
            return True
        return False

    def release(self) -> None:
        if not self.held:
            return
        self.held = False
        if read_json(self.path).get("pid") == os.getpid():
            with contextlib.suppress(OSError):
                self.path.unlink()

    def wait_released(self, timeout: float, poll: float = 0.5) -> bool:
        deadline = time.monotonic() + timeout
        while self.holder() is not None:
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll)
        return True


# --- the launch decision (FR-3, FR-4, FR-8, FR-9, FR-11) --------------------------------------


@dataclass
class LaunchFacts:
    """What a launch found, before it opened anything."""

    current: Optional[str]
    latest: Optional[str]
    kind: str = "pip"
    auto: bool = True
    #: "absent" (no Hub on the port), "idle" (answered: no work), "busy" (work running) or
    #: "silent" (a Hub that did not answer the work check -- not idle, D3).
    hub: str = "absent"
    #: The running Hub's /health `version`; None for an older Hub that does not say.
    hub_version: Optional[str] = None
    window_open: bool = False
    other_hubs: List[int] = field(default_factory=list)


@dataclass
class Decision:
    action: str  # "update" or "open"
    reason: str
    target: Optional[str] = None


def decide_at_launch(facts: LaunchFacts) -> Decision:
    """Update first, or open as things are. Pure: every reason not to update is one line here."""
    if facts.kind != "pip":
        return Decision("open", f"not a pip-installed release ({facts.kind})")
    if not is_newer(facts.latest, facts.current):
        return Decision("open", "no newer release known")
    if not facts.auto:
        return Decision("open", "automatic updating is off")
    if facts.hub != "absent" and not facts.hub_version:
        return Decision("open", "the running Hub does not report its version")
    if facts.hub == "busy":
        return Decision("open", "work is running")
    if facts.hub == "silent":
        return Decision("open", "the running Hub did not answer the work check")
    if facts.hub not in ("absent", "idle"):
        return Decision("open", f"unknown Hub state {facts.hub!r}")
    if facts.window_open:
        return Decision("open", "a window is already open on this Hub")
    if facts.other_hubs:
        return Decision(
            "open", f"another Hub of this installation runs on {_ports(facts.other_hubs)}"
        )
    return Decision("update", f"{facts.current} -> {facts.latest}", facts.latest)


def work_state(work: Optional[Dict[str, Any]]) -> str:
    """`idle`, `busy` or `silent` from the /api/v1/work/running answer (None: no answer)."""
    if not isinstance(work, dict) or "running" not in work:
        return "silent"
    return "busy" if work.get("running") else "idle"


def _ports(ports: List[int]) -> str:
    return ", ".join(f"port {p}" for p in sorted(ports))


# --- the database copy (FR-7) -----------------------------------------------------------------


def backup_database(db_path: Path, backups_root: Path, keep: int = BACKUPS_KEPT) -> Optional[Path]:
    """Copy the Hub's SQLite database with the backup API (consistent under WAL), into
    `update-backups/<UTC stamp>/`; keep the newest `keep`. None when there is no database yet."""
    if not db_path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = backups_root / stamp
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / db_path.name
    _sqlite_copy(db_path, target)
    _prune(backups_root, keep)
    return target


def restore_database(copy: Optional[Path], db_path: Path) -> None:
    """Put the copy back over the database; no copy means there was none, so none is left.

    Restored with the backup API into the database file itself, which replaces its whole content
    (a half-applied migration's tables included) and leaves its WAL consistent with it."""
    if copy is None:
        for suffix in ("", "-wal", "-shm", "-journal"):
            with contextlib.suppress(FileNotFoundError):
                Path(str(db_path) + suffix).unlink()
        return
    _sqlite_copy(copy, db_path)


def _sqlite_copy(source: Path, target: Path) -> None:
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()


def _prune(backups_root: Path, keep: int) -> None:
    folders = sorted(p for p in backups_root.iterdir() if p.is_dir())
    import shutil

    for old in folders[:-keep] if keep > 0 else folders:
        shutil.rmtree(old, ignore_errors=True)


# --- pip (D4) ---------------------------------------------------------------------------------


def pip_command(version: str, reinstall: bool = False, python: Optional[str] = None) -> List[str]:
    """`python -m pip install agentweave-ai==V agentweave-hub==V`, run by this interpreter (not the
    console script, which Windows will not overwrite while it runs)."""
    cmd = [
        python or sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
    ]
    if reinstall:
        cmd += ["--force-reinstall", "--no-deps"]
    url = os.environ.get(INDEX_ENV)
    if url:
        cmd += ["--index-url", url]
    cmd += [f"{p}=={version}" for p in PACKAGES]
    return cmd


def run_pip(version: str, reinstall: bool = False) -> Tuple[bool, str]:
    """Run pip with no console window; (ok, the last of what it printed)."""
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        done = subprocess.run(
            pip_command(version, reinstall=reinstall),
            capture_output=True,
            text=True,
            timeout=PIP_SECONDS,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    output = (done.stdout or "") + (done.stderr or "")
    return done.returncode == 0, output[-2000:]


# --- the apply sequence (FR-6, FR-7, FR-8, FR-10) ---------------------------------------------


@dataclass
class ApplyResult:
    #: "applied", "failed" (the previous version is back), "blocked" (nothing was touched) or
    #: "needs_confirm" (work is running and the operator has not confirmed stopping it).
    state: str
    detail: str
    backup: Optional[Path] = None


@dataclass
class Applier:
    """The injectable callables an update runs; cli.py binds them to the real Hub."""

    port: int
    current: str
    target: str
    db_path: Path
    backups_root: Path
    lock: UpdateLock
    #: Ports of other Hubs of this installation that are running (FR-8).
    other_hubs: Callable[[], List[int]]
    #: Stop the Hub on `port`; None when it is stopped (or was not running), else why not.
    stop: Callable[[], Optional[str]]
    #: Start the Hub on `port` and profile; None when started, else why not.
    start: Callable[[], Optional[str]]
    #: The version the Hub on `port` reports, or None.
    version: Callable[[], Optional[str]] = lambda: None
    #: Install `version` of both packages; (ok, output). `reinstall` is the restore.
    pip: Callable[..., Tuple[bool, str]] = run_pip
    healthy_seconds: float = HEALTHY_SECONDS
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = lambda _m: None


def apply_update(
    applier: Applier,
    confirmed: bool = True,
    work: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    describe: Callable[[Dict[str, Any]], str] = lambda w: "work is running",
) -> ApplyResult:
    """Stop this port's Hub, copy the database, upgrade, start, verify -- or put it all back.

    Order (D4): every refusal (another Hub, an update already under way, unconfirmed work)
    happens before anything is touched. Once the database is copied, any failure restores:
    the previous version reinstalled, the copy put back, the Hub started, and `failed` says why.
    """
    a = applier
    if work is not None and not confirmed:
        answer = work()
        state = work_state(answer)
        if state != "idle":
            text = describe(answer) if answer else "the Hub did not say what is running"
            return ApplyResult("needs_confirm", text)
    others = a.other_hubs()
    if others:
        return ApplyResult(
            "blocked",
            f"Another AgentWeave Hub of this installation is running on {_ports(others)}. "
            "Stop it, then update.",
        )
    owned = a.lock.held
    if not owned and not a.lock.acquire(a.port):
        holder = a.lock.holder() or {}
        where = f" for port {holder['port']}" if holder.get("port") else ""
        return ApplyResult("blocked", f"An update is already under way{where}.")
    try:
        return _apply_locked(a)
    finally:
        if not owned:
            a.lock.release()


def _apply_locked(a: Applier) -> ApplyResult:
    a.log(f"Updating AgentWeave {a.current} -> {a.target}")
    why = a.stop()
    if why:
        return ApplyResult("failed", f"The Hub could not be stopped, so nothing changed: {why}")
    try:
        copy = backup_database(a.db_path, a.backups_root)
    except Exception as exc:  # no copy, no update: the database is the one thing not risked
        started = a.start()
        tail = f" (and the Hub did not start again: {started})" if started else ""
        return ApplyResult(
            "failed", f"The database could not be copied, so nothing changed: {exc}{tail}"
        )
    a.log(f"Database copied to {copy}" if copy else "No database yet; nothing to copy")

    ok, output = a.pip(a.target)
    if not ok:
        return _restore(a, copy, f"the upgrade to {a.target} failed: {_last_line(output)}")
    why = a.start()
    if why:
        return _restore(a, copy, f"{a.target} did not start: {why}")
    version = _wait_for_version(a, a.target)
    if version != a.target:
        seen = f"it reported {version}" if version else "it did not answer"
        return _restore(
            a, copy, f"{a.target} did not report healthy within {int(a.healthy_seconds)} s ({seen})"
        )
    a.log(f"AgentWeave {a.target} is running")
    return ApplyResult("applied", f"Updated to {a.target}.", copy)


def _wait_for_version(a: Applier, target: str) -> Optional[str]:
    deadline = time.monotonic() + a.healthy_seconds
    seen: Optional[str] = None
    while True:
        seen = a.version()
        if seen == target or time.monotonic() >= deadline:
            return seen
        a.sleep(1.0)


def _restore(a: Applier, copy: Optional[Path], reason: str) -> ApplyResult:
    """FR-7: without asking, the previous version and the database copy back, then started."""
    a.log(f"Update failed ({reason}); restoring {a.current}")
    problems: List[str] = []
    stopped = a.stop()
    if stopped:
        problems.append(f"the new Hub could not be stopped: {stopped}")
    ok, output = a.pip(a.current, reinstall=True)
    if not ok:
        problems.append(f"reinstalling {a.current} failed: {_last_line(output)}")
    try:
        restore_database(copy, a.db_path)
    except Exception as exc:
        problems.append(f"the database copy {copy} could not be put back: {exc}")
    why = a.start()
    if why:
        problems.append(f"{a.current} did not start again: {why}")
    detail = f"The update to {a.target} failed: {reason}. {a.current} was put back"
    if copy is not None:
        detail += f", with the database as it was before (copy kept in {copy.parent})"
    detail += "."
    if problems:
        detail += " But: " + "; ".join(problems) + "."
    return ApplyResult("failed", detail, copy)


def _last_line(output: str) -> str:
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    return lines[-1] if lines else "no output"
