"""Finding Copilot's real executable, and reading its launchability from Copilot itself
(`a-copilot-agent-runs-over-acp`, design D2 and D15).

**D2: `copilot.exe`, never the npm shim.** npm installs `copilot.cmd`/`copilot.ps1`/`copilot`, a
*JS* shim (`node npm-loader.js`) that `pty_runner.resolve_executable` deliberately does not unwrap.
Running it costs two processes and orphans the real one when only `node` is killed, so the platform
package's binary is used instead. Only the Windows layout is VERIFIED; the others are INFERRED.

**D15: launchability.** `probe_agent` is synchronous and runs on list routes, so it cannot spawn.
`CopilotProbe` keeps one process-wide verdict per resolved executable (path and mtime) and refreshes
it in the background with a model-free ACP handshake: `initialize` (the version), `session/new`
(`-32000` means not signed in), `session/close`. A positive verdict is fresh for ten minutes; a
negative one is always stale, because `copilot login` and `copilot update` change neither the path
nor the mtime, so the attempt after the operator repairs it must not wait out a TTL. A verdict not
yet computed is permissive (`verdict_pending`): the run's own handshake is the binding gate, and a
fresh Hub's first Copilot agent must not be uncreatable because a probe had not finished. A refresh
that fails for any other reason changes nothing that gates; it only adds `probe_error`.

Every Copilot turn also writes what it learned (`record`), so a turn that finds the CLI too old or
signed out makes the trigger's next `probe_agent` hold the input rather than spend its delivery
attempts (D12, R3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

#: Raw session events, `session_info`/plan updates (1.0.81), `usage_update` and `session/close`
#: (1.0.78). Without raw events D8's server identification and D10's error classification fail.
COPILOT_MIN_VERSION: Tuple[int, ...] = (1, 0, 81)
COPILOT_MIN_VERSION_TEXT = "1.0.81"

#: JSON-RPC `-32000` "Authentication required" from `session/new` (CODE: `newSession`).
AUTH_REQUIRED_CODE = -32000

POSITIVE_TTL_SECONDS = 600.0
#: A refresh that finished this recently is not repeated, so a polling list route cannot spawn one
#: probe per request.
REFRESH_DEBOUNCE_SECONDS = 5.0
PROBE_TIMEOUT_SECONDS = 30.0

#: `--disable-builtin-mcps`: `session/new` awaits the built-in GitHub server otherwise.
PROBE_ARGS: Tuple[str, ...] = ("--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps")

NOT_FOUND_REASON = (
    "GitHub Copilot CLI was not found: install it with npm (`@github/copilot`) or the "
    "standalone installer."
)


def not_signed_in_reason() -> str:
    """Names the file the Hub copies the account from (F483): `copilot login` under another
    `COPILOT_HOME` signs in an account the Hub never sees."""
    from .copilot_home import operator_copilot_home

    config = operator_copilot_home() / "config.json"
    return (
        "Copilot CLI is not signed in. Run `copilot login`; the Hub signs Copilot in as the "
        f"account it records in {config}."
    )


_SCRIPT_SUFFIXES = {".cmd", ".bat", ".ps1", ".js", ".mjs", ".cjs", ".sh"}
_SHIM_NAMES = {"copilot", "copilot.cmd", "copilot.ps1"}


class CopilotExecutableNotFound(FileNotFoundError):  # noqa: N818 -- the name the design fixes
    """No native Copilot executable could be resolved. A `FileNotFoundError`, so the one-shot
    callers and the executor's pre-spawn `except` catch it without naming a runner (D14)."""

    def __init__(self, message: str, looked_for: Optional[Path] = None) -> None:
        super().__init__(message)
        self.looked_for = looked_for


def too_old_reason(version: Optional[str]) -> str:
    shown = version or "(unknown version)"
    return f"Copilot CLI {shown} is older than the supported {COPILOT_MIN_VERSION_TEXT}. Update it."


def parse_version(value: Any) -> Optional[Tuple[int, ...]]:
    """Dotted integers, or None. A missing or unparseable version is treated as too old."""
    if not isinstance(value, str) or not value.strip():
        return None
    parts = []
    for piece in value.strip().split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts)


def version_supported(value: Any) -> bool:
    parsed = parse_version(value)
    return parsed is not None and parsed >= COPILOT_MIN_VERSION


def _platform_package() -> Tuple[str, str]:
    system = platform.system().lower()
    osname = {"windows": "win32", "darwin": "darwin", "linux": "linux"}.get(system, system)
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine, machine
    )
    binary = "copilot.exe" if osname == "win32" else "copilot"
    return f"copilot-{osname}-{arch}", binary


def _npm_package_dir(found: Path) -> Optional[Path]:
    """The `@github/copilot` package directory an npm shim forwards to, or None."""
    if found.name.lower() in _SHIM_NAMES:
        candidate = found.parent / "node_modules" / "@github" / "copilot"
        if (candidate / "npm-loader.js").is_file():
            return candidate
    # POSIX npm links `bin/copilot` into the package. Only a link is followed: the platform
    # binary itself also sits under `@github/copilot/`, and must not read as a shim.
    if not found.is_symlink():
        return None
    try:
        resolved = found.resolve()
    except OSError:
        return None
    for parent in resolved.parents:
        if parent.name == "copilot" and parent.parent.name == "@github":
            return parent
    return None


def _is_script(path: Path) -> bool:
    if path.suffix.lower() in _SCRIPT_SUFFIXES:
        return True
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def resolve_copilot_executable(cli_override: Optional[str]) -> Path:
    """The native Copilot executable to spawn (D2). Raises `CopilotExecutableNotFound`."""
    if cli_override:
        pinned = Path(cli_override)
        if not pinned.is_file():
            raise CopilotExecutableNotFound(
                f"Pinned Copilot CLI {cli_override!r} is not a file.", looked_for=pinned
            )
        if (
            _is_script(pinned)
            or _is_script(pinned.resolve())
            or _npm_package_dir(pinned) is not None
        ):
            raise CopilotExecutableNotFound(
                f"Pinned Copilot CLI {cli_override!r} is a script, not the native executable; "
                "pin the platform binary instead.",
                looked_for=pinned,
            )
        return pinned.resolve()

    which = shutil.which("copilot")
    if which is None:
        raise CopilotExecutableNotFound(NOT_FOUND_REASON)
    found = Path(which)
    package = _npm_package_dir(found)
    if package is None:
        if _is_script(found):
            raise CopilotExecutableNotFound(
                f"{NOT_FOUND_REASON} ({found} is a script this Hub cannot unwrap.)",
                looked_for=found,
            )
        return found.resolve()

    platform_package, binary = _platform_package()
    looked_for = package / "node_modules" / "@github" / platform_package / binary
    if looked_for.is_file():
        return looked_for.resolve()
    raise CopilotExecutableNotFound(
        f"{NOT_FOUND_REASON} The npm shim at {found} has no platform binary; looked for "
        f"{looked_for}.",
        looked_for=looked_for,
    )


@dataclass
class _Verdict:
    present: bool
    authorized: bool
    reason: Optional[str]
    version: Optional[str] = None
    computed_at: float = 0.0
    probe_error: Optional[str] = None

    @property
    def positive(self) -> bool:
        return self.present and self.authorized


def _key(path: Path) -> Tuple[str, int]:
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return (str(path), mtime)


class CopilotProbe:
    """The process-wide Copilot launchability verdict. Every method is a classmethod: there is
    one Copilot installation per Hub process, and every caller must see the same verdict."""

    _verdicts: Dict[Tuple[str, int], _Verdict] = {}
    _in_flight: Set[Tuple[str, int]] = set()
    _finished_at: Dict[Tuple[str, int], float] = {}
    #: Held until done, as `agent_trigger._background_runs` holds runs: an unreferenced task can
    #: be collected mid-flight.
    _tasks: Set["asyncio.Task[None]"] = set()
    #: The test suite switches this off (`hub/tests/conftest.py`) so no route test spawns a real
    #: Copilot on a machine that has one.
    refresh_enabled: bool = True

    @classmethod
    def reset(cls) -> None:
        cls._verdicts = {}
        cls._in_flight = set()
        cls._finished_at = {}

    @classmethod
    def verdict(cls, cli_override: Optional[str] = None) -> Dict[str, Any]:
        """The cached verdict as `probe_agent`'s dict. Never raises and never blocks; schedules a
        refresh when the verdict is stale and an event loop is running."""
        try:
            path = resolve_copilot_executable(cli_override)
        except CopilotExecutableNotFound as exc:
            looked_for = exc.looked_for
            return _as_probe_dict(
                str(looked_for) if looked_for is not None else "copilot",
                _Verdict(present=False, authorized=False, reason=str(exc)),
            )
        except Exception as exc:  # resolution must never raise out of a list route
            logger.warning("Resolving the Copilot CLI failed unexpectedly: %s", exc)
            return _as_probe_dict(
                "copilot", _Verdict(present=False, authorized=False, reason=NOT_FOUND_REASON)
            )

        key = _key(path)
        cached = cls._verdicts.get(key)
        now = time.monotonic()
        if cached is None:
            cls._schedule(key, path)
            result = _as_probe_dict(str(path), _Verdict(True, True, None))
            result["verdict_pending"] = True
            return result
        if not cached.positive or now - cached.computed_at >= POSITIVE_TTL_SECONDS:
            cls._schedule(key, path)
        return _as_probe_dict(str(path), cached)

    @classmethod
    def record(
        cls,
        *,
        present: bool,
        authorized: bool,
        reason: Optional[str],
        version: Optional[str] = None,
        cli_override: Optional[str] = None,
    ) -> None:
        """What a Copilot turn learned from its own handshake. Never raises."""
        try:
            path = resolve_copilot_executable(cli_override)
        except Exception:
            return
        cls._verdicts[_key(path)] = _Verdict(
            present=present,
            authorized=authorized,
            reason=reason,
            version=version,
            computed_at=time.monotonic(),
        )

    @classmethod
    def _schedule(cls, key: Tuple[str, int], path: Path) -> None:
        if not cls.refresh_enabled or key in cls._in_flight:
            return
        finished = cls._finished_at.get(key)
        if finished is not None and time.monotonic() - finished < REFRESH_DEBOUNCE_SECONDS:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        cls._in_flight.add(key)
        task = loop.create_task(cls._refresh(key, path))
        cls._tasks.add(task)
        task.add_done_callback(cls._tasks.discard)

    @classmethod
    async def _refresh(cls, key: Tuple[str, int], path: Path) -> None:
        try:
            result = await probe_copilot(path)
        except Exception as exc:
            # An unclassified failure moves nothing that gates: a `reason` would make every
            # Copilot agent unlaunchable for a TTL over one slow spawn (R3).
            logger.warning("Copilot launchability probe of %s failed: %s", path, exc)
            previous = cls._verdicts.get(key)
            if previous is not None:
                previous.probe_error = str(exc) or type(exc).__name__
        else:
            cls._verdicts[key] = result
        finally:
            cls._in_flight.discard(key)
            cls._finished_at[key] = time.monotonic()


def _as_probe_dict(cli: str, verdict: _Verdict) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "runner": "copilot",
        "cli": cli,
        "present": verdict.present,
        "authorized": verdict.authorized,
        "runnable": verdict.present and verdict.authorized,
        "reason": verdict.reason,
    }
    if verdict.version:
        result["version"] = verdict.version
    if verdict.probe_error:
        result["probe_error"] = verdict.probe_error
    return result


def probe_argv(path: Path) -> list[str]:
    return [str(path), *PROBE_ARGS]


def probe_env(home: Path) -> Dict[str, str]:
    """The probe's environment: the Copilot guard over the Hub's own, under the worker home."""
    from .copilot_env import copilot_guard_env

    env, _removed = copilot_guard_env(dict(os.environ), {})
    env["COPILOT_HOME"] = str(home)
    return env


async def _spawn_probe_process(argv: list[str], *, cwd: Path, env: Dict[str, str]):
    from .subprocess_windows import no_console_kwargs

    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        # Its own process group on POSIX, for the reason `copilot_acp.ACPProcess.spawn` gives: the
        # tree kill below kills the child's group, which must not be the Hub's.
        **({} if os.name == "nt" else {"start_new_session": True}),
        **no_console_kwargs(),
    )


async def _exchange(proc, request_id: int, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send one request and read lines until its response, skipping notifications."""
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    await proc.stdin.drain()
    while True:
        line = await proc.stdout.readline()
        if not line:
            raise ConnectionError(f"copilot exited before answering {method}")
        try:
            data = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("id") == request_id and "method" not in data:
            return data


async def probe_copilot(path: Path) -> _Verdict:
    """One model-free handshake. Classifies only what it can conclude; raises otherwise."""
    from .copilot_home import ensure_copilot_worker_home
    from .pty_runner import terminate_process_tree

    home = ensure_copilot_worker_home()
    proc = await _spawn_probe_process(probe_argv(path), cwd=home, env=probe_env(home))
    try:

        async def _talk() -> _Verdict:
            init = await _exchange(
                proc,
                1,
                "initialize",
                {"protocolVersion": 1, "clientCapabilities": {}},
            )
            if "error" in init:
                raise RuntimeError(f"initialize failed: {init['error']}")
            info = (init.get("result") or {}).get("agentInfo") or {}
            version = info.get("version") if isinstance(info, dict) else None
            if not version_supported(version):
                return _Verdict(True, False, too_old_reason(version), version, time.monotonic())
            new = await _exchange(proc, 2, "session/new", {"cwd": str(home), "mcpServers": []})
            error = new.get("error")
            if isinstance(error, dict) and error.get("code") == AUTH_REQUIRED_CODE:
                return _Verdict(True, False, not_signed_in_reason(), version, time.monotonic())
            if error is not None:
                raise RuntimeError(f"session/new failed: {error}")
            session_id = (new.get("result") or {}).get("sessionId")
            if session_id:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(
                        _exchange(proc, 3, "session/close", {"sessionId": session_id}), 5
                    )
            return _Verdict(True, True, None, version, time.monotonic())

        return await asyncio.wait_for(_talk(), PROBE_TIMEOUT_SECONDS)
    finally:
        if proc.returncode is None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(terminate_process_tree, proc.pid, True)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), 5)
