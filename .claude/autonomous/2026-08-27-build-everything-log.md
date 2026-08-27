# Autonomous run, 2026-08-27 — build everything decided

**Branch:** `autonomous/2026-08-27-build-everything-decided`
**Parent:** `master` @ `a2f61c3` — cut 2026-08-27 ~00:30 local
**Runner:** `claude` / `claude-sonnet-5` / `unattended-full-access`
**Stop at:** 2026-08-27T08:00:00+01:00
**Driver:** Windows Scheduled Task (`AgentWeaveAutonomousSession`) — survives the interactive
session ending, which `ScheduleWakeup` and `CronCreate` do not.
**State:** `.claude/autonomous/STATE.json` — 23 queue items, `current: Q1-R1`.

Newest entry at the **bottom**.

---

## Limits, stated before any work so a later process inherits them

1. **Stay on this branch.** No commits, merges or rebases onto `master`. Master was merged and
   CI-verified by the operator immediately before this run was armed; it is not this run's to move.
   No PRs — the standing directive is **push, no PRs**.
2. **Nothing outward-facing.** No publish, no release, no force-push, no history rewriting. Pushing
   *this* branch every iteration is required, not optional: it is what makes the work durable.
3. **Nothing destructive.** No deleting projects, databases, or kept reproductions.
4. **Never mark work complete on the strength of a plan existing.** This matters more when nobody is
   checking, not less.
5. **Every claim is measured or labelled unverified.**
6. **Decisions that are genuinely the operator's get written down, not guessed** — they collect in
   `STATE.json`'s `decisions_for_user`, which is what the operator reads first.

The full 14 limits and 39 dead ends live in `STATE.json`. Read them before the first unit of work;
seven of the dead ends were added the night this run was armed and have already cost time once.

---

## Iteration 0 — arming (interactive, operator awake)

Not a work iteration. Recorded so the morning knows what state the run started from.

**What the operator decided, in one place.** All eight open findings were answered on 2026-08-26 and
the decisions are recorded with their rejected alternatives in
`openspec/explorations/2026-08-26-what-is-still-unanswered.md`. Every queue item below cites that
file rather than restating it. Two of the eight answers changed the shape of the item they answered:
F58 became per-task worktrees (and is **out of scope tonight** — it needs its own exploration), and
F61's chosen fix was **withdrawn** because it rested on "role", a concept the product does not own
and that CLAUDE.md forbids recreating.

**The round discipline, decided 2026-08-27 and binding on this run.** A change with no artifacts yet
gets three separate rounds before any implementation — explore-then-propose, compare-to-code-and-fix,
compare-and-fix-again — each its own queue item and its own commit. A change that already has
artifacts gets one round: compare it to the codebase and confirm the spec is good. Rounds must not be
collapsed; the point is that the second and third readings happen with the first already written
down. **A round that finds nothing must enumerate what it checked** — "looks fine" means the round
did not happen.

**Green at arming, and unusually well established.** CI run `33022066377` passed all eight matrix
cells on `master`: `ui-test`, `hub-test`, and `test` across {ubuntu, windows, macos} × {3.11, 3.12}.
That is the first time this code has ever run on Linux, macOS or Python 3.12 — before tonight it had
only ever been green on Windows/3.11 locally, because CI triggers only on `master` pushes and PRs,
and 80 commits had accumulated on a feature branch. **Any red from here is this run's own.**

**One inherited defect cleared before arming.** `/health` reported `ui_stale` and
`AW_CHECK_UI_BUNDLE=1 test_ui_build_stamp.py` genuinely failed: the stamp recorded
`src_commit: 3ec36e5`, but `38a2394` changed four files under `hub/ui/src` afterwards while
recording the pre-change commit. Rebuilt and re-recorded (`bf04ad8`) — bundle bytes unchanged, only
the stamp moved. A loop that starts on inherited red cannot tell its own breakage from what it was
handed.

**What a reviewer should distrust about this entry:** nothing was built in it. It records
preparation only.

---

## Iteration 1 onwards

*(appended by the driver, one entry per iteration)*

---

## Iteration 1 — Q1-R1: reachable-by-a-human, explore then propose (2026-08-27T01:01:11+01:00)

Confirmed branch and `git log` matched `STATE.json` before starting: current branch is
`autonomous/2026-08-27-build-everything-decided`, cut from `master@a2f61c3` with one prep commit
(`174abb8`) on top. No reconciliation needed.

**Explored every path Q1-R1 named, before writing anything**, and one it didn't:

- `hub/hub/utils.py:25` `persist_event` — confirmed it writes `severity` verbatim
  (`entry = EventLog(..., severity=severity)`, `:49`), no normalisation.
- All 21 `persist_event` call sites: 20 use `"info"`/`"warn"`/`"error"`; exactly one
  (`run_divergence.py:613`) uses `"warning"`.
- `EventRow.tsx` `SEVERITY_CHIP` (:37-42) and `SEVERITY_BORDER` (:44-47) — key on `error`/`warn`/
  `info`/`debug` (chip) and `error`/`warn` (border) only. `"warning"` matches neither map.
- `ActivityLog.tsx` `SEVERITY_FILTERS` (:31) and its strict-equality filter (:165) — same hole.
- `events.py:42-43` (`GET /events/history`) and `logs.py:58-59` (`GET /logs`) — both filter
  `EventLog.severity ==` exactly.
- **Not named in the queue item, found by reading `persist_event`'s callers exhaustively**:
  `hub/hub/api/v1/logs.py:85` (`POST /logs`) passes `severity=body.severity` straight from an
  external request body; `schemas/logs.py:15,25` bounds it only to 64 characters, no enum. This is
  why the exploration's "normalise in `persist_event`, not just the one call site" recommendation is
  the only fix that actually closes the input surface — an API boundary fix alone would still leave
  every internal call site free to drift.
- `conversation_titles.py:168-224` `generate_conversation_title` — confirmed fully wired: gated on
  `project.conversation_title_mode == "generate"` (:185), called from `agent_trigger.py` at run
  completion, declines correctly on an operator-set title (:181, :213) and an unsupported runner CLI
  (:189-190).
- `db/models.py:96,103`, `api/v1/projects.py:87-89`, `ui/src/api/projects.ts:88-89` — field exists
  end to end. `PUT /projects/{id}/settings` (`projects.py:446-496`) already validates and persists
  both `conversation_title_mode` and `conversation_title_runner_id`, including the cross-project
  runner check at :485-496 — confirmed no backend work is needed for this half.
- `ProjectSettingsPanel.tsx` — zero references to either field, confirmed by grep.
  `projectSettingsPanel.test.tsx:23-24,146-147` fixtures `conversation_title_mode: 'generate'` with
  no control in the panel that could produce that value.

**Design choice made while proposing, not left to the exploration's account**: rather than
inventing a new capability, searched `openspec/specs/*/spec.md` for existing requirements this
change makes newly true. Found `agent-capability-plane`'s "Operator-facing severity values are the
ones the operator's view understands" (already states the general rule, pinned by only one
scenario — a refused action) and `conversation-lifecycle`'s "Title generation is a project setting,
off by default" (documents the setting, never requires it be operator-reachable). Both are modified
in place rather than duplicated as new requirements.

**Ran `openspec new change reachable-by-a-human`**, then wrote `proposal.md`, `design.md`, two
spec deltas (`agent-capability-plane`, `conversation-lifecycle`), and `tasks.md` (3 groups, tests
opening each phase per the method reminder, mutation checks 1.7 and 2.5 named explicitly).
`npx openspec validate reachable-by-a-human --strict` passes.

**What this round did NOT do**: no code was touched. Per the round discipline, R1 is explore-then-
propose only; R2 and R3 are separate queue items and separate commits.

Committed `3b80f99`. Next: Q1-R2 — compare the proposal to the code claim-by-claim and fix drift.

*What a reviewer should distrust about this entry*: the exploration and the proposal were written
by the same pass with no independent check yet — that is exactly what R2 exists to catch.

---

## Iteration 2 — Q1-R2: reachable-by-a-human, compare to the code, fix the change (2026-08-27T01:12:00+01:00)

Confirmed branch and `git log` matched `STATE.json` before starting: `autonomous/2026-08-27-build-
everything-decided` at `288e00e`, five commits ahead of `master@a2f61c3` (arming + iteration 1 +
heartbeat release). Clean tree. No reconciliation needed.

**Went claim by claim, not file by file**, through `proposal.md`, `design.md`, `tasks.md`, and both
spec deltas. Every `file:line` citation was opened and read against the current code, not against
iteration 1's own account of it:

- `hub/hub/utils.py:25` `persist_event` signature, `:49` `severity=severity` — exact match.
- `run_divergence.py:613` `severity="warning"` — exact match, still the only one.
- All `severity=` call sites re-grepped directly (not re-read from the log): confirmed 20 literal
  `info`/`warn`/`error` sites plus `logs.py:85` `severity=body.severity` (external, unbounded) —
  matches the "20 use info/warn/error, one uses warning" claim exactly.
- `EventRow.tsx:37-47` `SEVERITY_CHIP`/`SEVERITY_BORDER`, `ActivityLog.tsx:31` `SEVERITY_FILTERS`
  and its filter — re-read at their cited lines; `ActivityLog.tsx`'s filter is genuinely at `:165`
  (design.md already had this right; only the original queue item's own text, `~163`, was
  approximate — not a defect in the artifacts, so left alone).
- `events.py:42-43`, `logs.py:58-59`, `schemas/logs.py:15,25` — exact match, including the
  `Field(default="info", max_length=64)` text on both `EventLogResponse` and `LogEventCreate`.
- `conversation_titles.py:168-224`, `db/models.py:96,103`, `projects.py:87-89,446-496,485-496`,
  `projects.ts:88-89`, `ProjectSettingsPanel.tsx:243-272` (checkpoint runner/model row structure,
  including the `set(...)` helper at `:86` that task 2.2 depends on), and
  `projectSettingsPanel.test.tsx:23-24,146-147` — every citation confirmed exact. Also confirmed
  `useRunners` is already imported and bound to a local `runners` array in the panel (`:12,55`), so
  task 2.3 is executable as written without a new import.
- Every task in `tasks.md` names a function/file/line that exists and is reachable by a stranger
  following it — no task named something absent.
- Every scenario in both spec deltas is falsifiable: each names a WHEN a real caller can trigger and
  a THEN that a real assertion can check against a real column or a real rendered element.

**One real drift found, not a citation error but a gap in what the design claims to close.**
`push_log` (`hub/hub/api/v1/logs.py:71-97`) calls `persist_event` (`:79-86`) and then builds an SSE
broadcast dict **independently**, at `:87-96`, reading `body.severity` a second time rather than
reusing what was just normalised and written. `ActivityLog`'s live view (`useSSE.ts`'s
`dispatchEvent`, fed by the `log_event` SSE frame) reads severity from that broadcast payload, not
from a history fetch. So the proposal's central claim — "a call site (or an external `POST /logs`
caller) cannot introduce a spelling the operator's views do not recognise" — would have been true
for the persisted row and **false for the live one**: an out-of-vocabulary `POST /logs` severity
would still have reached a connected operator's screen unnormalised immediately, only self-correcting
the next time something refetched history. This is exactly the class of bug the change exists to
close, just relocated from the write path to the broadcast path. Confirmed by reading `useSSE.ts`'s
`dispatchEvent` (`:179-190`, extracts `obj?.severity` from the event's own `data`) end to end from
the SSE frame back to `push_log`'s broadcast dict — not assumed from the exploration's account.

**Fixed in the artifacts, not just noted**: `persist_event` now returns the normalised value
(`proposal.md`, `design.md` new Decision, `tasks.md` 1.7); `push_log` broadcasts that return value
instead of `body.severity` (`proposal.md` Impact, `tasks.md` 1.6 test + 1.10 mutation check); the
`agent-capability-plane` spec delta gained a requirement sentence and a fifth scenario ("A live
broadcast matches the persisted value") so the spec, design and tasks all describe the same fixed
behaviour rather than the design alone knowing about it. Re-ran `npx openspec validate
reachable-by-a-human --strict` after every edit — passes.

**What this round checked and found nothing wrong with**: every citation in `design.md`'s Context
and Decisions sections; the two Non-Goals (`EventLog.severity` CHECK constraint, backfill of
existing `"warning"` rows) — both still correctly out of scope, no code changed under them; the
Migration Plan's "no migration needed" claim — confirmed both fields already exist as columns with
no pending Alembic revision under `hub/hub/migrations/versions/` naming them.

Committed `2fecfe5`. Next: Q1-R3 — a second independent pass for what this round did not catch
(claims that are true but incomplete, tasks that cannot execute in the stated order, scenarios that
would pass regardless of the code).

*What a reviewer should distrust about this entry*: the SSE-broadcast fix was designed and written
into the artifacts by the same round that found it, with no independent second check yet — exactly
what R3 exists to catch, same as iteration 1's own caveat about itself.

---

## Iteration 3 — Q1-R3: second independent pass over `reachable-by-a-human` (found nothing to fix)

Four specific checks, as `next_action` set them, plus the standing citation/order/falsifiability
sweep. All were run against the live code and a live query, not against R1/R2's own account of
either.

1. **Does `{info, warn, error, debug}` cover every value actually in the database?** Queried the
   trial Hub's live `event_logs` table directly (`beta` profile, read-only connection, not the
   design's claim): `info` (2996 rows), `warn` (108), `warning` (3). No `error` or `debug` rows exist
   yet, and no fifth spelling does either. `warning` is exactly the one value the fallback exists to
   catch — confirms the enumerated set, doesn't just fail to contradict it.

2. **Does anything besides `run_divergence.py:613` and `push_log`'s broadcast read or re-emit a
   severity string outside `persist_event`'s own write?** Grepped every `severity=` call site (21
   internal callers, all pass literal `"info"`/`"warn"`/`"error"` except the one bad spelling) and
   every place a response or broadcast payload sets a `"severity"` key. Found exactly two:
   `logs.py:94` (`push_log`'s broadcast, already the subject of task 1.7) and `events.py:53`
   (`GET /events/history`, reading `r.severity` off an already-persisted, already-normalised row —
   not an independent write path, nothing to fix). No third site exists.

3. **Are tasks 1.1–1.10 executable in the stated order?** Yes: 1.1/1.2 are tests against
   not-yet-written normalisation (red until 1.3), 1.5 exercises 1.3 through `POST /logs`, 1.6 is a
   test against the not-yet-written broadcast fix (red until 1.7), 1.8 is the first point every
   preceding test can be green together, 1.9/1.10 revert-and-confirm each implementation task in
   turn. A stranger following the list in order hits no forward reference to code that doesn't exist
   yet at that step.

4. **Does the runner `Select` need a guard forcing a runner when `generate` is selected, or does the
   backend already refuse `generate` + no runner?** Read `update_project_settings`
   (`projects.py:485-496`): the cross-project check only runs `if runner_id` truthy — a null
   `conversation_title_runner_id` is accepted unconditionally, in any mode. Then read
   `_resolve_runner` (`conversation_titles.py:148-165`): when the project's
   `conversation_title_runner_id` is unset, titling falls back to the triggering conversation's own
   agent's bound runner. So `generate` + no project-level runner isn't a validation gap the design
   missed — it's a working, meaningful configuration (per-agent runner) that task 2.3's "None" option
   already accounts for correctly. Worth recording because it's a stronger claim than the design
   currently makes (design only says the backend "already validates" the pair; it doesn't say `None`
   is itself a real fallback, not just a tolerated absence) — but not a defect, so the artifacts were
   left as they are rather than padding them with a claim the tasks don't depend on.

**Also re-swept, unchanged from R2 and still correct**: every file:line citation in `proposal.md`,
`design.md`, `tasks.md` against the current code (`utils.py:25,31,49`; `ProjectSettingsPanel.tsx`'s
existing Checkpoint runner/model rows at `:243-272`, confirmed byte-identical to R2's citation); both
spec deltas' scenarios are falsifiable (each names a real WHEN a real caller triggers and a real THEN
against a real column, broadcast payload, or rendered control); `debug`'s "reserved but unwritten"
claim confirmed directly in `EventRow.tsx:41` and `ActivityLog.tsx:31,41`.

**Verdict: nothing to fix.** No artifact edit this round. `npx openspec validate reachable-by-a-human
--strict` re-run anyway (not skipped just because nothing changed) — passes. Next: Q1-IMPL, working
the tasks.md the three rounds produced.

*What a reviewer should distrust about this entry*: a round that finds nothing carries weaker
evidence than one that catches something, precisely because a clean pass and a lazy pass look
identical from outside. The four numbered checks above are the falsifiable record of what was
actually queried and read this round, not a claim to take on faith.

---

## Iteration 4 — Q1-IMPL: implement `reachable-by-a-human` (2026-08-27T02:02:07+01:00)

**Reconciliation, before any new work.** This process started fresh with a working tree that was
already dirty — a prior iteration had begun Q1-IMPL (backend severity normalisation, the UI panel
control, a UI rebuild) but had died before committing, logging, or advancing `STATE.json`
(`iteration` still read 4, `current` still read `Q1-IMPL`, and `last_heartbeat` predated the last
real commit). Per the "verify it" step, the inherited diff was not trusted on sight: every file was
read claim-by-claim against `tasks.md` rather than assumed correct because it looked plausible.

One cosmetic side-quest, resolved and not worth more time: `hub/hub/api/v1/logs.py` in `HEAD`
already had a **pre-existing mix** of CRLF (68 lines) and bare LF (29 lines) line endings — confirmed
with a binary-safe `git cat-file -p` read via `subprocess`, not through Git Bash pipes (which
themselves add or strip `\r` in text mode and gave contradictory readings first). The inherited edit
had normalised the whole file to CRLF, which is why its diff looked like ~60 lines changed for a
~4-line edit. Normalising the other direction (all-LF) made the diff *worse*, not better, because
`HEAD` itself isn't internally consistent. Left as the inherited full-CRLF version — CRLF vs LF has
no behavioural effect in Python, and untangling a pre-existing per-line inconsistency in `HEAD` is
out of scope for this task. Not introduced by this run; recording it so a future session doesn't
re-diagnose it as new damage.

**What the inherited diff actually contained, verified against `tasks.md` section by section:**

- Section 1 (severity normalisation): `hub/hub/utils.py`'s `persist_event` gained
  `_KNOWN_SEVERITIES = frozenset({"info", "warn", "error", "debug"})`, normalises any other value to
  `"warn"`, and now returns the normalised value instead of `None`. `run_divergence.py:613` changed
  `"warning"` → `"warn"`. `logs.py`'s `push_log` captures `persist_event`'s return and broadcasts
  that instead of `body.severity`. `hub/tests/test_event_severity.py` (new, 116 lines) covers tasks
  1.1, 1.2, 1.5, 1.6 exactly as specified.
- Section 2 (conversation-title control): `ProjectSettingsPanel.tsx` gained two rows — a mode
  `Select` (`truncate`/`generate`) and a runner `Select` with a `None` option falling back to the
  triggering conversation's own agent's bound runner (confirmed by Q1-R3's check 4, not re-derived
  here) — modelled directly on the existing Checkpoint runner row. `projectSettingsPanel.test.tsx`
  restructured its `settings` fixture into a `makeSettings()` factory (needed because the new "changes
  the mode" test mutates the fixture before render) and added the two tests tasks 2.1 specifies.
  All citations in the diff matched the code they touched; nothing was invented.

**Ran what the inherited work had not**, in task order:

- 1.8: `hub/tests/test_event_severity.py` — 4/4 passed in isolation.
- **1.9 mutation check**: reverted `persist_event`'s mapping to `normalised_severity = severity`
  (no-op). `test_persist_event_normalises_unknown_severity` failed exactly as predicted (extra
  `'warn'` in the expected set never appeared; raw `'warning'`/`'critical'` were written through).
  Restored; re-ran green.
- **1.10 mutation check**: reverted `push_log`'s broadcast to read `body.severity` again.
  `test_push_log_broadcast_carries_normalised_severity` failed exactly as predicted
  (`'critical' == 'warn'` assertion error). Restored; re-ran green.
- 2.4: `npx vitest run src/__tests__/projectSettingsPanel.test.tsx` — 13/13 passed. `npm run lint` —
  clean.
- **2.5 mutation check**: replaced the mode `Select`'s `onChange` with a no-op. `changes the
  conversation title mode and saves it` failed exactly as predicted (`update` was called with
  `conversation_title_mode: 'truncate'`, the untouched initial value, instead of `'generate'`).
  Restored; re-ran 13/13 green.
- 3.1: `cd hub/ui && npm run build` — same asset hash (`index-awJ7Bmpi.js`) as the inherited build,
  confirming the source content matched what iteration 4 had already built, not a fluke of a stale
  bundle. `py -3.11 scripts/refresh_ui_bundle.py` re-recorded the stamp.
  `git status` after showed exactly a rename (`index-CsVsE-C3.js` → `index-awJ7Bmpi.js`) plus
  `index.html`/`ui-build-stamp.json` — the expected shape of a real rebuild, not a no-op.
- 3.3: **Full `pytest hub/tests/ -v` (actually `-q`, 3282 collected)** — `3198 passed, 84 skipped,
  1 xpassed in 1189.63s (0:19:49)`. No failures, no new skips beyond the suite's existing baseline.
  The one `xpassed` is not new to this change (nothing touched here carries an `xfail` marker) and
  was not chased further under this iteration's scope.
- 3.4: `ruff check src/ hub/ tests/` — all checks passed. `black --check --target-version py311
  src/ hub/hub/ hub/tests/ tests/` — 491 files unchanged. `mypy src/` — no issues, 22 files.
- 3.5: `cd hub/ui && npm run lint` — clean (0 warnings, `--max-warnings 0`).
- 3.6: `npx openspec validate reachable-by-a-human --strict` — valid.

All of `tasks.md`'s 21 checkboxes are now checked, each with the measured result recorded inline in
the task list itself, not just here.

**Q1 is closed.** Staged explicit paths (never `-A`): `hub/hub/api/v1/logs.py`,
`hub/hub/run_divergence.py`, `hub/hub/utils.py`, `hub/hub/static/ui/` (rename + `index.html` +
stamp), `hub/tests/test_event_severity.py`, `hub/ui/src/__tests__/projectSettingsPanel.test.tsx`,
`hub/ui/src/components/environment/ProjectSettingsPanel.tsx`, and the updated `tasks.md`.

**Next: Q2-R1** — every-run-knows-its-task's single verification round. Its own queue text already
flags the one thing to check first: whether Q1 moved `run_divergence.py`'s severity emission in a
way that invalidates design D6. It did not — `run_divergence.py:613` still reads `severity="warn"`,
the exact literal D6 was written against (R1/R2/R3 all decided the fix stays *inside*
`persist_event`, not by changing what call sites pass) — but Q2-R1 should confirm this against D6's
actual text rather than trust this paragraph's account of it.

*What a reviewer should distrust about this entry*: the implementation itself was inherited, not
newly authored by this process — this iteration's contribution is the verification (reading every
line against `tasks.md`, running every test and both mutation checks, running the full sweep), not
the code. If the inherited code had been subtly wrong in a way none of the specified checks would
catch, this entry would not have found it either.
