"""Apply one phase-5 mutation, run the two suites, restore the tree. One mutation per invocation.

Usage: py -3.11 scripts/drive/_mutate_p5.py <id>

Restores every touched product file from git in a `finally`, and prints `git status --short` at the
end so a harness killed mid-run is visible rather than silent (N-19).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RE = "hub/hub/requirement_evidence.py"
SPEC = "hub/hub/api/v1/spec.py"
ACTIONS = "hub/hub/api/v1/agent_actions.py"

MUTATIONS = {
    "M0": [],
    # _apply_footprint stops writing the column at all.
    "M1": [(RE, "    row.outside_workspace_writes = outside_writes\n", "")],
    # capture_footprint reads it and then does not pass it.
    "M2": [(RE, "taken, outside_writes=outside_writes)", "taken)")],
    # the read collapses to "not observed" always.
    "M3": [
        (
            RE,
            "    return await session.scalar("
            "select(Run.outside_workspace_writes).where(Run.id == run_id))",
            "    return None",
        )
    ],
    # the read coalesces NULL into "observed and clean" -- the distinction this change is about.
    "M4": [
        (
            RE,
            "    return await session.scalar("
            "select(Run.outside_workspace_writes).where(Run.id == run_id))",
            "    return (await session.scalar("
            "select(Run.outside_workspace_writes).where(Run.id == run_id))) or []",
        )
    ],
    # restamp fabricates instead of reading the run (the D11 failure).
    "M5": [(RE, "_apply_footprint(session, evidence, taken, footprint, outside_writes=outside_writes)", "_apply_footprint(session, evidence, taken, footprint)")],
    # the skip guard goes back to the commit alone.
    "M6": [(RE, "            and footprint.outside_workspace_writes == outside_writes\n", "")],
    # the response stops reporting it.
    "M7": [(SPEC, '        "outside_workspace_writes": footprint.outside_workspace_writes,\n', "")],
    # the agent's recording response stops reporting the footprint.
    "M8": [(ACTIONS, '        "footprint": footprint_view(prints.get(evidence.id)),\n', "")],
    # the "fix" design D7 forbids: follow the recorded path and footprint that tree instead.
    "M9": [
        (
            RE,
            "    outside_writes = await outside_writes_for_run(session, evidence.run_id)\n"
            "    if taken is None:",
            "    outside_writes = await outside_writes_for_run(session, evidence.run_id)\n"
            "    if outside_writes:\n"
            "        taken = read_footprint(Path(outside_writes[0]['path']).parent)\n"
            "    if taken is None:",
        )
    ],
}

SUITES = [
    "hub/tests/test_evidence_footprint_root.py",
    "hub/tests/test_evidence_restamp.py",
]


def main() -> int:
    mid = sys.argv[1]
    edits = MUTATIONS[mid]
    # The pre-mutation *bytes*, not `git checkout --`: the working tree here carries uncommitted
    # work, and restoring from HEAD would throw it away rather than undo the mutation. Learned the
    # expensive way on the first run of this harness.
    touched = {}
    try:
        for rel, old, new in edits:
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{mid}: {rel} anchor matched {text.count(old)} times"
            touched[rel] = text
            path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header", "-p", "no:randomly"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        tail = [line for line in result.stdout.splitlines() if line.strip()]
        print(f"--- {mid} ---")
        for line in tail:
            if line.startswith("FAILED") or " passed" in line or " failed" in line:
                print(line)
    finally:
        for rel, original in touched.items():
            (ROOT / rel).write_text(original, encoding="utf-8", newline="")
        print(subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True).stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
