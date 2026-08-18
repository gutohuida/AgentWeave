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

---

## Entry 1 — iteration 1: P2a, the panel shell component (2026-08-18 21:29-21:36)

Between entry 0 and this iteration's start, a small correction commit (`9e5b961`, "Correct the prep
note: the hub suite was killed at 61%, not passed") landed on this same branch and was already
pushed to origin by the time this iteration began — the prep session's own tail end, not a second
concurrent session. Confirmed by `git fetch` that origin has nothing beyond it: no race, just a
sequential handoff. `STATE.json.environment.hub_pytest` now correctly says the full hub suite is
**unverified**, not passed, and asks iteration 1 to confirm it. Not done this iteration — see below.

**Work done: P2a — tasks 2.1, 2.6, 2.7 of `2026-08-18-one-shell-three-panels`.**

Read `panelTabsStore.ts` (section 1, already built/tested), `tasks.md`, `design.md` D1-D12,
`Icon.tsx`'s glyph map, `RowMenu.tsx` (an existing Radix-`DropdownMenu`-based menu with its own
keyboard contract already solved), and `ConversationView.tsx:150-291` (the block P2b re-hosts,
read for styling convention only — not touched this iteration).

Built `hub/ui/src/components/spec/PanelShell.tsx`: a shell owning the tab strip, the plus
affordance, and the visible tab's content, rendering exactly one tab at a time. Deliberately
generic — `availableTabs` / `describeTab` / `renderTabContent` props — so it knows nothing about
specs or files; section 3 (specs as the first tenant) and section 5 (files) plug in without
re-plumbing, which is the entire reason tasks.md orders 1→2→3 before 4/5. Consumes
`panelTabsStore` directly via the Zustand hook, matching how the store's own tests and every other
project-scoped store in this codebase are read.

**Task 2.6 (keyboard):** chose **automatic activation** — the WAI-ARIA APG's other supported
`tablist` variant, arrow keys move focus and activate together, roving `tabIndex` keeps only the
active tab in the page's `Tab` sequence, `Enter`/`Space` activate for free via native `<button>`
semantics (no bespoke handler needed). The close control is a second ordinary button inside the
same tab, reached by `Tab` right after it, deliberately outside the arrow-key roving set. This is a
stated choice, not a guess — the task's bullet order ("Enter/Space to activate" listed before "arrow
keys between tabs") could also read as the *manual*-activation variant; D11 says nothing exists to
inherit here, so the choice and its reasoning are recorded in `tasks.md` rather than left implicit.
The plus affordance reuses `RowMenu.tsx` rather than a new menu — its Radix `DropdownMenu` already
has a full, tested keyboard contract (see `rowMenus.test.tsx`), so building a second one would be
exactly the kind of duplicated mechanism D1's reasoning warns against for a different part of this
same change.

**Task 2.7 (icons):** audited `Icon.tsx`'s `ICONS` map before writing any glyph reference, per the
task's own instruction. `close` → `X` and `add` → `Plus` both already exist; no new mapping needed.
Every glyph in the strip goes through `Icon` — nothing in `PanelShell.tsx` imports `lucide-react`
directly.

**Verification, measured:**
- 14 new vitest cases in `hub/ui/src/__tests__/panelShell.test.tsx`: empty state (not an empty grey
  box — task-8 user guide step 1), exactly-one-tab's-content-visible, opening from the plus menu,
  the plus menu omitting already-open tabs and hiding once nothing is left to add, closing a
  background tab without stealing activation, closing the last tab returning to the empty state,
  and 8 keyboard-specific cases (roving `tabIndex`, `ArrowRight`/`ArrowLeft` wrap in both
  directions, `Home`/`End`, `Enter`/`Space` activation, close-by-keyboard, plus-trigger-by-keyboard).
- Full UI suite: **1028 passed across 102 files** (was 1014 at prep — 14 new, zero regressions).
- `eslint --max-warnings 0`: clean. `tsc --noEmit`: clean (one real type error caught and fixed —
  the strip's keydown handler was typed against the wrong event target).
- `npx openspec validate --changes --strict`: 2/2 changes still pass.
- Marked 2.1, 2.6, 2.7 done in `tasks.md` with dated notes in the same style section 1 used,
  including the 2.6 activation-variant reasoning and what 2.1 deliberately does not yet do (not
  mounted anywhere — that is 2.2, a separate task; the empty state exists but has no real tenant).

**Not done, and why:** `PanelShell` is not mounted into `ConversationView` yet (2.2-2.5, this
iteration's `next_action`), so nothing operator-visible changed and there is nothing yet to drive
with Playwright — the operator's Playwright requirement becomes exercisable once P2b lands a real
mount point. The full `hub/hub` pytest suite the corrected prep note asks iteration 1 to confirm
was not run: this iteration touched zero Python (`hub/ui/src` and `openspec/` only, confirmed via
`git status --porcelain` before staging), so the suite's result is still exactly what it was at
prep — inherited from master's last CI run (2335 passed) and not independently reverified. Left for
whichever iteration first touches `hub/hub/*.py` (likely an `L*` loop-migration task), since running
a 30+ minute suite for a change that cannot have touched it would burn runway without adding
evidence.

Committed as `77dfd5b` on top of `9e5b961`, pushed. `current`/`next_action` now point at **P2b**
(tasks 2.2-2.5: mount the shell into `ConversationView`, generalize the breakpoint, the overlay,
the width) with the P2a↔section-3 sequencing question named explicitly for whoever picks it up, and
an explicit instruction to exercise it with Playwright against the live trial Hub once mounted —
not deferred again.
