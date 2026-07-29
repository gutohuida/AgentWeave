# Handoff: Change 4 sections 5-7 complete; context UI section 8 next

**Date:** 2026-07-29T12:25:17+01:00 · **Branch:** `master` · **HEAD:** `17f6f76`
**Agent:** Codex (GPT-5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1204-change4-section4-complete-section5-next.md`
**Status:** chunk complete

## Goal

Implement OpenSpec Change 4, `add-agent-stream-kinds`, so every supported runner produces one
canonical structured stream-event contract and one canonical context-usage contract, delivered
safely through the CLI, Hub, and UI with rolling-upgrade compatibility. Sections 1-7 are complete;
section 8 must now make every Hub context surface consume and present the same canonical state.

## Current state

Sections 5, 6, and 7 were implemented and committed in this session:

- `fb950ce` adds Hub migration `0011`, structured AgentOutput persistence/validation, REST/SSE/chat
  projection, deterministic newest-window retrieval, and Hub tests.
- `f7e7dad` replaces context dictionary ingress with a canonical Pydantic schema, normalizes legacy
  aliases, persists latest snapshots through EventLog, projects the identical object through SSE
  and agent summaries, and ignores stale observations.
- `17f6f76` adds one shared UI stream model/renderer, structured AgentOutput API/SSE types,
  per-run thinking grouping and duration, tool pairing, semantic status/diagnostic/error display,
  one legacy-prefix adapter, and integrations in AgentOutputPanel, SpecPage, and AgentActivityTab.

Tasks 5.1-7.9 are checked in `openspec/changes/add-agent-stream-kinds/tasks.md`. Section 8 is
unstarted. The current `ContextUsage` TypeScript interface in `hub/ui/src/api/agents.ts` still uses
legacy fields (`tokens_used`, `tokens_limit`, warning flags, `updated_at`), while the Hub now
projects canonical fields (`status`, `context_tokens`, `limit_tokens`, `basis`, `source`,
`observed_at`, etc.). Existing context renderers therefore need a shared normalization and
presentation helper before they can correctly show measured, estimated, token-only, unavailable,
unsupported, and new-session reset states.

## Files touched

- `hub/hub/migrations/versions/0011_add_agent_output_stream_fields.py` — migration adding nullable
  stream fields and the project/agent/run/sequence index; finished and committed in `fb950ce`.
- `hub/hub/db/models.py` — AgentOutput structured columns and index; finished and committed.
- `hub/hub/schemas/agents.py` — bounded stream schemas plus canonical context schema and legacy
  normalization; finished and committed across `fb950ce` and `f7e7dad`.
- `hub/hub/api/v1/agents.py` — stream persistence/SSE/newest-window retrieval and typed context
  latest-snapshot ingress; finished and committed.
- `hub/hub/api/v1/agent_chat.py` — structured chat projection and stable output ordering; finished
  and committed.
- `hub/tests/test_agent_output_stream.py` — stream migration/API/SSE/chat/ordering tests; finished
  and committed.
- `hub/tests/test_context_usage.py` — canonical/legacy/state/stale context tests; finished and
  committed.
- `hub/tests/test_migrations.py` — head revision updated to 0011 and migration columns/index
  asserted; finished and committed.
- `hub/ui/src/api/agents.ts` — structured AgentOutputLine types and SSE propagation; finished and
  committed in `17f6f76`. Its legacy ContextUsage interface is the next edit target.
- `hub/ui/src/components/stream/streamModel.ts` — single structured/legacy semantic adapter and
  activity projection; finished and committed.
- `hub/ui/src/components/stream/SharedStreamRenderer.tsx` — shared stream UI; finished and
  committed.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — now uses shared renderer; finished and
  committed.
- `hub/ui/src/components/spec/SpecPage.tsx` — now uses shared renderer with diagnostics hidden but
  errors retained; finished and committed.
- `hub/ui/src/components/agents/AgentActivityTab.tsx` — uses semantic activity projection instead
  of prefix classification; finished and committed.
- `hub/ui/src/__tests__/streamRenderer.test.tsx` — deterministic shared renderer tests; finished
  and committed.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — tasks 5.1-7.9 marked complete; committed.
- `.claude/handoffs/LATEST.md` — tracked handoff pointer, dirty by design and updated to this file.
- `.claude/handoffs/2026-07-29-1225-change4-section7-complete-section8-next.md` — this handoff.
- `.claude/handoffs/2026-07-28-2203-kimi-fix-and-commit-split.md` — pre-existing untracked handoff,
  unchanged.
- `.claude/handoffs/2026-07-28-2320-add-spec-manifest-implementation.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-0040-change1-archived-stream-kinds-next.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-0155-change4-stream-kinds-adapters-in-progress.md` — pre-existing
  untracked handoff, unchanged.
- `.claude/handoffs/2026-07-29-0947-change4-stream-kinds-section2-done.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-1015-change4-section3-3-of-4-collectors-done.md` — pre-existing
  untracked handoff, unchanged.
- `.claude/handoffs/2026-07-29-1115-change4-section3-done-section4-next.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-1134-change4-section4-4to8-uncommitted.md` — pre-existing untracked
  handoff, unchanged.
- `.claude/handoffs/2026-07-29-1204-change4-section4-complete-section5-next.md` — previous handoff,
  pre-existing and unchanged.

## Key decisions

- Hub stream fields are additive and nullable. Readable `content` remains the compatibility
  fallback; rejecting legacy rows or replacing the endpoint was rejected because rolling upgrades
  must keep working.
- The run-ordering index is `(project_id, agent, run_id, sequence)`. Default retrieval selects
  descending stable keys and reverses the newest window; legacy null sequences coalesce to `-1`
  for consistent SQLite/PostgreSQL behavior.
- Hub context remains a latest snapshot in the existing `context_warning` EventLog path; no new
  context table/migration was added because implementation evidence did not require one.
- Canonical Hub context payloads are strictly validated. Payloads without `status` are treated as
  rolling-upgrade legacy input and normalized at ingress. Stale `observed_at` values are ignored
  before persistence/SSE so an older session cannot replace the newer snapshot.
- Stream rendering semantics live in one shared model. SpecPage hides diagnostics through a
  semantic flag, never prefix filtering, and errors are never hidden. Activity consumes the same
  semantic projection.
- Thinking is grouped by consecutive events sharing `run_id`, remains visible while live, and
  collapses after subsequent output. Tool use/result pairing requires both matching `run_id` and
  `call_id`; unmatched tools render independently rather than receiving invented IDs.
- Copilot still keeps unresolved model/limit absent. Kimi task 3.10 remains intentionally
  unimplemented. New commits only; no history was amended.

## Constraints and user directives (verbatim)

- `"$resume"`
- `"start section 6"`
- `"go on"`
- `"$handoff"`
- Carried forward and still binding:
  - `"yes"` — Copilot context samples remain without model/limit when unresolved.
  - `"Kimi's session-status service (task 3.10) is intentionally not implemented — do not silently
    implement it."`
  - `"New commits, not amends."`
  - `"Zero new runtime dependencies (stdlib only)."`
  - `"Never commit .agentweave/*; use template loading not hardcoded template strings; lock task
    mutations; preserve unrelated dirty work; target Kimi v0.29.x only."`
  - `"Live CLI probes must run in isolated scratch directories outside the repo, cleaned up
    after."`
  - Pushing has not been requested.

## Dead ends

- The previous handoff named migration `0010_add_agent_session_model.py`, but live revision 0010
  is `0010_add_project_spec_snapshots.py`. The revision chain was correct; the stale filename was
  ignored.
- Black initially reported `hub/hub/schemas/agents.py` needed formatting; it was formatted before
  commit.
- Ruff initially reported import ordering and a `try/except/pass` in the context schema; imports
  were reordered and `contextlib.suppress` used.
- `npm run lint` cannot start: installed ESLint is 9.39.4 but `hub/ui` has no
  `eslint.config.(js|mjs|cjs)`. Do not interpret this as feature lint failures or silently add lint
  infrastructure inside section 8.
- UI test runs print the intentional `Error: boom` stack from `ErrorBoundary.test.tsx`; the suite
  still passes.
- Vite build warns about a pre-existing duplicate `task_created` case in
  `hub/ui/src/lib/eventSummary.ts`. It is unrelated to Change 4 and was not modified.

## Verification

Ran and passed:

- `cd hub; ..\.venv\Scripts\pytest.exe tests/test_agent_output_stream.py
  tests/test_agent_chat.py tests/test_migrations.py tests/test_sse.py -q` — **28 passed, 1 skipped**.
- `cd hub; ..\.venv\Scripts\pytest.exe tests -q` after section 5 — **236 passed, 4 skipped**.
- `cd hub; ..\.venv\Scripts\pytest.exe tests/test_context_usage.py tests/test_bola.py -q` —
  **7 passed**.
- `cd hub; ..\.venv\Scripts\pytest.exe tests -q` after section 6 — **240 passed, 4 skipped**.
- Root `.venv` Ruff/Black checks over affected Hub Python files — passed.
- `git diff --check` and `git diff --cached --check` before commits — passed.
- `cd hub/ui; npm test -- --run` after section 7 — **14 files, 81 tests passed**.
- `cd hub/ui; npm run build` — TypeScript and Vite production build passed (432 modules).

Attempted but unavailable:

- `cd hub/ui; npm run lint` — ESLint 9 stopped before linting because no flat config exists.

Not tested:

- No browser/manual flow was run for the shared renderer.
- No live structured output was viewed through a running Hub.
- No CLI suite was rerun because sections 5-7 touched only Hub/backend/UI files and the OpenSpec
  task list.
- No live runner probes were run.
- Nothing was pushed to `origin`.

## Git state

- Branch: `master`
- HEAD: `17f6f76` (`Render structured agent streams across Hub UI`)
- Previous commits: `f7e7dad` (section 6), `fb950ce` (section 5).
- Implementation tree is clean. Dirty state is handoff metadata only:
  `.claude/handoffs/LATEST.md` plus the ten untracked handoff files listed under Files touched
  (nine previous files and this new file).
- `master` is **18 commits ahead of `origin/master`**; none were pushed.
- Upstream remote: `origin`.

## Next steps

1. Implement tasks 8.1-8.2 by replacing the legacy `ContextUsage` interface in
   `hub/ui/src/api/agents.ts` with canonical status/operands/percent/model/session/source/basis/
   observed-time/breakdown fields, then create
   `hub/ui/src/components/context/contextPresentation.ts` containing one normalization and
   presentation helper that accepts canonical data plus rolling legacy aliases. Re-read section 8
   of `openspec/changes/add-agent-stream-kinds/tasks.md` and decision 12 in `design.md` first.
2. Locate every direct `context_usage` consumer in AgentCard, AgentDetailPanel, AgentsPage,
   OverviewPage, and StatusBar. Replace local percentage/threshold logic with the shared helper.
3. Render measured threshold states, label estimates without warning/critical policy, show
   token-only counts with unknown limit, distinguish unavailable/unsupported neutral states, and
   ensure a new-session unavailable snapshot replaces the old bar.
4. Add deterministic UI tests for canonical states, legacy normalization, thresholds, estimates,
   unknown limits, and new-session replacement. Run focused tests, all UI tests, and production
   build. Record the existing ESLint configuration blocker rather than claiming lint passed.
5. Mark tasks 8.1-8.8 complete only after green and create a new commit; do not amend or push.

## Open questions for the user

None. Section 8 can proceed without a new decision. Pushing remains unauthorized.

## Read on resume

- `openspec/changes/add-agent-stream-kinds/tasks.md` — section 8 requirements and progress.
- `openspec/changes/add-agent-stream-kinds/design.md` — decision 12 context presentation policy.
- `hub/ui/src/api/agents.ts` — legacy ContextUsage interface to replace.
- `hub/ui/src/components/agents/AgentCard.tsx` — primary context bar consumer.
- `hub/ui/src/components/agents/AgentDetailPanel.tsx` — detail context consumer.
- `hub/ui/src/components/agents/AgentsPage.tsx` — page-level context projection/threshold logic.
- `hub/ui/src/components/overview/OverviewPage.tsx` — overview context consumer.
- `hub/ui/src/components/layout/StatusBar.tsx` — status context consumer.
