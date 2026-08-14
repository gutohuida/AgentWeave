# Handoff: an end-to-end run found integration reporting success while integrating nothing — and the fix for it

**Date:** 2026-08-14T10:46+0100 · **Branch:** hub-native-experience · **HEAD:** `d10ef7e`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0041-2026-08-13-2035-b3-and-b4-implemented-end-to-end.md`
**Status:** **chunk complete.** 11 commits this session, 46 unpushed in total, working tree clean
apart from one untracked stray file.

## Goal

Two things happened this session, in order.

1. **`/e2e-loop` was run from zero** at the operator's request — *"I want to test what was developed
   now. So I project from 0 with the agents… At least one feature nothing very complicated. We
   should check every friction point."* It found four structural gaps, the worst of them in code
   committed the day before.
2. **The operator approved a plan and said "implement everything."** All of it is implemented.

The *why*, for judgment calls later: B3 built `verified, not integrated` specifically so `verified`
could never describe code that never ships. The run found that guarantee **inverted into the exact
false positive it existed to prevent** — approval merged `master` into `master`, recorded
`outcome: merged`, and coverage said `verified / integrated` while every line of the product sat on
`agentweave/builder`.

## Current state

### The E2E run (project `aw-loop5`, preserved)

Drove a project from nothing: interview → 19-requirement specification → tasks → a Claude builder
that wrote a habit tracker with 38 tests → a Codex architect that reviewed and sent all three tasks
back to `revision_needed` unprompted. Findings are in
`openspec/explorations/2026-08-13-loop5-integration-reports-success-while-integrating-nothing.md`,
including a `## Resolution` section added at the end of this session.

### What was implemented

One openspec change, `openspec/changes/2026-08-14-what-the-product-actually-built/`, phases 1–9
checked; phase 10 is human-only and is the operator's.

1. **`5e9736a` — the guard.** `git merge <ancestor>` prints "Already up to date", exits 0 and
   creates nothing, so `integrate()` recorded a no-op as `merged`. Now `skipped`, checked *before*
   the working-tree preconditions.
2. **`8223877` — the footprint names the work.** `footprint_root()` +
   `worktrees.existing_worktree()`. Ships with `refresh_reachability()` and the drift fix, which
   **cannot be separated** (see Key decisions 2 and 3).
3. **`8b5461d` — statements on task payloads.** New `hub/hub/spec_reading.py`.
4. **`ab8ef00` — `read_spec_document`.** New agent-actions GET route + MCP tool + both registrations.
5. **`36bc012` — approval creates the tasks the document declares.** Migration `0071`.
6. **`4d224c4` — housekeeping.** `.gitignore` seeding, rename carries the title, prose stops being
   an "unresolved requirement", evidence reports its footprint.
7. **`1234abb` — three defects only the live run could show** (see Dead ends).
8. **`0086a2f`** — the exploration's resolution section.
9. **`d10ef7e` — a rigor guard that checks the rule, not the word.** Found by the full suite after this handoff was first written; see Verification.

### Verified live against the real reproduction

`aw-loop5` began this session with `master` at `init` holding only `README.md`. After the fix, with
the Hub restarted onto the new code:

```
ev-0adc23cd  operator  branch=master              reachable=True    ← the lie
ev-6590836c  agent     branch=agentweave/builder  reachable=False   ← the truth
approval      merged 63ec206278bb → master
master now    .gitignore, README.md, habits.py, test_habits.py + "Integrate approved work 63ec206278bb"
coverage      FR-17  verified / integrated
drift         raised nothing
2nd approval  skipped: "63ec206278bb is already in master; there was nothing to merge"
```

## Files touched

Everything is committed. `git status --short` shows only `?? hub/agentweave.db` — a stray empty
SQLite file that was **already untracked at session start** (it appears in the session's opening git
status). It is not the live database; that is `hub/data/agentweave.db`. Left alone deliberately.

| path | what |
|---|---|
| `hub/hub/requirement_evidence.py` | `is_reachable_from()`, `footprint_root()`, `tree_entries()`, `refresh_reachability()`; `capture_footprint` derives its root from the evidence row; drift compares per-ref; dead `locator` param removed |
| `hub/hub/worktrees.py` | **new** `existing_worktree()`; **new** `COMMIT_IDENTITY` constant, now used by `snapshot_worktree` |
| `hub/hub/task_integration.py` | `ALREADY_INTEGRATED` + the ancestor guard; the merge supplies `COMMIT_IDENTITY` |
| `hub/hub/task_transition_service.py` | calls `refresh_reachability` after a `MERGED` result |
| `hub/hub/spec_reading.py` | **new** — `payloads_for_documents`, `statements_by_key`, `criteria_by_requirement_key`, `requirement_view` |
| `hub/hub/spec_tasks.py` | **new** — `materialise` / `materialise_quietly` for document-declared tasks |
| `hub/hub/api/v1/tasks.py` | `_attach_requirements(…, *, project_id)` adds `key`/`statement`/`modal`; **new** `GET /tasks/{id}/integrations` was from the prior session |
| `hub/hub/api/v1/agent_actions.py` | **new** `GET /spec/documents?path=&include=` |
| `hub/hub/api/v1/spec.py` | drift route refreshes reachability; phase route materialises tasks and returns `tasks_created`; `_evidence_view` gains `footprint`; **new** `_footprints_for` |
| `hub/hub/api/v1/agents.py` | `read_spec_document` in `_tool_surface_lines` **and** in the open-document turn-context block |
| `hub/hub/api/v1/projects.py` | (prior session) `main_branch` setting + suggestion route |
| `hub/hub/mcp_server.py` | **new** `read_spec_document` tool, above the `__main__` guard |
| `hub/hub/project_lifecycle.py` | **new** `_seed_gitignore` + `GITIGNORE_BEGIN/END/PATTERNS`; called on **every** open path (3 sites) |
| `hub/hub/spec_service.py` | `rename_document` promotes `subject` to `document.title` |
| `hub/hub/requirement_links.py` | **new** `NOT_A_REFERENCE` reason + `LinkOutcome.notes`; `for_task` docstring corrected |
| `hub/hub/schemas/tasks.py` | `requirement_links` comment corrected to name the real fields |
| `hub/hub/main.py` | `_git_last_commit_iso(…, exclude=…)`; staleness check excludes `__tests__` |
| `hub/hub/db/models.py` | `Task.spec_document_id` (**no ForeignKey** — see Dead ends) + `Task.spec_task_key` + `uq_tasks_spec_declaration` |
| `hub/hub/migrations/versions/0071_add_spec_declared_tasks.py` | **new** |
| `hub/tests/test_evidence_footprint_root.py` | **new** — 19 tests, the arrangement the product actually creates |
| `hub/tests/test_spec_reading.py` | **new** — 8 tests |
| `hub/tests/test_read_spec_document.py` | **new** — 10 tests |
| `hub/tests/test_spec_declared_tasks.py` | **new** — 6 tests |
| `hub/tests/test_task_integration.py` | +2 tests for the ancestor guard |
| `hub/tests/test_requirement_links.py` | `unparsed` → `not_a_reference` for prose |
| `hub/tests/test_spec_rename.py` | +1 test: rename carries the title |
| `hub/tests/test_requirement_gate.py` | `_rigor_mutations()` AST helper replaces two substring scans; **new** `test_no_tool_advertises_a_rigor_argument` |
| `hub/tests/test_migrations.py`, `test_project_persistence.py` | head assertions → `0071` |
| `hub/ui/src/__tests__/specChatSurface.test.tsx` | 3 tests fixed — they indexed `fetch` calls by position |
| `hub/hub/static/ui/` | rebuilt, `diff -rq` identical |
| `src/agentweave/constants.py` | orphaned `AGENTWEAVE_GITIGNORE_PATTERNS` + markers **deleted** |
| `CLAUDE.md` | "21 starter charters" → 9, pointing at `charters.json` |
| `openspec/changes/2026-08-14-what-the-product-actually-built/` | **new** — `proposal.md`, `design.md`, `tasks.md`, and deltas under `specs/` on `task-lifecycle-governance`, `spec-document-authority`, `agent-capability-plane`, `local-project-workspace` |
| `openspec/changes/2026-08-13-approved-means-it-is-in-the-product/tasks.md` | 6.2 and 6.7 **unchecked** with what was really true |
| `openspec/explorations/2026-08-13-loop5-…-nothing.md` | **new** this session, plus a `## Resolution` section |

## Key decisions

1. **The footprint root is derived from the evidence row, not passed in.** `capture_footprint` reads
   `evidence.actor_kind` / `evidence.actor`, so no route changed. Rejected: threading an `agent`
   argument through `record` and both routes — the footprint hangs off the row, so deriving it there
   means the two cannot disagree, and a later backfill gets it right for free.
2. **`refresh_reachability` had to ship in the same commit.** `EvidenceFootprint.reachable_from_main`
   is written once at capture, and evidence is always recorded *before* integration — so without
   this, the footprint fix would replace a false positive with a **permanent false negative**
   (`verified, not integrated` forever, including right after a merge).
3. **Drift compares against the branch a footprint names**, cached per ref. Without it, agent
   footprints make **every accepted requirement** a candidate on the first scan — reporting "this is
   not on master", which coverage already says. Rejected: switching the basis to main once
   reachable — that makes the basis depend on a column `refresh_reachability` mutates, and drift
   would flip bases underneath an open candidate.
4. **`existing_worktree` asks git, not the filesystem.** A git command run inside a directory git
   does not track **walks up to the enclosing repository**, so `.exists()` would return the project
   checkout's HEAD while appearing to have checked. There is a dedicated test for the stale-directory
   case.
5. **The operator keeps the project root for their own evidence.** Safe by construction: git refuses
   to check out a branch already checked out in a linked worktree, so the project checkout can never
   *be* an agent's branch.
6. **Statements are read from the document, never stored.** `SpecRequirement` holds no wording by
   explicit design; a column would violate that deliberately. Batched one read per distinct document
   per request.
7. **The read tool returns the payload, not the rendered HTML**, with identifiers joined on and
   acceptance criteria nested under their requirement. Readable at **any phase** — a capability
   refused depending on state is one an agent concludes it does not have.
8. **Approval materialises `payload.tasks`, a convention that already existed.** `spec_payload`
   validates the keys, `spec_completeness` reads them, nothing consumed them. Idempotent by
   `(project_id, document_id, spec_task_key)`; an existing task is never modified or reassigned.
9. **`.gitignore` seeding covers only what the Hub creates** — not `__pycache__`, which belongs to
   the project's language, not to us.
10. **`0071` uses no ForeignKey on `spec_document_id`** — see Dead ends.

## Constraints and user directives (verbatim)

**From this session:**
- *"I want to test what was developed now. So I project from 0 with the agents. We need to create
  the spec, the spec should generate the tasks and the agents should work on it. At least one
  feature nothing very complicated. We should check every friction point. If the spec is good. If we
  can evolve the spec... Anything that you can check."*
- On spec→tasks: *"Since it's a html we should have a convention. On approval the hub creates the
  tasks based on what is on the html. So the html should have everything needed."*
- On the interview backstop, **declining the fix**: *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test. The operator will answer those
  questions when he's working on it."* → G5 is a **non-goal**, do not re-propose it.
- Packaging: *"One change covering everything."*
- *"Local first. Yes the merge happens automatically."* — and on GitHub, *"it's the first"* reading:
  the PR is **where the single approval happens**, not a second ceremony.
- *"plan approved. Implement everything"*

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that his
  work is good."* · *"only test agents can accept the evidence… If no tester agent then all defers to
  the operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session — all three found by running against a real project, not by the suite:**

- **`git merge` fails with "Committer identity unknown"** in a repository with no configured
  `user.email`. `snapshot_worktree` had always supplied `-c user.name/-c user.email`; the merge did
  not. Every test repository sets an identity in setup, so no test could reach it. Fixed via
  `worktrees.COMMIT_IDENTITY`, used by both.
- **`.gitignore` seeding placed only in the new-project path did nothing.** `open_existing` returns
  early for an already-registered project, and existing projects are precisely the set whose agents
  have already been committing. Now called on all three return paths.
- **The UI staleness warning could not be cleared.** It watched all of `hub/ui/src` including
  `__tests__`, which is never bundled; an identical rebuild commits nothing, so the artefact's commit
  date never moves and the warning stands forever.

**Other new dead ends:**

- **A `ForeignKey` on a new nullable column makes the migration irreversible in SQLite** —
  `error in table tasks after drop column: unknown column "spec_document_id" in foreign key
  definition`. Same class as the CHECK-constraint trap on `TaskTransition.origin`, different
  spelling. Caught by `test_migration_0052_downgrade_drops_the_history`.
- **The openspec validator reads only a requirement's FIRST PHYSICAL LINE** when checking for
  SHALL/MUST. A modal that wraps to line two fails with "must contain SHALL or MUST". This also
  explains the earlier em-dash failure. **Put SHALL on the first line.**
- **`readableApiError` discarded object-shaped `detail`** (fixed in the prior session's `cb39e1c`),
  which is why B4's gate refusal rendered as "The Hub refused this change."
- **Do not assert `fetchMock.mock.calls[0]` in UI tests.** Any added query takes slot zero. Three
  `specChatSurface` tests broke this way at `4b78c8a` and were not caught because that session ran
  three vitest files rather than the suite.
- **`npx openspec new change` rejects a name starting with a digit** — create by hand (carried, still
  true).
- **`git add -A` after `black`/`ruff --fix`** will sweep unrelated reformatting; stage paths
  explicitly.

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`black` without `--target-version py311`** reformats into py38-invalid `with` statements.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`**
  (`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`).
- **PowerShell's `Invoke-RestMethod` swallows error bodies** — use `curl` via the Bash tool to read a
  refusal.
- **`git commit -m @'…'@` is PowerShell syntax; the Bash tool is Git Bash.** Use a heredoc into
  `git commit -F -`.
- **`vitest` full-suite runs flake** on `chartersUi` / `runnersUi` under load; both pass in isolation.
- **Never `git stash` during a background pytest run.**

## Verification

**Ran, with real output:**
- `pytest tests/ -q` — **360 passed, 3 skipped.**
- `ruff check hub/ src/` — **All checks passed.** `black --target-version py311` on every file touched.
- `npx tsc --noEmit` — clean.
- `npx vitest run` — **839 passed, 2 failed**; the two are `chartersUi` and `runnersUi`, confirmed to
  **pass in isolation** (the documented load flake).
- `npx openspec validate --changes --strict` — **16 passed, 0 failed.**
- `npm run build`; `hub/hub/static/ui` replaced; `diff -rq` **identical**.
- Per-file pytest runs, all green: `test_evidence_footprint_root.py` (19), `test_spec_reading.py`
  (8), `test_read_spec_document.py` (10), `test_spec_declared_tasks.py` (6),
  `test_task_integration.py` (21), `test_migrations.py` + `test_project_persistence.py`,
  `test_mcp_*` (55), `test_tasks.py`, `test_requirement_links.py`, `test_spec_rename.py` (19),
  `test_project_lifecycle.py`, `test_spec.py`, `test_requirement_evidence.py`.
- **Live on `aw-loop5`** — the full before/after table in "Current state" above. Every line of it is
  real command output, not inference.

- ✅ **`pytest hub/tests/ -q` — 1864 passed, 10 skipped** (11m19s), at `d10ef7e`. It ran **after** the
  handoff was first written and **found two real failures that every per-file run had missed**, now
  fixed in `d10ef7e` — see below. Re-running it is no longer next step 1, but note the fix itself has
  only been verified by running `test_requirement_gate.py` (25 passed), not by another whole-suite pass.

**What the full suite caught, and why it matters as a lesson:**
`test_no_agent_facing_route_sets_rigor` and `test_the_tool_surface_offers_no_way_to_set_rigor`
asserted `"rigor" not in source` over whole modules. `read_spec_document` returns
`"rigor": document.rigor` by design (D7), so both failed. **The property was never violated** — the
only occurrences are one dict-literal read and one docstring, with no `set_rigor` or `spec_rigor`
anywhere in either module. The tests forbade the *word*, conflating reading with writing. They now
walk the AST for the four ways rigor could actually be set (attribute assignment, a bound
name/Pydantic field, a `rigor` argument, a `set_rigor`/`spec_rigor` reference), each verified against
a synthetic violation, plus a new test asserting no tool's **generated schema** advertises a `rigor`
property. Strictly stronger than the substring, which any alternative spelling would have defeated.

**NOT run, and it matters:**
- **Phase 10 (human-only) has not been done** — five judgements, `tasks.md` §10.
- **No agent has actually used `read_spec_document` in a live run.** It is tested over HTTP and over
  stdio, and named in the turn context, but no real agent has been observed calling it.
- **Approval-creates-tasks has never run on a real project** — only in tests. `aw-loop5`'s document
  was approved before the feature existed.
- **Spec evolution was never exercised**, in this run or the previous one: reopen an approved
  document, reword a requirement, confirm evidence goes `stale` and links survive.
- **`npx vitest run` was not re-run after the final commits** (only `specChatSurface` in isolation).

## Git state

Branch `hub-native-experience`, HEAD **`d10ef7e`**, working tree **clean** except `?? hub/agentweave.db`
(pre-existing stray, not the live DB), **46 unpushed commits** (11 from this session).

**Live environment:** Hub on `:8010`, health `ok`, running `1234abb`-era code with migrations through
**`0071`** applied. Find the PID with `Get-NetTCPConnection -LocalPort 8010 -State Listen`. **It does
not have `0086a2f`'s exploration-only change, which is documentation and does not affect it.**

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`
(`proj-471e281a`), and **`aw-loop5` (`proj-30d900a7`, at `C:\Users\huida\Documents\aw-loop5`)**.

**Keep `aw-loop5`.** It is the reproduction for the whole session and now the worked example of the
fix: `master` carries `habits.py`, `test_habits.py` and a real merge commit that arrived through the
product. A run credential was minted into it for verification — `run-verify5`, token
`aw_run_verify-loop5` — which should be cleaned up if the project is ever shared.

## Next steps

1. **Re-run the full Hub suite once**, to confirm `d10ef7e` in the whole-suite context:
   `python -m pytest hub/tests/ -q` from the repo root, with the Python311 interpreter.
   Expect **1865 passed, 10 skipped** — one more than the 1864 recorded, from the new
   `test_no_tool_advertises_a_rigor_argument`. Takes ~11 minutes; run it in the background.
2. **Then `npx vitest run`** from `hub/ui` once, to confirm nothing beyond the two known flakes.
3. **Phase 10 human-only verification** — `openspec/changes/2026-08-14-what-the-product-actually-built/tasks.md`
   §10. 10.1 is the one the change rests on: does the first automatic merge feel safe or alarming?
4. **Archive the two changes** once phase 10 is done —
   `2026-08-13-approved-means-it-is-in-the-product` (whose 6.2/6.7 are now correctly unchecked and
   are fixed by the newer change) and `2026-08-14-what-the-product-actually-built`. By hand; the
   openspec CLI rejects names starting with a digit.
5. **Re-run `/e2e-loop` from zero.** Every finding this session was invisible to a green unit suite
   because it lived between features. Specifically unexercised: spec evolution, approval creating
   tasks on a real project, and an agent using `read_spec_document`.

## Open questions for the user

1. **Push?** 46 unpushed commits. The `ci.yml` question is settled (*"just push the branch"*) but the
   push has not been done.
2. **`aw-loop5` cleanup** — keep it as the worked example (recommended), or `python
   .claude/skills/e2e-loop/e2e.py clean proj-30d900a7`? The minted `run-verify5` credential lives in
   it either way.
3. Carried: should `.claude/handoffs/` stay tracked (**now 128 files including `LATEST.md`**)?

## Read on resume

- `openspec/explorations/2026-08-13-loop5-integration-reports-success-while-integrating-nothing.md` —
  all eleven findings and the `## Resolution` section; the record of what the run cost and what closed it.
- `openspec/changes/2026-08-14-what-the-product-actually-built/tasks.md` — §10 is what remains, §11 is
  the user test guide to follow.
- `openspec/changes/2026-08-14-what-the-product-actually-built/design.md` — D1–D10; read D2 and D4
  before touching the footprint or reachability paths, they encode traps.
- `hub/hub/requirement_evidence.py` — `footprint_root`, `refresh_reachability` and `detect_drift`;
  the three interlocking pieces of the main fix.
- `hub/hub/spec_tasks.py` — the newest and least-exercised module; nothing has run it on a real project.
- `hub/tests/test_evidence_footprint_root.py` — the fixture shape any future integration test must
  copy, and its docstring explains why the previous tests could not see the defect.
