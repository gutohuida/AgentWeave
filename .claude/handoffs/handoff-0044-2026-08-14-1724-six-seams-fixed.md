# Handoff: the six defects loop 7 found, all implemented

**Date:** 2026-08-14T17:24+0100 · **Branch:** hub-native-experience · **HEAD:** `4ec3c50`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0043-2026-08-14-1326-the-loop-agents-can-drive-implemented.md`
**Status:** **chunk complete.** 10 commits this session, **0 unpushed**, working tree clean apart
from one pre-existing stray file. Phases 1–8 of one openspec change done and green; phase 9 is
human-only and is the operator's. See Verification, which distinguishes what ran from what did not.

## Goal

Two things happened, in order.

1. **Ran `/e2e-loop` phase 9.1** at the operator's instruction ("Run 9.1 from zero"), proving the
   previous session's change: an agent-driven project reached `integration: integrated` with no
   minted credential and no curl-as-agent. **It passed.** The run also found six defects.
2. **The operator said "fix all of the defects first. Enter plan mode explore the solution and then
   fix it", then "implement".** All six are implemented.

The *why*, for judgment calls later: the previous two sessions built the evidence→integration
pipeline and made it agent-drivable. Loop 7 proved that works, and proved the things *around* it do
not — six defects that live **between** features, invisible to 1949 passing tests.

## Current state

### The e2e run (project `aw-loop7`, preserved)

`proj-e6c1de74` at `C:\Users\huida\Documents\aw-loop7`. Drove from nothing: interview → 9-requirement
spec for a prorated-refund library → approval creating 2 tasks → a Claude builder → a Codex verifier
that **rejected all nine pieces of evidence** on a commit mismatch (correctly) → an unattended
peer-driven correction → merge to `master`. Coverage `verified / integrated` ×9.

Findings: `openspec/explorations/2026-08-14-loop7-evidence-drives-but-a-skipped-merge-is-terminal.md`.
**Finding 5 in that file was corrected by me during implementation** — see Key decisions 8.

### What was implemented

One openspec change, `openspec/changes/2026-08-14-the-seams-loop7-found/`. **Phases 1–7 checked;
phase 8 (agent-verifiable) and 9 (human-only) NOT checked.** 8 implementation commits:

1. **`2fbbcb7`** — the change itself: proposal, design (D1–D15), tasks, 4 spec deltas.
2. **`599a1fc`** — **the headline.** Evidence was footprinted against the *previous* commit, always.
3. **`1ec5c08`** — proves the re-stamp moves what `integration_targets` would merge.
4. **`bfe0032`** — a skipped merge can be retried; operator plane, agent plane, and on settings save.
5. **`e050368`** — proves the re-stamp and the retry compose.
6. **`51f5e50`** — a dead runtime reports exit code, in-flight method, stderr tail.
7. **`92f3dc6`** — a failed run cannot wedge its agent. **The only migration: `0072`.**
8. **`9cec364`** — `requirement_ids` is readable; the board shows checked links.
9. **`4ec3c50`** — the bundle staleness warning can be cleared.

## Files touched

Everything is committed and pushed. `git status --short` shows only `?? hub/agentweave.db` — a stray
empty SQLite file **already untracked at session start** and named in the last three handoffs. Not
the live database; that is `hub/data/agentweave.db`. Left alone deliberately.

Full diffstat: `git diff --stat 07eb4c7..HEAD` — 44 files, +4085/−219.

| path | what |
|---|---|
| `hub/hub/requirement_evidence.py` | **new** `_apply_footprint`, **new** `restamp_run_footprints`; `capture_footprint` refactored onto the shared applier |
| `hub/hub/api/v1/agent_trigger.py` | **new** `_restamp_evidence_footprints`, **new** `_report_abandoned_entries`, **new** `_transport_failure_fields`; both snapshot sites call the re-stamp; both requeue sites report abandonment; `run_failed` payload enriched; imports gained `requirement_evidence`, `Project`, `abandoned_for_run` |
| `hub/hub/task_transition_service.py` | `_integrate` → public **`integrate_task`** (now returns results); **new** `retry_integration`; **new** `IntegrationRetryRefusedError` |
| `hub/hub/task_integration.py` | **new** `tasks_skipped_for_want_of_a_main_branch`; `func` added to the sqlalchemy import |
| `hub/hub/api/v1/tasks.py` | **new** `_integration_view` (shared by read + retry), **new** `POST /{task_id}/integrations/retry`; `requirement_ids` filled in `_attach_requirements` |
| `hub/hub/api/v1/agent_actions.py` | **new** `GET /tasks/{id}/integrations` and `POST /tasks/{id}/integrations/retry` |
| `hub/hub/api/v1/projects.py` | **new** `_integrate_what_was_waiting_for_a_branch`; `main_branch_newly_named` hoisted; **new** module `logger` |
| `hub/hub/codex_appserver.py` | `AppServerError` gains `exit_code`/`method`/`stderr_tail`; **new** `_Pending`; **new** `_drain_stderr`, `stderr_tail`, `returncode`, `process_ended_error`; reader reaps before reporting; `TurnOutcome.exit_code`; **new** `STDERR_TAIL_LINES`/`STDERR_TAIL_CHARS` |
| `hub/hub/inbound_queue.py` | **new** `RESUME_RETRY_LIMIT=2`, `DELIVERY_ATTEMPT_LIMIT=3`; `return_run_entries` rewritten; **new** `abandoned_for_run`; `Conversation` imported |
| `hub/hub/api/v1/inbound_queue.py` | `delivery_attempts`/`abandoned_reason` on `QueueEntryResponse`; `delivery_attempts` on `QueueStatus`; attempts sentence appended last in `get_queue_status` |
| `hub/hub/run_reconciliation.py` | `abandoned_entry_ids` on the `run_interrupted` payload |
| `hub/hub/db/models.py` | `InboundQueueEntry.delivery_attempts`, `.abandoned_reason` |
| `hub/hub/migrations/versions/0072_add_queue_delivery_attempts.py` | **new**, guarded for a missing table |
| `hub/hub/schemas/tasks.py` | `TaskResponse.requirement_ids` |
| `hub/hub/main.py` | **new** `ui_source_fingerprint`, `read_ui_build_stamp`, `_has_uncommitted_ui_source`, `_reset_ui_staleness_cache`, `UI_BUILD_STAMP`, `UI_STALENESS_TTL_SECONDS`; `lru_cache` → TTL; imports gained `hashlib`/`json`/`time`, lost `functools` |
| `scripts/refresh_ui_bundle.py` | **new** — copies `dist`, verifies, writes the stamp; `--check` mode |
| `Makefile` | **new** `ui` and `ui-check` targets |
| `CLAUDE.md` | bundle-refresh rule rewritten to name `make ui` and the stamp |
| `hub/ui/src/api/tasks.ts` | **new** `useRetryTaskIntegration`, **new** `RequirementLink`; `Task` gains `requirement_ids`/`requirement_links`/`unresolved_requirements` |
| `hub/ui/src/components/tasks/TaskIntegrationNote.tsx` | rewritten — newest-per-target dedupe, "Try again", settings pointer for `NO_MAIN_BRANCH` |
| `hub/ui/src/components/tasks/TaskCard.tsx` | **new** "Serves" and "Unresolved" blocks; prose relabelled "Requirements (as written)" |
| `hub/ui/src/hooks/useSSE.ts` | `task_integration_retried` + `queue_entry_abandoned` allowlisted and handled |
| `hub/hub/static/ui/` | rebuilt 3×, `diff -rq` identical each time; now carries `ui-build-stamp.json` |
| **new tests** | `test_evidence_restamp.py` (14), `test_task_integration_retry.py` (9), `test_codex_appserver_process.py` (7), `test_delivery_attempts.py` (11), `test_task_requirement_ids_readable.py` (6), `test_ui_build_stamp.py` (9 + 1 gated), `taskIntegrationRetry.test.tsx` (6), `taskRequirementLinks.test.tsx` (4) |
| **edited tests** | `test_codex_appserver_run_turn.py` (fake gained `returncode`/`stderr_tail`/`process_ended_error`), `test_migrations.py` + `test_project_persistence.py` (head `0071`→`0072`) |
| `openspec/changes/2026-08-14-the-seams-loop7-found/` | **new** — proposal, design D1–D15, tasks, 4 spec deltas |
| `openspec/explorations/2026-08-14-loop7-…-terminal.md` | **new** this session, then finding 5 corrected |

## Key decisions

1. **The footprint is corrected *after* the turn, not deferred during it.** `record_evidence` cannot
   name a commit that does not exist yet, and the Hub's commit-on-delivery placement is load-bearing
   (D6 of the previous change). Joins through `RequirementEvidence.run_id` — written for every
   agent row and, until now, read by nothing.
2. **Every row of the run is re-stamped, whatever its review state.** `integration_targets` reads
   *accepted* footprints, so sparing decided rows leaves approval merging a commit that lacks the
   work — and makes correctness depend on how fast a reviewer clicked. Rejected: only `awaiting`.
3. **A `None` snapshot is not a skip** — it also means "the agent committed its own work mid-turn",
   where the footprint is still stale. Falls back to `HEAD`.
4. **The re-stamp writes a fresh `reachable_from_main`, including `False`.** Deliberately **not**
   `refresh_reachability`'s upgrade-only rule: that is right for a fixed commit, wrong here.
5. **`retry_integration` is a second entry point to `integrate_task`, not a second path through the
   transition.** The `to_status == from_status` early return stays — manufacturing an
   `approved → approved` row would make "who approved this" return the retrying run.
6. **No refusal when the work is already merged.** `integrate` self-guards on reachability, a fact,
   rather than parsing the attempt log. Rejected: refusing on a `merged` newest row.
7. **No MCP tool for retry.** Five of six skip reasons name a remediation only the operator can
   perform. **Reversal condition is recorded in D7** — if `NOTHING_TO_MERGE` clears via peer
   acceptance in live use, add it.
8. **Finding 5 was mine to correct.** I reported `requirement_ids` "reads `None` despite 18 link rows"
   — implying the API contradicted the database. It does not: the field was never on `TaskResponse`,
   and the links *are* exposed as `requirement_links`, which my harness never checked. Corrected in
   the exploration doc; severity dropped; fix kept.
9. **Abandonment reuses `withdrawn`, not a fourth state.** The value is CHECK-constrained, and
   rewriting a CHECK on SQLite means rebuilding the table whose autoincrement `sequence` orders the
   whole queue. `abandoned_reason` distinguishes it from an operator withdrawal.
10. **`conversation_id` is NOT cleared on requeue** — an entry belonging to no conversation is
    unschedulable, so it would wedge *silently and forever*, strictly worse than the bug.
    `arrived_at` is not bumped: ordering is by `sequence`, so it would only hide how long the input
    has been stuck.
11. **The staleness stamp fingerprints *content*, not a commit sha.** A sha cannot be named until
    after the source is committed (two-commit dance, unrescuable by `--amend`) and cannot see an
    uncommitted edit. **It is a promise, not a proof** — this is stated in D14 and in the commit.
12. **The strict bundle-matches-source test is gated behind `AW_CHECK_UI_BUNDLE=1`**, so it does not
    reverse CLAUDE.md's stated "`test_ui_staleness.py` does not check this repo's copy".

## Constraints and user directives (verbatim)

**From this session:**
- **"Run 9.1 from zero (Recommended)"** — chosen over a targeted check or skipping to archive.
- **"Keep the inference (Recommended)"** — `create_task`'s `spec_document_id` inference stays;
  recorded in the previous change's `design.md` D8. **This closes the open question from handoff 0043.**
- **"Keep it (Recommended)"** — `aw-loop6` stays, with its `run-ev6` credential.
- **"fix all of the defects first. Enter plan mode explore the solution and then fix it"**
- **"implement"**
- On the queue give-up rule: **"Reset thread at 2, abandon at 3 (Recommended)"**.
- On settings save: **"Yes, only for that one skip reason (Recommended)"**.
- On the staleness fix: **"Build stamp + make target (Recommended)"**.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- **G5 (the interview backstop) is a non-goal** — *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test."* **Do not re-propose it.** (Loop 7
  re-observed it — architect asked six questions as prose, no question row — and it is recorded as
  finding 7 *as an observation only*.)
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that
  his work is good."* · *"only test agents can accept the evidence… If no tester agent then all
  defers to the operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; **never mark a task complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**

- **`test_codex_appserver_run_turn.py`'s `_FakeSession` had to gain `returncode`, `stderr_tail` and
  `process_ended_error`.** I first considered a `getattr` guard in production code — wrong: the fake
  should implement the interface. `test_codex_appserver.py`'s purity assertions were **not** touched
  (`git diff` on it is empty).
- **`returncode` is racily `None` when the reader loop sees EOF.** Losing stdout means the process is
  going, but `returncode` is only populated after `wait()`. Fixed by reaping (bounded, shielded,
  suppressed) in `_read_loop`'s `finally` — without it, the exit code is absent exactly when wanted.
- **Importing a pytest fixture by name shadows a parameter of the same name** — `from
  .test_task_integration import builder` gave F811 on every helper taking `builder`. Define the
  fixture locally instead.
- **There is no `Button` component** in `hub/ui/src/components/common/` — only `Badge`,
  `EmptyState`, `ErrorBoundary`, `Icon`. I assumed one; use a plain `<button>`.
- **`_compute_ui_staleness_warning` needs both trees in ONE repo** for the fingerprint path. The
  existing tests use two separate throwaway repos, which is why they exercise only the fallback.
- **`make` is NOT on PATH in Git Bash on this machine.** `make ui` is untested here; run
  `python scripts/refresh_ui_bundle.py` directly. Recorded in CLAUDE.md.
- **My `test_the_stderr_tail_is_bounded` first sampled the child mid-stream** and asserted on line
  640 of 1000. Poll for the last line, do not assume the writer has finished.

**Tooling quirks, re-confirmed:**

- **A heredoc through the Bash tool mangles `\n` inside Python string literals.** Hit again in
  `test_evidence_restamp.py` (produced an unterminated string literal). Use the `Write` tool, or fix
  with `Edit` after.
- **A heredoc containing apostrophes broke `cat >> file <<'PYEOF'`** with "unexpected EOF". Write a
  separate file instead of appending.
- **`pytest --timeout=` is not available** (no pytest-timeout). Use `timeout 120 pytest …`.
- **Long pytest runs exceed the 600s Bash timeout** — the full hub suite takes ~8–12 min. Use
  `run_in_background: true`. Its output file stays **empty until the process exits** (pytest buffers),
  so polling it mid-run tells you nothing.

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`black` without `--target-version py311`** reformats into py38-invalid `with` statements.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`**
  (`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`).
- **The spec router is mounted at `/api/v1/projects/{id}/project/spec/...`** — note the doubled
  `project`. The agents router is `/api/v1/projects/{id}/agents/{name}`.
- **`git commit -m @'…'@` is PowerShell syntax; the Bash tool is Git Bash.** Use `git commit -F -`.
- **`npx openspec new change` rejects a name starting with a digit** — create by hand.
- **The openspec validator reads only a requirement's FIRST PHYSICAL LINE** for SHALL/MUST.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1998 passed, 11 skipped**, at HEAD (`4ec3c50`), 8m12s, exit 0.
  Confirmed twice: an earlier run of the same suite gave an identical count, so the two agree.
- `pytest tests/ -q` — **360 passed, 3 skipped**, at HEAD.
- `npx vitest run` — **864 passed, 90 files**, after phase 5.
- `npx tsc --noEmit` — clean. `ruff check hub/ src/ scripts/` — clean.
  `black --target-version py311` on every file touched.
- `npx openspec validate --changes --strict` — **18 passed, 0 failed.**
- `npm run build` + bundle refresh, `diff -rq` **identical** (3×).
- Phase 6 targeted: `test_ui_build_stamp.py` + `test_ui_staleness.py` — **14 passed, 1 skipped**; the
  gated `AW_CHECK_UI_BUNDLE=1` test passes.
- `python scripts/refresh_ui_bundle.py --check` — passes.

**Three mutation checks, because a vacuous assertion has bitten this codebase three times:**
- Neutering `restamp_run_footprints` fails **5** of `test_evidence_restamp.py`.
- Removing either snapshot call site fails `test_every_snapshot_site_restamps`.
- Removing the stderr drain fails **4** of `test_codex_appserver_process.py` — including
  `test_stderr_is_drained_so_a_chatty_child_cannot_block`, which fails on a **TimeoutError**. That is
  the pipe-blocking hang, demonstrated.
- Restoring the unconditional requeue fails **6** of `test_delivery_attempts.py`.

**NOT run, and it matters:**
- **`make ui` itself has never been executed** — `make` is not on PATH here. Only the underlying
  script has run.
- **Nothing in this change has been exercised by a real agent.** Every assertion is a test. No agent
  has hit the retry route, no queue entry has been abandoned in a live run, no Codex process has died
  and reported an exit code to a real timeline.
- **The Hub on `:8010` is running code from before all eight implementation commits** (restarted at
  13:38 for the e2e run). Restart before any live verification.
- **Phase 9 of `tasks.md` is unchecked** — it is human-only and is the operator's.

## Git state

Branch `hub-native-experience`, HEAD **`4ec3c50`**, working tree **clean** except
`?? hub/agentweave.db` (pre-existing stray, not the live DB), **0 unpushed commits** — pushed at
`07eb4c7..4ec3c50`.

**Live environment:** Hub on `:8010`, started 13:38, **pre-change code**. Find the PID with
`Get-NetTCPConnection -LocalPort 8010 -State Listen`.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`, `aw-loop5`,
`aw-loop6` (`proj-c28f08df`), and **`aw-loop7` (`proj-e6c1de74`, at `C:\Users\huida\Documents\aw-loop7`)**.

**Keep `aw-loop6` and `aw-loop7`.** Loop 6 is the operator's explicit choice this session and holds a
hand-minted credential `run-ev6` / `aw_run_loop6_evidence` — **delete that row if ever shared.**
Loop 7 is the reproduction for all six defects fixed here and **minted no credentials.** Remove
either with `python .claude/skills/e2e-loop/e2e.py clean <project-id>`.

## Next steps

1. **Restart the Hub onto the new code** before anything live, using the WMI command in Dead ends.
   The running process predates all eight commits.
2. **Phase 9.1 of the new change** —
   `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md` §9. Re-run `/e2e-loop` from zero.
   **Pass condition: a builder records evidence mid-turn and the footprint names the SNAPSHOT commit,
   with no reject/re-record cycle at all.** That round trip is what phase 1 exists to remove, and its
   absence is the proof. §10 is the step-by-step operator guide.
3. **Archive the four outstanding changes, in this order** — stated in each proposal's
   "Archive ordering": `2026-08-13-approved-means-it-is-in-the-product`, then
   `2026-08-14-what-the-product-actually-built`, then `2026-08-14-the-loop-agents-can-drive`, then
   `2026-08-14-the-seams-loop7-found`. The last **MODIFIES** a `spec-document-authority` requirement
   the second **ADDS**; applied out of order the modification has nothing to modify. By hand — the
   openspec CLI rejects names starting with a digit.

## Open questions for the user

1. **Phase 9.2–9.6 are judgement calls only the operator can make** and are unanswered: does an
   abandoned queue entry read as "the Hub gave up" clearly enough to act on; does "Try again" read as
   safe given it merges into the main branch; is `make ui` a workflow they would actually run, or
   will the stamp rot.
2. Carried, still unanswered: should `.claude/handoffs/` stay tracked (**now 130 files**)?

## Read on resume

- `openspec/changes/2026-08-14-the-seams-loop7-found/tasks.md` — §8 and §9 are what remain; §10 is
  the operator test guide.
- `openspec/changes/2026-08-14-the-seams-loop7-found/design.md` — D1–D15. **Read D2, D4 and D12
  before touching the re-stamp or the queue**; they encode the three traps that would otherwise be
  rediscovered.
- `openspec/explorations/2026-08-14-loop7-evidence-drives-but-a-skipped-merge-is-terminal.md` — the
  run's findings, ranked by cost, with the correction to finding 5 and a "what held" section.
- `hub/hub/requirement_evidence.py` — `restamp_run_footprints`, the newest and most consequential
  seam: it decides what commit gets merged into a real repository.
- `hub/hub/inbound_queue.py` — `return_run_entries` and the two limits. The widest blast radius in
  this change, and the only migration.
- `hub/hub/main.py` — the staleness check and the stamp. The one fix that is a promise rather than a
  proof, and the one most likely to rot.
