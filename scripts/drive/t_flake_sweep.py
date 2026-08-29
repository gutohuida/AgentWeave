"""F109's unanswered question: which *other* tests are green for a reason unrelated to what they claim?

F109 proved that the suite runs every session on one database connection, so a background run task's
COMMIT and a request session's transaction interleave. `test_spawn_failure_marks_run_failed` is the
one test known to be flaky because of it. The finding says plainly that nothing has looked for
others.

This looks. It runs the twenty-one test files that await a background run — the population where the
interleaving is available at all — repeatedly, and reports every test that is not deterministic.

A test that fails intermittently here is not necessarily wrong; it is *unreliable*, which is the
same thing from CI's point of view and is the list the operator needs before deciding whether to
change the harness.

Run: py -3.11 scripts/drive/t_flake_sweep.py [rounds]
"""

import collections
import pathlib
import re
import subprocess
import sys

# The repository root, found by walking up from this file rather than assumed, so the sweep runs
# from anywhere.  is two levels down.
REPO = pathlib.Path(__file__).resolve().parents[2]

FILES = sorted(
    str(p.relative_to(REPO)).replace("\\", "/")
    for p in (REPO / "hub" / "tests").glob("test_*.py")
    if "_await_background_run" in p.read_text(encoding="utf-8", errors="replace")
    or "_background_runs" in p.read_text(encoding="utf-8", errors="replace")
)

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
FAILED = re.compile(r"^FAILED (\S+)", re.M)

print(f"{len(FILES)} files that await a background run, {ROUNDS} rounds")
for name in FILES:
    print(f"  {name}")
print()

counts: collections.Counter = collections.Counter()
completed = 0
for round_number in range(1, ROUNDS + 1):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *FILES, "-q", "-p", "no:randomly"],
        cwd=REPO,
        capture_output=True,
        text=True,
        errors="replace",
    )
    names = FAILED.findall(proc.stdout)
    tail = [
        line for line in proc.stdout.strip().splitlines() if " passed" in line or " failed" in line
    ]
    if not tail:
        # A round that never produced a summary did not run — killed by a timeout, a collection
        # error, an interpreter that could not start. Counting it as clean is how a sweep reports
        # "deterministic" for a sweep that never happened, which is the failure this whole file
        # exists to look for. It happened on the first run of this script and is why the check
        # is here.
        print(f"round {round_number}: DID NOT RUN — no pytest summary")
        for line in (proc.stdout or proc.stderr).strip().splitlines()[-3:]:
            print(f"      {line[:120]}")
        continue
    completed += 1
    print(f"round {round_number}: {tail[-1]}")
    for name in names:
        counts[name] += 1
        print(f"    FAILED {name}")

print()
print("=" * 78)
if completed < ROUNDS:
    print(f"WARNING: only {completed} of {ROUNDS} rounds actually ran. The verdict below covers")
    print("those rounds and nothing else.")
if completed == 0:
    print("no verdict: nothing ran")
elif not counts:
    print(f"deterministic across {completed} rounds — no test in this population was unreliable")
else:
    print(f"unreliable tests, out of {completed} completed rounds:")
    for name, hits in counts.most_common():
        print(f"  {hits}/{completed}  {name}")
