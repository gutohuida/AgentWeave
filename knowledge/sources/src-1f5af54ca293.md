# Project checks for AgentWeave: all five are green on master (2026-10-24, commit 3a083d7)

This note supersedes the "turn them on in stages" advice in the earlier note on project checks
(src-2c4713ed8e82). Master is now green on every check. All five can be enabled in
**Settings → General → Checks** for project `proj-d85a82bf4216`, in this order:

| Order | Name | Command | Timeout (s) | Time on 3a083d7 |
|---|---|---|---|---|
| 1 | `lint` | `py -3.11 -m ruff check src/ hub/ tests/ && py -3.11 -m ruff check scripts/ --select E9,F63,F7,F82,F401,F841` | 300 | 3 s |
| 2 | `format` | `py -3.11 -m black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` | 300 | 22 s |
| 3 | `types` | `py -3.11 -m mypy src/` | 300 | 24 s |
| 4 | `cli-tests` | `set PYTHONPATH=src&& py -3.11 -m pytest tests/ -q -n auto -p no:cacheprovider --deselect tests/test_skill_sync.py` | 900 | about 1 min (574 passed) |
| 5 | `hub-tests` | `cd hub && py -3.11 -m pytest tests/ -q -n auto --dist loadfile --timeout=300 --timeout-method=thread -p no:cacheprovider` | 3600 | 20 min (8875 passed, 0 failed) |

All five were run on a scratch checkout of 3a083d7, the way the Hub runs checks (cmd.exe, run from
the checkout's root). Every one exited 0.

## Why each command has the shape it has

- **`cd hub` and `set PYTHONPATH=src`.** Without them, the suites import the main checkout's
  editable install and test the wrong code. From these directories, `hub` and `agentweave` resolve
  to the scratch checkout being checked.
- **`--deselect tests/test_skill_sync.py`.** That test compares the repository's skills against
  machine-local mirrors (`~/.codex/skills`, `.agents/skills`). A task that edits a skill would fail
  it until someone runs `py -3.11 scripts/sync_skills.py`, and the failure would be charged to the
  task. It is machine hygiene, not a code check; it still runs in an ordinary `pytest tests/`.
- **`hub-tests` timeout 3600.** The suite takes about 20 minutes. When it fails, the Hub runs it
  again on master to see whether the failure is the task's, so a red task costs about 40 minutes.
- **The UI checks (`npm run lint`, `tsc`, `vitest`) are still left out.** A scratch checkout has no
  `node_modules`. They pass on 3a083d7: 226 test files, 2305 tests.

## What made master green

- **Lint and format:** `black` on `chapters_job.py` and `test_manager_jobs.py`, and ruff fixes in
  `hub/ui/mock/drive_thread.py`.
- **Project-delete tests:** `chapter_versions` was added to the test's expected list of tables.
- **Surface ceilings:** the board now reads the error of a task opened by id.
- **Context snapshot:** updated for slice 2's `read_chapters` and `save_chapters` tools.
- **Six tests that failed only under parallel load** (announce wait, checks gate, thread feed,
  slow share, real-process startup): each still tells blocked from prompt, but with headroom. They
  passed in the parallel run beside live agents.
- **Codex skill mirror:** re-synced.

## A caveat

A timing-sensitive test can still fail on a heavily loaded machine. If it fails on the task's run
but passes on master's re-run, the failure is charged to the task, and the task is sent back
although its work is fine. If it fails on both, the Hub holds the approval for the operator
(`hub/hub/requirement_gate.py`). When a check failure names a timing test that the task did not
touch, treat it as a flake and re-run the checks before reworking anything.
