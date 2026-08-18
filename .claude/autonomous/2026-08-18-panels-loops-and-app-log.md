# Autonomous run — panels, loops, and the app

**Branch:** `autonomous/2026-08-18-panels-loops-and-app`
**Parent:** `panel-shell/2026-08-18-tab-store` @ `8d52a93` (itself one commit ahead of `master` @ `024bf72`)
**Window:** 2026-08-18 21:30 → 2026-08-19 08:00 (+01:00)
**Driver:** Windows Scheduled Task → headless `claude -p`, one iteration per firing.

Newest entry at the **bottom**.

---

## Entry 0 — preparation (interactive, operator awake)

Written by `/autonomous-prep` before the run started. The operator was awake for this entry and
asleep for every one after it.

### What the operator asked for, verbatim

> *"I want you to work on both specs. The side panel and the loop. Testing of the UI should be done
> using playwright. If you finish both specs I want you to work on making the app experience for
> agentweave better. Having a desktop icon would be nice. You can clear all project from the test
> hub. The autonomous run should go until 8AM. If all of that is done you can decide on whatever you
> want to work, fixing anything outstanding or whatever we need. Prepare the autonomous run and
> trigger it. I'm off for the night"*

Plus one limit, chosen explicitly from a list: **no merging to master unattended.**

Intent was asked **before** the handoff or git log were opened, per the skill — so the target is not
shaped by what was last built.

### What landed before the run (interactive)

Panel change **section 1 is done**: `hub/ui/src/store/panelTabsStore.ts` plus 27 tests, committed as
`8d52a93` and pushed. That is the parent this run branches from. Verified non-vacuous by mutation
probe rather than assumed — disabling `normalize` fails exactly the four restore-rule tests, and
making the migration chain accept an unknown version fails exactly the stale-shape test.

`hub/seed_taste_doc.py`, untracked and ruff-failing since the previous session, was moved to
`testbed/scratch/seed_taste_doc.py` on the operator's instruction. `ruff check src/ hub/ tests/` is
now clean repo-wide for the first time since it appeared.

### What was measured, not assumed

| Check | Result |
|---|---|
| Browser suite (live Hub) | **33 passed**, 17.26s |
| UI vitest | **1014 passed**, 101 files |
| eslint / `tsc --noEmit` | clean |
| ruff (`src/ hub/ tests/`) | All checks passed |
| black | 403 files unchanged |
| openspec strict | 2 changes, 32 specs |
| `hub/tests/test_migrations.py` | 51 passed, 1 skipped |
| mypy `hub/hub/` | **361 errors, 86 files — pre-existing** |

A full `hub/tests` run was still in flight when prep ended; the first iteration confirms it.

### Stalls found and removed before the run

1. **`mypy` clean is impossible.** Loop task 12.2 demands it; the repo has 361 pre-existing errors
   across 86 files. Baselined to `.claude/autonomous/mypy-baseline.txt` and the task rescoped to
   "introduced no new errors". Without this the run would have met a wall at 3am and either burned
   hours or guessed.
2. **CI cannot see a branch push.** `ci.yml` triggers only on push to `master` or a PR to `master`,
   while the standing rule is "full auto, but only on green CI". Pre-authorised **one draft PR**,
   never marked ready, never merged — the only way to get the signal without merging.
3. **"Clear all projects" collides with a protected project.** Four projects existed. Deleted the
   stray `Agentweave` registration pointing at `<repo>/hub`, which CLAUDE.md explicitly says to
   delete if it appears. Kept `proj-5e960453` (the browser suite's fixture) and `proj-ff695d96`
   (aw-loop10 — protected by CLAUDE.md, three handoffs, and an executable guard). Flagged for the
   operator; deleting aw-loop10 is irreversible and they were asleep.
4. **The Playwright runway was unproven for this run.** Now proven: 33 passed against the live Hub,
   and the Hub is an **editable install** pointing at this repo, so a UI rebuild is served without a
   restart. Recorded in `STATE.json.environment` with the exact commands.
5. **The build stamp has a trap that would have bitten immediately.** Its fingerprint enumerates via
   `git ls-files`, so an untracked new source file is invisible to it. The first `refresh_ui_bundle.py`
   run of the session recorded a stamp that would have gone stale the instant the commit landed. The
   rule — `git add` before stamping — is now in `STATE.json.environment.ui_rebuild`.
6. **A false-green pattern was reproduced live.** Two concurrent `pytest` invocations produced a
   spurious "no tests ran" *and* a spurious "2385 skipped". Both directories pass when run alone.
   Recorded in `traps` so an iteration does not read either as inherited breakage.

### Queue shape

32 items, interleaving both changes deliberately so neither is starved — that is "work on both
specs" made concrete. Panel shell first (P2a, P2b, P3) because it is operator-visible and unblocks
the loop change's B5/B6, then loop foundations, then the two changes alternate. App experience
(APP1 desktop icon, APP2) is last because the operator made it conditional on finishing both specs.
`src/agentweave/assets/icon.ico` already exists and APP1 should reuse it.

**Honest scoping note:** 124 tasks remain across the two changes. A night will not finish both. The
queue is ordered so that what does get done is the highest-value, dependency-respecting slice, and
so the run never runs dry and starts inventing work.

### What a reviewer should distrust in the morning

- Everything after this entry was written with nobody checking it.
- The run tests its own work, which inherits its own blind spots. A finding it did *not* make is
  weaker evidence than one it did.
- Human-only sections (panel 7.x, loop 13.x, A6.x, B7.x) must still be unticked. If any are ticked,
  that is a defect in the run, not a completed task.
