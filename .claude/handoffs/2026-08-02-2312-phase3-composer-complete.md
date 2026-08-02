# Handoff: Phase 3 (Composer) complete

**Date:** 2026-08-02T23:12:01+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `85c2cca`
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** `.claude/handoffs/2026-08-02-2253-composer-extraction-drafts-complete.md`
**Status:** chunk complete — phase 3 of `2026-08-02-agent-conversation-workspace` is fully done

## Goal

Make the AgentWeave conversation the primary workspace and let operators talk to a running agent,
per `openspec/changes/2026-08-02-agent-conversation-workspace/`. This session completed all of
Phase 3 ("Composer") in one continuous chunk at the user's explicit request ("Just continue no need
for resume. Context still good. Do the entire phase 3"): tasks 3.4 through 3.11.

## Current state

Phases 0–3 of this change are now fully implemented and verified. Task 0.1 (explicit backend
`Conversation` contract/migration/lifecycle tests) is the **only** open item left anywhere in phases
0–3. Phase 4 (regression re-pointing + umbrella annotation + archive) has not been started.

The conversation footer in `AgentOutputPanel.tsx` is now, top to bottom: `ConversationControls`
(active-agent indicator, context usage, Stop-while-running, overflow-menu trigger) → `BannerStack`
(conditional) → the `session-continuity` text span (unchanged from the previous chunk) → `Composer`
(unchanged from the previous chunk). The header bar is now just back-button + agent name + status
chip — the provider-session-ID chip, the always-visible Stop/Fold-all/autoscroll-toggle buttons, and
the `<select>` conversation picker are all gone.

`ConversationControls.tsx` (new) owns a Radix `DropdownMenu` with five items in fixed order — New
conversation, one item per conversation (flat, not a submenu — see Key decisions), Handoff, Fold all
turns, Agent details — plus a Radix `Dialog` for "Agent details" that renders the pre-existing
`AgentInfoTab` (originally built for the now-unrouted `AgentsPage`/`AgentDetailPanel` master-detail
view; reused here as-is, unchanged). The dialog does not unmount the conversation underneath it and
returns focus to the overflow-menu trigger button on close via a ref + `onCloseAutoFocus`.

`BannerStack.tsx` (new) is a dumb renderer: it takes an already-ordered array of `{id, message}` and
renders each as a `role="alert"` div. `AgentOutputPanel.tsx` builds that array in one fixed
evaluation order every render — `[runFailure, streamLoss, blockedQueue]`, filtering out whichever
are inactive — so a cleared condition can never reshuffle the ones that remain. Stream loss is read
from the pre-existing `useSSEConnectionState()` (`'reconnecting'` state); blocked queue is read from
`timelineEntries.some(entry => entry.hop_budget_exceeded)`, the same flag `AgentTimeline` already
uses to render its own "deliver now" affordance on the blocked entry.

Autoscroll required almost no new logic: the effect that scrolls to bottom when `autoscroll` is true,
and the `handleScroll` handler that flips `autoscroll` based on scroll position, already existed and
were already the sole drivers of the behavior — the manual "Pause scroll / Resume scroll" toggle
button was the only piece of "not purely scroll-position-driven" left, and removing it as part of
stripping the header was sufficient to close task 3.7.

Two existing test files broke when the `<select>`/`Handoff` `<button>` were removed and were
re-pointed in this session (not deferred to phase 4's task 4.1, since the suite cannot be left red at
a phase boundary): `agentHandoff.test.tsx` now opens the overflow menu and reads an
`onConversationChange` spy instead of a combobox's `.value`; `agentRunningComposer.test.tsx`'s one
`getByRole('combobox')` synchronization point became a `session-continuity` text-content wait.

## Files touched

- `hub/ui/src/components/agents/ConversationControls.tsx` — new; the control row + overflow menu +
  agent-details dialog; finished.
- `hub/ui/src/components/agents/BannerStack.tsx` — new; presentational ordered-banner renderer;
  finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — header stripped to back+name+status; footer
  rebuilt around `ConversationControls`/`BannerStack`; `sessionId`/`useCopy` derivation removed
  (was only for the deleted chip); added `useSSEConnectionState`, the `banners` array, and the
  `selectConversation` helper (replaces the old `<select>`'s inline `onChange`); finished.
- `hub/ui/src/components/common/Icon.tsx` — added `more_vert`, `hourglass_top`, `move_up`, `link`
  mappings (the latter three were already referenced by the pre-existing `session-continuity` icon
  but were silently missing from the icon map — a pre-existing gap fixed in passing since this
  session was already editing the surrounding code); finished.
- `hub/ui/src/__tests__/conversationControls.test.tsx` — new; 11 tests covering resting control set
  idle/running, provider-identity hiding, fixed menu order, keyboard operability + focus return,
  conversation selection from the menu, disabled-with-reason, agent details non-navigating +
  focus-return, context-usage placement (present/absent), banner stacking/clearing, and autoscroll
  scroll-position behavior; finished, all passing.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — re-pointed at the overflow menu and an
  `onConversationChange` spy in place of the removed `<select>`; finished, passing.
- `hub/ui/src/__tests__/agentRunningComposer.test.tsx` — one `combobox` wait replaced with a
  `session-continuity` text wait; finished, passing.
- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — 3.4–3.11 checked off from
  real passing evidence; finished.

## Key decisions

1. **"Conversation selection" is a flat list of menu items, not a Radix `DropdownMenu.Sub`.** A
   submenu adds hover/ArrowRight-open interaction that is fragile to drive deterministically in
   jsdom tests, and the spec only requires the items be reachable in fixed order from the overflow
   menu — it does not require nesting. Ordering requirement is satisfied by rendering "New
   conversation" then each conversation item contiguously, before "Handoff".
2. **`ConversationControls` and `Composer` stay separate components; `Composer` was not expanded to
   own the whole footer.** The previous chunk's `Composer.tsx` (textarea + send, its own submitting
   lock, its own draft persistence) was already implemented and tested; growing its prop surface to
   also own Stop/menu/details would have re-touched a component whose contract was just signed off,
   for no behavioral requirement that demanded it. `AgentOutputPanel` composes the two as siblings.
3. **Agent details reuses `AgentInfoTab` unmodified**, opened in a new Radix `Dialog` inside
   `ConversationControls` rather than building a new details view. `AgentInfoTab` already shows
   status, provider sessions (via `useAgentSessions`), roles, and stats — exactly what "provider
   binding remains available in agent details or diagnostics" requires — and it was already
   provider-agnostic (no assumption about being inside the old `AgentDetailPanel` tab shell it was
   originally built for, which is now unrouted dead code left untouched).
4. **`ConversationControls`'s own `isSending`/submission-lock story was deliberately NOT unified with
   `Composer`'s internal `submitting` flag.** They were already separate as of the previous chunk
   (see that handoff's key decision 3); this chunk did not change that boundary. `AgentOutputPanel`'s
   `interactionLocked` (built from `isSending`, used to gate Handoff/selector-equivalent actions)
   and `Composer`'s own `submitting` remain two independent locks for two independent surfaces.
5. **Discovered via debugging, not assumed: Radix `DropdownMenu.Content` does NOT auto-focus the
   first item on open in this environment/version** — focus lands on the content root itself (a
   `role="menu"` element with `tabIndex={-1}`), and the first `ArrowDown` moves it onto the first
   item. Tests account for this explicitly (see Dead ends). This is a fact about the library version
   in this repo, not an assumption to trust blindly if Radix is ever upgraded.
6. **Existing tests were re-pointed now, not deferred to phase 4 task 4.1.** Task 4.1 formally scopes
   "re-point agentChat/agentTimeline/agentTimelineEvents/agentHandoff/agentStatus/App-mount at the
   new surface" to phase 4, but leaving `agentHandoff.test.tsx` and `agentRunningComposer.test.tsx`
   red for an entire phase boundary would violate the working protocol's implicit "verification
   passes before `/handoff`" expectation. Only the two suites this phase's changes actually broke
   were touched; `agentChat`/`agentTimeline`/`agentTimelineEvents`/`agentStatus`/`App-mount` were
   untouched and still pass unmodified — phase 4's task 4.1 is about a broader systematic re-point
   sweep, which is a smaller remaining task now, not a larger one.

## Constraints and user directives (verbatim)

- "Just continue no need for resume. Context still good. Do the entire phase 3" — this session's
  explicit instruction; explains why the whole phase was done in one chunk with one handoff at the
  end rather than smaller sub-chunks with intermediate handoffs.
- "Ignore the aw-spec skills. I'm using openspec only." (carried from earlier sessions, still binding)
- "This is not a project where we user agentweave is a project where we develop agentweave." (ditto)
- "This will become local only like T3 but with spec and inter agent comunications." (ditto)
- (From persistent memory) "commit each completed task/checkpoint without asking first" — this
  session followed that directly for both commits (`85c2cca` and the prior chunk's handoff commit),
  without asking, since each was a clean, well-scoped diff — consistent with the prior handoff's note
  that the earlier ask-once was a one-time resolution for an already-tangled multi-phase diff, not a
  new standing rule.

## Dead ends

- Assumed Radix `DropdownMenu` auto-focuses the first menu item on open (matching some other
  Menu-button implementations) and wrote a test waiting for `getByRole('menuitem', {name:'New
  conversation'})` `toHaveFocus()` right after opening — the `waitFor` timed out. Built a throwaway
  debug test (`zzdebug.test.tsx`, deleted, never committed) rendering a bare `DropdownMenu` and
  asserting `document.activeElement.textContent` against a bogus probe string to force the failure
  message to reveal the real value: `"Item 1Item 2"` — i.e. the **content root**, not an item, holds
  focus on open. Fixed by sending one `{ArrowDown}` before expecting focus on the first item. See Key
  decision 5.
- First pass at the phase-3 test file used `screen.findByText('conv-old')` as a "wait for the
  conversation to settle" step in 8 different tests. This is exact-match text querying, and no DOM
  text node is ever exactly `"conv-old"` — the `session-continuity` span always wraps it (e.g.
  `"Continuing conv-old…"`). Every one of those 8 tests failed identically until replaced with
  `waitFor(() => expect(getByTestId('session-continuity')).toHaveTextContent('conv-old'))`
  (substring match).
- `npx vitest run` / `npm run build` run from the **repo root** instead of `hub/ui` fail outright
  (wrong `package.json`, wrong Vite alias resolution) or, worse, silently `npm install`s a
  transient `vitest@4.1.10` into a stray root-level `node_modules/` (visible as `npm warn exec ...
  will be installed`). This created an untracked `node_modules/` at the repo root this session,
  caught via `git status` before committing and deleted (`rm -rf node_modules`) rather than
  committed — it was never real project state, just fallout from running the wrong command in the
  wrong directory. **Always `cd hub/ui` first** — the Bash tool's working directory does not persist
  reliably across tool calls in this environment, so this must be re-verified before every
  `npm`/`npx` invocation, not assumed from a previous command in the same turn.
- `npm run lint` in `hub/ui` still fails with "ESLint couldn't find an eslint.config.js file" —
  confirmed still broken this chunk too, unrelated to any code touched here (carried forward from
  the previous handoff, not re-diagnosed).

## Verification

- `npx vitest run src/__tests__/conversationControls.test.tsx` (from `hub/ui`) — 11/11 passed after
  the two dead-end fixes above.
- `npx vitest run src/__tests__/agentHandoff.test.tsx src/__tests__/agentRunningComposer.test.tsx`
  (from `hub/ui`) — 3/3 passed after re-pointing.
- `npx vitest run` (full suite, from `hub/ui`) — **first full run: 31 files, 254 tests passed**
  (up from 243 in the previous chunk: +9 conversationControls minus the −2 net from
  agentHandoff/agentRunningComposer keeping their test counts, actually +11 new tests total since
  both re-pointed files kept the same number of `it()` blocks). A **second** full run showed
  `agentChat.test.tsx`'s `"disables the query when sessionId === NEW_SESSION_ID"` test flake
  (`fetchStatus` expected `'fetching'`, got `'idle'`) — reproduced it flaking pass/fail across two
  isolated re-runs of that file alone with **no code changes in between**, confirming it is a
  pre-existing timing-based flake (`await new Promise(r => setTimeout(r, 10))` racing React Query's
  fetch-start) in a file this session never touched, not a regression. Left as-is; flagging here per
  the "distinguish ran-and-passed from not-run" rule rather than silently re-running until green.
- `npm run build` (from `hub/ui`) — `tsc && vite build` passed after fixing two `session_id: null`
  → `session_id: undefined` type errors in the new test file's fixtures (`AgentOutputLine.session_id`
  is `string | undefined`, not nullable). Only the pre-existing `eventSummary.ts` duplicate-case
  warning remains, unrelated.
- `npm run lint` (from `hub/ui`) — still fails on missing `eslint.config.js`; see Dead ends.
- `openspec validate --all --strict --no-interactive` (from repo root) — 14 passed, 0 failed.
- `git status --short` before committing — caught and removed the stray root `node_modules/`; final
  status showed exactly the 8 intended files, nothing else.

Not tested this chunk: live browser interaction with the new overflow menu/dialog (only jsdom +
Radix, no real-browser check of animation/positioning); backend (unchanged); PostgreSQL migration;
the phase-0 task-0.1 coverage gap remains open and untouched; the pre-existing `agentChat.test.tsx`
flake was not fixed (out of scope — touches no file this session changed).

## Git state

Branch `hub-native-experience`, HEAD `85c2cca`, **clean** (working tree matches HEAD, nothing staged
or unstaged). No upstream tracking branch. Not pushed. Commits this session, oldest first:
`ab91db9` (phases 0–2 checkpoint), `dc17c27` (previous chunk's handoff), `85c2cca` (this chunk,
phase 3 complete). Never use `git add -A` — stage paths explicitly.

## Next steps

1. Re-read `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` phase 4 and
   `design.md`'s reconciliation rule, then start task 4.1: re-point `agentChat.test.tsx`,
   `agentTimeline.test.tsx` (or wherever that suite lives — search for it), `agentTimelineEvents`
   equivalent, `agentStatus` equivalent, and `App-mount.test.tsx` at the new surface if they need it
   — changing only how the surface is mounted/queried, not what they assert. Most of these were
   **not** touched by phase 3's changes and may already pass unmodified (confirm by running them);
   only re-point what actually breaks.
2. Task 4.2: run the full suite again and confirm every continuity/handoff/stop/withdraw/
   deliver-now assertion still passes and queue semantics are untouched (this should already be true
   given the current 254/255-ish passing state, but re-verify explicitly as its own task per the
   working protocol rather than inferring it from phase 3's verification).
3. Task 4.3: annotate the superseded phases of
   `openspec/changes/2026-07-30-hub-native-experience/tasks.md` naming this change as the successor,
   per the reconciliation rule in this change's `design.md`. Do not mark any umbrella task complete —
   only real implementation closes a task, and it already closed here.
4. Task 4.4: sync `specs/agent-conversation-workspace/` and `specs/agent-conversation-handoff/` into
   `openspec/specs/`, then archive this change.
5. Task 4.5: `/handoff`.
6. Separately, close task 0.1 (backend `Conversation` contract/migration/lifecycle tests) — open
   since phase 0, no dependency on phases 1–4's UI work, can be picked up independently.
7. Separately, consider whether the pre-existing `agentChat.test.tsx` flake (see Verification) is
   worth a targeted fix — it is not blocking, but it will keep intermittently failing full-suite runs
   until someone either increases its wait or asserts on something less timing-sensitive.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — phase 4 task list.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — the reconciliation rule
  (for task 4.3) and the umbrella slice table.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — the umbrella whose superseded
  phases task 4.3 must annotate.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — the rebuilt surface phase 4's re-pointed
  tests will mount and query.
- `hub/ui/src/components/agents/ConversationControls.tsx` — new component phase 4's tests may need
  to interact with (overflow menu) if any of the suites being re-pointed touch handoff/selection.
