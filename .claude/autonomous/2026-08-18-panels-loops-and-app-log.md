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

## Entry 2 — iteration 2: P2b, mounting the shell (2026-08-18 21:45-22:01)

Fresh process. Read `STATE.json`, verified `git log` matched exactly (`352dfd2` release-heartbeat
tip), confirmed a clean tree before starting. Read `PanelShell.tsx`, `panelTabsStore.ts`,
`ConversationView.tsx:1-310` and `SpecDocumentPanel.tsx`'s breadcrumb/close section first, per
`next_action` and `read_first`.

**Work done: P2b — tasks 2.2-2.5 of `2026-08-18-one-shell-three-panels`.**

`ConversationView` now mounts `<PanelShell projectId={projectId} availableTabs={[]} ...>` in place
of the bare `<SpecDocumentPanel>` it built by hand. `projectId` is a new required prop, threaded
from `App.tsx`'s `destination.projectId`; four test files that render `ConversationView` directly
(`specWorkspace`, `specChatSurface`, `specNavigationUi`, `specDriftReport`) got a fixture project id
and a `usePanelTabsStore.setState({ projects: {} })` reset in `beforeEach`, matching the pattern
`panelShell.test.tsx` already established.

**The path-keyed, single-tab decision (2.2), stated rather than guessed** — this component only
ever held a document *path*, never an id, so the tab it opens is `spec:<path>`, not the durable
`spec:<document_id>` key section 3 will switch to. Two `useEffect`s keep the destination and the
store in sync both ways: a `document` prop change closes the previous path's tab and opens the new
one; the tab strip's own close button (which calls the store directly, bypassing `onOpenDocument`)
is caught by a second effect that re-reads `usePanelTabsStore.getState()` live rather than trusting
a subscribed value from the same commit — needed because within one render, an effect that just
called `openTab` has already mutated the module-level store before a *later* effect in the same
commit runs, but that later effect's own subscribed prop is still the pre-mutation snapshot. Traced
through by hand before writing it, since a naive "check the subscribed tabs array" version would
have raced and wrongly nulled the document on every `document` prop change.

**Task 2.3's generalization**, done honestly rather than cosmetically: `specPreferences.ts` gained
`minWidthForTabKind(kind: TabKind | null): number`, and `ConversationView` now derives its
breakpoint, `conversationMax`'s subtraction, and the document-pane's own `minWidth` from
`minWidthForTabKind(tabKind(panelActiveTabId))` — one source, not three places that could disagree.
Today every kind still resolves to `SPEC_DOC_MIN_WIDTH` (files have no measured minimum until task
5.5), so behaviourally nothing changed yet — the seam exists for section 5 to fill in, which is what
"generalize" asked for at this point in the sequence, not a new number. `DOCUMENT_COLUMN_BREAKPOINT`
stays exported as a constant so the ten-odd existing test assertions that treat it as one keep
working; the component itself no longer reads that export for its actual layout decision.

**An honest, unscoped observation for whoever picks up section 3**, recorded in `tasks.md` rather
than silently left for someone to rediscover: because the store persists tabs per project
independent of this component's lifecycle, a `ConversationView` instance that unmounts (navigating
away from the conversation destination kind entirely) and remounts on a *different* conversation
that opens a *different* document can leave the first document's tab sitting in the strip alongside
the new one — the forward-sync effect only closes the *previous* tab it itself opened, and a fresh
mount does not know what a previous instance last had open. This is not a bug: it is section 1's
per-project tab memory doing exactly what it was built to do, surfacing before section 3's real
multi-tab UI exists to make it legible. Flagging it because 2.2's framing ("the shell's one tenant")
undersold what can actually appear on screen already.

**Verification, measured — not just vitest this time, per the operator's explicit instruction:**
- UI vitest: **1028 passed across 102 files** (unchanged from P2a — no tests added here, all
  existing coverage still green with the new mount).
- `eslint --max-warnings 0` and `tsc --noEmit`: both clean.
- `npx openspec validate --changes --strict`: 2/2 changes still pass.
- **Playwright, against the live trial Hub (`:8010`), for the first time this run — 6 new tests in
  `hub/tests/browser/test_panel_shell.py`, full package 39 passed** (33 prior + 6 new):
  the document opens inside the shell with breadcrumb/phase bar intact; the tab strip's own close
  button closes the document; the narrow-window overlay hosts the shell and survives a
  dismiss-then-reopen with the same tab; the composer's own "Close the document" pill also tears
  the shell down (a third close path, unaffected by this task but only correct if it still routes
  through the same sync); starting from a bare conversation and attaching a document through the
  Ctrl+K picker mounts the shell (the path most conversations actually take, not just the deep-link
  `_open` helper); and the ordinary wide-window two-column case. Rebuilt the UI (`npm run build` +
  `refresh_ui_bundle.py`) before running any of this, and confirmed `/health` no longer reports
  `ui_stale` — the trial Hub is an editable install, so this was the only step needed for it to serve
  the new mount.
- **Which project, and why it had to be a different one than usual:** the browser suite's default
  fixture (`proj-5e960453`, this repo's own registration) has **zero agents** —
  `test_command_palette.py` already documents this as a standing gap, since a conversation
  destination requires one. `proj-b44fac0c` ("Throwaway (taste pass)", already flagged disposable in
  `STATE.json`) has a real agent (`q2verify`) with a real conversation and a real specification
  document, so the new tests read from it — never mutating it — rather than creating a throwaway
  agent in the protected fixture project.
- ruff (`src/ hub/ tests/`) and black: both clean after removing an unused `pytest` import and
  accepting black's one reformat of the new test file's long function signature.
- Did **not** re-run the full `hub/pytest` suite: this iteration touched zero Python besides the new
  browser-test file (which the browser-suite run above already exercises), so the prior iteration's
  reasoning for deferring it still holds — inherited from master's last CI measurement, not
  independently reverified this iteration either.

**Not done, and correctly deferred:** section 3 (specs as the shell's first real, id-keyed,
multi-document tenant) is the next task — P2b's temporary path-keyed single-document sync is
explicitly what it replaces, not extends. PW1 (the queue's dedicated Playwright-coverage item) stays
open rather than being marked done: today's 6 tests cover P2b's re-hosting, not sections 3/4/5's
tenants, which do not exist yet to test.

Committed, pushed. `current`/`next_action` now point at **P3** (tasks 3.1-3.6: specs as the shell's
first tenant — a `specs` index tab, id-keyed `spec:` tabs replacing this iteration's path-keyed
sync, unfusing attach from display per D9, and the 3.6 regression pass this iteration's Playwright
tests partially anticipated but did not substitute for).

## Entry 3 — iteration 3: P3, specs as the shell's first tenant (2026-08-18 22:05-22:40)

Fresh process. `git log` matched `cfc0a3e` exactly, tree clean. Read `tasks.md` section 3, `design.md`
D9/D4/D12, `panelTabsStore.ts`, `PanelShell.tsx`, `ConversationView.tsx`, `SpecDocumentPicker.tsx`,
and `specNavigation.ts` per `next_action` and `read_first` before writing anything.

**Work done: P3 — tasks 3.1-3.6 of `2026-08-18-one-shell-three-panels`.**

**The path<->id question, resolved by checking rather than guessing.** `next_action` explicitly said
not to assume either way. `SpecEntry`/`SpecNode` carried no document id at all — `GET /project/specs`
enriched entries with `phase` from `spec_lifecycle.list_documents` but never with `id`, even though a
different endpoint (`GET /project/documents`) already returned one for Hub-tracked documents. Added
`document_id` to the same enrichment `phase` already goes through (`hub/hub/api/v1/spec.py`), one
`tracked` map read twice. Not every document has one — a filesystem discovery with no `spec_documents`
row (never created through the Hub) reports `document_id: null` — so `specNavigation.ts` gained
`SpecNode.documentId: string | null` plus exactly two functions, `tabKeyForNode`/`resolveTabPath`,
that are the only places a tab's key is made or unmade (id if present, else the path). New backend
test: `test_the_specs_tree_carries_the_document_id_the_panel_shell_keys_tabs_by`.

**3.1 (specs index tab):** extracted the picker dialog's search/browse content into a new,
chrome-free `SpecDocumentBrowser.tsx` (shared by `SpecDocumentPicker`'s dialog and a new
`SpecIndexTab.tsx`), rather than duplicating the search-and-rank logic a second time. Selecting a
node in the index tab calls the tab store's `openTab` directly — never `onOpenDocument` — which is
what makes the unfuse structural rather than a rule to remember. Added to `ConversationView`'s
`availableTabs` as a fixed `specs` entry.

**3.3 (the actual unfuse, D9):** two fused paths existed, not one. Deleted P2b's store-watching
effect outright (the one that called `onOpenDocument(null)` when a tab it opened disappeared) — not
made conditional, removed, because D9 says a closed reader must never detach the agent's document.
Also rewired `SpecDocumentPanel`'s own in-panel close button (`spec-document-close`), which was a
*second*, undocumented fused path straight to `onOpenDocument(null)`, to call `closeTab` instead —
now identical in meaning to the tab strip's own close button. `onSelectPath` (in-document link
navigation) was deliberately left wired to `onOpenDocument`: a pinned regression test
(`'routes a valid relative cross-document link through the destination'`) locks that behavior in, and
D9 states only the composer control is in scope this change. Recorded as an honest, known gap in
`tasks.md` rather than silently accepted — reading a second, unattached tab's internal link can still
reattach the conversation, and fixing it is a design call this task did not make.

**A real bug found by Playwright, not vitest — exactly why the operator asked for it.** The
destination-to-store sync opens the attached document's tab keyed by `tabKeyForNode` (id-or-path).
The first live run against the trial Hub's `proj-b44fac0c` fixture (a document that already carries a
real Hub id) failed `test_closing_the_tab_closes_the_reading_pane_but_not_the_document`: closing the
one visible tab left the document panel showing anyway. Root cause: on first paint, before the specs
list has loaded over the network, `attachedTabKey` falls back to the raw path; once the list loads and
the real id resolves, the key changes and the effect opened a *second*, id-keyed tab without closing
the stale path-keyed one — two tabs for the same document, the close button only closing one. Every
vitest fixture in this codebase provides `document_id` synchronously from the first render, so nothing
in the 1028-test suite could have caught this timing race. Fixed by resolving both the previous and
current keys back to a path before deciding whether to close the previous tab: same resolved path
means the same document merely re-keyed (close it, no duplicate); different paths mean a genuine
attach change (leave the old tab as an ordinary reading tab, per D9). Confirmed non-vacuous by
reverting the fix and re-running a new synchronous vitest regression
(`'closes the fallback path-keyed tab when the inventory upgrades it to a real id...'`) — it failed
exactly as expected, then passed once the fix was restored.

**Verification, measured:**
- UI vitest: **1035 passed across 102 files** (was 1028 at P2b — 7 new: the upgrade-transition
  regression above, plus 6 covering the specs index tab, id-keyed opening/refocus, two-documents-one-
  attached, archived-document-from-the-index, and the rewritten close-button test). `eslint
  --max-warnings 0` and `npx tsc --noEmit`: both clean.
- Backend: `pytest hub/tests/test_spec.py hub/tests/test_spec_archive.py hub/tests/test_spec_rename.py`
  — 47 passed (every existing test reading `GET /project/specs`, to catch anything assuming the
  response's exact shape). `ruff check` and `black --check` clean on every touched Python file.
- **Playwright, against the live trial Hub, restarted to pick up the Python change** (the running
  process was still serving the pre-P3 code; `document_id` read back `None` until restarted — caught
  by directly curling `/project/specs` before trusting any test result). Rebuilt the UI bundle twice
  (once before the duplicate-tab fix, once after) and confirmed `refresh_ui_bundle.py --check` and
  `/health`'s `ui_stale` cleared each time. **41 passed** (33 pre-P2b + 6 P2b + 2 new P3 tests, with
  one P2b-era test rewritten for the new close semantics rather than counted as new). The fixture
  project's only document (`teal-roc/spec.html`) already carries a real Hub id, so the suite's
  `spec_tab_id` fixture now resolves it from the live API rather than hardcoding the old path-keyed
  form — every hardcoded `SPEC_TAB_ID` in the P2b tests would otherwise have silently tested a tab
  the app no longer opens.
- `npx openspec validate --changes --strict`: 2/2 still pass.

**Not done, correctly deferred:** the shell still only mounts when a document is attached
(`documentOpen = document !== null`, unchanged) — there is still no way to open the `specs` index tab
from a bare conversation with nothing attached yet. This matches design D12's own explicit deferral
("whether the shell should subsume the explore button's actions... the operator decides while looking
at the working shell") rather than an oversight; task 3's user-guide step 1 ("press the panel button")
describes a future entry point this task did not build.

Marked 3.1-3.6 done in `tasks.md` with dated notes following section 2's style, including the
path<->id resolution, the D9 unfuse's two fused paths (not one), the deliberate `onSelectPath` gap,
and the live-only duplicate-tab bug and its fix.

Committed, pushed. `current`/`next_action` now point at **PW1** (dedicated Playwright coverage item —
today's section 3 tests satisfy most of what PW1 asked for; whoever picks it up should confirm the
queue's PW1 entry can simply be marked done pointing at this iteration's tests, or state what it still
needs) — but per the queue's stated interleaving, the *next* firing should prefer **L1** (loop:
migration + model) so the run does not spend the whole night on one change, per the operator's
explicit "work on both specs" instruction.

## Entry 4 — iteration 4: L1, loop migration + model (2026-08-18 22:44-22:57)

Fresh process. `git log` matched `0cde7c1` exactly, tree clean. Read `next_action`, design D1/D4, and
the `0075`/`0020` migration precedents before writing anything, per `read_first` and the queue's
interleaving instruction (P3 done last iteration; this one deliberately picks up **L1**, the loop
change, so neither change is starved).

**Work done: L1 — tasks 1.1-1.3 and 2.1-2.2 of `2026-08-18-a-loop-writes-its-own-queue`.**

New migration `hub/hub/migrations/versions/0077_loop_declares_source_and_checkpoint_loop.py`,
`down_revision = "0076"` (reconfirmed via `alembic heads` — single head, nothing else had claimed it).
Two additive nullable columns, guarded for a missing table exactly like `0075`: `loops.
spec_document_id` (design D1) and `checkpoints.loop_id` (design D4). `hub/hub/db/models.py` gained
`Loop.spec_document_id` and `Checkpoint.loop_id` matching.

**A real bug caught by actually running the up/down/up cycle, not by inspection.** Task 1.3 asked for
exactly this, and it earned its keep. The task's own text planned the unique index on
`loops.spec_document_id` as `uq_loops_spec_document_id`. First scratch run (`Base.metadata.create_all`
— what `init_db` does for a fresh install — then `alembic upgrade head`, then `downgrade -1`) failed
`downgrade -1` with `sqlite3.OperationalError: error in table loops after drop column: no such column:
spec_document_id`. Root cause: the model declared `spec_document_id` with `unique=True` alone (no
`index=True`), so `create_all` built the uniqueness as an inline table-level constraint — a SQLite
autoindex (`sqlite_autoindex_loops_N`), not a named index. The migration's downgrade looked for
`uq_loops_spec_document_id` by name, didn't find it (wrong name entirely), skipped dropping it, then
`DROP COLUMN` failed because SQLite refuses to drop a column still part of *any* index, named or not.
Checked whether this codebase already has a working precedent for a nullable, unique, indexed column
added via `ALTER TABLE`: `Run.capability_token_hash` (`models.py:1024-1026`, migration `0020`) declares
`unique=True, index=True` together, which makes SQLAlchemy name the index `ix_<table>_<column>` by its
own default convention — exactly matching `0020`'s explicit `ix_runs_capability_token_hash`. Renamed
this migration's index to `ix_loops_spec_document_id` and added `index=True` to the model to match.
Reran the same scratch cycle (create_all → upgrade → downgrade -1 → upgrade head): clean, columns and
indexes present after re-upgrade, confirmed by directly reading `PRAGMA table_info`/`PRAGMA
index_list` rather than trusting alembic's own "no error" as sufficient. Also ran a second scratch
cycle — pure sequential `alembic upgrade head` against a *truly empty* database, no `create_all` —
which passed cleanly end-to-end (0001→0077→-1→0077 again) for a different reason: `loops`/`checkpoints`
never get far enough to need the new columns until every earlier migration's own table-creation guard
is satisfied in sequence, so this path never exercised the bug at all. Recording both runs rather than
only the one that caught the bug, since a future reader asking "why does 1.3 ask for a *scratch* file
specifically, twice" should be able to see that the two runs test genuinely different things — the
`create_all` path is what real fresh installs hit, and the pure-sequential path is what a database
upgrading from an old, real revision hits.

**Verification, measured:**
- `hub/tests/test_migrations.py`: `HEAD_REVISION` bumped `0076` → `0077`. Added three new tests
  (`test_migration_0077_adds_the_loop_source_document_and_checkpoint_loop_binding`,
  `test_migration_0077_spec_document_id_is_unique_per_loop` — inserts a second loop declaring the same
  document and asserts `sqlite3.IntegrityError`, not `sqlalchemy.exc.IntegrityError` (raw `sqlite3`
  connections raise the driver's own exception type, not the ORM's — caught by the first version of
  this test failing to catch anything at all), `test_migration_0077_downgrade_then_upgrade_round_trips`
  — seeds a real loop with a real `spec_document_id` and a real checkpoint with a real `loop_id`, not
  just empty tables, then downgrades and confirms the rows survive with the binding column genuinely
  gone, then upgrades and confirms the column returns as `NULL` — the upgrade cannot resurrect what
  the downgrade discarded, and the test says so rather than assuming). `hub/tests/
  test_project_persistence.py`'s `version == "0076"` assertion bumped to `"0077"`.
- `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q` — **61
  passed, 1 skipped** (the skip predates this change, unrelated).
- `ruff check` and `black --check` clean on every touched file (`models.py`, the new migration, both
  test files) — black did reformat the migration and the test file once (a line-length wrap and a
  parenthesization), applied and reverified clean.
- `mypy` on the new migration: 3 "missing parameter annotation" errors, identical in shape and count to
  running mypy on `0075_add_loops_and_traceability.py` directly — confirmed by running both, not
  assumed. This is `0075`'s own established style for these migration helper functions (`_tables`,
  `_columns`, `_indexes` all take an untyped `conn`), not a new regression against the session's mypy
  baseline.
- `npx openspec validate --changes --strict`: 2/2 still pass.

**Not done, correctly deferred:** section 3 (`spec_tasks.materialise()` stamping `loop_id`) is
next-in-queue for the loop change — `next_action` explicitly said not to start it this iteration, so
the interleaving with the panel change (currently at PW1) stays honest and this iteration stays one
reviewable unit.

Marked 1.1-1.3 and 2.1-2.2 done in `tasks.md`, including the naming-bug discovery and both scratch
verification runs, in the dated-note style P3's entries in the panel change already established.

Committed, pushed. `current`/`next_action` now point at **L3** (loop: spec materialisation stamps
`loop_id`, tasks 3.1-3.2) — the queue's own written order, not an alternating-per-iteration guess:
the queue groups L1 through L12 together before returning to the panel change at P4, and
`pre_authorised` is explicit — "Follow the queue order as written... Do not reorder to finish one
change first." An earlier draft of this entry incorrectly said P4 was next; caught before commit by
rereading the queue array in `STATE.json` rather than assuming alternation from memory.

## Entry 5 — iteration 5: L3, spec materialisation stamps loop_id (2026-08-18 22:57-23:03)

Fresh process. `git log` matched `3a51a17` exactly, tree clean. Read `next_action`, re-read design D1
(per the instruction not to skip it even though iteration 4 already summarised it), and read
`spec_tasks.py` in full before touching anything.

**Work done: L3 — tasks 3.1-3.2 of `2026-08-18-a-loop-writes-its-own-queue`.**

`hub/hub/spec_tasks.py`'s `materialise()` gained one query right after the empty-declaration
early-return: `select(Loop).where(Loop.spec_document_id == document.id)`, `.scalars().first()`
(unique column, at most one row). Every `Task(...)` the function constructs now sets
`loop_id=owning_loop.id if owning_loop is not None else None`. Reread `materialise_quietly()` before
touching anything else, per the instruction not to assume its relationship to `materialise()` — it is
a thin try/except wrapper that returns `[]` on any exception; confirmed unchanged by reading the body,
not by trusting its docstring.

**Tests, `hub/tests/test_spec_declared_tasks.py`, matching its existing `app`/`auth_headers`/`author`
fixture style** rather than a new one. A `Loop` needs a `job_id`, and there is no `create_loop`
endpoint yet (that's L11, still open), so a new `_declaring_loop()` helper constructs a real `AIJob` +
`Loop` pair directly via the ORM, mirroring `test_scheduler.py`'s `_make_job`/`_make_loop` shape rather
than inventing a third pattern. Three new tests:
- **A document with a declaring loop stamps its tasks** — approves a document with a loop already
  naming it, then confirms both created tasks come back from the real `GET /tasks?loop_id=<id>` filter
  (exercising L1's own query-param path through the actual route, not a raw DB read).
- **No declaring loop stamps nothing** — the default case, asserted directly against `Task.loop_id`
  since `TaskResponse` does not expose the field in JSON (checked `hub/hub/schemas/tasks.py` first
  rather than assuming the board endpoint would show it).
- **Re-approving stamps the loop only on newly-created tasks** — approves once with *no* loop
  declared, *then* a loop declares the document, *then* a revision adds one new declared task and the
  document is re-approved. Confirms the two original tasks still read `loop_id IS NULL` — never
  retroactively touched — while only the new task carries the loop's id. This is the sharpest of the
  three: it proves the binding is evaluated at materialisation time, not backfilled onto a document's
  whole task history the moment a loop claims it.

**Verification, measured:**
- `py -3.11 -m pytest hub/tests/test_spec_declared_tasks.py -q` — **11 passed** (8 pre-existing + 3
  new).
- `py -3.11 -m pytest hub/tests/test_spec_archive.py hub/tests/test_spec_board_task_convergence.py
  hub/tests/test_task_spec_document_context.py -q` — **24 passed**, the other files that already read
  `materialise()`'s output shape.
- Broader sweep, `py -3.11 -m pytest hub/tests/test_spec*.py -q` — **301 passed, 11 warnings**
  (pre-existing FastAPI deprecation warnings, unrelated). Confirms nothing across the whole spec
  surface assumed `loop_id` is always `None`.
- `ruff check` and `black` on both touched files (`spec_tasks.py`, `test_spec_declared_tasks.py`) —
  ruff caught one real issue (`C416`, an unnecessary dict comprehension in the third test, rewritten as
  `dict(rows)`), black reformatted both once after that fix, reverified clean on both tools after.
- `npx openspec validate --changes --strict`: 2/2 still pass.

**Not done, correctly deferred:** section 4 (declaring a source document on loop creation,
`hub/hub/api/v1/jobs.py` — the creation-side half that lets a loop actually claim a document, with the
409-on-conflict behaviour) is next-in-queue; `next_action` explicitly said not to start it this
iteration so this stays one reviewable unit.

Marked 3.1-3.2 done in `tasks.md`, plus corrected the file's own top-of-file summary line ("Sections
1-2 are implemented" → "Sections 1-3") which would otherwise have gone stale the moment 3.1-3.2 were
checked off.

Committed, pushed. `current`/`next_action` now point at **L4** (declaring a source document on loop
creation, tasks 4.1-4.2) — the queue's own written order, continuing straight through the L-series
before returning to the panel change at P4 per `pre_authorised`.

## Entry 6 — iteration 6: L4, declaring a source document on loop creation (2026-08-18 23:05-23:19)

Fresh process. `git log` matched `226518f` exactly, tree clean. Reread design D1 (per the instruction
not to skip it) and D2 (the `create_loop`-vs-widened-`create_job` decision), since D2 turned out to be
load-bearing for a scope question 4.1's own text does not answer: whether `spec_document_id` alone
should opt a plain job into being a loop via `POST /jobs`. D2 settles it — no. Only the agent-facing
`create_loop` tool (still open, L11) states the stricter contract; `POST /jobs` "keeps accepting a job
with `purpose` set and no stop condition exactly as it does today."

**Work done: L4 — tasks 4.1-4.2 of `2026-08-18-a-loop-writes-its-own-queue`.**

`JobCreate` and `JobUpdate` (`hub/hub/schemas/jobs.py`) both gained `spec_document_id: Optional[str]`.
A new `_check_spec_document_conflict()` helper in `hub/hub/api/v1/jobs.py`, placed beside the existing
`_loop_opts_in()`, queries `Loop` scoped to `project_id` and raises `409` naming the conflicting loop's
id — grepped the file for its existing "Job with ID '{id}' already exists" 409 first and matched that
tone rather than inventing a new shape, per the instruction. Wired into `create_job` (checked before
the `Loop` insert, and only inside the existing loop-opt-in branch — a plain `spec_document_id` with no
`purpose`/`stop_at`/`stop_when_queue_empties` still does not create a loop, per D2 above) and into
`update_job` (checked with `exclude_loop_id=loop.id`, so a no-op re-declare of a loop's own document
does not 409 against itself — read literally from 4.1's "not just DB layer" framing, which only makes
sense if a legitimate re-PATCH of your own document is expected to succeed). `update_job`'s existing
`loop_fields_supplied` gate (four fields) widened to five; `spec_document_id` alone still does not opt
a *plain* job into a loop via PATCH either, gated the same way `stop_reason` already is, for the same
D2 reason. `create_job`'s `Loop` insert also gained an `IntegrityError` catch as a race-condition
backstop behind the pre-check, mirroring the existing pattern immediately above it in the same
function for the job-id conflict — not asked for explicitly, but cheap and consistent with the file's
own established style rather than leaving the DB-layer unique constraint as the only guard under a
race.

**Tests, `hub/tests/test_jobs.py`** (grepped for `purpose=` and the `POST /jobs` route first, per the
instruction, rather than guessing a file — confirmed this is where every existing loop test already
lives). Six new tests: the three named in 4.2 exactly —
`test_declaring_a_source_document_on_loop_creation_round_trips` (round-trips via a direct `Loop` row
read through `async_session_factory`, matching `test_spec_declared_tasks.py`'s established direct-DB
pattern, since `LoopSummary` does not expose `spec_document_id` in JSON — checked `schemas/jobs.py`
first rather than assuming it would), `test_a_second_loop_declaring_the_same_document_is_refused`
(409, first loop's id asserted as a substring of `detail`), and
`test_a_loop_can_still_be_created_with_no_source_document` (field omitted, `Loop.spec_document_id is
None` on the row) — plus three more covering the PATCH side of 4.1's own code, which the task list
does not name but which would otherwise have shipped unverified since `JobUpdate` gained the field
too: `test_patch_declares_a_source_document_on_an_existing_loop`,
`test_patch_declaring_a_claimed_document_is_refused`, and
`test_patch_re_declaring_your_own_document_is_not_a_conflict` (the `exclude_loop_id` no-op case).

**Verification, measured:**
- `py -3.11 -m pytest hub/tests/test_jobs.py -q` — **28 passed, 1 skipped** (the skip is the
  pre-existing `CRONITER_AVAILABLE` guard, unrelated to this change).
- `py -3.11 -m pytest hub/tests/test_scheduler.py hub/tests/test_spec_declared_tasks.py -q` — **18
  passed** — the other files reading `Loop`/loop-job creation, confirming nothing there assumed
  `spec_document_id` never exists on a row.
- `ruff check` on all three touched files — clean. `black --check` — reformatted `jobs.py` once (a
  long `select(...)` line wrapped, and a stray two-fragment f-string in the new helper collapsed into
  one), reverified clean after.
- `mypy hub/hub/api/v1/jobs.py hub/hub/schemas/jobs.py` — ran, then filtered output to lines starting
  with the two touched file paths (mypy's own transitive-import chasing otherwise surfaces ~289
  pre-existing errors in unrelated files it pulls in, which would read as a regression if not
  filtered) — **zero lines attributed to either touched file**.
- `npx openspec validate --changes --strict` — 2/2 still pass, both before and after the `tasks.md`
  edit.

**Not done, correctly deferred:** section 5 (creator authorship gate on `create_task`,
`hub/hub/api/v1/tasks.py` + `mcp_server.py`) is next-in-queue — `next_action` explicitly said not to
start it this iteration, and it is a materially different surface (task creation, not loop creation)
from what this iteration touched.

Marked 4.1-4.2 done in `tasks.md`, including the D2-scope reasoning and the PATCH-side tests the task
text didn't name but the code required, in the dated-note style sections 1-3 already established.
Corrected the file's own top-of-file summary line ("Sections 1-3" → "Sections 1-4").

Committed, pushed. `current`/`next_action` now point at **L5** (creator authorship gate on
`create_task`, tasks 5.1-5.4) — the queue's own written order, continuing through the L-series.

## Entry 7 — 2026-08-18T23:39+01:00 — L5 done, creator authorship gate on `create_task`

Branch and `git log` matched STATE.json exactly on read (`b9e8304` at HEAD, iteration 6's release
heartbeat). Continued straight to the queued `next_action`: loop change section 5, the creator
authorship gate on direct `create_task(loop_id=...)` calls.

**Re-derived D7 against D8's collapse before writing anything, per `next_action`'s own warning not
to trust its paraphrase.** Design D8 leaves no field on `Loop`/`AIJob` for "creator" distinct from
`AIJob.agent` — so `_authorize_loop_task_creation` (new, `hub/hub/api/v1/tasks.py`) implements the
whole gate as two checks against that one string: the operator always passes; any other caller must
equal `AIJob.agent` (403 naming `send_message` otherwise); and that same caller, having matched, is
refused (403 naming operator approval) once the job's `run_count > 0`, with the operator exempt from
that second gate too. Worked out — and wrote into the tasks.md dated note — why this makes D7's own
"general case: only the creator adds tasks" phrase reduce to "the operator," and why that's not a
bug: D8's collapse makes every non-operator-privileged loop self-created by construction, which is
exactly the gap the later D10 addendum (queued separately as `LA1`, an explicit per-loop "controller"
field) exists to close. This change ships D7's narrower version on purpose; D10 generalises it later.

**Touched:** `hub/hub/schemas/tasks.py` (`TaskCreate.loop_id`), `hub/hub/api/v1/agent_actions.py`
(`AgentTaskCreate.loop_id`, `create_shared_task` now threads `run_actor(actor.run_id, actor.agent)`
into `create_task_for_actor`), `hub/hub/api/v1/tasks.py` (new `_authorize_loop_task_creation`,
`create_task_for_actor` gains a required `actor: Actor` parameter and stamps `Task.loop_id`, the
operator's own `create_task` route passes `actor=operator()`), `hub/hub/mcp_server.py` (`create_task`
tool gains `loop_id`, forwarded in the POST body).

**Tests:** four new tests in `hub/tests/test_agent_actions_coordination.py` (chosen over
`test_jobs.py` because it already carries the `_active_run` fixture — a real bound-run bearer token
per agent identity — which is what exercising `actor` for real, not just at the ORM layer, needs).
Added a `_loop_with_agent` fixture mirroring `_declaring_loop`/`_make_job`+`_make_loop` rather than
inventing a fourth shape. First run of the two operator-route tests failed 405 (`POST /api/v1/tasks`
doesn't exist — the operator's task route is project-scoped, `/api/v1/projects/{id}/tasks`); fixed
against the `TASKS` constant in `test_evidence_latest_review_signal.py` and reverified.

**Verification, measured:** `pytest hub/tests/test_agent_actions_coordination.py -q` — 23 passed (19
pre-existing + 4 new). `pytest hub/tests/test_jobs.py hub/tests/test_scheduler.py
hub/tests/test_spec_declared_tasks.py -q` — 46 passed, 1 skipped (pre-existing cronite skip).
`pytest hub/tests/test_mcp_body_contract.py hub/tests/test_mcp_tool_schemas.py
hub/tests/test_mcp_server.py -q` — 53 passed. `ruff check` clean on all four touched files plus the
test file. `black` reformatted the new test file once (line-wrapping), clean after. `mypy` on the
four touched files, filtered to their own lines — every error line and count matches
`.claude/autonomous/mypy-baseline.txt` exactly, zero new. `npx openspec validate --changes --strict`
— 2/2.

Marked 5.1-5.4 done in `tasks.md` with the dated note above (fuller version there), corrected the
file's own summary line ("Sections 1-4" → "Sections 1-5").

Committed, pushed. `current`/`next_action` now point at **L6** (claiming the current item,
`hub/hub/scheduler.py`, tasks 6.1-6.3) — a materially different surface (scheduler firing logic) from
everything L1-L5 touched (API routes and schemas).

## Entry 8 — iteration 8: L6, claiming the current item (2026-08-18T23:39-23:54+01:00)

Fresh process. Branch and `git log` matched STATE.json exactly on read (HEAD at the release-heartbeat
commit following entry 7). Read design D3 (`2026-08-18-a-loop-writes-its-own-queue/design.md`) before
touching code, per the instruction not to trust `next_action`'s own paraphrase.

**Work done: L6 — tasks 6.1-6.3, `hub/hub/scheduler.py`.**

New `_claim_loop_task(session, loop) -> Optional[Task]`, placed beside `_loop_stop_reason`. Built it to
mirror `_batch_loop_summaries`'s existing "current item" query (`api/v1/jobs.py:98`, design D7 of
`many-named-loops`) *literally* rather than to the wider `ENTRY_STATUSES` (`pending`/`assigned`)
reading `next_action`'s own paraphrase implied: D3's actual text names only `in_progress`/`blocked`
as the active tier and the oldest **`pending`** task as the fallback — the exact set
`_batch_loop_summaries` already queries, no `assigned`. Deliberately not factored into a shared
function with `jobs.py` — that module is the API layer, `scheduler.py` is not, and introducing a
cross-import for three lines of `order_by` was judged not worth the new coupling; a comment instead
points at `jobs.py:98`/D7 so the duplication is at least discoverable.

Wired into `_do_fire_job`: right after the `_loop_stop_reason` check passes (fire proceeding), a
second `select(Loop).where(Loop.job_id == job.id)` (mirroring the exact same lookup the stop-reason
branch above it already makes) finds the job's loop, and `_claim_loop_task` runs against it. A
`pending` result transitions to `assigned` via `apply_transition(session, claimed_task, "assigned",
operator())` — **not** `run_task_binding`'s `in_progress`: D3's own text is explicit that the scheduler
sets `assigned` at claim time, a deliberately different, earlier mechanism than the run-binding
`in_progress` move, which needs an actual `Run` row that does not exist yet here (the `InboundQueueEntry`
this change creates does not carry a `task_id`, so `resolve_bound_task` never sees this task — wiring
the two mechanisms together is explicitly left to a later section, not assumed here). An already-active
(`in_progress`/`blocked`) claimed task is left untouched; `assignee=job.agent` is stamped in both
branches, per D3's own text describing that as unconditional.

**The transition's actor took two tries.** `origin=ORIGIN_RUNTIME` (the more honest label — this is
the Hub acting, not a person) fails
`test_only_the_binding_module_may_record_a_runtime_transition`, a source scan in
`hub/tests/test_task_transitions.py` that hard-refuses `origin="runtime"` outside
`run_task_binding.py`/`task_transition_service.py`. Caught this by running that suite before
committing, not by reading the scan first — worth recording since it is exactly the kind of guard a
plausible-looking choice trips silently otherwise. Fell back to `operator()` with the default origin
(`ORIGIN_ACTOR`), the same precedent `release_block_for_question` already sets for an automatic,
not-run-bound Hub action; legal (`pending`→`assigned` is a `_BOTH` edge) and its
`resolve_divergences_for_task` side effect is a no-op on a freshly materialised task.

**Tests, `hub/tests/test_scheduler.py`**, extending `_make_job`/`_make_loop` rather than inventing new
fixtures, matching the file's established `bind_runner`+`PtySession.spawn`-patched full-fire pattern:
`test_loop_fire_claims_the_oldest_pending_task` (two `pending` tasks with distinct `created_at`; the
older is claimed and stamped, the newer untouched), `test_loop_fire_resumes_an_active_task_instead_of_
claiming_another` (an `in_progress` task beats a `pending` one regardless of creation order; only the
active task's `assignee` moves), and `test_loop_fire_with_empty_queue_claims_nothing_and_does_not_error`
— deliberately built with a loop carrying **no** `stop_when_queue_empties`, since the existing
queue-empty fixture's stop condition would pre-empt `_claim_loop_task` before it ever ran, which would
have proven the stop check works rather than that the claim step itself no-ops safely on an empty
queue.

**Verification, measured:**
- `py -3.11 -m pytest hub/tests/test_scheduler.py -q` — **10 passed** (7 pre-existing + 3 new).
- `py -3.11 -m pytest hub/tests/test_task_transitions.py hub/tests/test_jobs.py
  hub/tests/test_spec_declared_tasks.py -q` — **105 passed, 1 skipped** (pre-existing cronite skip),
  including the runtime-origin source scan.
- `py -3.11 -m pytest hub/tests/test_run_task_binding.py hub/tests/test_task_transition_service.py
  hub/tests/test_run_divergence.py -q` — **67 passed** — the other suites reading `apply_transition`
  or the binding module.
- `ruff check` clean on both touched files. `black --fast` (the safety-check version-mismatch warning
  is cosmetic — 3.11 running code black itself formatted for 3.12 syntax detection — `--fast` skips
  the redundant AST re-parse) reformatted `test_scheduler.py` once, clean after; `scheduler.py` was
  already clean.
- `mypy hub/hub/scheduler.py`, filtered to its own lines — six error lines, matching
  `.claude/autonomous/mypy-baseline.txt`'s six `scheduler.py` lines exactly (two `Result[Any].rowcount`,
  four pre-existing `import-untyped`) — zero new.
- `npx openspec validate --changes --strict` — 2/2. Run from the repo root only after the first attempt,
  from `hub/ui`, silently reported "No items found to validate" rather than erroring — a directory trap
  worth remembering, now recorded in `next_action` for the next iteration.

No Hub restart this iteration: unlike the panel-shell sections, L6 is verified entirely through pytest
against the scheduler's own logic, with no UI or live-Hub surface to exercise — consistent with L4/L5's
own verification scope, which also skipped a restart.

Marked 6.1-6.3 done in `tasks.md` with the dated note above (fuller version there, including the D3-vs-
paraphrase and actor-choice reasoning), corrected the file's own summary line ("Sections 1-5" →
"Sections 1-6").

Committed, pushed. `current`/`next_action` now point at **L7** (loop-scoped checkpoints, `hub/hub/
checkpoints.py` — confirmed this iteration that `checkpoint_generation.py`, also named in the section
header, does not actually hold the touched functions; only `checkpoints.py` does), tasks 7.1-7.4.

## Entry 9 — iteration 9: L7, loop-scoped checkpoints + envelope (2026-08-18T23:57-2026-08-19T00:06+01:00)

Fresh process. Branch and `git log` matched STATE.json exactly on read (HEAD at the release-heartbeat
commit following entry 8). Read design D4 (`2026-08-18-a-loop-writes-its-own-queue/design.md`) before
touching code.

**Work done: L7 — tasks 7.1-7.4, `hub/hub/checkpoints.py` and `hub/hub/checkpoint_generation.py`.**

New `loop_for_conversation(db, conversation_id) -> Optional[Loop]` in `checkpoints.py`, doing task
7.1's join (`JobRun.conversation_id` → `job_id` → `Loop.job_id`) once — the same join
`_batch_loop_summaries` (`api/v1/jobs.py:98`, design D7 of `many-named-loops`) already makes. Rather
than inline this join at both `create_checkpoint` and `compute_envelope` call sites, `generate_checkpoint`
(`checkpoint_generation.py`, the only function that calls both) derives it once and passes the same
`Loop` object into each. `scalar_one_or_none()`, not `scalar_one()` — a conversation with no `JobRun`
row (most conversations) or a `JobRun` whose job carries no `Loop` both correctly resolve to `None`
without raising.

New `latest_checkpoint_for_loop(db, loop_id)` (task 7.2), copied from `latest_checkpoint`'s shape
exactly, `Checkpoint.loop_id == loop_id` in place of `conversation_id`, same
`order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())` tie-break.

`compute_envelope` (task 7.3) gained an optional `loop=` parameter. When supplied, `tasks` is built by
new `_tasks_for_loop(db, loop_id)` — `Task.loop_id == loop.id`, every status, no `_LIVE_TASK_STATUSES`
filter — instead of the agent-wide `_tasks_for`. A new `LOOP_TASK_SCOPE_NOTE` constant, not a runtime
substitution into the existing `TASK_SCOPE_NOTE` string: the two scopes are genuinely different claims
("every task assigned to this agent" vs "every task belonging to this loop"), and stating each as its
own literal text is the same "explicit scope hides nothing" reasoning `TASK_SCOPE_NOTE`'s own comment
already gives for existing at all — a templated single constant would have hidden that difference
behind a parameter instead of making it directly reviewable.

`create_checkpoint` (task 7.1) also gained an optional `loop=` parameter; when supplied,
`checkpoint.loop_id = loop.id` on the constructed row, `None` otherwise. The `Checkpoint.loop_id`
column itself was already migrated in section 1 (confirmed on the model before writing the stamp,
per `next_action`'s explicit instruction not to assume it).

**The caller side.** `generate_checkpoint` (`checkpoint_generation.py`) now calls
`loop = await loop_for_conversation(db, conversation.id)` once, right after resolving the anchor
checkpoint, and threads the same `loop` into both `compute_envelope(..., loop=loop)` and
`create_checkpoint(..., loop=loop)`. This is the only place in the codebase that calls both functions
(confirmed by grepping every call site of `compute_envelope`/`create_checkpoint` across `hub/hub` —
`checkpoint_trigger.py` and `api/v1/checkpoints.py` both only call `generate_checkpoint`, never the
two lower-level functions directly), so no other call site needed touching.

**A mypy correction made mid-iteration, not caught until the second pass.** The three new functions
were first written matching this file's existing convention of an untyped `db` parameter (every
pre-existing function in `checkpoints.py` does this). `mypy` then reported three fresh
`no-untyped-def` hits beyond the seven already in `.claude/autonomous/mypy-baseline.txt` for this
file — the existing convention is itself the pre-existing baseline debt, not a precedent to extend.
Fixed by typing all three new functions' `db` parameter as `db: AsyncSession` (imported from
`sqlalchemy.ext.asyncio`) — deliberately not touching any of the file's other seven untyped functions,
which stay exactly as they were, out of this task's scope. Re-ran mypy after: `checkpoints.py` back to
exactly 7 matching lines, `checkpoint_generation.py` unchanged at 6 — zero new errors either way. Worth
recording since "match the file's existing style" and "add zero new mypy errors" pointed in opposite
directions here, and only running mypy caught it — reading the file's own convention would have
produced a plausible-looking wrong answer.

**Tests, `hub/tests/test_checkpoint_record.py`.** New `_loop_firing(db, *, conversation_id, job_id,
loop_id)` fixture builds an `AIJob` + `Loop` + the `JobRun` that joins a given conversation to it —
the minimal shape `loop_for_conversation` reads. Seven new tests: a loop-scoped envelope's `tasks`
includes a task in `status="approved"` alongside a `pending` one (proving the scope is genuinely every
status, not `_LIVE_TASK_STATUSES` with a different filter value) and excludes another loop's task; a
plain conversation's envelope is unchanged (`scope == "agent"`, `TASK_SCOPE_NOTE`) as a regression
guard; `create_checkpoint` stamps `loop_id` when given a loop and leaves it `None` when not; two direct
`loop_for_conversation` tests (finds the loop, returns `None` for an untouched conversation); and
`test_latest_checkpoint_for_loop_crosses_conversations` — the load-bearing one task 7.4 named
explicitly — a checkpoint created against one conversation, then asked for from a *second* conversation
whose `JobRun` points at the same `job_id`, proving the query is genuinely `loop_id`-scoped rather than
degenerating to a same-conversation query that would pass either way.

**Verification, measured:**
- `py -3.11 -m pytest hub/tests/test_checkpoint_record.py -q` — **23 passed** (16 pre-existing + 7 new).
- `py -3.11 -m pytest hub/tests/test_checkpoint_generation.py hub/tests/test_checkpoint_access.py
  hub/tests/test_checkpoint_cutover.py hub/tests/test_checkpoint_notes.py -q` — **96 passed** — every
  other suite reading `compute_envelope`/`create_checkpoint`/`generate_checkpoint`, confirming nothing
  assumed `Checkpoint.loop_id` is always `None` or that `compute_envelope`'s `tasks` is always
  agent-scoped.
- `ruff check` on all three touched Python files — one import-sort fix applied by `--fix`, clean after.
- `black --fast` — reformatted `checkpoints.py` once (import-block wrap from the new `AsyncSession`
  import), clean after on all three files.
- `mypy hub/hub/checkpoints.py hub/hub/checkpoint_generation.py`, filtered to each file's own lines —
  `checkpoints.py`: 7, `checkpoint_generation.py`: 6, both matching
  `.claude/autonomous/mypy-baseline.txt` exactly — zero new (see the correction above).
- `npx openspec validate --changes --strict`, run from the repo root — 2/2.

No Hub restart this iteration: like L4-L6, this section is verified entirely through pytest against
database-layer logic, with no UI or live-Hub surface to exercise.

Marked 7.1-7.4 done in `tasks.md` with the dated note above (fuller version there), corrected the
file's own summary line ("Sections 1-6" → "Sections 1-7").

Committed, pushed. `current`/`next_action` now point at **L9** (the briefing, `hub/hub/scheduler.py`,
tasks 9.1-9.3) — the queue deliberately orders L9 before L8, since the briefing leans on
`latest_checkpoint_for_loop` this iteration just built; L8 (refusing `resume` for a loop's job) follows
after L9, not before.

## Entry 10 — iteration 10: L9, the briefing (2026-08-19T00:11-00:22+01:00)

Fresh process. Branch and `git log` matched STATE.json exactly on read (HEAD at the release-heartbeat
commit following entry 9). Read design D5 (`2026-08-18-a-loop-writes-its-own-queue/design.md`) before
touching code.

**Work done: L9 — tasks 9.1-9.3, `hub/hub/scheduler.py`.**

New `_compose_loop_briefing(session: AsyncSession, loop, claimed_task, prior_checkpoint) -> str`.
`next_action`'s named signature omitted `session`, but every other session-touching helper already in
this file leads with it (`_loop_stop_reason(session, job)`, `_claim_loop_task(session, loop)`), and the
queue's open/done summary needs a query the other three params cannot supply — adding it as the first
positional parameter matches the file's own convention rather than deviating from it.

Content order matches D5 exactly: `loop.purpose` (skipped entirely, not rendered as an empty heading,
when blank), the claimed task's title/description/acceptance criteria, `## Prior checkpoint` rendered
via `checkpoint_generation.render_checkpoint` — the same function a human reader gets, no second
serialisation — truncated from the end at a new `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000` when
`latest_checkpoint_for_loop` (L7) finds one, then `Queue: {open} open, {done} done`. The open/done
split reuses `TERMINAL_FOR_BINDING` (`("approved", "rejected")`) — the exact split `_loop_stop_reason`,
already in this file, uses to decide whether a loop's queue is drained — rather than inventing a second,
differently-drawn line for the same concept. The per-status count query is recomputed directly in
`scheduler.py`, not imported from `api/v1/jobs.py`'s `_batch_loop_summaries`: L6's own precedent (task
6.1's note) already rejected an api-layer-to-scheduler cross-import for a similarly small query, for the
same layering reason.

**The caller side (task 9.2).** `_do_fire_job`: `content = job.message` by default. When
`loop is not None` (the existing branch that already claims the queue item), fetch
`prior_checkpoint = await latest_checkpoint_for_loop(session, loop.id)` — not `loop_for_conversation`,
which resolves a loop *from* a conversation the caller does not have yet; the `loop` local is already
the right object — compose the briefing, and set `content = f"{briefing}\n{job.message}"`. `new_entry`
now receives `content=content` instead of `content=job.message` directly. A non-loop job never enters
the `if loop is not None:` branch, so `content` stays byte-identical to `job.message`.

**Tests, `hub/tests/test_scheduler.py`**, extending the same `_make_job`/`_make_loop` fixtures section
6's tests already use, plus a new `_make_checkpoint` helper that deliberately attributes the checkpoint
to a conversation OTHER than the one about to fire — mirroring L7's own
`test_latest_checkpoint_for_loop_crosses_conversations`, since a loop's next firing is by construction a
conversation that does not exist yet. Four new tests:
`test_loop_briefing_omits_prior_checkpoint_section_on_a_first_firing` (no checkpoint exists — asserts
`"## Prior checkpoint" not in entry.content`, and separately that purpose/claimed-task/queue-summary
lines are present and `entry.content` ends with `job.message`);
`test_loop_briefing_includes_a_prior_checkpoint_in_full_under_the_cap` (a short body — asserts
`render_checkpoint(checkpoint)` appears in `entry.content` byte-for-byte);
`test_loop_briefing_truncates_an_oversized_prior_checkpoint_to_exactly_the_cap` (a 10,000-character
body — asserts the extracted `## Prior checkpoint` section equals
`rendered[:_LOOP_BRIEFING_CHECKPOINT_CHARS]` exactly, `len(section) == _LOOP_BRIEFING_CHECKPOINT_CHARS`,
and the untruncated `rendered` string does NOT appear anywhere in `entry.content` — a length assertion,
not just presence, per `next_action`'s explicit instruction);
`test_non_loop_job_fired_content_is_byte_identical_to_job_message` (no `Loop` row at all — asserts
`entry.content == job.message == "hello from a scheduled job"`), the regression guard for every
non-loop job in the suite.

**Verification, measured:**
- `py -3.11 -m pytest hub/tests/test_scheduler.py -q` — **14 passed** (10 pre-existing + 4 new).
- `py -3.11 -m pytest hub/tests/test_checkpoint_record.py hub/tests/test_checkpoint_generation.py -q`
  — **42 passed** — both suites reading `render_checkpoint`/`latest_checkpoint_for_loop`, confirming
  this section's new call sites did not change either function's behaviour.
- `ruff check hub/hub/scheduler.py hub/tests/test_scheduler.py` — clean.
- `black --fast hub/hub/scheduler.py hub/tests/test_scheduler.py` — both already formatted, unchanged.
- `mypy hub/hub/scheduler.py`, filtered to lines attributed to the file — exactly the same 6 error
  lines as `.claude/autonomous/mypy-baseline.txt` (2 `Result[Any].rowcount` + 4 pre-existing
  `import-untyped`) — **zero new errors**. `_compose_loop_briefing`'s `session: AsyncSession` parameter
  is explicitly typed for the same reason L7's three new functions were.
- `npx openspec validate --changes --strict` (from the repo root) — 2/2.

No Hub restart this iteration: like L3-L7, this section is verified entirely through pytest against
scheduler logic, with no UI or live-Hub surface to exercise.

Marked 9.1-9.3 done in `tasks.md` with the dated note above (fuller version there), corrected the
file's own summary line: "Sections 1-7" (which had already gone stale the moment 9 finished ahead of 8)
→ "Sections 1-7 and 9 ... section 8 and everything from section 10 onward is still a spec only" — stating
the actual set rather than a contiguous range that would imply 8 is done, per `next_action`'s explicit
instruction not to mechanically bump it.

Committed, pushed. `current`/`next_action` now point at **L8** (refusing `resume` for a loop's job,
`hub/hub/api/v1/jobs.py`, tasks 8.1-8.2) — the queue's next item, now that L9 (which depended on L7) is
done.
