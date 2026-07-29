# Handoff: Change 1 (`add-spec-manifest`) verified and fully implemented — 35/35 tasks, all green, nothing committed

**Date:** 2026-07-28T23:20+0100 · **Branch:** `master` · **HEAD:** `283463d`
**Agent:** Claude Code (Sonnet 5, `claude-sonnet-5`)
**Previous handoff:** `.claude/handoffs/2026-07-28-2203-kimi-fix-and-commit-split.md`
**Status:** chunk complete — working tree dirty (uncommitted implementation), nothing pushed

## Goal

Continue the spec-journey work: Codex proposed Change 1 (`add-spec-manifest` — the manifest
system that fixes the two-hard-coded-glob discovery bug and makes the Hub's spec sync
multi-machine-safe). This session's job was (a) verify Codex's proposal against the live
code, then (b) apply/implement it end-to-end per `openspec/changes/add-spec-manifest/tasks.md`.
The *why*: the user is authoring specs through the Hub Spec tab and the current Hub only
recognizes `spec/spec.html`/`spec/changes/*/spec.html` — this repo's own baseline
(`spec/agentweave-spec.html`) was invisible to the Hub before this change.

## Current state

**Both objectives done. All 35 tasks across 7 sections are implemented and checked off in
`openspec/changes/add-spec-manifest/tasks.md`. Nothing is committed.**

1. **Verification (first half of session, before compaction):** every factual claim in
   Codex's `proposal.md`/`design.md` was checked against the live code and held up,
   including one confirmed real bug (the spec role's HTML-conventions reference pointed at
   a `references/` subfolder that doesn't exist in generated skill output). `openspec
   validate add-spec-manifest --strict` passed. User then said "I want you to apply it."

2. **Implementation, section by section, via the `openspec-apply-change` skill:**
   - **§1 Manifest module** — `src/agentweave/spec_manifest.py` (new): `validate_spec_path`,
     `discover_spec_files`, `load_manifest`/`Manifest`/`ManifestDocument`/`ManifestDiagnostic`,
     `parse_html_head`, `compute_intrinsic_conflicts`. Wired into `watchdog._discover_spec_files`
     (replacing the two-glob implementation).
   - **§2 CLI/HTTP reconciliation** — `transport/config.py` `_ensure_spec_source_id` (lazy,
     persisted, non-secret per-workspace ID); `transport/http.py` `reconcile_specs()`;
     `watchdog._sync_spec_files`/`_reconcile_specs` rewritten to track per-file state +
     inventory/manifest fingerprint and only reconcile after a fully-successful cycle;
     `cli.py` `cmd_spec_push` rewritten with `--prune` and diagnostics reporting.
   - **§3 Hub persistence/API** — `hub/hub/spec_manifest.py` (new, independent copy — Hub
     never imports the CLI package); `ProjectSpecSnapshot` model + migration `0010`;
     `hub/hub/api/v1/spec.py` rewritten: structured path validation, `POST
     /project/specs/reconcile` (drift computation, `ACTIVE_SOURCE_TTL_SECONDS=300`,
     conflict-safe prune), `GET /project/specs` enriched additively
     (`home`/`manifest`/`missing`/`diagnostics`), SSE `spec_updated` now carries `{reason}`
     for reconciliation-only events (no `path`) vs `{path}` for per-file syncs.
   - **§4 Hub UI** — `hub/ui/src/api/spec.ts` enriched types; `SpecPage.tsx`: home selection
     prefers `specList.home`, a compact drift banner (expandable detail), and a **Repair
     manifest** button (prefers an idle `spec`-role agent, falls back to the selected chat
     agent, honors the existing new/resume session toggle).
   - **§5 Skills/role** — new `/aw-spec-reindex` skill + shared
     `spec-manifest-conventions.md` reference; `/aw-spec-propose` and `/aw-spec-archive`
     updated to maintain `spec/index.json`; removed the obsolete `spec/specs/` merge flow
     from archive; `html-spec-conventions.md` made kind-aware (`living` for
     baseline/system-map/roadmap, `draft`/`approved` only for `change-spec`); both spec-role
     sources (`src/agentweave/templates/roles/spec.md`, `hub/hub/data/roles/spec.md`) leaned
     and kept byte-identical (test added), the broken `.agents/skills/.../references/...`
     path fixed.
   - **§6 Docs** — `aw-spec-workflow.md` gained a "Spec Manifest and the Hub" section;
     `cli-commands.md` gained a `## Spec` section documenting `spec push`/`--prune`; the
     framework's own baseline `spec/agentweave-spec.html` updated (changelog row, DB/endpoint
     tables, role/UI descriptions) — see "Dead ends" below re: its pre-existing validator
     failures; **this repo's `spec/index.json` was generated** (home=baseline, +system-map,
     +roadmap) and verified to produce zero diagnostics and zero intrinsic conflicts.
   - **§7 Verification** — see below.

## Files touched

Everything below is **uncommitted** (`git status --short` — 23 modified, 12 new). Full list
from `git status`/`git diff --stat HEAD` (24 files changed, 1381 insertions, 165 deletions,
plus 12 new untracked files):

**New:**
- `src/agentweave/spec_manifest.py`, `tests/test_spec_manifest.py`
- `hub/hub/spec_manifest.py`, `hub/tests/test_spec_manifest.py`
- `hub/hub/migrations/versions/0010_add_project_spec_snapshots.py`
- `hub/tests/test_spec_reconcile.py`
- `hub/ui/src/__tests__/specManifestRepair.test.tsx`
- `tests/test_spec_push.py`, `tests/test_transport_config.py`
- `src/agentweave/templates/skills/aw-spec-reindex.md`
- `src/agentweave/templates/skills/references/spec-manifest-conventions.md`
- `spec/index.json`

**Modified (CLI):** `src/agentweave/cli.py` (spec push --prune, SKILL_SUPPORT_FILES),
`src/agentweave/watchdog.py` (discovery + reconciliation), `src/agentweave/transport/config.py`
(source_id), `src/agentweave/transport/http.py` (reconcile_specs), `tests/test_http_transport.py`,
`tests/test_watchdog.py`, `tests/test_roles.py`, `tests/test_skill_templates.py`

**Modified (Hub):** `hub/hub/api/v1/spec.py`, `hub/hub/db/models.py`,
`hub/tests/test_migrations.py` (version bumped 0009→0010 in 3 assertions/docstrings),
`hub/ui/src/api/spec.ts`, `hub/ui/src/components/spec/SpecPage.tsx`

**Modified (skills/role/docs):** `src/agentweave/templates/roles/spec.md`,
`hub/hub/data/roles/spec.md` (kept identical), `src/agentweave/templates/skills/aw-setup.md`,
`aw-spec-archive.md`, `aw-spec-propose.md`, `references/html-spec-conventions.md`,
`docs/guides/aw-spec-workflow.md`, `docs/reference/cli-commands.md`,
`spec/agentweave-spec.html`, `validate_spec.py` (fixed stale `PATH` constant),
`openspec/changes/add-spec-manifest/tasks.md` (all 35 boxes checked, gitignored — not in
this diff list, but changed on disk)

**Unrelated to this change, pre-existing dirty:** `.claude/handoffs/LATEST.md` (handoff
bookkeeping) — ignore.

## Key decisions

**Hub re-validates independently — no import from the CLI package.** `hub/hub/spec_manifest.py`
is a hand-maintained copy of `src/agentweave/spec_manifest.py`'s structural-validation half
(not the filesystem-discovery half, which the Hub never does). This was Codex's design
decision (§2 of design.md), confirmed correct: `hub/pyproject.toml` has zero dependency on
`agentweave`. Keep the two in sync by hand on future edits — there is deliberately no shared
import.

**Reconciliation state machine — "claimed" set.** `claimed = union(active-snapshot
inventories) ∪ union(active-valid-manifest document paths)`. A `ProjectSpec` row not in
`claimed` is `stale`; only `--prune` deletes stale rows, and only after recomputing `claimed`
with the pruning source's own just-submitted snapshot included (so a source can't
accidentally orphan its own paths mid-request). `ACTIVE_SOURCE_TTL_SECONDS = 300` (5 min,
comfortably above the 120s heartbeat threshold already used elsewhere in the Hub).

**Four-way document state, not two.** Landed on `filed` (covered by the current valid
manifest) / `unindexed` (no source has ever reconciled — legacy `/specs/sync`-only content)
/ `unfiled` (an active source's inventory has it, no manifest entry) / `stale` (no active
source claims it at all). The three-way version I started with conflated "never reconciled"
with "reconciled but manifest-omitted", which would have broken the explicit "legacy CLI ...
lists it as unindexed" scenario in the delta spec. *Rejected:* a simpler
claimed-vs-not-claimed boolean — loses the legacy-vs-drift distinction the UI needs.

**SQLite naive/aware datetime bug, fixed once at the source.** `_snapshot_view()` strips
`tzinfo` immediately when reading `ProjectSpecSnapshot.updated_at` from the DB, because
SQLite round-trips `DateTime(timezone=True)` as naive while a freshly-flushed row's
`_now()` default is aware — comparing them directly (`max(..., key=...)`) raised
`TypeError`. Normalizing once at read time was simpler than threading tz-safety through
every comparison site.

**Test isolation for Hub drift tests.** `hub/tests/test_spec_reconcile.py` creates a fresh
project+API-key per test (BOLA-fixture pattern from `test_bola.py`) rather than sharing the
bootstrap `proj-test` project that `test_spec.py` uses — drift computation looks at *every*
snapshot for a project, so sharing would let one test's leftover snapshots pollute another's
"active source" set.

**`validate_spec.py` fixed, not the pre-existing failures it now reveals.** Its `PATH`
constant still said `spec/agentweave-1.0-spec.html` (stale from the spec-root-rename
session, three sessions ago) — fixed to `spec/agentweave-spec.html` so I could use it to
check my own edits to the baseline spec. Running it now surfaces two **pre-existing**
failures unrelated to this change (see Dead Ends) — deliberately not fixed; out of scope and
the user hasn't asked for a spec-consistency repair pass.

**No version bump in `spec/agentweave-spec.html`'s changelog.** Added a 2026-07-28 row
describing the change but kept `CLI v0.42.0 · Hub v0.35.0 (unreleased)` — `pyproject.toml`
values are unchanged and are the single source of truth per `CLAUDE.md`; inventing a version
number would have been wrong.

## Constraints and user directives (verbatim)

From **this** session:
- "I want you to first verify the work done by codex on change 1. It already has a openspec
  writen" — verification requested before any implementation.
- "I want you to apply it." — the instruction to implement, given after verification passed.

Carried forward from **earlier** handoffs (still binding, not yet acted on this session):
- "Assume only kimi 0.x is used. Kimi 1.x is not supported by agentweave"
- "I want before actually coding executing a explore on 4 and 6 to make sure everything is
  in order then proposing. Not going to execute this after I execute 1." — Change 1 is now
  done; Changes 4/6 explore-then-propose is the logical next spec-journey item, but the user
  has not yet re-raised it this session.
- "commit everything but split by commits." (from the *previous* session, about that
  session's tree — likely still the user's general preference for this repo, worth
  confirming before committing this session's work.)
- Standing `CLAUDE.md` rules: never commit `.agentweave/*`; templates via `get_template()`;
  `with lock("name"):` for task mutations — none touched this session.

## Dead ends

- **`validate_spec.py` reports two pre-existing, unrelated failures** on
  `spec/agentweave-spec.html`: `h2 sequence wrong: [0..14]` (expects `0..17`) and an FR-index
  mismatch (every `FR-*` ID is defined in the body but the §14 index table that's supposed to
  list them appears empty to the parser). Confirmed these existed **before** my edits (same
  failure list before and after touching the file — verified by running the validator
  immediately after fixing its stale `PATH`, before making any content edits). Not fixed;
  flagged to the user, not investigated further.
- **Ruff `SIM300` (Yoda condition)** flagged `"spec/.hidden/spec.html" == d.path` in a test —
  trivial, fixed inline (`d.path == "..."`), not a real finding.
- **Black auto-reformatted every new file after first write** — expected; just re-ran tests
  after each reformat pass, no actual behavior changes from it.

## Verification

**Ran and passed, end of session (after all 35 tasks):**
- `.venv/Scripts/python.exe -m pytest tests/ -q` → **653 passed, 4 skipped**
- `cd hub && ../.venv/Scripts/python.exe -m pytest tests/ -q` → **231 passed, 4 skipped**
- `cd hub/ui && npx vitest run` → **75 passed, 13 files**
- `cd hub/ui && npx tsc --noEmit` → clean
- `cd hub/ui && npm run build` → succeeds (pre-existing unrelated esbuild warning in
  `eventSummary.ts`, not touched this session)
- `.venv/Scripts/python.exe -m ruff check src/ hub/ tests/` → all checks passed
- `.venv/Scripts/python.exe -m black --check src/ hub/ tests/` → 137 files unchanged
- `.venv/Scripts/python.exe -m mypy src/` → no issues (hub/ mypy is NOT CI-gated —
  `grep mypy .github/workflows/ci.yml` confirms only `mypy src/` runs; hub/ has ~90
  pre-existing `no-untyped-def`/etc. errors in files I didn't touch, left alone)
- `npx openspec validate add-spec-manifest --strict` → valid
- **Live end-to-end exercise** (task 7.4): started a real Hub via `uvicorn hub.main:app` on
  `127.0.0.1:8811` with a temp SQLite DB, drove the real `agentweave.exe spec push` binary
  from two simulated machine checkouts sharing one Hub project. Confirmed: (a) an older
  checkout's inventory omitting a document the other checkout has doesn't hide/delete it;
  (b) ordinary `spec push` (no `--prune`) reclassifies a genuinely-deleted document as
  `stale` in the diagnostics but never removes it — verified via `GET /project/spec` still
  returning 200; (c) `spec push --prune` removed exactly the one true orphan
  (`spec/roadmaps/epic.html`, claimed by neither machine) and left the other two documents
  untouched — verified via 404 on the pruned path and 200 on the survivors. Hub process
  killed cleanly afterward (PID 12688 via PowerShell `Stop-Process`).

**NOT run:**
- `mkdocs build` — mkdocs isn't installed in this environment (`pip show mkdocs` → not
  found; it's the optional `docs` extras group in `pyproject.toml`). Pre-existing gap per
  the prior handoff too. The two docs files I edited are plain markdown/code-block prose —
  low risk, but genuinely unverified by a real mkdocs build.
- The live exercise didn't test the `active_source_conflict` (two disagreeing manifests) or
  `prune_conflict` (prune blocked by another active source) paths live — those ARE covered by
  `hub/tests/test_spec_reconcile.py::TestSourceConflict` and
  `TestPrune::test_prune_preserves_path_claimed_by_another_active_source` through the real
  FastAPI app (httpx `ASGITransport`, real DB, not mocked), just not through the actual CLI
  binary over real HTTP the way the rest of 7.4 was.
- `/aw-spec-reindex` itself was never run by an actual agent — it's a markdown skill
  instruction file; verified via `tests/test_skill_templates.py` (bundling, support files,
  content assertions) but its *behavior* when an LLM agent actually follows it is unverified
  (same category of "not run" as every other aw-spec-*.md skill in this repo).
- Nothing in this session's diff has been through CI — still true from the prior handoff for
  the earlier 12 commits, and now equally true for this session's uncommitted 24 changed +
  12 new files.

## Git state

- **Branch:** `master`
- **HEAD:** `283463d` "Track session handoff notes" (unchanged since the previous handoff)
- **Dirty:** yes — 23 modified files, 12 new untracked files (all this session's
  implementation), plus the pre-existing `.claude/handoffs/LATEST.md` bookkeeping churn.
- **Unpushed:** 12 commits from before this session (see previous handoff) — this session
  added zero commits; everything above is uncommitted working-tree state.
- No branch created, no push, no rebase performed this session.

## Next steps

1. **Ask the user whether/how to commit this session's work.** The previous session's
   instruction was "commit everything but split by commits" — confirm that still applies,
   then split by the 7 section boundaries above (manifest module / transport+watchdog / Hub
   API+migration / Hub UI / skills+role / docs / — verification changes fold into whichever
   section they belong to, e.g. the `hub/tests/test_migrations.py` version-bump edit belongs
   with the migration commit). Do not commit `openspec/changes/add-spec-manifest/tasks.md`
   or `spec/index.json`'s generation — wait, `openspec/` is gitignored (see below) but
   `spec/index.json` is NOT gitignored and should be committed alongside the docs/spec commit.
2. **Decide whether to archive `add-spec-manifest`.** All 35 tasks are done and verified;
   it's a candidate for `/opsx:archive` or the `aw-spec-archive` equivalent once the user
   confirms they're satisfied. Not archived yet — user hasn't been asked.
3. **Optionally fix the two pre-existing `validate_spec.py` failures** (h2 sequence, FR-index)
   found as a side effect this session — separate, unscoped work; flagged, not started.
4. **Return to the still-open spec-journey thread:** Changes 4 (`add-agent-stream-kinds`) and
   6 (`fix-context-tracking-all-runners`) explore-then-propose, and the still-undecided
   "#4/#6: one change or two?" question from two sessions ago (user said "not yet — discuss
   first" when last asked, in the conversation before this implementation work started).
5. **Push decision still outstanding** — now 12 commits *plus* this session's uncommitted
   work once committed. Nothing has been through CI.

## Open questions for the user

1. **Commit this session's work now?** And if so, one bundled commit or split by the 7
   sections (matching the pattern from the previous session's 11-commit split)?
2. **`#4`/`#6`: one change or two?** Still unanswered from before this session.
3. **Push everything (old 12 commits + this session once committed)?** Nothing has run
   through CI yet.
4. Do you want the two pre-existing `spec/agentweave-spec.html` validator failures
   (h2 numbering, FR-index) fixed as a follow-up, or left alone?

## Read on resume

- `openspec/changes/add-spec-manifest/tasks.md` — **read first.** All 35 boxes checked;
  confirms exactly what's implemented vs. this handoff's prose. Gitignored (`openspec/*`),
  not backed by git — this file and the exploration record are the only durable copies of
  this change's planning state.
- `hub/hub/api/v1/spec.py` — the core of the Hub-side implementation (`_compute_state`,
  drift/prune logic); read before touching anything spec-sync related on the Hub side.
- `src/agentweave/spec_manifest.py` / `hub/hub/spec_manifest.py` — the two independent
  manifest-validation copies; remember they have no import relationship and must be
  hand-kept in sync.
- `hub/ui/src/components/spec/SpecPage.tsx` — the UI's drift banner + repair trigger; read
  before any further Spec-tab UI work.
- `spec/agentweave-spec.html` — the framework's own baseline; has two pre-existing,
  unrelated `validate_spec.py` failures (see Dead Ends) worth knowing about before editing
  it further.
