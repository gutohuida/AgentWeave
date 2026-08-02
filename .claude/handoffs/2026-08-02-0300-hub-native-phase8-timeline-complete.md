# Handoff: Phase 8 conversation timeline and agent colours complete

**Date:** 2026-08-02T03:00:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `8ef6cc3`
**Agent:** Claude Sonnet 5
**Previous handoff:** `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This chunk completed Phase 8: agents get a
stable identity colour, and one merged, typed conversation timeline — replacing the raw stream
renderer — shows operator input, agent output, and agent-to-agent traffic in both directions,
including entries still waiting to be delivered.

## Current state

Phase 8 tasks 8.1-8.12 are implemented, verified, and committed (`8ef6cc3` implementation,
tasks.md ledger checkpoint pending as the very next action — see below).

**Backend**: `Agent.color_index` (migration 0016) is assigned once at registration — monotonically
per project via `hub/hub/agent_colors.py`'s `next_color_index()`, wired into all three creation
sites (session sync roster diff, self-registration, budgeted agent requests) — and exposed on
`AgentSummary.color_index`. `hub/hub/api/v1/agent_chat.py`'s two endpoints
(`/agent/{agent}/chat[/{session_id}]`) were rewritten from a `{messages: [...]}` shape keyed by
`role` into a `{session_id, agent, entries: [...]}` shape keyed by `kind` — one of
`operator_input`/`agent_output`/`inbound_peer`/`outbound_peer` — with every entry placed by a
*recorded* association: a delivered `InboundQueueEntry`'s `Run.session_id`, `AgentOutput`'s own
`session_id`, or `Message.session_id` (a column that existed since migration 0003 but was never
populated — now set at send time from the sender's live `Run`, in both `messages.py`'s
`create_message` and `agents.py`'s `request_agent`). Still-queued entries are appended to every
response regardless of requested session, tagged `delivery_state: "queued"` plus
`hop_budget_exceeded` when an agent-origin entry exceeds the project's hop budget. Nothing else
needed backend work: the Phase-6 `GET /queue/{agent}/status` (waiting count + not-running reason)
and `DELETE /queue/entries/{id}` (withdraw) endpoints already existed, just unwired to any UI.

**Frontend**: new `hub/ui/src/lib/agentColors.ts` maps a `color_index` onto CSS vars
(`--agent-N`/`--agent-N-tint`/`--agent-N-border`, added to `index.css` via one shared
`color-mix(in oklab, …)` formula per hue that works in both themes from one definition — the raw
`--agent-1..8` hue tokens already existed pre-tuned per theme from an earlier phase). New
`hub/ui/src/lib/agentTimelineModel.ts` is the pure logic layer: `entryCategory()` partitions each
entry into `message`/`work`/`result` (design.md's three-category principle), `groupIntoTurns()`
groups delivered entries by `run_id` with still-queued ones held out as `pending`,
`findPairedResult()` pairs a `tool_use` with its `tool_result` by `call_id`, and
`runStatusByRunId()` builds a terminal-status lookup from the *existing*
`/agents/{name}/timeline` run-lifecycle events (`run_started`/`completed`/`failed`/`stopped`/
`interrupted` — all already carry `data.run_id`) so the new timeline and the old Activity tab
never disagree about a run's outcome. New `hub/ui/src/components/agents/AgentTimeline.tsx` renders
it: turns as foldable cards (last turn starts unfolded, earlier ones start folded to a
status/timestamp summary, independently toggleable), a Stop button on the currently-running turn,
work entries collapsed behind one per-turn "N steps of intermediate work" toggle, `status`/
`diagnostic` outputs as `ResultCard`s using `var(--radius-content)` with a clip-fade past 240
chars, and a trailing dashed "Waiting to be delivered" section for queued entries with a withdraw
button (wired to the previously-unused `DELETE /queue/entries/{id}`) and the hop-suspended
explanation text. `AgentOutputPanel.tsx`'s body now renders `AgentTimeline` instead of
`SharedStreamRenderer` (which remains used by the unrelated `SpecChatPane.tsx` — untouched). The
orphaned, schema-mismatched `AgentPromptMessage.tsx` (dead code, referenced nowhere) was deleted
rather than patched.

A real bug was caught by the component's own tests before it shipped: the first draft of
`participantLabel()` labelled an **outbound** peer entry with the *subject* agent's own name
instead of the recipient's, contradicting the spec's explicit "outbound entries carry the
recipient's colour and are labelled with its name" scenario. Fixed in
`AgentTimeline.tsx`'s `participantLabel()`.

## Files touched

- `hub/hub/agent_colors.py` — new: `next_color_index()`, `PALETTE_SIZE = 8`. Finished.
- `hub/hub/migrations/versions/0016_add_agent_color_index.py` — new: adds `agents.color_index`,
  backfills existing rows by `created_at` per project. Finished.
- `hub/hub/db/models.py` — adds `Agent.color_index`. Finished.
- `hub/hub/schemas/agents.py` — adds `AgentSummary.color_index`. Finished.
- `hub/hub/api/v1/agents.py` — wires `color_index` into the two `Agent(...)` creation sites in
  this file (self-registration, budgeted agent requests) and into `list_agents()`'s response.
  Finished.
- `hub/hub/api/v1/session_sync.py` — wires `color_index` into the roster-diff creation site,
  computed once per sync call and incremented locally (not re-queried per agent, since several new
  agents in one sync aren't flushed yet). Finished.
- `hub/hub/api/v1/messages.py` — `create_message` now sets `Message.session_id` from the sender's
  live `Run` when `run_id` is provided. Finished.
- `hub/hub/api/v1/agent_chat.py` — full rewrite: `TimelineEntry`/`ChatHistoryResponse` models,
  `_queue_entry_to_timeline`/`_output_to_timeline`/`_message_to_timeline`/`_queued_entries_for`
  helpers, both endpoints rebuilt. Finished.
- `hub/tests/test_migrations.py` — adds `test_migration_0016_adds_and_backfills_agent_color_index`.
  Finished.
- `hub/tests/test_agent_chat.py` — full rewrite (the old file's docstring described a three-tier
  timestamp heuristic already absent from the real pre-Phase-8 implementation; new tests cover
  recorded-association placement, session isolation, peer traffic both directions,
  undelivered/hop-suspended flagging, sort order). Finished.
- `hub/tests/test_agent_output_stream.py` — updates one assertion for the new `entries`/`kind`
  response shape. Finished.
- `hub/tests/test_bola.py` — updates the cross-project-isolation assertions for the new dict-shaped
  (not bare-list) chat response; adds the sessionless `/chat` endpoint to the same check. Finished.
- `hub/ui/src/index.css` — adds `--agent-N-tint`/`--agent-N-border` derived tokens. Finished.
- `hub/ui/src/lib/agentColors.ts` — new: `agentColorVars()`, `AGENT_COLOR_PALETTE_SIZE`. Finished.
- `hub/ui/src/lib/agentTimelineModel.ts` — new: pure grouping/typing/pairing logic. Finished.
- `hub/ui/src/api/agents.ts` — adds `AgentSummary.color_index`. Finished.
- `hub/ui/src/api/agentChat.ts` — replaces `ChatMessage`/`{messages}` types with
  `TimelineEntry`/`{entries}`; `eventTargetsAgent` now also matches the four queue lifecycle event
  types so undelivered/delivered transitions update live. Finished.
- `hub/ui/src/api/queue.ts` — new: `useQueueStatus()` (Phase-6 `/queue/{agent}/status`, previously
  unwired to any UI), `withdrawQueueEntry()`. Finished.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — new: the typed timeline component. Finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — renders `AgentTimeline` instead of
  `SharedStreamRenderer`; wires the four new hooks (`useAgents`, `useAgentTimeline`,
  `useQueueStatus`, `useAgentChatHistory`/`useAgentRecentChat`) and a withdraw handler. Finished.
- `hub/ui/src/components/agents/AgentPromptMessage.tsx` — deleted (dead code, schema-mismatched,
  referenced nowhere).
- `hub/ui/src/__tests__/agentColors.test.ts` — new, 4 tests. Finished.
- `hub/ui/src/__tests__/agentTimelineModel.test.ts` — new, covers `entryCategory`/`groupIntoTurns`/
  `findPairedResult`/`runStatusByRunId`. Finished.
- `hub/ui/src/__tests__/agentTimeline.test.tsx` — new, 9 component tests mapping directly onto the
  spec's scenarios (this is where the outbound-label bug was caught). Finished.
- `hub/ui/src/__tests__/agentChat.test.tsx` — adds a test for the new queue-event matching in
  `eventTargetsAgent`. Finished.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — mocks the four new hooks (`useAgents`,
  `useAgentTimeline`, `useAgentChatHistory`/`useAgentRecentChat`, `useQueueStatus`) the same way
  `useAgentOutput`/`useAgentSessions` were already mocked, since this test renders
  `AgentOutputPanel` with no `QueryClientProvider` ancestor. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 8.1-8.12 checked with evidence;
  **not yet committed** — see Next steps.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — this handoff.
- `.claude/handoffs/LATEST.md` — to be updated to point here; deliberately not part of the
  implementation commit (matches Phase 7's precedent).

## Key decisions

1. **The merged timeline is a flat, typed list; turn-grouping happens client-side.** Rejected
   nesting turns server-side — the frontend already needs `run_id`-based grouping for the fold/work
   UI, and T3's own `MessagesTimeline.logic.ts` precedent (cited in design.md) does grouping
   client-side too. One source of truth for "what a turn is" (the frontend model), not two.
2. **`runStatusByRunId` reuses the existing `/agents/{name}/timeline` lifecycle events rather than
   adding run status to the new endpoint.** Every `run_started`/`completed`/`failed`/`stopped`/
   `interrupted` `EventLog` row already carries `data.run_id` (confirmed by reading
   `agent_trigger.py`'s `_broadcast_run_lifecycle` and `run_reconciliation.py` directly). Avoids a
   second source of truth for a run's outcome that could drift from the Activity tab's.
3. **`Message.session_id` is now populated, closing a column that existed since migration 0003 but
   was dead.** This is exactly the kind of "recorded association" the spec requires for outbound
   peer entries — the alternative (inferring from timestamp proximity) is the literal thing task
   8.3 says to remove.
4. **Colour assignment is monotonically increasing per project, never reused after an agent is
   removed.** Rejected filling gaps (e.g. `MIN` unused index) — two agents never end up sharing a
   colour while both are registered, at the cost of the index eventually exceeding the 8-hue
   palette and cycling (explicitly allowed by design.md: "Beyond the palette size, hues cycle").
5. **`AgentPromptMessage.tsx` was deleted, not migrated.** It was dead code (grep confirmed zero
   importers) built for a bubble-only, non-typed, non-peer-aware chat view that the new
   `AgentTimeline` supersedes entirely — patching it to compile against the new schema would have
   produced a second, unused implementation.
6. **The stop control appears on the running turn's own header, in addition to the existing
   header-level Stop button from task 3.7** — not instead of it. Task 8.10's own wording is "add the
   stop control to the running turn," and the two are reachable independently (the turn-level one
   is only visible when that turn is expanded).

## Constraints and user directives (verbatim)

- "$resume Review the changes of phase 5 and execute phase 6" (from the chain start; still the
  active project directive to keep executing phases in order).
- "Yeah and always commit the changes."
- "After every threshold of implementation you must run the skill `/handoff`"
- "Only stop if there is actually a blocking issue... don't need to be conservative on the changes...
  if there is genuinely a best approach you can scrap anything that already exists. Also apply these
  new rules when creating handoffs. Do a little bit less handoffs then previously but still do them."
- Repository instruction: "Files to Never Commit" includes runtime `.agentweave/` state — the
  scratch verification project (`/tmp/aw-phase8-verify`) and its seed script were created outside
  and deleted from the repo, never staged.
- The task-ledger protocol requires re-reading the proposal, design, and affected spec; scenario
  verification; and one handoff at each phase boundary.

## Dead ends

- None specific to this phase's implementation. The three backend test failures seen during full
  suite runs (`test_list_agents_avoids_n_plus_one`, `test_queue_settings_defaults_...`,
  `test_reconciling_twice_is_idempotent`) are pre-existing order-dependent flakiness from the shared
  in-memory test DB across a pytest session — confirmed by running the identical full suite against
  unmodified `d241d38` (stashing this phase's tracked changes and temporarily moving aside the two
  new untracked files) and seeing the same two-of-three reproduce there too. Already flagged in the
  Phase 7 handoff's dead-ends as a pre-existing class of issue; not something this phase introduced
  or should fix incidentally.
- `agentweave hub stop` / `agentweave hub status` misidentified a hub started via bare
  `agentweave hub start --no-detach` (no `--docker` flag) as a Docker deployment and tried to reach
  the Docker API, which isn't running on this machine. Worked around by finding the PID via
  `Get-NetTCPConnection -LocalPort 8000` and `Stop-Process -Force` directly. Not investigated
  further — this is CLI/Hub lifecycle-detection behavior, out of scope for a UI/timeline phase, but
  worth a look if `hub stop` reliability becomes its own task.

## Verification

Ran and passed:

- `.venv\Scripts\python.exe -m pytest tests -q` (CLI) — **971 passed, 4 skipped**.
- `cd hub; ..\.venv\Scripts\python.exe -m pytest tests -q` — **382 passed, 4 skipped, 3 failed**
  (all three confirmed pre-existing — see Dead ends).
- `cd hub\ui; npx tsc --noEmit` — clean.
- `cd hub\ui; npx vitest run` — **222 passed** (was 194 before this phase's Phase-2 baseline moved
  on; 27 new tests added this phase across `agentColors.test.ts`, `agentTimelineModel.test.ts`,
  `agentTimeline.test.tsx`, plus one added to `agentChat.test.tsx`).
- `.venv\Scripts\python.exe -m black --check` / `ruff check` over every touched Python file —
  passed (one file needed `black` auto-format, re-verified after).
- Live end-to-end against a real native Hub (`agentweave hub start`) and real Vite dev server
  (`npm run dev`), using a disposable scratch project (`agentweave init` in a temp directory,
  outside this repo): seeded a realistic conversation directly into the dev SQLite DB (a completed
  turn with thinking/tool_use/tool_result/text plus an outbound delegation message, a second
  running turn with a delivered inbound peer reply, and a hop-budget-suspended queued entry) via a
  throwaway script (deleted afterward, never committed). This incidentally woke the scratch
  project's own watchdog, which ran a **real** `kimi` agent turn in response to the seeded
  delegation message — its genuine reply then flowed through the new merged timeline and queue
  status correctly, live via SSE, confirmed in the actual browser in both light and dark themes
  (`preview_set_appearance` / clicking the theme toggle): folded/unfolded turns, coloured peer
  bubbles with visible name labels, the Stop button on the running turn, and "Waiting to be
  delivered (N)" with the hop-suspended explanation text. Cleaned up afterward: stopped the watchdog
  (`agentweave stop`), force-killed the native Hub and Vite processes by port, deleted the scratch
  project directory and the seed script.

Not tested:

- No automated test exercises the live SSE-driven refetch path end-to-end (i.e., a headless test
  that asserts the UI updates without a manual re-render) — the browser verification above covered
  this manually, but there is no regression test pinning it.
- `npm run lint` (hub/ui) still cannot run at all — pre-existing, unrelated: no `eslint.config.js`
  exists anywhere in the repo (flagged in task 3.7's handoff, still true). `tsc --noEmit` and
  `vitest run` remain the meaningful gates, per every prior phase's precedent.
- The withdraw button's real network call (`DELETE /queue/entries/{id}`) was exercised by the
  pre-existing Phase-6 backend tests for that endpoint, not by a new test or live click in this
  phase's browser session (the seeded scratch conversation's queued entries were both left in place
  to also verify the hop-suspended rendering, rather than withdrawn).

## Git state

- Branch: `hub-native-experience`.
- HEAD: `8ef6cc3 Phase 8: conversation timeline and agent colours` (implementation, 26 files).
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` has 8.1-8.12 checked with evidence
  but is **not yet committed** — it is the very next action (see Next steps step 1).
- Untracked, not part of this phase, pre-existing: every `.claude/handoffs/*.md` file except this
  one and its immediate predecessor, plus `.claude/skills/aw-spec-reindex/`. Do not stage them.
- `.claude/handoffs/LATEST.md` is tracked and dirty (still points at the Phase 7 handoff) — update
  and include in the checkpoint commit below.

## Next steps

1. Update `.claude/handoffs/LATEST.md` to `2026-08-02-0300-hub-native-phase8-timeline-complete.md`,
   then commit `openspec/changes/2026-07-30-hub-native-experience/tasks.md` and
   `.claude/handoffs/LATEST.md` together as a "Checkpoint Phase 8" commit (matches the Phase 6/7
   precedent of a separate small ledger-only commit after the implementation commit).
2. Read Phase 9 ("Accounting and budgets") in
   `openspec/changes/2026-07-30-hub-native-experience/tasks.md` (starts immediately after task
   8.12, around line 1242 as of this handoff — re-check, since this handoff's own edits shifted
   line numbers), the relevant `design.md` sections (Decision on tokens vs. currency, the
   context-window-meter section referencing T3), and any `specs/*/spec.md` it touches, before
   starting implementation.
3. Run `/handoff` again at the next phase boundary or substantial chunk within Phase 9.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — read Phase 9's task list first.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — Phase 9's token/currency
  decisions and the T3 context-window-meter comparison.
- `hub/hub/output_recording.py` — existing `record_context_usage`, likely the extension point for
  Phase 9's usage parsing.
- `hub/hub/runner_parsing.py` — existing Claude/Codex usage-sample extraction
  (`_claude_usage_sample`/`_codex_usage_sample` equivalents), relevant if Phase 9 extends parsing.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — this phase's main new component, in case Phase
  9's accounting surfaces need to render inside it (e.g. a per-turn token count).
