---
paths:
  - "tests/**"
  - "hub/tests/**"
  - "scripts/checks/**"
  - "Makefile"
---

# Testing rules (loaded when a test file or a check script is read)

Spec `agentweave-s-checks-fit-a-busy-machine` (FR-8). The machine the Hub runs on is shared with
the operator's own work, and two full Hub suites at once crashed after ~45 minutes on 2026-11-03.

## Builders and reviewers: what to run

1. **The tests for the files you changed.** The test files you touched, and the Hub tests that
   exercise the modules you touched (`rg -l "<module>" hub/tests`). `py -3.11 -m pytest <files>`.
   The CLI suite (`tests/`) is small: run it whole when you touch `src/`.
2. **The sweep set**: `py -3.11 scripts/checks/sweep_check.py` (about 1-2 minutes). These are the
   Hub tests that scan the whole repository or the UI source rather than importing what they
   guard (`scripts/checks/sweep_tests.txt`), so no choice of tests "for what you changed" reaches
   them — and they are where most failures caught before review come from.
3. **Not the full Hub suite.** Leave it to the Hub's `hub-tests` check: before review it runs only
   the related tests (the changed Hub test files plus every Hub test file naming a changed
   `hub/hub` module; `hub_suite.py --changed-files`, the full suite when `hub/tests/conftest.py`
   or a packaging file changed), and at landing it runs the full suite. Your own full run only
   competes with it for CPU.

A reviewer checks the builder's claim the same way: run the changed files' tests and the sweep set,
and read `hub-tests`' result on the task's check run for the rest -- **the pre-review result
covers only the related tests**, so a green there is not the full suite; the landing run is.

## If you do run the full Hub suite

Run it through the entry point, never as bare `pytest hub/tests`:

```bash
py -3.11 scripts/checks/hub_suite.py                 # defaults: hub/tests -q --dist loadgroup ...
py -3.11 scripts/checks/hub_suite.py hub/tests -x    # any pytest arguments pass through
```

It holds a machine-wide lock, so it waits its turn behind any other full run (a check run's or
another agent's) and prints who it is waiting for; it then chooses its workers from how idle the
CPUs are and prints that choice. Its exit code is pytest's. Pass `-n` yourself only with a reason.
`make test-hub` calls it.

## Adding a test that scans the tree

A Hub test that walks or globs a source tree of this repository, or reads a file under
`hub/ui/src`, belongs in `scripts/checks/sweep_tests.txt`;
`hub/tests/test_the_sweep_set_is_current.py` fails, naming the file, until it is listed.

The project's check settings that call these scripts: `.claude/reference/checks.md`.
