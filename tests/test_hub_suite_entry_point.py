"""The full Hub suite's entry point, `scripts/checks/hub_suite.py`.

Spec `agentweave-s-checks-fit-a-busy-machine`: one full suite at a time on the machine (FR-1),
a dead holder never blocks the next run (FR-2), a waiting run says so first (FR-3), and the
worker count follows CPU idle (FR-4). The two-checkouts drive is
`scripts/drive/d1104_one_suite_at_a_time.py`; these are the faster checks beside it.

Every run here uses its own lock directory (`AW_HUB_SUITE_LOCK_DIR`), so a real suite on the
machine neither blocks these tests nor is blocked by them.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "checks" / "hub_suite.py"


def _load():
    """Import `scripts/checks/hub_suite.py` by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("hub_suite", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hub_suite = _load()


# --- FR-4: workers from idle -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("idle", "cpus", "expected"),
    [(0.8, 16, 16), (0.3, 16, 8), (0.3, 2, 2), (0.5, 16, 16), (0.49, 16, 8), (None, 16, 8)],
)
def test_worker_choice_follows_idle_share(idle, cpus, expected):
    assert hub_suite.choose_workers(idle, cpus) == expected


def test_the_run_prints_each_choice_with_its_idle_share(tmp_path, capsys):
    """80% then 30% idle on 16 CPUs runs 16 then 8 workers, each printed with the share read."""
    seen = []
    for idle in (0.8, 0.3):
        code = hub_suite.run(
            ["sel"],
            lock=hub_suite.SuiteLock(tmp_path),
            read_idle=lambda idle=idle: idle,
            logical_cpus=16,
            run_pytest=lambda args: seen.append(args) or 0,
        )
        assert code == 0
    assert [args[:2] for args in seen] == [["-n", "16"], ["-n", "8"]]
    out = capsys.readouterr().out
    assert "16 workers (CPU idle 80% on 16 logical CPUs)" in out
    assert "8 workers (CPU idle 30% on 16 logical CPUs)" in out


def test_a_caller_who_sets_workers_is_obeyed(tmp_path):
    seen = []
    hub_suite.run(
        ["sel", "-n", "0"],
        lock=hub_suite.SuiteLock(tmp_path),
        read_idle=lambda: pytest.fail("idle read although the caller set -n"),
        run_pytest=lambda args: seen.append(args) or 0,
    )
    assert seen == [["sel", "-n", "0"]]


def test_pytest_exit_code_is_the_runs(tmp_path):
    code = hub_suite.run(
        ["sel", "-n", "0"], lock=hub_suite.SuiteLock(tmp_path), run_pytest=lambda args: 3
    )
    assert code == 3


def test_idle_share_reads_on_this_machine():
    share = hub_suite.read_idle_share(sample_seconds=0.2)
    assert share is None or 0.0 <= share <= 1.0
    if os.name == "nt" or Path("/proc/stat").exists():
        assert share is not None


# --- FR-1, FR-2, FR-3: the lock, across real processes -----------------------------------------

SLOW = "import time\n\n\ndef test_holds():\n    time.sleep({seconds})\n"
FAILING = "def test_passes():\n    pass\n\n\ndef test_breaks_on_purpose():\n    assert 1 == 2\n"


def _env(lock_dir: Path) -> dict:
    return {**os.environ, "AW_HUB_SUITE_LOCK_DIR": str(lock_dir), "PYTHONUNBUFFERED": "1"}


def _start(cwd: Path, lock_dir: Path, *selection: str) -> subprocess.Popen:
    # sys.executable, not the `py` launcher, so the pid printed is the process we hold.
    return subprocess.Popen(
        [sys.executable, str(SCRIPT), *selection, "-q", "-p", "no:cacheprovider", "-n", "0"],
        cwd=cwd,
        env=_env(lock_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for_line(proc: subprocess.Popen, needle: str, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    lines = []
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if needle in line:
            return line
    raise AssertionError(f"never printed {needle!r}: {''.join(lines)}")


def _selection(root: Path, name: str, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body)
    return root


def test_a_failing_run_that_waited_reports_as_it_would_alone(tmp_path):
    """result-unchanged-by-wait and wait-printed: the second run waits, says so, then fails the
    same way it fails alone."""
    lock_dir = tmp_path / "lock"
    failing = _selection(tmp_path / "failing", "test_failing.py", FAILING)

    alone = subprocess.run(
        [sys.executable, str(SCRIPT), "-q", "-p", "no:cacheprovider", "-n", "0"],
        cwd=failing,
        env=_env(lock_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert alone.returncode == 1
    assert "test_breaks_on_purpose" in alone.stdout

    holder_dir = _selection(tmp_path / "holder", "test_slow.py", SLOW.format(seconds=4))
    holder = _start(holder_dir, lock_dir)
    try:
        _wait_for_line(holder, "started at")
        waited = subprocess.run(
            [sys.executable, str(SCRIPT), "-q", "-p", "no:cacheprovider", "-n", "0"],
            cwd=failing,
            env=_env(lock_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert holder.wait(timeout=60) == 0
    finally:
        holder.kill()
        holder.communicate()

    lines = waited.stdout.splitlines()
    assert lines[0].startswith("hub-suite: waiting for the suite lock")
    assert f"held by pid {holder.pid} since 20" in lines[0]
    assert any("started at" in line and "after waiting" in line for line in lines[1:])
    assert waited.returncode == alone.returncode
    assert "test_breaks_on_purpose" in waited.stdout
    assert "1 failed, 1 passed" in waited.stdout and "1 failed, 1 passed" in alone.stdout


def test_a_killed_holder_does_not_block_the_next_run(tmp_path):
    """dead-holder-taken-over: the holder is terminated with no cleanup; the next run takes the
    lock within 10 seconds and completes."""
    lock_dir = tmp_path / "lock"
    holder = _start(
        _selection(tmp_path / "holder", "test_slow.py", SLOW.format(seconds=120)), lock_dir
    )
    try:
        _wait_for_line(holder, "started at")
        holder.kill()  # TerminateProcess / SIGKILL: no finally, no release
        holder.wait(timeout=30)
    finally:
        holder.communicate()
    assert (lock_dir / "hub-suite.lock").exists()

    began = time.monotonic()
    nxt = _start(_selection(tmp_path / "next", "test_quick.py", SLOW.format(seconds=0)), lock_dir)
    try:
        _wait_for_line(nxt, "started at", timeout=10)
        took = time.monotonic() - began
        out, _ = nxt.communicate(timeout=60)
    finally:
        nxt.kill()
    assert took < 10, f"took the lock after {took:.1f} s"
    assert nxt.returncode == 0, out
    assert "1 passed" in out


# --- FR-8, FR-9: the guidance and the settings name the entry point ------------------------------


def test_agent_guidance_sends_full_runs_through_the_entry_point():
    """CLAUDE.md (loaded every request) and the testing rule say: changed tests plus the sweep set,
    the full suite left to the Hub, and the entry point for any full run."""
    for guidance in (REPO_ROOT / "CLAUDE.md", REPO_ROOT / ".claude" / "rules" / "testing.md"):
        text = guidance.read_text(encoding="utf-8")
        assert "scripts/checks/hub_suite.py" in text, guidance
        assert "scripts/checks/sweep_check.py" in text, guidance
        assert "hub-tests" in text, guidance
        # No bare full-suite command left for an agent to copy.
        assert "pytest hub/tests/ -v" not in text, guidance


def test_the_settings_to_paste_use_the_entry_point_and_write_reports():
    """checks.md shows exactly `scripts/checks/check_settings.json`, the list the operator applies
    and the d1105 drive applies (`checks-report-which-tests-failed-in-any-language`, FR-9)."""
    import json
    import re

    text = (REPO_ROOT / ".claude" / "reference" / "checks.md").read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert block, "checks.md carries the whole check list as JSON"
    delivered = REPO_ROOT / "scripts" / "checks" / "check_settings.json"
    assert json.loads(block.group(1)) == json.loads(delivered.read_text(encoding="utf-8"))
    checks = {c["name"]: c for c in json.loads(block.group(1))}
    for name, script in (("hub-tests", "hub_suite.py"), ("sweep", "sweep_check.py")):
        check = checks[name]
        report = check["report_path"]
        assert check["command"] == f"py -3.11 scripts/checks/{script} --report {report}"
        assert check["rerun_command"] == f"{check['command']} --rerun {{tests}}"
        assert report.startswith(".agentweave/")  # gitignored at any depth
    assert checks["hub-tests"]["paths"] == [] and not checks["hub-tests"]["fast"]
    # Every entry has only the fields the Hub's `ProjectCheck` takes, within its bounds.
    fields = {"name", "command", "timeout_seconds", "paths", "fast", "phase"}
    for check in checks.values():
        assert (
            fields <= set(check) <= fields | {"report_path", "rerun_command", "change_command"}
        ), check["name"]
        assert 10 <= check["timeout_seconds"] <= 3600, check["name"]
        assert check["phase"] in ("review", "landing", "both"), check["name"]
        assert not check["fast"] or check["timeout_seconds"] <= 120, check["name"]


# --- spec `a-check-can-run-only-the-tests-for-what-a-task-changed`, FR-8 -----------------------


def _tree(tmp_path):
    tests = tmp_path / "hub" / "tests"
    tests.mkdir(parents=True)
    (tests / "conftest.py").write_text("", encoding="utf-8")
    (tests / "test_queue.py").write_text("from hub import landing_queue\n", encoding="utf-8")
    (tests / "test_other.py").write_text("import json\n", encoding="utf-8")
    (tests / "test_landing_queue_extra.py").write_text("# landing_queue\n", encoding="utf-8")
    return tmp_path


def _main(tmp_path, monkeypatch, paths, *extra):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AW_HUB_SUITE_LOCK_DIR", str(tmp_path / "lock"))
    listing = tmp_path / "list.txt"
    listing.write_text("".join(f"{p}\n" for p in paths), encoding="utf-8")
    seen = []
    code = hub_suite.main(
        ["--report", "r.xml", "--changed-files", str(listing), *extra],
        run_pytest=lambda args: seen.append(args) or 0,
        read_idle=lambda: 1.0,
        logical_cpus=4,
    )
    return code, seen


def test_a_changed_module_runs_the_test_files_that_name_it(tmp_path, monkeypatch):
    _tree(tmp_path)
    code, seen = _main(tmp_path, monkeypatch, ["hub/hub/landing_queue.py"])
    assert code == 0 and len(seen) == 1
    ran = [a for a in seen[0] if a.endswith(".py")]
    assert ran == ["hub/tests/test_landing_queue_extra.py", "hub/tests/test_queue.py"]
    assert any(a.startswith("--junitxml=") for a in seen[0])


def test_a_changed_test_file_runs_itself_and_a_deleted_one_is_skipped(tmp_path, monkeypatch):
    _tree(tmp_path)
    _, seen = _main(tmp_path, monkeypatch, ["hub/tests/test_other.py", "hub/tests/test_gone.py"])
    assert [a for a in seen[0] if a.endswith(".py")] == ["hub/tests/test_other.py"]


def test_a_change_no_test_relates_to_runs_nothing_passes_and_says_so(tmp_path, monkeypatch, capsys):
    _tree(tmp_path)
    code, seen = _main(tmp_path, monkeypatch, ["hub/ui/src/App.tsx"])
    assert code == 0 and seen == []
    assert "no Hub test relates" in capsys.readouterr().out
    assert (tmp_path / "r.xml").is_file()


@pytest.mark.parametrize("path", ["hub/tests/conftest.py", "hub/pyproject.toml"])
def test_a_conftest_or_packaging_change_runs_the_full_suite(tmp_path, monkeypatch, path):
    _tree(tmp_path)
    _, seen = _main(tmp_path, monkeypatch, [path])
    assert "hub/tests" in seen[0] and not any(a.endswith(".py") for a in seen[0])


def test_the_repository_settings_size_hub_tests_to_the_change():
    import json

    checks = {
        c["name"]: c
        for c in json.loads((REPO_ROOT / "scripts/checks/check_settings.json").read_text("utf-8"))
    }
    assert checks["sweep"]["timeout_seconds"] == 3600
    assert checks["hub-tests"]["phase"] == "both"
    assert "{changed_files}" in checks["hub-tests"]["change_command"]
