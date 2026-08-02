# Handoff: Composer extraction and draft-store phase-3 chunk complete

**Date:** 2026-08-02T22:53:39+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `ab91db9`
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** `.claude/handoffs/2026-08-02-2145-running-agent-composer-complete.md`
**Status:** chunk complete

## Goal

Make the AgentWeave conversation the primary workspace and let operators talk to a running agent,
per `openspec/changes/2026-08-02-agent-conversation-workspace/`. This chunk covers the start of
Phase 3 ("Composer"): extracting the textarea/send control into its own component with bounded
autosizing, and giving it a project- and conversation-scoped draft store so unsent text survives
navigation, reload, and storage failure without leaking between conversations.

## Current state

Tasks 3.1–3.3 are implemented and verified; tasks 3.4–3.11 (control-row/overflow-menu rework,
provider-session-selector replacement, autoscroll-from-scroll-position, context-usage placement,
banner stack) are **not started**. Task 0.1 (explicit backend contract/migration/lifecycle test
coverage for `Conversation`) remains the one open gap from phase 0, unchanged this chunk.

`hub/ui/src/components/agents/Composer.tsx` is a new self-contained component owning its own text
state, its own in-flight `submitting` flag (independent of `AgentOutputPanel`'s `isSending`, which
still gates the handoff/deliver-now actions only), and draft load/debounced-save/flush-on-unmount.
It is rendered from `AgentOutputPanel` keyed by `${agent.name}::${conversationId ?? '__new__'}` so
a conversation switch remounts it — that remount boundary is what makes "load draft on mount" /
"flush draft on unmount" correct without tracking identity changes mid-life inside the component.

`hub/ui/src/lib/composerDrafts.ts` stores all drafts under one localStorage key
(`aw.composer.drafts.v1`) as a flat `{ "project::agent::conversationId" -> text }` map, mirroring
the bounded-persistence pattern in `hub/ui/src/components/spec/specPreferences.ts`. Reads and
writes are wrapped in try/catch and degrade to empty/no-op — never throw.

`AgentOutputPanel.tsx` lost its own `message`/`setMessage` state, `handleSend`, and `handleKeyDown`;
it now exposes `handleComposerSubmit(text): Promise<void>` (same trigger/prefix/notice logic as the
old `handleSend`, minus the text-state bookkeeping Composer now owns) and passes it as `onSubmit`.
The `submissionError` banner and `session-continuity` text are unchanged and still rendered by
`AgentOutputPanel` — Composer signals failure only by rejecting the `onSubmit` promise, which is
enough for it to restore its own typed text; it does not render the banner itself (that stays a
`AgentOutputPanel` concern until task 3.9 formalizes a banner stack).

## Files touched

- `hub/ui/src/lib/composerDrafts.ts` — new; `getComposerDraft`/`setComposerDraft`/`clearComposerDraft`
  against one namespaced localStorage key; finished.
- `hub/ui/src/components/agents/Composer.tsx` — new; extracted textarea+send button, bounded
  autosizing (`COMPOSER_MIN_ROWS=3`, `COMPOSER_MAX_HEIGHT_PX=240` i.e. 12 rows × 20px), own
  submitting lock, draft load/debounce-save/flush-on-unmount/cancel-before-clear; finished.
- `hub/ui/src/__tests__/conversationComposer.test.tsx` — new; 9 tests covering resting/maximum
  height, draft survival across unmount+remount (navigation and reload are both modelled this way),
  isolation between two conversations of one agent, isolation between two projects for the
  not-yet-created-conversation key, clear-on-success with no delayed-write race, restore-on-failure,
  and storage-unavailable degradation; finished, all passing.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — removed `message`/`setMessage`/`handleSend`/
  `handleKeyDown`/`submissionLocked`; added `handleComposerSubmit` and renders `<Composer .../>` in
  place of the old inline textarea+button; now also destructures `projectId` from `useConfigStore`;
  finished for this chunk.
- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — 3.1, 3.2, 3.3 checked off
  from real passing evidence; finished for this chunk.
- All other files carried in this session's checkpoint commit `ab91db9` (phases 0–2, backend
  conversation model/migration/routing, navigation shell, running-composer lock removal) are
  unchanged this chunk — see that commit for their own history; nothing else was touched.

## Key decisions

1. **Composer is keyed by `agent::conversationId` from the parent, not self-tracking identity
   changes.** Design.md's draft algorithm reads as "load on mount, flush on unmount"; giving the
   component a stable per-conversation lifecycle via React `key` makes that literal instead of
   requiring an internal `useEffect` on identity change (which would also need to distinguish
   "identity changed" from "same identity, closure now stale" for the debounce timer — the key
   approach sidesteps that class of bug entirely).
2. **The debounce timer is cancelled explicitly at submit-start, before the optimistic clear.**
   This is what prevents the race in design.md point 4: without it, a timer scheduled from the last
   keystroke (holding the full pre-submit text) could still fire after `clearComposerDraft` runs on
   success, resurrecting the just-submitted text in storage.
3. **Composer manages its own `submitting` flag; `AgentOutputPanel`'s `isSending` is left wired only
   to the handoff/deliver-now handlers, not to composer submission.** This matches the phase-2
   decision that "composer submission lock is separate from conversation-control lock." No existing
   test asserted that a plain composer send disables the conversation selector, and design.md's
   requirement is scoped to the composer's own text/submit controls, so this was safe to narrow
   rather than thread a second flag through both components.
4. **Scope for this chunk is exactly tasks 3.1–3.3.** The selector, handoff button, fold-all button,
   and autoscroll toggle in `AgentOutputPanel`'s footer are untouched — those belong to tasks
   3.4–3.9 (control-row/overflow-menu rebuild, provider-session-selector removal, autoscroll-from-
   scroll-position, banner stack), not this chunk.
5. **Row/height constants are fixed pixel values (`COMPOSER_ROW_HEIGHT_PX = 20`), not measured from
   the DOM.** jsdom does not perform real layout, so tests assert against the same exported
   constants the component uses, and the `rows` HTML attribute (which jsdom does reflect
   correctly) rather than computed pixel heights for the "at least 3 rows at rest" scenario.
6. **Committed the entire accumulated span since `b443a8a`** (phases 0–2 plus this chunk) as one
   checkpoint commit `ab91db9`, after asking the user — prior handoffs back to phase 0 had
   deliberately left the tree uncommitted, which conflicted with the user's standing "always commit
   checkpoints" preference recorded in memory, so I surfaced the conflict via `AskUserQuestion`
   rather than guessing. User chose "one checkpoint commit now."

## Constraints and user directives (verbatim)

- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "This will become local only like T3 but with spec and inter agent comunications."
- "continue without using resume" — **superseded this session**: the user explicitly typed `$resume`
  to start this session, so the resume skill was used as instructed. Treat this line as historical
  context, not a live prohibition, unless the user restates it.
- (From persistent memory, not this session's chat) "commit each completed task/checkpoint without
  asking first" — this session deviated by asking once, because the pending diff spanned multiple
  already-"completed" phases with no clean per-phase split; the user's answer ("one checkpoint
  commit now") is the resolution, not a standing new rule. Default back to committing without
  asking for the next (cleanly-scoped) checkpoint.

## Dead ends

- None new this chunk. (Phase-2 dead ends are recorded in the previous handoff and remain valid:
  `npm test -- --runInBand` is invalid for Vitest; `ruff` is unavailable in this environment. Also
  newly confirmed this chunk: `npm run lint` in `hub/ui` fails with "ESLint couldn't find an
  eslint.config.js file" — pre-existing environment/config issue, not something this chunk broke;
  do not attempt to fix it as a side quest.)

## Verification

- `npx vitest run src/__tests__/conversationComposer.test.tsx` (from `hub/ui`) — confirmed RED
  first (import of not-yet-created `@/components/agents/Composer` failed), then GREEN after
  implementation: 9/9 passed.
- `npx vitest run` (full suite, from `hub/ui`) — 30 files, 243 tests passed (up from the 234 the
  prior handoff recorded — the +9 are the new composer suite; no regressions). The `Error: boom`
  lines in the output are expected console noise from the pre-existing `ErrorBoundary.test.tsx`.
- `npm run build` (from `hub/ui`) — `tsc && vite build` passed; only the pre-existing
  `eventSummary.ts` duplicate-case warning remains, unrelated to this chunk.
- `npm run lint` (from `hub/ui`) — **failed on missing `eslint.config.js`**, an environment issue
  unrelated to this chunk's code; not fixed, flagged above as a dead end.
- `openspec validate --all --strict --no-interactive` (from repo root) — 14 passed, 0 failed.
- `git diff --check` was not re-run this chunk (only the two pre-existing CRLF warnings on umbrella
  files appeared during `git add`, unchanged from before).

Not tested this chunk: live browser interaction with the new Composer (no visual/behavioral check
of the actual autosizing in a real browser, only jsdom-mocked `scrollHeight`); backend (unchanged);
PostgreSQL migration; the phase-0 task-0.1 coverage gap remains open and untouched.

## Git state

Branch `hub-native-experience`, HEAD `ab91db9`, **clean** (working tree matches HEAD, nothing
staged or unstaged). No upstream tracking branch configured (`no upstream` from
`git log origin/...`). Not pushed. Never use `git add -A` — stage paths explicitly; the repo
carries deliberately-untracked-until-committed `.claude/handoffs/` scratch (all of which is now
committed as of `ab91db9`, but future sessions will accumulate more before their own checkpoint).

## Next steps

1. Re-read `design.md`'s "Control placement" algorithm and the "Only high-frequency controls remain
   visible" / "Conversation identity is readable without exposing provider identity" requirements in
   `specs/agent-conversation-workspace/spec.md`, then write the failing control-placement test spec
   (task 3.4) in a new or extended test file: resting control set idle vs. running, absence of the
   removed controls (provider-session selector, handoff button, fold-all, scroll toggle as
   standalone visible controls), full keyboard operability of the overflow menu including focus
   return on dismissal, and unavailable actions shown disabled with a stated reason.
2. Build the composer control row and keyboard-operable overflow menu (task 3.5): submit,
   active-agent indicator, context usage, and — only while running — stop, in the row; new
   conversation, conversation selection, handoff, fold all, and agent details in a fixed-order
   overflow menu. Agent details must open without unmounting or navigating away from the
   conversation.
3. Replace the provider-session `<select>` in `AgentOutputPanel.tsx` with AgentWeave conversation
   selection inside that overflow menu (task 3.6), keeping continuity visible as human-readable text
   (the existing `session-continuity` region) and provider IDs confined to details/diagnostics;
   preserve the successor-conversation handoff state machine tested in `agentHandoff.test.tsx`.
4. Remove the pause/resume-scroll button and drive autoscroll from scroll position instead (task
   3.7); place `ContextUsageIndicator` in the new control row (task 3.8, everything it needs already
   exists per design.md's evidence table — only placement remains); build the banner stack (task
   3.9) generalizing the current single `role="alert"` region.
5. Verify tasks 3.4–3.9 together (task 3.10), run `/handoff` (task 3.11), then proceed to phase 4
   (regression re-pointing and umbrella annotation) per `tasks.md`.
6. Separately, close task 0.1 (backend `Conversation` contract/migration/lifecycle tests) — it has
   been open since phase 0 and has no dependency on phase 3's UI work, so it can be picked up in
   parallel whenever convenient.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — task list and phase-3
  working protocol.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — "Control placement" and
  "Submitting composer input" algorithms, key decisions, evidence/coverage-limits table.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — current footer/header structure that tasks
  3.4–3.9 will restructure around the new `Composer`.
- `hub/ui/src/components/agents/Composer.tsx` — the component tasks 3.5/3.8/3.9 will extend with
  the control row, context-usage indicator, and banner stack.
- `hub/ui/src/lib/composerDrafts.ts` — draft store the overflow-menu "new conversation" action must
  keep working with once conversation selection moves off the removed `<select>`.
