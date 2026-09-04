"""Apply one phase-9 mutation to the classifier, run the suites, restore the tree.

Usage: py -3.11 scripts/drive/mutate_a_write_p9.py <id>

Task 9.1 asks for the mutation check again at the end of the change rather than trusting the one
phase 3 ran, because six phases of edits have landed since and a test that was load-bearing then
can be made insensitive by anything added after it.

Restores every touched product file from the pre-mutation **bytes**, never `git checkout --`: the
working tree carries uncommitted work and restoring from HEAD would throw it away rather than undo
the mutation (learned on the first run of the phase-5 harness, N-20). Prints `git status --short`
at the end so a harness killed mid-run is visible rather than silent.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WW = "hub/hub/workspace_writes.py"

MUTATIONS = {
    "M0": [],
    # Drop the join-before-resolve line, the first of the two traps rounds 1 and 2 both fell into.
    # `os.path.realpath` then resolves a relative path against the *Hub process's* cwd instead of
    # the run's workspace. If nothing fails, the tests are being run from the fixture workspace's
    # own directory and prove nothing about the join -- which is itself the finding.
    "M1": [
        (
            WW,
            "    absolute = path if os.path.isabs(path) else os.path.join(root, path)\n",
            "    absolute = path\n",
        )
    ],
    # Fold the `hub` kind into `project`. A write into `.agentweave/` stops being distinguishable
    # from a write anywhere else in the project tree.
    "M2": [(WW, '    return WriteLocation("hub")\n', '    return WriteLocation("project")\n')],
}

SUITES = [
    "hub/tests/test_workspace_writes.py",
    "hub/tests/test_a_write_outside_the_workspace_is_recorded.py",
    "hub/tests/test_outside_write_record.py",
]


def main() -> int:
    mid = sys.argv[1]
    edits = MUTATIONS[mid]
    touched = {}
    try:
        for rel, old, new in edits:
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{mid}: {rel} anchor matched {text.count(old)} times"
            touched[rel] = text
            path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        if edits:
            diff = subprocess.run(
                ["git", "diff", "--stat", "--", *sorted(touched)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            ).stdout.strip()
            print(f"mutant diff: {diff}")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header", "-p", "no:randomly"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        print(f"--- {mid} ---")
        for line in result.stdout.splitlines():
            if line.startswith("FAILED") or " passed" in line or " failed" in line:
                print(line)
    finally:
        for rel, original in touched.items():
            (ROOT / rel).write_text(original, encoding="utf-8", newline="")
        print(subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True).stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
