# Handoff: Phase 3 task 3.17 complete — README documents the native one-command Hub flow

**Date:** 2026-08-01T17:46:36+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `7373716`
**Agent:** T3 Code / Codex (gpt-5.6-sol)
**Previous handoff:** `.claude/handoffs/2026-08-01-1541-task-3-12-alembic-packaging-complete.md`
**Status:** chunk complete

## Goal

Continue the `openspec/changes/2026-07-30-hub-native-experience/` change, which makes the
native Hub own agent execution and removes Docker/watchdog ceremony from the normal local path.
This chunk completed Phase 3 task 3.17: make the README describe the actual one-command start.

## Current state

Task 3.17 is complete and committed at `7373716`. The README quick start now installs the CLI and
Hub into one uv tool environment, starts the native Hub with `agentweave hub start --app`, and
explains direct Claude/Codex execution without a watchdog. Related environment, database,
development, package-layout, mode-table, and FAQ text was made consistent with tasks 3.1 and
3.12–3.16. The next task is 3.18, an end-to-end runtime verification task; it has not begun.

The handoff loaded at session start was stale relative to the branch: HEAD had already advanced
from `07d657d` through the pilot-mode spec update and completed tasks 3.15 and 3.16. That drift was
reconciled from git history, and none of those completed tasks was repeated. A pre-existing dirty
`README.md` contained the beginning of task 3.17; it was audited, completed, and included in the
task commit rather than overwritten.

## Files touched

- `README.md` — finished and committed; rewrote Quick Start from three runtime commands to the
  native `hub start --app` flow, documented uv/pipx/pip installation, and corrected related native
  database, source-development, package-layout, mode, and FAQ claims.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — finished and committed; checked
  task 3.17 and recorded the concrete documentation changes.
- `.claude/handoffs/2026-08-01-1746-phase3-task-3-17-readme-complete.md` — this checkpoint; new.
- `.claude/handoffs/LATEST.md` — updated to point at this checkpoint.

Six unrelated, pre-existing untracked `.claude/handoffs/*.md` files remain untouched; they are
listed under Git state.

## Key decisions

1. Treated “one-command flow” as one start command after installation: `agentweave hub start
   --app`. Installation remains an explicit prerequisite because the CLI and Hub are separately
   published Python distributions. Rejected retaining `init` → `activate`: that is the old
   watchdog-managed path the change is replacing.
2. Documented `uv tool install agentweave-ai --with agentweave-hub` as the primary install so both
   distributions share one tool environment. Kept pipx and pip as supported fallbacks, matching
   OpenSpec decision 0.1. Rejected documenting only `pip install agentweave-hub`, because that does
   not install the `agentweave` CLI that owns `hub start`.
3. Did not claim users can add projects in the dashboard. Phase 10 multi-project UI/API is not
   implemented yet. The README instead says to configure Claude or Codex agents in the dashboard.
4. Included the pre-existing README edits for `AW_HOST`, native SQLite persistence, native Makefile
   development, and package layout because they are correct consequences of already-completed
   Phase 3 work and prevent the new quick start from contradicting later sections.

## Constraints and user directives (verbatim)

- Carried from the standing session chain: **“Yeah and always commit the changes.”**
- Carried from the standing session chain: **“After every threshold of implementation you must
  run the skill `/handoff`”**
- Carried from the standing session chain: **“Before starting a new implementation revise the
  entire session for the spec”**
- Carried from the standing session chain: **“let's make sure it works with claude and codex first
  locally”**
- Repository rule: never commit runtime `.agentweave/` state; stage explicitly rather than using
  `git add -A`.

## Dead ends

- The initial README wording said “Add a project … in the dashboard.” This was caught before
  commit: Phase 10 multi-project support is still queued, so the text was corrected to configuring
  Claude/Codex agents without promising project creation.
- The session-start `LATEST.md` pointed to the task 3.12 handoff even though live HEAD already
  contained tasks 3.15 and 3.16. Git history, task checkboxes, and the current diff were used to
  reconcile reality; following that handoff’s old next step would have duplicated finished work.

## Verification

Ran and passed:

- `git diff --check` — clean before commit.
- `git diff --cached --check` — clean before commit.
- `uv tool install --help | Select-String -SimpleMatch '--with <WITH>'` — confirmed this installed
  uv supports the documented `--with` option.
- `agentweave hub start --help | Select-String -SimpleMatch '--app'` — confirmed the documented
  start flag is present.
- Explicit-path commit succeeded: `7373716 Complete Phase 3 task 3.17: document one-command Hub
  start` (2 files, 33 insertions, 48 deletions).

Not tested:

- No package installation was performed; command syntax was checked from local CLI help only.
- The Hub was not started and no browser was opened in this documentation-only chunk.
- No Python/UI test suite was run because only Markdown changed.
- Task 3.18’s trigger/output/failure/shutdown scenarios have not been exercised yet.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `7373716`.
- No upstream is configured; nothing was pushed.
- Tracked implementation tree was clean immediately after the commit.
- Pre-existing untracked files, intentionally untouched:
  - `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
  - `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
  - `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md`
  - `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md`
  - `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md`
  - `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md`
- This handoff and `LATEST.md` are expected to be committed in a separate checkpoint commit,
  following the existing chain convention.

## Next steps

1. Read task 3.18 in `openspec/changes/2026-07-30-hub-native-experience/tasks.md`, then inspect
   `hub/tests/test_agent_trigger.py`, `hub/hub/api/v1/agent_trigger.py`,
   `hub/hub/pty_runner.py`, and `hub/hub/run_reconciliation.py` to design an end-to-end verification
   matrix for exactly three required cases: direct trigger/output with no watchdog, a missing
   binary with a stated reason, and Hub death mid-run leaving no orphan plus an interrupted run.
2. Run those scenarios locally with Claude and Codex first, preserving real logs/database evidence
   and avoiding disruption to unrelated running processes. Add/fix tests only if verification
   exposes a gap.
3. Mark task 3.18 complete only when all acceptance cases have concrete evidence, run proportionate
   test/lint checks, and commit explicitly by path.
4. Complete Phase 3 task 3.19 by running `/handoff` at that next checkpoint.

## Open questions for the user

None blocking. The branch still has no upstream; pushing has not been requested.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — task 3.18 acceptance cases and the
  completed Phase 3 trail.
- `hub/hub/api/v1/agent_trigger.py` — direct spawn, lifecycle events, output capture, and stop path.
- `hub/hub/pty_runner.py` — process ownership and termination behavior.
- `hub/hub/run_reconciliation.py` — startup transition from abandoned in-progress runs to
  interrupted.
- `hub/tests/test_agent_trigger.py` — existing direct-execution coverage to map against task 3.18.
- `README.md` — the just-committed one-command flow; do not rework it during runtime verification
  unless evidence proves it inaccurate.
