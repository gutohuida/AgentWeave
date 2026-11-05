# This project's check settings (`:8000`, `proj-d85a82bf4216`)

The check settings live in the operator's Hub database, which agents never write: **the operator
applies them**, in the app under Settings → General → Checks. The exact list to apply is
`scripts/checks/check_settings.json`; the acceptance drive
(`scripts/drive/d1105_checks_report_tests.py --only repo`) applies that same file to a scratch
clone, so what is pasted and what was driven cannot drift apart.

## Since 2026-11-05: `sweep` and `hub-tests` write a report

Spec `checks-report-which-tests-failed-in-any-language`, FR-9. The Hub takes a check's failing
tests from the JUnit XML report the check writes, and re-runs them through the check's re-run
command; a check with neither is judged as a whole, naming no test. Read back `mode=ro` on
2026-11-05, the settings were ruff, black, sweep, hub-ui (all phase `both`, none fast) and
hub-tests (phase `landing`). Only `sweep` and `hub-tests` change; every other field stays.

| Check | Field | Value |
|---|---|---|
| `sweep` | Command | `py -3.11 scripts/checks/sweep_check.py --report .agentweave/check-reports/sweep.xml` |
| | Report path | `.agentweave/check-reports/sweep.xml` |
| | Re-run command | `py -3.11 scripts/checks/sweep_check.py --report .agentweave/check-reports/sweep.xml --rerun {tests}` |
| `hub-tests` | Command | `py -3.11 scripts/checks/hub_suite.py --report .agentweave/check-reports/hub-tests.xml` |
| | Report path | `.agentweave/check-reports/hub-tests.xml` |
| | Re-run command | `py -3.11 scripts/checks/hub_suite.py --report .agentweave/check-reports/hub-tests.xml --rerun {tests}` |

Until the settings panel shows the two new fields (task `settings-ui`), save them through the
project settings route (`PUT /api/v1/projects/proj-d85a82bf4216/settings` with the list below as
`checks`). `.agentweave/` is gitignored at any depth, so the report never reaches a commit.

What the scripts do with them (`scripts/checks/junit_rerun.py`):

- `--report PATH` adds `--junitxml=PATH -o junit_family=xunit1 --rootdir=.`: xunit1 so each
  testcase carries its file, and the repository root as pytest's rootdir so a Hub test's id is
  `hub.tests.test_x.TestY::test_a` with file `hub/tests/test_x.py` (left alone pytest roots Hub
  tests at `hub/`, and the file would not match the paths a task changed).
- `--rerun ID...` turns each `classname::name` back into a node id (the longest dotted prefix of
  the classname that is a `.py` file is the module, the rest are classes) and runs them with
  `-n 0`: re-runs are serial (`a-red-main-does-not-hold-the-night`, FR-2). `hub_suite.py`'s
  re-run does not wait for the full suite's lock. An id naming no test file exits 4.

## The whole list, as it reads after the change

The content of `scripts/checks/check_settings.json`:

```json
[
  {"name": "ruff", "command": "py -3.11 -m ruff check src/ hub/ tests/ && py -3.11 -m ruff check scripts/ --select E9,F63,F7,F82,F401,F841", "timeout_seconds": 360, "paths": [], "fast": false, "phase": "both"},
  {"name": "black", "command": "py -3.11 -m black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/", "timeout_seconds": 360, "paths": [], "fast": false, "phase": "both"},
  {"name": "sweep", "command": "py -3.11 scripts/checks/sweep_check.py --report .agentweave/check-reports/sweep.xml", "timeout_seconds": 360, "paths": [], "fast": false, "phase": "both", "report_path": ".agentweave/check-reports/sweep.xml", "rerun_command": "py -3.11 scripts/checks/sweep_check.py --report .agentweave/check-reports/sweep.xml --rerun {tests}"},
  {"name": "hub-ui", "command": "cd hub/ui && (node -e \"process.exit(require('fs').existsSync('node_modules')?0:1)\" || npm ci --no-audit --no-fund --prefer-offline) && npm run lint && npx tsc --noEmit && npx vitest run", "timeout_seconds": 1800, "paths": ["hub/ui/"], "fast": false, "phase": "both"},
  {"name": "hub-tests", "command": "py -3.11 scripts/checks/hub_suite.py --report .agentweave/check-reports/hub-tests.xml", "timeout_seconds": 3600, "paths": [], "fast": false, "phase": "landing", "report_path": ".agentweave/check-reports/hub-tests.xml", "rerun_command": "py -3.11 scripts/checks/hub_suite.py --report .agentweave/check-reports/hub-tests.xml --rerun {tests}"}
]
```

## How to tell it took

A failing `sweep` or `hub-tests` result names tests as `hub.tests.<module>.<Class>::<name>`, its
confirmation reads `how: tests`, and its output begins with `hub-suite: re-running 1 test(s)
serially, without the suite lock` (hub-tests) when re-run. A result reading `no report
configured` means the settings were not applied. To read them without the app:

```bash
py -3.11 -c "import sqlite3; c=sqlite3.connect('file:C:/Users/huida/.agentweave/hub/data/agentweave.db?mode=ro', uri=True); print(c.execute('select checks from projects where id=?', ('proj-d85a82bf4216',)).fetchone()[0])"
```

## Rolling back

Put the two commands back to `py -3.11 scripts/checks/sweep_check.py` and
`py -3.11 scripts/checks/hub_suite.py` and clear both report paths and re-run commands. Until the
pytest parsing is retired (task `retire`) the Hub then reads their console as before; after it,
they are judged as whole checks.

## Earlier: one full suite at a time (2026-11-04)

Spec `agentweave-s-checks-fit-a-busy-machine`, FR-9 moved `hub-tests` to
`scripts/checks/hub_suite.py` (one full suite at a time, workers from CPU idle) and added `sweep`
(`scripts/checks/sweep_check.py`, the tests that scan the tree). Its rollback was
`py -3.11 -m pytest hub/tests -q -n auto --dist loadgroup -p no:cacheprovider --timeout=600` for
`hub-tests` and removing `sweep`.
