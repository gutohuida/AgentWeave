"""The one entry point for running this repository's full Hub test suite.

The hub-tests check, agents and the operator all run the full suite through this script:

    py -3.11 scripts/checks/hub_suite.py [--report PATH] [pytest arguments...]
    py -3.11 scripts/checks/hub_suite.py [--report PATH] --rerun ID [ID ...]

With no arguments it runs `hub/tests -q --dist loadgroup -p no:cacheprovider --timeout=600`.
Arguments given are passed to pytest unchanged, plus `-n <workers>` unless they already set one.

`--report PATH` writes the JUnit XML report the Hub reads the failing tests from, and `--rerun`
runs only the given `classname::name` ids, serially, without waiting for the suite lock: it is not
the full suite (spec `checks-report-which-tests-failed-in-any-language`, FR-9; `junit_rerun.py`).

Two things it adds over calling pytest directly (spec `agentweave-s-checks-fit-a-busy-machine`):

- **One full suite at a time on this machine (FR-1, FR-2, FR-3).** The run holds an OS file lock
  on `<lock dir>/hub-suite.lock`; a second run prints that it is waiting, names the holder's pid
  and start time, waits, then runs. The lock is the operating system's (`msvcrt.locking` on
  Windows, `fcntl.flock` elsewhere), so it is released by the OS the moment its holder dies --
  killed, crashed or rebooted -- and the next run takes it on its next poll, with nothing to
  remove by hand. The lock dir is the user's temp directory, which every checkout on the machine
  shares; `AW_HUB_SUITE_LOCK_DIR` overrides it (tests and drives only).
  pytest runs in this process, not a child, so killing this process kills the suite with it: a
  holder's lock can never be released while its tests are still running.
- **Workers fitted to the load (FR-4).** Once it holds the lock it samples CPU idle for about a
  second and chooses: every logical CPU when at least half is idle, otherwise half of them and
  never fewer than 2. It prints the number and the idle share it read.

Its exit code is pytest's, so a run that waited reports exactly what it would have alone.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import junit_rerun  # noqa: E402 -- beside this script, which is run by path

DEFAULT_ARGS = ["hub/tests", "-q", "--dist", "loadgroup", "-p", "no:cacheprovider", "--timeout=600"]
POLL_SECONDS = 0.5
PREFIX = "hub-suite:"


def say(message: str) -> None:
    print(f"{PREFIX} {message}", flush=True)


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- the lock ----------------------------------------------------------------------------------


def lock_dir() -> Path:
    return Path(os.environ.get("AW_HUB_SUITE_LOCK_DIR") or tempfile.gettempdir())


def _try_lock(handle) -> bool:
    """Take the OS lock on byte 0 of `handle` without blocking; True when taken."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        with contextlib.suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_holder(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class SuiteLock:
    """The machine-wide one-at-a-time lock. `acquire` waits, printing who it waits for."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        directory = directory or lock_dir()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "hub-suite.lock"
        # Who holds it lives in a second file: on Windows a locked byte cannot be read by others.
        self.holder_path = directory / "hub-suite.holder.json"
        self._handle = None

    def acquire(self) -> float:
        """Take the lock, waiting as long as it takes. Returns the seconds spent waiting."""
        # Held open for the lock's whole life and closed by release(), not by a block.
        handle = open(self.path, "a+b")  # noqa: SIM115
        began = time.monotonic()
        if not _try_lock(handle):
            # The holder writes its record just after it takes the lock; give it a moment.
            holder = _read_holder(self.holder_path)
            for _ in range(10):
                if holder:
                    break
                time.sleep(0.1)
                holder = _read_holder(self.holder_path)
            say(
                f"waiting for the suite lock, held by pid {holder.get('pid', 'unknown')} "
                f"since {holder.get('started', 'unknown')} ({self.path})"
            )
            while not _try_lock(handle):
                time.sleep(POLL_SECONDS)
        self._handle = handle
        self.holder_path.write_text(
            json.dumps({"pid": os.getpid(), "started": now_text(), "cwd": os.getcwd()}),
            encoding="utf-8",
        )
        return time.monotonic() - began

    def release(self) -> None:
        if self._handle is None:
            return
        _unlock(self._handle)
        self._handle.close()
        self._handle = None


# --- the worker count --------------------------------------------------------------------------


def choose_workers(idle_share: Optional[float], logical_cpus: int) -> int:
    """All logical CPUs when at least half is idle; else half of them, never fewer than 2.

    An unreadable idle share counts as busy: the cautious choice on a shared machine.
    """
    if idle_share is not None and idle_share >= 0.5:
        return logical_cpus
    return max(2, logical_cpus // 2)


def describe_workers(workers: int, idle_share: Optional[float], logical_cpus: int) -> str:
    idle = "unreadable" if idle_share is None else f"{idle_share:.0%}"
    return f"{workers} workers (CPU idle {idle} on {logical_cpus} logical CPUs)"


def _cpu_times() -> Optional[tuple[int, int]]:
    """(idle, total) CPU time counters since boot, or None where they cannot be read."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None

        def ticks(ft) -> int:
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        # Kernel time already includes idle time.
        return ticks(idle), ticks(kernel) + ticks(user)
    try:
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    except (OSError, IndexError):
        return None
    values = [int(v) for v in fields]
    idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
    return idle, sum(values[:8])


def read_idle_share(sample_seconds: float = 1.0) -> Optional[float]:
    """The share of CPU capacity idle over a short sample, 0..1, or None if unreadable."""
    first = _cpu_times()
    if first is not None:
        time.sleep(sample_seconds)
        second = _cpu_times()
        if second is not None and second[1] > first[1]:
            share = (second[0] - first[0]) / (second[1] - first[1])
            return min(1.0, max(0.0, share))
    if hasattr(os, "getloadavg"):
        load = os.getloadavg()[0]
        return min(1.0, max(0.0, 1 - load / (os.cpu_count() or 1)))
    return None


# --- the run -----------------------------------------------------------------------------------


def _sets_workers(args: list[str]) -> bool:
    """True when the arguments already say how many xdist workers (`-n 4`, `-n4`, `--numprocesses=4`)."""
    return any(
        a in ("-n", "--numprocesses") or a.startswith(("-n", "--numprocesses=")) for a in args
    )


def run(
    args: list[str],
    *,
    lock: Optional[SuiteLock] = None,
    read_idle: Callable[[], Optional[float]] = read_idle_share,
    logical_cpus: Optional[int] = None,
    run_pytest: Optional[Callable[[list[str]], int]] = None,
) -> int:
    args = list(args) or list(DEFAULT_ARGS)
    lock = lock or SuiteLock()
    waited = lock.acquire()
    try:
        say(
            f"started at {now_text()} (pid {os.getpid()})"
            + (f" after waiting {waited:.1f} s" if waited >= POLL_SECONDS else "")
        )
        if _sets_workers(args):
            say("workers set by the caller's arguments")
        else:
            cpus = logical_cpus or os.cpu_count() or 2
            idle = read_idle()
            workers = choose_workers(idle, cpus)
            say(describe_workers(workers, idle, cpus))
            args = ["-n", str(workers), *args]
        code = (run_pytest or _run_pytest)(args)
        say(f"ended at {now_text()} with exit {code}")
        return code
    finally:
        lock.release()


def _run_pytest(args: list[str]) -> int:
    import pytest

    # As `python -m pytest` does: the current directory is importable.
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    return int(pytest.main(args))


# --- the tests for a change --------------------------------------------------------------------

#: Changes that can alter any test, so they run the full suite.
FULL_SUITE_FILES = {"pyproject.toml", "hub/pyproject.toml", "constraints-dev.txt"}
NO_TESTS_MESSAGE = "no Hub test relates to the change; running no tests"


def extract_changed_files(argv: list[str]) -> tuple[Optional[str], list[str]]:
    """(the `--changed-files` path or `None`, argv without the option)."""
    args = list(argv)
    for i, arg in enumerate(args):
        if arg == "--changed-files":
            if i + 1 >= len(args):
                raise junit_rerun.UsageError("--changed-files needs a path")
            path = args[i + 1]
            return path, args[:i] + args[i + 2 :]
        if arg.startswith("--changed-files="):
            return arg.split("=", 1)[1], args[:i] + args[i + 1 :]
    return None, args


def related_tests(changed: list[str], root: Path) -> Optional[list[str]]:
    """The Hub test files to run for *changed* paths, or `None` for the full suite.

    The changed Hub test files that still exist, plus every Hub test file that names a changed
    `hub/hub` module by its module name. A conftest or a packaging file runs everything.
    """
    paths = [p.strip().replace("\\", "/") for p in changed if p.strip()]
    if any(
        p in FULL_SUITE_FILES or (p.startswith("hub/tests/") and p.endswith("/conftest.py"))
        for p in paths
    ):
        return None
    tests_dir = root / "hub" / "tests"
    selected: set[str] = set()
    modules: set[str] = set()
    for path in paths:
        if path.startswith("hub/tests/") and path.endswith(".py"):
            if (root / path).is_file() and Path(path).name.startswith("test_"):
                selected.add(path)
        elif path.startswith("hub/hub/") and path.endswith(".py"):
            parts = Path(path[len("hub/hub/") :]).with_suffix("").parts
            name = parts[-2] if parts[-1] == "__init__" and len(parts) > 1 else parts[-1]
            if name != "__init__":
                modules.add(name)
    if modules and tests_dir.is_dir():
        pattern = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, modules))) + r")\b")
        for test in sorted(tests_dir.rglob("test_*.py")):
            try:
                text = test.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if pattern.search(text):
                selected.add(test.relative_to(root).as_posix())
    return sorted(selected)


def _write_empty_report(report: str) -> None:
    path = Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" '
        'errors="0" failures="0" skipped="0" tests="0" time="0"/></testsuites>',
        encoding="utf-8",
    )


def main(
    argv: list[str],
    *,
    run_pytest: Optional[Callable[[list[str]], int]] = None,
    **run_options,
) -> int:
    """Run the suite, or with `--rerun` only the named tests; `--report` writes the report.

    `--changed-files PATH` (one path per line) runs only the tests related to those files."""
    try:
        changed_path, argv = extract_changed_files(argv)
        report, rerun_ids, args = junit_rerun.parse_options(argv)
        if rerun_ids is not None:
            pytest_args = junit_rerun.rerun_args(rerun_ids, report, Path.cwd())
        if changed_path is not None and rerun_ids is None:
            try:
                listing = Path(changed_path).read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                raise junit_rerun.UsageError(f"cannot read --changed-files {changed_path}: {exc}")
            related = related_tests(listing, Path.cwd())
            if related is None:
                say("the change touches a conftest or packaging file; running the full suite")
            elif not related:
                say(NO_TESTS_MESSAGE)
                if report:
                    _write_empty_report(report)
                return 0
            else:
                say(f"running {len(related)} Hub test file(s) related to the change")
                args = [*related, *(args or DEFAULT_ARGS[1:])]
    except junit_rerun.UsageError as exc:
        say(str(exc))
        return 4  # pytest's usage error
    if rerun_ids is not None:
        say(f"re-running {len(rerun_ids)} test(s) serially, without the suite lock")
        code = (run_pytest or _run_pytest)(pytest_args)
        say(f"ended at {now_text()} with exit {code}")
    elif report:
        args = [*(args or DEFAULT_ARGS), *junit_rerun.report_args(report)]
        code = run(args, run_pytest=run_pytest, **run_options)
    else:
        return run(args, run_pytest=run_pytest, **run_options)
    if report:
        junit_rerun.tidy_report(Path(report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
