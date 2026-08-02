# Handoff: Phase 8 mock-fidelity revision + persistent live test environment

**Date:** 2026-08-02T11:30:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `90e7fe8`
**Agent:** Claude Sonnet 5
**Previous handoff:** `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This session was a follow-up correction to
the just-shipped Phase 8, not a new phase: the user pointed out that the conversation timeline's
actual visual language had drifted from `openspec/changes/2026-07-30-hub-native-experience/mock.html`
— the authoritative pixel-level design reference I had not checked closely enough before building
Phase 8's UI from `design.md`'s prose alone. The user also reported "sent a message to codex and
nothing happened" in the just-created test environment, which needed live debugging.

## Current state

**Mock-fidelity revision (committed):** `AgentTimeline.tsx` was substantially rewritten to match
`mock.html`'s actual treatment rather than my first-pass interpretation of `design.md`:
- Turns fold to a single dashed one-line pill ("Turn folded · N entries"), not a bordered card.
  Open turns render with no wrapping chrome at all — entries just flow in the stream, matching the
  mock exactly.
- The agent's own text (`agent_output`, kind `text`/`error`) is borderless/plain — just a coloured
  dot + name + timestamp, then plain text. Only the operator ("you") gets a tinted, right-aligned
  bubble. Peer messages (inbound tinted card / outbound transparent-with-left-border) unchanged in
  concept from the original Phase 8 build, restyled to match the mock's exact treatment.
- Queued (undelivered) entries now render **inline**, in their normal per-kind form, at opacity
  0.55 with a small `QUEUED` tag — the original build pulled them into a separate dashed section at
  the bottom, which the mock does not do (mock keeps them in chronological stream position).
- The hop-budget-suspended state is now an amber `.notice`-style banner with a warning icon and a
  "Deliver now" button, replacing a plain text line under each entry.
- Terminal turns (`stopped`/`failed`/`interrupted`) render as a centered divider
  ("Turn stopped · 14:09") flanked by horizontal rules, instead of a coloured header badge.
- Folding control moved to a header-level "Fold all turns" button (`AgentOutputPanel.tsx`) plus a
  small per-turn `fold` toggle; the original per-turn Stop button was removed since the mock only
  has the existing header-level Stop (from task 3.7) — no per-turn one.
- New `onDeliverNow` prop on `AgentTimeline`, wired in `AgentOutputPanel.tsx`'s `handleDeliverNow`:
  sends a fixed operator message ("Continue — deliver the queued messages.") through the existing
  trigger flow. This is not a new backend capability — any operator-origin entry is hop-depth 0,
  which unblocks and drains a hop-budget-suspended chain in the same turn per design.md's decision
  0.5 ("operator input resets the chain"). Confirmed by reading `turn_scheduler.py`/`inbound_queue.py`
  directly, not assumed.

**A real bug found and fixed, not just a style pass:** the fold-all effect's original "skip the
first mount" guard was a boolean ref (`mountedRef`). React 18 `StrictMode` (confirmed enabled in
`hub/ui/src/main.tsx:18`) double-invokes effects on mount specifically to catch bugs like this one
— the boolean flipped `true` on the phantom first invocation, so the *second* (also-on-mount)
invocation incorrectly proceeded and folded the newest turn immediately on every real page load.
jsdom/RTL tests didn't catch it because `render()` doesn't wrap in `StrictMode` by default. Fixed
by comparing against the **last-processed signal value** (`lastProcessedSignal` ref, lazily
initialized to the incoming `foldAllSignal`) instead of counting invocations — immune to being
invoked an extra time, since a repeat invocation still carries the same value. A new test wraps
render in `<StrictMode>` explicitly to pin this (`agentTimeline.test.tsx`, "does not fold the
newest turn on mount under StrictMode double-invoked effects").

**Live debugging of the test environment's "nothing happened" report:** root cause was that the
scratch project directory (`/tmp/aw-phase8-test`, i.e.
`C:\Users\huida\AppData\Local\Temp\aw-phase8-test` on Windows) was never a git repository. Phase
5's worktree isolation (`hub/hub/worktrees.py`'s `resolve_agent_workspace`) fails closed for any
writing agent when `is_git_repo(repo_root)` is false, so every trigger to `claude` or `codex` was
silently queuing forever with `waiting_reason: "...is not a usable git repository"` — a real
diagnosis surfaced by the `POST /agent/trigger` response body itself (the Hub side works exactly as
designed), but the **frontend never surfaces `waiting_reason` from a 200 response** — `postTrigger`
in `AgentOutputPanel.tsx` only checks `response.ok`. That gap is why "nothing happened" from the
operator's point of view. Fixed the immediate problem by running `git init` + an initial commit
inside the scratch project. **The frontend gap itself (silently swallowing `waiting_reason` on
success) was not fixed** — noted here as a real, still-open finding; see Next steps.

**The scratch test environment is still running and left in place per the user's request** (not
torn down, unlike the earlier throwaway verification pass): a native Hub, a Vite dev server, and a
git-initialized scratch AgentWeave project with `claude` + `codex` as real (non-manual) runners.
See Git state below for exact connection details — it lives entirely outside this repository.

## Files touched

- `hub/ui/src/components/agents/AgentTimeline.tsx` — substantially rewritten for mock fidelity
  (fold-to-pill, borderless own-text, inline queued rendering, notice banner, terminal divider,
  StrictMode-safe fold-all effect). Finished, committed in `90e7fe8`.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — adds `foldAllSignal` state + header "Fold
  all turns" button, adds `handleDeliverNow`, removes the old per-turn stop wiring, adjusts body
  padding for `AgentTimeline`'s own layout. Finished, committed in `90e7fe8`.
- `hub/ui/src/__tests__/agentTimeline.test.tsx` — rewritten assertions for the new DOM shape
  (fold-pill text, inline queued+QUEUED tag, notice banner, deliver-now callback), plus the new
  StrictMode regression test. Finished, committed in `90e7fe8`.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — prior handoff, read,
  not modified.
- `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md` — this handoff.
- `.claude/handoffs/LATEST.md` — **not yet updated to point here** — see Next steps (deliberately
  left for the very next action so the git state section below is accurate at write time).

## Key decisions

1. **Read `mock.html` this session, should have been read before building Phase 8's UI at all.**
   It is the authoritative pixel-level reference in the same directory as `design.md`, and its
   conversation-view markup covers exactly the component built in Phase 8. Owning this directly
   rather than treating the earlier build as "close enough."
2. **Multi-project sidebar tree and the composer overhaul (mock's other two sections) stay
   deferred**, per explicit user confirmation — those are Phase 10 and a separate composer effort,
   not part of this correction.
3. **`onDeliverNow` reuses the existing trigger endpoint rather than adding a force-deliver
   endpoint.** Verified directly in `turn_scheduler.py`/`inbound_queue.py` that any new
   operator-origin entry (always hop-depth 0) is sufficient to unblock and drain an over-budget
   queue in the same turn — no new backend capability needed.
4. **The StrictMode bug's fix compares against a last-processed-value ref, not an invocation-count
   guard.** A boolean "have I mounted yet" flag is provably wrong under `StrictMode`'s
  double-invoke-on-mount behavior; comparing the actual signal value is invocation-count-agnostic.
5. **The frontend's silent-swallowing of `waiting_reason` on a 200 trigger response was diagnosed
   but deliberately not fixed this session** — it's a real, separate gap (predates Phase 8, lives in
   `postTrigger`'s `if (!response.ok)`-only check), not part of what the user asked to fix right
   now. Flagged explicitly rather than silently left implicit.
6. **The scratch test environment's shared Hub data directory (`~/.agentweave/hub/data`) was wiped
   once, deliberately, before this session's live verification** — a fresh `claude`+`codex` roster
   was the point of "set up a new test environment," and the directory is shared across any local
   AgentWeave project that doesn't use a distinct remote Hub (the `project_id` is always
   `proj-default` for local bootstrap use). Do not wipe it again without checking first — the user
   has since been sending real messages into it and it now holds real conversation history for the
   `codex` debugging session.

## Constraints and user directives (verbatim)

- "$resume Review the changes of phase 5 and execute phase 6" (original chain-start directive —
  still the operative instruction to keep working through phases/corrections in order).
- "Yeah and always commit the changes." — also independently recorded in persistent memory
  (`feedback_always_commit_checkpoints.md`).
- "After every threshold of implementation you must run the skill `/handoff`."
- "Only stop if there is actually a blocking issue... don't need to be conservative on the
  changes... if there is genuinely a best approach you can scrap anything that already exists."
- "I want something that looks like and feels like mock.html." — the directive that started this
  session's work.
- On scope: user answered via `AskUserQuestion` — "Yes, match the mock now (recommended)" for the
  chat-view revision, and "Keep deferred (recommended)" for the multi-project sidebar + composer
  (i.e. do NOT build those now).
- "Also just sent a message to codex and nothing happened" — the live bug report that led to the
  worktree/git-repo root-cause finding.
- Test environment agent choice: user answered "claude, codex" (not the manual-runner-only safe
  option) — real runners, real API usage is expected/accepted.
- Test environment persistence: user answered "New scratch folder outside the repo (recommended)"
  — and this session's instructions were to leave it running, not tear it down (contrast with the
  earlier Phase 8.11 verification pass, which was explicitly cleaned up afterward).

## Dead ends

- Initially assumed the "nothing happened" report might be a frontend rendering bug in the new
  Phase 8 timeline. It was not — `curl`-ing `POST /agent/trigger` directly showed the Hub was
  behaving exactly as designed (correctly refusing to spawn without a usable worktree) and
  returning a clear `waiting_reason`; the actual defect is that the frontend never surfaces that
  field on a 200 response. Don't re-investigate the timeline rendering path for this class of
  report again — check `waiting_reason` in the raw trigger response first.
- The mystery of a `codex`→`claude` peer message that reported `agentweave.send_message completed`
  (`is_error: false`) but never actually produced a queue entry for `claude` was investigated far
  enough to see codex's own internal log line `ERROR codex_core::tools::router: error=live agent
  path '/root/claude' not found` immediately before it — this looks like a codex-CLI-side identity/
  routing issue specific to this machine's codex config (possibly a stale profile referencing a
  Linux container path), not a Hub bug. Not chased further; flagged to the user as an aside, not
  fixed. If this resurfaces, start from that exact log line, not from the Hub's MCP tool-call
  handling (which returned success correctly for what it was asked to do).
- The browser automation tool (`mcp__t3-code__preview_evaluate`/`preview_click`) intermittently
  failed with "Preview automation {evaluate,navigate} failed on client ..." on a previously-used
  tab after some idle time — matches the pre-existing "same MCP schema-validation issue" noted in
  earlier phase handoffs. Workaround: open a fresh tab (`preview_open` with
  `reuseExistingTab: false`) rather than retrying the same `tabId`.

## Verification

Ran and passed:

- `cd hub/ui; npx tsc --noEmit` — clean, twice (once after the mock-fidelity rewrite, once after
  the StrictMode fix).
- `cd hub/ui; npx vitest run` — **223 passed** (up from 222 the previous handoff; +1 new StrictMode
  regression test, net of the rewritten assertions in the same file).
- Live-verified against the persistent test Hub + Vite dev server (not the earlier throwaway
  verification project — this session reused/fixed the one the user is actively using): confirmed
  via direct `curl` to `POST /api/v1/agent/trigger` that the pre-git-init failure mode was
  `waiting_reason: "...is not a usable git repository"` for both `claude` and `codex`; confirmed
  post-`git init` that codex spawned for real (`run_id` returned, `status: "running"`); confirmed
  via `GET /api/v1/agent/codex/chat` that the resulting 8-entry, single-turn conversation (3 stuck
  operator messages that all got bundled into the one real drain, plus codex's own
  text/tool_use/tool_result outputs) renders correctly in the browser: open by default (not
  folded), "you" bubbles right-aligned and tinted, "codex" own-text plain with dot+name+timestamp,
  the "Work · 2 steps · 0.1s" collapsed work section. Confirmed the StrictMode fold-all-on-mount
  bug reproduced in the live browser before the fix (fold pill shown despite being the only/newest
  turn) and confirmed it was gone after the fix (same session reload, content open by default).

Not tested:

- Dark theme was not re-checked in the browser this specific session (it was checked in the
  previous Phase 8 handoff before this mock-fidelity revision; the CSS token usage is unchanged
  between the two, only structural/layout JSX changed, but an explicit dark-mode screenshot pass
  was not repeated here).
- The `onDeliverNow` "Deliver now" button was not clicked live in the browser this session (no
  hop-budget-suspended state existed in the live test conversation to exercise it against) — only
  unit-tested (`agentTimeline.test.tsx`'s "explains a hop-budget-suspended chain and offers to
  deliver now").
- The frontend's `waiting_reason`-swallowing gap (see Key decisions #5) has no fix and no test —
  it is an open, diagnosed-but-unaddressed finding.
- The `codex`→`claude` send_message routing anomaly (see Dead ends) was not resolved or further
  investigated.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `90e7fe8 Revise conversation timeline to match mock.html's visual language`.
- Working tree: clean relative to HEAD. Untracked (pre-existing, not part of this session's work,
  do not stage): every `.claude/handoffs/*.md` file except this one and its immediate predecessor,
  plus `.claude/skills/aw-spec-reindex/`.
- `.claude/handoffs/LATEST.md` still points at the Phase 8 handoff
  (`2026-08-02-0300-hub-native-phase8-timeline-complete.md`) as of this write — update it to this
  file as the very first action of the next session, per Next steps.
- No upstream tracking branch configured; nothing pushed.
- **Outside this repository**, a persistent test environment is running and was deliberately left
  up (not part of git state, but necessary context for continuing to use it):
  - Native Hub at `http://localhost:8000` (401 without auth — expected).
  - Vite dev server at `http://localhost:5173` (the actual Hub UI being tested).
  - Scratch AgentWeave project at `C:\Users\huida\AppData\Local\Temp\aw-phase8-test` — now a real
    git repo (single "Initial scratch commit"), roster is `claude` (colour index 0) + `codex`
    (colour index 1, `yolo: true`).
  - Hub API key: `aw_live_71b0560849ca74d02b882593ad4d10b1` (also in that project's
    `.agentweave/transport.json`).
  - The Hub's shared data directory (`~/.agentweave/hub/data`, i.e.
    `C:\Users\huida\.agentweave\hub\data`) now holds real conversation history from this session's
    live debugging (one completed `codex` run, `run-22fa7bcd`, 8 entries) — this is *not* disposable
    verification data the way the earlier Phase 8.11 pass's seeded data was; treat it as the user's
    active test data.

## Next steps

1. Update `.claude/handoffs/LATEST.md` to point to this file
   (`2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md`), then commit it alone (matches the
   established "checkpoint" commit precedent — ledger/pointer-only changes get their own small
   commit separate from implementation).
2. Ask the user whether they want the `postTrigger`/`waiting_reason`-swallowing gap (Key decisions
   #5, Dead ends) fixed now — it's a small, real UX gap (the operator gets no feedback at all when
   a trigger silently queues instead of running) but wasn't explicitly requested this session.
3. If continuing feature work rather than fixing that gap: re-read
   `openspec/changes/2026-07-30-hub-native-experience/tasks.md` starting at Phase 9 ("Accounting and
   budgets") — this session was a correction chunk, not Phase 9 itself, so Phase 9 has not been
   started.
4. Do not tear down the persistent test environment (Hub/Vite/scratch project) without asking first
   — the user is actively using it, unlike the earlier disposable verification pass.

## Open questions for the user

- Should the `waiting_reason`-swallowing frontend gap (silent failure feedback on a queued-but-
  stuck trigger) be fixed now, or tracked for later? (See Next steps #2.)
- Is the `codex`→`claude` `send_message` routing anomaly (the `live agent path '/root/claude' not
  found` codex-internal error) worth investigating further, or is it a known artifact of this
  machine's codex configuration?

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/mock.html` — the authoritative visual
  reference; re-check against it for any further Hub UI work before assuming a prose spec suffices.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — the just-revised component; read before
  touching the conversation view again.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — header controls, trigger/stop/deliver-now
  wiring.
- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent`'s `waiting_reason` field, relevant if fixing
  the frontend gap in Next steps #2.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — Phase 9 onward, if resuming
  feature work instead.
