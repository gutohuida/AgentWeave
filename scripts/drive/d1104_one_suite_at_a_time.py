"""Acceptance drive 'two-runs-queue' for `agentweave-s-checks-fit-a-busy-machine` (FR-1, FR-3).

Builds two throwaway "checkouts" under testbed/drive1104-one-suite/<time>/{a,b}, each holding
its own copy of the suite entry point (scripts/checks/hub_suite.py) and the same stub selection:
one test file whose four tests sleep five seconds each (~20 s, one worker under
`--dist loadfile`). The first and last test of each selection write the wall-clock time the test
phase began and ended into that checkout's `phase.json`, so overlap is measured from the tests
themselves, not from anything the entry point prints.

Both are started within one second of each other. PASS needs: both exit 0, their test phases do
not overlap, and the one that ran second printed, as its first line, that it was waiting (naming
the holder's pid and start time) and later that it started.

Before the change there is no entry point, so the drive runs the selection the way hub-tests
runs today (`py -3.11 -m pytest ...`) in both checkouts, and they overlap: the drive FAILS.
`--before` forces that path even after the change, to show the baseline.

The lock directory is the drive's own (AW_HUB_SUITE_LOCK_DIR), so a real suite running on the
machine does not make the drive wait for it; the mechanism under test is the same.

    py -3.11 scripts/drive/d1104_one_suite_at_a_time.py [--before]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENTRY = REPO / "scripts" / "checks" / "hub_suite.py"
TMP = REPO / "testbed" / "drive1104-one-suite" / time.strftime("%H%M%S")

STUB = """\
import json
import time
from pathlib import Path

PHASE = Path(__file__).resolve().parent.parent / "phase.json"


def test_1():
    PHASE.write_text(json.dumps({"start": time.time()}))
    time.sleep(5)


def test_2():
    time.sleep(5)


def test_3():
    time.sleep(5)


def test_4():
    time.sleep(5)
    data = json.loads(PHASE.read_text())
    data["end"] = time.time()
    PHASE.write_text(json.dumps(data))
"""


def make_checkout(root: Path, with_entry: bool) -> None:
    (root / "sel").mkdir(parents=True)
    (root / "sel" / "test_stub_selection.py").write_text(STUB)
    if with_entry:
        (root / "scripts" / "checks").mkdir(parents=True)
        shutil.copy2(ENTRY, root / "scripts" / "checks" / "hub_suite.py")


def command(root: Path, with_entry: bool) -> list[str]:
    selection = ["sel", "-q", "-p", "no:cacheprovider", "--dist", "loadfile"]
    if with_entry:
        return [sys.executable, str(root / "scripts" / "checks" / "hub_suite.py"), *selection]
    return [sys.executable, "-m", "pytest", *selection]


def main() -> int:
    with_entry = ENTRY.exists() and "--before" not in sys.argv
    print(f"mode: {'entry point' if with_entry else 'before the change (plain pytest)'}")
    lock_dir = TMP / "lock"
    lock_dir.mkdir(parents=True)
    env = {**os.environ, "AW_HUB_SUITE_LOCK_DIR": str(lock_dir), "PYTHONUNBUFFERED": "1"}
    procs = {}
    for name in ("a", "b"):
        root = TMP / name
        make_checkout(root, with_entry)
        procs[name] = subprocess.Popen(
            command(root, with_entry),
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    outputs = {name: p.communicate(timeout=300)[0] for name, p in procs.items()}
    failures = []
    phases = {}
    for name, p in procs.items():
        print(f"--- {name} exit {p.returncode} ---\n{outputs[name]}")
        if p.returncode != 0:
            failures.append(f"{name} exited {p.returncode}")
        phases[name] = json.loads((TMP / name / "phase.json").read_text())
    a, b = phases["a"], phases["b"]
    print(f"phases: a {a}  b {b}")
    if a["start"] < b["end"] and b["start"] < a["end"]:
        overlap = min(a["end"], b["end"]) - max(a["start"], b["start"])
        failures.append(f"test phases overlap by {overlap:.1f} s")
    second = "b" if b["start"] > a["start"] else "a"
    lines = outputs[second].splitlines()
    first = lines[0] if lines else ""
    if not ("waiting" in first and "pid" in first and "since" in first):
        failures.append(f"{second} ran second but its first line is not a wait: {first!r}")
    if not any("started" in line for line in lines[1:]):
        failures.append(f"{second} never printed that it started")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS: the second run waited, then ran after the first ended; both exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
