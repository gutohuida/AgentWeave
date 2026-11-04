# This project's check settings (`:8000`, `proj-d85a82bf4216`)

Spec `agentweave-s-checks-fit-a-busy-machine`, FR-9. The check settings live in the operator's
Hub database, which agents never write: **the operator applies them**, in the app under
Settings → General → Checks. What follows is the exact text to enter. Read back, `mode=ro`, on
2026-11-04 the settings were ruff (fast), black (fast), hub-ui and hub-tests, all phase `both`,
with `checks_give_way` on.

## The two changes

**1. Edit `hub-tests`: replace its command.** Leave everything else as it is (timeout 3600, no
paths, not fast, phase "Before review and at landing"), so the full suite still runs on every
task and on every landing.

| Field | Value |
|---|---|
| Name | `hub-tests` |
| Command | `py -3.11 scripts/checks/hub_suite.py` |
| Timeout (seconds) | `3600` |
| Paths | *(none)* |
| Fast | off |
| When | Before review and at landing (`both`) |

The command with no arguments runs `hub/tests -q --dist loadgroup -p no:cacheprovider
--timeout=600` with `-n` chosen from the CPU idle share (the old command's `-n auto` is what it
replaces; its trailing `600.` was a typo the new default drops). A run that waits its turn spends
the wait inside the 3600 s limit; 3600 is the most the Hub accepts.

**2. Add `sweep`, marked fast.** Put it after black.

| Field | Value |
|---|---|
| Name | `sweep` |
| Command | `py -3.11 scripts/checks/sweep_check.py` |
| Timeout (seconds) | `120` |
| Paths | *(none)* |
| Fast | on |
| When | Before review and at landing (`both`) |

120 s is the most a fast check may have (`FAST_CHECK_MAX_SECONDS`). Measured on this machine with
other agents working, 2026-11-04: 756 passed in 83.7 s, 1 min 31 s wall. That is inside the limit
but not by much: if `sweep` starts timing out on a busy machine, untick Fast and raise its timeout
(it then runs with the rest, still before review) rather than raising the limit.

## The whole list, as it reads after the change

```json
[
  {"name": "ruff", "command": "py -3.11 -m ruff check src/ hub/ tests/ && py -3.11 -m ruff check scripts/ --select E9,F63,F7,F82,F401,F841", "timeout_seconds": 120, "paths": [], "fast": true, "phase": "both"},
  {"name": "black", "command": "py -3.11 -m black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/", "timeout_seconds": 120, "paths": [], "fast": true, "phase": "both"},
  {"name": "sweep", "command": "py -3.11 scripts/checks/sweep_check.py", "timeout_seconds": 120, "paths": [], "fast": true, "phase": "both"},
  {"name": "hub-ui", "command": "cd hub/ui && (node -e \"process.exit(require('fs').existsSync('node_modules')?0:1)\" || npm ci --no-audit --no-fund --prefer-offline) && npm run lint && npx tsc --noEmit && npx vitest run", "timeout_seconds": 1800, "paths": ["hub/ui/"], "fast": false, "phase": "both"},
  {"name": "hub-tests", "command": "py -3.11 scripts/checks/hub_suite.py", "timeout_seconds": 3600, "paths": [], "fast": false, "phase": "both"}
]
```

## How to tell it took

On the next task that completes, its check run shows `sweep` deciding with ruff and black, before
`hub-tests` starts, and `hub-tests`' output begins with the entry point's lines:

```
hub-suite: started at <time> (pid <n>)
hub-suite: <n> workers (CPU idle <share>% on <cpus> logical CPUs)
```

A landing batch's run still lists `hub-tests`. To read it without the app:

```bash
py -3.11 -c "import sqlite3; c=sqlite3.connect('file:C:/Users/huida/.agentweave/hub/data/agentweave.db?mode=ro', uri=True); print(c.execute('select checks from projects where id=?', ('proj-d85a82bf4216',)).fetchone()[0])"
```

## Rolling back

Put `hub-tests`' command back to `py -3.11 -m pytest hub/tests -q -n auto --dist loadgroup -p
no:cacheprovider --timeout=600` and remove `sweep`. Nothing else changed.
