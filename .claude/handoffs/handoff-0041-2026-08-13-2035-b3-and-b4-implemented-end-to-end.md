# Handoff: B3 and B4 implemented end to end — a requirement knows its work, and a gate only evidence opens

**Date:** 2026-08-13T20:35+0100 · **Branch:** hub-native-experience · **HEAD:** `3dafcba`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0040-2026-08-13-1907-the-loop-driven-end-to-end-and-b3-b4-specced.md`
**Status:** **chunk complete.** 7 commits this session, 32 unpushed in total, working tree clean.

## Goal

The operator asked for **B3 and B4 implemented fully**, running tests as needed. Both were
specified and entirely unimplemented at the previous handoff. They are now both implemented,
tested and committed — every agent-verifiable task in both `tasks.md` files is checked, and the
human-only phases (B3 §8, B4 §5) are the operator's to run.

The *why*, for judgment calls later: the end-to-end run on 2026-08-13 found that **a building agent
could not read the specification it was implementing** (F1) and that **an approved document still
said "no implementation exists" after 99 tests passed** (F5). B3 is what makes a requirement
addressable and demonstrable; B4 is what makes ignoring it cost something.

## Current state

### Shipped and verified this session

1. **`5d1f33a` — B3 phase 1, the requirement index.** `spec_requirements` +
   `spec_requirement_revisions`, migration `0066`, rebuilt from the document inside
   `save_document`'s transaction.
2. **`cd99459` — B3's delta corrected** for what phase 1 discovered about identifiers.
3. **`76b2420` — B3 phase 2, links replace the JSON.** `task_requirement_links` +
   `task_requirement_references`, migration `0067` with a data backfill, `unserved()`, and
   `POST .../project/spec/reindex`.
4. **`5acd428` — B3 phases 3–5.** Evidence, reviews, footprints, drift, and coverage as one
   computation. Migration `0068`.
5. **`4b78c8a` — B3 task 6.3, coverage on the Spec view.** `SpecCoverageBar`.
6. **`5d83df7` — B3 phase 7**, the migration tested against the real legacy strings.
7. **`3dafcba` — B4 in full.** Rigor, `spec_rigor_events`, migration `0069`, the gate inside
   `apply_transition`, `TaskTransition.policy_digest`, and the rigor control in the phase bar.

### Live-verified against the running Hub, not only by tests

The Hub was restarted twice this session and is now **PID 24628 on `:8010`, health `ok`, running
`3dafcba`** with all four migrations applied to the real database (confirmed in
`%TEMP%\agentweave-hub.log`).

Run against **`aw-e2e` (`proj-471e281a`)**, the real project the previous session's E2E run built:

- `POST .../spec/reindex` → **12 requirements indexed** from the real agent-authored document, and
  **27 legacy free-text references converted into real links, 0 remaining.** This is the exact path
  B3 task 8.3 asks a human to check, and it worked on real data.
- `GET .../spec/coverage` → 12 requirements, **0 unserved**, **0 diagnostics**, all 12
  `in_progress`, integration `not_applicable`.

That last result is the point of the whole change: the work is done and **nothing demonstrates it**,
which is F5 stated honestly for the first time. Before B3 the document simply claimed no
implementation existed.

## Files touched

Everything is committed; `git status --short` is empty.

| path | what |
|---|---|
| `hub/hub/spec_digest.py` | **new** — the one semantic-digest definition + canonicalization version |
| `hub/hub/spec_index.py` | **new** — index build/rebuild, retirement, revisions, `resolve()` |
| `hub/hub/requirement_links.py` | **new** — strict identifier resolution, lenient free-text absorption, `unserved`, `backfill_project` |
| `hub/hub/requirement_coverage.py` | **new** — the single coverage computation and its precedence |
| `hub/hub/requirement_evidence.py` | **new** — record, decide, footprints (git + paths), drift, retention |
| `hub/hub/requirement_gate.py` | **new** — `evaluate(task)` and the typed refusal |
| `hub/hub/spec_rigor.py` | **new** — `set_rigor` (operator-only, CAS), promotion blockers, policy digest |
| `hub/hub/spec_identity.py` | `read_digests`, `carried_digests`; `identity_block` now carries digests |
| `hub/hub/spec_service.py` | computes digests once; reindexes in-transaction; passes `rigor` to the renderer |
| `hub/hub/spec_lifecycle.py` | `record_content` takes `digests`; `requirement_digests()` **deleted** |
| `hub/hub/spec_render.py` | `requirement_anchor()`, `RIGOR_META`, `rigor` parameter + meta + chip |
| `hub/hub/db/models.py` | `SpecRequirement`, `SpecRequirementRevision`, `TaskRequirementLink`, `TaskRequirementReference`, `RequirementEvidence`, `EvidenceReview`, `EvidenceFootprint`, `RequirementDrift`, `SpecRigorEvent`; `SpecDocument.rigor`, `Agent.can_accept_evidence`, `Project.evidence_retention`, `TaskTransition.policy_digest` |
| `hub/hub/task_transition_service.py` | `GateUnsatisfiedError`; the gate wired on `approved` only |
| `hub/hub/main.py` | the transition handler passes a gate refusal's structure through |
| `hub/hub/api/v1/spec.py` | coverage, requirements, evidence, reviews, drift, retention, reindex, rigor, rigor-history |
| `hub/hub/api/v1/tasks.py` | `requirement_ids` resolution, `_attach_requirements`, free-text absorption |
| `hub/hub/api/v1/agent_actions.py` | `requirement_ids` on `AgentTaskCreate`; agent evidence record + decision routes |
| `hub/hub/schemas/tasks.py` | `requirement_ids`, `spec_document`, `requirement_links`, `unresolved_requirements` |
| `hub/hub/mcp_server.py` | `create_task` gains `requirement_ids` / `spec_document` |
| `hub/hub/migrations/versions/0066…0069` | **new** — four migrations, each guarded for missing tables |
| `hub/tests/test_spec_index.py`, `test_requirement_links.py`, `test_requirement_evidence.py`, `test_requirement_coverage.py`, `test_requirement_drift.py`, `test_requirement_gate.py` | **new** — 17 + 17 + 13 + 14 + 11 + 24 = 96 tests |
| `hub/tests/test_migrations.py` | head → `0069`; `policy_digest` column; 2 new legacy-backfill tests |
| `hub/tests/test_project_persistence.py` | head → `0069` |
| `hub/ui/src/api/spec.ts` | coverage types + `useSpecCoverage`, `useSetSpecRigor`, `rigor`/`content_digest` on the record |
| `hub/ui/src/components/spec/SpecCoverageBar.tsx` | **new** |
| `hub/ui/src/components/spec/SpecDocumentPanel.tsx` | renders the coverage bar |
| `hub/ui/src/components/spec/SpecPhaseBar.tsx` | the rigor control and its refusal display |
| `hub/ui/src/__tests__/specCoverage.test.tsx`, `specRigor.test.tsx` | **new** — 9 tests |
| `hub/hub/static/ui/` | rebuilt twice, `diff -rq` clean |
| `openspec/changes/2026-08-13-a-requirement-knows-its-work/{tasks.md,specs/…}` | phases 1–7 checked; delta corrected |
| `openspec/changes/2026-08-13-a-gate-that-only-evidence-opens/tasks.md` | phases 1–4 checked |

## Key decisions

1. **Identifiers are document-scoped, not project-scoped** — the operator chose this when asked.
   B3's delta said unique on `(project_id, identifier)`, but `spec_identity` reads its high-water
   mark from *the document's own file*, so `FR-1` exists in every document and that constraint
   could never have held. The constraint is `(project_id, document_id, identifier)`; links point at
   the row's FK; resolution *by name* refuses an identifier two documents declare rather than
   choosing. Rejected: making minting project-wide (changes shipped behaviour, and a new change
   spec would start at FR-47), and an opaque qualified handle (nobody can type it).
2. **One semantic digest, in `spec_digest`.** Covers modal, statement, party and acceptance
   criteria; **excludes rationale**. Under-inclusion fails silently — a MUST→MAY change would leave
   evidence reporting a requirement verified; over-inclusion fails noisily and recoverably. Carries
   a canonicalization version. `spec_lifecycle.requirement_digests` was deleted rather than left as
   a second definition. Algorithms are named by the technical design as a fourth input but are
   **not** included: the payload has no way to say which requirement an algorithm belongs to.
3. **The identity block now carries per-identifier digests.** Without this a retired requirement is
   not rebuildable from files at all — its wording is gone from the document by definition. This is
   what makes "a discarded index rebuilds identically" true.
4. **Retirement is permanent, and `restored` is only for external edits.** `mint` gives a returning
   key a *new* identifier; that is `spec_identity`'s documented rule and the code was right where my
   first test was wrong.
5. **Two different obligations for two fields.** `requirement_ids` is checked and refuses; the
   legacy free-text `requirements` is converted where it resolves and preserved verbatim where it
   does not, and never refuses — a free-text field that starts rejecting values breaks every caller
   using it as prose.
6. **A partly-unknown identifier set links nothing.** A task silently serving two of the three
   requirements it named is a task whose author believes it serves three.
7. **The migration converts against whatever the index holds, which for an old project is nothing.**
   Rather than guess, `POST .../spec/reindex` rebuilds from files and retries the references. This
   is what converted 27 references on `aw-e2e`.
8. **`verified` means the same at every rigor** (B4 D7, carried from the spec).
9. **`gate_policy` is retired, not reconciled.** B4 task 1.2 said "decide which; do not leave two
   spellings" — it turned out never to have existed in this codebase at all.
10. **No CHECK constraint on `spec_documents.rigor`.** A table-level CHECK naming a column makes
    that column undroppable in SQLite, which would have made `0069` irreversible. The same trap is
    already documented on `TaskTransition.origin`. Found by `test_migration_0052_downgrade_drops_the_history`
    failing. Values are declared in `SPEC_RIGORS` and refused by `set_rigor`, the only writer.
11. **A project with no main branch reports integration `unknown`, not `not_integrated`.** The
    second would be an accusation about a choice.
12. **A reworded requirement is deliberately not also drift.** It is already reported as stale
    evidence; raising both asks the operator one question in two vocabularies.
13. **The gate refusal carries structure through the exception handler**, with the ordinary sentence
    kept inside it as `message` so a caller reading only that keeps working.

## Constraints and user directives (verbatim)

**From this session:**
- *"Implement b3 and b4 fully, running test when you need to."*
- On identifier scope, the operator chose **"Document-scoped + FK"**.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence (B3 Q1): *"The evidence can be anything. Test running, screen shots, paths. What ever the
  model thinks it's necessary to show that his work is good."* … *"User can even chose never and
  deal with it in their own way."*
- B3 Q4: *"only test agents can accept the evidence… If no tester agent then all defers to the
  operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented
  yet."*
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **Running `black hub/tests/ -q` without `--target-version py311`.** It reformatted four unrelated
  test files into parenthesized `with` statements, which ruff rejects against the py38 target. Had
  to `git checkout --` them. Always pass `--target-version py311` when running black here.
- **Adding a CHECK constraint on a new SQLite column.** Makes the column undroppable and the
  migration irreversible. Caught by an existing downgrade test.
- **Assuming `requirements_from_payload` would leave retirement to the absent-row loop.** Retirement
  arrives *through* the identity block, so it lands in the update branch; the absent loop never
  fired for a Hub save.
- **Asserting a returning key keeps its identifier.** It does not, by design. The code was right.
- **Assuming `ApiError` carries a parsed body.** It carries the response text verbatim; the
  structured refusal has to be `JSON.parse`d back out of `error.message`.
- **Marking B3 task 6.3 complete before building the UI.** Caught it before committing; the rule is
  in `CLAUDE.md` for a reason.

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`openspec` CLI rejects change names starting with a digit** — create and archive by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`.**
- **`git commit -m @'…'@` is PowerShell syntax and the Bash tool is Git Bash.** Use a heredoc into
  `git commit -F -`.
- **`vitest` full-suite runs flake** on `chartersUi` / `runnersUi` under load; both pass in isolation.
- **Never `git stash` during a background pytest run** — it silently invalidates the whole run.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1800 passed, 10 skipped** at `3dafcba`. (Was 1702 at the previous
  handoff; +98.)
- `pytest tests/ -q` — **360 passed, 3 skipped**.
- `ruff check hub/ src/` — **All checks passed.** `black` on every file touched.
- `npx tsc --noEmit` — clean. `npx vitest run` on the three spec test files — **14 passed**.
- `npx openspec validate --changes --strict` — **14 passed**.
- `npm run build`; `hub/hub/static/ui` replaced and `diff -rq` **identical**.
- **Live against the running Hub on the real `aw-e2e` project**: reindex produced 12 requirements
  and converted 27 legacy references with 0 remaining; coverage returned 12 `in_progress`, 0
  unserved, 0 diagnostics.
- **All four migrations applied to the real database** on Hub startup (`0065 → 0069`).

**NOT run, and it matters:**
- **B3 §8 and B4 §5 are human-only and have not been done.** Five and four checks respectively —
  most importantly B3 §8.3 (was the migration right on real data — the reindex above is evidence
  for it but not a substitute for reading the links), and B4 §5.1 (is a refusal actionable?).
- **B4 §5.3 asks whether `contract` earns its place.** It reports and blocks nothing today.
- **The gate has never fired against a real agent's task** — only in tests and never in the app.
- **F4 (nothing integrates) is still open and still unowned.** B3 now *reports* it
  (`verified, not integrated`) but nothing creates the integration step.
- **F6, F8, F9, F10 from the E2E run are untouched.**
- **The full `npx vitest run` suite was not run** — only the three spec files.

## Git state

Branch `hub-native-experience`, HEAD **`3dafcba`**, working tree **clean**, **32 unpushed commits**
(7 from this session).

**Live environment:** Hub on `:8010`, **PID 24628**, health `ok`, running `3dafcba` with migrations
through `0069` applied. Find the real PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`.

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4` (`proj-477dab47`), and
**`aw-e2e` (`proj-471e281a`, at `C:\Users\huida\Documents\aw-e2e`)** — now carrying a populated
requirement index and 27 converted task links. Keep it; it is the only worked example of the full
loop and it is now also the fixture proving the migration works on real data.

## Next steps

1. **Run B3 §8.3 on `aw-e2e`.** Open
   `openspec/changes/2026-08-13-a-requirement-knows-its-work/tasks.md` §8 and inspect the links the
   reindex produced: `GET http://127.0.0.1:8010/api/v1/projects/proj-471e281a/tasks` with the
   bearer key, and check each task's `requirement_links` and `unresolved_requirements` against what
   its `requirements` string used to say. **This is the one step where being wrong is silent.**
2. **Then B4 §5.1** — set `aw-e2e`'s document to `gate` in the Spec view's Enforcement control, take
   a task to `approved`, and judge whether the refusal tells you what to do without reading code.
3. **Decide who owns integration (F4).** It has now blocked two designs and B3 reports it on every
   coverage answer, so the gap is visible in the product for the first time. Nothing in the A–B7
   roadmap creates it.
4. **Archive B3 and B4** once the human-only phases are done — `openspec-archive-change`, by hand,
   since the CLI rejects names starting with a digit.
5. Optional: F9 (rename moves the path but not the title), and the untouched F6/F8/F10.

## Open questions for the user

1. **Does `contract` earn its place?** It reports and blocks nothing. B4 §5.3 asks this deliberately;
   two levels may be clearer than three.
2. **Who owns integration (F4)?** Blocking next step 3.
3. Carried: should `.claude/handoffs/` stay tracked (**now 127 files including `LATEST.md`**)?

## Read on resume

- `openspec/changes/2026-08-13-a-requirement-knows-its-work/tasks.md` — §8 and §9 are what remain,
  and §9 is the user test guide to follow.
- `openspec/changes/2026-08-13-a-gate-that-only-evidence-opens/tasks.md` — §5 and §6, same.
- `hub/hub/requirement_coverage.py` — the single precedence everything reads; the file to understand
  before touching any coverage surface.
- `hub/hub/requirement_gate.py` — what refuses, and the `REMEDY` wording B4 §5.1 asks a human to
  judge.
- `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md` — F1–F10; F4, F6, F8, F9
  and F10 are still open.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — where B5 and B7
  sit now that B3 and B4 are done.
