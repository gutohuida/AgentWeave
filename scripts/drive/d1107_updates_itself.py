"""Acceptance drive for "AgentWeave updates itself" (spec/changes/agentweave-updates-itself).

Written failing first (task AWUI-1), against the CONTRACT in the document's design:
  * GET /health gains `version` and `install` ("pip" | "editable" | "checkout");
  * AW_UPDATE_INDEX_URL, a PEP 503 simple index base URL, read only by the updater;
  * the window bridge (`window.pywebview.api`) gains `update_status()`, `set_auto_update(on)` and
    `apply_update(confirmed)` -> {"state": "needs_confirm" | "applied" | "failed" | "blocked"};
  * HUB_DIR/app-window/update.json {"auto": bool} (absent = on), update-check.json, update.lock;
  * HUB_DIR/update-backups/<stamp>/ holding the database copy.

What it builds, all of it scratch and all of it its own:
  * wheels of THIS checkout, both packages, with the version rewritten to 2.1.0, 2.1.1, 2.1.2
    (listed yanked), 2.2.0rc1 (a pre-release), and a second 2.1.1 of the Hub whose extra migration
    raises -- so the 2.1.0 installed is the code under test, and an update is a real pip upgrade;
  * a virtual environment (cached across runs in %TEMP%\\agentweave-d1107\\venv for its
    dependencies; the AgentWeave packages are reinstalled at every step) with 2.1.0 pip-installed;
  * a local package index on a free port, three variants: `base` (2.1.0 only), `good` (2.1.0,
    2.1.1, yanked 2.1.2, 2.2.0rc1) and `fail` (2.1.0, the failing 2.1.1, 2.2.0rc1), logging every
    request; plus a port that refuses and a port that accepts and never answers (index down);
  * a scratch home: the app runs with USERPROFILE pointing at it, so HUB_DIR (profiles, .env,
    app-window/update.json, the lock, the backups, the Desktop shortcut) is the drive's, never the
    operator's ~/.agentweave/hub. CLAUDE_CONFIG_DIR keeps the real ~/.claude so Haiku turns can
    sign in. Scratch ports 8190-8191 by default; never :8000 or :8010, which are only listed
    (netstat), never called.

The app is launched as the shortcut launches it: the scratch install's own
`_resolve_shortcut_target()` (`pythonw.exe -m agentweave`) plus --profile/--port. The page is read
through WebView2's DevTools port (each app its own port and user-data folder), and the bridge is
called from the page exactly as the page calls it. Real agent turns run on Haiku where work must be
running (d1105_own_app.start_turn: a turn that sleeps 150 s in a shell).

Steps, each named after the criterion it checks (`--only` takes these names):
  version     c-shows-version         /health `version` and App settings both 2.1.0
  newer       c-knows-newer-offline   index up: 2.1.1 named (not 2.2.0rc1, not yanked 2.1.2) in
                                      App settings and on the Update button; index refusing and
                                      index silent: no error, window within 5 s of the baseline
  idle        c-launch-updates-idle   auto at default, nothing running: the window opens on 2.1.1,
                                      a database copy kept, no console window of the app's
  auto-off    c-auto-off              set_auto_update(false) in the window; next launch opens on
                                      2.1.0 with the button naming 2.1.1; still off a launch later
  busy        c-never-interrupts      a Haiku turn running, auto on, a second launch: same Hub pid,
              c-button-names-work     same turn, 2.1.0, the button shown; apply_update(false)
                                      answers needs_confirm naming "1 agent turn", nothing changes;
                                      apply_update(true) applies
  after-work  c-after-work-ends       window maximized, a turn runs and ends, apply_update: the same
                                      window (same handle), maximized, same rectangle, on 2.1.1, the
                                      projects and runs that were there
  migration   c-migration-failure     the `fail` index: apply_update; 2.1.0 installed and running
                                      again, no native dialog, the failure stated, the database's
                                      schema, revision and project/agent/runner rows equal to the
                                      copy taken before, no trace of the failed migration's table
  other-hub   c-other-hub             two Hubs of the install; apply_update on one: blocked naming
                                      the other's port; the other's pid and health unchanged
  concurrent  c-concurrent            two launches 0.3 s apart: each 2.1.1 wheel fetched once from
                                      the index, one window, one Hub, 2.1.1
  checkout    c-checkout              an editable install: /health names 2.1.0 and install not
                                      "pip", App settings shows it, no Update button, no upgrade

Assumptions about details the CONTRACT leaves open (named once so the build can move them):
  UPDATE_BUTTON -- the button carries data-testid="update-button" (else: any button whose text says
                   Update and a version number).
  The App settings text is read across every section of App settings (the rail's App settings,
  then each section in turn), so the version may live in any section.

Ends with one baseline line per criterion,
  check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <first failing assertion>
which is what the drive task's `drive_baseline` evidence carries.

Restores on exit what a scratch launch rewrites outside the scratch home: the `agentweave:` link
registration (HKCU) and the Start-menu shortcut. Kills every process it started, and every process
running from the scratch venv.

  py -3.11 scripts/drive/d1107_updates_itself.py
  py -3.11 scripts/drive/d1107_updates_itself.py --only version,newer
  py -3.11 scripts/drive/d1107_updates_itself.py --port 8190 --fresh-venv
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.server
import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
import d1105_own_app as d  # noqa: E402
import d1108_windows_notifications as w  # noqa: E402

user32 = d.user32
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, d.ctypes.POINTER(wintypes.RECT)]
note, wait_for = d.note, d.wait_for

FORBIDDEN_PORTS = {8000, 8010}
NO_WINDOW = 0x08000000
SW_MAXIMIZE = 3
RUN = time.strftime("%H%M%S")
BASE = pathlib.Path(tempfile.gettempdir()) / "agentweave-d1107"
SCRATCH = BASE / RUN
VENV = BASE / "venv"  # its dependencies are kept between runs; the AgentWeave packages are not
VENV_PY = VENV / "Scripts" / "python.exe"
HOME = SCRATCH / "home"
HUB_DIR = HOME / ".agentweave" / "hub"
WHEELS = SCRATCH / "wheels"
PROFILE_PREFIX = "d1107upd"
REAL_CLAUDE = pathlib.Path.home() / ".claude"
REAL_APPDATA = pathlib.Path.home() / "AppData"
APPDATA_LINK = HOME / "AppData"
UPDATE_BUTTON = '[data-testid="update-button"]'
OLD, NEW, YANKED, PRE = "2.1.0", "2.1.1", "2.1.2", "2.2.0rc1"
LAUNCH_EXTRA_LIMIT = 5.0  # the criterion's "under 5 seconds extra"
APPLY_LIMIT = 360.0  # stop + pip + start + health (120 s) + restore, with room


# --- criteria ----------------------------------------------------------------------------------


class Criterion:
    """One acceptance criterion: its preconditions, then its assertions, in order.

    A precondition that cannot be established leaves the criterion not reached (its assertions are
    skipped, not counted); the first assertion that fails is what the baseline line names."""

    def __init__(self, key: str, fr: str):
        self.key, self.fr = key, fr
        self.blocked: str | None = None
        self.asserted = False
        self.first_fail: str | None = None
        self.passed = 0

    def need(self, name: str, ok: bool, detail: str = "") -> bool:
        d.check(f"{self.key}: {name} (precondition)", bool(ok), detail)
        if not ok and self.blocked is None:
            self.blocked = f"{name}" + (f": {detail}" if detail else "")
        return bool(ok) and self.blocked is None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        if self.blocked is not None:
            return False
        self.asserted = True
        d.check(f"{self.key}: {name}", bool(ok), detail)
        if ok:
            self.passed += 1
        elif self.first_fail is None:
            self.first_fail = f"{name}" + (f" -- {detail}" if detail else "")
        return bool(ok)

    def line(self) -> str:
        reached = self.asserted and self.blocked is None
        failed = self.first_fail is not None
        if not reached:
            why = self.blocked or "its step did not run"
        elif failed:
            why = self.first_fail
        else:
            why = f"all {self.passed} assertions passed"
        why = re.sub(r"\s+", " ", why or "")[:300]
        return (
            f"check {self.key} ({self.fr}): reached={'yes' if reached else 'no'} "
            f"failed_at_assertion={'yes' if reached and failed else 'no'} -- {why}"
        )


CRITS = {
    c.key: c
    for c in (
        Criterion("c-shows-version", "FR-1"),
        Criterion("c-knows-newer-offline", "FR-2"),
        Criterion("c-launch-updates-idle", "FR-3"),
        Criterion("c-auto-off", "FR-11"),
        Criterion("c-never-interrupts", "FR-4"),
        Criterion("c-button-names-work", "FR-5"),
        Criterion("c-after-work-ends", "FR-6"),
        Criterion("c-migration-failure", "FR-7"),
        Criterion("c-other-hub", "FR-8"),
        Criterion("c-checkout", "FR-9"),
        Criterion("c-concurrent", "FR-10"),
    )
}


# --- processes ---------------------------------------------------------------------------------


def sh(cmd: list, timeout: float = 900, env: dict | None = None, cwd=None):
    return subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
        creationflags=NO_WINDOW,
    )


def clean_env() -> dict:
    """The drive's environment less what would point the scratch install at this checkout or at
    another database, index or home."""
    env = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "DATABASE_URL",
        "AW_UPDATE_INDEX_URL",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_FIND_LINKS",
        "VIRTUAL_ENV",
    ):
        env.pop(name, None)
    env["PIP_NO_CACHE_DIR"] = "1"  # every 2.1.1 the index serves is counted (c-concurrent)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def pip(*args, timeout: float = 1200):
    done = sh([VENV_PY, "-m", "pip", *args], timeout=timeout, env=clean_env())
    if done.returncode != 0:
        raise SystemExit(
            f"pip {' '.join(map(str, args))} failed:\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
        )
    return done


def installed(package: str = "agentweave-hub") -> str:
    """The version the scratch install holds now, read from its own metadata."""
    done = sh(
        [VENV_PY, "-c", f"import importlib.metadata as m; print(m.version('{package}'))"],
        timeout=60,
        env=clean_env(),
    )
    return done.stdout.strip() or f"? {done.stderr.strip()[-200:]}"


def editable(package: str = "agentweave-hub") -> bool:
    done = sh(
        [
            VENV_PY,
            "-c",
            "import importlib.metadata as m, json;"
            f" t = m.distribution('{package}').read_text('direct_url.json');"
            " print(bool(t and json.loads(t).get('dir_info', {}).get('editable')))",
        ],
        timeout=60,
        env=clean_env(),
    )
    return done.stdout.strip() == "True"


def kill_tree(pids) -> None:
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW
        )


def kill_venv_processes() -> None:
    """Anything still running from the scratch venv is this drive's."""
    venv = str(VENV).lower()
    rows = d.processes()
    kill_tree(r["ProcessId"] for r in rows if venv in (r.get("CommandLine") or "").lower())


# A venv's pythonw.exe is a redirector: it starts the base interpreter's pythonw.exe as its child,
# and that child owns the window and serves the Hub (2026-11-15, the first run of this drive). So
# windows and Hubs are found through the process tree, read with a Toolhelp snapshot (fast enough
# to poll every 100 ms, unlike d1105's CIM query).


class PROCESSENTRY32W(d.ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", d.ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


kernel32 = d.ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, d.ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, d.ctypes.POINTER(PROCESSENTRY32W)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def parents() -> dict[int, int]:
    """pid -> parent pid, for every process."""
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    out: dict[int, int] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = d.ctypes.sizeof(PROCESSENTRY32W)
    try:
        ok = kernel32.Process32FirstW(snap, d.ctypes.byref(entry))
        while ok:
            out[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(snap, d.ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


def tree(roots: set[int]) -> set[int]:
    table = parents()
    found, grew = set(roots), True
    while grew:
        grew = False
        for pid, parent in table.items():
            if parent in found and pid not in found:
                found.add(pid)
                grew = True
    return found


def windows_of(roots: set[int]) -> list[dict]:
    return d.app_windows(tree(roots))


def hub_pids(port: int, rows: list[dict] | None = None) -> list[int]:
    """The process serving `port`: the uvicorn command line's deepest process (the venv
    redirector's child), so one Hub is one pid."""
    rows = rows if rows is not None else d.processes()
    matched = set(d.hub_pids(port, rows))
    has_child = {r["ParentProcessId"] for r in rows if r["ProcessId"] in matched}
    return sorted(matched - has_child)


# --- the scratch home ----------------------------------------------------------------------------
#
# With USERPROFILE pointed at a bare folder, WebView2 never opens its DevTools port (the browser
# carries --remote-debugging-port and listens on nothing; measured 2026-11-15 with a plain pywebview
# window, which listens as soon as the folder holds AppData). So the scratch home holds a junction
# to the real AppData: HUB_DIR (home/.agentweave/hub) stays the drive's own, and what was in AppData
# is where it always was (APPDATA and LOCALAPPDATA are not changed either). The junction is removed
# with os.rmdir, which never touches its target, BEFORE anything deletes the scratch folder.


def make_home() -> None:
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    if not APPDATA_LINK.exists():
        done = sh(["cmd", "/c", "mklink", "/J", APPDATA_LINK, REAL_APPDATA], timeout=30)
        if done.returncode != 0:
            raise SystemExit(f"cannot link the scratch home's AppData: {done.stdout} {done.stderr}")


def _writable_then(func, path, _exc) -> None:
    """rmtree's retry for a read-only file (git's objects)."""
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
        func(path)


def unlink_home() -> bool:
    """Remove the junction; True when the scratch folder is then safe to delete."""
    if os.path.lexists(APPDATA_LINK):
        with contextlib.suppress(OSError):
            os.rmdir(APPDATA_LINK)
    return not os.path.lexists(APPDATA_LINK)


# --- wheels ------------------------------------------------------------------------------------


def migration_head() -> str:
    versions = ROOT / "hub" / "hub" / "migrations" / "versions"
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


FAILING_MIGRATION = '''"""d1107: a migration made to fail, for the failed-update-restores drive only."""

import sqlalchemy as sa
from alembic import op

revision = "d1107fail"
down_revision = "{head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("d1107_half_migrated", sa.Column("x", sa.Integer))
    op.execute("insert into d1107_half_migrated (x) values (1)")
    raise RuntimeError("d1107: this migration is made to fail")


def downgrade() -> None:
    pass
'''


def stage(version: str, fail: bool = False) -> pathlib.Path:
    """This checkout's two packages, as source trees, with `version` written in."""
    out = SCRATCH / "stage" / (version + ("-fail" if fail else ""))
    if out.exists():
        return out
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules", ".pytest_cache")
    ai, hub = out / "ai", out / "hub"
    ai.mkdir(parents=True)
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
        shutil.copy2(ROOT / name, ai / name)
    shutil.copytree(ROOT / "src", ai / "src", ignore=ignore)
    hub.mkdir()
    for name in ("pyproject.toml", "LICENSE", "NOTICE"):
        shutil.copy2(ROOT / "hub" / name, hub / name)
    shutil.copytree(ROOT / "hub" / "hub", hub / "hub", ignore=ignore)
    for project in (ai, hub):
        toml = project / "pyproject.toml"
        text = re.sub(
            r'^version = "[^"]+"',
            f'version = "{version}"',
            toml.read_text("utf-8"),
            count=1,
            flags=re.M,
        )
        text = re.sub(r'"agentweave-hub>=[^"]+"', f'"agentweave-hub>={version}"', text)
        toml.write_text(text, encoding="utf-8")
    if fail:
        (hub / "hub" / "migrations" / "versions" / "9999_d1107_fails.py").write_text(
            FAILING_MIGRATION.format(head=migration_head()), encoding="utf-8"
        )
    return out


def build(version: str, fail: bool = False) -> dict[str, pathlib.Path]:
    src = stage(version, fail)
    out = WHEELS / src.name
    out.mkdir(parents=True, exist_ok=True)
    pip("wheel", "--no-deps", "--no-build-isolation", "-w", out, src / "hub", src / "ai")
    found = {
        "agentweave-hub": next(out.glob("agentweave_hub-*.whl")),
        "agentweave-ai": next(out.glob("agentweave_ai-*.whl")),
    }
    note(f"built {src.name}: {[p.name for p in found.values()]}")
    return found


def remove_venv(limit: float = 30.0) -> None:
    """Delete the cached venv, waiting out a process still exiting that holds its python.exe:
    a silent partial delete left `py -m venv` failing with Permission denied."""

    def gone() -> bool:
        shutil.rmtree(VENV, onerror=_writable_then)
        return not VENV.exists()

    if not wait_for(gone, limit, 1.0):
        raise SystemExit(f"cannot delete {VENV}: something still holds it; delete it by hand")


def sweep_pip_leftovers() -> None:
    """A run interrupted mid-pip leaves `~`-prefixed stashes (`~gentweave_hub`) in site-packages."""
    site = VENV / "Lib" / "site-packages"
    for left in site.glob("~*") if site.is_dir() else []:
        note(f"removing pip's leftover {left.name}")
        shutil.rmtree(left, onerror=_writable_then)


def ensure_venv(fresh: bool) -> None:
    marker = VENV / ".d1107-ready"
    if fresh:
        remove_venv()
    if marker.exists() and VENV_PY.exists():
        sweep_pip_leftovers()
        return
    remove_venv()
    done = sh(["py", "-3.11", "-m", "venv", VENV], timeout=300, env=clean_env())
    if done.returncode != 0:
        raise SystemExit(f"venv: {done.stderr}")
    pip("install", "-U", "pip", "setuptools>=77", "wheel")
    marker.parent.mkdir(parents=True, exist_ok=True)


def install_release(wheels: dict, version: str) -> None:
    """The scratch install holds `version` of both packages, as a pip install (not editable)."""
    whl = wheels[version]
    pip("install", "--force-reinstall", "--no-deps", whl["agentweave-hub"], whl["agentweave-ai"])
    assert installed() == version, installed()


def install_dependencies(wheels: dict) -> None:
    """The first install: the 2.1.0 wheels with their dependencies from PyPI (as an operator's
    `pip install agentweave-ai` does), plus pywebview for the window, once per cached venv."""
    marker = VENV / ".d1107-ready"
    if marker.exists():
        return
    whl = wheels[OLD]
    pip(
        "install",
        "-c",
        ROOT / "constraints-dev.txt",
        whl["agentweave-hub"],
        whl["agentweave-ai"],
        "pywebview>=5.0",
    )
    marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


# --- the local package index -------------------------------------------------------------------


class Index:
    """A PEP 503 (and PEP 691) simple index of the scratch wheels, three variants, every request
    logged."""

    def __init__(self, variants: dict[str, list[tuple[dict, bool]]]):
        # variant -> project -> [(filename, path, yanked)]
        self.files: dict[str, dict[str, list[tuple[str, pathlib.Path, bool]]]] = {}
        for variant, releases in variants.items():
            projects: dict[str, list] = {}
            for wheels, yanked in releases:
                for project, path in wheels.items():
                    projects.setdefault(project, []).append((path.name, path, yanked))
            self.files[variant] = projects
        self.hits: list[tuple[float, str]] = []
        self.lock = threading.Lock()
        index = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def do_GET(self):  # noqa: N802
                with index.lock:
                    index.hits.append((time.time(), self.path))
                index.serve(self)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, variant: str) -> str:
        return f"http://127.0.0.1:{self.port}/{variant}/simple/"

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()

    def downloads(self, filename_prefix: str) -> int:
        with self.lock:
            return sum(1 for _, path in self.hits if f"/files/{filename_prefix}" in path)

    def serve(self, handler) -> None:
        parts = [p for p in handler.path.split("?", 1)[0].split("/") if p]
        json_wanted = "application/vnd.pypi.simple.v1+json" in (handler.headers.get("Accept") or "")
        variant = self.files.get(parts[0]) if parts else None
        if variant is None:
            return self._send(handler, 404, b"no such variant", "text/plain")
        if parts[1:2] == ["files"] and len(parts) == 3:
            for entries in variant.values():
                for name, path, _ in entries:
                    if name == parts[2]:
                        return self._send(
                            handler, 200, path.read_bytes(), "application/octet-stream"
                        )
            return self._send(handler, 404, b"no such file", "text/plain")
        if parts[1:2] != ["simple"]:
            return self._send(handler, 404, b"not found", "text/plain")
        if len(parts) == 2:
            if json_wanted:
                body = {"meta": {"api-version": "1.0"}, "projects": [{"name": n} for n in variant]}
                return self._json(handler, body)
            links = "".join(f'<a href="/{parts[0]}/simple/{n}/">{n}</a>\n' for n in variant)
            return self._send(
                handler, 200, f"<html><body>\n{links}</body></html>".encode(), "text/html"
            )
        project = re.sub(r"[-_.]+", "-", parts[2]).lower()
        entries = variant.get(project)
        if entries is None:
            return self._send(handler, 404, b"no such project", "text/plain")
        rows = []
        for name, path, yanked in entries:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append((name, f"/{parts[0]}/files/{name}", digest, yanked))
        if json_wanted:
            body = {
                "meta": {"api-version": "1.0"},
                "name": project,
                "files": [
                    {
                        "filename": n,
                        "url": u,
                        "hashes": {"sha256": h},
                        "requires-python": ">=3.11",
                        "yanked": y,
                    }
                    for n, u, h, y in rows
                ],
            }
            return self._json(handler, body)
        links = "".join(
            f'<a href="{u}#sha256={h}" data-requires-python="&gt;=3.11"'
            + (' data-yanked=""' if y else "")
            + f">{n}</a>\n"
            for n, u, h, y in rows
        )
        self._send(handler, 200, f"<html><body>\n{links}</body></html>".encode(), "text/html")

    def _json(self, handler, body) -> None:
        self._send(handler, 200, json.dumps(body).encode(), "application/vnd.pypi.simple.v1+json")

    @staticmethod
    def _send(handler, code: int, body: bytes, kind: str) -> None:
        handler.send_response(code)
        handler.send_header("Content-Type", kind)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


class SilentPort:
    """Accepts connections and never answers: an index that does not answer within 3 s."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.held: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.held.append(conn)


def refusing_url() -> str:
    """A port nothing listens on: an index that is offline."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/simple/"


# --- the scratch app ---------------------------------------------------------------------------


class BridgeMissingError(Exception):
    """The window bridge has no such method."""


def project_dir(name: str) -> pathlib.Path:
    path = SCRATCH / "projects" / name
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        (path / "README.md").write_text("updates-itself drive\n", encoding="utf-8")
        for cmd in (
            ["git", "init", "-b", "main"],
            ["git", "config", "user.email", "d@example.invalid"],
            ["git", "config", "user.name", "d"],
            ["git", "add", "."],
            ["git", "commit", "-m", "x"],
        ):
            subprocess.run(cmd, cwd=path, check=True, capture_output=True, creationflags=NO_WINDOW)
    return path


class App:
    """One scratch Hub of the scratch install, on one port and profile, launched as the shortcut."""

    def __init__(self, port: int, profile: str, cwd: pathlib.Path, cdp: int):
        if port in FORBIDDEN_PORTS:
            raise SystemExit(f"refusing port {port}: :8000 and :8010 are never driven")
        self.port, self.profile, self.cwd, self.cdp = port, profile, cwd, cdp
        self.udf = SCRATCH / f"webview-{cdp}"
        self.launchers: list[subprocess.Popen] = []
        self.opened_in: float | None = None
        self.launched_at = 0.0

    def env(self, index_url: str) -> dict:
        env = clean_env()
        env.update(
            {
                "USERPROFILE": str(HOME),  # HUB_DIR is Path.home()/.agentweave/hub
                "CLAUDE_CONFIG_DIR": os.environ.get("CLAUDE_CONFIG_DIR", str(REAL_CLAUDE)),
                "AGENTWEAVE_SOUND": "0",
                "AW_UPDATE_INDEX_URL": index_url,
                "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={self.cdp}",
                "WEBVIEW2_USER_DATA_FOLDER": str(self.udf),
            }
        )
        return env

    def shortcut(self, index_url: str) -> list[str]:
        done = sh(
            [
                VENV_PY,
                "-c",
                "import json; from agentweave.cli import _resolve_shortcut_target as r;"
                " print(json.dumps(r()))",
            ],
            timeout=60,
            env=self.env(index_url),
        )
        target, arguments = json.loads(done.stdout.strip().splitlines()[-1])
        return [target, *arguments.split()]

    def launch(self, index_url: str, cmd: list[str] | None = None) -> subprocess.Popen:
        """`cmd` is a shortcut target resolved beforehand: resolving it spawns the venv's Python."""
        cmd = cmd or self.shortcut(index_url)
        user32.AllowSetForegroundWindow(d.ASFW_ANY)
        proc = subprocess.Popen(
            [*cmd, "--profile", self.profile, "--port", str(self.port)],
            cwd=self.cwd,
            env=self.env(index_url),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.launchers.append(proc)
        return proc

    def open(self, index_url: str, timeout: float = 120) -> int | None:
        """Launch and wait for the window; `opened_in` is the seconds from launch to window."""
        started = self.launched_at = time.monotonic()
        proc = self.launch(index_url)
        found = wait_for(lambda: windows_of({proc.pid}), timeout, 0.1)
        self.opened_in = time.monotonic() - started if found else None
        if not found:
            note(f":{self.port} no window within {timeout:.0f} s (launcher exit {proc.poll()})")
            return None
        return found[0]["hwnd"]

    @property
    def pids(self) -> set[int]:
        return {p.pid for p in self.launchers}

    def windows(self) -> list[dict]:
        return windows_of(self.pids)

    def health(self) -> dict | None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=3) as r:
                return json.loads(r.read() or b"null")
        except Exception:
            return None

    def version(self) -> str | None:
        return (self.health() or {}).get("version")

    def wait_healthy(self, timeout: float = 120) -> bool:
        return bool(wait_for(lambda: self.health() is not None, timeout, 0.5))

    def hub_pids(self) -> list[int]:
        return hub_pids(self.port)

    def key(self) -> str:
        for line in (HUB_DIR / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("AW_BOOTSTRAP_API_KEY="):
                return line.split("=", 1)[1].strip()
        raise RuntimeError("no AW_BOOTSTRAP_API_KEY in the scratch Hub folder's .env")

    def api(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1{path}",
            data,
            {"Authorization": "Bearer " + self.key(), "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")[:2000]

    @property
    def db_path(self) -> pathlib.Path:
        return HUB_DIR / "profiles" / self.profile / "agentweave.db"

    def db(self, sql: str, args=()):
        connection = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        try:
            return connection.execute(sql, args).fetchall()
        finally:
            connection.close()

    # -- the page, through WebView2's DevTools port

    def _pages(self) -> list[dict]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp}/json", timeout=2) as r:
                pages = [p for p in json.loads(r.read()) if p.get("type") == "page"]
        except Exception:
            return []
        hosts = (f"http://127.0.0.1:{self.port}/", f"http://localhost:{self.port}/")
        return [p for p in pages if p.get("url", "").startswith(hosts)]

    def page(self, expression: str, timeout: float = 15):
        w._pages = self._pages  # d1108's DevTools client, pointed at this app's page
        return w.page_eval(expression, timeout)

    def page_try(self, expression: str, default=None, timeout: float = 15):
        try:
            return self.page(expression, timeout)
        except Exception:
            return default

    def loaded_in(self, timeout: float = 120) -> float | None:
        """Seconds from the last `open` until the app's page has loaded, or None."""
        return time.monotonic() - self.launched_at if self.page_ready(timeout) else None

    def page_ready(self, timeout: float = 120) -> bool:
        return bool(
            wait_for(
                lambda: self.page_try(
                    "!!document.querySelector('[data-testid=\"rail-app-settings\"]')"
                    " && !!(window.pywebview && window.pywebview.api)",
                    False,
                ),
                timeout,
                1.0,
            )
        )

    def bridge(self, method: str, *args, timeout: float = 30):
        """Call `window.pywebview.api.<method>(*args)` from the page, as the page does."""
        call = json.dumps(method)
        expression = (
            "(async () => { const api = window.pywebview && window.pywebview.api;"
            f" if (!api || typeof api[{call}] !== 'function')"
            " return {__missing: Object.keys(api || {}).sort()};"
            f" return {{value: await api[{call}]({', '.join(json.dumps(a) for a in args)})}} }})()"
        )
        result = self.page(expression, timeout)
        if isinstance(result, dict) and "__missing" in result:
            raise BridgeMissingError(
                f"the window bridge has no {method}(); it has {result['__missing']}"
            )
        return result.get("value") if isinstance(result, dict) else result

    def fire(self, method: str, *args) -> str:
        """Start a bridge call that outlives the page (the update reloads it); '' when started."""
        call = json.dumps(method)
        expression = (
            "(() => { const api = window.pywebview && window.pywebview.api;"
            f" if (!api || typeof api[{call}] !== 'function')"
            " return 'the window bridge has no ' + " + call + " + '(); it has '"
            " + JSON.stringify(Object.keys(api || {}).sort());"
            " window.__d1107 = null;"
            f" api[{call}]({', '.join(json.dumps(a) for a in args)})"
            ".then(r => { window.__d1107 = r }, e => { window.__d1107 = {error: String(e)} });"
            " return '' })()"
        )
        try:
            return self.page(expression)
        except Exception as exc:
            return f"page: {exc}"

    def settings_text(self) -> str | None:
        """Every section of App settings, as the operator reads them in turn."""
        return self.page_try(
            """(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const rail = [...document.querySelectorAll('[data-testid="rail-app-settings"]')]
    .find(e => e.offsetParent !== null) || document.querySelector('[data-testid="rail-app-settings"]');
  if (!rail) return null;
  rail.click(); await sleep(1000);
  let text = '';
  const count = document.querySelectorAll('[data-slot="settings-nav-item"]').length;
  for (let i = 0; i < count; i++) {
    const item = document.querySelectorAll('[data-slot="settings-nav-item"]')[i];
    if (!item) continue;
    item.click(); await sleep(700);
    // A section's groups read the window bridge on mount (update_status, ~4 s on this machine),
    // so read it once its text has held still for 6 s (at most ~25 s), not the moment it is clicked.
    let last = null, cur = '', still = 0;
    for (let k = 0; k < 25 && still < 6; k++) {
      const s = document.querySelector('[data-testid^="app-settings-"]');
      cur = s ? s.innerText : '';
      still = cur === last ? still + 1 : 0;
      last = cur; await sleep(1000);
    }
    text += '\\n' + cur;
  }
  return text;
})()""",
            None,
            timeout=40,
        )

    def update_button(self) -> str | None:
        """The Update button's words (text, label and title), or None when there is none."""
        return self.page_try(
            f"""(() => {{
  const words = e => [e.innerText, e.getAttribute('aria-label'), e.title].filter(Boolean).join(' ');
  const b = document.querySelector('{UPDATE_BUTTON}')
    || [...document.querySelectorAll('button')].find(e => /\\bupdate\\b/i.test(words(e))
         && /\\d+\\.\\d+\\.\\d+/.test(words(e)));
  return b ? words(b).trim() : null;
}})()""",
            None,
        )

    def body_text(self) -> str:
        return self.page_try("document.body ? document.body.innerText : ''", "") or ""

    def cleanup(self) -> None:
        """Stop this Hub (`agentweave stop` of the scratch install) and end what was started."""
        with contextlib.suppress(Exception):
            sh(
                [
                    VENV_PY,
                    "-m",
                    "agentweave",
                    "stop",
                    "--profile",
                    self.profile,
                    "--port",
                    self.port,
                ],
                timeout=120,
                env=self.env(""),
                cwd=self.cwd,
            )
        rows = d.processes()
        kill_tree(d.descendants(rows, set(d.hub_pids(self.port, rows)) | self.pids))
        for proc in self.launchers:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.launchers.clear()
        wait_for(lambda: d.port_free(self.port), 30, 0.5)


# --- shared reads ------------------------------------------------------------------------------


def update_file() -> pathlib.Path:
    return HUB_DIR / "app-window" / "update.json"


def set_auto_file(on: bool | None) -> None:
    """Write the auto-update setting as App settings writes it (None: absent, the default)."""
    path = update_file()
    if on is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"auto": on}), encoding="utf-8")


def auto_file() -> object:
    try:
        return json.loads(update_file().read_text(encoding="utf-8")).get("auto")
    except (OSError, ValueError):
        return "absent"


def forget_check() -> None:
    (HUB_DIR / "app-window" / "update-check.json").unlink(missing_ok=True)


def backups() -> list[pathlib.Path]:
    root = HUB_DIR / "update-backups"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def stable_dump(path: pathlib.Path) -> str:
    """What an update must not change: the schema, the migration revision, and which projects,
    agents and runners exist. Ids only: a live Hub keeps rewriting their status columns (seen
    2026-11-15: the full rows differed with no update applied at all), and runs and messages
    keep moving."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        parts = [
            repr(
                connection.execute(
                    # sqlite_stat*: the Hub's own ANALYZE 30 s after a start (db_maintenance.py)
                    "select name, sql from sqlite_master where type in ('table','index')"
                    " and name not like 'sqlite_stat%' order by name"
                ).fetchall()
            )
        ]
        with contextlib.suppress(sqlite3.Error):
            parts.append(repr(connection.execute("select * from alembic_version").fetchall()))
        for table in ("projects", "agents", "runners"):
            with contextlib.suppress(sqlite3.Error):
                parts.append(
                    repr(connection.execute(f"select id from {table} order by id").fetchall())
                )
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()
    finally:
        connection.close()


def has_table(path: pathlib.Path, table: str) -> bool:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return bool(
            connection.execute("select 1 from sqlite_master where name=?", (table,)).fetchall()
        )
    finally:
        connection.close()


def bridge_try(app: App, method: str, *args, timeout: float = 30) -> tuple[object, str]:
    """(value, '') or (None, why)."""
    try:
        return app.bridge(method, *args, timeout=timeout), ""
    except BridgeMissingError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"page: {exc}"


def wait_version(app: App, version: str, timeout: float) -> bool:
    return bool(wait_for(lambda: app.version() == version, timeout, 2.0))


def rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, d.ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def ids(app: App, table: str) -> set[str]:
    with contextlib.suppress(Exception):
        return {row[0] for row in app.db(f"select id from {table}")}
    return set()


def profile(step: str) -> str:
    return f"{PROFILE_PREFIX}{RUN}{step}"


def native_boxes(pids: set[int]) -> list[dict]:
    rows = d.processes()
    ours = d.descendants(rows, pids)
    return [
        w_
        for w_ in d.top_windows()
        if w_["pid"] in ours and w_["cls"] == "#32770" and w_["visible"]
    ]


# --- steps -------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, wheels, index: Index, silent: SilentPort, refused: str, ports, cdps):
        self.wheels, self.index, self.silent, self.refused = wheels, index, silent, refused
        self.ports, self.cdps = ports, cdps

    def app(self, step: str, which: int = 0) -> App:
        return App(self.ports[which], profile(step), project_dir(step), self.cdps[which])


def step_version(ctx: Ctx) -> None:
    c = CRITS["c-shows-version"]
    install_release(ctx.wheels, OLD)
    set_auto_file(None)
    app = ctx.app("version")
    try:
        hwnd = app.open(ctx.index.url("base"))
        if not c.need("the scratch app's window opens", hwnd is not None):
            return
        if not c.need("its Hub answers /health", app.wait_healthy()):
            return
        c.need("the scratch install is 2.1.0", installed() == OLD, installed())
        if not c.need("the page has loaded", app.page_ready()):
            return
        health = app.health()
        note(f"/health: {health}")
        c.check(
            "GET /health names version 2.1.0",
            (health or {}).get("version") == OLD,
            json.dumps(health),
        )
        text = app.settings_text()
        c.check(
            "App settings shows 2.1.0",
            bool(text) and OLD in text,
            "no App settings" if text is None else re.sub(r"\s+", " ", text)[:300],
        )
        note(f"/health install: {(health or {}).get('install')!r} (CONTRACT: 'pip' here)")
    finally:
        app.cleanup()


def step_newer(ctx: Ctx) -> None:
    c = CRITS["c-knows-newer-offline"]
    install_release(ctx.wheels, OLD)
    set_auto_file(False)  # so the launch shows what it learned instead of applying it
    app = ctx.app("newer")
    try:
        # The baseline launch: an index that answers, with nothing newer on it.
        if not c.need(
            "a baseline launch opens (index up, nothing newer)",
            app.open(ctx.index.url("base")) is not None,
        ):
            return
        baseline = app.loaded_in()
        if not c.need("the baseline launch loads the app", baseline is not None):
            return
        note(f"baseline launch: window in {app.opened_in:.1f} s, app loaded in {baseline:.1f} s")
        app.cleanup()

        forget_check()
        if not c.need(
            "a launch with 2.1.1 and 2.2.0rc1 on the index opens",
            app.open(ctx.index.url("good")) is not None,
        ):
            return
        if not c.need("the page has loaded", app.wait_healthy() and app.page_ready()):
            return
        status, why = bridge_try(app, "update_status")
        note(f"update_status(): {status if status is not None else why}")
        latest = (status or {}).get("latest") if isinstance(status, dict) else None
        c.check(
            "index up: the newest final release, 2.1.1, is what the app learned",
            latest == NEW,
            why or f"latest {latest!r} (2.2.0rc1 is a pre-release, 2.1.2 is yanked)",
        )
        text = app.settings_text() or ""
        c.check(
            "index up: App settings names 2.1.1 and neither 2.2.0rc1 nor 2.1.2",
            NEW in text and PRE not in text and YANKED not in text,
            re.sub(r"\s+", " ", text)[:300],
        )
        button = app.update_button()
        c.check(
            "index up: the Update button names 2.1.1", bool(button) and NEW in button, repr(button)
        )
        app.cleanup()

        for label, url in (
            ("refusing", ctx.refused),
            ("silent", f"http://127.0.0.1:{ctx.silent.port}/simple/"),
        ):
            forget_check()
            hwnd = app.open(url)
            c.check(f"index {label}: the window opens", hwnd is not None)
            took = app.loaded_in() if hwnd is not None else None
            c.check(
                f"index {label}: the app loads within {LAUNCH_EXTRA_LIMIT:.0f} s of the baseline",
                took is not None and took - baseline < LAUNCH_EXTRA_LIMIT,
                f"{took if took is None else round(took, 1)} s against {baseline:.1f} s",
            )
            c.check(
                f"index {label}: it loads on the installed 2.1.0",
                took is not None and app.health() is not None and installed() == OLD,
                installed(),
            )
            shown = app.body_text() + "\n" + (app.settings_text() or "")
            status, _ = bridge_try(app, "update_status")
            message = (status or {}).get("message", "") if isinstance(status, dict) else ""
            error = re.search(
                r"(update|pypi|index|version)[^\n]{0,60}(fail|error|unreachable|could not|timed out)"
                r"|(fail|error|unreachable|could not|timed out)[^\n]{0,60}(update|pypi|index)",
                shown + "\n" + (message or ""),
                re.I,
            )
            c.check(
                f"index {label}: no error is shown", error is None, error.group(0) if error else ""
            )
            app.cleanup()
    finally:
        app.cleanup()


def step_idle(ctx: Ctx) -> None:
    c = CRITS["c-launch-updates-idle"]
    install_release(ctx.wheels, OLD)
    set_auto_file(None)
    app = ctx.app("idle")
    try:
        # A first launch with nothing newer gives the profile its database, as an operator's has.
        if not c.need(
            "a first launch on 2.1.0 opens (index with nothing newer)",
            app.open(ctx.index.url("base")) is not None,
        ):
            return
        c.need("its Hub answers", app.wait_healthy())
        app.cleanup()
        if not c.need(
            "nothing is running (the Hub stopped, the port free)",
            d.port_free(app.port) and not app.hub_pids(),
        ):
            return
        before = backups()
        watch = d.ConsoleWatch(lambda: app.pids).start()
        try:
            hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
            healthy = hwnd is not None and app.wait_healthy()
            at_open = app.version()
            time.sleep(3.0)
        finally:
            watch.stop()
        if not c.need("the launch opens a window", hwnd is not None):
            return
        c.check(
            "the window opens on 2.1.1 (GET /health when it appears)",
            healthy and at_open == NEW,
            f"version {at_open!r}",
        )
        c.check(
            "the scratch install is now 2.1.1",
            installed() == NEW and installed("agentweave-ai") == NEW,
            installed(),
        )
        c.check(
            "a copy of the database was kept in update-backups",
            len(backups()) > len(before),
            f"{len(before)} -> {len(backups())}",
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


def step_auto_off(ctx: Ctx) -> None:
    c = CRITS["c-auto-off"]
    install_release(ctx.wheels, OLD)
    set_auto_file(None)
    app = ctx.app("autooff")
    try:
        if not c.need(
            "the app opens on 2.1.0 (index with nothing newer)",
            app.open(ctx.index.url("base")) is not None,
        ):
            return
        if not c.need("the page has loaded", app.wait_healthy() and app.page_ready()):
            return
        text = app.settings_text() or ""
        c.check(
            "App settings offers 'Update automatically when I open AgentWeave'",
            "Update automatically when I open AgentWeave" in text,
            re.sub(r"\s+", " ", text)[:300],
        )
        done, why = bridge_try(app, "set_auto_update", False)
        c.check(
            "the setting is turned off through the window (set_auto_update(false))",
            not why,
            why or repr(done),
        )
        c.check("update.json records it off", auto_file() is False, repr(auto_file()))
        app.cleanup()

        hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        if not c.need(
            "the launch with 2.1.1 published opens", hwnd is not None and app.wait_healthy()
        ):
            return
        c.check(
            "the window opens on 2.1.0 (GET /health)", app.version() == OLD, repr(app.version())
        )
        c.check("nothing was upgraded (the install is 2.1.0)", installed() == OLD, installed())
        app.page_ready()
        # The button reads update_status() through the bridge once the page is up: allow it that.
        wait_for(lambda: app.update_button(), 15, 1.0)
        button = app.update_button()
        c.check("the Update button names 2.1.1", bool(button) and NEW in button, repr(button))
        app.cleanup()

        hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        if not c.need("a further launch opens", hwnd is not None and app.wait_healthy()):
            return
        app.page_ready()
        status, why = bridge_try(app, "update_status")
        c.check(
            "after a further launch the setting is still off (update_status, update.json)",
            isinstance(status, dict) and status.get("auto") is False and auto_file() is False,
            why
            or f"update_status auto {(status or {}).get('auto')!r}, update.json {auto_file()!r}",
        )
        c.check(
            "and it is still 2.1.0",
            app.version() == OLD and installed() == OLD,
            f"{app.version()!r}, {installed()}",
        )
    finally:
        app.cleanup()


def step_busy(ctx: Ctx) -> None:
    cn, cb = CRITS["c-never-interrupts"], CRITS["c-button-names-work"]
    install_release(ctx.wheels, OLD)
    set_auto_file(False)  # the first launch must not apply before the turn starts
    app = ctx.app("busy")
    try:
        hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        ok = hwnd is not None and app.wait_healthy() and app.page_ready()
        for c in (cn, cb):
            c.need("2.1.0 is running with its window open", ok and installed() == OLD, installed())
        if not ok:
            return
        run_id, why = d.start_turn(app)
        running = bool(run_id) and bool(
            wait_for(lambda: d.run_status(app, run_id) == "running", 90, 1.0)
        )
        for c in (cn, cb):
            c.need(
                "a real Haiku turn is in progress",
                running,
                why or f"{run_id} {run_id and d.run_status(app, run_id)}",
            )
        if not running:
            return
        hub = app.hub_pids()
        set_auto_file(True)  # automatic updating on, as by default: the case that must hold back
        second = app.launch(ctx.index.url("good"))
        wait_for(lambda: second.poll() is not None, 60, 0.5)
        time.sleep(3.0)
        cn.check(
            "after a second launch the Hub process id is unchanged",
            app.hub_pids() == hub and bool(hub),
            f"{hub} -> {app.hub_pids()}",
        )
        cn.check(
            "after a second launch the turn is unchanged (running)",
            d.run_status(app, run_id) == "running",
            d.run_status(app, run_id),
        )
        cn.check(
            "the Hub still reports 2.1.0 (GET /health)", app.version() == OLD, repr(app.version())
        )
        cn.check("nothing was upgraded (the install is 2.1.0)", installed() == OLD, installed())
        button = app.update_button()
        cn.check("the Update button is shown", bool(button) and NEW in button, repr(button))

        cb.check("the Update button is shown while the turn runs", bool(button), repr(button))
        answer, why = bridge_try(app, "apply_update", False)
        note(f"apply_update(false) with a turn running: {answer if answer is not None else why}")
        answer = answer if isinstance(answer, dict) else {}
        cb.check(
            "pressed with a turn running, it asks first (state needs_confirm)",
            answer.get("state") == "needs_confirm",
            why or repr(answer),
        )
        cb.check(
            "the prompt names the running turn ('1 agent turn')",
            bool(re.search(r"\b1 agent turn\b", answer.get("detail") or "")),
            repr(answer.get("detail")),
        )
        time.sleep(5.0)  # the operator cancels: nothing is applied
        cb.check(
            "after cancel nothing changed: same Hub, 2.1.0, the turn running",
            app.hub_pids() == hub
            and app.version() == OLD
            and installed() == OLD
            and d.run_status(app, run_id) == "running",
            f"{app.hub_pids()} {app.version()!r} {installed()} {d.run_status(app, run_id)}",
        )
        why = app.fire("apply_update", True)
        cb.check("pressed and confirmed, the update starts (apply_update(true))", not why, why)
        cb.check(
            "confirmed, the update applies: the Hub reports 2.1.1",
            wait_version(app, NEW, APPLY_LIMIT),
            repr(app.version()),
        )
        cb.check("and the install is 2.1.1", installed() == NEW, installed())
    finally:
        app.cleanup()


def step_after_work(ctx: Ctx) -> None:
    c = CRITS["c-after-work-ends"]
    install_release(ctx.wheels, OLD)
    set_auto_file(
        False
    )  # work is running at the launch in the criterion; held back by the setting here
    app = ctx.app("afterwork")
    try:
        hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        if not c.need(
            "2.1.0 opens with its window",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        time.sleep(2.0)
        c.need("the window is maximized", bool(user32.IsZoomed(hwnd)))
        run_id, why = d.start_turn(app)
        running = bool(run_id) and bool(
            wait_for(lambda: d.run_status(app, run_id) == "running", 90, 1.0)
        )
        if not c.need("a real Haiku turn is in progress", running, why or str(run_id)):
            return
        wait_for(lambda: app.update_button(), 15, 1.0)  # update_status() through the bridge
        button = app.update_button()
        c.check("the Update button is shown while the work runs", bool(button), repr(button))
        ended = wait_for(
            lambda: d.run_status(app, run_id) not in ("running", "pending", "queued"), 330, 3.0
        )
        if not c.need("the work ends", bool(ended), d.run_status(app, run_id)):
            return
        projects, runs = ids(app, "projects"), ids(app, "runs")
        zoomed, where = bool(user32.IsZoomed(hwnd)), rect(hwnd)
        launcher = sorted(app.pids)
        note(
            f"before: {len(projects)} project(s), {len(runs)} run(s), maximized {zoomed}, rect {where}"
        )
        why = app.fire("apply_update", False)
        c.check("pressed with nothing running, the update starts at once", not why, why)
        c.check("the Hub reports 2.1.1", wait_version(app, NEW, APPLY_LIMIT), repr(app.version()))
        c.check(
            "the same window is open (same handle, same launcher)",
            bool(user32.IsWindow(hwnd)) and sorted(app.pids) == launcher,
        )
        c.check("the page loads again", app.page_ready())
        c.check("the window is still maximized", bool(user32.IsZoomed(hwnd)) == zoomed and zoomed)
        c.check(
            "the window has the same size and place",
            rect(hwnd) == where,
            f"{where} -> {rect(hwnd)}",
        )
        geometry = HUB_DIR / "app-window" / f"window-{app.port}.json"
        note(f"geometry file: {geometry.read_text('utf-8') if geometry.exists() else 'absent'}")
        c.check(
            "the projects and history that were there still are",
            bool(projects) and projects <= ids(app, "projects") and runs <= ids(app, "runs"),
            f"projects {len(projects)} -> {len(ids(app, 'projects'))}, runs {len(runs)} -> {len(ids(app, 'runs'))}",
        )
    finally:
        app.cleanup()


def step_migration(ctx: Ctx) -> None:
    c = CRITS["c-migration-failure"]
    install_release(ctx.wheels, OLD)
    set_auto_file(False)
    app = ctx.app("migration")
    try:
        hwnd = app.open(ctx.index.url("fail"), timeout=APPLY_LIMIT)
        if not c.need(
            "2.1.0 opens with its window (the failing 2.1.1 published)",
            hwnd is not None and app.wait_healthy() and app.page_ready(),
        ):
            return
        before = stable_dump(app.db_path)
        copies = backups()
        hub = app.hub_pids()
        pids = set(app.pids)
        why = app.fire("apply_update", False)
        c.check("the update is applied (apply_update)", not why, why)
        went = wait_for(lambda: app.hub_pids() != hub, 120, 1.0)
        note(f"the Hub process changed: {bool(went)} ({hub} -> {app.hub_pids()})")
        stated = {"text": ""}

        def failure_stated() -> bool:
            if app.version() != OLD:
                return False
            status, _ = bridge_try(app, "update_status", timeout=10)
            message = (status or {}).get("message") if isinstance(status, dict) else None
            if isinstance(message, dict):  # the bridge answers {"state", "detail", "at"}
                message = f"{message.get('state', '')}: {message.get('detail', '')}"
            text = (message or "") + "\n" + app.body_text()
            found = re.search(r"[^\n]{0,80}fail[^\n]{0,120}", text, re.I)
            stated["text"] = found.group(0) if found else ""
            return bool(found)

        wait_for(failure_stated, APPLY_LIMIT, 3.0)
        c.check(
            "2.1.0 is installed again",
            installed() == OLD and installed("agentweave-ai") == OLD,
            installed(),
        )
        c.check("2.1.0 is running again (GET /health)", app.version() == OLD, repr(app.version()))
        c.check("the window states that the update failed", bool(stated["text"]), stated["text"])
        c.check(
            "without any prompt (no native dialog of the app's)",
            not native_boxes(pids),
            str(native_boxes(pids)),
        )
        after = stable_dump(app.db_path)
        newest = [p for p in backups() if p not in copies]
        copy = next(
            (f for p in newest for f in sorted(p.iterdir()) if f.is_file() and f.suffix == ".db"),
            None,
        )
        c.check(
            "a copy of the database was taken before (update-backups)",
            copy is not None,
            str(newest),
        )
        c.check(
            "the database equals the copy: schema, revision, projects, agents and runners",
            # Against the update's own copy, taken with the Hub stopped: the drive's snapshot of the
            # live Hub is a note only (it differed from the live database with no update applied).
            copy is not None and after == stable_dump(copy),
            f"drive's snapshot {before[:12]}, after {after[:12]},"
            f" copy {stable_dump(copy)[:12] if copy else None}",
        )
        c.check(
            "no trace of the failed migration's table",
            not has_table(app.db_path, "d1107_half_migrated"),
        )
    finally:
        app.cleanup()


def step_other_hub(ctx: Ctx) -> None:
    c = CRITS["c-other-hub"]
    install_release(ctx.wheels, OLD)
    set_auto_file(False)
    one, other = ctx.app("otherhub1", 0), ctx.app("otherhub2", 1)
    try:
        a = one.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        b = other.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        if not c.need(
            "two Hubs of the same install run on two ports, each with a window",
            a is not None
            and b is not None
            and one.wait_healthy()
            and other.wait_healthy()
            and one.page_ready(),
            f":{one.port} {a}, :{other.port} {b}",
        ):
            return
        hub = other.hub_pids()
        answer, why = bridge_try(one, "apply_update", True, timeout=60)
        note(f"apply_update(true) on :{one.port}: {answer if answer is not None else why}")
        answer = answer if isinstance(answer, dict) else {}
        c.check(
            f"the update names the other Hub (:{other.port}) and does not proceed (state blocked)",
            answer.get("state") == "blocked" and str(other.port) in (answer.get("detail") or ""),
            why or repr(answer),
        )
        time.sleep(15.0)
        c.check(
            "the other Hub keeps running untouched",
            other.hub_pids() == hub and bool(hub) and other.health() is not None,
            f"{hub} -> {other.hub_pids()}",
        )
        c.check(
            "and it waits: this Hub is still 2.1.0, nothing upgraded",
            one.version() == OLD and installed() == OLD,
            f"{one.version()!r}, {installed()}",
        )
    finally:
        one.cleanup()
        other.cleanup()


def step_concurrent(ctx: Ctx) -> None:
    c = CRITS["c-concurrent"]
    install_release(ctx.wheels, OLD)
    set_auto_file(None)
    app = ctx.app("concurrent")
    try:
        if not c.need("nothing is running", d.port_free(app.port) and not app.hub_pids()):
            return
        url = ctx.index.url("good")
        # Resolved once, before the clock starts: each resolution imports agentweave.cli in the
        # venv's Python, which alone takes longer than the 0.7 s the two launches may span.
        cmd = app.shortcut(url)
        ctx.index.reset()
        started = time.monotonic()
        app.launch(url, cmd)
        time.sleep(0.3)
        app.launch(url, cmd)
        if not c.need("two launches started within one second", time.monotonic() - started < 1.0):
            return
        wait_for(lambda: app.version() == NEW, APPLY_LIMIT, 2.0)
        wait_for(lambda: app.windows(), 60, 0.5)
        time.sleep(10.0)  # let a second window, or a second update, show itself
        ai = ctx.index.downloads(f"agentweave_ai-{NEW}-")
        hub = ctx.index.downloads(f"agentweave_hub-{NEW}-")
        c.check(
            "the index served each 2.1.1 package once",
            ai == 1 and hub == 1,
            f"agentweave-ai {ai}, agentweave-hub {hub}",
        )
        note(f"launchers' exit codes: {[p.poll() for p in app.launchers]}")
        windows = app.windows()
        c.check(
            "both launches resolve to one window", len(windows) == 1, f"{len(windows)} window(s)"
        )
        c.check("one Hub process serves the port", len(app.hub_pids()) == 1, str(app.hub_pids()))
        c.check(
            "it runs 2.1.1",
            app.version() == NEW and installed() == NEW,
            f"{app.version()!r}, {installed()}",
        )
    finally:
        app.cleanup()


def step_checkout(ctx: Ctx) -> None:
    c = CRITS["c-checkout"]
    src = stage(OLD)
    pip(
        "install",
        "--force-reinstall",
        "--no-deps",
        "--no-build-isolation",
        "-e",
        src / "hub",
        "-e",
        src / "ai",
    )
    set_auto_file(None)
    app = ctx.app("checkout")
    try:
        if not c.need(
            "the install is editable, 2.1.0",
            editable() and installed() == OLD,
            f"{installed()}, editable {editable()}",
        ):
            return
        ctx.index.reset()
        copies = backups()
        hwnd = app.open(ctx.index.url("good"), timeout=APPLY_LIMIT)
        if not c.need(
            "the app opens", hwnd is not None and app.wait_healthy() and app.page_ready()
        ):
            return
        health = app.health() or {}
        note(f"/health: {health}")
        c.check(
            "the version shows: GET /health names 2.1.0",
            health.get("version") == OLD,
            json.dumps(health),
        )
        c.check(
            "GET /health names the install as not a pip release",
            health.get("install") in ("editable", "checkout"),
            repr(health.get("install")),
        )
        text = app.settings_text() or ""
        c.check("App settings shows the version", OLD in text, re.sub(r"\s+", " ", text)[:300])
        c.check("no Update button", app.update_button() is None, repr(app.update_button()))
        time.sleep(20.0)
        c.check(
            "no automatic upgrade: still editable 2.1.0, no 2.1.1 fetched, no database copy",
            editable()
            and installed() == OLD
            and ctx.index.downloads(f"agentweave_hub-{NEW}-") == 0
            and backups() == copies,
            f"{installed()}, editable {editable()}, fetched {ctx.index.downloads(f'agentweave_hub-{NEW}-')}",
        )
    finally:
        app.cleanup()


STEPS = {
    "version": step_version,
    "newer": step_newer,
    "idle": step_idle,
    "auto-off": step_auto_off,
    "busy": step_busy,
    "after-work": step_after_work,
    "migration": step_migration,
    "other-hub": step_other_hub,
    "concurrent": step_concurrent,
    "checkout": step_checkout,  # last: it leaves the install editable
}


class SavedShortcut:
    """The Start-menu shortcut as the drive found it: a scratch launch rewrites it to the venv."""

    def __init__(self):
        sys.path.insert(0, str(ROOT / "src"))
        from agentweave.notifier import start_menu_shortcut

        self.path = start_menu_shortcut()
        self.data = self.path.read_bytes() if self.path and self.path.exists() else None

    def restore(self) -> None:
        if self.path is None:
            return
        if self.data is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_bytes(self.data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8190, help="first of two scratch ports")
    parser.add_argument("--cdp", type=int, default=9346, help="first of two DevTools ports")
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
    link, shortcut = w.SavedLink(), SavedShortcut()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    make_home()
    index = None
    try:
        ensure_venv(opts.fresh_venv)
        wheels = {v: build(v) for v in (OLD, NEW, YANKED, PRE)}
        failing = build(NEW, fail=True)
        install_dependencies(wheels)
        index = Index(
            {
                "base": [(wheels[OLD], False)],
                "good": [
                    (wheels[OLD], False),
                    (wheels[NEW], False),
                    (wheels[YANKED], True),
                    (wheels[PRE], False),
                ],
                "fail": [(wheels[OLD], False), (failing, False), (wheels[PRE], False)],
            }
        )
        silent = SilentPort()
        note(f"index on :{index.port}; silent :{silent.port}; scratch home {HOME}")
        ctx = Ctx(wheels, index, silent, refusing_url(), ports, cdps)
        for name in chosen:
            print(f"\n=== {name}", flush=True)
            try:
                STEPS[name](ctx)
            except Exception as exc:  # a step that breaks is reported, and the next one runs
                d.check(f"{name}: the step ran to its end", False, f"{type(exc).__name__}: {exc}")
    finally:
        kill_venv_processes()
        link.restore()
        shortcut.restore()
        if index is not None:
            index.server.shutdown()
        if unlink_home():
            shutil.rmtree(SCRATCH, onerror=_writable_then)
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
