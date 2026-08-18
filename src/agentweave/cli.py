#!/usr/bin/env python3
"""Command-line interface for AgentWeave."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, List, Optional

from . import __version__
from .utils import load_dotenv, print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)


def _emit_diagnostic_log(result: object) -> None:
    """Emit one diagnostic result through the existing structured logging path."""
    if not hasattr(result, "to_dict"):
        return
    data = result.to_dict()  # type: ignore[attr-defined]
    event = "diagnostic_check_failed" if data.get("status") == "fail" else "diagnostic_check_warn"
    if data.get("status") not in ("fail", "warn"):
        return
    log_fn = logger.error if data.get("status") == "fail" else logger.warning
    log_fn(event, extra={"event": event, "data": data})


def _emit_nonfatal_diagnostic(
    step: str, message: str, *, hint: Optional[str] = None, severity: str = "warn"
) -> None:
    event = "diagnostic_check_failed" if severity == "error" else "diagnostic_check_warn"
    log_fn = logger.error if severity == "error" else logger.warning
    data = {
        "id": f"{step}_failed",
        "target": step,
        "status": "fail" if severity == "error" else "warn",
        "severity": severity,
        "message": message,
        "category": "setup",
    }
    if hint:
        data["hint"] = hint
    log_fn(event, extra={"event": event, "data": data})


def _print_readiness_summary(results: List[Any], *, title: str = "[READINESS]") -> None:
    from .diagnostics import format_results, summarize

    summary = summarize(results)
    print()
    print(title)
    print(
        f"  pass: {summary.get('pass', 0)}  warn: {summary.get('warn', 0)}  fail: {summary.get('fail', 0)}"
    )
    rendered = format_results([r for r in results if getattr(r, "status", "") != "pass"])
    if rendered:
        print(rendered)
    else:
        print_success("No readiness problems detected.")


def cmd_status(args: argparse.Namespace) -> int:
    """Report whether the Hub-owned runtime is running, on what port, and against which project."""
    import urllib.error as _uerr
    import urllib.request as _req

    port = getattr(args, "port", None)
    profile = getattr(args, "profile", "default")
    port_error = _hub_require_port_for_named_profile(profile, port)
    if port_error:
        print_error(port_error)
        return 1
    port = port if port is not None else DEFAULT_HUB_PORT
    hub_url = _hub_url(port)
    health_url = _hub_health_url(port)

    # Check native PID first
    pid = _hub_pid_running(port=port, profile=profile)
    mode_label = "native" if pid is not None else "docker"

    try:
        with _req.urlopen(health_url, timeout=5) as resp:
            if resp.status == 200:
                print(f"[HUB] Status: running ({mode_label})")
                print(f"   URL:    {hub_url}")
                projects = _hub_project_status_summary(port)
                if projects:
                    print(f"   Projects: {projects}")
                if pid is not None:
                    print(f"   PID:    {pid}")
                with contextlib.suppress(ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    body = json.loads(resp.read().decode("utf-8"))
                    if body.get("ui_stale"):
                        print_warning(f"   {body.get('ui_stale_detail', 'UI bundle is stale.')}")
                return 0
    except _uerr.HTTPError as exc:
        print(f"[HUB] Status: error (HTTP {exc.code})")
        return 1
    except Exception:
        pass

    print("[HUB] Status: stopped")
    print("       Run 'agentweave' to start it")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run runtime readiness diagnostics."""
    import json as _json

    from .diagnostics import collect_diagnostics, format_results, has_failures, summarize

    results = collect_diagnostics(include_network=not getattr(args, "no_network", False))
    if getattr(args, "json", False):
        payload = {
            "summary": summarize(results),
            "results": [result.to_dict() for result in results],
        }
        print(_json.dumps(payload, indent=2))
    else:
        summary = summarize(results)
        print("[DOCTOR] AgentWeave runtime diagnostics")
        print(
            f"         pass: {summary.get('pass', 0)}  "
            f"warn: {summary.get('warn', 0)}  fail: {summary.get('fail', 0)}"
        )
        print()
        print(format_results(results))

    for result in results:
        _emit_diagnostic_log(result)
    return 1 if has_failures(results) else 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop a running Hub-owned runtime instance (native process or Docker container)."""
    import subprocess as _sp

    port = getattr(args, "port", None)
    profile = getattr(args, "profile", "default")
    port_error = _hub_require_port_for_named_profile(profile, port)
    if port_error:
        print_error(port_error)
        return 1
    port = port if port is not None else DEFAULT_HUB_PORT
    local = getattr(args, "local", False)

    # --- Native mode: check PID file first ---
    pid = _hub_pid_running(port=port, profile=profile)
    if pid is not None:
        if _hub_native_confirmed(port):
            print_info(f"Stopping Hub (native, PID {pid})...")
            _hub_kill_pid(pid)
            with contextlib.suppress(OSError):
                _hub_pid_file(port, profile).unlink()
            print_success("Hub stopped")
            return 0
        # PID is alive but nothing is serving the Hub on the recorded port — most
        # likely a recycled PID owned by an unrelated process. Never kill it; just
        # discard the stale PID file and fall through to the Docker check.
        with contextlib.suppress(OSError):
            _hub_pid_file(port, profile).unlink()

    # --- Docker mode ---
    import urllib.request as _req

    health_url = _hub_health_url(port)

    # Check if Hub is running at all
    try:
        with _req.urlopen(health_url, timeout=2) as resp:
            if resp.status != 200:
                print_info("Hub is not running")
                return 0
    except Exception:
        print_info("Hub is not running")
        return 0

    if local:
        compose_dir = Path.cwd() / "hub"
        if not (compose_dir / "docker-compose.yml").exists():
            print_error(f"Local hub not found: {compose_dir / 'docker-compose.yml'}")
            print_info("Run this command from the AgentWeave repository root.")
            return 1
    else:
        compose_file = HUB_DIR / "docker-compose.yml"
        if not HUB_DIR.exists() or not compose_file.exists():
            print_error(
                f"Hub is running on port {port} but no docker-compose.yml found at {HUB_DIR}."
            )
            print_info("If you started it with 'docker compose' manually, stop it with:")
            print_info("  docker compose down  (from the directory where you started it)")
            return 1
        compose_dir = HUB_DIR

    print_info("Stopping AgentWeave Hub...")
    env = os.environ.copy()
    env["AW_PORT"] = str(port)
    result = _sp.run(
        ["docker", "compose", "down"],
        cwd=compose_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        print_error(f"Failed to stop Hub: {result.stderr}")
        return 1

    print_success("Hub stopped")
    return 0


HUB_DIR = Path.home() / ".agentweave" / "hub"
# The port every command falls back to. Named here because the PID file's name depends on
# whether a start is on this port or another one — see `_hub_pid_file`.
DEFAULT_HUB_PORT = 8000
HUB_COMPOSE_URL = (
    "https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml"
)
HUB_ENV_URL = "https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example"
# Optional SHA256 sidecar URLs. Operators may publish these alongside the
# files in hub/ to enable integrity verification. When unset (None), the
# download proceeds without verification and a WARN is logged. (S9.)
HUB_COMPOSE_SHA256_URL: Optional[str] = None
HUB_ENV_SHA256_URL: Optional[str] = None


def _hub_url(port: int = 8000) -> str:
    """Get the Hub base URL for a given port."""
    return f"http://localhost:{port}"


def _hub_health_url(port: int = 8000) -> str:
    """Get the Hub health endpoint URL for a given port."""
    return f"{_hub_url(port)}/health"


def _hub_setup_token_url(port: int = 8000) -> str:
    """Get the Hub setup token endpoint URL for a given port."""
    return f"{_hub_url(port)}/api/v1/setup/token"


def _hub_projects_url(port: int = 8000) -> str:
    """Get the Hub project-collection endpoint URL for a given port."""
    return f"{_hub_url(port)}/api/v1/projects"


def _hub_open_project(port: int, directory: Path, token: Optional[str]) -> Optional[dict]:
    """Register/select `directory` as a project via POST /api/v1/projects/open.

    Returns the project summary dict on success, or None on any failure (missing
    token, network error, or Hub-side rejection) — the caller must treat this as
    non-fatal and fall back to opening the bare Hub URL.
    """
    import json as _json
    import urllib.request as _req

    if not token:
        return None
    body = _json.dumps({"path": str(directory)}).encode("utf-8")
    request = _req.Request(
        f"{_hub_projects_url(port)}/open",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with _req.urlopen(request, timeout=10) as resp:
            return _json.loads(resp.read())
    except Exception:
        return None


def _hub_project_app_url(port: int, project: Optional[dict]) -> str:
    """Return the app URL to open: project-scoped if `project` resolved, else bare."""
    if project and project.get("id"):
        return f"{_hub_url(port)}/?project={project['id']}&view=overview"
    return _hub_url(port)


def _hub_resolve_launch_url(port: int, cwd: Optional[Path]) -> str:
    """Open/register `cwd` as a project (after health) and return the launch URL.

    Non-fatal by design: a Hub that is slow, unauthenticated, or offline for this
    one call must not block the app from opening — it just opens without a project
    selected, matching a directly started Hub with zero registered projects.
    """
    if cwd is None:
        return _hub_url(port)
    project = _hub_open_project(port, cwd, _fetch_setup_token(port))
    if project is None:
        print_warning("Could not open the current directory as a project; opening Hub without one.")
        return _hub_url(port)
    print_info(f"Project: {project.get('name')} ({project.get('id')})")
    return _hub_project_app_url(port, project)


def _hub_project_status_summary(port: int) -> Optional[str]:
    """Fetch live project-collection state for `status`: count and most recent."""
    import json as _json
    import urllib.request as _req

    token = _fetch_setup_token(port)
    if not token:
        return None
    request = _req.Request(_hub_projects_url(port), headers={"Authorization": f"Bearer {token}"})
    try:
        with _req.urlopen(request, timeout=5) as resp:
            projects = _json.loads(resp.read())
    except Exception:
        return None
    if not projects:
        return "0 registered"
    most_recent = projects[0]
    label = most_recent.get("name") or most_recent.get("id")
    return f"{len(projects)} registered (most recent: {label})"


def _docker_available() -> bool:
    """Check if Docker and docker compose are available."""
    if not shutil.which("docker"):
        return False
    # Check for docker compose (v2) or docker-compose (v1). CREATE_NO_WINDOW keeps this
    # silent probe from flashing a console on Windows -- see cli.py:866's DETACHED_PROCESS
    # for the same reasoning applied to the long-lived Hub spawn. Hardcoded rather than
    # `subprocess.CREATE_NO_WINDOW` because that attribute doesn't exist in typeshed's
    # non-Windows stubs -- mypy fails the attr-defined check even under the platform guard,
    # same as DETACHED_PROCESS/CREATE_NEW_PROCESS_GROUP below.
    CREATE_NO_WINDOW = 0x08000000  # noqa: N806
    creationflags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        timeout=10,
        creationflags=creationflags,
    )
    if result.returncode == 0:
        return True
    # Fallback to docker-compose
    return bool(shutil.which("docker-compose"))


def _hub_health_check(port: int = 8000, timeout: int = 120) -> bool:
    """Poll Hub health endpoint until it responds or timeout."""
    import time as _time

    start = _time.time()
    while _time.time() - start < timeout:
        try:
            with urllib.request.urlopen(_hub_health_url(port), timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        _time.sleep(1)
    return False


def _fetch_setup_token(port: int = 8000) -> Optional[str]:
    """Fetch the API key from Hub's /setup/token endpoint (localhost only)."""
    import json as _json
    import urllib.request as _req

    try:
        with _req.urlopen(_hub_setup_token_url(port), timeout=5) as resp:
            data = _json.loads(resp.read())
            return data.get("api_key")
    except Exception:
        return None


def _download_with_sha256(
    url: str,
    dest: Path,
    sha256_url: Optional[str] = None,
    expected_sha256: Optional[str] = None,
) -> bool:
    """Download a file with optional SHA256 verification (S9).

    Behavior:
    - If sha256_url is None (and expected_sha256 is None), the file is
      downloaded without verification. This is the current default.
    - If sha256_url is set, the sidecar is downloaded, the file's SHA256
      is computed, and they are compared. A mismatch fails loud: the
      file is removed and False is returned.
    - If sha256_url is set but the sidecar fetch fails (network or
      missing file), a WARN is logged and the download proceeds
      unverified. This lets operators adopt sidecar files
      incrementally.
    - expected_sha256 may be passed as a constant fallback when the
      sidecar is unavailable. If both are provided, the sidecar wins.

    Returns True on success (verified or unverified). False on
    verification failure.
    """
    import hashlib
    import urllib.error as _uerr
    import urllib.request as _req

    try:
        _req.urlretrieve(url, dest)
    except Exception as exc:
        print_error(f"Failed to download {url}: {exc}")
        return False

    actual_sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    expected: Optional[str] = None

    if sha256_url:
        try:
            with _req.urlopen(sha256_url, timeout=10) as resp:
                expected = resp.read().decode("utf-8", errors="replace").strip().split()[0]
        except (_uerr.HTTPError, _uerr.URLError, OSError):
            print_warning(
                f"Could not fetch SHA256 sidecar {sha256_url}; " f"proceeding without verification."
            )
        except Exception as exc:
            print_warning(f"Unexpected error fetching SHA256 sidecar: {exc}")

    if expected is None and expected_sha256:
        expected = expected_sha256

    if expected is None:
        # No verification possible — log and accept
        print_warning(
            f"No SHA256 sidecar available for {url}; "
            f"downloaded file is not verified. (sha256={actual_sha})"
        )
        return True

    if actual_sha != expected.lower():
        print_error(
            f"SHA256 mismatch for {url}:\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual_sha}\n"
            f"Removing untrusted file {dest}."
        )
        with contextlib.suppress(OSError):
            dest.unlink()
        return False

    return True


def _hub_pid_file(port: Optional[int] = None, profile: str = "default") -> Path:
    """Return the path to the native Hub PID file for `port` and `profile`.

    Per-port, because one machine can legitimately run more than one Hub: the instance you
    work in, and a throwaway one on another port and another `DATABASE_URL` that you test
    against. With a single shared `hub.pid` the second start overwrote the first's record,
    which left `stop` and `status` blind to whichever instance started earlier — the process
    kept running with nothing tracking it.

    `DEFAULT_HUB_PORT` keeps the historic unsuffixed name, so a Hub already running from an
    older build is still found, reported and stopped by this one. A named profile always gets
    `hub-<profile>-<port>.pid`, even at `DEFAULT_HUB_PORT`, so its filename alone identifies
    which profile it belongs to and it can never collide with the default profile's file at the
    same port (`design.md` D6).
    """
    if profile and profile != "default":
        resolved_port = port if port is not None else DEFAULT_HUB_PORT
        return HUB_DIR / f"hub-{profile}-{resolved_port}.pid"
    if port is None or port == DEFAULT_HUB_PORT:
        return HUB_DIR / "hub.pid"
    return HUB_DIR / f"hub-{port}.pid"


def _hub_pid_running(port: Optional[int] = None, profile: str = "default") -> Optional[int]:
    """Return the PID from the port's/profile's PID file if the process is alive, else None.

    If port is given, only returns the PID if the native process was started on that port.
    Removes a stale PID file if the process is no longer running.
    """
    pid_file = _hub_pid_file(port, profile)
    if not pid_file.exists():
        return None
    try:
        content = pid_file.read_text().strip().splitlines()
        pid = int(content[0])
        file_port = int(content[1]) if len(content) > 1 else None
    except (ValueError, OSError, IndexError):
        with contextlib.suppress(OSError):
            pid_file.unlink()
        return None

    # If a specific port was requested, only match if it's the same port
    if port is not None and file_port is not None and file_port != port:
        return None

    # Check if process is alive (cross-platform)
    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle == 0:
                raise OSError("no such process")
            kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
        return pid
    except (ProcessLookupError, OSError):
        with contextlib.suppress(OSError):
            pid_file.unlink()
        return None


def _hub_kill_pid(pid: int) -> None:
    """Terminate a native Hub process by PID (graceful SIGTERM, then forced)."""
    import subprocess as _sp
    import time as _time

    try:
        if sys.platform == "win32":
            _sp.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15)
        else:
            os.kill(pid, 15)  # SIGTERM
            for _ in range(10):
                _time.sleep(1)
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, OSError):
                    break
            else:
                os.kill(pid, 9)  # SIGKILL fallback
    except (ProcessLookupError, OSError):
        pass


def _hub_native_confirmed(port: int) -> bool:
    """Return True if a Hub health endpoint actually responds on ``port``.

    Called before force-killing a PID read from hub.pid: after an OS PID recycle
    the stored PID may belong to an unrelated process. Confirming the Hub is
    genuinely serving on the recorded port prevents killing a bystander process.
    """
    import urllib.request as _req

    try:
        with _req.urlopen(_hub_health_url(port), timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _hub_profile_data_dir(profile: str = "default") -> Path:
    """Return the data directory for a Hub profile (`design.md` D6).

    The default profile keeps its historic path (`HUB_DIR/data`) untouched; a named profile
    gets its own directory under `HUB_DIR/profiles/<name>`, so two profiles' databases can
    never collide with each other or with the default profile's.
    """
    if profile and profile != "default":
        return HUB_DIR / "profiles" / profile
    return HUB_DIR / "data"


def _hub_require_port_for_named_profile(profile: str, port: Optional[int]) -> Optional[str]:
    """Return an error message if a named profile was given without an explicit `--port`.

    `--port` defaults to `None` on every subparser that carries it (not `DEFAULT_HUB_PORT`)
    specifically so this check can distinguish "not passed" from "passed and happens to equal
    8000" — a plain `default=8000` cannot tell the two apart. A named profile silently falling
    back to `DEFAULT_HUB_PORT` would bind the same port the default profile normally uses;
    profile-namespaced database and PID-file paths do nothing to prevent that collision, because
    they namespace identity, not the socket (`design.md` D6, "Port"). The default profile is
    unaffected: `None` there resolves to `DEFAULT_HUB_PORT` with no error, exactly as before this
    check existed.
    """
    if profile and profile != "default" and port is None:
        return (
            f"--profile '{profile}' needs an explicit --port "
            f"(a named profile does not default to port {DEFAULT_HUB_PORT}, "
            "to avoid colliding with the default profile's instance)"
        )
    return None


def _hub_resolve_database_source(old_db_url: Optional[str], profile: str, db_path: Path) -> tuple:
    """Decide the effective `DATABASE_URL` and what (if anything) to tell the operator.

    An explicit `DATABASE_URL` always wins, unchanged from before profiles existed — `--profile`
    only computes a default database path, it does not add a second source of truth on top of an
    explicit override (`design.md` D6). Returns `(db_url, message_or_None)`; the message names
    which one took effect whenever a named profile is in play, so the two never silently disagree.
    """
    if old_db_url:
        message = None
        if profile and profile != "default":
            message = f"Using DATABASE_URL from environment (--profile '{profile}' ignored)"
        return old_db_url, message
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    message = None
    if profile and profile != "default":
        message = f"Using profile '{profile}' database at {db_path}"
    return db_url, message


def _hub_native_scaffold(data_dir: Path) -> tuple:
    """Scaffold ~/.agentweave/hub/ for native mode.

    Creates data dir and .env (with generated API key) if they don't exist.
    Returns (env_path, api_key, is_first_run).
    """
    import secrets as _secrets

    data_dir.mkdir(parents=True, exist_ok=True)
    env_path = HUB_DIR / ".env"
    is_first_run = not env_path.exists()
    api_key = None

    if is_first_run:
        api_key = f"aw_live_{_secrets.token_hex(16)}"
        db_path = data_dir / "agentweave.db"
        # Use forward slashes for the SQLite URL (required on Windows)
        db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        # No AW_BOOTSTRAP_PROJECT_ID/NAME here: a genuinely fresh native install starts
        # with zero registered projects (local-multi-project-workspace design decision
        # 6). The first post-health `open` call registers the invocation directory.
        env_content = (
            f"DATABASE_URL={db_url}\n"
            f"AW_BOOTSTRAP_API_KEY={api_key}\n"
            f"AW_TICKET_SECRET={_secrets.token_hex(32)}\n"
        )
        env_path.write_text(env_content, encoding="utf-8")
        # This file holds the bootstrap API key and ticket secret — restrict it to
        # the owner on POSIX (mirrors the 0600 handling of transport.json).
        if os.name != "nt":
            with contextlib.suppress(OSError):
                os.chmod(env_path, 0o600)

    return env_path, api_key, is_first_run


def _hub_run_migrations(hub_pkg_dir: Path) -> bool:
    """Run Alembic migrations using the installed hub package.

    Expects DATABASE_URL to already be set in os.environ before calling.
    """
    try:
        from alembic import command as _alembic_cmd
        from alembic.config import Config as _AlembicConfig
    except ImportError:
        print_error("alembic is not installed. Run: pip install agentweave-hub")
        return False

    migrations_dir = hub_pkg_dir / "migrations"
    if not migrations_dir.exists():
        print_error(
            f"Migrations not found at {migrations_dir}. "
            "Is agentweave-hub installed from a released wheel?"
        )
        return False

    try:
        cfg = _AlembicConfig()
        cfg.set_main_option("script_location", str(migrations_dir))
        # hub.config.settings reads DATABASE_URL from os.environ at import time;
        # we set it before importing hub.main so this is already correct.
        _alembic_cmd.upgrade(cfg, "head")
        return True
    except Exception as exc:
        print_error(f"Migration failed: {exc}")
        return False


def _hub_load_env_into(env: dict, env_path: Path) -> None:
    """Load KEY=VALUE lines from env_path into env dict (setdefault, no override)."""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    except OSError:
        pass


def _find_app_mode_browser() -> Optional[str]:
    """Locate an installed Chromium-based browser binary supporting `--app=<url>`.

    None of these ship on PATH from a standard installer on Windows/macOS, so this checks
    known install locations directly rather than relying solely on `shutil.which`.
    """
    candidates: List[str] = []
    if sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        relative_paths = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"Chromium\Application\chromium.exe",
        ]
        candidates.extend(str(Path(root) / rel) for root in roots if root for rel in relative_paths)
    elif sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    else:
        for name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "microsoft-edge",
        ):
            found = shutil.which(name)
            if found:
                candidates.append(found)

    return next((c for c in candidates if Path(c).exists()), None)


def _open_app_window(url: str) -> None:
    """Open `url` in a chromeless app-mode browser window; fall back to a normal tab."""
    browser = _find_app_mode_browser()
    if browser:
        try:
            subprocess.Popen(
                [browser, f"--app={url}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return
        except OSError:
            pass

    import webbrowser

    webbrowser.open(url)


def _app_icon_path() -> Optional[str]:
    """Absolute path to the packaged provisional AgentWeave mark, if the asset is
    present on disk. Both an editable install and a built wheel put it at
    agentweave/assets/icon.ico; returns None rather than raising if it is missing,
    so a stripped-down install still opens a window, just with pywebview's own
    fallback icon."""
    try:
        from importlib import resources

        icon = resources.files("agentweave").joinpath("assets", "icon.ico")
        if icon.is_file():
            return str(icon)
    except Exception:
        pass
    return None


def _set_windows_app_user_model_id() -> None:
    """On Windows, tell the shell this process is its own app rather than a
    fungible `python.exe`. Without this, `webview.start(icon=...)` still sets
    the *window's* icon (title bar, Alt-Tab), but the taskbar button keeps
    showing python.exe's own icon regardless -- confirmed empirically: the
    taskbar button only picks up the packaged mark once this is set before
    the window is created. No-op, and never raises, off Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AgentWeave.Hub")
    except Exception:
        pass


def _open_app_window_native(url: str) -> bool:
    """Open `url` in a native OS window via pywebview.

    Returns True if the pywebview path ran, False if pywebview is not installed
    or failed to open a window (caller falls back to `_open_app_window`).
    """
    try:
        import webview  # type: ignore[import]
    except ImportError:
        return False

    _set_windows_app_user_model_id()

    try:
        webview.create_window("AgentWeave", url)
        webview.start(icon=_app_icon_path())
        return True
    except Exception as exc:
        print_error(f"Native app window unavailable ({exc}); falling back to browser.")
        return False


def _wait_and_open_app(port: int, cwd: Optional[Path]) -> None:
    """Poll for Hub health, open/register `cwd`, then open the app-mode window.

    Runs off the main thread so a foreground (--no-detach) start can block on
    uvicorn while still opening the browser once the Hub answers healthy.
    """
    if _hub_health_check(port=port, timeout=60):
        _open_app_window(_hub_resolve_launch_url(port, cwd))


def _hub_native_start(
    port: int,
    detach: bool = True,
    app: bool = False,
    cwd: Optional[Path] = None,
    profile: str = "default",
) -> int:
    """Start the Hub natively using uvicorn (no Docker).

    Handles scaffolding, migrations, and process management.
    DATABASE_URL is set in os.environ BEFORE importing hub modules so that
    hub.config.settings picks up the correct absolute path at import time.
    """
    import importlib.util as _imp_util
    import subprocess as _sp
    import urllib.request as _req

    # 1. Check hub.main is available WITHOUT importing it yet
    if _imp_util.find_spec("hub.main") is None:
        print_error("agentweave-hub is not installed.")
        print_info("Install it with: pip install agentweave-hub")
        return 1

    # 2. Check if Hub is already running
    health_url = _hub_health_url(port)
    try:
        with _req.urlopen(health_url, timeout=2) as resp:
            if resp.status == 200:
                print_info(f"Hub is already running at {_hub_url(port)}")
                url = _hub_resolve_launch_url(port, cwd)
                if app:
                    print_info("Opening Hub in app mode...")
                    if not _open_app_window_native(url):
                        _open_app_window(url)
                return 0
    except Exception:
        pass

    # 3. Clean up stale PID
    _hub_pid_running(port=port, profile=profile)

    # 4. Compute db_url early — before any hub imports — so DATABASE_URL is set
    #    in os.environ before hub.config.settings is instantiated.
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    data_dir = _hub_profile_data_dir(profile)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "agentweave.db"

    # An explicit DATABASE_URL wins. This used to be overwritten unconditionally, which made
    # `--port` a trap: a second start got its own process and its own port but the *same*
    # database, so two SQLite writers shared one file and both instances showed one project
    # list. Honouring the variable is what lets one machine run an instance you work in and a
    # throwaway one you test against. Absent it, the path below is unchanged, so a plain
    # `agentweave` start still lands exactly where every existing install already has its data.
    _old_db_url = os.environ.get("DATABASE_URL")
    db_url, _db_source_message = _hub_resolve_database_source(_old_db_url, profile, db_path)
    if _db_source_message:
        print_info(_db_source_message)
    os.environ["DATABASE_URL"] = db_url

    try:
        # 5. Now safe to import hub (settings reads DATABASE_URL from env)
        try:
            import hub.main as _hub_main  # type: ignore[import]
        except ImportError:
            print_error("agentweave-hub is not installed.")
            print_info("Install it with: pip install agentweave-hub")
            return 1

        hub_pkg_dir = Path(_hub_main.__file__).parent

        # 6. Scaffold .env (creates it with the same db_url if first run)
        env_path, api_key, is_first_run = _hub_native_scaffold(data_dir)

        # 7. Run migrations
        print_info("Running database migrations...")
        if not _hub_run_migrations(hub_pkg_dir):
            return 1

        env = os.environ.copy()
        env["AW_PORT"] = str(port)
        _hub_load_env_into(env, env_path)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "hub.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        if detach:
            if sys.platform == "win32":
                DETACHED_PROCESS = 0x00000008  # noqa: N806
                CREATE_NEW_PROCESS_GROUP = 0x00000200  # noqa: N806
                proc = _sp.Popen(
                    cmd,
                    env=env,
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                )
            else:
                proc = _sp.Popen(
                    cmd,
                    env=env,
                    start_new_session=True,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                )

            _hub_pid_file(port, profile).write_text(f"{proc.pid}\n{port}", encoding="utf-8")
            print_info(f"Starting Hub (native, PID {proc.pid}) on port {port}...")

            if not _hub_health_check(port=port, timeout=60):
                print_error("Hub failed to start within 60 seconds")
                print_info(
                    f"Check that port {port} is not in use and agentweave-hub is installed correctly."
                )
                # Terminate the orphaned uvicorn process so it doesn't linger and
                # bind the port with no PID file left to track it.
                _hub_kill_pid(proc.pid)
                with contextlib.suppress(OSError):
                    _hub_pid_file(port, profile).unlink()
                return 1

            print_success(f"Hub ready at {_hub_url(port)}")
            if is_first_run and api_key:
                print_info(f"API key: {api_key}")
                print_info(f"(Saved to {HUB_DIR / '.env'})")
            url = _hub_resolve_launch_url(port, cwd)
            if app:
                print_info("Opening Hub in app mode...")
                if not _open_app_window_native(url):
                    _open_app_window(url)
        else:
            # Foreground mode — block until Ctrl+C
            if is_first_run and api_key:
                print_info(f"API key: {api_key}  (saved to {HUB_DIR / '.env'})")
            print_info(f"Starting Hub (native, foreground) on port {port} — press Ctrl+C to stop")
            if app:
                import threading

                threading.Thread(target=_wait_and_open_app, args=(port, cwd), daemon=True).start()
            try:
                import uvicorn  # type: ignore[import]

                uvicorn.run("hub.main:app", host="127.0.0.1", port=port)
            except ImportError:
                print_error("uvicorn is not installed. Run: pip install agentweave-hub")
                return 1
            except KeyboardInterrupt:
                print_info("Hub stopped.")

        return 0

    finally:
        # Restore original DATABASE_URL
        if _old_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = _old_db_url


def cmd_hub_start(args: argparse.Namespace) -> int:
    """Start the AgentWeave Hub."""
    port = getattr(args, "port", None)
    profile = getattr(args, "profile", "default")
    port_error = _hub_require_port_for_named_profile(profile, port)
    if port_error:
        print_error(port_error)
        return 1
    port = port if port is not None else DEFAULT_HUB_PORT
    local = getattr(args, "local", False)
    docker = getattr(args, "docker", False) or local
    no_detach = getattr(args, "no_detach", False)
    app = getattr(args, "app", False)

    if not docker:
        return _hub_native_start(
            port=port, detach=not no_detach, app=app, cwd=Path.cwd(), profile=profile
        )

    import subprocess as _sp
    import urllib.request as _req

    hub_url = _hub_url(port)
    health_url = _hub_health_url(port)

    if not _docker_available():
        print_error("Docker is not available")
        print_info("Please install Docker: https://docs.docker.com/get-docker/")
        print_info("Docker Desktop is recommended for Windows/Mac users.")
        print_info("Alternatively, run without --docker to start natively (no Docker needed).")
        return 1

    # Check if Hub is already running on this port
    try:
        with _req.urlopen(health_url, timeout=2) as resp:
            if resp.status == 200:
                print_info(f"Hub is already running at {hub_url}")
                if app:
                    print_info("Opening Hub in app mode...")
                    if not _open_app_window_native(hub_url):
                        _open_app_window(hub_url)
                return 0
    except Exception:
        pass

    if local:
        # Local dev mode: build and run from ./hub/ in the current directory
        local_hub_dir = Path.cwd() / "hub"
        compose_file = local_hub_dir / "docker-compose.yml"
        if not compose_file.exists():
            print_error(f"Local hub not found: {compose_file}")
            print_info("Run this command from the AgentWeave repository root.")
            return 1

        print_info(f"Building and starting Hub from {local_hub_dir} on port {port}...")
        env = os.environ.copy()
        env["AW_PORT"] = str(port)
        result = _sp.run(
            ["docker", "compose", "up", "--build", "-d"],
            cwd=local_hub_dir,
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
        )
        if result.returncode != 0:
            print_error(f"Failed to start Hub: {result.stderr}")
            return 1
    else:
        HUB_DIR.mkdir(parents=True, exist_ok=True)

        # Download docker-compose.yml if not present
        compose_file = HUB_DIR / "docker-compose.yml"
        if not compose_file.exists():
            print_info("Downloading Hub configuration...")
            if not _download_with_sha256(
                url=HUB_COMPOSE_URL,
                dest=compose_file,
                sha256_url=HUB_COMPOSE_SHA256_URL,
            ):
                return 1

        # Download .env if not present
        env_file = HUB_DIR / ".env"
        if not env_file.exists() and not _download_with_sha256(
            url=HUB_ENV_URL,
            dest=env_file,
            sha256_url=HUB_ENV_SHA256_URL,
        ):
            return 1

        # Update .env with custom port if needed
        if port != 8000:
            try:
                env_content = env_file.read_text(encoding="utf-8")
                # Replace or add HUB_HTTP_PORT
                if "HUB_HTTP_PORT=" in env_content:
                    env_content = env_content.replace("HUB_HTTP_PORT=8000", f"HUB_HTTP_PORT={port}")
                else:
                    env_content += f"\nHUB_HTTP_PORT={port}\n"
                env_file.write_text(env_content)
            except Exception as exc:
                print_warning(f"Could not update port in .env: {exc}")

        # Start the Hub
        print_info(f"Starting AgentWeave Hub on port {port}...")
        result = _sp.run(
            ["docker", "compose", "up", "-d"],
            cwd=HUB_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print_error(f"Failed to start Hub: {result.stderr}")
            return 1

    # Wait for Hub to be healthy
    print_info("Waiting for Hub to be ready (this may take a while for first build)...")
    if not _hub_health_check(port=port, timeout=120):
        print_error("Hub failed to start within 120 seconds")
        if local:
            print_info("Check logs with: docker compose -f hub/docker-compose.yml logs")
        else:
            print_info(
                "Check logs with: docker compose -f ~/.agentweave/hub/docker-compose.yml logs"
            )
        return 1

    print_success(f"Hub ready at {hub_url}")
    if app:
        print_info("Opening Hub in app mode...")
        if not _open_app_window_native(hub_url):
            _open_app_window(hub_url)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Destroy local Hub state for a clean slate — the escape hatch when something is wedged."""
    import shutil as _shutil

    yes = getattr(args, "yes", False)
    destroy_all = getattr(args, "all", False)
    profile = getattr(args, "profile", "default")

    # Without --profile, reset targets only the default profile's data/ directory, exactly as
    # before profiles existed — it does not enumerate or sweep profiles/. With --profile <name>,
    # it targets only that profile's directory, so reset's blast radius is always exactly one
    # profile, named or default, never inferred (`design.md` D6).
    data_dir = _hub_profile_data_dir(profile)
    env_path = HUB_DIR / ".env"
    pid_file = _hub_pid_file(profile=profile)

    if not data_dir.exists() and not env_path.exists() and not pid_file.exists():
        print_info("No Hub data found. Nothing to destroy.")
        return 0

    # Describe what will be deleted
    targets = [str(data_dir)]
    if destroy_all:
        targets.append(str(env_path))
        targets.append("any log files in " + str(HUB_DIR))

    if profile and profile != "default":
        print_warning(f"This will permanently delete the following Hub data (profile '{profile}'):")
    else:
        print_warning("This will permanently delete the following Hub data:")
    for t in targets:
        print(f"  - {t}")
    if not destroy_all:
        print_info("(Use --all to also remove the .env config and API key)")

    if not yes:
        try:
            answer = input("Type 'yes' to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            print_info("Destroy cancelled.")
            return 0
        if answer != "yes":
            print_info("Destroy cancelled.")
            return 0

    # Stop the Hub first if running
    pid = _hub_pid_running(profile=profile)
    if pid is not None:
        # Read the recorded port so we can confirm identity before killing.
        recorded_port: Optional[int] = None
        with contextlib.suppress(OSError, ValueError, IndexError):
            _content = pid_file.read_text().strip().splitlines()
            recorded_port = int(_content[1]) if len(_content) > 1 else None
        if recorded_port is not None and not _hub_native_confirmed(recorded_port):
            # Alive PID but no Hub serving on the recorded port — likely a recycled
            # PID owned by an unrelated process. Skip the kill; just clear the file.
            print_info("No running native Hub found (stale PID file removed).")
        else:
            print_info(f"Stopping Hub (native, PID {pid}) before destroy...")
            _hub_kill_pid(pid)
        with contextlib.suppress(OSError):
            pid_file.unlink()

    # Delete data directory
    if data_dir.exists():
        _shutil.rmtree(data_dir, ignore_errors=True)
        print_info(f"Deleted {data_dir}")

    # Always clean up PID file
    with contextlib.suppress(OSError):
        pid_file.unlink()

    if destroy_all:
        if env_path.exists():
            env_path.unlink()
            print_info(f"Deleted {env_path}")
        # Remove any *.log files in hub dir
        for log_file in HUB_DIR.glob("*.log"):
            with contextlib.suppress(OSError):
                log_file.unlink()
                print_info(f"Deleted {log_file}")

    print_success("Hub data destroyed. Run 'agentweave' to start fresh.")
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser.

    Single-runtime (`openspec/changes/single-runtime`): five commands total. Bare invocation is
    the primary entry point — equivalent to what used to be `hub start --app` — and is the only
    way to launch the app. `doctor`/`status`/`stop`/`reset` describe *app* lifecycle (is the one
    Hub-owned process up, on what port) rather than the removed watchdog's collaboration-session
    lifecycle.
    """
    parser = argparse.ArgumentParser(
        prog="agentweave",
        description="AgentWeave - the locally-installed multi-agent AI collaboration app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agentweave                 Launch the app (starts the Hub, opens the app window)
  agentweave doctor          Check environment readiness
  agentweave status          Check whether the Hub is running
  agentweave stop            Stop a running Hub instance
  agentweave reset           Destroy local Hub state and start clean

For more help: https://github.com/gutohuida/AgentWeave
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "Port to run the Hub on (default: 8000; required if --profile names a non-default "
            "profile)"
        ),
    )
    parser.add_argument(
        "--docker", action="store_true", help="Run the Hub via Docker instead of natively"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Docker dev mode: build and run from ./hub/ in the current directory",
    )
    parser.add_argument(
        "--no-detach",
        action="store_true",
        dest="no_detach",
        help="Run in the foreground instead of detaching",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help='Named Hub instance to use, isolated from the default one (default: "default")',
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    doctor_parser = subparsers.add_parser("doctor", help="Check environment readiness")
    doctor_parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON diagnostics"
    )
    doctor_parser.add_argument(
        "--no-network", action="store_true", help="Skip network reachability checks"
    )

    status_parser = subparsers.add_parser("status", help="Check whether the Hub is running")
    status_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to check (default: 8000; required if --profile names a non-default profile)",
    )
    status_parser.add_argument(
        "--profile", type=str, default="default", help="Named Hub instance to check"
    )

    stop_parser = subparsers.add_parser("stop", help="Stop a running Hub instance")
    stop_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to stop (default: 8000; required if --profile names a non-default profile)",
    )
    stop_parser.add_argument(
        "--local", action="store_true", help="Docker dev mode: stop the ./hub/ compose project"
    )
    stop_parser.add_argument(
        "--profile", type=str, default="default", help="Named Hub instance to stop"
    )

    reset_parser = subparsers.add_parser("reset", help="Destroy local Hub state and start clean")
    reset_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    reset_parser.add_argument(
        "--profile",
        type=str,
        default="default",
        help="Only destroy this named profile's data, not the default profile's",
    )
    reset_parser.add_argument(
        "--all", action="store_true", help="Also remove the .env config and API key"
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point."""
    # Load .env file before any command dispatch so all CLI commands benefit
    load_dotenv()

    # Ensure stdout/stderr handle Unicode (e.g. emoji in messages) on Windows
    import sys as _sys

    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(_sys.stderr, "reconfigure"):
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    from .logging_handlers import _configure_logging

    _configure_logging()

    parser = create_parser()
    parsed_args = parser.parse_args(args)

    try:
        if not parsed_args.command:
            # Bare invocation is the app's primary entry point: launch it, in app mode.
            parsed_args.app = True
            return cmd_hub_start(parsed_args)
        elif parsed_args.command == "doctor":
            return cmd_doctor(parsed_args)
        elif parsed_args.command == "status":
            return cmd_status(parsed_args)
        elif parsed_args.command == "stop":
            return cmd_stop(parsed_args)
        elif parsed_args.command == "reset":
            return cmd_reset(parsed_args)
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
