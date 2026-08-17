# Handoff: the night run landed seven items, was reviewed, and is not yet merged

**Date:** 2026-08-17T09:25+01:00 · **Branch:** `autonomous/2026-08-16-spec-corpus-and-jobs` · **HEAD:** `0f576de`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0051-2026-08-16-1825-the-run-closed-and-the-dogfooding-decision.md`
**Status:** **chunk complete.** The unattended run finished on its own; its work is reviewed. One
uncommitted file (the review). Nothing half-built.

## Goal

Two things, and the second is the reason the first mattered.

1. **Close the gap that blocks dogfooding.** `spec_lifecycle.py` had three phases and stopped at
   `approved` — no archive, no current-behaviour document. That is the stated reason `CLAUDE.md`
   keeps the specification corpus in openspec rather than AgentWeave. Until it closed, migrating was
   impossible, so it was the night's keystone.
2. **Make the overnight loop a product feature rather than a script.** Everything that makes these
   runs work lived in `.claude/autonomous/STATE.json` on disk, driven by a Windows Scheduled Task.
   The operator's framing: *"take advantage of agentweave"* and *"we can have loops for multiple
   things."*

## Current state

### The run — complete, reviewed, unmerged

Ran 21:25 → 06:41, stopping **1h19m early** on an empty queue and unregistering its own Scheduled
Task. **26 iterations, 65 commits, 145 files, +12,931/−917.** All seven queue items `done`,
including N6, which the prep estimated would almost certainly not be reached.

**Gates, re-run by me this morning and green** (these are measured, not transcribed from the run):

| Gate | Result |
|---|---|
| `pytest hub/tests/ -n 8` | 2123 passed, 11 skipped (+55 vs baseline) |
| `pytest tests/ -n 4` | 362 passed, 3 skipped |
| `npm test` | 957 passed (+36) |
| `npm run lint` | clean |
| `openspec validate --changes --strict` | 8/8 (17 → 8; nine archived) |

**What shipped as working code:**

- **N2, the keystone** — `ARCHIVED` and `CURRENT` phases; `(APPROVED, ARCHIVED)` with no transition
  out; operator-only archive guard **inside `spec_lifecycle.transition()` at line 239**, not only at
  the API edge. Migration `0074`.
- **N2b** — task board scoped by specification.
- **N3** — `Loop` = "an `AIJob` wearing a purpose and an optional stop condition". Migration `0075`.
  Composed rather than reinvented: no `status` enum (because `AIJob.enabled` already answers it), the
  loop's queue is `Task` via a new `Task.loop_id`, and the fields ride the existing jobs API — there
  is no parallel loop API.
- **Authored merge** — `SpecEditProposal` / `SpecDocumentMerge`, migration `0076`, with
  accept/reject/merge routes. Agents propose (gated by document rigor), the operator disposes.
- **N6's own fallback** — `openspec/changes/2026-08-17-authoring-rigor-and-scope`.

**Spec-only, as scoped:** N4 (Q6's three amendments resolved, zero code). **Thinking only:** N5
(architecture proposals, plus the §2 chronology correction to the market research).

### The review — `Ship with follow-ups`

Written to `.claude/handoffs/reviews/review-0003-2026-08-17-0900.md`. **Uncommitted.**

Three findings, all with reproducers or traced call paths:

- **Major — `0074`'s downgrade aborts on any database holding a capability document.** `downgrade()`
  runs `UPDATE spec_documents SET phase='approved' WHERE phase IN ('archived','current')` *before*
  dropping `ck_spec_documents_kind_phase`, which that update violates. Reproduced end to end. Fails
  safe (transaction aborts, stays at head, no corruption), so nothing is at risk today — the cost is
  that rollback is impossible precisely when the feature has been used. Only *capability* rows
  trigger it; an archived-changes-only database downgrades fine.
- **Minor — `_KINDS` restated in `0074:52` with no drift test** against `spec_payload.KINDS`, which
  is the pattern `CLAUDE.md` explicitly requires a test for. Identical today, so no live bug.
- **Minor — stale assertion messages** at `hub/tests/test_migrations.py:147` and `:515`: assert
  `"0076"`, message says `expected alembic_version=0075`.

Plus an **addendum**: the UI build stamp is stale (`5a9c7773…` recorded vs `e7562bb9…` current), so
`/health` false-positives `ui_stale`. **The bundle content is fine** — a literal unique to the new
`SpecProposalsPanel` is present in the shipped JS, verified with a control.

**Checked hardest and found clean:** the operator-only guarantee. All four routes go through
`get_project` → `_operator_from_credential` (`auth.py:88`), requiring an `aw_live_` key in
`OperatorCredential`; MCP exposes no archive/merge/accept/reject/set_phase tool; and
`spec_service.py:129` refuses capability writes from a non-operator actor at the service layer too.

### The trial Hub

Running on **:8010**, database `~/.agentweave/hub/profiles/beta/agentweave.db`, this repo registered
as `proj-5e960453`. Serving code from 21:13 last night, so it is **behind the branch** — restart it
before trusting any UI observation. It reports `ui_stale` for the stamp reason above.

## Files touched

`git status --short` shows exactly one entry:

- `.claude/handoffs/reviews/review-0003-2026-08-17-0900.md` — **new, uncommitted.** The review plus
  its addendum. Finished; only needs committing.

Everything else this session was committed and pushed before the run started. My own commits on this
branch, in order:

- `652601e` — `hub/ui/vitest.config.ts`: `testTimeout: 20000`, fixing a load-dependent flake.
- `0cc5df7` — the lint refactor (six files split so components export only components), the
  `OverviewPage` documented `eslint-disable`, `.github/workflows/ci.yml`'s new `ui-test` job, and
  the rebuilt bundle.
- `ad0ec1b` — `hub/ui/src/__tests__/markdownMessage.test.tsx`: pins the `javascript:`/`data:` link
  boundary.
- `c330431` — `src/agentweave/cli.py` (honour a pre-set `DATABASE_URL`, per-port `_hub_pid_file`),
  `tests/test_cli.py` (`TestTwoInstancesDoNotCollide`), `hub/ui/vite.config.ts` (`AW_DEV_HUB`).
- `40629e8` — Q6's three amendments in its `design.md`/`tasks.md`, plus the strict-validation fix in
  its `app-lifecycle` delta.
- `354661c` — `black` over eight drifted files.
- `b2b0cd5` — `CLAUDE.md`'s trial-Hub section, and the rebuilt bundle.

The run's own 58 commits touched 145 files; they are enumerated by item in
`.claude/autonomous/2026-08-16-spec-corpus-and-jobs-log.md`, not repeated here.

## Key decisions

**Merge into `hub-native-experience` happened before the night run**, as a clean fast-forward
(`a6164a8..ad0ec1b`). The night's branch has **not** been merged anywhere.
*Rejected: reviewing first* — the operator chose to merge on green gates and review after, and the
review then happened against the night's work rather than the merged base.

**Four spec-design rulings, taken with the operator awake**, each with its rejected alternative
recorded so it is not re-proposed:

- Archiving is an **operator act**. *Rejected: agent-archives-on-evidence* — lets an agent write the
  current-behaviour record unsupervised.
- The corpus absorbs a finished change by **explicit authored merge**. *Rejected: automatic
  requirement migration* — "the corpus becomes an accumulation rather than a document".
- Capability documents sit **outside** the phase machine. *Rejected: same phases* — every typo fix
  becomes a three-step lifecycle.
- A capability document carries a **dedicated phase value** (`current`) with no transitions.
  *Rejected: permanent `approved` with the UI hiding the bar* — the row would lie about what it is.

**`at_cap` changed to approve-and-execute.** The direct fix for Q6 ending the previous run at 0/21.
This is why N2/N2b/N3 are working code rather than artifacts.

**The trial Hub runs from the working tree, not a separate venv.** I had recommended a pinned venv
for structural isolation, then dropped it: the driver is Claude Code plus a Scheduled Task, **not**
the Hub, so editing Hub code cannot kill a run. The isolation that mattered was the database.

**Reviewed only the risky half of the diff.** 145 files is ~4× what fits in one careful pass.
*Rejected: skimming everything* — a shallow review of everything is worth less than a real review of
the risky half.

## Constraints and user directives (verbatim)

From this session:

> *"one more change after the 3 round spec cap approve and execute"*

> *"On N3, take inspiration on what we use today but take advantage of agentweave. Also remeber that
> we can have loops for mulitple things. Shorter dev loops that keeps developing and longer loops
> that will do security scans, etc."*

> *"The operator but be mindifull of the folder trees and what not. The spec should still be useful
> also we need to be ware of the task board as well with time things will pile up there. Maybe make
> a task board by spec? I don't know."*

> *"Give me the entire plan first. Let me see if I approve whtat's going to be built"*

> *"Can we have two modes? the test webapp only for local dev testing where we can use playwright and
> the installable for agentweave were I'm going to use it?"*

Carried, still binding:

> *"Be honest about it. My intention is not to drop agentweave but we can always evolve it and pivot
> it like we did from previous versions to this one."*

**No new dependencies are authorised.** The operator confirmed the 3-round cap but selected neither
"allow pywebview" nor a general toolchain rule. Read conservatively as: install nothing. This is why
Q6 remains 0/21.

Standing repo constraints unchanged: stage paths explicitly, never `git add -A`; never commit
`kimichanges.md`/`kimiwork.md`; `approve_tool_call` keeps no return annotation;
`hub/hub/mcp_server.py` imports only stdlib + fastmcp; commit `hub/ui/src` and `hub/hub/static/ui`
together via `python scripts/refresh_ui_bundle.py`.

## Dead ends

- **`agentweave` cannot be started from this repo's root.** `python -m uvicorn` puts the cwd on
  `sys.path[0]`, so the repo's own `hub/` directory shadows the installed `hub` package:
  `ImportError: cannot import name '__version__' from 'hub' (unknown location)`. The parent survives,
  so migrations run and only the spawned child dies — 60 seconds later, with stderr already at
  `DEVNULL`. Start from `hub/`. Documented in `CLAUDE.md`.
- **Starting from `hub/` registers `<repo>/hub` as a junk project.** One was created and deleted via
  `DELETE /api/v1/projects/{id}` (which live-verified that endpoint: 204, siblings intact).
- **A migrate-from-zero database is not a valid migration harness here.** My first `0074` reproducer
  built one, where `projects` never exists, so `0074`'s guard correctly skipped and two CHECKs looked
  missing. `init_db` runs `create_all` **then** `alembic upgrade head`. Use `create_all` +
  `stamp <prev>` + `upgrade head`.
- **`pytest --timeout=` fails collection with exit 4** — pytest-timeout is not installed.
- **PowerShell here-strings (`@'…'@`) in the Bash tool** are taken literally and corrupt the commit
  subject. Use a heredoc in Bash.
- **Reasoning from commit order about bundle staleness is unreliable.** I concluded from
  `git log` ordering that 244 lines of UI code were never built, and was wrong — a literal-presence
  check against the bundle (with a control) disproved it. Grep the bundle, do not infer.

## Verification

**Run and passed, this session:**

- All five gates in the table above, re-run this morning against `0f576de`.
- Migration `0074` reproducer: `create_all` → `stamp 0073` → `upgrade head` → seed a capability and
  an archived document → `downgrade 0073`. Confirmed the recreate preserves
  `uq_spec_documents_project_path` and all three CHECKs; confirmed the paired CHECK rejects
  `capability`+`approved`; confirmed the downgrade `IntegrityError`.
- Authz trace to `_operator_from_credential`, and a grep of the whole MCP tool surface.
- Bundle literal check with a control, and a direct `ui_source_fingerprint` comparison.
- `DELETE /api/v1/projects/{id}` driven live against the beta Hub.
- Three databases confirmed isolated by mtime after starting the beta Hub.

**NOT run, and not verified:**

- **The N2b task-board UI, N5's architecture documents, the N6 archive backlog, and ~87 openspec
  prose files were not reviewed.** Genuinely unreviewed, not lightly reviewed.
- No UI was driven and no screenshot taken. F1–F6 from the *previous* run also remain unverified as
  experience.
- `0075` and `0076` downgrades were not probed; only `0074`'s.
- The run's claim that N3's job-fire path was checked live (16/16) could not be confirmed — the
  script was torn down, which is what "torn down" means.
- Nothing was merged, so no post-merge state exists to verify.

## Git state

- **Branch:** `autonomous/2026-08-16-spec-corpus-and-jobs`
- **HEAD:** `0f576de` — "Final heartbeat: session stopped, not released for next firing"
- **Dirty:** one untracked file, `.claude/handoffs/reviews/review-0003-2026-08-17-0900.md`
- **Unpushed:** none — `git log origin/<branch>..HEAD` is empty
- **Parent:** `hub-native-experience` @ `b2b0cd5`. The branch is **not merged**; last time this was a
  clean fast-forward, and `hub-native-experience` has not moved since, so it still would be.
- **Scheduled Task:** unregistered — the run ended cleanly by itself.

## Next steps

1. **Commit the review.** `git add .claude/handoffs/reviews/review-0003-2026-08-17-0900.md` and
   commit; it is the only uncommitted file.
2. **Fix the Major finding.** In
   `hub/hub/migrations/versions/0074_archive_and_capability_phase.py`, move the
   `UPDATE spec_documents SET phase='approved' …` statement (currently lines 135-140) to **after**
   the `batch_alter_table` block at 141-148 that drops `ck_spec_documents_kind_phase`, or inside it.
   Then add a test in `hub/tests/test_migrations.py` that seeds a `kind='capability'`,
   `phase='current'` row and asserts `command.downgrade(cfg, "0073")` succeeds — mirroring
   `test_migration_0052_downgrade_drops_the_history` at line 1245.
3. Refresh the build stamp: `python scripts/refresh_ui_bundle.py`, commit the stamp.
4. Decide the two open questions below, then merge or don't.
5. If merging: `git checkout hub-native-experience && git merge --ff-only autonomous/2026-08-16-spec-corpus-and-jobs`.
6. **Drive the UI.** F1–F6 from the previous run, the delete confirmation, `Cmd+K`, and now the
   proposals panel and the loops UI are all unverified as *experience*. Restart the beta Hub first —
   it is running last night's code.

## Open questions for the user

- **Does the downgrade path need to work at all?** If rollback is not supported for this product,
  the Major finding is a documentation fix rather than a code fix. If it is supported, it needs the
  reorder plus a test.
- **Should "queue empty" stop a loop that was never populated?** Creating a loop with
  `stop_when_queue_empties=True` before adding tasks disables it permanently on the first fire
  (`scheduler.py:378-387`, `job.enabled = False`). It is opt-in, defaults `False` everywhere, and is
  deliberately tested — so not a defect, but it collides with the create-then-populate order that
  "shorter dev loops that keep developing" implies.
- **`pywebview`, or another approach for Q6?** It is spec-complete with amendments resolved but 0/21,
  blocked solely on that dependency decision.
- **`2026-07-30-hub-native-experience` has 48 unbuilt tasks** (sections 9-15: token budget, project
  navigation, composer, agent/runner selector, charter scope enforcement, spec-traceability on-ramps,
  approval surface). Largest remaining body of work in the repository. It wants its own planned
  session, not a fallback slot.

## Read on resume

- `.claude/handoffs/reviews/review-0003-2026-08-17-0900.md` — the three findings with their
  reproducers, what was checked and found clean, and the addendum. Read before deciding on the merge.
- `.claude/autonomous/STATE.json` — the four binding rulings in `decisions_for_user`. **Note it is
  stale**: the run never updated it, so entry 6 still reads "OPEN … N1 must answer it" although N1
  and N2b both completed.
- `hub/hub/migrations/versions/0074_archive_and_capability_phase.py` — specifically `downgrade()` at
  135-148, which is next step 2.
- `hub/hub/spec_lifecycle.py:28-51` — the phase constants and the five-entry `TRANSITIONS` set, the
  thing the whole night existed to change.
- `.claude/autonomous/2026-08-16-spec-corpus-and-jobs-log.md` — the run's narrative, oldest first;
  its final entry is a self-summary.
- `CLAUDE.md` — the trial-Hub section added yesterday, including the repo-root start trap.
